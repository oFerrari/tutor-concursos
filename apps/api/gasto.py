#!/usr/bin/env python3
"""
Painel de consumo do LLM: quanto foi gasto hoje, em qual modelo, por quem.

    ./tutor gasto              hoje
    ./tutor gasto --dias 7     a semana
    ./tutor gasto --json       o mesmo, pra script

Nasceu de um 429 que derrubou uma bateria inteira de `testar.sh` sem que
houvesse, de dentro do projeto, como saber quanto tinha sido gasto. A fonte é
`telemetria_llm` (030), gravada por `core/llm.py` a cada TENTATIVA — inclusive
a que falhou, que é justamente a que consumiu cota sem produzir nada.

O QUE ESTE PAINEL NÃO É: a contabilidade da Google. Ele conta o que ESTE
projeto pediu; a cota da chave é da conta e pode estar sendo gasta por outra
coisa (o ai-memory, por exemplo, se estiver com a mesma chave). O número
oficial está no AI Studio; este é o que dá pra agir em cima.
"""
import argparse
import json
import os

from rich.console import Console
from rich.table import Table

from core import telemetria
from core.config import GEMINI_MODEL, LLM_PROVIDER

VERSAO = "gasto-v2"
console = Console()

# TETO DECLARADO, NÃO MEDIDO — e a diferença importa o suficiente pra estar
# escrita no próprio painel. O free tier da Google muda de limite por modelo e
# ao longo do tempo, e este número é o que VOCÊ declarou, não o que a API
# confirmou. Quem sabe o valor real é a mensagem do 429, que traz o limite e a
# métrica ("limit: 20, model: gemini-3.5-flash").
#
# Ajustável sem mexer no código: `LIMITE_DIARIO_REQ=250` no .env.
LIMITE_DIARIO_REQ = int(os.getenv("LIMITE_DIARIO_REQ", "1500"))
LARGURA_BARRA = 10


def _linha_do_topo(r: dict) -> str:
    ativo = r["modelo_ativo"] or GEMINI_MODEL
    marca = "" if ativo == GEMINI_MODEL else f"  (configurado: {GEMINI_MODEL})"
    return f"[bold]{LLM_PROVIDER}[/] · modelo ativo: [bold cyan]{ativo}[/]{marca}"


def barra(chamadas: int) -> str:
    """[██░░░░░░░░] 2,1% (32/1500 requisições), com a cor dizendo a urgência."""
    if LIMITE_DIARIO_REQ <= 0:
        return ""
    pct = min(chamadas / LIMITE_DIARIO_REQ * 100, 100.0)
    cheios = int(pct / 100 * LARGURA_BARRA)
    cor = "green" if pct < 60 else "yellow" if pct < 85 else "red"
    desenho = "█" * cheios + "░" * (LARGURA_BARRA - cheios)
    return (rf"[{cor}]\[{desenho}][/] {pct:.1f}% "
            f"({chamadas}/{LIMITE_DIARIO_REQ} requisições)".replace(".", ","))


def imprimir(r: dict) -> None:
    janela = "hoje" if r["dias"] == 1 else f"últimos {r['dias']} dias"
    console.print()
    console.print(f"  {_linha_do_topo(r)}")
    console.print(f"  {barra(r['chamadas'])}")
    console.print(f"  [dim]{janela} · última chamada: "
                  f"{r['ultima_chamada'] or '—'}[/]")
    # O QUE A BARRA NÃO VÊ, dito onde ela é lida. A conta é da CHAVE; esta
    # tabela só registra o que passou por `core/llm.py`. Qualquer outro processo
    # com a mesma chave — o ai-memory, um script solto, a outra máquina —
    # consome a mesma cota sem aparecer aqui.
    console.print("  [dim]estimativa local: conta só o que este backend pediu. "
                  "Outro processo com a mesma chave (ai-memory, outra máquina) "
                  "gasta e não entra.[/]")
    console.print()

    if not r["chamadas"]:
        console.print("  [dim]nenhuma chamada registrada nesta janela.[/]")
        console.print("  [dim]a telemetria começa a valer depois da 030 — "
                      "rodadas anteriores não aparecem aqui.[/]\n")
        return

    total_tokens = r["tokens_input"] + r["tokens_output"]
    console.print(f"  [bold]{r['chamadas']}[/] chamada(s) · "
                  f"[bold]{total_tokens:,}[/] tokens "
                  f"({r['tokens_input']:,} entrada + {r['tokens_output']:,} saída)"
                  .replace(",", "."))
    # O 429 ganha destaque próprio: é o número que responde "estourei a cota?".
    cor = "red" if r["quota_429"] else "dim"
    console.print(f"  [{cor}]{r['quota_429']} estouro(s) de cota (429)[/] · "
                  f"[dim]{r['falhas']} outra(s) falha(s)[/]")
    console.print()

    t = Table(box=None, pad_edge=False, header_style="dim")
    t.add_column("modelo"); t.add_column("chamadas", justify="right")
    t.add_column("entrada", justify="right"); t.add_column("saída", justify="right")
    t.add_column("429", justify="right")
    for m in r["por_modelo"]:
        t.add_row(m["modelo"], str(m["chamadas"]),
                  f"{m['tokens_input']:,}".replace(",", "."),
                  f"{m['tokens_output']:,}".replace(",", "."),
                  f"[red]{m['quota']}[/]" if m["quota"] else "—")
    console.print(t)

    if r["por_origem"]:
        console.print()
        o = Table(box=None, pad_edge=False, header_style="dim")
        o.add_column("de onde veio"); o.add_column("chamadas", justify="right")
        o.add_column("tokens", justify="right")
        for x in r["por_origem"]:
            o.add_row(x["origem"], str(x["chamadas"]),
                      f"{x['tokens']:,}".replace(",", "."))
        console.print(o)

    console.print()
    console.print("  [dim]a cota diária do free tier zera à meia-noite do Pacífico "
                  "(madrugada no Brasil).[/]")
    console.print("  [dim]o número oficial da conta está em "
                  "https://aistudio.google.com/apikey[/]\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="consumo do LLM deste projeto")
    ap.add_argument("--dias", type=int, default=1,
                    help="janela em dias de calendário (padrão: 1, hoje)")
    ap.add_argument("--json", action="store_true", help="devolve o resumo cru")
    a = ap.parse_args()

    r = telemetria.resumo(dias=max(1, a.dias))
    if a.json:
        print(json.dumps(r, default=str, ensure_ascii=False, indent=2))
    else:
        imprimir(r)


if __name__ == "__main__":
    main()
