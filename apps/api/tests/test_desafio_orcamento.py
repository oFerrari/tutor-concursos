"""
Orçamento de tempo do desafio — o "só tenho 20 minutos hoje".

`orcamento_blocos` é PURA: nem banco nem relógio, testável sozinha (mesmo
molde de scheduler_regras/ritmo_regras). O que ela codifica é uma decisão de
produto — a ORDEM do corte — e é isso que estes testes travam.
"""
import pytest

from core import db, desafio

VERSAO = "test-desafio-orcamento-v1"


def test_reincidente_e_o_ultimo_a_cair():
    """É o que a pessoa erra de novo e de novo: num orçamento apertado é o
    que mais rende por minuto."""
    assert desafio.orcamento_blocos(1, 3, 5, 5) == (1, 0, 0)
    assert desafio.orcamento_blocos(3, 3, 5, 5) == (3, 0, 0)


def test_novas_entram_depois_dos_reincidentes():
    """Material inédito é o mais caro cognitivamente — sai antes do
    reincidente numa sessão curta, não depois."""
    assert desafio.orcamento_blocos(5, 3, 5, 5) == (3, 2, 0)
    assert desafio.orcamento_blocos(8, 3, 5, 5) == (3, 5, 0)


def test_mini_simulado_cai_inteiro_ou_nao_cai():
    """Simulado de 2 questões não é simulado — medida sobre amostra pequena
    é ruído. Abaixo do mínimo o bloco sai inteiro."""
    # 3 reincidentes + 5 novas + 2 de sobra: as 2 NÃO viram simulado.
    assert desafio.orcamento_blocos(10, 3, 5, 5) == (3, 5, 0)
    # com 3 de sobra ele existe.
    assert desafio.orcamento_blocos(11, 3, 5, 5) == (3, 5, 3)


def test_orcamento_zero_devolve_desafio_vazio():
    """Quem pediu 0 minuto recebe vazio, e a tela diz isso — melhor que
    entregar 1 questão fingindo que coube."""
    assert desafio.orcamento_blocos(0, 3, 5, 5) == (0, 0, 0)
    assert desafio.orcamento_blocos(-3, 3, 5, 5) == (0, 0, 0)


def test_sem_orcamento_nada_muda():
    """Chamar sem `minutos` tem que dar exatamente o desafio de antes."""
    assert desafio.orcamento_blocos(99, 3, 5, 5) == (3, 5, 5)


def test_minutos_usam_a_velocidade_real_do_aluno(client, usuario):
    """
    O ponto que separa isto de um número chutado: 20 minutos de quem
    responde em 30s rende mais que de quem responde em 120s. Prometer "10
    questões em 20 min" pra todo mundo seria número fixo onde existe medida.
    """
    qs = db.query("SELECT id FROM questao LIMIT 2")
    if len(qs) < 2:
        pytest.skip("acervo sem questões")

    # Sem histórico: cai no default documentado (90s) -> 20min ≈ 13 questões.
    plano = client.get("/desafio?minutos=20", headers=usuario["headers"]).json()
    assert plano["minutos_pedidos"] == 20
    lento = plano["total_questoes"]

    # Agora com histórico RÁPIDO: a mesma janela passa a caber mais.
    for q in qs:
        db.query(
            "INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, "
            "dicas_usadas, segundos) VALUES (%(u)s, %(q)s, 'x', 'correta', 0, 20)",
            {"u": usuario["id"], "q": q["id"]},
        )
    rapido = client.get("/desafio?minutos=20", headers=usuario["headers"]).json()
    assert rapido["total_questoes"] >= lento
