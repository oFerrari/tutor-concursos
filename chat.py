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

VERSAO = "chat-v21"
con = Console()
MAX_DICAS = 3


def _dicas(q) -> list[str]:
    d = q["dicas"]
    return json.loads(d) if isinstance(d, str) else (d or [])


MAX_TENTATIVAS = 3      # respostas erradas antes de revelar o gabarito


def estudar() -> None:
    pendentes = scheduler.fila()
    if not pendentes:
        con.print("[green]Nada pendente hoje.[/] Ingira material novo ou volte amanhã.")
        return

    c = scheduler.carga_hoje()
    con.print(f"[bold]{len(pendentes)}[/] questões na fila · "
              f"{c['revisoes']} revisões venceram, {c['ineditas']} inéditas"
              + (f" · [yellow]{c['atraso']} de atraso[/]" if c["atraso"] else "") + "\n")

    for q in pendentes:
        dicas = _dicas(q)
        con.print(Panel(q["enunciado"],
                        title=f"{q['disciplina']} · {q['tema']}",
                        subtitle=f"caixa {q['caixa']}", border_style="blue"))

        # DOIS ORÇAMENTOS SEPARADOS. Antes uma única variável contava dicas,
        # tentativas e penalidade ao mesmo tempo: pedir dica gastava tentativa,
        # e errar consumia dica automaticamente — o que dava dicas_usadas>0 a
        # quem nunca pediu dica e bloqueava a promoção em silêncio.
        dicas_mostradas = 0    # ponteiro da próxima dica a exibir
        dicas_pedidas = 0      # dicas que VOCÊ pediu, antes de responder
        erradas = 0
        inicio = time.monotonic()
        veredito, ultima_resposta = None, ""
        historico = []          # turnos desta questão, para o avaliador seguir o fio
        avisou_contrato = False

        def fechar(v):
            # PENALIDADE = errar, não receber dica. Como a dica vem automática
            # ao errar, as duas coisas andam juntas: usar ambas para penalizar
            # contaria a mesma falha duas vezes. Dica pedida por iniciativa
            # própria conta, porque aí é ajuda escolhida.
            penalidade = erradas + dicas_pedidas
            r = scheduler.registrar(q["id"], v, ultima_resposta, penalidade,
                                    int(time.monotonic() - inicio))
            motivo = ("acertou de primeira" if v == "correta" and penalidade == 0 else
                      f"{erradas} erro(s), {dicas_pedidas} dica(s) pedida(s)")
            con.print(f"[dim]{v} · {motivo} · caixa {r['caixa']} · "
                      f"volta em {r['prox_revisao']}[/]\n")

        while True:
            rest_d = min(MAX_DICAS, len(dicas)) - dicas_mostradas
            try:
                resposta = con.input(
                    f"\n[bold cyan]resposta[/] [dim](tentativa {erradas + 1} de "
                    f"{MAX_TENTATIVAS} · {rest_d} dica(s) disponível(is) · "
                    f"'dica', 'pular', 'sair')[/]: ").strip()
            except (EOFError, KeyboardInterrupt):
                resposta = "sair"

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
                if rest_d > 0:
                    con.print(f"[yellow]dica {dicas_mostradas + 1}:[/] {dicas[dicas_mostradas]}")
                    dicas_mostradas += 1
                    dicas_pedidas += 1
                else:
                    con.print("[yellow]as dicas acabaram. Tente formular o que você lembra.[/]")
                continue
            if not resposta:
                continue

            ultima_resposta = resposta
            with con.status("corrigindo…"):
                try:
                    av = socratic.avaliar(q["enunciado"], q["gabarito"], resposta,
                                          erradas, historico)
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

            erradas += 1
            historico.append({"resposta": resposta, "comentario": av["comentario"],
                              "pergunta": av["pergunta"]})
            con.print(f"[yellow]{av['comentario']}[/]")
            if av["pergunta"]:
                con.print(f"[cyan]→ {av['pergunta']}[/]")
                if not avisou_contrato:
                    # A pergunta-guia parece ser a nova questão, mas a avaliação
                    # continua sendo contra o enunciado do quadro. Dizer isso uma
                    # vez evita o aluno responder a coisa errada e ser punido.
                    con.print("[dim]  (é uma pista; sua resposta continua valendo "
                              "para a questão do quadro)[/]")
                    avisou_contrato = True
            # Dica automática a cada erro: errar já é a penalidade, então
            # entregar a pista de graça não cobra nada a mais.
            if dicas_mostradas < min(MAX_DICAS, len(dicas)):
                con.print(f"[dim]dica {dicas_mostradas + 1}: {dicas[dicas_mostradas]}[/]")
                dicas_mostradas += 1
            if erradas >= MAX_TENTATIVAS:
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
