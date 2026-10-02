"""Assunto fora do edital se ensina — e a ordem vai JUNTO da pergunta.

Medido em 29/09/2026 (bateria de descoberta): "você sabe algo sobre formas de
coesão de lp?" numa mesa sem Língua Portuguesa recebeu "isso não cai na sua
prova" em quatro turnos seguidos, com a regra na seção 4 e na precedência 1.
Com o prompt exato do turno, a regra geral perdeu; o bloco local antes da
pergunta ganhou. As disciplinas dos testes são inventadas.
"""
from core import db, retrieval, socratic

VERSAO = "test-fora-do-edital-v1"

EDITAL = ["Direito Sintético Constitucional", "Raciocínio Sintético Lógico"]


def test_bloco_so_quando_a_fala_traz_assunto_e_nao_nomeia_disciplina():
    assert socratic._assunto_da_fala("você sabe algo sobre formas de coesão?", EDITAL)
    assert socratic._assunto_da_fala("e homônimos, parônimos?", EDITAL)
    assert socratic._assunto_da_fala("quero estudar raciocínio sintético lógico", EDITAL) is None
    assert socratic._assunto_da_fala("sim", EDITAL) is None
    assert socratic._assunto_da_fala("pode ser", EDITAL) is None
    assert socratic._assunto_da_fala("ahan...", EDITAL) is None
    # Sem edital não há "fora" dele.
    assert socratic._assunto_da_fala("você sabe algo sobre formas de coesão?", []) is None


def _mesa(client, usuario):
    m = client.post("/mesas", json={"nome": "Concurso sintético"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, 'Edital sintético') "
                   "RETURNING id", {"m": m["id"]})["id"]
    for i, d in enumerate(EDITAL):
        db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) VALUES (%(e)s, %(d)s, %(o)s, %(t)s)",
                 {"e": eid, "d": d, "o": i, "t": f"{i + 1}.1 Tópico sintético de {d}."})
    return {**usuario["headers"], "X-Mesa-Id": str(m["id"])}


def test_pergunta_fora_do_edital_leva_a_ordem_junto_da_pergunta(client, usuario, llm_falso,
                                                                 monkeypatch):
    cab = _mesa(client, usuario)
    # O que a busca devolveu no caso real: a apostila da matéria do edital,
    # sem nada do que foi perguntado.
    alheio = {"id": 91, "titulo": "Apostila", "texto": "Proposição é oração declarativa.",
              "disciplina": EDITAL[1], "assunto": "Proposições"}
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **k: [alheio])
    llm_falso.retorno = "Coesão referencial retoma um termo; isso não cai nesta prova."

    client.post("/perguntar", json={"pergunta": "você sabe algo sobre formas de coesão?"},
                headers=cab)

    prompt = llm_falso.chamadas[-1]["prompt"]
    assert "### Assunto desta fala" in prompt
    assert prompt.index("### Assunto desta fala") > prompt.index("### Questões deste turno")
    assert prompt.index("### Assunto desta fala") < prompt.index("### Pergunta do aluno")


def test_fala_que_nomeia_a_disciplina_do_edital_nao_leva_o_bloco(client, usuario, llm_falso,
                                                                 monkeypatch):
    cab = _mesa(client, usuario)
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **k: [])
    llm_falso.retorno = "Vamos começar."

    client.post("/perguntar", json={"pergunta": "quero estudar direito sintético constitucional"},
                headers=cab)

    assert "### Assunto desta fala" not in llm_falso.chamadas[-1]["prompt"]
