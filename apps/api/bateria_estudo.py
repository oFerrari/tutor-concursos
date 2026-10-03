#!/usr/bin/env python3
"""
BATERIA DE ESTUDO — dois meses de um aluno fictício sobre o material e o edital
de uma mesa REAL, numa conta DESCARTÁVEL. Cota zero: nenhuma chamada ao modelo.

    python bateria_estudo.py --mesa 123            # 60 dias
    python bateria_estudo.py --mesa 123 --dias 30 --semente 7
    python bateria_estudo.py --mesa 123 --gravar-na-origem   # e GRAVA o resultado na conta da mesa
    python bateria_estudo.py --mesa 123 --desfazer           # tira da conta só o que a bateria gravou

GRAVAR NA ORIGEM só a pedido do dono da conta (02/10/2026: "quero continuar a
partir deles"). Antes, o histórico real vai para `.logs/backup-estudo-<conta>-…json`.
Vão as tentativas (marcadas `resposta='bateria-estudo'`) e uma conversa com as
leituras; caixa, próxima revisão e caderno são RECALCULADOS juntando as
tentativas reais e as simuladas em ordem de data. `--desfazer` apaga as marcadas
e recalcula de novo.

1. COPIA a mesa (edital, materiais com trechos e índice, questões, a ligação
   índice -> edital do 038) para `bateria-…@local`, SEM histórico de estudo. A
   conta de origem não é tocada: dois meses inventados no histórico real
   misturariam fila, caderno e mapa com o que nunca aconteceu.
2. SIMULA cada dia pelas rotas da API: lê material com o tutor (mensagem com
   fontes em sequência, como a leitura grava), responde a fila do dia
   (`GET /fila`; múltipla escolha corrigida por `/avaliar`, que é código; tudo
   gravado por `/registrar`). O aluno tem domínio LATENTE por assunto, aprende
   lendo e respondendo, esquece sem contato, folga e para uma semana.
3. Ao fim de cada dia ENVELHECE em um dia todas as datas da conta — o código
   continua usando o hoje de verdade, e o tempo passa para os dados.
4. CONFERE, toda semana e no fim, as telas contra o que o simulador sabe que
   aconteceu: caixa de cada questão (refeita pelas regras puras), mapa de
   domínio (refeito do banco por outro caminho), meta, fila, caderno, desempenho.

Saída: `.logs/estudo.md`. A conta descartável é apagada no fim.
"""
import argparse
import json
import random
import sys
import uuid
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import api
from core import auth, db, dominio, scheduler_regras as R

VERSAO = "bateria-estudo-v2"
SAIDA = Path(__file__).resolve().parents[2] / ".logs" / "estudo.md"
PARADA = range(29, 35)            # uma semana sem estudar no meio
MARCA = "bateria-estudo"          # tentativa.resposta e título da conversa gravadas na origem
TITULO_CONVERSA = "Leituras simuladas (bateria de estudo)"


# ------------------------------------------------------------------ cópia
def copiar_mesa(mesa_origem: int, uid: int) -> dict:
    """A mesa, o edital, o material (trechos, índice) e as questões, para `uid`."""
    dono = db.exec1("SELECT usuario_id FROM mesa WHERE id = %(m)s", {"m": mesa_origem})["usuario_id"]
    mid = db.exec1("""INSERT INTO mesa (usuario_id, nome, orgao, banca, disciplinas_manuais, biblioteca_compartilhada)
                      SELECT %(u)s, nome, orgao, banca, disciplinas_manuais, biblioteca_compartilhada
                        FROM mesa WHERE id = %(m)s RETURNING id""", {"u": uid, "m": mesa_origem})["id"]
    ed_velho = db.exec1("SELECT id FROM edital WHERE mesa_id = %(m)s ORDER BY criado_em DESC LIMIT 1",
                        {"m": mesa_origem})["id"]
    ed = db.exec1("""INSERT INTO edital (titulo, orgao, banca, data_prova, arquivo, mesa_id, cargo)
                     SELECT titulo, orgao, banca, data_prova, arquivo, %(m)s, cargo FROM edital WHERE id = %(e)s
                     RETURNING id""", {"m": mid, "e": ed_velho})["id"]
    topico = {}
    for t in db.query("SELECT id, disciplina, ordem, texto FROM topico WHERE edital_id = %(e)s", {"e": ed_velho}):
        topico[t["id"]] = db.exec1("""INSERT INTO topico (edital_id, disciplina, ordem, texto)
                                      VALUES (%(e)s, %(d)s, %(o)s, %(t)s) RETURNING id""",
                                   {"e": ed, "d": t["disciplina"], "o": t["ordem"], "t": t["texto"]})["id"]
    doc = {}
    for d in db.query("SELECT id, mesa_id FROM documento WHERE usuario_id = %(u)s ORDER BY id", {"u": dono}):
        doc[d["id"]] = db.exec1(
            """INSERT INTO documento (titulo, disciplina, tipo, origem, hash, usuario_id, status, chunks_total,
                                      erro, assunto, classificado_por, mesa_id, arquivo_tipo, arquivo_bytes, url,
                                      assuntos_status, assuntos_em, questoes_extraidas, questoes_sem_gabarito)
               SELECT titulo, disciplina, tipo, origem, hash, %(u)s, status, chunks_total, erro, assunto,
                      classificado_por, %(m)s, arquivo_tipo, arquivo_bytes, url, assuntos_status, assuntos_em,
                      questoes_extraidas, questoes_sem_gabarito
                 FROM documento WHERE id = %(d)s RETURNING id""",
            {"u": uid, "m": mid if d["mesa_id"] == mesa_origem else None, "d": d["id"]})["id"]
    for velho, novo in doc.items():
        db.query("""UPDATE documento n SET gabarito_de = %(g)s FROM documento v
                     WHERE v.id = %(v)s AND n.id = %(n)s AND v.gabarito_de IS NOT NULL""",
                 {"v": velho, "n": novo, "g": None})
        g = db.exec1("SELECT gabarito_de FROM documento WHERE id = %(v)s", {"v": velho})["gabarito_de"]
        if g in doc:
            db.query("UPDATE documento SET gabarito_de = %(g)s WHERE id = %(n)s", {"g": doc[g], "n": novo})
        db.query("""INSERT INTO chunk (documento_id, ordem, texto, norma, artigo, paragrafo, inciso, pagina,
                                       embedding, rubrica, secao, rotulo)
                    SELECT %(n)s, ordem, texto, norma, artigo, paragrafo, inciso, pagina, embedding, rubrica,
                           secao, rotulo FROM chunk WHERE documento_id = %(v)s""", {"n": novo, "v": velho})
        db.query("""INSERT INTO material_assunto (documento_id, ordem, nome, pagina_inicio, pagina_fim, papel, origem)
                    SELECT %(n)s, ordem, nome, pagina_inicio, pagina_fim, papel, origem
                      FROM material_assunto WHERE documento_id = %(v)s""", {"n": novo, "v": velho})
    chunk = {r["v"]: r["n"] for r in db.query(
        """SELECT cv.id AS v, cn.id AS n FROM chunk cv
             JOIN chunk cn ON cn.ordem = cv.ordem
             JOIN unnest(%(vs)s::bigint[], %(ns)s::bigint[]) AS m(v, n) ON m.v = cv.documento_id AND m.n = cn.documento_id""",
        {"vs": list(doc), "ns": list(doc.values())})}
    assunto = {r["v"]: r["n"] for r in db.query(
        """SELECT av.id AS v, an.id AS n FROM material_assunto av
             JOIN material_assunto an ON an.ordem = av.ordem
             JOIN unnest(%(vs)s::bigint[], %(ns)s::bigint[]) AS m(v, n) ON m.v = av.documento_id AND m.n = an.documento_id""",
        {"vs": list(doc), "ns": list(doc.values())})}
    for r in db.query("SELECT chunk_id, assunto_id, papel, origem FROM chunk_assunto WHERE chunk_id = ANY(%(c)s)",
                      {"c": list(chunk)}):
        if r["assunto_id"] in assunto:
            db.query("INSERT INTO chunk_assunto VALUES (%(c)s, %(a)s, %(p)s, %(o)s) ON CONFLICT DO NOTHING",
                     {"c": chunk[r["chunk_id"]], "a": assunto[r["assunto_id"]], "p": r["papel"], "o": r["origem"]})
    for r in db.query("SELECT assunto_id, topico_id, origem FROM assunto_no_edital WHERE edital_id = %(e)s",
                      {"e": ed_velho}):
        if r["assunto_id"] in assunto:
            db.query("""INSERT INTO assunto_no_edital (assunto_id, edital_id, topico_id, origem)
                        VALUES (%(a)s, %(e)s, %(t)s, %(o)s)""",
                     {"a": assunto[r["assunto_id"]], "e": ed, "t": topico.get(r["topico_id"]), "o": r["origem"]})
    questao = {}
    for q in db.query("SELECT * FROM questao WHERE usuario_id = %(u)s AND contexto_id IS NULL", {"u": dono}):
        novo = db.exec1(
            """INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito, dicas, fonte_chunks, tipo,
                                    gabarito_ce, usuario_id, origem, numero_na_prova, gabarito_letra, gabarito_fonte)
               VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s, %(tipo)s, %(ce)s, %(u)s, %(o)s,
                       %(n)s, %(l)s, %(gf)s) RETURNING id""",
            {"d": doc.get(q["documento_id"]), "disc": q["disciplina"], "t": q["tema"], "e": q["enunciado"],
             "g": q["gabarito"], "dic": json.dumps(q["dicas"]), "tipo": q["tipo"], "ce": q["gabarito_ce"],
             "f": [chunk[c] for c in (q["fonte_chunks"] or []) if c in chunk], "u": uid, "o": q["origem"],
             "n": q["numero_na_prova"], "l": q["gabarito_letra"], "gf": q["gabarito_fonte"]})["id"]
        questao[q["id"]] = novo
        db.query("""INSERT INTO questao_no_edital (questao_id, edital_id, topico_id, origem)
                    SELECT %(n)s, %(e)s, %(t)s, origem FROM questao_no_edital
                     WHERE questao_id = %(v)s AND edital_id = %(ev)s""",
                 {"n": novo, "e": ed, "v": q["id"], "ev": ed_velho,
                  "t": topico.get((db.exec1("SELECT topico_id FROM questao_no_edital WHERE questao_id = %(v)s "
                                            "AND edital_id = %(ev)s", {"v": q["id"], "ev": ed_velho})
                                   or {}).get("topico_id"))})
        db.query("""INSERT INTO questao_alternativa (questao_id, letra, texto)
                    SELECT %(n)s, letra, texto FROM questao_alternativa WHERE questao_id = %(v)s""",
                 {"n": novo, "v": q["id"]})
    return {"mesa": mid, "edital": ed, "documentos": len(doc), "trechos": len(chunk),
            "assuntos": len(assunto), "questoes": len(questao), "topicos": len(topico),
            "_questao": questao, "_chunk": chunk, "_dono": dono}


# ------------------------------------------------------------------ origem
def recalcular(uid: int) -> None:
    """Caixa, próxima revisão e caderno de `uid`, refeitos das tentativas em ordem."""
    hist = defaultdict(list)
    for t in db.query("""SELECT questao_id, veredito, dicas_usadas, criada_em FROM tentativa
                          WHERE usuario_id = %(u)s ORDER BY criada_em, id""", {"u": uid}):
        hist[t["questao_id"]].append(t)
    db.query("DELETE FROM progresso WHERE usuario_id = %(u)s AND NOT (questao_id = ANY(%(q)s))",
             {"u": uid, "q": list(hist)})
    for qid, ts in hist.items():
        caixa = 0
        for t in ts:
            caixa = R.proxima_caixa(caixa, t["veredito"], t["dicas_usadas"])
        prox = ts[-1]["criada_em"].date() + timedelta(days=R.dias_ate_revisao(caixa))
        db.query("""INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao) VALUES (%(u)s, %(q)s, %(c)s, %(p)s)
                    ON CONFLICT (usuario_id, questao_id) DO UPDATE SET caixa = EXCLUDED.caixa,
                                                                      prox_revisao = EXCLUDED.prox_revisao""",
                 {"u": uid, "q": qid, "c": caixa, "p": prox})
    # mesmo cálculo de `sincronizar.py`: o caderno é derivado das tentativas
    db.query("DELETE FROM erro_caderno WHERE usuario_id = %(u)s", {"u": uid})
    db.query("""INSERT INTO erro_caderno (usuario_id, questao_id, disciplina, tema, vezes, ultima)
                SELECT %(u)s, q.id, q.disciplina, q.tema, count(*), max(t.criada_em)::date
                  FROM tentativa t JOIN questao q ON q.id = t.questao_id
                 WHERE t.usuario_id = %(u)s AND t.veredito <> 'correta' GROUP BY q.id""", {"u": uid})


def backup(uid: int) -> Path:
    def linhas(sql):
        return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
                for r in db.query(sql, {"u": uid})]
    dados = {"tentativa": linhas("SELECT * FROM tentativa WHERE usuario_id = %(u)s"),
             "progresso": linhas("SELECT * FROM progresso WHERE usuario_id = %(u)s"),
             "erro_caderno": linhas("SELECT * FROM erro_caderno WHERE usuario_id = %(u)s")}
    alvo = SAIDA.parent / f"backup-estudo-{uid}-{date.today():%Y%m%d}-{uuid.uuid4().hex[:6]}.json"
    alvo.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return alvo


def desfazer(uid: int) -> dict:
    n = db.exec1("SELECT count(*) AS n FROM tentativa WHERE usuario_id = %(u)s AND resposta = %(m)s",
                 {"u": uid, "m": MARCA})["n"]
    db.query("DELETE FROM tentativa WHERE usuario_id = %(u)s AND resposta = %(m)s", {"u": uid, "m": MARCA})
    db.query("DELETE FROM conversa WHERE usuario_id = %(u)s AND titulo = %(t)s", {"u": uid, "t": TITULO_CONVERSA})
    recalcular(uid)
    return {"tentativas_apagadas": n}


def gravar_na_origem(clone: int, copia: dict, mesa_origem: int) -> dict:
    """As tentativas e as leituras do aluno simulado, na conta dona da mesa."""
    dono = copia["_dono"]
    de_volta_q = {novo: velho for velho, novo in copia["_questao"].items()}
    de_volta_c = {novo: velho for velho, novo in copia["_chunk"].items()}
    n = 0
    for t in db.query("""SELECT questao_id, veredito, dicas_usadas, segundos, criada_em FROM tentativa
                          WHERE usuario_id = %(u)s ORDER BY criada_em, id""", {"u": clone}):
        if t["questao_id"] in de_volta_q:
            db.query("""INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, dicas_usadas, segundos, criada_em)
                        VALUES (%(u)s, %(q)s, %(m)s, %(v)s, %(d)s, %(s)s, %(c)s)""",
                     {"u": dono, "q": de_volta_q[t["questao_id"]], "m": MARCA, "v": t["veredito"],
                      "d": t["dicas_usadas"], "s": t["segundos"], "c": t["criada_em"]})
            n += 1
    msgs = db.query("""SELECT m.texto, m.fontes, m.criada_em FROM mensagem m JOIN conversa c ON c.id = m.conversa_id
                        WHERE c.usuario_id = %(u)s ORDER BY m.id""", {"u": clone})
    if msgs:
        cid = db.exec1("""INSERT INTO conversa (usuario_id, mesa_id, titulo, criada_em, atualizada_em)
                          VALUES (%(u)s, %(m)s, %(t)s, %(c)s, %(a)s) RETURNING id""",
                       {"u": dono, "m": mesa_origem, "t": TITULO_CONVERSA,
                        "c": msgs[0]["criada_em"], "a": msgs[-1]["criada_em"]})["id"]
        for m in msgs:
            fontes = [{**f, "id": de_volta_c.get(f["id"], f["id"])} for f in m["fontes"] or []]
            db.query("""INSERT INTO mensagem (conversa_id, autor, texto, fontes, criada_em)
                        VALUES (%(c)s, 'tutor', 'Leitura simulada pela bateria de estudo.', %(f)s, %(cr)s)""",
                     {"c": cid, "f": json.dumps(fontes), "cr": m["criada_em"]})
    recalcular(dono)
    return {"tentativas": n, "leituras": len(msgs)}


# ------------------------------------------------------------------ tempo
def envelhecer(uid: int, dias: int = 1) -> None:
    """Todas as datas da conta, `dias` para trás: o tempo passa para os dados."""
    p = {"u": uid, "d": dias}
    db.query("UPDATE progresso SET prox_revisao = prox_revisao - %(d)s WHERE usuario_id = %(u)s", p)
    db.query("UPDATE tentativa SET criada_em = criada_em - make_interval(days => %(d)s) WHERE usuario_id = %(u)s", p)
    db.query("UPDATE erro_caderno SET ultima = ultima - make_interval(days => %(d)s) WHERE usuario_id = %(u)s", p)
    db.query("""UPDATE mensagem SET criada_em = criada_em - make_interval(days => %(d)s)
                 WHERE conversa_id IN (SELECT id FROM conversa WHERE usuario_id = %(u)s)""", p)
    db.query("""UPDATE conversa SET criada_em = criada_em - make_interval(days => %(d)s),
                                    atualizada_em = atualizada_em - make_interval(days => %(d)s)
                 WHERE usuario_id = %(u)s""", p)


# ------------------------------------------------------------------ aluno
class Aluno:
    """Domínio latente por assunto (0–1). Aprende lendo e respondendo; esquece."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.dominio: dict = defaultdict(lambda: 0.25 + 0.2 * rng.random())
        self.contato: dict = {}

    def ler(self, chave, dia: int):
        self.dominio[chave] = min(0.95, self.dominio[chave] + 0.07)
        self.contato[chave] = dia

    def responder(self, chave, caixa: int, dia: int, livre: bool) -> tuple[str, int]:
        sem = dia - self.contato.get(chave, dia)
        esquecido = max(0.0, (sem - R.dias_ate_revisao(caixa)) * 0.01)
        p = min(0.97, max(0.05, self.dominio[chave] + 0.06 * caixa - esquecido))
        self.contato[chave] = dia
        acertou = self.rng.random() < p
        self.dominio[chave] = min(0.95, self.dominio[chave] + (0.05 if acertou else 0.03))
        if acertou:
            return "correta", 0
        if livre:      # discursiva: a escada socrática dá dica
            sorte = self.rng.random()
            if sorte < 0.55:
                return "correta", 1 + int(self.rng.random() < 0.3)
            return ("parcial", 1) if sorte < 0.8 else ("incorreta", 2)
        return "incorreta", 0


# ------------------------------------------------------------------ conferência
def conferir(cli, cab, uid: int, mid: int, hoje: date) -> tuple[list[str], dict]:
    falhas: list[str] = []
    # 1. caixa e próxima revisão de cada questão, refeitas pelas regras puras
    hist = defaultdict(list)
    for t in db.query("""SELECT questao_id, veredito, dicas_usadas, criada_em FROM tentativa
                          WHERE usuario_id = %(u)s ORDER BY criada_em, id""", {"u": uid}):
        hist[t["questao_id"]].append(t)
    prog = {r["questao_id"]: r for r in db.query("SELECT * FROM progresso WHERE usuario_id = %(u)s", {"u": uid})}
    for qid, ts in hist.items():
        caixa = 0
        for t in ts:
            caixa = R.proxima_caixa(caixa, t["veredito"], t["dicas_usadas"])
        esperado = ts[-1]["criada_em"].date() + timedelta(days=R.dias_ate_revisao(caixa))
        p = prog.get(qid)
        if not p or p["caixa"] != caixa:
            falhas.append(f"questão {qid}: caixa {p and p['caixa']} no banco, {caixa} pelas regras")
        elif abs((p["prox_revisao"] - esperado).days) > 1:
            falhas.append(f"questão {qid}: revisão {p['prox_revisao']} no banco, {esperado} pelas regras")

    # 2. telas
    rotas = {}
    for rota in ("/dominio", "/meta", "/fila", "/carga", "/erros", "/stats", "/desafio", "/edital", "/conceitos"):
        r = cli.get(rota, headers=cab)
        if r.status_code != 200:
            falhas.append(f"GET {rota} -> HTTP {r.status_code}: {r.text[:120]}")
        else:
            rotas[rota] = r.json()
    mapa, meta, fila = rotas.get("/dominio"), rotas.get("/meta"), rotas.get("/fila")
    if not mapa:
        return falhas, {}

    # 3. mapa refeito do banco por outro caminho
    assuntos = {a["id"]: a for d in mapa["disciplinas"] for a in d["assuntos"]}
    ed = db.exec1("SELECT id FROM edital WHERE mesa_id = %(m)s ORDER BY criado_em DESC LIMIT 1", {"m": mid})["id"]
    por_trecho = {r["chunk_id"]: r["topico_id"] for r in db.query(
        """SELECT DISTINCT ON (ca.chunk_id) ca.chunk_id, ae.topico_id
             FROM chunk_assunto ca JOIN assunto_no_edital ae ON ae.assunto_id = ca.assunto_id
            WHERE ae.edital_id = %(e)s AND ae.topico_id IS NOT NULL
            ORDER BY ca.chunk_id, (ca.papel = 'ensino') DESC""", {"e": ed})}
    pelo_enunciado = {r["questao_id"]: r["topico_id"] for r in db.query(
        "SELECT questao_id, topico_id FROM questao_no_edital WHERE edital_id = %(e)s", {"e": ed})}
    caixas, revisoes, tocados = defaultdict(list), defaultdict(list), set()
    ligadas = 0
    for qid, ts in hist.items():
        q = db.exec1("SELECT fonte_chunks, origem FROM questao WHERE id = %(q)s", {"q": qid})
        tid = next((por_trecho[c] for c in q["fonte_chunks"] or [] if c in por_trecho), None) \
            or pelo_enunciado.get(qid)
        ligadas += bool(tid)
        if tid:
            caixas[tid].append(prog[qid]["caixa"])
            revisoes[tid].append(prog[qid]["prox_revisao"])
            tocados.add(tid)
    for r in db.query("""SELECT DISTINCT (f->>'id')::bigint AS c FROM conversa cv JOIN mensagem m ON m.conversa_id = cv.id,
                                jsonb_array_elements(m.fontes) f WHERE cv.usuario_id = %(u)s""", {"u": uid}):
        if r["c"] in por_trecho:
            tocados.add(por_trecho[r["c"]])
    for tid, a in assuntos.items():
        if tid in caixas:
            dom = min(caixas[tid]) >= dominio.CAIXA_DOMINIO
            if a["dominado"] != dom:
                falhas.append(f"assunto {tid}: mapa diz dominado={a['dominado']}, banco diz {dom}")
            faltam = (min(revisoes[tid]) - hoje).days
            if a["proxima_em"] is not None and a["proxima_em"] != faltam:
                falhas.append(f"assunto {tid}: próxima em {a['proxima_em']} no mapa, {faltam} no banco")
        if (tid in tocados) != (a["estado"] != "ns"):
            falhas.append(f"assunto {tid}: estado {a['estado']} mas tocado={tid in tocados}")

    # 4. coerência entre telas
    total_q = db.exec1("""SELECT count(*) AS n FROM questao WHERE usuario_id = %(u)s""", {"u": uid})["n"]
    dominadas = sum(1 for p in prog.values() if p["caixa"] >= 3)
    if meta and total_q and abs(meta["cobertura_pct"] - round(100 * dominadas / total_q, 1)) > 0.2:
        falhas.append(f"/meta dominado {meta['cobertura_pct']}% ≠ {dominadas}/{total_q} questões na caixa ≥ 3")
    vencidas = sum(1 for p in prog.values() if p["prox_revisao"] <= hoje)
    revisoes_na_fila = sum(1 for q in fila or [] if q["id"] in prog)
    if fila is not None and revisoes_na_fila != min(vencidas, 40):
        falhas.append(f"/fila tem {revisoes_na_fila} revisões, {vencidas} vencidas no banco")
    for a in assuntos.values():
        if a["estado"] in ("td", "od", "st") and not any(
                q["id"] in prog and prog[q["id"]]["prox_revisao"] <= hoje for q in fila or []):
            falhas.append(f"assunto {a['id']} pede revisão ({a['estado']}) e a fila não tem revisão vencida")
            break
    for e in rotas.get("/erros") or []:
        if not any(t["veredito"] != "correta" for t in hist.get(e.get("id") or e.get("questao_id"), [])):
            falhas.append(f"caderno tem a questão {e.get('id') or e.get('questao_id')} sem erro registrado")
            break

    t = mapa["totais"]
    foto = {"estudados": t["estudados"], "total": t["total"], "dominados": t["dominados"], "hoje": t["hoje"],
            "atrasados": sum(a["estado"] == "od" for a in assuntos.values()),
            "sem_contato": sum(a["estado"] == "st" for a in assuntos.values()),
            "sem_revisao": sum(a["estado"] == "nr" for a in assuntos.values()),
            "dominado_pct": meta and meta["cobertura_pct"], "construcao_pct": meta and meta.get("em_construcao_pct"),
            "fila": len(fila or []), "erros": len(rotas.get("/erros") or []),
            "respondidas": len(hist), "ligadas": ligadas,
            "sem_assunto": sum(d["questoes_sem_assunto"] for d in mapa["disciplinas"])}
    return falhas, foto


# ------------------------------------------------------------------ dias
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesa", type=int, required=True)
    ap.add_argument("--dias", type=int, default=60)
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--gravar-na-origem", action="store_true")
    ap.add_argument("--desfazer", action="store_true")
    a = ap.parse_args()
    if a.desfazer:
        dono = db.exec1("SELECT usuario_id FROM mesa WHERE id = %(m)s", {"m": a.mesa})["usuario_id"]
        print(f"backup: {backup(dono)}")
        print(desfazer(dono))
        return 0
    rng = random.Random(a.semente)
    gasto0 = db.exec1("SELECT count(*) AS n FROM telemetria_llm")["n"]
    uid = auth.usuario_da_cli(f"bateria-{uuid.uuid4().hex[:12]}@local")
    linhas = [f"# Bateria de estudo ({VERSAO}) — {a.dias} dias, semente {a.semente}", ""]
    todas_falhas: list[tuple[int, str]] = []
    try:
        copia = copiar_mesa(a.mesa, uid)
        resumo = {k: v for k, v in copia.items() if not k.startswith("_")}
        print(f"cópia: {resumo}", flush=True)
        linhas += [f"Cópia: {resumo}", ""]
        mid = copia["mesa"]
        cli = TestClient(api.app)
        cab = {"Authorization": f"Bearer {auth.emitir_token(uid)}", "X-Mesa-Id": str(mid)}
        conv = db.exec1("INSERT INTO conversa (usuario_id, mesa_id, titulo) VALUES (%(u)s, %(m)s, 'bateria') "
                        "RETURNING id", {"u": uid, "m": mid})["id"]
        # leitura: material de ensino em ordem, uma disciplina por vez, trocando a cada semana
        docs = db.query("""SELECT id, disciplina FROM documento WHERE usuario_id = %(u)s AND tipo IN ('aula', 'resumo')
                            ORDER BY disciplina, id""", {"u": uid})
        marcador = {d["id"]: -1 for d in docs}
        ed = copia["edital"]
        topico_do_trecho = {r["chunk_id"]: r["topico_id"] for r in db.query(
            """SELECT DISTINCT ON (ca.chunk_id) ca.chunk_id, ae.topico_id FROM chunk_assunto ca
                 JOIN assunto_no_edital ae ON ae.assunto_id = ca.assunto_id
                WHERE ae.edital_id = %(e)s AND ae.topico_id IS NOT NULL ORDER BY ca.chunk_id""", {"e": ed})}
        topico_da_questao = {r["questao_id"]: r["topico_id"] for r in db.query(
            "SELECT questao_id, topico_id FROM questao_no_edital WHERE edital_id = %(e)s AND topico_id IS NOT NULL",
            {"e": ed})}
        aluno = Aluno(rng)
        fotos = []
        for dia in range(1, a.dias + 1):
            estuda = dia not in PARADA and not (dia % 7 == 0 and rng.random() < 0.5)
            lidos = respondidas = 0
            if estuda and docs:
                d = docs[(dia // 7) % len(docs)]
                trechos = db.query("""SELECT id FROM chunk WHERE documento_id = %(d)s AND ordem > %(o)s
                                      ORDER BY ordem LIMIT %(n)s""",
                                   {"d": d["id"], "o": marcador[d["id"]], "n": rng.randint(3, 6)})
                if trechos:
                    ids = [t["id"] for t in trechos]
                    marcador[d["id"]] = db.exec1("SELECT ordem FROM chunk WHERE id = %(i)s", {"i": ids[-1]})["ordem"]
                    db.query("""INSERT INTO mensagem (conversa_id, autor, texto, fontes)
                                VALUES (%(c)s, 'tutor', 'leitura da bateria', %(f)s)""",
                             {"c": conv, "f": json.dumps([{"id": i, "documento_id": d["id"], "sequencial": True}
                                                          for i in ids])})
                    for i in ids:
                        aluno.ler(topico_do_trecho.get(i) or ("disc", d["disciplina"]), dia)
                    lidos = len(ids)
                fila = cli.get("/fila", headers=cab).json()
                for q in fila[:rng.randint(8, 25)]:
                    qd = db.exec1("SELECT fonte_chunks, disciplina, tipo, gabarito_letra FROM questao WHERE id = %(q)s",
                                  {"q": q["id"]})
                    chave = next((topico_do_trecho[c] for c in qd["fonte_chunks"] or [] if c in topico_do_trecho),
                                 None) or topico_da_questao.get(q["id"]) or ("disc", qd["disciplina"])
                    caixa = (db.exec1("SELECT caixa FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
                                      {"u": uid, "q": q["id"]}) or {"caixa": 0})["caixa"]
                    veredito, dicas = aluno.responder(chave, caixa, dia, qd["tipo"] == "resposta_livre")
                    if qd["tipo"] == "multipla_escolha":
                        letra = qd["gabarito_letra"] if veredito == "correta" else \
                            rng.choice([x for x in "ABCDE" if x != qd["gabarito_letra"]])
                        corr = cli.post(f"/questoes/{q['id']}/avaliar", headers=cab, json={"resposta": letra}).json()
                        if corr.get("veredito") != veredito:
                            todas_falhas.append((dia, f"/avaliar deu {corr.get('veredito')} para a letra {letra} "
                                                      f"(gabarito {qd['gabarito_letra']})"))
                    r = cli.post(f"/questoes/{q['id']}/registrar", headers=cab,
                                 json={"veredito": veredito, "resposta": "bateria", "dicas_usadas": dicas})
                    if r.status_code != 200:
                        todas_falhas.append((dia, f"/registrar HTTP {r.status_code}: {r.text[:100]}"))
                    respondidas += 1
            if dia % 7 == 0 or dia == a.dias:
                falhas, foto = conferir(cli, cab, uid, mid, date.today())
                todas_falhas += [(dia, f) for f in falhas]
                fotos.append((dia, foto))
                print(f"dia {dia:>2}: {foto} · {len(falhas)} falha(s)", flush=True)
            envelhecer(uid)
            if dia % 10 == 0:
                print(f"  ...dia {dia} (leu {lidos}, respondeu {respondidas})", flush=True)

        # domínio latente x mapa: o mapa deve acompanhar o que o aluno sabe
        mapa = cli.get("/dominio", headers=cab).json()
        grupos = defaultdict(list)
        for d in mapa["disciplinas"]:
            for x in d["assuntos"]:
                if x["id"] in aluno.dominio:
                    grupos["dominado" if x["dominado"] else x["estado"]].append(aluno.dominio[x["id"]])
        linhas += ["## Evolução semanal", "",
                   "| dia | estudados | dominados | hoje | atrasados | sem contato | sem revisão | dominado% | "
                   "construção% | fila | caderno | respondidas | ligadas a assunto | sem assunto |",
                   "|" + "---|" * 14]
        for dia, f in fotos:
            if f:
                linhas.append(f"| {dia} | {f['estudados']}/{f['total']} | {f['dominados']} | {f['hoje']} | "
                              f"{f['atrasados']} | {f['sem_contato']} | {f['sem_revisao']} | {f['dominado_pct']} | "
                              f"{f['construcao_pct']} | {f['fila']} | {f['erros']} | {f['respondidas']} | "
                              f"{f['ligadas']} | {f['sem_assunto']} |")
        linhas += ["", "## Domínio latente do aluno por estado no mapa (média)", ""]
        for k, v in sorted(grupos.items()):
            linhas.append(f"- {k}: {sum(v) / len(v):.2f} ({len(v)} assuntos)")
        if a.gravar_na_origem:
            print(f"backup da conta de origem: {backup(copia['_dono'])}", flush=True)
            gravado = gravar_na_origem(uid, copia, a.mesa)
            print(f"gravado na origem: {gravado}", flush=True)
            linhas += ["", f"**Gravado na conta de origem:** {gravado} (desfazer: `--desfazer`)"]
        linhas += ["", f"## Falhas ({len(todas_falhas)})", ""]
        vistas = set()
        for dia, f in todas_falhas:
            chave = f.split(":")[0]
            if chave not in vistas:
                vistas.add(chave)
                linhas.append(f"- dia {dia}: {f}")
    finally:
        db.query("DELETE FROM questao WHERE usuario_id = %(u)s", {"u": uid})
        db.query("DELETE FROM usuario WHERE id = %(u)s", {"u": uid})
    gasto = db.exec1("SELECT count(*) AS n FROM telemetria_llm")["n"] - gasto0
    linhas.insert(1, f"_chamadas ao modelo: {gasto}_")
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    print(f"falhas: {len(todas_falhas)} · chamadas ao modelo: {gasto} → {SAIDA}")
    return 1 if todas_falhas else 0


if __name__ == "__main__":
    sys.exit(main())
