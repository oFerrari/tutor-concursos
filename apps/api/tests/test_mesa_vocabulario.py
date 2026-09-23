"""O acervo e o edital não falam a mesma língua — e a ponte sai do próprio edital.

Medido em 22/09/2026: material chamado "Criminalística" numa mesa cujo edital
diz "Ciências Forenses" ficava fora de fila, desempenho, caderno, simulado e
mesa — 62 questões (15% do acervo). A correção NÃO pode ser um apelido fixo
entre esses dois nomes: acertaria este concurso e erraria o próximo. Por isso
estes testes usam um concurso inventado, sem nenhum nome do banco atual.
"""
from core import db, mesa, scheduler

VERSAO = "test-mesa-vocabulario-v1"

BANCARIOS = "Conhecimentos Bancários"


def _mesa_com_edital(client, usuario, topicos: list[tuple[str, str]]) -> int:
    m = client.post("/mesas", json={"nome": "Banco do Norte"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, 'Edital sintético') "
                   "RETURNING id", {"m": m["id"]})["id"]
    for ordem, (disciplina, texto) in enumerate(topicos, 1):
        db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
                 "VALUES (%(e)s, %(d)s, %(o)s, %(t)s)",
                 {"e": eid, "d": disciplina, "o": ordem, "t": texto})
    return m["id"]


def _material(usuario, disciplina: str) -> int:
    return db.exec1("INSERT INTO documento (titulo, tipo, disciplina, usuario_id) "
                    "VALUES (%(t)s, 'aula', %(d)s, %(u)s) RETURNING id",
                    {"t": f"apostila de {disciplina}", "d": disciplina,
                     "u": usuario["id"]})["id"]


def test_material_com_outro_nome_entra_pelo_cabecalho_do_topico(client, usuario):
    mid = _mesa_com_edital(client, usuario, [
        (BANCARIOS, "3.1 Matemática Financeira: juros simples e compostos; descontos."),
        ("Língua Portuguesa", "1.1 Interpretação de texto: coesão e coerência."),
    ])
    _material(usuario, "Matemática Financeira")

    mapa = mesa.mapa_do_acervo(mid, usuario["id"])

    assert "Matemática Financeira" in mapa[BANCARIOS]
    assert "Matemática Financeira" not in mapa["Língua Portuguesa"]
    assert "Matemática Financeira" in mesa.recorte(mesa.disciplinas(mid), mapa)
    assert mesa.dono_no_alvo("Matemática Financeira", mapa) == BANCARIOS


def test_mencao_no_corpo_do_topico_nao_basta(client, usuario):
    """Só o CABEÇALHO (antes do ":") é o edital dizendo que a matéria mora ali.
    Menção solta na lista de conteúdos puxaria qualquer material citado de
    passagem para dentro da disciplina."""
    mid = _mesa_com_edital(client, usuario, [
        (BANCARIOS, "3.2 Sistema Financeiro Nacional: estrutura; noções de ética no atendimento."),
    ])
    _material(usuario, "Ética")

    assert "Ética" not in mesa.mapa_do_acervo(mid, usuario["id"])[BANCARIOS]


def test_acento_e_caixa_nao_separam_o_mesmo_nome(client, usuario):
    mid = _mesa_com_edital(client, usuario, [
        (BANCARIOS, "3.1 MATEMATICA FINANCEIRA: juros."),
    ])
    _material(usuario, "Matemática Financeira")

    assert "Matemática Financeira" in mesa.mapa_do_acervo(mid, usuario["id"])[BANCARIOS]


def test_nome_contido_continua_valendo(client, usuario):
    """A regra antiga de `mesa.filtro` — um nome contém o outro — segue dentro
    do mapa: o recorte novo é superconjunto do antigo, nunca menor."""
    mid = _mesa_com_edital(client, usuario, [
        ("Noções De Direito Tributário", "1.1 Tributo: conceito e espécies."),
    ])
    _material(usuario, "Direito Tributário")

    mapa = mesa.mapa_do_acervo(mid, usuario["id"])
    assert "Direito Tributário" in mapa["Noções De Direito Tributário"]


def test_disciplina_manual_soma_ao_edital(client, usuario):
    """Decisão do dono (22/09/2026): o manual é "como se o PDF tivesse deixado
    alguma de fora" — soma, não é ignorado nem substitui."""
    mid = _mesa_com_edital(client, usuario, [(BANCARIOS, "3.1 Juros: simples.")])
    _material(usuario, "Estatística Aplicada")
    r = client.patch(f"/mesas/{mid}", json={"disciplinas": ["Estatística Aplicada"]},
                     headers=usuario["headers"])
    assert r.status_code == 200, r.text

    assert mesa.disciplinas(mid) == sorted([BANCARIOS, "Estatística Aplicada"])


def test_mesa_sem_alvo_segue_sem_filtro(client, usuario):
    """`None` é "acervo inteiro" (010). O mapa não pode transformá-lo em lista
    vazia, que esvaziaria fila, simulado e desempenho da mesa no dia 1."""
    m = client.post("/mesas", json={"nome": "Sem edital"}, headers=usuario["headers"]).json()
    assert mesa.recorte(mesa.disciplinas(m["id"]), mesa.mapa_do_acervo(m["id"], usuario["id"])) is None


def test_desempenho_soma_no_nome_do_edital_e_refaz_o_percentual():
    """Média de percentuais daria peso igual a disciplina de 2 e de 200 questões."""
    linhas = [
        {"usuario_id": 1, "disciplina": "Matemática Financeira", "questoes": 8, "dominadas": 2,
         "tentativas": 4, "acertos": 1, "pct_acerto": 25.0, "cobertura_pct": 25.0},
        {"usuario_id": 1, "disciplina": BANCARIOS, "questoes": 2, "dominadas": 0,
         "tentativas": 4, "acertos": 3, "pct_acerto": 75.0, "cobertura_pct": 0.0},
    ]
    mapa = {BANCARIOS: ["Matemática Financeira", BANCARIOS]}

    [g] = scheduler._no_nome_do_alvo(linhas, mapa)

    assert g["disciplina"] == BANCARIOS
    assert (g["questoes"], g["dominadas"], g["tentativas"], g["acertos"]) == (10, 2, 8, 4)
    assert g["pct_acerto"] == 50.0
    assert g["cobertura_pct"] == 20.0


def test_stats_e_edital_contam_o_material_de_outro_nome(client, usuario):
    """Fim a fim: a tentativa numa questão do material "Matemática Financeira"
    aparece no /stats e no /edital da mesa cujo edital só fala em
    "Conhecimentos Bancários" — sob o nome do edital."""
    mid = _mesa_com_edital(client, usuario, [
        (BANCARIOS, "3.1 Matemática Financeira: juros simples e compostos."),
    ])
    doc = _material(usuario, "Matemática Financeira")
    qid = db.exec1(
        "INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito, dicas, "
        "fonte_chunks, usuario_id) VALUES (%(d)s, 'Matemática Financeira', 'Juros', "
        "'O que é juro simples?', 'Juro sobre o capital inicial.', '[]'::jsonb, '{}', %(u)s) "
        "RETURNING id", {"d": doc, "u": usuario["id"]})["id"]
    db.query("INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, dicas_usadas, "
             "segundos) VALUES (%(u)s, %(q)s, 'x', 'correta', 0, 10)",
             {"u": usuario["id"], "q": qid})
    db.query("INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao) "
             "VALUES (%(u)s, %(q)s, 1, CURRENT_DATE + 3)", {"u": usuario["id"], "q": qid})
    cab = {**usuario["headers"], "X-Mesa-Id": str(mid)}

    stats = {s["disciplina"]: s for s in client.get("/stats", headers=cab).json()}
    assert BANCARIOS in stats, stats
    assert "Matemática Financeira" not in stats, "a tela tem de mostrar o nome do edital"
    assert (stats[BANCARIOS]["tentativas"], stats[BANCARIOS]["acertos"]) == (1, 1)

    cobertura = {c["disciplina"]: c for c in client.get("/edital", headers=cab).json()["cobertura"]}
    assert cobertura[BANCARIOS]["questoes_disciplina"] >= 1
