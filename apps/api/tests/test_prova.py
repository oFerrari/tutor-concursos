"""Questões de prova (037, `core/prova.py`): o simulado do aluno vira banco de questões.
Provas inventadas em `cenarios/provas/`."""
import json
from pathlib import Path

from core import auth, db, indice, material, prova, socratic

VERSAO = "test-prova-v1"

PROVAS = Path(__file__).resolve().parent.parent / "cenarios" / "provas"
DISC = ["Língua Portuguesa", "Raciocínio Lógico-Matemático", "Direito Constitucional"]


def _texto(nome):
    return (PROVAS / f"{nome}.txt").read_text(encoding="utf-8")


def test_le_gabarito_junto_comentario_titulos_e_lista_numerada_no_enunciado():
    qs = prova.separar(_texto("comentada"), DISC)
    assert [q["numero"] for q in qs] == [1, 2, 3, 4]
    q1, q2, q3, q4 = qs
    assert q1["gabarito"] == "C" and len(q1["alternativas"]) == 5
    assert q1["alternativas"][2][1].endswith("preservando o sentido original."), "alternativa de duas linhas"
    assert "cérebro sintético" in q1["texto_base"] and q1["disciplina"] == "Língua Portuguesa"
    assert q1["comentario"].startswith("A paráfrase")
    assert "Raciocínio" not in q2["comentario"], "o título da próxima seção não é comentário"
    assert q3["disciplina"] == "Raciocínio Lógico-Matemático"
    assert "1. Cavalo sintético" in q3["enunciado"], "lista numerada do enunciado não vira questão"
    assert prova.tipo_da_questao(q4) == "certo_errado" and q4["gabarito"] == "C*"


def test_le_tabela_de_gabarito_e_arquivo_so_de_respostas():
    assert prova.tabela_de_gabarito(_texto("tabela")) == {1: "B", 2: "D", 3: "A", 4: "C"}
    qs = prova.separar(_texto("tabela"), DISC)
    assert len(qs) == 4 and qs[1]["alternativas"][3] == ("D", "4")
    assert "rio sintético" in qs[2]["texto_base"]
    assert not qs[1]["texto_base"], "o texto-base é da questão seguinte, não da anterior"
    assert prova.e_so_gabarito(_texto("so_gabarito"))
    assert not prova.e_so_gabarito(_texto("comentada"))


def test_corrige_multipla_escolha_sem_modelo():
    assert socratic.avaliar_questao({"tipo": "multipla_escolha", "gabarito_letra": "C"}, "c")["veredito"] == "correta"
    assert socratic.avaliar_questao({"tipo": "multipla_escolha", "gabarito_letra": "C"}, "B")["veredito"] == "incorreta"
    assert socratic.avaliar_questao({"tipo": "multipla_escolha", "gabarito_letra": "C"}, "")["veredito"] == "incorreta"


def _subir(client, usuario, nome):
    r = client.post("/materiais", files={"arquivo": (f"{nome}.txt", _texto(nome).encode(), "text/plain")},
                    data={"disciplina": "Simulados Sintéticos", "tipo": "simulado"}, headers=usuario["headers"])
    assert r.status_code == 201, r.text
    assert material.esperar_fila(30)
    return r.json()["id"]


def _da_prova(doc):
    return db.query("""SELECT id, numero_na_prova, tipo, gabarito_letra, gabarito_ce, gabarito_fonte,
                              usuario_id, fonte_chunks, origem
                         FROM questao WHERE documento_id = %(d)s ORDER BY numero_na_prova""", {"d": doc})


def test_simulado_vira_questoes_do_aluno_com_fonte_real(client, usuario, llm_falso):
    doc = _subir(client, usuario, "comentada")
    qs = _da_prova(doc)
    assert [q["numero_na_prova"] for q in qs] == [1, 2, 3, 4]
    assert [q["tipo"] for q in qs] == ["multipla_escolha"] * 3 + ["certo_errado"]
    assert qs[0]["gabarito_letra"] == "C" and qs[3]["gabarito_ce"] is True
    assert all(q["origem"] == "prova" and q["gabarito_fonte"] == "arquivo" for q in qs)
    assert all(q["usuario_id"] == usuario["id"] for q in qs), "o dono sai do documento"
    for q in qs:
        assert db.exec1("SELECT count(*) AS n FROM chunk WHERE id = ANY(%(f)s) AND documento_id = %(d)s",
                        {"f": q["fonte_chunks"], "d": doc})["n"] == len(q["fonte_chunks"]) > 0

    tela = client.get(f"/questoes/{qs[0]['id']}", headers=usuario["headers"]).json()
    assert [a["letra"] for a in tela["alternativas"]] == list("ABCDE")
    assert tela["contexto"] and "cérebro sintético" in tela["contexto"]
    r = client.post(f"/questoes/{qs[0]['id']}/avaliar", json={"resposta": "C"}, headers=usuario["headers"])
    assert r.json()["veredito"] == "correta"

    # Reimportar atualiza, não duplica.
    prova.importar(doc)
    assert len(_da_prova(doc)) == 4

    # Questão de prova é do aluno: outra pessoa não a vê.
    outro = auth.usuario_da_cli("teste-prova-outro@local")
    try:
        cab = {"Authorization": f"Bearer {auth.emitir_token(outro)}"}
        assert client.get(f"/questoes/{qs[0]['id']}", headers=cab).status_code == 404
    finally:
        db.query("DELETE FROM usuario WHERE id = %(u)s", {"u": outro})


def test_gabarito_em_arquivo_separado_completa_o_simulado(client, usuario, llm_falso):
    doc = _subir(client, usuario, "questoes_sem_gabarito")
    assert _da_prova(doc) == []
    assert db.exec1("SELECT questoes_sem_gabarito AS n FROM documento WHERE id=%(d)s", {"d": doc})["n"] == 3
    gab = _subir(client, usuario, "so_gabarito")
    assert db.exec1("SELECT gabarito_de AS g FROM documento WHERE id=%(d)s", {"d": gab})["g"] == doc
    qs = _da_prova(doc)
    assert [(q["numero_na_prova"], q["gabarito_letra"], q["gabarito_fonte"]) for q in qs] == \
        [(1, "B", "arquivo"), (2, "A", "arquivo"), (3, "C", "arquivo")]


def test_sem_gabarito_o_modelo_resolve_e_fica_marcado(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 1000)

    def gerar(prompt, *a, **k):
        if "QUESTÃO 1" in prompt:
            return json.dumps({"respostas": [{"numero": 1, "letra": "B"}, {"numero": 2, "letra": "A"},
                                             {"numero": 3, "letra": "C"}]})
        return json.dumps({"assuntos": [], "trechos": []})
    llm_falso.gerar = gerar
    doc = _subir(client, usuario, "questoes_sem_gabarito")
    assert [(q["gabarito_letra"], q["gabarito_fonte"]) for q in _da_prova(doc)] == [("B", "tutor")] * 1 + \
        [("A", "tutor"), ("C", "tutor")]


def test_questoes_de_x_na_conversa_vem_da_prova(client, usuario, llm_falso):
    def gerar(prompt, sistema="", json_mode=False, max_tokens=0, schema=None, temperatura=None):
        if schema is socratic.ESQUEMA_RESPOSTA_TUTOR:
            return json.dumps({"resposta": "Seguem as questões da sua prova.", "fontes_usadas": []})
        return "[]"
    llm_falso.gerar = gerar
    doc = _subir(client, usuario, "tabela")
    r = client.post("/perguntar", headers=usuario["headers"],
                    json={"pergunta": "me manda uma questão sobre o rio sintético"}).json()
    assert [q["id"] for q in r["questoes"]] == [q["id"] for q in _da_prova(doc) if q["numero_na_prova"] == 3]
    assert r["questoes"][0]["tipo"] == "multipla_escolha" and r["questoes"][0]["alternativas"]
    assert "SIMULADO que ele subiu" in llm_falso.chamadas[-1]["prompt"] if llm_falso.chamadas else True


def test_tabela_em_bloco_e_lista_numerada_no_comentario():
    """Layout do simulado real: todas as linhas de números, depois todas as de
    letras; e comentário de professor com "2. …" que não pode abrir a questão 2."""
    t = _texto("comentada_tabela_em_bloco")
    assert prova.tabela_de_gabarito(t) == {1: "C", 2: "E", 3: "A", 4: "C", 5: "B", 6: "D"}
    qs = prova.separar(t, DISC)
    assert [q["numero"] for q in qs] == [1, 2, 3, 4]
    assert qs[1]["enunciado"].startswith("Assinale a frase")
    assert "2. reler o trecho" in qs[0]["comentario"]


def test_apagar_o_simulado_leva_as_questoes_dele(client, usuario, llm_falso):
    doc = _subir(client, usuario, "comentada")
    assert _da_prova(doc)
    assert client.delete(f"/materiais/{doc}", headers=usuario["headers"]).status_code in (200, 204)
    assert db.exec1("SELECT count(*) AS n FROM questao WHERE origem='prova' AND usuario_id=%(u)s",
                    {"u": usuario["id"]})["n"] == 0, "questão de prova sem o arquivo não fica para trás"


def test_trecho_de_simulado_de_outra_materia_sai_da_resposta(monkeypatch):
    from core import socratic
    trechos = [{"id": 1, "tipo": "simulado"}, {"id": 2, "tipo": "simulado"},
               {"id": 3, "tipo": "aula"}, {"id": 4, "tipo": "simulado"}]
    monkeypatch.setattr(prova, "materias_dos_trechos", lambda ids: {
        1: {"Raciocínio Lógico-Matemático"}, 2: {"Estatística"}})
    ficou = [t["id"] for t in socratic._sem_prova_de_outra_materia(trechos, ["Raciocínio Lógico-Matemático"])]
    assert ficou == [1, 3, 4], "sai só o trecho de simulado de OUTRA matéria; apostila e simulado sem questão ficam"
    assert [t["id"] for t in socratic._sem_prova_de_outra_materia(trechos, None)] == [1, 2, 3, 4]


def test_trecho_de_simulado_cita_a_questao(client, usuario, llm_falso):
    doc = _subir(client, usuario, "comentada")
    cid = db.exec1("SELECT fonte_chunks[1] AS c FROM questao WHERE documento_id=%(d)s AND numero_na_prova=2",
                   {"d": doc})["c"]
    assert prova.rotulos_dos_trechos([cid])[cid].startswith("quest")
