"""Mapa de domínio (038). Edital, material e questões inventados, conta descartável."""
import json
from datetime import date

from core import db, dominio, indice, llm, mesa, scheduler

VERSAO = "test-dominio-v1"

DISC = "Disciplina Sintética Gama"
TOPICOS = ["1.1 Classes sintéticas: substantivo sintético; verbo sintético; adjetivo sintético.",
           "1.2 Organização discursiva sintética: narração e descrição sintéticas."]


def test_estado_do_assunto():
    assert dominio.estado(False, None, None) == "ns"
    assert dominio.estado(True, None, None) == "nr"
    assert dominio.estado(True, 2, 3) == "sc"
    assert dominio.estado(True, 2, 0) == "td"
    assert dominio.estado(True, 2, -5) == "od"     # caixa 2 = 7 dias: atraso de 5 ainda é "atrasado"
    assert dominio.estado(True, 2, -8) == "st"     # passou do intervalo: sem contato


def test_letra_do_historico():
    assert dominio.letra("correta", 0) == "c"
    assert dominio.letra("correta", 2) == "d"
    assert dominio.letra("parcial", 0) == "d"
    assert dominio.letra("incorreta", 1) == "e"


def test_palavras_exigem_folga_sobre_o_segundo():
    ts = [{"id": 1, "texto": TOPICOS[0]}, {"id": 2, "texto": TOPICOS[1]}]
    idf = dominio.pesos(ts)
    assert dominio.por_palavras("o verbo sintético no texto", ts, idf) == 1
    assert dominio.por_palavras("sintético", ts, idf) is None      # está nos dois
    assert dominio.por_palavras("futebol", ts, idf) is None


def _conta(client, usuario):
    uid = usuario["id"]
    m = client.post("/mesas", json={"nome": "Concurso sintético"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, 'Edital sintético') RETURNING id",
                   {"m": m["id"]})["id"]
    tids = [db.exec1("INSERT INTO topico (edital_id, disciplina, ordem, texto) VALUES (%(e)s, %(d)s, %(o)s, %(t)s) "
                     "RETURNING id", {"e": eid, "d": DISC, "o": i, "t": t})["id"] for i, t in enumerate(TOPICOS)]
    doc = db.exec1("INSERT INTO documento (titulo, tipo, disciplina, usuario_id, assunto) "
                   "VALUES ('Aula sintética', 'aula', %(d)s, %(u)s, 'Verbos sintéticos') RETURNING id",
                   {"d": DISC, "u": uid})["id"]
    cid = db.exec1("INSERT INTO chunk (documento_id, ordem, texto) VALUES (%(d)s, 0, 'O verbo sintético.') "
                   "RETURNING id", {"d": doc})["id"]
    aid = db.exec1("INSERT INTO material_assunto (documento_id, ordem, nome, papel, origem) "
                   "VALUES (%(d)s, 0, 'Modo dos verbos sintéticos', 'ensino', 'modelo') RETURNING id",
                   {"d": doc})["id"]
    db.query("INSERT INTO chunk_assunto (chunk_id, assunto_id, papel, origem) VALUES (%(c)s, %(a)s, 'ensino', 'modelo')",
             {"c": cid, "a": aid})
    qid = db.exec1("INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito, fonte_chunks, usuario_id) "
                   "VALUES (%(d)s, %(disc)s, 'Verbos', 'O que é o verbo sintético?', 'É...', %(f)s, %(u)s) RETURNING id",
                   {"d": doc, "disc": DISC, "f": [cid], "u": uid})["id"]
    return mesa.contexto(uid, m["id"]), tids, aid, qid


def test_modelo_liga_o_assunto_do_indice_e_o_mapa_mostra_o_ciclo(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 10 ** 6)      # a suíte zera; aqui o modelo decide
    ctx, tids, aid, qid = _conta(client, usuario)
    assert dominio.pendente(ctx, usuario["id"])
    # "Modo dos verbos" tem "modo", como "Organização discursiva" não tem — mas é o
    # modelo que decide: liga ao assunto das CLASSES.
    llm_falso.retorno = json.dumps({"ligacoes": [{"assunto": aid, "topico": tids[0]}]})
    assert dominio.ligar(ctx, usuario["id"]) == {"ligados": 1}
    assert not dominio.pendente(ctx, usuario["id"])

    antes = dominio.mapa(ctx, usuario["id"])
    assert (antes["totais"]["total"], antes["totais"]["tocados"], antes["totais"]["com_material"],
            antes["totais"]["material_nao_lido"]) == (2, 0, 1, 1)

    scheduler.registrar(usuario["id"], qid, "correta", "r", 1)          # acerto com dica: caixa 0
    m = dominio.mapa(ctx, usuario["id"], hoje=date.today())
    [d] = m["disciplinas"]
    a = d["assuntos"][0]
    assert (a["estado"], a["historico"], a["questoes"], a["estagio"]) == ("sc", "d", 1, 1)
    assert a["questoes_distintas"] == 1
    # Respondeu, mas o material do assunto está sem ler: encostou, não estudou.
    assert (a["nivel"], a["estudado"], a["leitura_pct"]) == ("contato", False, 0)
    assert d["assuntos"][1]["estado"] == "ns"
    assert (d["estudados"], d["em_andamento"], d["em_construcao"], d["material_nao_lido"]) == (0, 1, 1, 1)

    # Leu o trecho do assunto com o tutor: agora estudou.
    conv = db.exec1("INSERT INTO conversa (usuario_id, titulo) VALUES (%(u)s, 't') RETURNING id",
                    {"u": usuario["id"]})["id"]
    cid = db.exec1("SELECT fonte_chunks[1] AS c FROM questao WHERE id = %(q)s", {"q": qid})["c"]
    db.query("INSERT INTO mensagem (conversa_id, autor, texto, fontes) VALUES (%(c)s, 'tutor', 'x', %(f)s)",
             {"c": conv, "f": json.dumps([{"id": cid, "sequencial": True}])})
    a = dominio.mapa(ctx, usuario["id"])["disciplinas"][0]["assuntos"][0]
    assert (a["nivel"], a["estudado"], a["leitura_pct"]) == ("lido", True, 100)
    assert a["materiais"][0]["assunto"] == "Modo dos verbos sintéticos"


def test_dominar_exige_ter_estudado():
    """Questão em dia com o material sem ler é acerto de questão, não domínio (02/10/2026)."""
    assert dominio.nivel(trechos=10, lidos=2, questoes=5, contato=True) == "contato"
    assert dominio.nivel(trechos=10, lidos=7, questoes=0, contato=True) == "lido"
    assert dominio.nivel(trechos=0, lidos=0, questoes=1, contato=True) == "so_questoes"
    assert dominio.nivel(trechos=4, lidos=0, questoes=0, contato=False) == "nenhum"


def test_sem_cota_a_reserva_grava_texto_e_nao_liga_no_empate(client, usuario, llm_falso):
    ctx, tids, aid, _ = _conta(client, usuario)
    llm_falso.excecao = llm.ErroLLM("sem cota")
    dominio.ligar(ctx, usuario["id"])
    r = db.exec1("SELECT topico_id, origem FROM assunto_no_edital WHERE assunto_id = %(a)s", {"a": aid})
    assert r["origem"] == "texto"
    assert r["topico_id"] == tids[0]     # "verbos" só está no 1.1


def test_rota(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 10 ** 6)
    ctx, tids, aid, qid = _conta(client, usuario)
    # Assunto sem lugar no edital: a questão dele não chega pelo trecho e é ligada
    # pelo enunciado (039) — o dublê responde as duas chamadas.
    llm_falso.retorno = json.dumps({"ligacoes": [{"assunto": aid, "topico": 0},
                                                 {"questao": qid, "topico": tids[1]}]})
    cab = {**usuario["headers"], "X-Mesa-Id": str(ctx["id"])}
    assert client.get("/dominio", headers=cab).json()["ligando"] is True
    r = client.get("/dominio", headers=cab).json()
    assert r["ligando"] is False
    assert [len(d["assuntos"]) for d in r["disciplinas"]] == [2]
    assert db.exec1("SELECT topico_id FROM assunto_no_edital WHERE assunto_id = %(a)s", {"a": aid})["topico_id"] is None
    assert db.exec1("SELECT topico_id FROM questao_no_edital WHERE questao_id = %(q)s", {"q": qid})["topico_id"] == tids[1]
