"""
Recuperação híbrida.

Três caminhos, em ordem de precisão:

1. `por_dispositivo` — o aluno citou "art. 312" ou "§1º". Busca exata por
   metadado. Nenhum vetor compete com isso em precisão.
2. `hibrida` — funde ranking vetorial e ranking full-text português com
   Reciprocal Rank Fusion. RRF dispensa normalizar scores de escalas
   diferentes (distância de cosseno vs ts_rank), que é o erro clássico
   de quem tenta somar os dois direto.
3. Caso nada retorne, o chamador decide se responde sem contexto.
"""
import re

from . import db
from .embeddings import embed_consulta

RRF_K = 60  # constante de amortecimento padrão do RRF

RE_CITACAO = re.compile(r"(?i)art(?:igo)?\.?\s*(\d+[\-\wºo]*)")

SQL_HIBRIDA = """
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
SELECT c.id, c.texto, c.norma, c.artigo, c.paragrafo, c.pagina,
       d.titulo, d.disciplina, d.tipo,
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


def por_dispositivo(pergunta: str, n: int = 4) -> list[dict]:
    m = RE_CITACAO.search(pergunta)
    if not m:
        return []
    return db.query(
        """SELECT c.id, c.texto, c.norma, c.artigo, c.paragrafo, c.pagina,
                  d.titulo, d.disciplina, d.tipo, 1.0 AS score
           FROM chunk c JOIN documento d ON d.id = c.documento_id
           WHERE c.artigo = %(art)s
           ORDER BY c.norma, c.ordem LIMIT %(n)s""",
        {"art": m.group(1), "n": n},
    )


def hibrida(pergunta: str, n: int = 6, k: int = 40) -> list[dict]:
    return db.query(SQL_HIBRIDA, {
        "emb": embed_consulta(pergunta),
        "termos": pergunta,
        "k": k,
        "n": n,
        "rrf": RRF_K,
    })


def buscar(pergunta: str, n: int = 6) -> list[dict]:
    """Ponto de entrada: tenta citação explícita, depois híbrida."""
    exatos = por_dispositivo(pergunta, n=3)
    if exatos:
        vistos = {c["id"] for c in exatos}
        complemento = [c for c in hibrida(pergunta, n=n) if c["id"] not in vistos]
        return exatos + complemento[: max(0, n - len(exatos))]
    return hibrida(pergunta, n=n)


def formatar_contexto(chunks: list[dict]) -> str:
    """Monta o bloco de contexto com referência, para o tutor poder citar a fonte."""
    partes = []
    for c in chunks:
        ref = c["titulo"]
        if c.get("artigo"):
            ref += f", art. {c['artigo']}"
            if c.get("paragrafo"):
                ref += f", §{c['paragrafo']}"
        elif c.get("pagina"):
            ref += f", p. {c['pagina']}"
        partes.append(f"[{ref}]\n{c['texto']}")
    return "\n\n---\n\n".join(partes)
