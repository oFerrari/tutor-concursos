"""
Embeddings locais — custo zero e os PDFs não saem da máquina.

O modelo e5 exige prefixos: "query: " para a pergunta e "passage: " para o
trecho indexado. Esquecer isso degrada a busca de forma silenciosa, então
os prefixos ficam encapsulados aqui e não no código que chama.
"""
from functools import lru_cache

from .config import EMBEDDING_MODEL

DIMENSOES = 768  # precisa casar com vector(768) no schema


@lru_cache(maxsize=1)
def _modelo():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_passagens(textos: list[str]) -> list[list[float]]:
    prep = [f"passage: {t}" for t in textos]
    vs = _modelo().encode(prep, normalize_embeddings=True, batch_size=16, show_progress_bar=len(prep) > 64)
    return [v.tolist() for v in vs]


def embed_consulta(texto: str) -> list[float]:
    v = _modelo().encode(f"query: {texto}", normalize_embeddings=True)
    return v.tolist()
