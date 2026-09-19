"""O braço lexical usa a lista de palavras vazias certa (assunto.VAZIAS)."""
from core import retrieval


def test_cortesia_nao_produz_termo_lexical():
    assert retrieval._termos_lexicais("obrigado, era só isso") == ""


def test_materia_sobrevive():
    t = retrieval._termos_lexicais("peculato culposo")
    assert "peculato" in t and "culposo" in t


def test_vocabulario_juridico_nao_e_removido():
    t = retrieval._termos_lexicais("poder de polícia no direito penal")
    for termo in ("poder", "polícia", "direito", "penal"):
        assert termo in t
