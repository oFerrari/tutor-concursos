"""
Interrupção proativa — a regra que manda PARAR a fila.

Separada de `sugestao()` porque o produto é outro: sugestão é tendência
(disciplina fraca há semanas) pra ler quando quiser; intervenção é estado de
AGORA (3 erros seguidos) e vem com pergunta pronta pro tutor.

`sugestao_erros_seguidos` é pura — testável sem banco, mesmo molde do resto
de `ritmo_regras`.
"""
from core import db, ritmo, ritmo_regras

VERSAO = "test-intervencao-v1"


def _t(veredito, tema="Peculato", disciplina="Direito Penal"):
    return {"veredito": veredito, "tema": tema, "disciplina": disciplina}


def test_tres_erros_seguidos_disparam():
    r = ritmo_regras.sugestao_erros_seguidos([_t("incorreta")] * 3)
    assert r and r["motivo"] == "erros_seguidos"
    assert "Peculato" in r["texto"] and "Peculato" in r["pergunta"]


def test_um_acerto_no_meio_nao_dispara():
    """A janela é de erros CONSECUTIVOS: acertar no meio significa que o
    aluno não está batendo a cabeça, está oscilando — e oscilar é o normal
    de quem aprende."""
    assert ritmo_regras.sugestao_erros_seguidos(
        [_t("incorreta"), _t("correta"), _t("incorreta")]) is None


def test_amostra_menor_que_a_janela_nao_dispara():
    """Dois erros num total de dois não é sequência, é a amostra inteira —
    a mesma guarda de `sugestao_sequencia`."""
    assert ritmo_regras.sugestao_erros_seguidos([_t("incorreta")] * 2) is None


def test_parcial_conta_como_erro():
    """`parcial` não é acerto: vai pro caderno de erros e desce a caixa.
    Tratá-lo como acerto aqui faria a interrupção nunca disparar pra quem
    erra "quase acertando", que é exatamente quem mais precisa parar."""
    r = ritmo_regras.sugestao_erros_seguidos([_t("parcial"), _t("incorreta"), _t("parcial")])
    assert r is not None


def test_temas_diferentes_caem_pra_disciplina():
    """"Errou 3 seguidas" é observação; "errou 3 seguidas de Direito Penal"
    é diagnóstico. Sem tema comum, a disciplina ainda dá o que perguntar."""
    r = ritmo_regras.sugestao_erros_seguidos(
        [_t("incorreta", tema="A"), _t("incorreta", tema="B"), _t("incorreta", tema="C")])
    assert r and "Direito Penal" in r["texto"]


def test_sem_assunto_comum_ainda_interrompe():
    """Nem tema nem disciplina em comum: o texto perde o diagnóstico mas a
    interrupção continua — três erros seguidos é motivo suficiente."""
    r = ritmo_regras.sugestao_erros_seguidos([
        _t("incorreta", tema="A", disciplina="X"),
        _t("incorreta", tema="B", disciplina="Y"),
        _t("incorreta", tema="C", disciplina="Z")])
    assert r and "3 erros seguidos" in r["texto"]


def test_rota_devolve_sugestao_e_intervencao_juntas(client, usuario):
    """Quem responde uma questão precisa dos dois e não deve pagar dois
    round-trips."""
    r = client.get("/sugestao", headers=usuario["headers"]).json()
    assert set(r) == {"sugestao", "intervencao"}
    assert r["intervencao"] is None          # conta nova, sem tentativa

    qs = db.query("SELECT id FROM questao LIMIT 3")
    if len(qs) < 3:
        return
    for q in qs:
        db.query(
            "INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, "
            "dicas_usadas, segundos) VALUES (%(u)s, %(q)s, 'x', 'incorreta', 0, 30)",
            {"u": usuario["id"], "q": q["id"]},
        )
    r = client.get("/sugestao", headers=usuario["headers"]).json()
    assert r["intervencao"] is not None
    assert r["intervencao"]["pergunta"]      # sempre leva pra algum lugar


def test_intervencao_respeita_a_mesa(client, usuario):
    """Errar em Penal não deve parar a sessão de quem sentou na mesa que só
    cobre Constitucional — mesmo recorte do resto de `ritmo`."""
    linhas = db.query("SELECT DISTINCT disciplina FROM questao ORDER BY 1")
    if len(linhas) < 2:
        return
    errada, outra = linhas[0]["disciplina"], linhas[1]["disciplina"]

    for q in db.query("SELECT id FROM questao WHERE disciplina = %(d)s LIMIT 3", {"d": errada}):
        db.query(
            "INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, "
            "dicas_usadas, segundos) VALUES (%(u)s, %(q)s, 'x', 'incorreta', 0, 30)",
            {"u": usuario["id"], "q": q["id"]},
        )

    m = client.post("/mesas", json={"nome": "Só a outra"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s,'e') RETURNING id",
                   {"m": m["id"]})["id"]
    db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
             "VALUES (%(e)s, %(d)s, 1, 'x')", {"e": eid, "d": outra})

    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}
    assert client.get("/sugestao", headers=cab).json()["intervencao"] is None
    assert ritmo.intervencao(usuario["id"]) is not None      # sem mesa, dispara
