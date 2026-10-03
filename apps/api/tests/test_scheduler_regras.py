"""
Testes de core/scheduler_regras.py — só funções puras, sem banco.

Por que exaustivo: esta regra decide o destino de toda questão do acervo.
Uma mudança silenciosa aqui não quebra nenhum teste de integração (não há
banco envolvido), então a única rede de segurança é este arquivo.
"""
import pytest

from core.scheduler_regras import (INTERVALOS, MAX_CAIXA, conta_como_erro,
                                    dias_ate_revisao, orcamento_novas,
                                    proxima_caixa)


# --------------------------------------------------------------------------
# proxima_caixa

@pytest.mark.parametrize("caixa, dicas, esperado", [
    (0, 0, 1),
    (2, 0, 3),
    (MAX_CAIXA, 0, MAX_CAIXA),      # já no topo: acerto sem dica não passa do teto
    (MAX_CAIXA - 1, 0, MAX_CAIXA),
])
def test_correta_sem_dica_promove(caixa, dicas, esperado):
    assert proxima_caixa(caixa, "correta", dicas) == esperado


@pytest.mark.parametrize("caixa, dicas", [(0, 1), (3, 2), (MAX_CAIXA, 3)])
def test_correta_com_dica_mantem(caixa, dicas):
    """Lembrou com andaime: não é domínio, não promove nem rebaixa."""
    assert proxima_caixa(caixa, "correta", dicas) == caixa


@pytest.mark.parametrize("caixa", [0, 1, 3, MAX_CAIXA])
def test_parcial_estaciona(caixa):
    """Meio acerto não desce (02/10/2026): repete na mesma caixa. Dica não muda nada."""
    for dicas in (0, 1, 3):
        assert proxima_caixa(caixa, "parcial", dicas) == caixa


@pytest.mark.parametrize("caixa", [0, 1, 3, MAX_CAIXA])
@pytest.mark.parametrize("dicas", [0, 1, 3])
def test_incorreta_zera_sempre(caixa, dicas):
    assert proxima_caixa(caixa, "incorreta", dicas) == 0


# --------------------------------------------------------------------------
# dias_ate_revisao

def test_dias_ate_revisao_segue_tabela_intervalos():
    for caixa, dias in enumerate(INTERVALOS):
        assert dias_ate_revisao(caixa) == dias


@pytest.mark.parametrize("caixa", [-5, -1])
def test_dias_ate_revisao_clampa_caixa_negativa(caixa):
    """Nunca deveria acontecer (proxima_caixa nunca devolve negativo), mas
    a função não deve indexar fora da lista se acontecer por outro caminho."""
    assert dias_ate_revisao(caixa) == INTERVALOS[0]


@pytest.mark.parametrize("caixa", [MAX_CAIXA + 1, 999])
def test_dias_ate_revisao_clampa_caixa_alem_do_teto(caixa):
    assert dias_ate_revisao(caixa) == INTERVALOS[MAX_CAIXA]


# --------------------------------------------------------------------------
# conta_como_erro

@pytest.mark.parametrize("veredito, esperado", [
    ("correta", False),
    ("parcial", True),
    ("incorreta", True),
])
def test_conta_como_erro(veredito, esperado):
    assert conta_como_erro(veredito) is esperado


# --------------------------------------------------------------------------
# orcamento_novas

def test_orcamento_novas_none_usa_todo_o_resto():
    assert orcamento_novas(n_revisoes=10, teto=40, novas=None) == 30


def test_orcamento_novas_none_com_teto_esgotado_por_revisoes():
    assert orcamento_novas(n_revisoes=40, teto=40, novas=None) == 0


def test_orcamento_novas_com_cota_respeita_o_menor():
    """Resto do teto (30) é maior que a cota (8): cota vence."""
    assert orcamento_novas(n_revisoes=10, teto=40, novas=8) == 8


def test_orcamento_novas_com_cota_maior_que_resto():
    """Cota (25) é maior que o resto do teto (5): resto vence."""
    assert orcamento_novas(n_revisoes=35, teto=40, novas=25) == 5


def test_orcamento_novas_nao_fica_negativo_se_revisoes_excederem_teto():
    """Não deveria acontecer (quem chama já limita a query a `teto`), mas a
    função é a borda de proteção contra essa invariante calada."""
    assert orcamento_novas(n_revisoes=50, teto=40, novas=None) == 0
    assert orcamento_novas(n_revisoes=50, teto=40, novas=10) == 0
