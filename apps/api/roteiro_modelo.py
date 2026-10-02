#!/usr/bin/env python3
"""
ROTEIRO COM O MODELO DE VERDADE — barato: uma chamada por turno, sem aluno
simulado e sem juiz. Quem lê as respostas é quem roda.

    python roteiro_modelo.py                 # todos os roteiros
    python roteiro_modelo.py --so calculos   # um só

Conta DESCARTÁVEL montada de `cenarios/descoberta.json` (material sintético e lei
pública), com o índice de assuntos desligado e os rótulos já dados — montar a
conta não gasta cota. Cada roteiro é uma conversa com falas FIXAS, tiradas dos
defeitos reais. Saída: `.logs/roteiro.md`, com a resposta, as fontes e os
cartões de cada turno.

É o passo 2. O passo 1, sempre antes, é `bateria_decisoes.py` (sem cota nenhuma).
"""
import argparse
import json
import re
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import api
from bateria_conversa import montar_conta
from core import assunto, auth, db, indice, telemetria  # noqa: F401 — telemetria conta as chamadas

VERSAO = "roteiro-modelo-v2"
SAIDA = Path(__file__).resolve().parents[2] / ".logs" / "roteiro.md"

# Falas da conversa real de 01/10/2026 e das anteriores, reescritas sobre o
# material sintético da conta.
ROTEIROS = {
    "calculos": ["rlm", "vamos pros calculos", "sim ja com a resolução", "e da questão anterior?"],
    "leitura": ["rlm", "traga todo conceito", "certo..", "é só isso que tem no material?",
                "o que é uma proposição?"],
    "explica": ["me explica a organização do estado", "qual a diferença entre união e estados?",
                "continua"],
    "sem_material": ["quero estudar informática", "me manda uma questão disso"],
    "questoes": ["quero questões de juros simples", "e de conjuntos?"],
}


# PALAVRA QUE O MODELO INVENTOU ("autovernossa" por "autogoverno", 02/10/2026).
# Só ALARME para quem lê: palavra longa cuja raiz não está em nenhum trecho do
# banco nem na fala. Não corrige nada — no português, plural, conjugação e nome
# próprio dariam troca errada; aqui o pior caso é um falso alarme no relatório.
RE_PALAVRA = re.compile(r"(?<![\\A-Za-zÀ-ÿ])[A-Za-zÀ-ÿ]{9,}")   # \comando de LaTeX não é palavra


def _raiz(p: str) -> str:
    return assunto._sem_acento(p.lower())[:7]


def vocabulario() -> set[str]:
    raizes: set[str] = set()
    for r in db.query("SELECT texto FROM chunk"):
        raizes |= {_raiz(p) for p in RE_PALAVRA.findall(r["texto"])}
    return raizes


def estranhas(resposta: str, fala: str, vocab: set[str]) -> list[str]:
    da_fala = {_raiz(p) for p in RE_PALAVRA.findall(fala)}
    return sorted({p for p in RE_PALAVRA.findall(resposta)
                   if _raiz(p) not in vocab and _raiz(p) not in da_fala})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", choices=list(ROTEIROS))
    a = ap.parse_args()
    indice.ORCAMENTO_DIA = 0          # o índice sai pela reserva: montar a conta não gasta cota
    dados = json.load(open(Path(__file__).parent / "cenarios" / "descoberta.json", encoding="utf-8"))["conta"]
    for m in dados["materiais"]:      # rótulo dado = classificador não roda
        m.setdefault("assunto", m.get("titulo"))
    uid = auth.usuario_da_cli(f"bateria-{uuid.uuid4().hex[:12]}@local")
    linhas = [f"# Roteiro com o modelo ({VERSAO})", ""]
    chamadas = alarmes = 0
    publicas: set[int] = set()        # questão da LEI sai pública: não morre com a conta
    try:
        mid = montar_conta(uid, dados)
        cli = TestClient(api.app)
        cab = {"Authorization": f"Bearer {auth.emitir_token(uid)}", "X-Mesa-Id": str(mid)}
        vocab = vocabulario()
        alarmes = 0
        antes = db.exec1("SELECT count(*) AS n FROM telemetria_llm")["n"]
        for nome, falas in ROTEIROS.items():
            if a.so and nome != a.so:
                continue
            linhas += [f"## {nome}", ""]
            cid = None
            for fala in falas:
                r = cli.post("/perguntar", headers=cab,
                             json={"pergunta": fala, **({"conversa_id": cid} if cid else {})})
                if r.status_code != 200:
                    linhas += [f"**Aluno:** {fala}", "", f"_HTTP {r.status_code}: {r.text[:200]}_", ""]
                    continue
                j = r.json()
                cid = j["conversa_id"]
                fontes = [f"{f.get('rotulo') or f.get('referencia') or f.get('id')}"
                          + (" (lida)" if f.get("sequencial") else "") for f in (j.get("fontes") or [])][:6]
                cartoes = [f"{q.get('tema')} [{q.get('tipo')}]" for q in j.get("questoes") or []]
                publicas |= {q["id"] for q in j.get("questoes") or [] if q.get("usuario_id") is None}
                fora = estranhas(j.get("resposta", ""), fala, vocab)
                alarmes += bool(fora)
                linhas += [f"**Aluno:** {fala}", "", "**Tutor:**", "", j.get("resposta", ""), "",
                           f"_fontes: {fontes or '—'} · cartões: {cartoes or '—'}_", ""]
                if fora:
                    linhas += [f"> ⚠ palavras que não estão em material nenhum (conferir): {', '.join(fora)}", ""]
                print(f"  {nome}: {fala!r} → {len(j.get('resposta', ''))} caracteres, "
                      f"{len(cartoes)} cartão(ões)", flush=True)
        chamadas = db.exec1("SELECT count(*) AS n FROM telemetria_llm")["n"] - antes
    finally:
        if publicas:
            db.query("DELETE FROM questao WHERE id = ANY(%(i)s) AND usuario_id IS NULL "
                     "AND NOT EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = questao.id)",
                     {"i": list(publicas)})
        db.query("DELETE FROM usuario WHERE id = %(u)s", {"u": uid})
    linhas.insert(1, f"_chamadas ao modelo: {chamadas} · turnos com palavra a conferir: {alarmes}_")
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    print(f"chamadas ao modelo: {chamadas} → {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
