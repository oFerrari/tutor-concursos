"""Garantias de custo, isolamento e honestidade do avaliador offline."""
import json
import socket

import pytest

import avaliar_offline as avaliar
from core import db, llm, pedido

VERSAO = "test-avaliar-offline-v1"


def test_offline_bloqueia_modelos_inclusive_instancia_preexistente(monkeypatch):
    externo = []
    monkeypatch.setattr(llm, "_post", lambda *a, **kw: externo.append(True))
    modelo = llm.Gemini()
    with avaliar.offline():
        for chamar in (lambda: llm.obter(), lambda: modelo.gerar("teste"),
                       lambda: modelo.gerar_json("teste"),
                       lambda: modelo.gerar_em_fluxo("teste", "", 1, print),
                       lambda: llm.Ollama().gerar("teste"),
                       lambda: llm._ComReserva(llm.Ollama(), modelo).gerar("teste")):
            with pytest.raises(avaliar.BloqueioOffline):
                chamar()
    assert externo == []


def test_offline_bloqueia_rede_e_restaura_depois():
    original = socket.socket.connect
    with avaliar.offline(), socket.socket() as s:
        with pytest.raises(avaliar.BloqueioOffline):
            s.connect(("127.0.0.1", 9))
    assert socket.socket.connect is original


def test_expectativa_independente_pega_regressao_do_produto(monkeypatch):
    monkeypatch.setattr(pedido, "treino", lambda fala: {"quantidade": 5, "formal": False})
    r = avaliar.regras([{"id": "negacao", "fala": "Não quero questões", "quantidade": None}])
    assert r[0]["erros"] == ["questões: esperado None, obtido 5"]


def test_diferenca_nao_chama_ausencia_de_correcao():
    a = {"camada": "historico", "conversa": 1, "mensagem": 2, "regra": "x"}
    b = {**a, "mensagem": 3}
    assert avaliar.comparar({"achados": [b]}, {"achados": [a, b]}) == {
        "novos": 0, "recorrentes": 1, "nao_observados_neste_recorte": 1}


def test_comparacao_inclui_regressoes_independentes():
    r = {"achados": [], "regras": [{"id": "negacao", "erros": ["gerou"]}]}
    assert avaliar.comparar(r, {})["novos"] == 1
    assert avaliar.comparar(r, r)["recorrentes"] == 1


def test_runner_banco_somente_leitura_e_falha_atual_reprova(tmp_path, monkeypatch):
    def historicos(r, *args):
        assert db.exec1("SHOW transaction_read_only")["transaction_read_only"] == "on"
        r.update(turnos=1, selecionados=1, total_disponivel=1)
    monkeypatch.setattr(avaliar, "historicos", historicos)
    monkeypatch.setattr(avaliar, "regras", lambda _: [
        {"id": "x", "fala": "sem questões", "erros": ["gerou"]}])
    assert avaliar.main(["--rapido", "--saida", str(tmp_path)]) == 1
    assert db.exec1("SHOW transaction_read_only")["transaction_read_only"] == "off"
    assert json.loads((tmp_path / "ultimo.json").read_text())["saida"] == 1


def test_runner_preserva_relatorio_quando_incompleto(tmp_path, monkeypatch):
    def interrompido(r, *args):
        r.update(turnos=1, selecionados=20, total_disponivel=30)
        raise avaliar.TempoEsgotado("tempo")
    monkeypatch.setattr(avaliar, "historicos", interrompido)
    monkeypatch.setattr(avaliar, "regras", lambda _: [])
    assert avaliar.main(["--saida", str(tmp_path)]) == 2
    r = json.loads((tmp_path / "ultimo.json").read_text())
    assert r["turnos"] == 1
    assert r["erros_execucao"] == ["TempoEsgotado: tempo"]


def test_apenas_alerta_historico_nao_reprova_codigo_atual(tmp_path, monkeypatch):
    def historicos(r, *args):
        r.update(turnos=1, selecionados=1, total_disponivel=1)
        r["achados"].append({"camada": "historico", "conversa": 1, "mensagem": 2,
                            "regra": "estilo", "fala": "oi", "detalhe": "antigo"})
    monkeypatch.setattr(avaliar, "historicos", historicos)
    monkeypatch.setattr(avaliar, "regras", lambda _: [])
    assert avaliar.main(["--rapido", "--saida", str(tmp_path)]) == 0


def test_caso_isolado_nao_acessa_banco(tmp_path, monkeypatch):
    def proibido(*a, **kw):
        raise AssertionError("modo só regras não deve conectar ao banco")
    monkeypatch.setattr(db, "conn", proibido)
    assert avaliar.main(["--so-regras", "--caso", "saudacao", "--saida", str(tmp_path)]) == 0
    r = json.loads((tmp_path / "ultimo.json").read_text())
    assert [c["id"] for c in r["regras"]] == ["saudacao"]


def test_caso_inexistente_nao_vira_aprovacao_vazia(tmp_path):
    assert avaliar.main(["--so-regras", "--caso", "inexistente", "--saida", str(tmp_path)]) == 2
