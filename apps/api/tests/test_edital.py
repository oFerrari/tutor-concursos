"""Testes de core/edital.py — funções puras de extração, sem banco."""
from core.edital import candidatos_data_prova, extrair_topicos

TEXTO_EXEMPLO = """
1. DAS DISPOSIÇÕES PRELIMINARES considerando a Lei Complementar nº 259,
de 21 de julho de 2023.

9. DA PROVA OBJETIVA
9.1 As Provas Objetivas serão realizadas no dia 11 de outubro de 2026
(domingo), no turno da tarde.

20.1 A Prova Discursiva será realizada no dia 20 de dezembro de 2026
(domingo).
"""

TEXTO_PROGRAMATICO = """
ANEXO I CONTEÚDO PROGRAMÁTICO
1. DIREITO PENAL: 1.1 Princípios Fundamentais. 1.1.1 Legalidade e
Anterioridade. 1.2 Aplicação da Lei Penal. 1.2.1 Lei Penal no Tempo.
2. DIREITO CONSTITUCIONAL: 2.1 Direitos Fundamentais. 2.2 Organização
do Estado.
"""


def test_candidatos_data_prova_acha_a_data_certa():
    cands = candidatos_data_prova(TEXTO_EXEMPLO)
    assert len(cands) >= 2
    # a que menciona "prova objetiva" perto deve vir primeiro
    assert cands[0]["data"].isoformat() == "2026-10-11"


def test_candidatos_data_prova_ignora_citacao_legal():
    """'de 21 de julho de 2023' (citação de lei) não tem a palavra 'dia'
    antes — não deveria aparecer como candidato a data de prova."""
    cands = candidatos_data_prova(TEXTO_EXEMPLO)
    datas = [c["data"].isoformat() for c in cands]
    assert "2023-07-21" not in datas


def test_candidatos_data_prova_texto_vazio_devolve_lista_vazia():
    assert candidatos_data_prova("") == []


def test_candidatos_data_prova_sem_prova_objetiva_ainda_lista_mas_pontua_zero():
    texto = "reunião marcada no dia 5 de maio de 2027 para tratar de outro assunto."
    cands = candidatos_data_prova(texto)
    assert len(cands) == 1
    assert cands[0]["pontuacao"] == 0


def test_extrair_topicos_conta_disciplinas_certo():
    topicos = extrair_topicos(TEXTO_PROGRAMATICO)
    disciplinas = {t["disciplina"] for t in topicos}
    assert disciplinas == {"Direito Penal", "Direito Constitucional"}


def test_extrair_topicos_conta_subitens_certo():
    topicos = extrair_topicos(TEXTO_PROGRAMATICO)
    penal = [t for t in topicos if t["disciplina"] == "Direito Penal"]
    # 1.1, 1.1.1, 1.2, 1.2.1 = 4 subitens
    assert len(penal) == 4


def test_extrair_topicos_texto_sem_padrao_devolve_vazio():
    assert extrair_topicos("um texto qualquer sem numeração nenhuma.") == []


def test_extrair_topicos_ordem_e_sequencial_e_unica():
    topicos = extrair_topicos(TEXTO_PROGRAMATICO)
    ordens = [t["ordem"] for t in topicos]
    assert ordens == list(range(len(topicos)))
