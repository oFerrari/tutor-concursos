#!/usr/bin/env python3
"""
Sessão de estudo no terminal.

    python chat.py estudar          # fila de revisão do dia, modo socrático
    python chat.py perguntar "diferença entre dolo eventual e culpa consciente"
    python chat.py erros
    python chat.py stats
    python chat.py meta 2026-11-15

Provar o loop aqui antes de escrever uma linha de Next.js. Se a tutoria
funciona sem interface, o frontend é só apresentação.
"""
import json
import sys
import time
from datetime import date

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from core import llm, scheduler, socratic

VERSAO = "chat-v16"
con = Console()
MAX_DICAS = 3


def _dicas(q) -> list[str]:
    d = q["dicas"]
    return json.loads(d) if isinstance(d, str) else (d or [])


def estudar() -> None:
    pendentes = scheduler.fila()
    if not pendentes:
        con.print("[green]Nada pendente hoje.[/] Ingira material novo ou volte amanhã.")
        return

    con.print(f"[bold]{len(pendentes)}[/] questões na fila de hoje.\n")
    for q in pendentes:
        dicas = _dicas(q)
        con.print(Panel(q["enunciado"],
                        title=f"{q['disciplina']} · {q['tema']}",
                        subtitle=f"caixa {q['caixa']}", border_style="blue"))
        nivel, inicio = 0, time.monotonic()
        veredito, ultima_resposta = None, ""

        def fechar(v):
            """Grava a tentativa. Chamado tanto no fim normal quanto ao sair."""
            r = scheduler.registrar(q["id"], v, ultima_resposta, nivel,
                                    int(time.monotonic() - inicio))
            con.print(f"[dim]registrado como {v} · caixa {r['caixa']} · "
                      f"próxima revisão {r['prox_revisao']}[/]\n")

        while True:
            restam = max(0, MAX_DICAS - nivel)
            aviso = (f"{restam} tentativa(s) antes do gabarito"
                     if restam else "o gabarito aparece na próxima")
            try:
                resposta = con.input(
                    f"\n[bold cyan]sua resposta[/] [dim]({aviso}; 'dica', 'pular', 'sair')[/]: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                resposta = "sair"

            # Sair não pode descartar o esforço: se houve tentativa errada, ela
            # é dado real e vai para o caderno de erros. Perder isso ensinava o
            # usuário a nunca interromper a sessão.
            if resposta in ("sair", "pular"):
                if ultima_resposta:
                    fechar("incorreta")
                elif resposta == "sair":
                    con.print("[dim]nada respondido; nada registrado.[/]")
                if resposta == "sair":
                    con.print("[dim]até a próxima.[/]")
                    return
                break

            if resposta == "dica":
                if nivel < min(MAX_DICAS, len(dicas)):
                    con.print(f"[yellow]dica {nivel + 1}:[/] {dicas[nivel]}")
                    nivel += 1
                else:
                    con.print("[yellow]as dicas acabaram. Tente formular o que você lembra.[/]")
                continue
            if not resposta:
                continue

            ultima_resposta = resposta
            with con.status("corrigindo…"):
                try:
                    av = socratic.avaliar(q["enunciado"], q["gabarito"], resposta, nivel)
                except llm.ErroLLM as e:
                    con.print(f"[red]LLM indisponível:[/] {e}")
                    con.print(Panel(q["gabarito"], title="gabarito", border_style="green"))
                    auto = con.input("acertou? [s/n]: ").strip().lower()
                    veredito = "correta" if auto.startswith("s") else "incorreta"
                    break

            veredito = av["veredito"]
            if veredito == "correta":
                con.print(f"[green]✓ {av['comentario']}[/]")
                break

            con.print(f"[yellow]{av['comentario']}[/]")
            if av["pergunta"]:
                con.print(f"[cyan]→ {av['pergunta']}[/]")
            if nivel < min(MAX_DICAS, len(dicas)):
                con.print(f"[dim]dica {nivel + 1}: {dicas[nivel]}[/]")
                nivel += 1
            if av["revelar_gabarito"] and nivel >= MAX_DICAS:
                con.print(Panel(q["gabarito"], title="gabarito", border_style="green"))
                break

        if veredito:
            fechar(veredito)


def perguntar(pergunta: str) -> None:
    with con.status("consultando o acervo…"):
        r = socratic.explicar(pergunta)
    con.print(Markdown(r["resposta"]))
    if r["fontes"]:
        # Listar tudo que foi recuperado engana: o modelo usa uma fração.
        # Mostra o que ele realmente citou; o resto vai como "consultado".
        citadas, consultadas = [], []
        for c in r["fontes"]:
            ref = c["titulo"] + (f", art. {c['artigo']}" if c.get("artigo") else "")
            marca = f"art. {c['artigo']}" if c.get("artigo") else c["titulo"]
            (citadas if marca in r["resposta"] else consultadas).append(ref)
        if citadas:
            con.print("\n[dim]citado: " + " · ".join(sorted(set(citadas))) + "[/]")
        if consultadas:
            con.print("[dim]consultado: " + " · ".join(sorted(set(consultadas))) + "[/]")


def erros() -> None:
    t = Table("tema", "disciplina", "vezes", "último", title="caderno de erros")
    for e in scheduler.caderno_erros():
        t.add_row(e["tema"], e["disciplina"], str(e["vezes"]), str(e["ultima"]))
    con.print(t)


def stats() -> None:
    t = Table("disciplina", "questões", "dominadas", "tentativas", "% acerto")
    for d in scheduler.desempenho():
        t.add_row(d["disciplina"], str(d["questoes"]), str(d["dominadas"]),
                  str(d["tentativas"]), f"{d['pct_acerto'] or 0}%")
    con.print(t)


def main() -> int:
    if len(sys.argv) < 2:
        con.print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "estudar":
        estudar()
    elif cmd == "perguntar":
        if len(sys.argv) < 3:
            con.print("uso: python chat.py perguntar \"sua pergunta\"")
            return 1
        perguntar(" ".join(sys.argv[2:]))
    elif cmd == "erros":
        erros()
    elif cmd == "stats":
        stats()
    elif cmd == "meta":
        if len(sys.argv) < 3:
            con.print("uso: python chat.py meta AAAA-MM-DD")
            return 1
        m = scheduler.meta(date.fromisoformat(sys.argv[2]))
        for k, v in m.items():
            con.print(f"{k.replace('_', ' ')}: [bold]{v}[/]")
    else:
        con.print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
