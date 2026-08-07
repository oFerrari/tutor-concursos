"""Testes de core/ritmo_regras.py — funções puras, sem banco."""
import pytest

from core.ritmo_regras import (priorizar, sugestao_disciplina_fraca,
                                sugestao_reincidencia, sugestao_sequencia)


# --------------------------------------------------------------------------
# sugestao_sequencia

def test_sequencia_completa_de_acertos_sem_dica_dispara():
    ultimos = [("correta", 0)] * 5
    assert sugestao_sequencia(ultimos, janela=5) is not None


def test_sequencia_incompleta_nao_dispara():
    """4 tentativas para uma janela de 5 — não é a mesma coisa que 4 de 4."""
    ultimos = [("correta", 0)] * 4
    assert sugestao_sequencia(ultimos, janela=5) is None


def test_uma_dica_no_meio_quebra_a_sequencia():
    ultimos = [("correta", 0), ("correta", 0), ("correta", 1),
               ("correta", 0), ("correta", 0)]
    assert sugestao_sequencia(ultimos, janela=5) is None


def test_um_erro_no_meio_quebra_a_sequencia():
    ultimos = [("correta", 0), ("incorreta", 0), ("correta", 0),
               ("correta", 0), ("correta", 0)]
    assert sugestao_sequencia(ultimos, janela=5) is None


def test_sequencia_olha_so_a_janela_nao_o_historico_todo():
    """6ª tentativa (mais antiga) é erro, mas está FORA da janela de 5."""
    ultimos = [("correta", 0)] * 5 + [("incorreta", 0)]
    assert sugestao_sequencia(ultimos, janela=5) is not None


# --------------------------------------------------------------------------
# sugestao_disciplina_fraca

def test_disciplina_abaixo_do_teto_com_amostra_suficiente_dispara():
    desempenho = [{"disciplina": "Direito Penal", "tentativas": 10, "pct_acerto": 40.0}]
    r = sugestao_disciplina_fraca(desempenho, minimo_tentativas=5, teto_pct=50.0)
    assert r is not None and "Direito Penal" in r


def test_disciplina_fraca_com_amostra_pequena_nao_dispara():
    """0% de acerto em 1 tentativa é ruído, não tendência — mesma lição do simulador."""
    desempenho = [{"disciplina": "Direito Penal", "tentativas": 1, "pct_acerto": 0.0}]
    assert sugestao_disciplina_fraca(desempenho, minimo_tentativas=5, teto_pct=50.0) is None


def test_disciplina_acima_do_teto_nao_dispara():
    desempenho = [{"disciplina": "Direito Penal", "tentativas": 20, "pct_acerto": 90.0}]
    assert sugestao_disciplina_fraca(desempenho, minimo_tentativas=5, teto_pct=50.0) is None


def test_escolhe_a_pior_entre_varias_candidatas():
    desempenho = [
        {"disciplina": "A", "tentativas": 10, "pct_acerto": 45.0},
        {"disciplina": "B", "tentativas": 10, "pct_acerto": 20.0},
    ]
    r = sugestao_disciplina_fraca(desempenho)
    assert "B" in r and "A" not in r


def test_desempenho_vazio_nao_dispara():
    assert sugestao_disciplina_fraca([]) is None


# --------------------------------------------------------------------------
# sugestao_reincidencia

def test_reincidencia_acima_do_minimo_dispara():
    erros = [{"tema": "Peculato", "vezes": 4}]
    r = sugestao_reincidencia(erros, minimo_vezes=3)
    assert r is not None and "Peculato" in r


def test_reincidencia_abaixo_do_minimo_nao_dispara():
    erros = [{"tema": "Peculato", "vezes": 2}]
    assert sugestao_reincidencia(erros, minimo_vezes=3) is None


def test_lista_vazia_de_erros_nao_dispara():
    assert sugestao_reincidencia([], minimo_vezes=3) is None


def test_reincidencia_usa_o_primeiro_como_pior_sem_reordenar():
    """Contrato: quem chama já manda ordenado por vezes DESC."""
    erros = [{"tema": "Pior", "vezes": 5}, {"tema": "Melhor", "vezes": 10}]
    r = sugestao_reincidencia(erros, minimo_vezes=3)
    assert "Pior" in r


# --------------------------------------------------------------------------
# priorizar

def test_priorizar_devolve_a_primeira_nao_nula():
    assert priorizar(None, "segunda", "terceira") == "segunda"


def test_priorizar_nunca_devolve_mais_de_uma():
    r = priorizar("primeira", "segunda", "terceira")
    assert r == "primeira"


def test_priorizar_tudo_none_devolve_none():
    assert priorizar(None, None, None) is None


def test_priorizar_sem_argumentos_devolve_none():
    assert priorizar() is None
