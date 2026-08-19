#!/usr/bin/env python3
"""
Sessão de estudo no terminal.

    python chat.py estudar          # fila de revisão do dia, modo socrático
    python chat.py desafio          # meta do dia: pontos fracos + novas + mini-simulado
    python chat.py simulado [N] [minutos]   # prova: sem dica, corrige no final
    python chat.py simulados        # histórico de simulados feitos
    python chat.py perguntar "diferença entre dolo eventual e culpa consciente"
    python chat.py erros
    python chat.py stats            # barras no terminal
    python chat.py stats --json     # mesmo dado, formato que a futura API vai servir
    python chat.py meta                # usa a data do edital ingerido (python edital.py)
    python chat.py meta 2026-11-15     # data manual, sempre vence a do edital
    python chat.py estudar --mesa "PF Agente"   # recorta pelo edital daquela mesa

Provar o loop aqui antes de escrever uma linha de Next.js. Se a tutoria
funciona sem interface, o frontend é só apresentação.

MULTIUSUÁRIO: a CLI não faz login — resolve (ou cria) UM usuário fixo pelo
email de `CLI_USUARIO_EMAIL` no .env (default: estudante@local, o mesmo
semeado pela migração 008). Login de verdade com senha só existe pelo
caminho da API (api.py), pra quem for usar o frontend.

MESA (migração 010): `--mesa NOME` vale para qualquer comando e recorta a
sessão pelas disciplinas do edital daquela mesa. Sem a flag, usa a mesa
padrão da conta (a mais antiga, criada na hora se não houver nenhuma) — e
mesa sem edital não filtra nada, ou seja, o comportamento é o mesmo de
antes da 010 pra quem nunca criou mesa.
"""
import json
import sys
import time
from datetime import date

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from core import auth, desafio as desafio_mod
from core import llm, mesa as mesa_mod, ritmo, scheduler, simulado as simulado_mod, socratic
from core.config import CLI_USUARIO_EMAIL

VERSAO = "chat-v21"
con = Console()
MAX_DICAS = 3

# Preenchido por _extrair_flag_mesa() antes do dispatch — a flag é removida
# de sys.argv ali mesmo porque `simulado [N] [minutos]` lê posicional, e um
# "--mesa" sobrando no meio viraria int("--mesa").
_MESA_NOME: str | None = None


def _usuario_id() -> int:
    return auth.usuario_da_cli(CLI_USUARIO_EMAIL)


def _extrair_flag_mesa() -> None:
    global _MESA_NOME
    if "--mesa" not in sys.argv:
        return
    i = sys.argv.index("--mesa")
    _MESA_NOME = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    del sys.argv[i:i + 2]


def _mesa(uid: int) -> dict:
    """Mesa da sessão, com as disciplinas já resolvidas. Nome que não existe
    é ERRO, não fallback silencioso pra padrão: escrever "PF Agente" quando a
    mesa se chama "PF - Agente" e receber a fila de outro concurso sem aviso
    é exatamente o tipo de falha calada que este projeto evita em outros
    lugares (ver `--norma` explícito em reingest.py)."""
    if not _MESA_NOME:
        return mesa_mod.contexto(uid)
    achada = next((m for m in mesa_mod.listar(uid)
                   if m["nome"].lower() == _MESA_NOME.lower()), None)
    if not achada:
        nomes = ", ".join(f'"{m["nome"]}"' for m in mesa_mod.listar(uid)) or "(nenhuma)"
        con.print(f'[red]mesa "{_MESA_NOME}" não existe.[/] suas mesas: {nomes}')
        sys.exit(1)
    return mesa_mod.contexto(uid, achada["id"])


def _cabecalho_mesa(m: dict) -> None:
    """Diz em qual recorte a sessão está rodando. Sem isso, "0 questões na
    fila" numa mesa filtrada é indistinguível de "acabou o acervo"."""
    disc = m.get("disciplinas")
    escopo = ", ".join(disc) if disc else "sem edital — acervo inteiro"
    con.print(f"[dim]mesa: {m['nome']} · {escopo}[/]")


def _dicas(q) -> list[str]:
    d = q["dicas"]
    return json.loads(d) if isinstance(d, str) else (d or [])


MAX_TENTATIVAS = 3      # respostas erradas antes de revelar o gabarito


def estudar() -> None:
    uid = _usuario_id()
    m = _mesa(uid)
    _cabecalho_mesa(m)
    pendentes = scheduler.fila(uid, disciplinas=m["disciplinas"])
    if not pendentes:
        con.print("[green]Nada pendente hoje.[/] Ingira material novo ou volte amanhã.")
        return

    c = scheduler.carga_hoje(uid, m["disciplinas"])
    con.print(f"[bold]{len(pendentes)}[/] questões na fila · "
              f"{c['revisoes']} revisões venceram, {c['ineditas']} inéditas"
              + (f" · [yellow]{c['atraso']} de atraso[/]" if c["atraso"] else "") + "\n")
    _mostrar_sugestao(uid, m["disciplinas"])

    _estudar_lista(uid, pendentes)


def _mostrar_sugestao(uid: int, disciplinas: list[str] | None = None) -> None:
    """
    Intervenção proativa: no máximo UMA sugestão, antes de começar a
    resolver. `core.ritmo` decide o quê (regra, não LLM — ver o porquê em
    ritmo_regras.py); aqui só é exibição.
    """
    dica = ritmo.sugestao(uid, disciplinas)
    if dica:
        con.print(f"[cyan]💡 {dica}[/]\n")


def _estudar_lista(uid: int, pendentes: list) -> bool:
    """
    Loop socrático questão a questão, extraído de `estudar()` para ser
    reaproveitado por `desafio()` — mesmo modo de estudo, lista diferente de
    onde tirar as questões (fila do dia vs. composição do desafio).

    Devolve True se o usuário pediu para SAIR no meio — `desafio()` precisa
    saber disso para não emendar o próximo bloco depois que a pessoa já
    disse que queria parar.
    """
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
        # O conceito que a última correção apontou como faltando (022).
        # Lido por `fechar()` como closure, igual `ultima_resposta`: quem sabe
        # o que faltou é o avaliador, e quem grava é o fechamento.
        ultimo_conceito = None
        historico = []          # turnos desta questão, para o avaliador seguir o fio
        avisou_contrato = False

        def fechar(v):
            # PENALIDADE = errar, não receber dica. Como a dica vem automática
            # ao errar, as duas coisas andam juntas: usar ambas para penalizar
            # contaria a mesma falha duas vezes. Dica pedida por iniciativa
            # própria conta, porque aí é ajuda escolhida.
            penalidade = erradas + dicas_pedidas
            r = scheduler.registrar(uid, q["id"], v, ultima_resposta, penalidade,
                                    int(time.monotonic() - inicio),
                                    conceito_faltante=ultimo_conceito)
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
                    return True
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
                    # Dispatcher, não `avaliar()`: item C/E é corrigido em
                    # código. A CLI seguia chamando o LLM direto e compararia
                    # "C" contra a justificativa em prosa — errado e pago.
                    av = socratic.avaliar_questao(q, resposta, erradas, historico)
                    ultimo_conceito = av.get("conceito_faltante") or ultimo_conceito
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
    return False


def simulado(n: int = simulado_mod.N_PADRAO, minutos: int | None = None,
             questoes: list | None = None) -> None:
    """
    `questoes` pronta (vinda de `desafio()`) pula a seleção aleatória —
    quem decidiu quais entram já foi `core.desafio.montar()`. Sem isso, o
    bloco de mini-simulado do desafio ia reamostrar o acervo todo de novo,
    podendo repetir questão que já caiu em reincidentes/novas no mesmo dia.
    """
    uid = _usuario_id()
    m = _mesa(uid)
    if questoes is None:
        _cabecalho_mesa(m)
        questoes = simulado_mod.selecionar(n, disciplinas=m["disciplinas"])
        if len(questoes) < n:
            con.print(f"[dim]só há {len(questoes)} questões no recorte desta mesa; "
                      f"simulado sai menor.[/]")
    if not questoes:
        con.print("[yellow]Nenhuma questão no acervo ainda.[/]")
        return

    sid = simulado_mod.iniciar(uid, len(questoes), minutos, m["id"])
    con.print(Panel(
        f"{len(questoes)} questões" + (f" · meta de {minutos} min" if minutos else "") +
        " · sem dica, sem correção durante a prova — gabarito só no final.",
        title="simulado", border_style="magenta"))

    respondidas = []   # (questao, resposta, segundos)
    inicio_total = time.monotonic()
    for i, q in enumerate(questoes, 1):
        con.print(Panel(q["enunciado"], title=f"{i}/{len(questoes)} · {q['disciplina']}",
                        border_style="blue"))
        t0 = time.monotonic()
        try:
            resposta = con.input("\n[bold cyan]resposta[/] [dim]('pular', 'sair')[/]: ").strip()
        except (EOFError, KeyboardInterrupt):
            resposta = "sair"
        segundos = int(time.monotonic() - t0)
        if resposta == "sair":
            con.print("[dim]simulado interrompido; corrigindo o que já foi respondido.[/]")
            break
        respondidas.append((q, "" if resposta == "pular" else resposta, segundos))

    if not respondidas:
        con.print("[dim]nada respondido; simulado descartado.[/]")
        return

    segundos_total = int(time.monotonic() - inicio_total)
    with con.status("corrigindo…"):
        pendentes = []
        for q, resposta, segundos in respondidas:
            try:
                av = simulado_mod.corrigir(q, resposta)
            except llm.ErroLLM as e:
                con.print(f"[red]LLM indisponível ao corrigir \"{q['tema']}\":[/] {e}")
                continue
            scheduler.registrar(uid, q["id"], av["veredito"], resposta, 0, segundos,
                                simulado_id=sid,
                                conceito_faltante=av.get("conceito_faltante"))
            if av["veredito"] != "correta":
                pendentes.append((q, resposta, av))

    r = simulado_mod.finalizar(sid, uid, segundos_total)
    mm, ss = segundos_total // 60, segundos_total % 60
    con.print(Panel(
        f"{r['acertos']}/{r['total']} corretas ([bold]{r['nota_pct']}%[/]) · "
        f"{r['parciais']} parciais · {r['erros']} erradas · {mm}min{ss:02d}s",
        title="resultado", border_style="green"))

    t = Table("disciplina", "questões", "acertos", "% acerto")
    for d in simulado_mod.relatorio(sid, uid):
        t.add_row(d["disciplina"], str(d["questoes"]), str(d["acertos"]), f"{d['pct']}%")
    con.print(t)

    if pendentes:
        con.print("\n[bold]revisão[/]")
        for q, resposta, av in pendentes:
            con.print(Panel(
                f"[dim]sua resposta:[/] {resposta or '(em branco)'}\n"
                f"[green]gabarito:[/] {q['gabarito']}",
                title=f"{q['tema']} · {av['veredito']}", border_style="yellow"))


def desafio(n_reincidentes: int = 3, n_novas: int = 5, n_simulado: int = 5) -> None:
    """
    Meta do dia em três blocos — mesma ordem de prioridade da fila normal
    (pontos fracos primeiro), mas do tamanho de uma sessão, com tempo
    estimado a partir do histórico real de `tentativa.segundos`.
    """
    uid = _usuario_id()
    m = _mesa(uid)
    _cabecalho_mesa(m)
    plano = desafio_mod.montar(uid, n_reincidentes, n_novas, n_simulado, m["disciplinas"])
    if plano["total_questoes"] == 0:
        con.print("[yellow]Nada para compor um desafio ainda — "
                  "ingira material ou responda algumas questões primeiro.[/]")
        return

    con.print(Panel(
        f"{len(plano['reincidentes'])} pontos fracos · {len(plano['novas'])} novas · "
        f"{len(plano['mini_simulado'])} mini-simulado · "
        f"~{plano['estimativa_minutos']} min estimados",
        title="desafio de hoje", border_style="magenta"))
    _mostrar_sugestao(uid, m["disciplinas"])

    if plano["reincidentes"]:
        con.print("\n[bold]bloco 1 — pontos fracos[/]")
        if _estudar_lista(uid, plano["reincidentes"]):
            return   # usuário pediu "sair" — não emenda o próximo bloco

    if plano["novas"]:
        con.print("\n[bold]bloco 2 — questões novas[/]")
        if _estudar_lista(uid, plano["novas"]):
            return

    if plano["mini_simulado"]:
        con.print("\n[bold]bloco 3 — mini-simulado[/]")
        simulado(len(plano["mini_simulado"]), questoes=plano["mini_simulado"])


def simulados() -> None:
    uid = _usuario_id()
    hist = simulado_mod.historico(uid, mesa_id=_mesa(uid)["id"])
    if not hist:
        con.print("[dim]nenhum simulado ainda. 'python chat.py simulado' para começar.[/]")
        return
    t = Table("data", "questões", "respondidas", "nota", title="histórico de simulados")
    for s in hist:
        t.add_row(str(s["criado_em"].date()), str(s["n_questoes"]), str(s["respondidas"]),
                  f"{s['nota_pct'] or 0}%")
    con.print(t)


def perguntar(pergunta: str) -> None:
    uid = _usuario_id()
    with con.status("consultando o acervo…"):
        r = socratic.explicar(pergunta, uid, _mesa(uid)["disciplinas"])
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
    uid = _usuario_id()
    t = Table("tema", "disciplina", "vezes", "último", title="caderno de erros")
    for e in scheduler.caderno_erros(uid, disciplinas=_mesa(uid)["disciplinas"]):
        t.add_row(e["tema"], e["disciplina"], str(e["vezes"]), str(e["ultima"]))
    con.print(t)


def _barra(pct: float | None, largura: int = 20) -> str:
    pct = max(0.0, min(100.0, pct or 0.0))
    preenchido = round(largura * pct / 100)
    return "█" * preenchido + "░" * (largura - preenchido)


def stats(como_json: bool = False) -> None:
    uid = _usuario_id()
    dados = scheduler.desempenho(uid, _mesa(uid)["disciplinas"])
    if como_json:
        # Mesma função que vai virar endpoint um dia — testar o JSON aqui
        # agora é testar o contrato exato que o frontend vai receber depois.
        # float8 na view garante que isto não precisa de serializer customizado.
        print(json.dumps(dados, ensure_ascii=False, indent=1))
        return
    if not dados:
        con.print("[dim]sem questões ainda.[/]")
        return

    largura_nome = max(len(d["disciplina"]) for d in dados)
    for d in dados:
        pct = d["pct_acerto"] or 0.0
        con.print(f"{d['disciplina']:<{largura_nome}}  {_barra(pct)}  {pct:>5.1f}% acerto")
    con.print()

    t = Table("disciplina", "questões", "dominadas", "% cobertura", "tentativas", "% acerto")
    for d in dados:
        t.add_row(d["disciplina"], str(d["questoes"]), str(d["dominadas"]),
                  f"{d['cobertura_pct'] or 0}%", str(d["tentativas"]), f"{d['pct_acerto'] or 0}%")
    con.print(t)


def main() -> int:
    _extrair_flag_mesa()
    if len(sys.argv) < 2:
        con.print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "estudar":
        estudar()
    elif cmd == "desafio":
        desafio()
    elif cmd == "simulado":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else simulado_mod.N_PADRAO
        minutos = int(sys.argv[3]) if len(sys.argv) > 3 else None
        simulado(n, minutos)
    elif cmd == "simulados":
        simulados()
    elif cmd == "perguntar":
        if len(sys.argv) < 3:
            con.print("uso: python chat.py perguntar \"sua pergunta\"")
            return 1
        perguntar(" ".join(sys.argv[2:]))
    elif cmd == "erros":
        erros()
    elif cmd == "stats":
        stats(como_json="--json" in sys.argv[2:])
    elif cmd == "meta":
        # sem data: usa o edital mais recente ingerido (python edital.py).
        # com data: sempre vence a automática — saída de emergência se a
        # extração do PDF errou o dia da prova.
        data = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
        uid = _usuario_id()
        mesa_ctx = _mesa(uid)
        _cabecalho_mesa(mesa_ctx)
        m = scheduler.meta(uid, data, mesa_ctx["id"], mesa_ctx["disciplinas"])
        for k, v in m.items():
            if isinstance(v, dict):
                con.print(f"{k.replace('_', ' ')}:")
                for k2, v2 in v.items():
                    con.print(f"  {k2.replace('_', ' ')}: [bold]{v2}[/]")
            else:
                con.print(f"{k.replace('_', ' ')}: [bold]{v}[/]")
    else:
        con.print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
