"""Sem material da matéria pedida, o tutor diz isso — não ensina de memória.

Medido em 24/09/2026: o aluno pediu Legislação Estadual e Institucional, sem
material nenhum dela; os trechos recuperados eram de Constitucional, nenhum foi
citado, e o tutor descreveu por cinco turnos uma estrutura de órgãos que não
estava em lugar algum. As disciplinas dos testes são inventadas.
"""
import json

from core import assunto, db, leitura, retrieval

VERSAO = "test-sem-material-v1"

EDITAL = ["Legislação Sintética Estadual E Institucional", "Direito Sintético Constitucional",
          "Direito Penal E Legislação Penal Extravagante"]


def test_nome_longo_dito_pela_metade_ainda_e_a_disciplina():
    assert assunto._disciplina_aproximada("quero aprender legislação sintética institucional",
                                          EDITAL) == EDITAL[0]
    assert assunto._disciplina_aproximada("e a parte penal?", EDITAL) is None


def test_continuacao_herda_a_materia_e_pergunta_nova_nao():
    historico = [{"autor": "aluno", "texto": "quero aprender legislação sintética institucional"},
                 {"autor": "tutor", "texto": "Vamos lá. Por onde começamos?"}]
    assert assunto.disciplina_em_foco("certo queria aprender todo o conceito disso",
                                      historico, EDITAL) == EDITAL[0]
    assert assunto.disciplina_em_foco("o que é peculato?", historico, EDITAL) is None
    assert assunto.disciplina_em_foco("me explica peculato", historico, EDITAL) is None


def test_frases_reais_que_pediam_leitura_e_nao_disparavam():
    for fala in ("não sei nada mais eu quero seguir a ordem do edital",
                 "na verdade eu queria um aulao né pra depois falar se eu entendi ou não",
                 "ta você ta me trazendo só resumo eu queria como se tivesse lendo um pdf",
                 "certo queria aprender todo o conceito disso"):
        assert leitura.intencao(fala, False, False) in ("inicio", "edital"), fala


def _mesa(client, usuario):
    m = client.post("/mesas", json={"nome": "Concurso sintético"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, 'Edital sintético') "
                   "RETURNING id", {"m": m["id"]})["id"]
    for i, d in enumerate(EDITAL):
        db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) VALUES (%(e)s, %(d)s, %(o)s, %(t)s)",
                 {"e": eid, "d": d, "o": i, "t": f"{i + 1}.1 Tópico sintético de {d}."})
    return {**usuario["headers"], "X-Mesa-Id": str(m["id"])}


def test_materia_sem_material_nao_recebe_trecho_de_outra(client, usuario, llm_falso, monkeypatch):
    cab = _mesa(client, usuario)
    alheio = {"id": 77, "titulo": "Apostila", "texto": "Poder Legislativo e processo legislativo.",
              "disciplina": "Direito Sintético Constitucional", "assunto": "Poder Legislativo"}
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **k: [alheio])
    llm_falso.retorno = "Você ainda não tem material dessa disciplina."

    r = client.post("/perguntar", json={"pergunta": "quero aprender legislação sintética institucional"},
                    headers=cab).json()

    prompt = llm_falso.chamadas[-1]["prompt"]
    assert "### Cobertura do material" in prompt and "Tópico sintético de Legislação" in prompt
    assert "Poder Legislativo e processo legislativo" not in prompt
    assert r["fontes"] == []


def test_materia_com_trecho_dela_segue_normal(client, usuario, llm_falso, monkeypatch):
    cab = _mesa(client, usuario)
    proprio = {"id": 78, "titulo": "Lei sintética", "texto": "Art. 1º A instituição sintética...",
               "disciplina": EDITAL[0], "assunto": None}
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **k: [proprio])
    llm_falso.retorno = json.dumps({"resposta": "Conforme o art. 1º...", "fontes_usadas": [78]})

    client.post("/perguntar", json={"pergunta": "quero aprender legislação sintética institucional"},
                headers=cab)

    prompt = llm_falso.chamadas[-1]["prompt"]
    assert "### Cobertura do material" not in prompt and "A instituição sintética" in prompt
