"""
Integração de simulado — iniciar, corrigir, relatório, histórico, e o
isolamento entre usuários (achado testando: ver `pertence_a()` em
core/simulado.py e o comentário em `api.py::rota_responder_simulado`).

Respostas em branco de propósito: `simulado.corrigir()` trata resposta
vazia como incorreta SEM chamar o LLM ("resposta em branco nem vai ao
LLM: é erro por definição") — cobre o fluxo inteiro (registrar, finalizar,
relatório, erros_do) sem gastar cota real do Gemini. Julgamento de
resposta de verdade é coberto em `test_llm_boundary_api.py`, com dublê.
"""
def _iniciar_com_ids(client, usuario, ids):
    r = client.post("/simulados", json={"questao_ids": ids}, headers=usuario["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_iniciar_com_ids_explicitos_nao_sorteia(client, usuario, duas_questoes):
    corpo = _iniciar_com_ids(client, usuario, duas_questoes)
    assert corpo["simulado_id"] > 0
    assert {q["id"] for q in corpo["questoes"]} == set(duas_questoes)


def test_responder_em_branco_conta_como_incorreta_sem_chamar_llm(client, usuario, questao_id, llm_falso):
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]

    r = client.post(
        f"/simulados/{sid}/respostas",
        json={"respostas": [{"questao_id": questao_id, "resposta": "", "segundos": 5}], "segundos_total": 5},
        headers=usuario["headers"],
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["resultado"]["total"] == 1
    assert corpo["resultado"]["erros"] == 1
    assert corpo["resultado"]["nota_pct"] == 0.0
    assert not llm_falso.chamadas  # confirma que realmente não bateu no LLM


def test_relatorio_por_disciplina_e_erros_para_revisao(client, usuario, questao_id):
    disciplina = None
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]
    disciplina = corpo["questoes"][0]["disciplina"]

    r = client.post(
        f"/simulados/{sid}/respostas",
        json={"respostas": [{"questao_id": questao_id, "resposta": "", "segundos": 3}], "segundos_total": 3},
        headers=usuario["headers"],
    )
    corpo = r.json()
    assert any(d["disciplina"] == disciplina for d in corpo["relatorio"])
    assert len(corpo["erros"]) == 1
    assert corpo["erros"][0]["resposta"] == ""


def test_historico_aparece_depois_de_finalizado(client, usuario, questao_id):
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]
    client.post(
        f"/simulados/{sid}/respostas",
        json={"respostas": [{"questao_id": questao_id, "resposta": "", "segundos": 2}], "segundos_total": 2},
        headers=usuario["headers"],
    )
    historico = client.get("/simulados", headers=usuario["headers"]).json()
    entrada = next(h for h in historico if h["id"] == sid)
    assert entrada["respondidas"] == 1
    assert entrada["nota_pct"] == 0.0


def test_responder_simulado_de_outro_usuario_e_bloqueado(client, usuario, outro_usuario, questao_id):
    """Regressão do achado: sid pertence a `usuario`; `outro_usuario` não
    pode responder por ele, e nada deve entrar como tentativa alheia."""
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]

    r = client.post(
        f"/simulados/{sid}/respostas",
        json={"respostas": [{"questao_id": questao_id, "resposta": "", "segundos": 1}], "segundos_total": 1},
        headers=outro_usuario["headers"],
    )
    assert r.status_code == 404

    # o simulado de `usuario` continua zerado — a tentativa de outro_usuario não colou nele
    historico = client.get("/simulados", headers=usuario["headers"]).json()
    entrada = next(h for h in historico if h["id"] == sid)
    assert entrada["respondidas"] == 0


def test_iniciar_simulado_com_ids_de_outro_documento_nao_quebra(client, usuario):
    """questao_ids vazio ou inexistente: 404 (acervo/filtro vazio), não 500."""
    r = client.post("/simulados", json={"questao_ids": [999999999]}, headers=usuario["headers"])
    assert r.status_code == 404
