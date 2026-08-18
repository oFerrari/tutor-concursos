"""
Embeddings locais — custo zero e os PDFs não saem da máquina.

O modelo e5 exige prefixos: "query: " para a pergunta e "passage: " para o
trecho indexado. Esquecer isso degrada a busca de forma silenciosa, então
os prefixos ficam encapsulados aqui e não no código que chama.

CACHE: o vetor é função pura de (texto, modelo). Antes de gastar CPU,
consulta-se `embedding_cache` pelo sha256 do texto. Na prática isso torna
correção de chunking barata: mudou a rubrica de 30 artigos, reprocessa 30,
não 436.
"""
import hashlib
import threading

from . import db
from .config import EMBEDDING_MODEL

VERSAO = "embeddings-v3"
DIMENSOES = 768  # precisa casar com vector(768) no schema


_TRAVA_MODELO = threading.Lock()
_MODELO = None


def _modelo():
    """Singleton do modelo, carregado UMA vez e com trava.

    Era `@lru_cache(maxsize=1)`, e isso não basta: o lru_cache memoiza o
    RESULTADO, não protege o CORPO. Duas threads que entram juntas erram o
    cache as duas e CONSTROEM o modelo as duas — e carregar o mesmo
    SentenceTransformer em paralelo estoura com `Cannot copy out of meta
    tensor; no data!`, porque o transformers inicializa os pesos no device
    `meta` e depois os move, e as duas cargas disputam esse estado.

    Não é hipótese: apareceu subindo TRÊS materiais em lote pela tela
    (`api.py` roda cada indexação em `BackgroundTasks`, ou seja, no pool de
    threads). Duas das três falharam e a primeira passou. O caminho
    interativo tem a mesma exposição — uma pergunta no tutor durante uma
    indexação chama `embed_consulta` de outra thread.

    Dupla checagem: o caminho rápido lê o global sem trava (atribuição a
    global é atômica no CPython), e só quem chega antes da primeira carga
    paga o lock."""
    global _MODELO
    if _MODELO is not None:
        return _MODELO
    with _TRAVA_MODELO:
        if _MODELO is None:
            from sentence_transformers import SentenceTransformer
            # device="cpu" explícito: a decisão documentada é "LOCAL (CPU)",
            # mas sem forçar isso o sentence-transformers autodetecta CUDA.
            # Numa GPU incompatível com o build do torch instalado, isso quebra
            # em runtime (CUDA error: no kernel image for device); numa GPU
            # compatível, usaria VRAM calado, contradizendo a decisão. CPU é
            # rápido o bastante para um modelo de 768 dim e evita as duas
            # armadilhas.
            _MODELO = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _MODELO


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _do_cache(hashes: list[str]) -> dict[str, list[float]]:
    if not hashes:
        return {}
    linhas = db.query(
        "SELECT hash, embedding FROM embedding_cache WHERE modelo = %(m)s AND hash = ANY(%(h)s)",
        {"m": EMBEDDING_MODEL, "h": hashes},
    )
    achados = {}
    for r in linhas:
        v = r["embedding"]
        # register_vector decodifica `vector` como numpy array OU como
        # pgvector.Vector dependendo da versão instalada — e a API mudou
        # entre elas (.tolist() no numpy, .to_list() no pgvector-python
        # atual; nenhum dos dois é iterável direto por list() sem isso).
        # Cobrir os três evita depender de qual versão está no ambiente.
        if hasattr(v, "tolist"):
            achados[r["hash"]] = v.tolist()
        elif hasattr(v, "to_list"):
            achados[r["hash"]] = v.to_list()
        else:
            achados[r["hash"]] = list(v)
    return achados


def _gravar_cache(pares: list[tuple[str, list[float]]]) -> None:
    for h, v in pares:
        db.query(
            """INSERT INTO embedding_cache (hash, modelo, embedding)
               VALUES (%(h)s, %(m)s, %(v)s)
               ON CONFLICT (hash, modelo) DO NOTHING""",
            {"h": h, "m": EMBEDDING_MODEL, "v": v},
        )


def embed_passagens(textos: list[str], usar_cache: bool = True,
                    relatorio: bool = False) -> list[list[float]]:
    """
    Devolve um vetor por texto, na mesma ordem. Deduplica textos repetidos
    dentro do próprio lote — no CP há artigos revogados com texto idêntico.
    """
    if not textos:
        return []
    hashes = [_hash(t) for t in textos]

    cache = _do_cache(list(set(hashes))) if usar_cache else {}
    faltantes = []
    vistos = set()
    for h, t in zip(hashes, textos):
        if h not in cache and h not in vistos:
            vistos.add(h)
            faltantes.append((h, t))

    if faltantes:
        prep = [f"passage: {t}" for _, t in faltantes]
        vs = _modelo().encode(prep, normalize_embeddings=True, batch_size=16,
                              show_progress_bar=len(prep) > 32)
        novos = [(h, v.tolist()) for (h, _), v in zip(faltantes, vs)]
        cache.update(dict(novos))
        if usar_cache:
            _gravar_cache(novos)

    if relatorio:
        print(f"    embeddings: {len(textos) - len(faltantes)} do cache, "
              f"{len(faltantes)} calculados")
    return [cache[h] for h in hashes]


def embed_consulta(texto: str) -> list[float]:
    """Consulta não vai para o cache: prefixo diferente e uso único."""
    v = _modelo().encode(f"query: {texto}", normalize_embeddings=True)
    return v.tolist()
