"""
Testes de core/chunking.taxa_colisao_artigo() — função pura.

Caso real que motivou: um livro de histórico de emendas constitucionais
reinicia "Art. 1º" a cada emenda — 90 ocorrências de "Art. 1º" num só
documento. ingest.py usa esta função para recusar ingerir isso como
--tipo lei antes de corromper citação exata.
"""
from core.chunking import taxa_colisao_artigo


def _chunk(norma, artigo):
    return {"norma": norma, "artigo": artigo, "texto": "x"}


def test_lista_vazia_e_zero():
    assert taxa_colisao_artigo([]) == 0.0


def test_todos_artigos_unicos_e_zero():
    chunks = [_chunk("CP", str(i)) for i in range(1, 11)]
    assert taxa_colisao_artigo(chunks) == 0.0


def test_um_artigo_repetido_conta_so_a_repeticao():
    """3 chunks com art. 1: o primeiro é a versão "original", só as
    duas repetições contam como colisão — por isso a taxa é 2/3, não 3/3."""
    chunks = [_chunk("CF", "1"), _chunk("CF", "1"), _chunk("CF", "1")]
    assert taxa_colisao_artigo(chunks) == 2 / 3


def test_caso_real_livro_de_emendas():
    """Reproduz a proporção real que apareceu no CF88_Livro_EC91: art. 1
    aparece 90 vezes num total de 915 chunks."""
    chunks = [_chunk("CF", "1")] * 90 + [_chunk("CF", str(i)) for i in range(2, 827)]
    taxa = taxa_colisao_artigo(chunks)
    assert taxa > 0.05  # bem acima de qualquer lei compilada legítima


def test_normas_diferentes_mesmo_numero_de_artigo_nao_colidem():
    """CP art. 1 e CF art. 1 são chaves diferentes — documento com mais de
    uma norma (não é o caso comum, mas a função não deve confundir)."""
    chunks = [_chunk("CP", "1"), _chunk("CF", "1")]
    assert taxa_colisao_artigo(chunks) == 0.0


def test_artigo_none_tambem_conta_colisao_entre_si():
    """chunk_generico() devolve artigo=None para tudo — mas essa função só
    é chamada para chunks vindos de chunk_lei(), onde None seria bug de
    parsing, não o caso normal. Documentando o comportamento mesmo assim:
    todos os None colidem entre si porque (None, None) é uma chave igual."""
    chunks = [_chunk(None, None), _chunk(None, None)]
    assert taxa_colisao_artigo(chunks) == 0.5
