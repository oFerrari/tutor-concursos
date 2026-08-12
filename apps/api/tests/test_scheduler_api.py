"""
Integração de agendamento via API — fila, promoção de caixa ponta-a-ponta
(HTTP -> scheduler.registrar -> Postgres) e caderno de erros.

`test_scheduler_regras.py` já cobre `proxima_caixa()` como função pura; o
que falta e este arquivo cobre é o fio inteiro: será que `/registrar`
grava a caixa certa em `progresso`, que `/fila` respeita revisão-antes-de-
novas de verdade contra o banco, e que `/erros` ordena por reincidência.
"""
from core import db
from core.scheduler_regras import MAX_CAIXA


def _registrar(client, usuario, questao_id, veredito, dicas_usadas=0):
    r = client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": veredito, "resposta": "x", "dicas_usadas": dicas_usadas},
        headers=usuario["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_carga_e_fila_consistentes_para_usuario_novo(client, usuario):
    carga = client.get("/carga", headers=usuario["headers"]).json()
    fila = client.get("/fila", headers=usuario["headers"]).json()

    assert carga["revisoes"] == 0  # nunca respondeu nada ainda
    assert len(fila) <= carga["teto"]
    # sem revisão nenhuma, tudo que vier na fila tem que ser caixa 0 (inédita)
    assert all(q["caixa"] == 0 for q in fila)


def test_correta_sem_dica_promove_uma_caixa(client, usuario, questao_id):
    resultado = _registrar(client, usuario, questao_id, "correta")
    assert resultado["caixa"] == 1


def test_correta_com_dica_mantem_a_caixa(client, usuario, questao_id):
    _registrar(client, usuario, questao_id, "correta")               # 0 -> 1
    resultado = _registrar(client, usuario, questao_id, "correta", dicas_usadas=1)
    assert resultado["caixa"] == 1                                   # dica: mantém, não promove


def test_parcial_desce_uma_caixa(client, usuario, questao_id):
    _registrar(client, usuario, questao_id, "correta")                # 0 -> 1
    _registrar(client, usuario, questao_id, "correta")                # 1 -> 2
    resultado = _registrar(client, usuario, questao_id, "parcial")    # 2 -> 1
    assert resultado["caixa"] == 1


def test_incorreta_zera_mesmo_de_caixa_alta(client, usuario, questao_id):
    for _ in range(3):
        _registrar(client, usuario, questao_id, "correta")
    resultado = _registrar(client, usuario, questao_id, "incorreta")
    assert resultado["caixa"] == 0


def test_promocao_nao_passa_do_teto_de_caixa(client, usuario, questao_id):
    resultado = None
    for _ in range(MAX_CAIXA + 5):  # bem mais tentativas do que caixas existem
        resultado = _registrar(client, usuario, questao_id, "correta")
    assert resultado["caixa"] == MAX_CAIXA


def test_erro_zera_a_caixa_mesmo_apos_a_promocao_ficar_no_erro_caderno(client, usuario, questao_id):
    _registrar(client, usuario, questao_id, "incorreta")
    erros = client.get("/erros", headers=usuario["headers"]).json()
    entrada = next((e for e in erros if e["questao_id"] == questao_id), None)
    assert entrada is not None
    assert entrada["vezes"] == 1

    _registrar(client, usuario, questao_id, "incorreta")
    erros = client.get("/erros", headers=usuario["headers"]).json()
    entrada = next(e for e in erros if e["questao_id"] == questao_id)
    assert entrada["vezes"] == 2  # ON CONFLICT ... vezes = vezes + 1, não um registro novo


def test_acerto_nao_entra_no_caderno_de_erros(client, usuario, questao_id):
    _registrar(client, usuario, questao_id, "correta")
    erros = client.get("/erros", headers=usuario["headers"]).json()
    assert questao_id not in {e["questao_id"] for e in erros}


def test_revisao_vencida_aparece_na_fila_como_revisao(client, usuario, questao_id):
    _registrar(client, usuario, questao_id, "correta")  # cria a linha em progresso (caixa 1)

    # Força o vencimento: sem isso prox_revisao é sempre no futuro (mínimo
    # 1 dia — INTERVALOS[0]) e a revisão nunca apareceria na fila hoje.
    db.query(
        "UPDATE progresso SET prox_revisao = CURRENT_DATE WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id},
    )

    fila = client.get("/fila", headers=usuario["headers"]).json()
    entrada = next((q for q in fila if q["id"] == questao_id), None)
    assert entrada is not None
    assert entrada["caixa"] == 1  # veio de progresso, não do default de inédita (caixa 0)

    carga = client.get("/carga", headers=usuario["headers"]).json()
    assert carga["revisoes"] >= 1
