"""
Acesso direto ao banco de questões — compartilhado entre usuários, sem
usuario_id (a questão em si não pertence a ninguém; progresso é que é
pessoal, e mora em `progresso`/`tentativa`).

Extraído como módulo próprio porque `api.py` precisa buscar uma questão
por id fora do contexto de fila/simulado/desafio (rota de diálogo turno a
turno), e nenhum módulo existente já tinha essa consulta simples pronta.
"""
from . import db

VERSAO = "questoes-v3"

CAMPOS = ("id, disciplina, tema, enunciado, gabarito, dicas, tipo, gabarito_ce, "
          "contexto_id, ordem_no_contexto")

# O texto-base vem JUNTO da questão, por LEFT JOIN, e não numa segunda
# chamada: item C/E de série é ilegível sem ele ("com base no argumento
# acima"), então buscar os dois separado só criaria um instante em que a
# tela tem a assertiva e não tem o enunciado — e uma rota a mais pra
# esquecer de chamar.
CAMPOS_COM_CONTEXTO = ("q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.dicas, "
                       "q.tipo, q.gabarito_ce, q.contexto_id, q.ordem_no_contexto, "
                       "x.texto AS contexto")
JOIN_CONTEXTO = "LEFT JOIN contexto x ON x.id = q.contexto_id"


def obter(questao_id: int) -> dict | None:
    return db.exec1(
        f"SELECT {CAMPOS_COM_CONTEXTO} FROM questao q {JOIN_CONTEXTO} WHERE q.id = %(id)s",
        {"id": questao_id})


def obter_varias(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.query(
        f"SELECT {CAMPOS_COM_CONTEXTO} FROM questao q {JOIN_CONTEXTO} WHERE q.id = ANY(%(ids)s)",
        {"ids": ids})
    return {r["id"]: r for r in rows}


def obter_com_progresso(usuario_id: int, questao_id: int) -> dict | None:
    """Como `obter()`, mas com caixa/prox_revisao DESTE usuário anexados —
    mesmo default de `scheduler.fila()` pra questão nunca tentada (caixa 0,
    hoje). Usado pela tela de responder, que precisa mostrar a caixa atual
    mesmo quando chega direto (refresh), sem vir da lista da fila."""
    return db.exec1(
        f"""SELECT {CAMPOS_COM_CONTEXTO}, COALESCE(p.caixa, 0) AS caixa,
                  COALESCE(p.prox_revisao, CURRENT_DATE) AS prox_revisao
           FROM questao q
           {JOIN_CONTEXTO}
           LEFT JOIN progresso p ON p.usuario_id = %(u)s AND p.questao_id = q.id
           WHERE q.id = %(id)s""",
        {"u": usuario_id, "id": questao_id},
    )
