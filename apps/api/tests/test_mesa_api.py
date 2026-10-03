"""
Mesas de estudo (migração 010) — CRUD, escopo por `X-Mesa-Id` e, o mais
importante, a DECISÃO de projeto: mesa é filtro, não silo.

O teste que mais importa aqui é `test_caderno_de_erros_atravessa_mesas`:
ele falha se alguém, um dia, resolver escopar `progresso`/`erro_caderno`
por mesa. A decisão de que a memória SM-2 é do ALUNO (e não do concurso)
não está só escrita em db/010_mesa.sql — está executável.

Edital e tópico entram por INSERT direto: a extração de PDF já é testada em
test_edital.py, e o que se testa aqui é o RECORTE que os tópicos causam,
não como eles foram parseados.
"""
import pytest

from core import db, scheduler

VERSAO = "test-mesa-v2"


def _criar_mesa(client, usuario, nome, disciplina=None):
    """Mesa nova; com `disciplina`, já nasce com edital e um tópico — que é
    o que faz o filtro existir (mesa sem edital não recorta nada)."""
    r = client.post("/mesas", json={"nome": nome}, headers=usuario["headers"])
    assert r.status_code == 200, r.text
    m = r.json()
    if disciplina:
        eid = db.exec1(
            "INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, %(t)s) RETURNING id",
            {"m": m["id"], "t": f"edital de {nome}"},
        )["id"]
        db.query(
            "INSERT INTO topico (edital_id, disciplina, ordem, texto) "
            "VALUES (%(e)s, %(d)s, 1, '1.1 tópico de teste')",
            {"e": eid, "d": disciplina},
        )
    return m


def _cab(usuario, mesa):
    return {**usuario["headers"], "X-Mesa-Id": str(mesa["id"])}


@pytest.fixture
def duas_disciplinas(acervo):
    """Duas disciplinas do acervo PÚBLICO.

    O `usuario_id IS NULL` não é enfeite — é o mesmo defeito que
    `test_geracao._disciplina_do_acervo` já documenta, agora na outra ponta.
    Sem ele, a consulta era `SELECT DISTINCT disciplina FROM questao`, e
    bastou a 026 existir (questão gerada da apostila do aluno) pra ela
    devolver "Criminalística" — disciplina com dezenas de questões PRIVADAS e
    zero públicas. Sete testes de recorte e cobertura quebraram de uma vez,
    todos afirmando coisas certas sobre um dado que não era acervo comum."""
    linhas = db.query("""SELECT DISTINCT disciplina FROM questao
                          WHERE usuario_id IS NULL AND disciplina IS NOT NULL
                          ORDER BY 1""")
    if len(linhas) < 2:
        pytest.skip("acervo precisa de questões em pelo menos 2 disciplinas")
    return [l["disciplina"] for l in linhas[:2]]


# ------------------------------------------------------------------- básico
def test_mesa_padrao_nasce_sob_demanda(client, usuario):
    """Conta nova não tem mesa nenhuma até alguém precisar de uma — e a
    primeira rota escopada resolve isso sozinha, sem ritual de criação
    (mesmo padrão de auth.usuario_da_cli)."""
    assert client.get("/mesas", headers=usuario["headers"]).json() == []

    assert client.get("/carga", headers=usuario["headers"]).status_code == 200

    mesas = client.get("/mesas", headers=usuario["headers"]).json()
    assert len(mesas) == 1
    assert mesas[0]["nome"] == "Mesa principal"
    assert mesas[0]["topicos"] == 0        # sem edital ainda


def test_mesa_atual_resolve_a_mesma_regra_de_fallback(client, usuario):
    """GET /mesa é a fonte única de "em qual mesa eu estou" — sem ele, o
    cliente reimplementaria o fallback e a sidebar poderia mostrar um nome
    enquanto a fila responde por outra mesa."""
    primeira = _criar_mesa(client, usuario, "Primeira")
    segunda = _criar_mesa(client, usuario, "Segunda")

    sem_header = client.get("/mesa", headers=usuario["headers"]).json()
    assert sem_header["id"] == primeira["id"]        # a mais antiga

    com_header = client.get("/mesa", headers=_cab(usuario, segunda)).json()
    assert com_header["id"] == segunda["id"]


def test_listar_traz_cobertura_no_mesmo_criterio_do_painel(client, usuario, duas_disciplinas):
    dentro, _ = duas_disciplinas
    _criar_mesa(client, usuario, "Com edital", disciplina=dentro)

    m = client.get("/mesas", headers=usuario["headers"]).json()[0]
    assert m["topicos"] == 1
    assert m["disciplinas"] == [dentro]
    assert m["questoes"] > 0            # o universo é o acervo DA disciplina
    assert m["dominadas"] == 0
    assert m["cobertura_pct"] == 0.0
    assert m["ultimo_estudo"] is None   # ninguém estudou nesta conta ainda


def _dominar_por_assunto(usuario, eid, disciplina, n_assuntos=None):
    """Responde e domina as questões públicas da disciplina, cada uma ligada a um
    assunto do edital (039) — o mapa de domínio só conta assunto com questão ligada.
    Devolve quantos assuntos DIFERENTES receberam questão."""
    tops = [t["id"] for t in db.query("SELECT id FROM topico WHERE edital_id = %(e)s AND disciplina = %(d)s "
                                      "ORDER BY ordem", {"e": eid, "d": disciplina})][:n_assuntos]
    qs = [q["id"] for q in db.query("SELECT id FROM questao WHERE disciplina = %(d)s AND usuario_id IS NULL "
                                    "ORDER BY id", {"d": disciplina})]
    ligados = set()
    for i, q in enumerate(qs):
        t = tops[i % len(tops)]
        ligados.add(t)
        db.query("INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, dicas_usadas) "
                 "VALUES (%(u)s, %(q)s, 'r', 'correta', 0)", {"u": usuario["id"], "q": q})
        db.query("INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao) "
                 "VALUES (%(u)s, %(q)s, 3, CURRENT_DATE + 15)", {"u": usuario["id"], "q": q})
        db.query("INSERT INTO questao_no_edital (questao_id, edital_id, topico_id, origem) "
                 "VALUES (%(q)s, %(e)s, %(t)s, 'modelo')", {"q": q, "e": eid, "t": t})
    return len(ligados)


def test_cartao_mede_progresso_em_topicos_do_edital(client, usuario, duas_disciplinas):
    """
    O cartão da mesa fala em TÓPICOS (a unidade do edital) pela MESMA conta do mapa
    de domínio, do Meu edital e da probabilidade de fechamento (02/10/2026): tópico
    coberto = assunto do edital dominado. Até então era ESTIMADO pela fração de
    questões dominadas, e 107 questões sobre meio edital davam 94% fechado.
    """
    dentro, _ = duas_disciplinas
    mesa = _criar_mesa(client, usuario, "Por tópico", disciplina=dentro)
    eid = db.exec1("SELECT id FROM edital WHERE mesa_id = %(m)s", {"m": mesa["id"]})["id"]
    db.query(
        "INSERT INTO topico (edital_id, disciplina, ordem, texto) "
        "SELECT %(e)s, %(d)s, g, '1.' || g || ' outro tópico' FROM generate_series(2, 4) g",
        {"e": eid, "d": dentro},
    )

    m = client.get("/mesas", headers=usuario["headers"]).json()[0]
    assert m["topicos"] == 4
    assert m["dominadas"] == 0
    assert m["topicos_cobertos"] == 0
    assert m["cobertura_topicos_pct"] == 0.0

    cobertos = _dominar_por_assunto(usuario, eid, dentro)
    m = client.get("/mesas", headers=usuario["headers"]).json()[0]
    assert m["dominadas"] == m["questoes"] > 0
    assert m["topicos_cobertos"] == cobertos > 0
    assert m["cobertura_topicos_pct"] == round(100.0 * cobertos / 4, 1)


def test_topicos_cobertos_pesam_pelo_tamanho_da_disciplina(client, usuario, duas_disciplinas):
    """
    Duas disciplinas com PESOS diferentes no edital: dominar assuntos da que vale 30
    tópicos e nada da que vale 10 dá cobertos/40 — não a média entre disciplinas nem
    a fração de QUESTÕES dominadas.
    """
    pesada, leve = duas_disciplinas
    mesa = _criar_mesa(client, usuario, "Pesos diferentes", disciplina=pesada)
    eid = db.exec1("SELECT id FROM edital WHERE mesa_id = %(m)s", {"m": mesa["id"]})["id"]
    db.query("DELETE FROM topico WHERE edital_id = %(e)s", {"e": eid})
    for disciplina, n in ((pesada, 30), (leve, 10)):
        db.query(
            "INSERT INTO topico (edital_id, disciplina, ordem, texto) "
            "SELECT %(e)s, %(d)s, g, %(d)s || ' ' || g FROM generate_series(1, %(n)s) g",
            {"e": eid, "d": disciplina, "n": n},
        )
    cobertos = _dominar_por_assunto(usuario, eid, pesada)

    m = client.get("/mesas", headers=usuario["headers"]).json()[0]
    assert m["topicos"] == 40
    assert m["topicos_cobertos"] == cobertos > 0
    assert m["cobertura_topicos_pct"] == round(100.0 * cobertos / 40, 1)
    # E o par por questão continua sendo outro número — os dois convivem no
    # payload de propósito (o cartão mostra tópicos, o painel mostra questões).
    assert m["cobertura_pct"] != m["cobertura_topicos_pct"]


def test_crud_da_mesa(client, usuario):
    m = _criar_mesa(client, usuario, "PF Agente")
    assert m["nome"] == "PF Agente"

    # nome repetido não passa: com duas "PF Agente" não haveria como
    # distinguir uma da outra nem na tela nem no --mesa da CLI
    r = client.post("/mesas", json={"nome": "pf agente"}, headers=usuario["headers"])
    assert r.status_code == 400

    r = client.patch(f"/mesas/{m['id']}", json={"banca": "Cebraspe"},
                     headers=usuario["headers"])
    assert r.status_code == 200 and r.json()["banca"] == "Cebraspe"
    assert r.json()["nome"] == "PF Agente"      # PATCH parcial não apaga o resto

    assert client.delete(f"/mesas/{m['id']}", headers=usuario["headers"]).status_code == 200
    assert client.get(f"/mesas/{m['id']}", headers=usuario["headers"]).status_code == 404


def test_mesa_de_outro_usuario_nunca_aparece(client, usuario, outro_usuario):
    """O id identifica, o token AUTORIZA — mesmo espírito de
    simulado.pertence_a(). 404 e não 403: não confirma pra quem chuta um id
    que ele existe e só não é dele."""
    alheia = _criar_mesa(client, outro_usuario, "Mesa do outro")

    assert client.get(f"/mesas/{alheia['id']}", headers=usuario["headers"]).status_code == 404
    assert client.get("/fila", headers=_cab(usuario, alheia)).status_code == 404
    assert client.patch(f"/mesas/{alheia['id']}", json={"nome": "sequestrada"},
                        headers=usuario["headers"]).status_code == 404
    assert client.delete(f"/mesas/{alheia['id']}",
                         headers=usuario["headers"]).status_code == 404
    # e continua de pé pro dono
    assert client.get(f"/mesas/{alheia['id']}",
                      headers=outro_usuario["headers"]).status_code == 200


def test_header_de_mesa_invalido(client, usuario):
    r = client.get("/fila", headers={**usuario["headers"], "X-Mesa-Id": "abc"})
    assert r.status_code == 422
    r = client.get("/fila", headers={**usuario["headers"], "X-Mesa-Id": "999999999"})
    assert r.status_code == 404


# -------------------------------------------------------------- o recorte
def test_mesa_recorta_fila_e_stats_pelas_disciplinas_do_edital(client, usuario,
                                                               duas_disciplinas):
    dentro, fora = duas_disciplinas
    m = _criar_mesa(client, usuario, "Só uma disciplina", disciplina=dentro)

    assert client.get(f"/mesas/{m['id']}", headers=usuario["headers"]).json()["disciplinas"] \
        == [dentro]

    fila = client.get("/fila", headers=_cab(usuario, m)).json()
    assert fila, "acervo tem questões da disciplina do edital, a fila não deveria vir vazia"
    assert {q["disciplina"] for q in fila} == {dentro}

    # E o filtro está de fato filtrando: a MESMA conta, numa mesa sem
    # edital, enxerga a outra disciplina. Comparar contra "sem header"
    # não serviria — sem header cai na mesa padrão, que aqui é justamente
    # a filtrada (é a mais antiga da conta).
    livre = _criar_mesa(client, usuario, "Sem recorte")
    sem_recorte = client.get("/fila", headers=_cab(usuario, livre)).json()
    assert fora in {q["disciplina"] for q in sem_recorte}

    # stats respeita o mesmo recorte que a fila — é o mesmo predicado
    # (core/mesa.filtro), e é justamente isso que impede o painel de dizer
    # uma cobertura e a fila entregar outra.
    stats = client.get("/stats", headers=_cab(usuario, m)).json()
    assert {d["disciplina"] for d in stats} <= {dentro}


def test_mesa_sem_edital_nao_filtra_nada(client, usuario, duas_disciplinas):
    """Degradação graciosa, não defeito: mesa recém-criada (antes do PDF)
    mostra o acervo inteiro, que é o comportamento anterior à 010."""
    vazia = _criar_mesa(client, usuario, "Mesa sem edital")
    assert client.get(f"/mesas/{vazia['id']}",
                      headers=usuario["headers"]).json()["disciplinas"] is None

    fila = client.get("/fila", headers=_cab(usuario, vazia)).json()
    assert len(set(q["disciplina"] for q in fila)) >= 2


# ------------------------------------- a decisão: progresso é do ALUNO
def test_caderno_de_erros_atravessa_mesas(client, usuario, duas_disciplinas, questao_id):
    """
    O TESTE DA DECISÃO CENTRAL DA 010. Errar uma questão estudando pra um
    concurso tem que aparecer no caderno de erros do outro concurso que
    cobra a mesma matéria — é conhecimento da pessoa, não do edital. Se
    alguém escopar `erro_caderno`/`progresso` por mesa um dia, é aqui que
    quebra.
    """
    disciplina = db.exec1("SELECT disciplina FROM questao WHERE id = %(q)s",
                          {"q": questao_id})["disciplina"]
    mesa_a = _criar_mesa(client, usuario, "Concurso A", disciplina=disciplina)
    mesa_b = _criar_mesa(client, usuario, "Concurso B", disciplina=disciplina)

    r = client.post(f"/questoes/{questao_id}/registrar",
                    json={"veredito": "incorreta", "resposta": "chute"},
                    headers=_cab(usuario, mesa_a))
    assert r.status_code == 200, r.text

    erros_b = client.get("/erros", headers=_cab(usuario, mesa_b)).json()
    assert questao_id in [e["questao_id"] for e in erros_b]

    # e a caixa (SM-2) também é a mesma pros dois lados
    assert db.exec1(
        "SELECT count(*) AS n FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id})["n"] == 1


def test_apagar_mesa_leva_o_edital_mas_nao_o_que_voce_aprendeu(client, usuario, questao_id):
    disciplina = db.exec1("SELECT disciplina FROM questao WHERE id = %(q)s",
                          {"q": questao_id})["disciplina"]
    m = _criar_mesa(client, usuario, "Mesa descartável", disciplina=disciplina)
    client.post(f"/questoes/{questao_id}/registrar",
                json={"veredito": "incorreta", "resposta": "chute"},
                headers=_cab(usuario, m))

    assert client.delete(f"/mesas/{m['id']}", headers=usuario["headers"]).status_code == 200

    assert db.exec1("SELECT count(*) AS n FROM edital WHERE mesa_id = %(m)s",
                    {"m": m["id"]})["n"] == 0
    assert db.exec1(
        "SELECT count(*) AS n FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id})["n"] == 1
    assert db.exec1(
        "SELECT count(*) AS n FROM erro_caderno WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id})["n"] == 1


# ------------------------------------------------------------- simulado
def test_simulado_fica_etiquetado_com_a_mesa(client, usuario, acervo):
    mesa_a = _criar_mesa(client, usuario, "Prova A")
    mesa_b = _criar_mesa(client, usuario, "Prova B")

    r = client.post("/simulados", json={"n": 2}, headers=_cab(usuario, mesa_a))
    assert r.status_code == 200, r.text
    sid = r.json()["simulado_id"]

    assert sid in [s["id"] for s in client.get("/simulados",
                                               headers=_cab(usuario, mesa_a)).json()]
    assert sid not in [s["id"] for s in client.get("/simulados",
                                                   headers=_cab(usuario, mesa_b)).json()]


def test_simulado_sobrevive_a_mesa_apagada(client, usuario, acervo):
    """ON DELETE SET NULL (não CASCADE): a prova que você já fez é
    histórico de desempenho seu, só etiquetado com a mesa."""
    m = _criar_mesa(client, usuario, "Mesa efêmera")
    sid = client.post("/simulados", json={"n": 1}, headers=_cab(usuario, m)).json()["simulado_id"]

    client.delete(f"/mesas/{m['id']}", headers=usuario["headers"])

    linha = db.exec1("SELECT usuario_id, mesa_id FROM simulado WHERE id = %(s)s", {"s": sid})
    assert linha is not None and linha["mesa_id"] is None
    assert linha["usuario_id"] == usuario["id"]


# ------------------------------- alvo declarado à mão, sem edital (017)
def test_mesa_nova_nao_tem_alvo_e_ainda_assim_e_utilizavel(client, usuario, acervo):
    """
    O relato que originou a 017: mesa recém-criada aparecia com "4/54
    questões · 7%" — número verdadeiro no lugar errado (é o progresso da
    PESSOA no acervo inteiro, num cartão que promete o da MESA).

    A correção NÃO foi zerar o escopo: `origem_alvo` diz "nenhum" pro
    cartão esconder a barra, e o filtro segue aberto pra mesa não nascer
    inútil. Escopo vazio deixaria fila, desafio, simulado e stats vazios.
    """
    m = _criar_mesa(client, usuario, "Sem alvo")
    ctx = client.get("/mesa", headers=_cab(usuario, m)).json()
    assert ctx["origem_alvo"] == "nenhum"
    assert ctx["disciplinas"] is None

    # utilizável: a fila continua servindo o acervo
    assert len(client.get("/fila", headers=_cab(usuario, m)).json()) > 0


def test_alvo_manual_recorta_como_o_edital(client, usuario, duas_disciplinas):
    """Quem estuda pra concurso cujo edital ainda não saiu (metade do tempo
    de preparação) passa a poder recortar a mesa mesmo assim."""
    dentro, fora = duas_disciplinas
    m = _criar_mesa(client, usuario, "Alvo manual")
    cab = _cab(usuario, m)

    r = client.patch(f"/mesas/{m['id']}", json={"disciplinas": [dentro]},
                     headers=usuario["headers"])
    assert r.status_code == 200

    ctx = client.get("/mesa", headers=cab).json()
    assert ctx["origem_alvo"] == "manual"
    assert ctx["disciplinas"] == [dentro]

    fila = client.get("/fila", headers=cab).json()
    assert fila and all(q["disciplina"] == dentro for q in fila)
    assert not any(q["disciplina"] == fora for q in fila)


def test_manual_soma_ao_edital_e_o_prazo_segue_do_edital(client, usuario, duas_disciplinas):
    """MUDANÇA DE CONTRATO, decidida pelo dono em 22/09/2026. Antes o edital
    tinha precedência e o manual era gravado sem nunca valer: a mesa com
    edital aceitava a escolha na tela e continuava com a mesma fila. Agora o
    manual SOMA — "é como se eu não tivesse pego todas ou faltasse ler alguma".

    O que a precedência protegia continua protegido: o PRAZO sai só do edital,
    então o recorte cresce sem passar a vir de outro lugar."""
    manual, doPdf = duas_disciplinas
    m = _criar_mesa(client, usuario, "Os dois", disciplina=doPdf)
    client.patch(f"/mesas/{m['id']}", json={"disciplinas": [manual]},
                 headers=usuario["headers"])

    ctx = client.get("/mesa", headers=_cab(usuario, m)).json()
    assert ctx["origem_alvo"] == "edital"
    assert ctx["disciplinas"] == sorted([doPdf, manual])


def test_disciplina_inexistente_no_acervo_e_recusada(client, usuario, duas_disciplinas):
    """Nome livre viraria filtro que nunca casa nada, e o sintoma seria fila
    vazia sem explicação — o aluno acharia que o app quebrou.

    MUDANÇA DE CONTRATO, e ela veio do uso: a versão anterior FILTRAVA o nome
    inválido e gravava o resto, então a tela dizia "salvo", a lista voltava
    menor e o aluno não tinha como saber por quê (relatado digitando um nome
    qualquer no alvo manual). Agora recusa nomeando o que não existe — mesmo
    princípio de `diagnostico.py` e `candidatos_data_prova`: reportar pro
    operador conferir, nunca decidir calado."""
    dentro, _ = duas_disciplinas
    m = _criar_mesa(client, usuario, "Alvo inválido")
    r = client.patch(f"/mesas/{m['id']}",
                     json={"disciplinas": ["Direito Intergaláctico"]},
                     headers=usuario["headers"])
    assert r.status_code == 400
    assert "Direito Intergaláctico" in r.json()["detail"]
    assert client.get("/mesa", headers=_cab(usuario, m)).json()["origem_alvo"] == "nenhum"

    # E o lote inteiro é recusado, não gravado pela metade: alvo parcial é
    # recorte errado sem ninguém saber que está errado.
    r = client.patch(f"/mesas/{m['id']}",
                     json={"disciplinas": [dentro, "Direito Intergaláctico"]},
                     headers=usuario["headers"])
    assert r.status_code == 400
    assert client.get("/mesa", headers=_cab(usuario, m)).json()["disciplinas"] is None


def test_remover_edital_devolve_a_mesa_ao_alvo_manual(client, usuario, duas_disciplinas):
    """`DELETE /edital` é o que faz a escolha manual PODER valer.

    O edital vence inteiro quando existe (017), então uma tela de alvo manual
    sobre mesa com edital estaria pedindo um trabalho que o servidor ignora —
    e era exatamente o que acontecia: a pessoa escolhia, salvava, e a lista não
    voltava. Agora ou se corrige o edital (na tela dele) ou se troca o edital
    por estudo avulso, e trocar significa o edital sair."""
    manual, doPdf = duas_disciplinas
    m = _criar_mesa(client, usuario, "Troca de alvo", disciplina=doPdf)
    cab = _cab(usuario, m)
    client.patch(f"/mesas/{m['id']}", json={"disciplinas": [manual]},
                 headers=usuario["headers"])
    assert client.get("/mesa", headers=cab).json()["origem_alvo"] == "edital"

    r = client.delete("/edital", headers=cab)
    assert r.status_code == 200, r.text
    # Devolve O QUE FOI EMBORA: a operação é irreversível pelo servidor (os
    # bytes do PDF não ficam guardados), e um "ok" esconderia a perda.
    assert "titulo" in r.json()["removido"] and "topicos" in r.json()["removido"]

    ctx = client.get("/mesa", headers=cab).json()
    assert ctx["origem_alvo"] == "manual"
    assert ctx["disciplinas"] == [manual]
    # Tópico morre pelo CASCADE da 007 — sem limpeza escrita na mão (009).
    assert db.query("SELECT 1 FROM topico t JOIN edital e ON e.id = t.edital_id "
                    "WHERE e.mesa_id = %(m)s", {"m": m["id"]}) == []


def test_remover_edital_de_mesa_sem_edital_da_404(client, usuario):
    """404 e não sucesso vazio: "esta mesa não tem edital" é informação, e
    responder 200 pra um apagar que não apagou nada faria a tela dizer que
    removeu algo que nunca existiu."""
    m = _criar_mesa(client, usuario, "Sem edital nenhum")
    assert client.delete("/edital", headers=_cab(usuario, m)).status_code == 404


def test_remover_edital_nao_apaga_o_progresso(client, usuario, duas_disciplinas):
    """O que o aluno respondeu é DELE, não do edital (mesma decisão da 010 pra
    `progresso`/`tentativa`). Trocar o alvo não pode zerar aprendizado — seria
    punir quem corrige o plano no meio do caminho."""
    manual, doPdf = duas_disciplinas
    m = _criar_mesa(client, usuario, "Progresso sobrevive", disciplina=doPdf)
    cab = _cab(usuario, m)
    fila = client.get("/fila", headers=cab).json()
    assert fila, "precisa de questão no recorte pra medir"
    # Registra pelo CORE e não por rota HTTP: `scheduler.registrar` é o ponto
    # por onde os quatro caminhos de resposta passam (fila, questão avulsa,
    # desafio, simulado), então é ele que representa "o aluno respondeu". Amarrar
    # o teste a uma rota específica mediria a rota, não a invariante.
    scheduler.registrar(usuario["id"], fila[0]["id"], "correta", "resposta do aluno", 0)
    antes = db.exec1("SELECT count(*) n FROM tentativa WHERE usuario_id = %(u)s",
                     {"u": usuario["id"]})["n"]

    client.patch(f"/mesas/{m['id']}", json={"disciplinas": [manual]},
                 headers=usuario["headers"])
    assert client.delete("/edital", headers=cab).status_code == 200

    depois = db.exec1("SELECT count(*) n FROM tentativa WHERE usuario_id = %(u)s",
                      {"u": usuario["id"]})["n"]
    assert depois == antes and antes > 0


def test_lista_vazia_limpa_o_alvo(client, usuario, duas_disciplinas):
    """`[]` tira o alvo (volta ao acervo inteiro); ausente preserva."""
    dentro, _ = duas_disciplinas
    m = _criar_mesa(client, usuario, "Limpar alvo")
    client.patch(f"/mesas/{m['id']}", json={"disciplinas": [dentro]},
                 headers=usuario["headers"])

    client.patch(f"/mesas/{m['id']}", json={"nome": "Só o nome"},
                 headers=usuario["headers"])
    assert client.get("/mesa", headers=_cab(usuario, m)).json()["disciplinas"] == [dentro]

    client.patch(f"/mesas/{m['id']}", json={"disciplinas": []},
                 headers=usuario["headers"])
    assert client.get("/mesa", headers=_cab(usuario, m)).json()["disciplinas"] is None


def test_disciplinas_do_acervo_saem_do_acervo(client, usuario):
    """Lista fixa mentiria num acervo que cresce (ou que está vazio).

    A comparação é contra o acervo PÚBLICO, não contra `documento` inteiro: a
    migração 019 pôs material privado na mesma tabela, e o `DISTINCT` cru
    passaria a devolver a matéria de outro aluno."""
    r = client.get("/disciplinas", headers=usuario["headers"]).json()["disciplinas"]
    publicas = [x["disciplina"] for x in db.query(
        """SELECT DISTINCT disciplina FROM documento
            WHERE usuario_id IS NULL AND disciplina IS NOT NULL ORDER BY 1""")]
    assert r == publicas


def test_acervo_nao_mostra_a_materia_de_outro_aluno(client, usuario, outro_usuario):
    """Vazamento REAL da 019: `SELECT DISTINCT disciplina FROM documento` sem
    predicado de dono mostrava na tela de escolha de alvo o rótulo que OUTRO
    aluno deu ao material dele — "tcc", "meu resumo do TRT". Mesma classe que
    `retrieval.DONO` fecha na busca e `material.sugestoes` no seletor.

    O material do próprio aluno CONTINUA aparecendo, e isso é o produto: subir
    material de uma matéria é justamente como ela passa a existir pra escolher."""
    corpo = ("meu material particular. " * 40).encode()
    client.post("/materiais", files={"arquivo": ("meu.txt", corpo, "text/plain")},
                data={"tipo": "resumo", "disciplina": "Segredo Do Dono"},
                headers=usuario["headers"])
    client.post("/materiais", files={"arquivo": ("dele.txt", corpo + b"x", "text/plain")},
                data={"tipo": "resumo", "disciplina": "Segredo Do Outro"},
                headers=outro_usuario["headers"])

    meu = client.get("/disciplinas", headers=usuario["headers"]).json()["disciplinas"]
    assert "Segredo Do Dono" in meu
    assert "Segredo Do Outro" not in meu

    dele = client.get("/disciplinas", headers=outro_usuario["headers"]).json()["disciplinas"]
    assert "Segredo Do Outro" in dele and "Segredo Do Dono" not in dele

    # E nunca uma opção VAZIA: `disciplina` é nullable desde a 020, e o
    # `DISTINCT` cru devolvia uma linha NULL que virava chip em branco na tela.
    client.post("/materiais", files={"arquivo": ("sem-rotulo.txt", corpo + b"y", "text/plain")},
                data={"tipo": "resumo"}, headers=usuario["headers"])
    assert all(d for d in client.get("/disciplinas", headers=usuario["headers"]).json()["disciplinas"])


# ---------------------------------------------------------------------------
# Edital declarado à mão (POST /edital/manual)
# ---------------------------------------------------------------------------

def test_edital_manual_com_so_a_data_ja_da_prazo_a_meta(client, usuario):
    """A decisão de fundo: um edital declarado à mão É um edital.

    A alternativa era guardar "data prevista" numa coluna nova da mesa e ensinar
    `scheduler.meta` a olhar em dois lugares — e aí o recorte viria de uma fonte
    e o prazo de outra, o defeito que a 010 evitou ao fazer disciplina e data
    saírem do MESMO último edital. Criando um `edital` de verdade, a data cai
    onde a meta já procura.

    Só data, sem matéria, é caso REAL: "a prova deve ser em novembro", programa
    ainda não publicado."""
    m = _criar_mesa(client, usuario, "Só o prazo")
    cab = _cab(usuario, m)
    r = client.post("/edital/manual", json={"data_prova": "2027-03-15"}, headers=cab)
    assert r.status_code == 201, r.text
    assert r.json()["data_prova"] == "2027-03-15" and r.json()["disciplinas"] == []
    # Sem matéria não há recorte, e isso é o estado "nenhum" da 017 — a mesa
    # segue utilizável mostrando o acervo inteiro.
    assert client.get("/mesa", headers=cab).json()["disciplinas"] is None
    assert client.get("/meta", headers=cab).json()["dias_restantes"] > 0


def test_edital_manual_recusa_so_o_vazio_completo(client, usuario):
    """Cada combinação parcial é um caso real de quem estuda antes do edital
    sair (só matérias, só data, só nome), então exigir os três transformaria um
    chute legítimo em bloqueio. O que não se aceita é gravar uma linha que não
    diz nada.

    O CUIDADO que custou um teste: a guarda tem que olhar pro que a PESSOA
    pediu, não pro que o servidor preencheu por ela. Com o fallback de título
    (herdar o nome da mesa) aplicado antes da checagem, um `POST {}` criava um
    edital chamado como a mesa — medido, e corrigido."""
    m = _criar_mesa(client, usuario, "Nada declarado")
    cab = _cab(usuario, m)
    assert client.post("/edital/manual", json={}, headers=cab).status_code == 400
    assert client.post("/edital/manual", json={"titulo": "   "}, headers=cab).status_code == 400
    assert client.post("/edital/manual", json={"disciplinas": ["", "  "]},
                       headers=cab).status_code == 400
    # E nada foi gravado no caminho.
    r = client.get("/edital", headers=cab)
    assert r.status_code == 200 and r.json() is None


def test_edital_manual_limpa_o_nome_da_materia_e_recusa_colagem(client, usuario):
    """`mesa.filtro` compara o nome com ILIKE contra o acervo: espaço duplo e
    quebra de linha colada de PDF fariam o filtro não casar nada, e o sintoma
    seria fila vazia sem explicação. Normaliza na escrita, uma vez.

    O teto de matérias existe pra recusar colagem de um documento inteiro no
    campo, não pra limitar concurso real — o pior edital que passou por aqui (o
    da Dataprev, treze perfis) tem 52."""
    m = _criar_mesa(client, usuario, "Entrada suja")
    cab = _cab(usuario, m)
    r = client.post("/edital/manual", headers=cab, json={
        "disciplinas": ["  Direito   Penal \n", "direito penal", "", "Contabilidade Pública"]})
    assert r.status_code == 201
    # Espaço colapsado, vazio fora, duplicata ignorando caixa fora.
    assert r.json()["disciplinas"] == ["Direito Penal", "Contabilidade Pública"]

    r = client.post("/edital/manual", headers=cab,
                    json={"disciplinas": [f"Materia {i}" for i in range(61)]})
    assert r.status_code == 400 and "limite" in r.json()["detail"]

    r = client.post("/edital/manual", headers=cab, json={"titulo": "X" * 400})
    assert len(r.json()["titulo"]) == 200


def test_edital_manual_substitui_e_nunca_acumula(client, usuario, duas_disciplinas):
    """SUBSTITUI e não soma: duas fontes de recorte é o que 010/017 recusam.

    E a ORDEM é à prova de falha — cria o novo ANTES de apagar o antigo, porque
    `db` roda em autocommit e não tem rollback (CLAUDE.md, "Armadilhas de
    método"). Apagando primeiro, uma falha no meio deixaria a mesa SEM edital
    nenhum, pior do que começou. `mais_recente` ordena por criado_em/id DESC,
    então o novo já vence no instante em que entra."""
    manual, doPdf = duas_disciplinas
    m = _criar_mesa(client, usuario, "Substituição", disciplina=doPdf)
    cab = _cab(usuario, m)
    assert client.get("/mesa", headers=cab).json()["disciplinas"] == [doPdf]

    r = client.post("/edital/manual", headers=cab,
                    json={"titulo": "Declarado à mão", "disciplinas": [manual]})
    assert r.status_code == 201 and r.json()["substituiu"] == 1
    assert db.exec1("SELECT count(*) n FROM edital WHERE mesa_id = %(m)s",
                    {"m": m["id"]})["n"] == 1
    ctx = client.get("/mesa", headers=cab).json()
    assert ctx["origem_alvo"] == "edital" and ctx["disciplinas"] == [manual]
    # O manual antigo é limpo: deixá-lo pra trás criaria um alvo fantasma, que
    # ressuscitaria se este edital fosse removido depois.
    assert ctx["disciplinas_manuais"] == []


def test_edital_manual_aceita_data_no_passado(client, usuario):
    """Quem estuda por edital vencido esperando o próximo é caso corrente (o da
    PF em corpus/ é de 2025). Quem avisa é a TELA; o banco recusar transformaria
    uma situação normal em erro."""
    m = _criar_mesa(client, usuario, "Espera o próximo")
    cab = _cab(usuario, m)
    r = client.post("/edital/manual", headers=cab,
                    json={"titulo": "Vai reabrir", "data_prova": "2020-01-01"})
    assert r.status_code == 201 and r.json()["data_prova"] == "2020-01-01"
    assert client.get("/meta", headers=cab).json()["dias_restantes"] == 0
