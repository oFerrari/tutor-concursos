"""
Recuperação híbrida.

Três caminhos, em ordem de precisão:

1. `por_dispositivo` — o aluno citou "art. 312" ou "§1º". Busca exata por
   metadado. Nenhum vetor compete com isso em precisão, e quando ela acerta
   NÃO se acrescenta complemento semântico: encher a resposta de artigos
   parecidos só dá ao modelo material para citar fonte errada.
2. `por_rubrica` — o aluno usou o nome do crime ("concussão"). Casa contra a
   rubrica, que é mais preciso que casar contra o corpo do artigo.
3. `hibrida` — funde ranking vetorial e ranking full-text português com
   Reciprocal Rank Fusion. RRF dispensa normalizar scores de escalas
   diferentes (distância de cosseno vs ts_rank), que é o erro clássico de
   quem tenta somar os dois direto.

O braço lexical ignora palavras que existem em todo dispositivo — "art",
"parágrafo", "inciso", "caput". Sem isso, a consulta "art. 312" casa com os
437 chunks do código e o ranking vira ruído.
"""
import re

from . import db
from .embeddings import embed_consulta

RRF_K = 60  # constante de amortecimento padrão do RRF

RE_CITACAO = re.compile(r"(?i)\bart(?:igo)?s?\.?\s*(\d+[\-\wºo]*)")
GENERICOS = {"art", "arts", "artigo", "artigos", "paragrafo", "parágrafo",
             "paragrafos", "parágrafos", "inciso", "incisos", "caput",
             "lei", "codigo", "código", "cf", "cp", "cpp"}

CAMPOS = """c.id, c.texto, c.norma, c.artigo, c.paragrafo, c.rubrica, c.secao,
            c.pagina, d.titulo, d.disciplina, d.tipo"""

SQL_HIBRIDA = f"""
WITH sem AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %(emb)s::vector) AS pos
    FROM chunk
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %(emb)s::vector
    LIMIT %(k)s
),
lex AS (
    SELECT c.id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.busca, q) DESC) AS pos
    FROM chunk c, websearch_to_tsquery('portuguese', %(termos)s) q
    WHERE c.busca @@ q
    ORDER BY ts_rank_cd(c.busca, q) DESC
    LIMIT %(k)s
)
SELECT {CAMPOS},
       COALESCE(1.0 / (%(rrf)s + sem.pos), 0) +
       COALESCE(1.0 / (%(rrf)s + lex.pos), 0) AS score
FROM chunk c
JOIN documento d ON d.id = c.documento_id
LEFT JOIN sem ON sem.id = c.id
LEFT JOIN lex ON lex.id = c.id
WHERE sem.id IS NOT NULL OR lex.id IS NOT NULL
ORDER BY score DESC
LIMIT %(n)s
"""


def _termos_lexicais(pergunta: str) -> str:
    """Remove palavras presentes em todo dispositivo, que só geram ruído."""
    palavras = [p for p in re.findall(r"[\wÀ-ÿ\-]+", pergunta)
                if p.lower() not in GENERICOS]
    return " ".join(palavras) or pergunta


def por_dispositivo(pergunta: str, n: int = 4) -> list[dict]:
    m = RE_CITACAO.search(pergunta)
    if not m:
        return []
    return db.query(
        f"""SELECT {CAMPOS}, 1.0 AS score
            FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.artigo = %(art)s
            ORDER BY d.tipo = 'lei' DESC, c.norma, c.ordem
            LIMIT %(n)s""",
        {"art": m.group(1), "n": n},
    )


def por_rubrica(pergunta: str, n: int = 4) -> list[dict]:
    """Nome de crime é o jeito humano de referenciar um tipo penal."""
    return db.query(
        f"""SELECT {CAMPOS}, 1.0 AS score
            FROM chunk c JOIN documento d ON d.id = c.documento_id,
                 websearch_to_tsquery('portuguese', %(t)s) q
            WHERE c.rubrica IS NOT NULL
              AND to_tsvector('portuguese', c.rubrica) @@ q
            ORDER BY ts_rank_cd(to_tsvector('portuguese', c.rubrica), q) DESC
            LIMIT %(n)s""",
        {"t": _termos_lexicais(pergunta), "n": n},
    )


def hibrida(pergunta: str, n: int = 6, k: int = 40) -> list[dict]:
    return db.query(SQL_HIBRIDA, {
        "emb": embed_consulta(pergunta),
        "termos": _termos_lexicais(pergunta),
        "k": k,
        "n": n,
        "rrf": RRF_K,
    })


def buscar(pergunta: str, n: int = 6) -> list[dict]:
    """
    Ponto de entrada. Precisão vence recall: quando há acerto exato de
    dispositivo, devolve só ele. Contexto extra não ajuda o modelo a
    responder "o que diz o art. 312" — só o convida a citar outra coisa.
    """
    exatos = por_dispositivo(pergunta, n=n)
    if exatos:
        return exatos

    rubricas = por_rubrica(pergunta, n=3)
    if rubricas:
        # Acerto de rubrica é forte: só 2 vagas de complemento, para permitir
        # comparação entre tipos sem afogar a resposta em artigo parecido.
        vistos = {c["id"] for c in rubricas}
        extra = [c for c in hibrida(pergunta, n=4) if c["id"] not in vistos][:2]
        return rubricas + extra
    return hibrida(pergunta, n=n)


def formatar_contexto(chunks: list[dict]) -> str:
    """
    Monta o bloco de contexto com referência, para o tutor citar a fonte.

    A referência NÃO menciona parágrafo: o chunk é o artigo inteiro, e
    rotulá-lo como "§1º" porque contém um parágrafo faz o modelo atribuir
    ao §1º o que está no caput. Errar dispositivo é grave para concurseiro.
    """
    partes = []
    for c in chunks:
        ref = c["titulo"]
        if c.get("artigo"):
            ref += f", art. {c['artigo']}"
            if c.get("rubrica"):
                ref += f" — {c['rubrica']}"
        elif c.get("pagina"):
            ref += f", p. {c['pagina']}"
        partes.append(f"[{ref}]\n{c['texto']}")
    return "\n\n---\n\n".join(partes)
