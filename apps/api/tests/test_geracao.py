"""
Geração de questão sob demanda a partir do acervo.

O que estes testes travam NÃO é a qualidade da questão (isso é do modelo e
não se testa com asserção) — é a PROVENIÊNCIA e o recorte:

  · questão cujo artigo não veio no lote é descartada, nunca gravada;
  · `documento_id`/`disciplina` saem do chunk casado, não de um parâmetro,
    porque um lote montado por busca atravessa normas;
  · material `historico` nunca vira fonte (não tem artigo, e pode conter
    redação revogada);
  · questão gerada entra na fila SM-2 como qualquer outra — se ficasse só
    na tela, não voltaria pra revisão, ou seja, não seria estudo espaçado.

O LLM é falso (fixture `llm_falso`): a chamada real custa cota e devolve
texto diferente a cada vez, o que testaria o modelo, não o encanamento.
"""
import json
import re

import pytest

from core import db, geracao

VERSAO = "test-geracao-v1"


def _chunk_real(norma: str = "L8112"):
    c = db.exec1(
        """SELECT c.id, c.documento_id, c.artigo, c.texto, c.norma, d.disciplina, d.titulo
             FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.norma = %(n)s AND c.artigo IS NOT NULL
              AND length(c.texto) >= 140 LIMIT 1""",
        {"n": norma},
    )
    if not c:
        pytest.skip(f"acervo sem chunks de {norma}")
    return c


def _questao_do_modelo(artigo: str) -> dict:
    return {"artigo": artigo, "tema": "Tema de teste",
            "enunciado": "Enunciado de teste?", "gabarito": "Gabarito de teste.",
            "dicas": ["d1", "d2", "d3"]}


def _modelo_que_responde_sobre_o_lote(fake):
    """
    Duplê que LÊ o material recebido e devolve uma questão por artigo dele.

    Um retorno fixo não serviria: `sob_demanda` sorteia os trechos, então o
    teste não sabe de antemão quais artigos virão — e um `artigo` fixo cairia
    sempre no descarte por proveniência, testando o descarte em vez do
    caminho feliz. Aqui o duplê imita o único comportamento do modelo real do
    qual a gravação depende: devolver o artigo QUE ESTAVA no material.
    """
    def gerar(prompt, sistema="", json_mode=False, max_tokens=1200, schema=None):
        arts = re.findall(r"\[[^\]]*?art\. ([^\]]+)\]", prompt)
        return json.dumps([_questao_do_modelo(a) for a in dict.fromkeys(arts)])
    fake.gerar = gerar
    return fake


def test_salvar_grava_com_a_disciplina_do_chunk_casado(usuario):
    """A disciplina vem do CHUNK, não de fora: é ela que a mesa usa depois
    pra recortar a fila, e herdar a de um documento escolhido por quem chamou
    rotularia a questão errado."""
    c = _chunk_real()
    salvas, descartes = geracao.salvar([_questao_do_modelo(c["artigo"])], [c])
    assert descartes == []
    assert len(salvas) == 1
    assert salvas[0]["disciplina"] == c["disciplina"]
    gravada = db.exec1(
        "SELECT documento_id, fonte_chunks FROM questao WHERE id = %(i)s", {"i": salvas[0]["id"]})
    assert gravada["documento_id"] == c["documento_id"]
    assert gravada["fonte_chunks"] == [c["id"]]
    db.query("DELETE FROM questao WHERE id = %(i)s", {"i": salvas[0]["id"]})


def test_questao_de_artigo_fora_do_lote_e_descartada(usuario):
    """A invariante do projeto: cobertura que mente é pior que cobertura
    inexistente. Gerar no meio de uma sessão não afrouxa isso."""
    c = _chunk_real()
    antes = db.exec1("SELECT count(*) n FROM questao")["n"]
    salvas, descartes = geracao.salvar([_questao_do_modelo("999999")], [c])
    assert salvas == []
    assert len(descartes) == 1 and "999999" in descartes[0]
    assert db.exec1("SELECT count(*) n FROM questao")["n"] == antes


def test_ordinal_nao_faz_a_questao_certa_ser_descartada(usuario):
    """LC 95/1998: o banco guarda "8o"/"5º", o modelo às vezes devolve "8".
    Sem normalizar, a questão CERTA seria jogada fora por proveniência."""
    c = db.exec1(
        """SELECT c.id, c.documento_id, c.artigo, d.disciplina FROM chunk c
             JOIN documento d ON d.id = c.documento_id
            WHERE c.artigo ~ '^[0-9]+[ºo]$' LIMIT 1""")
    if not c:
        pytest.skip("acervo sem artigo com ordinal")
    sem_ordinal = c["artigo"][:-1]
    salvas, descartes = geracao.salvar([_questao_do_modelo(sem_ordinal)], [c])
    assert descartes == [] and len(salvas) == 1
    db.query("DELETE FROM questao WHERE id = %(i)s", {"i": salvas[0]["id"]})


def test_sob_demanda_enche_a_fila_de_uma_mesa_vazia(client, usuario, llm_falso):
    """O cenário que motivou o módulo: mesa cujo edital cobre uma disciplina
    que TEM material no acervo e ZERO questão. Antes disso, fila vazia pra
    sempre — o material estava lá e ninguém o transformava em pergunta."""
    _modelo_que_responde_sobre_o_lote(llm_falso)
    disc = db.exec1(
        """SELECT d.disciplina FROM documento d
            WHERE NOT EXISTS (SELECT 1 FROM questao q WHERE q.documento_id = d.id)
            LIMIT 1""")
    if not disc:
        pytest.skip("todo documento do acervo já tem questão")
    d = disc["disciplina"]

    m = client.post("/mesas", json={"nome": "Mesa vazia"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s,'e') RETURNING id",
                   {"m": m["id"]})["id"]
    db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
             "VALUES (%(e)s, %(d)s, 1, 'x')", {"e": eid, "d": d})
    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}

    antes = client.get("/fila", headers=cab).json()

    r = client.post("/questoes/gerar", json={"quantidade": 2}, headers=cab)
    assert r.status_code == 200, r.text
    geradas = r.json()["questoes"]
    assert geradas, r.json()

    # O ponto: a questão gerada entra na FILA — está no acervo, não na tela.
    depois = client.get("/fila", headers=cab).json()
    assert len(depois) > len(antes)
    assert set(q["id"] for q in geradas) <= set(q["id"] for q in depois)

    db.query("DELETE FROM questao WHERE id = ANY(%(ids)s)",
             {"ids": [q["id"] for q in geradas]})


def test_sem_material_devolve_409_e_nao_500(client, usuario):
    """"O acervo não cobre isso" é resposta válida do sistema são, não erro.
    A tela precisa distinguir de "a IA falhou": as duas pedem ação oposta
    do aluno (ingerir material × tentar de novo)."""
    m = client.post("/mesas", json={"nome": "Mesa sem acervo"},
                    headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s,'e') RETURNING id",
                   {"m": m["id"]})["id"]
    db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
             "VALUES (%(e)s, 'Matemática Financeira', 1, 'x')", {"e": eid})

    r = client.post("/questoes/gerar", json={"quantidade": 1},
                    headers={**usuario["headers"], "X-Mesa-Id": str(m["id"])})
    assert r.status_code == 409, r.text
    assert "acervo" in r.json()["detail"]


def test_material_historico_nunca_vira_fonte(usuario, llm_falso):
    """Chunk de `historico` não tem (norma, artigo) e pode conter redação
    REVOGADA — questão gerada dali cobraria lei que não vale mais."""
    tem = db.exec1("SELECT 1 x FROM documento WHERE tipo = 'historico' LIMIT 1")
    if not tem:
        pytest.skip("acervo sem material histórico")
    disc = db.exec1("SELECT disciplina FROM documento WHERE tipo = 'historico' LIMIT 1")["disciplina"]
    ids = geracao._por_disciplina([disc], 5)
    tipos = db.query(
        """SELECT DISTINCT d.tipo FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.id = ANY(%(ids)s)""", {"ids": ids})
    assert all(t["tipo"] != "historico" for t in tipos)


# ---------------------------------------------------- item CERTO/ERRADO (012)
def test_gabarito_ce_falso_nao_e_descartado_como_ausente(usuario):
    """
    O bug clássico deste formato: `if not q["gabarito_ce"]` descartaria TODO
    item cujo gabarito é ERRADO, porque False é falsy em Python — metade do
    lote, e justamente a metade que dá valor ao formato Cebraspe. A
    validação checa `isinstance(..., bool)`.
    """
    from core import socratic
    itens = [
        {"artigo": "1", "tema": "t", "enunciado": "assertiva certa",
         "gabarito_ce": True, "justificativa": "porque sim"},
        {"artigo": "2", "tema": "t", "enunciado": "assertiva errada",
         "gabarito_ce": False, "justificativa": "porque não"},
        {"artigo": "3", "tema": "t", "enunciado": "sem gabarito booleano",
         "gabarito_ce": "Certo", "justificativa": "string no lugar do bool"},
    ]
    validas = socratic._validar_ce(itens)
    assert [v["gabarito_ce"] for v in validas] == [True, False]
    assert all(v["tipo"] == "certo_errado" and v["dicas"] == [] for v in validas)
    # A justificativa vira `gabarito` — a coluna é NOT NULL nos dois tipos.
    assert validas[1]["gabarito"] == "porque não"


def test_correcao_de_item_ce_nao_chama_o_llm(usuario, llm_falso):
    """Booleano se compara com `==`. Mandar isso pro modelo custaria cota e
    introduziria erro num julgamento que não pode errar."""
    from core import socratic
    q = {"tipo": "certo_errado", "gabarito_ce": True,
         "enunciado": "assertiva", "gabarito": "justificativa"}

    assert socratic.avaliar_questao(q, "C")["veredito"] == "correta"
    assert socratic.avaliar_questao(q, "certo")["veredito"] == "correta"
    assert socratic.avaliar_questao(q, "E")["veredito"] == "incorreta"
    assert socratic.avaliar_questao(q, "")["veredito"] == "incorreta"
    # Ilegível é erro, nunca acerto por acidente de parsing.
    assert socratic.avaliar_questao(q, "talvez")["veredito"] == "incorreta"
    assert llm_falso.chamadas == []


def test_item_ce_nunca_recebe_veredito_parcial(usuario):
    """Metade de um booleano não é nada — e `parcial` DESCE uma caixa em
    scheduler_regras, então um item C/E que caísse ali seria punido por um
    estado que ele não pode ocupar."""
    from core import socratic
    q = {"tipo": "certo_errado", "gabarito_ce": False,
         "enunciado": "a", "gabarito": "b"}
    for resposta in ("C", "E", "", "meio certo", "V", "0"):
        assert socratic.avaliar_questao(q, resposta)["veredito"] in ("correta", "incorreta")


def test_banco_recusa_tipo_e_gabarito_incoerentes(usuario):
    """
    A CHECK casada da 012 é o coração da migração: "item C/E sem booleano" e
    "discursiva COM booleano" não podem existir. Deixar isso pro código
    significaria que o primeiro caminho de escrita que esquecesse a regra
    gravaria lixo calado — e são vários (gerar.py, sob_demanda, sincronizar).
    """
    import psycopg
    base = ("INSERT INTO questao (disciplina, tema, enunciado, gabarito, tipo, gabarito_ce) "
            "VALUES ('x','x','x','x', %(t)s, %(ce)s)")
    for tipo, ce in [("certo_errado", None), ("resposta_livre", True)]:
        with pytest.raises(psycopg.errors.CheckViolation):
            db.query(base, {"t": tipo, "ce": ce})
    with pytest.raises(psycopg.errors.CheckViolation):
        db.query(base, {"t": "multipla_escolha", "ce": None})


def test_tipo_da_banca(usuario):
    """A banca decide o formato, e a mesa já sabe qual é. Banca desconhecida
    cai em discursiva — o comportamento anterior à 012."""
    assert geracao.tipo_da_banca("Cebraspe") == "certo_errado"
    assert geracao.tipo_da_banca("CESPE/UnB") == "certo_errado"
    assert geracao.tipo_da_banca("FGV") == "resposta_livre"
    assert geracao.tipo_da_banca(None) == "resposta_livre"


def test_item_ce_gerado_entra_na_fila_e_corrige_sem_llm(client, usuario, llm_falso):
    """Fim a fim: gera item C/E, ele aparece na fila com o tipo, e responder
    pela rota devolve veredito binário sem tocar no modelo."""
    def gerar(prompt, sistema="", json_mode=False, max_tokens=1200, schema=None):
        arts = re.findall(r"\[[^\]]*?art\. ([^\]]+)\]", prompt)
        return json.dumps([{"artigo": a, "tema": "t", "enunciado": "assertiva",
                            "gabarito_ce": i % 2 == 0, "justificativa": "porque a lei diz"}
                           for i, a in enumerate(dict.fromkeys(arts))])
    llm_falso.gerar = gerar

    disc = db.exec1("SELECT disciplina FROM documento WHERE tipo <> 'historico' LIMIT 1")["disciplina"]
    m = client.post("/mesas", json={"nome": "Mesa CE", "banca": "Cebraspe"},
                    headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s,'e') RETURNING id",
                   {"m": m["id"]})["id"]
    db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
             "VALUES (%(e)s, %(d)s, 1, 'x')", {"e": eid, "d": disc})
    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}

    # Sem `tipo` no corpo: o servidor decide pela banca da mesa.
    r = client.post("/questoes/gerar", json={"quantidade": 2}, headers=cab)
    assert r.status_code == 200, r.text
    geradas = r.json()["questoes"]
    assert geradas and all(q["tipo"] == "certo_errado" for q in geradas)

    fila = client.get("/fila", headers=cab).json()
    na_fila = next(q for q in fila if q["id"] == geradas[0]["id"])
    assert na_fila["tipo"] == "certo_errado"
    assert isinstance(na_fila["gabarito_ce"], bool)

    certa = "C" if na_fila["gabarito_ce"] else "E"
    av = client.post(f"/questoes/{na_fila['id']}/avaliar",
                     json={"resposta": certa, "nivel": 0, "historico": []},
                     headers=usuario["headers"]).json()
    assert av["veredito"] == "correta"
    assert llm_falso.chamadas == []   # nenhuma chamada na CORREÇÃO

    db.query("DELETE FROM questao WHERE id = ANY(%(ids)s)",
             {"ids": [q["id"] for q in geradas]})


# ------------------------------------------ texto associado / série (013)
def _serie_falsa(fake, n_itens=3):
    """Duplê que devolve UMA série: texto-base + N itens sobre o artigo que
    veio no material (mesmo motivo do duplê de item avulso)."""
    def gerar(prompt, sistema="", json_mode=False, max_tokens=1200, schema=None):
        art = re.findall(r"\[[^\]]*?art\. ([^\]]+)\]", prompt)[0]
        return json.dumps({
            "artigo": art,
            "contexto": "Carlos, servidor estável, foi inabilitado no estágio probatório.",
            "itens": [{"tema": f"t{i}", "enunciado": f"assertiva {i}",
                       "gabarito_ce": i % 2 == 0, "justificativa": "porque a lei diz"}
                      for i in range(n_itens)],
        })
    fake.gerar = gerar
    return fake


def test_serie_grava_texto_base_uma_vez_e_itens_ordenados(client, usuario, llm_falso):
    """O ponto da 013: o texto-base é UM registro compartilhado, não uma
    cópia dentro de cada enunciado — é o que permite dizer "item 2 de 3" e o
    que impede as cópias divergirem quando uma for corrigida."""
    _serie_falsa(llm_falso, 3)
    disc = db.exec1("SELECT disciplina FROM documento WHERE tipo <> 'historico' LIMIT 1")["disciplina"]
    m = client.post("/mesas", json={"nome": "Mesa série", "banca": "Cebraspe"},
                    headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s,'e') RETURNING id",
                   {"m": m["id"]})["id"]
    db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
             "VALUES (%(e)s, %(d)s, 1, 'x')", {"e": eid, "d": disc})
    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}

    r = client.post("/questoes/gerar", json={"quantidade": 3}, headers=cab).json()
    geradas = r["questoes"]
    assert len(geradas) == 3
    assert r["contexto"].startswith("Carlos")

    ctx_ids = {q["contexto_id"] for q in geradas}
    assert len(ctx_ids) == 1 and None not in ctx_ids   # UM texto-base pros três
    assert [q["ordem_no_contexto"] for q in geradas] == [1, 2, 3]

    # A fila entrega o texto-base JUNTO: assertiva sem ele é ilegível.
    fila = client.get("/fila", headers=cab).json()
    na_fila = next(q for q in fila if q["id"] == geradas[0]["id"])
    assert na_fila["contexto"] == r["contexto"]

    db.query("DELETE FROM contexto WHERE id = %(i)s", {"i": ctx_ids.pop()})


def test_apagar_contexto_leva_os_itens_junto(usuario, llm_falso):
    """CASCADE deliberado: item cujo texto-base sumiu é ILEGÍVEL ("com base
    no argumento acima" sem o argumento), e apareceria na fila de alguém.
    Órfão silencioso é pior que apagar junto."""
    _serie_falsa(llm_falso, 2)
    disc = db.exec1("SELECT disciplina FROM documento WHERE tipo <> 'historico' LIMIT 1")["disciplina"]
    r = geracao.sob_demanda([disc], quantidade=2, tipo="certo_errado")
    ids = [q["id"] for q in r["questoes"]]
    ctx = r["questoes"][0]["contexto_id"]
    assert len(ids) == 2

    db.query("DELETE FROM contexto WHERE id = %(i)s", {"i": ctx})
    assert db.exec1("SELECT count(*) n FROM questao WHERE id = ANY(%(ids)s)",
                    {"ids": ids})["n"] == 0


def test_ordem_sem_contexto_e_recusada_pelo_banco(usuario):
    """A CHECK da 013: `ordem_no_contexto` sem `contexto_id` seria uma
    posição numa série que não existe."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        db.query("INSERT INTO questao (disciplina, tema, enunciado, gabarito, ordem_no_contexto) "
                 "VALUES ('x','x','x','x', 2)")


def test_um_item_so_nao_vira_serie(usuario, llm_falso):
    """Pedir UM item não justifica inventar uma situação hipotética pra ele
    sozinho — o Cebraspe cobra item avulso também, e é o formato mais barato
    de gerar."""
    _modelo_que_responde_sobre_o_lote(llm_falso)
    disc = db.exec1("SELECT disciplina FROM documento WHERE tipo <> 'historico' LIMIT 1")["disciplina"]
    chamadas_antes = len(llm_falso.chamadas)
    r = geracao.sob_demanda([disc], quantidade=1, tipo="certo_errado")
    assert "contexto" not in r
    db.query("DELETE FROM questao WHERE id = ANY(%(ids)s)",
             {"ids": [q["id"] for q in r["questoes"]]})
    del chamadas_antes
