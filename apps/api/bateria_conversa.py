"""Bateria de conversas com o modelo REAL, numa conta DESCARTÁVEL montada aqui.

Complementa o `./testar.sh` (aluno sintético sem material próprio): esta monta
uma conta com biblioteca e edital, que é onde a leitura em sequência, a matéria
sem material e a retomada por material acontecem.

A CONTA É DA BATERIA, NÃO DE NINGUÉM. Nasce com e-mail aleatório `@local`,
recebe as "apostilas" descritas no arquivo de cenários — recortes do corpus
PÚBLICO do repositório (CF, Lei 8.112) — e um edital sintético, roda os
cenários e é apagada no fim (o CASCADE da 009/019 leva mesa, edital e
material). Nenhuma conta real é lida nem escrita, e nada disto depende de quem
roda. Criada em 24/09/2026: a primeira versão pedia o e-mail do dono, e as
mudanças que ela valida são para qualquer aluno.

    python bateria_conversa.py cenarios/leitura_e_sem_material.json

Gasta uma chamada ao modelo por turno. Sai com código 1 se algum turno falhar.

Expectativa de cada turno:
  "sem"            sem material: nenhum trecho, e a resposta diz que não há material
  "ler:<disc>"     turno de leitura de material dessa disciplina ("ler:" = qualquer)
  "busca"          turno comum (não é leitura)
  null             só observa
"""
import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

from core import auth, db, diario, material, mesa, socratic

VERSAO = "bateria-conversa-v3"

AQUI = Path(__file__).parent
RE_DIZ_QUE_NAO_HA = re.compile(
    r"(?i)n[aã]o (h[aá]|tem|temos|est[aá]|traz\w*|tenho|consta)|ainda n[aã]o|sem material|vazi[oa]")


def _recorte_do_corpus(arquivo: str, de: str, ate: str) -> str:
    """Os artigos `de` até antes de `ate`, do corpus público — a "apostila"."""
    texto = (AQUI / arquivo).read_text(encoding="utf-8")
    ini = re.search(rf"(?m)^Art\.\s*{re.escape(de)}(?:[º°o.\s])", texto)
    if not ini:
        sys.exit(f"{arquivo}: não achei o Art. {de}")
    fim = re.search(rf"(?m)^Art\.\s*{re.escape(ate)}(?:[º°o.\s])", texto[ini.start() + 1:])
    return texto[ini.start():ini.start() + 1 + fim.start()] if fim else texto[ini.start():]


def _apostila(titulo: str, recorte: str) -> str:
    """O recorte da lei vestido de AULA: apresentação, cada artigo com o
    comentário de como a banca cobra, e uma questão no fim. Lei crua é recusada
    pelo próprio app quando o acervo já a tem (`material.registrar`), e é
    classificada como lei seca — a companhia de "banca" e "questão" é o que
    separa apostila de lei (ver `test_apostila_que_transcreve_a_lei_nao_e_lei_seca`)."""
    artigos = [a.strip() for a in re.split(r"(?m)^(?=Art\.)", recorte) if a.strip()]
    partes = [f"{titulo}\n\nApresentação da aula\n\nOlá, aluno! Nesta aula vamos percorrer o texto "
              f"legal na ordem, comentando como a banca costuma cobrar cada ponto. Bons estudos!"]
    for n, art in enumerate(artigos, 1):
        partes.append(f"Tópico {n}\n\n{art}\n\nComentário: a banca costuma cobrar este dispositivo "
                      f"pela literalidade; em questões, atenção aos termos do texto legal e às "
                      f"exceções que ele mesmo prevê.")
    partes.append("Questão comentada\n\n(Banca sintética) Julgue o item com base no texto estudado "
                  "nesta aula. Gabarito: certo, conforme a literalidade do dispositivo.")
    return "\n\n".join(partes)


def montar_conta(uid: int, conta: dict) -> int:
    m = mesa.criar(uid, "Mesa da bateria")
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, 'Edital sintético da bateria') "
                   "RETURNING id", {"m": m["id"]})["id"]
    ordem = 0
    for disciplina, topicos in conta["edital"].items():
        for t in topicos:
            db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) "
                     "VALUES (%(e)s, %(d)s, %(o)s, %(t)s)",
                     {"e": eid, "d": disciplina, "o": ordem, "t": t})
            ordem += 1
    for mat in conta["materiais"]:
        # "texto": apostila escrita para o teste (a de cálculo, que o corpus não tem);
        # "corpus": recorte da lei pública, vestido de aula.
        texto = ((AQUI / mat["texto"]).read_text(encoding="utf-8") if mat.get("texto") else
                 _apostila(mat["titulo"], _recorte_do_corpus(mat["corpus"], mat["de"], mat["ate"])))
        dados = texto.encode()
        doc = material.registrar(uid, mat["arquivo"], dados, disciplina=mat.get("disciplina"),
                                 tipo=mat.get("tipo", "aula"), titulo=mat["titulo"], assunto=mat.get("assunto"))
        material.indexar(doc["id"], mat["arquivo"], dados)
        n = db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id = %(d)s", {"d": doc["id"]})["n"]
        print(f"  material: {mat['titulo']} ({mat['disciplina']}) — {n} trechos")
    return m["id"]


def apagar_conta(uid: int) -> None:
    db.query("DELETE FROM usuario WHERE id = %(u)s", {"u": uid})


def rodar(nome: str, turnos: list, uid: int, contexto: dict) -> int:
    hist, fontes_tutor, falhas = [], [], 0

    def ultima():
        for i, fs in enumerate(reversed(fontes_tutor)):
            lidas = [f for f in fs if f.get("sequencial") and f.get("ordem") is not None]
            if lidas:
                return {"documento_id": lidas[-1]["documento_id"], "ordem": max(f["ordem"] for f in lidas),
                        "ids": [f["id"] for f in lidas], "foi_a_ultima": i == 0}

    def marcadores():
        mk = {}
        for n, fs in enumerate(fontes_tutor):
            lidas = [f for f in fs if f.get("sequencial") and f.get("ordem") is not None]
            if lidas:
                mk[lidas[-1]["documento_id"]] = {"ordem": max(f["ordem"] for f in lidas), "quando": n}
        return mk

    def recente():
        for fs in reversed(fontes_tutor[-6:]):
            mats = [f for f in fs if f.get("dono") is not None and f.get("tipo") in ("aula", "resumo")]
            cit = [f for f in mats if f.get("citada")]
            if cit or mats:
                return (cit or mats)[0]["documento_id"]

    print(f"\n################ {nome}")
    for fala, espera in turnos:
        t = time.time()
        try:
            r = socratic.explicar(fala, uid, contexto["disciplinas"], contexto, hist[-16:],
                                  auth.perfil(uid), leitura_atual=ultima(),
                                  material_recente=recente(), marcadores=marcadores())
        except Exception as e:  # noqa: BLE001 — a bateria reporta e segue
            print(f"✗ {fala!r}: EXCEÇÃO {e}")
            falhas += 1
            continue
        fontes_tutor.append(r["fontes"])
        hist += [{"autor": "aluno", "texto": fala}, {"autor": "tutor", "texto": r["resposta"]}]
        seq = [f for f in r["fontes"] if f.get("sequencial")]
        cit = [f for f in r["fontes"] if f.get("citada")]
        tipo = (f"LEITURA {seq[0].get('disciplina')} ordens {[f['ordem'] for f in seq]}"
                if seq else f"busca {len(r['fontes'])} trechos, {len(cit)} citados")
        ok = True
        if espera == "sem":
            ok = not r["fontes"] and bool(RE_DIZ_QUE_NAO_HA.search(r["resposta"]))
        elif espera and espera.startswith("ler:"):
            ok = bool(seq) and espera[4:].lower() in (seq[0].get("disciplina") or "").lower()
        elif espera == "busca":
            ok = not seq
        falhas += not ok
        marca = "  " if espera is None else ("✓ " if ok else "✗ ")
        resposta = re.sub(r"\s+", " ", r["resposta"])[:260]
        print(f"{marca}[{time.time() - t:4.1f}s {len(r['resposta'].split()):4}p] {fala!r}\n"
              f"      → {tipo}\n      » {resposta}")
    print(f"  == {nome}: {falhas} falha(s)")
    return falhas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cenarios", help="JSON com a conta sintética e os cenários")
    ap.add_argument("--so", help="rodar só os cenários cujo nome contém este texto")
    args = ap.parse_args()
    dados = json.loads((Path(args.cenarios)).read_text(encoding="utf-8"))
    diario.anotar = lambda *a, **k: None   # cada cenário começa sem "aula de ontem"
    uid = auth.usuario_da_cli(f"bateria-{uuid.uuid4().hex[:12]}@local")
    try:
        contexto = mesa.contexto(uid, montar_conta(uid, dados["conta"]))
        total = sum(rodar(c["nome"], [tuple(t) for t in c["turnos"]], uid, contexto)
                    for c in dados["cenarios"] if not args.so or args.so in c["nome"])
    finally:
        apagar_conta(uid)
    print(f"\nTOTAL DE FALHAS: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
