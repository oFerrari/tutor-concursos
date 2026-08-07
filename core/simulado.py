"""
Simulado — sessão sob condição de prova.

Diferença deliberada em relação a `estudar` (chat.py): aqui não há dica, não
há diálogo socrático questão a questão, e o gabarito só aparece na revisão
final. É a mesma diferença entre treino e prova — dar andaime durante a
prova mede a ajuda, não o aluno.

Reaproveita `scheduler.registrar`: acerto num simulado É acerto, e deve
alimentar a caixa e o caderno de erros como qualquer outro. Como aqui nunca
há dica, `dicas_usadas` é sempre 0, então todo acerto promove — não é um
caso especial, é a mesma regra de sempre vendo o mesmo sinal limpo.

Seleção de questões é amostra aleatória sobre TODO o acervo, não sobre a
fila do dia: a fila prioriza o que venceu; o simulado testa o conjunto
inteiro, porque é isso que a prova real vai cobrar. `ORDER BY random()`
sobre a tabela já produz proporção por disciplina de graça — não precisa de
GROUP BY para "estratificar".

Limitação conhecida: `sincronizar.py` não exporta `simulado`/`simulado_id`.
Aceitável porque simulado é snapshot de desempenho, não fonte de verdade —
o que importa (caixa, prox_revisao) já viaja pela tentativa comum.
"""
from . import db, socratic

VERSAO = "simulado-v2"

N_PADRAO = 20


def selecionar(n: int = N_PADRAO, disciplina: str | None = None) -> list[dict]:
    return db.query(
        """SELECT id, disciplina, tema, enunciado, gabarito
           FROM questao
           WHERE %(d)s::text IS NULL OR disciplina = %(d)s
           ORDER BY random()
           LIMIT %(n)s""",
        {"n": n, "d": disciplina},
    )


def iniciar(n_questoes: int, minutos_alvo: int | None = None) -> int:
    r = db.exec1(
        """INSERT INTO simulado (n_questoes, minutos_alvo) VALUES (%(n)s, %(m)s)
           RETURNING id""",
        {"n": n_questoes, "m": minutos_alvo},
    )
    return r["id"]


def corrigir(questao: dict, resposta: str) -> dict:
    """
    Correção única, sem histórico e sem segunda chance — é assim que sai
    numa prova real. Resposta em branco nem vai ao LLM: é erro por definição.
    """
    if not resposta.strip():
        return {"veredito": "incorreta", "comentario": "(em branco)",
                "pergunta": "", "conceito_faltante": ""}
    return socratic.avaliar(questao["enunciado"], questao["gabarito"], resposta, nivel=0)


def finalizar(simulado_id: int, segundos_total: int) -> dict:
    """Nota sai de GROUP BY sobre tentativa, não de contador mantido à mão."""
    db.query(
        "UPDATE simulado SET segundos_total = %(s)s WHERE id = %(id)s",
        {"s": segundos_total, "id": simulado_id},
    )
    r = db.exec1(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE veredito = 'correta')  AS acertos,
                  count(*) FILTER (WHERE veredito = 'parcial')  AS parciais,
                  count(*) FILTER (WHERE veredito = 'incorreta') AS erros
           FROM tentativa WHERE simulado_id = %(id)s""",
        {"id": simulado_id},
    ) or {"total": 0, "acertos": 0, "parciais": 0, "erros": 0}
    r["nota_pct"] = round(100.0 * r["acertos"] / r["total"], 1) if r["total"] else 0.0
    return r


def relatorio(simulado_id: int) -> list[dict]:
    """Desempenho por disciplina DENTRO deste simulado — não é a v_desempenho global."""
    return db.query(
        """SELECT q.disciplina,
                  count(*)                                          AS questoes,
                  count(*) FILTER (WHERE t.veredito = 'correta')     AS acertos,
                  round(100.0 * count(*) FILTER (WHERE t.veredito = 'correta')
                        / count(*), 1)::float8                       AS pct
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.simulado_id = %(id)s
           GROUP BY q.disciplina ORDER BY pct""",
        {"id": simulado_id},
    )


def erros_do(simulado_id: int) -> list[dict]:
    """Questões erradas ou parciais, para a revisão final — com resposta dada e gabarito."""
    return db.query(
        """SELECT q.tema, q.enunciado, q.gabarito, t.resposta, t.veredito
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.simulado_id = %(id)s AND t.veredito <> 'correta'
           ORDER BY t.id""",
        {"id": simulado_id},
    )


def historico(limite: int = 10) -> list[dict]:
    return db.query(
        """SELECT s.id, s.n_questoes, s.minutos_alvo, s.segundos_total, s.criado_em,
                  count(t.id) FILTER (WHERE t.veredito = 'correta') AS acertos,
                  count(t.id)                                       AS respondidas,
                  round(100.0 * count(t.id) FILTER (WHERE t.veredito = 'correta')
                        / NULLIF(count(t.id), 0), 1)::float8        AS nota_pct
           FROM simulado s LEFT JOIN tentativa t ON t.simulado_id = s.id
           GROUP BY s.id ORDER BY s.criado_em DESC LIMIT %(l)s""",
        {"l": limite},
    )
