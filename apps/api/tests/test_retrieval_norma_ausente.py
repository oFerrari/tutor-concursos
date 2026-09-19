"""Norma citada e ausente do corpus não pode virar acerto exato de outra norma."""
from core import retrieval


def test_norma_citada_fora_do_corpus_nao_devolve_outra_norma():
    assert retrieval.por_dispositivo("art. 1º da Lei 8.429") == []


def test_norma_do_corpus_continua_funcionando():
    r = retrieval.por_dispositivo("art. 312 do CP")
    assert r and all(c["norma"] == "CP" for c in r)
