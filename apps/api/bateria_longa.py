#!/usr/bin/env python3
"""
BATERIA LONGA — uma conversa de 55 falas seguidas (`cenarios/roteiro_longo.json`)
numa conta DESCARTÁVEL com material e edital sintéticos (`cenarios/descoberta.json`).

    python bateria_longa.py                # etapa 1: decisões, SEM modelo (cota zero)
    python bateria_longa.py --modelo       # etapa 2: o chat de verdade, ~1 chamada por fala
                                           #   + etapa 3: avaliar_offline nas respostas gravadas

ETAPA 1. Cada fala passa pela lógica de decisão do chat (`bateria_decisoes.turno`,
alinhada à rota): matéria em foco, leitura (abre / continua / não), cartões e de
que matéria, resolução. A resposta do tutor é a ESCRITA no roteiro, e o estado
avança como na rota: a leitura vira marcador na mensagem, o trecho usado vira
fonte citada. É o que deixa uma conversa longa e encadeada rodar sem modelo.

ETAPA 2. As mesmas falas no `/perguntar` real, uma após a outra, na mesma
conversa. Confere o que a resposta EXPÕE: cartões (e de que matéria) e leitura
(fonte em sequência). Etapa 3: `avaliar_offline.py` lê a conversa gravada.

Saída: `.logs/bateria-longa.md` (e a conversa da etapa 2 em `.logs/bateria-longa-conversa.md`).
Código 1 quando alguma expectativa falha.
"""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import bateria_decisoes as BD
from bateria_conversa import montar_conta
from core import auth, db, indice, mesa

VERSAO = "bateria-longa-v1"
AQUI = Path(__file__).resolve().parent
LOGS = AQUI.parents[1] / ".logs"
SAIDA = LOGS / "bateria-longa.md"
CONVERSA = LOGS / "bateria-longa-conversa.md"


def _conta() -> tuple[int, int, dict]:
    indice.ORCAMENTO_DIA = 0      # índice pela reserva: montar a conta não gasta cota
    dados = json.loads((AQUI / "cenarios" / "descoberta.json").read_text(encoding="utf-8"))["conta"]
    for m in dados["materiais"]:  # rótulo dado = o classificador não roda
        m.setdefault("assunto", m.get("titulo"))
    uid = auth.usuario_da_cli(f"bateria-{uuid.uuid4().hex[:12]}@local")
    mid = montar_conta(uid, dados)
    return uid, mid, mesa.contexto(uid, mid)


def _disciplinas_dos_cartoes(cartoes: dict, mapa: dict) -> set[str]:
    nomes = set()
    if cartoes.get("trechos"):
        cs = db.query("""SELECT c.id, d.disciplina, d.tipo FROM chunk c JOIN documento d ON d.id = c.documento_id
                          WHERE c.id = ANY(%(i)s)""", {"i": cartoes["trechos"]})
        for ms in BD._materias_do_trecho(cs).values():
            nomes |= ms
    if cartoes.get("prova"):
        nomes |= {r["disciplina"] for r in db.query("SELECT disciplina FROM questao WHERE id = ANY(%(i)s)",
                                                     {"i": cartoes["prova"]})}
    return nomes


def _materia_dos_docs(ids: list[int], mapa: dict, disciplinas: list[str]) -> set[str]:
    from core import assunto
    return {assunto.disciplina_do_edital(r["disciplina"], disciplinas, mapa) or r["disciplina"]
            for r in db.query("SELECT DISTINCT disciplina FROM documento WHERE id = ANY(%(i)s)", {"i": ids})}


def _confere(esp: dict, foco, leitura: str, cartoes, resolucao, quantidade=None, lida=None) -> list[str]:
    erros = []
    # Só quando leu algo: material que acabou ("continua" sem trecho novo) é outro caso.
    if esp.get("leitura_de") and lida and lida != {esp["leitura_de"]}:
        erros.append(f"leu material de {sorted(lida) or 'nada'}, esperado {esp['leitura_de']}")
    if esp.get("foco", "*") != "*" and foco != esp["foco"]:
        erros.append(f"foco {foco!r}, esperado {esp['foco']!r}")
    if esp.get("leitura", "*") != "*" and leitura != esp["leitura"]:
        erros.append(f"leitura {leitura!r}, esperado {esp['leitura']!r}")
    c = esp.get("cartoes", "*")
    if c == "nao" and cartoes is not None:
        erros.append(f"tratou como pedido de questões ({cartoes})")
    elif c == "nenhum" and (cartoes is None or cartoes):
        erros.append("não reconheceu o pedido" if cartoes is None else f"cartões de {sorted(cartoes)} sem material da matéria")
    elif c not in ("*", "nao", "nenhum"):
        if cartoes is None:
            erros.append("não reconheceu o pedido de questões")
        elif not cartoes:
            erros.append(f"pedido sem cartões (esperado de {c})")
        elif cartoes - {c}:
            erros.append(f"cartões de {sorted(cartoes)}, esperado só {c}")
    if esp.get("quantidade") and quantidade and quantidade != esp["quantidade"]:
        erros.append(f"quantidade {quantidade}, esperado {esp['quantidade']}")
    if esp.get("resolucao") and not resolucao:
        erros.append("não reconheceu o pedido de resolução")
    return erros


def etapa_offline(uid: int, mid: int, ctx: dict, turnos: list) -> list[tuple[int, str, list[str]]]:
    msgs, resultados = [], []
    for i, t in enumerate(turnos, 1):
        msgs.append({"autor": "aluno", "texto": t["aluno"], "fontes": []})
        r = BD.turno(uid, mid, ctx, msgs, len(msgs) - 1)
        plano = r["plano"]
        leitura = "nao" if not plano else ("continua" if plano.get("intencao") == "continua" else "abre")
        cart = None if r["cartoes"] is None else _disciplinas_dos_cartoes(r["cartoes"], ctx["mapa"])
        # Em pedido de questões, a matéria que vale é a da escolha dos cartões (inclui a do material lido).
        foco = r["foco_cartoes"] if r["cartoes"] is not None else r["foco"]
        lida = (_materia_dos_docs([c["documento_id"] for c in plano["trechos"]], ctx["mapa"], ctx["disciplinas"])
                if plano and plano["trechos"] else set())
        erros = _confere(t, foco, leitura, cart, r["resolucao"], (r["cartoes"] or {}).get("quantidade"), lida)
        resultados.append((i, t["aluno"], erros))
        # O estado avança como na rota: leitura vira marcador; trecho usado, fonte citada.
        if plano:
            fontes = [{"id": c["id"], "documento_id": c.get("documento_id"), "ordem": c.get("ordem"),
                       "sequencial": True, "material": True, "citada": True} for c in plano["trechos"]]
        else:
            # "material" como na rota: só aula ou resumo do aluno (simulado não é material de leitura)
            fontes = [{"id": c["id"], "documento_id": c.get("documento_id"), "citada": True,
                       "material": c.get("dono") is not None and c.get("tipo") in ("aula", "resumo")}
                      for c in (r["chunks"] or [])[:2]]
        msgs.append({"autor": "tutor", "texto": t["tutor"], "fontes": fontes})
        if r["cartoes"] and (r["cartoes"].get("trechos") or r["cartoes"].get("prova")):
            # a rota grava o evento depois dos cartões; é o que `veio_de_treino` lê
            msgs.append({"autor": "evento", "texto": "Você propôs questões. O aluno vai respondê-las agora.",
                         "fontes": []})
    return resultados


def etapa_modelo(uid: int, mid: int, turnos: list, mesa_ctx: dict) -> tuple[list, int | None, int]:
    from fastapi.testclient import TestClient
    import api
    cli = TestClient(api.app)
    cab = {"Authorization": f"Bearer {auth.emitir_token(uid)}", "X-Mesa-Id": str(mid)}
    g0 = db.exec1("SELECT count(*) AS n FROM telemetria_llm")["n"]
    cid, resultados, transcricao = None, [], [f"# Conversa da bateria longa ({VERSAO})", ""]
    for i, t in enumerate(turnos, 1):
        r = cli.post("/perguntar", headers=cab, json={"pergunta": t["aluno"], **({"conversa_id": cid} if cid else {})})
        if r.status_code != 200:
            resultados.append((i, t["aluno"], [f"HTTP {r.status_code}: {r.text[:160]}"]))
            transcricao += [f"**{i}. Aluno:** {t['aluno']}", "", f"_HTTP {r.status_code}_", ""]
            continue
        j = r.json()
        cid = j["conversa_id"]
        seq = any(f.get("sequencial") for f in j.get("fontes") or [])
        leitura = "nao" if not seq else ("*")  # abre x continua não aparece na resposta
        qs = j.get("questoes") or []
        cart = None if not qs and t.get("cartoes") in ("nao", "*") else {q.get("disciplina") for q in qs}
        esp = {**t, "foco": "*", "leitura": "*" if t.get("leitura") in ("abre", "continua") and seq
               else t.get("leitura", "*")}
        if t.get("leitura") in ("abre", "continua") and not seq:
            esp["leitura"] = t["leitura"]
        lida = _materia_dos_docs([f["documento_id"] for f in j.get("fontes") or [] if f.get("sequencial")],
                                 mesa_ctx["mapa"], mesa_ctx["disciplinas"])
        erros = _confere(esp, None, leitura, cart, True, lida=lida)
        if t.get("cartoes") == "nao" and qs:
            erros.append(f"{len(qs)} cartão(ões) sem pedido")
        resultados.append((i, t["aluno"], erros))
        transcricao += [f"**{i}. Aluno:** {t['aluno']}", "", j.get("resposta", ""), "",
                        f"_cartões: {[(q.get('disciplina'), q.get('tema')) for q in qs] or '—'} · leitura: {'sim' if seq else 'não'}_"
                        + (f" · **{'; '.join(erros)}**" if erros else ""), ""]
        print(f"  {i:>2}. {t['aluno'][:50]!r} → {len(j.get('resposta', ''))} car., {len(qs)} cartão(ões)"
              + (f" ✗ {erros}" if erros else ""), flush=True)
    CONVERSA.write_text("\n".join(transcricao), encoding="utf-8")
    return resultados, cid, db.exec1("SELECT count(*) AS n FROM telemetria_llm")["n"] - g0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", action="store_true", help="etapas 2 e 3: o chat de verdade (gasta cota)")
    a = ap.parse_args()
    turnos = json.loads((AQUI / "cenarios" / "roteiro_longo.json").read_text(encoding="utf-8"))["turnos"]
    LOGS.mkdir(exist_ok=True)
    uid, mid, ctx = _conta()
    linhas = [f"# Bateria longa ({VERSAO}) — {len(turnos)} falas", ""]
    falhas = 0
    try:
        off = etapa_offline(uid, mid, ctx, turnos)
        n_off = sum(1 for _, _, e in off if e)
        falhas += n_off
        linhas += [f"## Etapa 1 — decisões, sem modelo: {len(turnos) - n_off}/{len(turnos)} falas ok", ""]
        linhas += [f"- **{i}.** {fala!r}: {'; '.join(e)}" for i, fala, e in off if e] or ["Nenhuma falha."]
        print(f"etapa 1 (sem modelo): {len(turnos) - n_off}/{len(turnos)} ok", flush=True)
        if a.modelo:
            mod, cid, chamadas = etapa_modelo(uid, mid, turnos, ctx)
            n_mod = sum(1 for _, _, e in mod if e)
            falhas += n_mod
            linhas += ["", f"## Etapa 2 — chat real: {len(turnos) - n_mod}/{len(turnos)} falas ok · "
                           f"{chamadas} chamadas ao modelo", ""]
            linhas += [f"- **{i}.** {fala!r}: {'; '.join(e)}" for i, fala, e in mod if e] or ["Nenhuma falha."]
            linhas += ["", f"Conversa completa: `.logs/{CONVERSA.name}`"]
            if cid:
                r = subprocess.run([sys.executable, str(AQUI / "avaliar_offline.py"), "--rapido",
                                    "--conversa", str(cid), "--usuario", str(uid), "--limite", "200",
                                    "--saida", str(LOGS / "bateria-longa-avaliacao")],
                                   capture_output=True, text=True, cwd=AQUI)
                resumo = (r.stdout.strip().splitlines() or ["(sem saída)"])[0]
                linhas += ["", f"## Etapa 3 — avaliação offline das respostas", "", resumo,
                           "Relatório: `.logs/bateria-longa-avaliacao/ultimo.md`"]
                print(f"etapa 3: {resumo}", flush=True)
    finally:
        db.query("DELETE FROM questao WHERE usuario_id = %(u)s", {"u": uid})
        db.query("DELETE FROM usuario WHERE id = %(u)s", {"u": uid})
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    print(f"→ {SAIDA}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
