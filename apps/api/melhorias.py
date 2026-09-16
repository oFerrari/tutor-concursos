"""
A FILA DE MELHORIA VIRA UM ARQUIVO PRONTO PRA ENTREGAR (029).

`/erro` e `/feedback` gravam o bilhete preso à resposta comentada. Isto aqui é
a outra ponta: transformar a fila num texto que um agente de IA leia e conserte,
sem ninguém ter que abrir o banco, achar a conversa, copiar a resposta e montar
o contexto à mão — que é exatamente o trabalho que o comando existe pra matar.

O MOLDE É O `.logs/defeitos.md`, e a cópia é deliberada: nome FIXO, para que
"conserta o que está em .logs/melhorias.md" não dependa de ninguém copiar um
timestamp da tela. O que muda é a origem — lá é o avaliador sintético, aqui é o
aluno de verdade reclamando no meio do estudo.

CADA ITEM LEVA A CONVERSA EM VOLTA, não só o bilhete. "Ele respondeu errado
sobre princípios" não se conserta; a resposta literal, com as fontes daquele
turno e os turnos anteriores, se conserta. É o mesmo princípio da proveniência
de questão: sem origem, o relato não é reproduzível.
"""
import argparse
import sys
from pathlib import Path

from core import db, melhoria

VERSAO = "melhorias-v1"

# Quantos turnos ANTES da resposta reclamada entram no arquivo. Quatro porque a
# reclamação quase sempre é sobre o rumo da conversa ("de novo a mesma
# pergunta", "não era isso que eu pedi"), e rumo não se lê num turno só.
TURNOS_DE_CONTEXTO = 4

ARQUIVO = "melhorias.md"


def _contexto(conversa_id: int, ate_mensagem: int | None) -> list[dict]:
    """Os últimos turnos até a resposta comentada, inclusive.

    `ate_mensagem=None` (feedback sem alvo) devolve o fim da conversa: é o que
    existe, e é melhor que nada."""
    return list(reversed(db.query(
        """SELECT autor, texto, fontes, criada_em
             FROM mensagem
            WHERE conversa_id = %(c)s
              AND (%(m)s::bigint IS NULL OR id <= %(m)s)
            ORDER BY id DESC
            LIMIT %(n)s""",
        {"c": conversa_id, "m": ate_mensagem, "n": TURNOS_DE_CONTEXTO * 2 + 1})))


def _fontes(valor) -> str:
    if not valor:
        return "— (nenhuma fonte recuperada neste turno)"
    return ", ".join(
        f"{f.get('titulo')}" + (f", art. {f['artigo']}" if f.get("artigo") else "")
        for f in valor)


def montar(limite: int) -> tuple[str, int]:
    itens = melhoria.pendentes(limite)
    if not itens:
        return "", 0

    linhas = [
        "# melhorias pedidas pelo aluno — fila de `/erro` e `/feedback` (029)",
        "",
        "Cada item é uma reclamação feita DENTRO do chat, com a resposta que ela",
        "comenta e os turnos anteriores. O ponteiro do defeito é o próprio texto do",
        "aluno; o contexto está aqui pra que ele seja reproduzível.",
        "",
        "**Depois de consertar**, feche os itens pelo id:",
        "",
        "```bash",
        f"./melhorias.sh --fechar {' '.join(str(i['id']) for i in itens[:3])}",
        "```",
        "",
        f"- versões: `{VERSAO}` · melhoria `{melhoria.VERSAO}`",
        f"- {len(itens)} item(ns) pendente(s)",
        "",
    ]
    for item in itens:
        linhas += [
            "---",
            "",
            f"## #{item['id']} — {item['criado_em']:%d/%m %H:%M}",
            "",
            f"**O aluno escreveu:** {item['feedback_texto']}",
            "",
            f"- conversa: {item['conversa_titulo']} (id {item['conversa_id']})",
        ]
        if item["resposta_do_tutor"] is None:
            linhas += ["- sem resposta do tutor presa a este item "
                       "(reclamação antes do primeiro turno)", ""]
        else:
            linhas += [f"- fontes daquele turno: {_fontes(item['fontes_do_turno'])}", ""]
        linhas += ["**A conversa até ali:**", ""]
        # ATÉ A MENSAGEM COMENTADA, não até o fim da conversa: o item #12
        # mostrava turnos POSTERIORES à resposta reclamada, e quem lê precisa
        # ver o que o tutor tinha na frente quando errou — não o que veio
        # depois, que já é consequência.
        for m in _contexto(item["conversa_id"], item["mensagem_tutor_id"]):
            quem = {"aluno": "ALUNO", "tutor": "TUTOR"}.get(m["autor"], m["autor"].upper())
            texto = " ".join((m["texto"] or "").split())
            linhas.append(f"> **{quem}:** {texto}")
            linhas.append(">")
        linhas.append("")
    return "\n".join(linhas), len(itens)


def fechar(ids: list[int]) -> int:
    """Tira da fila o que já foi consertado.

    `status` vira 'resolvido' em vez de a linha ser apagada: a fila é o
    histórico do que o produto errou, e apagar isso jogaria fora a única série
    temporal de reclamação real que o projeto tem."""
    linhas = db.query(
        "UPDATE fila_melhoria SET status='resolvido' "
        " WHERE id = ANY(%(i)s) AND status='pendente' RETURNING id",
        {"i": ids})
    return len(linhas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limite", type=int, default=50)
    ap.add_argument("--fechar", type=int, nargs="+", metavar="ID",
                    help="marca estes itens como resolvidos e sai")
    a = ap.parse_args()

    if a.fechar:
        print(f"{fechar(a.fechar)} item(ns) fechado(s).")
        return 0

    texto, n = montar(a.limite)
    destino = Path(__file__).resolve().parents[2] / ".logs" / ARQUIVO
    if not n:
        # A AUSÊNCIA DO ARQUIVO É O SINAL DE LIMPO, igual ao defeitos.md: um
        # arquivo antigo dizendo "3 pendentes" é pior que arquivo nenhum.
        destino.unlink(missing_ok=True)
        print("fila vazia — nada pendente.")
        return 0
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"{n} item(ns) em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
