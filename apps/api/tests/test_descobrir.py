"""A bateria de descoberta compara o JUIZ com o que o SISTEMA fez (sem LLM aqui)."""
import descobrir

VERSAO = "test-descobrir-v2"


def _turno(**k):
    return {"fala": "f", "texto": "t", "tela": "t", "cartoes": [], "consultado": [], **k}


def _v(n, **k):
    return {"turno": n, "pedido": "p", "atendeu": True, "cartoes_devidos": False,
            "consultado_devido": True, "defeitos": [], **k}


def test_cartao_sem_pedido_e_pedido_sem_cartao_sao_graves():
    turnos = [_turno(cartoes=["União de conjuntos"]), _turno()]
    achados = descobrir.divergencias(turnos, [_v(1), _v(2, cartoes_devidos=True)])
    textos = [(a["turno"], a["gravidade"], a["origem"]) for a in achados]
    assert (1, "grave", "cartões") in textos and (2, "grave", "cartões") in textos


def test_consultado_sem_motivo_e_marcacao_crua_na_tela():
    turnos = [_turno(consultado=["Poder Judiciário"], tela="resultado \\boxed{105} e ```")]
    achados = descobrir.divergencias(turnos, [_v(1, consultado_devido=False)])
    origens = {a["origem"] for a in achados}
    assert origens == {"consultado", "tela"}


def test_tela_limpa_nao_acusa_dinheiro_nem_texto_comum():
    assert not descobrir.RE_MARCACAO_CRUA.search("A multa vai de R$ 1.000 a R$ 5.000, e x² = 4.")
    assert descobrir.RE_MARCACAO_CRUA.search("custa $x$")


def test_juiz_mudo_vira_defeito_e_nao_silencio():
    achados = descobrir.divergencias([_turno()], [{"turno": 0, "erro": "cota"}])
    assert achados and achados[0]["origem"] == "juiz"


def test_secoes_de_decisoes():
    texto = "intro\n## A primeira\ncorpo a\n## A segunda\ncorpo b\n"
    assert [t for t, _ in descobrir._secoes(texto)] == ["A primeira", "A segunda"]


def test_tela_cega_para_a_rodada_antes_de_gastar_cota(monkeypatch):
    # 29/09/2026: node fora do PATH do Agendador, todo turno virou "[[não deu para
    # desenhar]]" e o juiz julgou a mensagem de erro (188 defeitos falsos).
    def sem_node(*a, **k):
        raise FileNotFoundError(2, "No such file or directory", "node")

    def banco(*a, **k):
        raise AssertionError("não podia chegar ao banco nem à cota")

    monkeypatch.setattr(descobrir.subprocess, "run", sem_node)
    monkeypatch.setattr(descobrir.db, "exec1", banco)
    monkeypatch.setattr(descobrir.sys, "argv", ["descobrir.py", "--so", "reais"])
    assert descobrir.main() == 2
