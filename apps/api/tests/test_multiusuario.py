"""
O contrato central da migração 008: acervo COMPARTILHADO, progresso
PESSOAL. Duas contas respondendo a MESMA questão não podem se misturar —
nem em `progresso` (caixa), nem em `erro_caderno`, nem em `v_desempenho_disciplina`.

Isto não está coberto por `test_scheduler_regras.py` (função pura, sem
usuario_id) nem por `test_auth_api.py` (uma conta só). É o único lugar que
prova, contra o banco de verdade, o motivo de existir de `progresso` em vez
de `caixa`/`prox_revisao` morarem em `questao`.
"""
from core import db


def test_mesma_questao_caixas_independentes(client, usuario, outro_usuario, questao_id):
    # usuario acerta sem dica -> promove; outro_usuario erra -> zera (já começa em 0, mas
    # o ponto é que a promoção de um não pode "vazar" caixa pro outro)
    r1 = client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": "correta", "resposta": "resp A", "dicas_usadas": 0},
        headers=usuario["headers"],
    )
    r2 = client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": "incorreta", "resposta": "resp B", "dicas_usadas": 0},
        headers=outro_usuario["headers"],
    )
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["caixa"] == 1     # correta sem dica: promove de 0 pra 1
    assert r2.json()["caixa"] == 0     # incorreta: zera (já estava em 0)

    linhas = db.query(
        "SELECT usuario_id, caixa FROM progresso WHERE questao_id = %(q)s "
        "AND usuario_id = ANY(%(us)s)",
        {"q": questao_id, "us": [usuario["id"], outro_usuario["id"]]},
    )
    por_usuario = {r["usuario_id"]: r["caixa"] for r in linhas}
    assert por_usuario[usuario["id"]] == 1
    assert por_usuario[outro_usuario["id"]] == 0


def test_erro_caderno_isolado_por_usuario(client, usuario, outro_usuario, questao_id):
    client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": "incorreta", "resposta": "errei", "dicas_usadas": 0},
        headers=usuario["headers"],
    )
    # outro_usuario nunca tentou esta questão — não pode aparecer no caderno dele
    r_erros_usuario = client.get("/erros", headers=usuario["headers"])
    r_erros_outro = client.get("/erros", headers=outro_usuario["headers"])

    ids_usuario = {e["questao_id"] for e in r_erros_usuario.json()}
    ids_outro = {e["questao_id"] for e in r_erros_outro.json()}
    assert questao_id in ids_usuario
    assert questao_id not in ids_outro


def test_fila_de_um_nao_contem_progresso_do_outro(client, usuario, outro_usuario, questao_id):
    """Depois que `usuario` responde, a questão sai da lista de 'inéditas'
    dele (ganhou prox_revisao futura) — mas continua inédita pra
    `outro_usuario`, porque o banco de questões é compartilhado e a
    ausência de linha em `progresso` é o sinal de 'nunca tentou' POR PESSOA."""
    client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": "correta", "resposta": "x", "dicas_usadas": 0},
        headers=usuario["headers"],
    )

    ainda_inedita_para_outro = db.exec1(
        "SELECT 1 FROM questao q WHERE q.id = %(q)s "
        "AND NOT EXISTS (SELECT 1 FROM progresso p WHERE p.usuario_id = %(u)s AND p.questao_id = q.id)",
        {"q": questao_id, "u": outro_usuario["id"]},
    )
    tem_progresso_para_usuario = db.exec1(
        "SELECT 1 FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id},
    )
    assert ainda_inedita_para_outro is not None
    assert tem_progresso_para_usuario is not None


def test_stats_nao_mistura_usuarios(client, usuario, outro_usuario, questao_id):
    disciplina = db.exec1("SELECT disciplina FROM questao WHERE id = %(q)s", {"q": questao_id})["disciplina"]

    client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": "correta", "resposta": "x", "dicas_usadas": 0},
        headers=usuario["headers"],
    )

    stats_usuario = {d["disciplina"]: d for d in client.get("/stats", headers=usuario["headers"]).json()}
    stats_outro = {d["disciplina"]: d for d in client.get("/stats", headers=outro_usuario["headers"]).json()}

    assert disciplina in stats_usuario
    assert stats_usuario[disciplina]["tentativas"] >= 1
    assert stats_usuario[disciplina]["acertos"] >= 1
    # outro_usuario nunca tentou nada nesta disciplina — v_desempenho_disciplina
    # (db/008_usuario.sql) não gera linha pra ele nela (CROSS JOIN só cobre
    # usuários que já têm QUALQUER progresso, e mesmo assim tentativas fica 0).
    if disciplina in stats_outro:
        assert stats_outro[disciplina]["tentativas"] == 0
        assert stats_outro[disciplina]["acertos"] == 0
