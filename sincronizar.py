#!/usr/bin/env python3
"""
Sincroniza QUESTÕES e PROGRESSO entre máquinas, via arquivo no repositório.

    python sincronizar.py estado
    python sincronizar.py exportar     # antes de sair de uma máquina
    python sincronizar.py importar     # ao chegar na outra

O QUE VIAJA E POR QUÊ
---------------------
chunks e embeddings NÃO viajam: são deriváveis do texto da lei, e reingerir
custa segundos com o cache. Levá-los inflaria o arquivo em dezenas de MB.

Questões viajam porque gastaram cota do LLM e são únicas — gerar de novo dá
outras questões, não as mesmas.

Tentativas viajam porque são o seu progresso. É o único dado insubstituível
do sistema.

A ARMADILHA DOS IDs
-------------------
`questao.fonte_chunks` guarda IDs sequenciais de chunk, diferentes em cada
banco. Copiar a tabela crua faria a questão apontar para outro artigo, em
silêncio. Por isso a exportação traduz id -> (norma, artigo) e a importação
resolve de volta contra o banco local.

Identidade da questão entre máquinas: sha256 do enunciado. Não há id comum.
"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

from core import db

VERSAO = "sincronizar-v1"
ARQUIVO = Path("dados/progresso.json")


def chave(enunciado: str) -> str:
    return hashlib.sha256(enunciado.strip().encode("utf-8")).hexdigest()[:16]


def _serial(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(type(o))


# ------------------------------------------------------------------ exportar
def exportar() -> int:
    questoes = db.query(
        """SELECT q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.dicas,
                  q.caixa, q.prox_revisao, q.criada_em,
                  d.titulo AS doc_titulo,
                  COALESCE(array_agg(DISTINCT c.norma || '|' || c.artigo)
                           FILTER (WHERE c.artigo IS NOT NULL), '{}') AS artigos
           FROM questao q
           LEFT JOIN documento d ON d.id = q.documento_id
           LEFT JOIN chunk c ON c.id = ANY(q.fonte_chunks)
           GROUP BY q.id, d.titulo
           ORDER BY q.id"""
    )
    if not questoes:
        print("nada a exportar: banco sem questoes.", file=sys.stderr)
        return 1

    por_id = {q["id"]: chave(q["enunciado"]) for q in questoes}
    tentativas = db.query(
        """SELECT questao_id, resposta, veredito, dicas_usadas, segundos, criada_em
           FROM tentativa ORDER BY criada_em"""
    )

    pacote = {
        "versao": VERSAO,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "questoes": [
            {"chave": por_id[q["id"]], "disciplina": q["disciplina"], "tema": q["tema"],
             "enunciado": q["enunciado"], "gabarito": q["gabarito"],
             "dicas": q["dicas"], "caixa": q["caixa"],
             "prox_revisao": q["prox_revisao"], "criada_em": q["criada_em"],
             "doc_titulo": q["doc_titulo"], "artigos": list(q["artigos"] or [])}
            for q in questoes
        ],
        "tentativas": [
            {"questao": por_id[t["questao_id"]], "resposta": t["resposta"],
             "veredito": t["veredito"], "dicas_usadas": t["dicas_usadas"],
             "segundos": t["segundos"], "criada_em": t["criada_em"]}
            for t in tentativas if t["questao_id"] in por_id
        ],
    }
    ARQUIVO.parent.mkdir(exist_ok=True)
    ARQUIVO.write_text(json.dumps(pacote, ensure_ascii=False, indent=1, default=_serial),
                       encoding="utf-8")
    print(f"{len(pacote['questoes'])} questoes e {len(pacote['tentativas'])} tentativas "
          f"-> {ARQUIVO} ({ARQUIVO.stat().st_size // 1024} KB)")
    print("agora: git add dados/progresso.json && git commit && git push")
    return 0


# ------------------------------------------------------------------ importar
def _mapa_artigos():
    """(norma|artigo) -> chunk_id no banco LOCAL."""
    return {f"{r['norma']}|{r['artigo']}": r["id"] for r in db.query(
        "SELECT id, norma, artigo FROM chunk WHERE artigo IS NOT NULL")}


def importar() -> int:
    if not ARQUIVO.exists():
        print(f"{ARQUIVO} nao existe. Rode 'exportar' na outra maquina e faça git pull.",
              file=sys.stderr)
        return 1
    pacote = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    mapa = _mapa_artigos()
    docs = {r["titulo"]: r["id"] for r in db.query("SELECT id, titulo FROM documento")}
    existentes = {chave(r["enunciado"]): r["id"]
                  for r in db.query("SELECT id, enunciado FROM questao")}

    novas = atualizadas = sem_fonte = 0
    id_por_chave = dict(existentes)
    for q in pacote["questoes"]:
        chunks = [mapa[a] for a in q["artigos"] if a in mapa]
        if q["artigos"] and not chunks:
            # Ingira o material ANTES de importar, senão a questão entra sem
            # fonte rastreável e a cobertura passa a mentir.
            sem_fonte += 1
        doc_id = docs.get(q["doc_titulo"])
        if q["chave"] in existentes:
            db.query(
                """UPDATE questao SET caixa = %(c)s, prox_revisao = %(p)s,
                       fonte_chunks = %(f)s WHERE id = %(i)s""",
                {"c": q["caixa"], "p": q["prox_revisao"], "f": chunks,
                 "i": existentes[q["chave"]]},
            )
            atualizadas += 1
        else:
            r = db.exec1(
                """INSERT INTO questao (documento_id, disciplina, tema, enunciado,
                                        gabarito, dicas, fonte_chunks, caixa,
                                        prox_revisao, criada_em)
                   VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s,
                           %(c)s, %(p)s, %(cr)s) RETURNING id""",
                {"d": doc_id, "disc": q["disciplina"], "t": q["tema"],
                 "e": q["enunciado"], "g": q["gabarito"],
                 "dic": json.dumps(q["dicas"]), "f": chunks, "c": q["caixa"],
                 "p": q["prox_revisao"], "cr": q["criada_em"]},
            )
            id_por_chave[q["chave"]] = r["id"]
            novas += 1

    # Tentativas: dedupe por (questao, instante). Reimportar não duplica.
    ja = {(r["questao_id"], r["criada_em"].isoformat())
          for r in db.query("SELECT questao_id, criada_em FROM tentativa")}
    inseridas = 0
    for t in pacote["tentativas"]:
        qid = id_por_chave.get(t["questao"])
        if qid is None or (qid, t["criada_em"]) in ja:
            continue
        db.query(
            """INSERT INTO tentativa (questao_id, resposta, veredito, dicas_usadas,
                                      segundos, criada_em)
               VALUES (%(q)s, %(r)s, %(v)s, %(d)s, %(s)s, %(c)s)""",
            {"q": qid, "r": t["resposta"], "v": t["veredito"],
             "d": t["dicas_usadas"], "s": t["segundos"], "c": t["criada_em"]},
        )
        inseridas += 1

    # erro_caderno é DERIVADO das tentativas: recalcular é mais seguro que
    # transportar, porque elimina a chance de o resumo divergir da origem.
    db.query("DELETE FROM erro_caderno")
    db.query(
        """INSERT INTO erro_caderno (questao_id, disciplina, tema, vezes, ultima)
           SELECT q.id, q.disciplina, q.tema, count(*), max(t.criada_em)::date
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.veredito <> 'correta'
           GROUP BY q.id"""
    )
    print(f"questoes: {novas} novas, {atualizadas} atualizadas")
    print(f"tentativas: {inseridas} inseridas")
    if sem_fonte:
        print(f"ATENCAO: {sem_fonte} questoes sem chunk correspondente. "
              f"Ingira o material antes de importar, senao a cobertura mente.")
    return 0


def estado() -> int:
    q = db.exec1("SELECT count(*) AS n FROM questao") or {"n": 0}
    t = db.exec1("SELECT count(*) AS n FROM tentativa") or {"n": 0}
    c = db.exec1("SELECT count(*) AS n FROM chunk") or {"n": 0}
    print(f"banco local : {c['n']} chunks · {q['n']} questoes · {t['n']} tentativas")
    if ARQUIVO.exists():
        p = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        print(f"arquivo     : {len(p['questoes'])} questoes · "
              f"{len(p['tentativas'])} tentativas · gerado {p['gerado_em']}")
    else:
        print(f"arquivo     : {ARQUIVO} nao existe")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["exportar", "importar", "estado"])
    a = ap.parse_args()
    return {"exportar": exportar, "importar": importar, "estado": estado}[a.acao]()


if __name__ == "__main__":
    sys.exit(main())
