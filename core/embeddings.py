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
from functools import lru_cache

from . import db
from .config import EMBEDDING_MODEL

DIMENSOES = 768  # precisa casar com vector(768) no schema


@lru_cache(maxsize=1)
def _modelo():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


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
        achados[r["hash"]] = v.tolist() if hasattr(v, "tolist") else list(v)
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
