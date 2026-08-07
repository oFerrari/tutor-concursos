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
outras questões, não as mesmas. O banco de questões é COMPARTILHADO (sem
usuario_id) — sincronizar não duplica isso por pessoa.

Progresso e tentativas viajam porque são o SEU progresso — pessoal, por
isso amarrado ao `usuario_email` do pacote. É o único dado insubstituível
do sistema.

A ARMADILHA DOS IDs
-------------------
`questao.fonte_chunks` guarda IDs sequenciais de chunk, diferentes em cada
banco. Copiar a tabela crua faria a questão apontar para outro artigo, em
silêncio. Por isso a exportação traduz id -> (norma, artigo) e a importação
resolve de volta contra o banco local.

Identidade da questão entre máquinas: sha256 do enunciado. Não há id comum.

MULTIUSUÁRIO: um pacote é de UM usuário (`CLI_USUARIO_EMAIL` no .env de quem
exportou). A importação resolve (ou cria, mesmo caminho de `auth.usuario_da_cli`)
o usuário local pelo email — sincronizar entre duas máquinas SUAS funciona
porque as duas apontam pro mesmo email; sincronizar com o progresso de OUTRA
pessoa exigiria ela rodar `exportar` com o próprio email e você importar o
arquivo dela, o que também funciona (cria uma conta local pro email dela),
mas não é o caso de uso que este script foi pensado para resolver.
"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

from core import auth, db
from core.config import CLI_USUARIO_EMAIL

VERSAO = "sincronizar-v2"
ARQUIVO = Path("dados/progresso.json")


def chave(enunciado: str) -> str:
    return hashlib.sha256(enunciado.strip().encode("utf-8")).hexdigest()[:16]


def _serial(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(type(o))


# ------------------------------------------------------------------ exportar
def exportar() -> int:
    usuario_id = auth.usuario_da_cli(CLI_USUARIO_EMAIL)

    questoes = db.query(
        """SELECT q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.dicas, q.criada_em,
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
    progresso = db.query(
        "SELECT questao_id, caixa, prox_revisao FROM progresso WHERE usuario_id = %(u)s",
        {"u": usuario_id},
    )
    tentativas = db.query(
        """SELECT questao_id, resposta, veredito, dicas_usadas, segundos, criada_em
           FROM tentativa WHERE usuario_id = %(u)s ORDER BY criada_em""",
        {"u": usuario_id},
    )

    pacote = {
        "versao": VERSAO,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "usuario_email": CLI_USUARIO_EMAIL,
        "questoes": [
            {"chave": por_id[q["id"]], "disciplina": q["disciplina"], "tema": q["tema"],
             "enunciado": q["enunciado"], "gabarito": q["gabarito"],
             "dicas": q["dicas"], "criada_em": q["criada_em"],
             "doc_titulo": q["doc_titulo"], "artigos": list(q["artigos"] or [])}
            for q in questoes
        ],
        "progresso": [
            {"questao": por_id[p["questao_id"]], "caixa": p["caixa"],
             "prox_revisao": p["prox_revisao"]}
            for p in progresso if p["questao_id"] in por_id
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
    print(f"{len(pacote['questoes'])} questoes, {len(pacote['progresso'])} progressos e "
          f"{len(pacote['tentativas'])} tentativas de {CLI_USUARIO_EMAIL} -> {ARQUIVO} "
          f"({ARQUIVO.stat().st_size // 1024} KB)")
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
    # Pacotes antigos (sincronizar-v1) não tinham usuario_email nem separavam
    # progresso — cair pro CLI_USUARIO_EMAIL local é o melhor esforço razoável,
    # mas progresso desses pacotes ficaria perdido (caixa vivia em `questao`,
    # que este script v2 não lê mais de lá). Aviso, não decide calado.
    email = pacote.get("usuario_email")
    if not email:
        print(f"AVISO: {ARQUIVO} é de uma versão antiga (sem usuario_email); "
              f"assumindo {CLI_USUARIO_EMAIL}. Progresso desse pacote pode ter ficado "
              f"de fora — reexporte na origem com a versão atual se possível.",
              file=sys.stderr)
        email = CLI_USUARIO_EMAIL
    usuario_id = auth.usuario_da_cli(email)

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
                "UPDATE questao SET fonte_chunks = %(f)s WHERE id = %(i)s",
                {"f": chunks, "i": existentes[q["chave"]]},
            )
            atualizadas += 1
        else:
            r = db.exec1(
                """INSERT INTO questao (documento_id, disciplina, tema, enunciado,
                                        gabarito, dicas, fonte_chunks, criada_em)
                   VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s, %(cr)s)
                   RETURNING id""",
                {"d": doc_id, "disc": q["disciplina"], "t": q["tema"],
                 "e": q["enunciado"], "g": q["gabarito"],
                 "dic": json.dumps(q["dicas"]), "f": chunks, "cr": q["criada_em"]},
            )
            id_por_chave[q["chave"]] = r["id"]
            novas += 1

    # Progresso: upsert por (usuario_id, questao_id) — mesmo padrão de
    # scheduler.registrar(). Só entra pra questão que resolveu localmente.
    prog_upsert = 0
    for p in pacote.get("progresso", []):
        qid = id_por_chave.get(p["questao"])
        if qid is None:
            continue
        db.query(
            """INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao)
               VALUES (%(u)s, %(q)s, %(c)s, %(p)s)
               ON CONFLICT (usuario_id, questao_id) DO UPDATE
                 SET caixa = %(c)s, prox_revisao = %(p)s""",
            {"u": usuario_id, "q": qid, "c": p["caixa"], "p": p["prox_revisao"]},
        )
        prog_upsert += 1

    # Tentativas: dedupe por (usuario_id, questao, instante). Reimportar não duplica.
    ja = {(r["questao_id"], r["criada_em"].isoformat())
          for r in db.query("SELECT questao_id, criada_em FROM tentativa WHERE usuario_id = %(u)s",
                            {"u": usuario_id})}
    inseridas = 0
    for t in pacote["tentativas"]:
        qid = id_por_chave.get(t["questao"])
        if qid is None or (qid, t["criada_em"]) in ja:
            continue
        db.query(
            """INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito,
                                      dicas_usadas, segundos, criada_em)
               VALUES (%(u)s, %(q)s, %(r)s, %(v)s, %(d)s, %(s)s, %(c)s)""",
            {"u": usuario_id, "q": qid, "r": t["resposta"], "v": t["veredito"],
             "d": t["dicas_usadas"], "s": t["segundos"], "c": t["criada_em"]},
        )
        inseridas += 1

    # erro_caderno é DERIVADO das tentativas DESTE usuário — escopado, porque
    # o banco local pode ter outros usuários cujo caderno não é deste pacote.
    db.query("DELETE FROM erro_caderno WHERE usuario_id = %(u)s", {"u": usuario_id})
    db.query(
        """INSERT INTO erro_caderno (usuario_id, questao_id, disciplina, tema, vezes, ultima)
           SELECT %(u)s, q.id, q.disciplina, q.tema, count(*), max(t.criada_em)::date
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.usuario_id = %(u)s AND t.veredito <> 'correta'
           GROUP BY q.id""",
        {"u": usuario_id},
    )
    print(f"usuario: {email} (id local {usuario_id})")
    print(f"questoes: {novas} novas, {atualizadas} atualizadas")
    print(f"progresso: {prog_upsert} upserts")
    print(f"tentativas: {inseridas} inseridas")
    if sem_fonte:
        print(f"ATENCAO: {sem_fonte} questoes sem chunk correspondente. "
              f"Ingira o material antes de importar, senao a cobertura mente.")
    return 0


def estado() -> int:
    q = db.exec1("SELECT count(*) AS n FROM questao") or {"n": 0}
    c = db.exec1("SELECT count(*) AS n FROM chunk") or {"n": 0}
    usuario_id = auth.usuario_da_cli(CLI_USUARIO_EMAIL)
    t = db.exec1("SELECT count(*) AS n FROM tentativa WHERE usuario_id = %(u)s",
                {"u": usuario_id}) or {"n": 0}
    print(f"banco local : {c['n']} chunks · {q['n']} questoes (compartilhadas) · "
          f"{t['n']} tentativas de {CLI_USUARIO_EMAIL}")
    if ARQUIVO.exists():
        p = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        print(f"arquivo     : {len(p['questoes'])} questoes · "
              f"{len(p.get('progresso', []))} progressos · "
              f"{len(p['tentativas'])} tentativas · "
              f"usuario {p.get('usuario_email', '?')} · gerado {p['gerado_em']}")
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
