"""Qual modelo atende cada tarefa, e o que acontece quando o local falha.
Puro: nenhuma chamada sai da máquina."""
from core import llm

# Guardado na importação: o conftest troca `llm.obter` por um bloqueio em todo teste.
OBTER_REAL = llm.obter

VERSAO = "test-llm-tarefa-v1"


def test_reservas_do_gemini_nao_repetem_o_principal(monkeypatch):
    monkeypatch.setattr(llm, "GEMINI_MODEL", "a")
    monkeypatch.setattr(llm, "GEMINI_RESERVAS", ["b", "a", "c", "b"])
    assert llm._modelos_gemini() == ["a", "b", "c"]


def test_modelo_local_falhando_cai_no_principal():
    class Falha(llm.LLM):
        def gerar(self, *a, **k):
            raise llm.ErroLLM("ollama parado")

    class Responde(llm.LLM):
        def gerar(self, *a, **k):
            return "ok"

    assert llm._ComReserva(Falha(), Responde()).gerar("p") == "ok"


def test_classificar_vai_ao_local_so_quando_configurado(monkeypatch):
    """`llm.obter` real, lido do módulo: o conftest troca o atributo, não a função."""
    import core.llm as modulo
    monkeypatch.setattr(modulo, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(modulo, "LLM_CLASSIFICADOR", "ollama")
    real = OBTER_REAL
    assert isinstance(real("classificar"), modulo._ComReserva)
    assert isinstance(real(), modulo.Gemini)
    monkeypatch.setattr(modulo, "LLM_CLASSIFICADOR", "")
    assert isinstance(real("classificar"), modulo.Gemini)


def test_cota_esgotada_e_contada_como_429_e_nao_como_sem_resposta(monkeypatch):
    """Em 24/09/2026 a telemetria gravou 119 "status 0" — a maior parte era cota."""
    import httpx
    import core.llm as modulo
    gravados = []
    monkeypatch.setattr(modulo, "GEMINI_API_KEY", "chave-falsa")
    monkeypatch.setattr(modulo, "GEMINI_MODEL", "modelo-a")
    monkeypatch.setattr(modulo, "GEMINI_RESERVAS", ["modelo-b"])
    monkeypatch.setattr(modulo.httpx, "post",
                        lambda *a, **k: httpx.Response(429, request=httpx.Request("POST", "http://x")))
    monkeypatch.setattr(modulo.telemetria, "registrar",
                        lambda provedor, modelo, status, **k: gravados.append((modelo, status)))

    import pytest
    with pytest.raises(llm.ErroLLM):
        modulo.Gemini().gerar("oi")

    assert gravados == [("modelo-a", 429), ("modelo-b", 429)]
