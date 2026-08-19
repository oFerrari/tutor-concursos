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


def _responder_e_finalizar(client, usuario, sid, questao_id, segundos=5):
    """Responde UMA questão e fecha a prova, que é o contrato desde a 018.

    Estes testes chamavam a rota de lote único no fim, que a 018 substituiu
    por `responder` (uma a uma, na hora) + `finalizar` (fecha e devolve o
    relatório) — prova retomável não tem "o fim" onde empilhar tudo. Três
    testes falhavam com 404 e um QUARTO passava por acidente: ele espera 404
    pra usuário errado, e rota inexistente também dá 404, então ficava verde
    sem testar nada — pior que vermelho.

    Devolve o corpo do `finalizar`: {resultado, relatorio, erros}.
    """
    r = client.post(
        f"/simulados/{sid}/responder",
        json={"questao_id": questao_id, "resposta": "",
              "segundos_pergunta": segundos, "segundos_acumulados": segundos},
        headers=usuario["headers"],
    )
    assert r.status_code == 200, r.text
    f = client.post(f"/simulados/{sid}/finalizar", json={"segundos_total": segundos},
                    headers=usuario["headers"])
    assert f.status_code == 200, f.text
    return f.json()


def test_iniciar_com_ids_explicitos_nao_sorteia(client, usuario, duas_questoes):
    corpo = _iniciar_com_ids(client, usuario, duas_questoes)
    assert corpo["simulado_id"] > 0
    assert {q["id"] for q in corpo["questoes"]} == set(duas_questoes)


def test_responder_em_branco_conta_como_incorreta_sem_chamar_llm(client, usuario, questao_id, llm_falso):
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]

    corpo = _responder_e_finalizar(client, usuario, sid, questao_id, segundos=5)
    assert corpo["resultado"]["total"] == 1
    assert corpo["resultado"]["erros"] == 1
    assert corpo["resultado"]["nota_pct"] == 0.0
    assert not llm_falso.chamadas  # confirma que realmente não bateu no LLM


def test_relatorio_por_disciplina_e_erros_para_revisao(client, usuario, questao_id):
    disciplina = None
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]
    disciplina = corpo["questoes"][0]["disciplina"]

    corpo = _responder_e_finalizar(client, usuario, sid, questao_id, segundos=3)
    assert any(d["disciplina"] == disciplina for d in corpo["relatorio"])
    assert len(corpo["erros"]) == 1
    assert corpo["erros"][0]["resposta"] == ""


def test_historico_aparece_depois_de_finalizado(client, usuario, questao_id):
    corpo = _iniciar_com_ids(client, usuario, [questao_id])
    sid = corpo["simulado_id"]
    _responder_e_finalizar(client, usuario, sid, questao_id, segundos=2)
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
        f"/simulados/{sid}/responder",
        json={"questao_id": questao_id, "resposta": "",
              "segundos_pergunta": 1, "segundos_acumulados": 1},
        headers=outro_usuario["headers"],
    )
    assert r.status_code == 404, r.text

    # o simulado de `usuario` continua zerado — a tentativa de outro_usuario não colou nele
    historico = client.get("/simulados", headers=usuario["headers"]).json()
    entrada = next(h for h in historico if h["id"] == sid)
    assert entrada["respondidas"] == 0


def test_iniciar_simulado_com_ids_de_outro_documento_nao_quebra(client, usuario):
    """questao_ids vazio ou inexistente: 404 (acervo/filtro vazio), não 500."""
    r = client.post("/simulados", json={"questao_ids": [999999999]}, headers=usuario["headers"])
    assert r.status_code == 404
