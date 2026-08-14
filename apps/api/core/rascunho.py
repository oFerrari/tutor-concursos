"""
Rascunho de edital — a área de curadoria entre "a IA leu o PDF" e "o
sistema passou a cobrar isso todo dia".

O ciclo é: sobe o PDF -> extrai pra cá (nada oficial acontece) -> a pessoa
escolhe o cargo e ajusta as disciplinas -> confirma -> vira `edital` +
`topico` de verdade e o rascunho morre.

O QUE ISSO COMPRA: a extração deixa de precisar ser perfeita. Antes, um
erro do parser (matéria engolida, cargo errado, 52 disciplinas somadas)
entrava direto na fila SM-2 e passava a gerar revisão de matéria que a
pessoa nunca vai cair na prova. Agora o erro morre na tela, antes de virar
agendamento — e o custo de estar errado é um clique, não um plano de
estudo contaminado.

Ver db/011_edital_rascunho.sql para o porquê de tabela (e não Redis).
"""
import json

from . import db, edital as edital_mod

VERSAO = "rascunho-v1"

CAMPOS = ("id, usuario_id, titulo, arquivo, data_prova, candidatos_data, "
          "estrutura, origem, criado_em, expira_em")


class ErroRascunho(Exception):
    pass


def _limpar_expirados() -> None:
    """Faxina oportunista, no caminho de escrita. Sem job agendado: o
    volume é de um registro por upload, e quem sobe um edital novo é
    exatamente quem já está pagando uma ida ao banco."""
    db.query("DELETE FROM edital_rascunho WHERE expira_em < now()")


def criar(usuario_id: int, titulo: str, texto: str, arquivo: str | None = None) -> dict:
    """
    Extrai e guarda, sem tocar em nada oficial. `origem` registra QUEM
    extraiu (parser ou LLM) porque a tela mostra isso — resultado de modelo
    merece uma conferida mais atenta que resultado de regex determinístico.
    """
    _limpar_expirados()
    estrutura, origem = edital_mod.estrutura_com_fallback(texto)
    candidatos = edital_mod.candidatos_data_prova(texto)
    data_prova = candidatos[0]["data"] if candidatos else None

    return db.exec1(
        f"""INSERT INTO edital_rascunho (usuario_id, titulo, arquivo, data_prova,
                                         candidatos_data, estrutura, origem)
            VALUES (%(u)s, %(t)s, %(a)s, %(d)s, %(c)s, %(e)s, %(o)s)
            RETURNING {CAMPOS}""",
        {"u": usuario_id, "t": titulo, "a": arquivo, "d": data_prova,
         "c": json.dumps([{**c, "data": c["data"].isoformat()} for c in candidatos[:5]]),
         "e": json.dumps(estrutura), "o": origem},
    )


def obter(usuario_id: int, rascunho_id: int) -> dict | None:
    """Escopado por usuário E por validade: rascunho de outra pessoa não
    existe (mesmo espírito de `mesa.obter`), e rascunho vencido também não
    — devolver um de três dias atrás seria pior que pedir o PDF de novo."""
    return db.exec1(
        f"""SELECT {CAMPOS} FROM edital_rascunho
             WHERE id = %(id)s AND usuario_id = %(u)s AND expira_em > now()""",
        {"id": rascunho_id, "u": usuario_id},
    )


def apagar(usuario_id: int, rascunho_id: int) -> bool:
    if not obter(usuario_id, rascunho_id):
        return False
    db.query("DELETE FROM edital_rascunho WHERE id = %(id)s AND usuario_id = %(u)s",
             {"id": rascunho_id, "u": usuario_id})
    return True


def confirmar(usuario_id: int, rascunho_id: int, mesa_id: int,
              disciplinas: list[dict], titulo: str | None = None,
              data_prova=None, orgao: str | None = None,
              banca: str | None = None) -> dict:
    """
    O "salvar de verdade": vira `edital` + `topico` na mesa e o rascunho
    morre. `disciplinas` é a lista JÁ CURADA que veio da tela
    ([{"disciplina", "topicos": [...]}]), não o que o extrator achou — se a
    pessoa apagou uma matéria ou acrescentou outra, é a versão dela que
    vale. O rascunho é insumo; a decisão é do aluno.

    Disciplina sem tópico nenhum (acrescentada na mão, "quero estudar
    Arquivologia e o edital não detalhou") entra com uma linha de tópico
    igual ao próprio nome: `mesa.disciplinas()` lê `topico`, então sem essa
    linha a matéria escolhida não entraria no recorte da mesa — seria
    escolher e não valer.
    """
    r = obter(usuario_id, rascunho_id)
    if not r:
        raise ErroRascunho("rascunho não encontrado ou expirado")
    if not disciplinas:
        raise ErroRascunho("escolha ao menos uma disciplina antes de confirmar")

    eid = db.exec1(
        """INSERT INTO edital (mesa_id, titulo, orgao, banca, data_prova, arquivo)
           VALUES (%(m)s, %(t)s, %(o)s, %(b)s, %(d)s, %(a)s) RETURNING id""",
        {"m": mesa_id, "t": (titulo or r["titulo"]).strip(), "o": orgao, "b": banca,
         "d": data_prova or r["data_prova"], "a": r["arquivo"]},
    )["id"]

    ordem = 0
    for d in disciplinas:
        nome = (d.get("disciplina") or "").strip()
        if not nome:
            continue
        for texto in (d.get("topicos") or [nome]):
            db.query(
                """INSERT INTO topico (edital_id, disciplina, ordem, texto)
                   VALUES (%(e)s, %(d)s, %(o)s, %(x)s)""",
                {"e": eid, "d": nome, "o": ordem, "x": texto},
            )
            ordem += 1

    apagar(usuario_id, rascunho_id)
    return {"edital_id": eid, "disciplinas": len(disciplinas), "topicos": ordem}
