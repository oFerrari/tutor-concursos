"""
Feedback dito DENTRO do chat (migração 029) — `/erro`, `/feedback`.

O que estes testes travam não é o parser, é a decisão de produto por trás dele:
o relato de defeito precisa carregar o CONTEXTO, e o contexto é a resposta que
ele comenta. Por isso a linha nasce com `mensagem_tutor_id` preenchido, e por
isso o comando não vira turno de conversa nem gasta cota.
"""
from core import db, melhoria

VERSAO = "test-melhoria-v1"


def _conversa_com_resposta(client, usuario, llm_falso, texto="resposta do tutor"):
    llm_falso.retorno = texto
    r = client.post("/perguntar", json={"pergunta": "o que é peculato?"},
                    headers=usuario["headers"])
    assert r.status_code == 200, r.text
    return r.json()["conversa_id"]


def test_comando_grava_preso_a_ultima_resposta_do_tutor(client, usuario, llm_falso):
    """O valor inteiro da 029 está nesta FK.

    "Ele respondeu errado sobre princípios" envelhece em horas; o id da mensagem
    não — dele saem a resposta literal, as `fontes` daquele turno e a conversa
    inteira em volta."""
    cid = _conversa_com_resposta(client, usuario, llm_falso)
    alvo = db.exec1("SELECT id FROM mensagem WHERE conversa_id=%(c)s AND autor='tutor' "
                    "ORDER BY id DESC LIMIT 1", {"c": cid})["id"]

    r = client.post("/perguntar",
                    json={"pergunta": "/erro o gabarito contradiz o artigo citado",
                          "conversa_id": cid},
                    headers=usuario["headers"])
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["feedback_salvo"] is True
    assert corpo["resposta"] == "Feedback salvo com sucesso!"
    assert corpo["feedback"]["mensagem_tutor_id"] == alvo

    linha = db.exec1("SELECT * FROM fila_melhoria WHERE id=%(i)s", {"i": corpo["feedback"]["id"]})
    assert linha["conversa_id"] == cid
    assert linha["mensagem_tutor_id"] == alvo
    assert linha["feedback_texto"] == "o gabarito contradiz o artigo citado"
    assert linha["status"] == "pendente"


def test_comando_nao_vai_ao_modelo_nem_vira_turno(client, usuario, llm_falso):
    """As duas metades do "não é pergunta": nada de cota, nada de histórico.

    Gravar em `mensagem` faria o turno seguinte LER a reclamação como matéria —
    o tutor passaria a responder sobre o próprio defeito."""
    cid = _conversa_com_resposta(client, usuario, llm_falso)
    antes = db.exec1("SELECT count(*) AS n FROM mensagem WHERE conversa_id=%(c)s", {"c": cid})["n"]
    llm_falso.chamadas.clear()

    client.post("/perguntar", json={"pergunta": "/feedback ficou raso demais", "conversa_id": cid},
                headers=usuario["headers"])

    assert llm_falso.chamadas == [], "o comando de feedback foi ao modelo"
    depois = db.exec1("SELECT count(*) AS n FROM mensagem WHERE conversa_id=%(c)s",
                      {"c": cid})["n"]
    assert depois == antes, "o comando virou mensagem na conversa"


def test_comando_sem_texto_pede_o_texto_e_nao_grava(client, usuario, llm_falso):
    """`/erro` sozinho é intenção pela metade, não erro: quem digitou está no
    caminho certo e recebe a instrução, não um 400 vermelho."""
    cid = _conversa_com_resposta(client, usuario, llm_falso)
    antes = db.exec1("SELECT count(*) AS n FROM fila_melhoria WHERE conversa_id=%(c)s",
                     {"c": cid})["n"]

    corpo = client.post("/perguntar", json={"pergunta": "/erro", "conversa_id": cid},
                        headers=usuario["headers"]).json()
    assert corpo["feedback_salvo"] is False
    assert "Escreva o que saiu errado" in corpo["resposta"]
    assert db.exec1("SELECT count(*) AS n FROM fila_melhoria WHERE conversa_id=%(c)s",
                    {"c": cid})["n"] == antes


def test_conversa_nova_aceita_feedback_sem_alvo(client, usuario):
    """Reclamar antes de o tutor ter dito qualquer coisa é estado previsto: a
    FK nasce NULL e o texto se preserva. Perder o relato porque falta o alvo
    seria trocar o dado que existe pelo que falta."""
    corpo = client.post("/perguntar", json={"pergunta": "/erro o app abriu vazio"},
                        headers=usuario["headers"]).json()
    assert corpo["feedback_salvo"] is True
    assert corpo["feedback"]["mensagem_tutor_id"] is None


def test_feedback_de_outro_aluno_nao_entra_na_conversa_alheia(client, usuario, outro_usuario,
                                                              llm_falso):
    """Quem autoriza é `conversa.obter`, e é por isso que a 029 não repete
    `usuario_id`: uma segunda fonte de verdade sobre posse divergiria da
    primeira."""
    cid = _conversa_com_resposta(client, usuario, llm_falso)
    r = client.post("/perguntar", json={"pergunta": "/erro xereta", "conversa_id": cid},
                    headers=outro_usuario["headers"])
    assert r.status_code == 404
    assert db.exec1("SELECT count(*) AS n FROM fila_melhoria WHERE conversa_id=%(c)s",
                    {"c": cid})["n"] == 0


def test_pergunta_normal_continua_indo_ao_modelo(client, usuario, llm_falso):
    """A guarda do falso positivo: "meu erro foi na alternativa b" é conversa,
    não comando. Sem a barra, nada é interceptado."""
    llm_falso.retorno = "resposta do tutor"
    corpo = client.post("/perguntar", json={"pergunta": "meu erro foi na alternativa b"},
                        headers=usuario["headers"]).json()
    assert corpo.get("feedback_salvo") is not True
    assert llm_falso.chamadas, "pergunta normal não chegou ao modelo"


def test_fila_traz_o_turno_comentado_junto(client, usuario, llm_falso):
    """A fila existe pra ser LIDA na hora de depurar, e ler significa ver a
    resposta reclamada — não só o id dela."""
    cid = _conversa_com_resposta(client, usuario, llm_falso, "peculato é do art. 312")
    corpo = client.post("/perguntar",
                        json={"pergunta": "/erro isso não responde o que perguntei",
                              "conversa_id": cid},
                        headers=usuario["headers"]).json()

    item = next(x for x in melhoria.pendentes() if x["id"] == corpo["feedback"]["id"])
    assert item["feedback_texto"] == "isso não responde o que perguntei"
    assert item["resposta_do_tutor"] == "peculato é do art. 312"
    assert item["conversa_titulo"]
