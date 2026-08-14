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

Seleção de questões é amostra aleatória sobre TODO o acervo COMPARTILHADO,
não sobre a fila do dia de ninguém: a fila prioriza o que venceu PARA UM
usuário; o simulado testa o conjunto inteiro, porque é isso que a prova
real vai cobrar — por isso `selecionar()` não recebe usuario_id, só
`iniciar`/`historico` (que são posse pessoal da sessão de prova).

MULTIUSUÁRIO: `simulado` agora carrega usuario_id — funções que recebem um
`simulado_id` específico (`finalizar`, `relatorio`, `erros_do`) TAMBÉM
recebem `usuario_id` e filtram por ele, não só por confiar no id numérico.
Sem isso, adivinhar um simulado_id de outra pessoa devolveria o relatório
dela — o dado sensível aqui é resposta e desempenho, não o id em si.

Limitação conhecida: `sincronizar.py` não exporta `simulado`/`simulado_id`.
Aceitável porque simulado é snapshot de desempenho, não fonte de verdade —
o que importa (caixa, prox_revisao) já viaja pela tentativa comum.
"""
from . import db, mesa, socratic

VERSAO = "simulado-v4"

N_PADRAO = 20


def selecionar(n: int = N_PADRAO, disciplina: str | None = None,
               disciplinas: list[str] | None = None) -> list[dict]:
    """
    DOIS filtros de disciplina, que respondem a perguntas diferentes:
    `disciplina` é escolha explícita de quem pediu a prova ("simulado só de
    Penal"); `disciplinas` é o recorte da mesa (o que o edital cobra). Os
    dois valem ao mesmo tempo — pedir "só Penal" numa mesa que não cobra
    Penal devolve vazio, e isso é a resposta certa, não um bug.
    """
    return db.query(
        f"""SELECT id, disciplina, tema, enunciado, gabarito
           FROM questao q
           WHERE (%(d)s::text IS NULL OR disciplina = %(d)s)
             AND {mesa.filtro('q.disciplina')}
           ORDER BY random()
           LIMIT %(n)s""",
        {"n": n, "d": disciplina, "disc": disciplinas},
    )


def pertence_a(simulado_id: int, usuario_id: int) -> bool:
    """
    Checagem de posse ANTES de aceitar respostas — achado testando
    isolamento multiusuário: sem isso, `POST /simulados/{sid}/respostas`
    processava `sid` de QUALQUER pessoa (o id só identifica a sessão, não
    quem pode responder por ela). `scheduler.registrar` grava a tentativa
    com o usuario_id de quem chamou, então a CAIXA de ninguém vaza — mas
    a tentativa fica com o `simulado_id` alheio, e `historico()` (join só
    por simulado_id, sem usuario_id) contava essa tentativa "estrangeira"
    na nota do simulado de quem nunca pediu aquela resposta.
    """
    return db.exec1(
        "SELECT 1 FROM simulado WHERE id = %(id)s AND usuario_id = %(u)s",
        {"id": simulado_id, "u": usuario_id},
    ) is not None


def iniciar(usuario_id: int, n_questoes: int, minutos_alvo: int | None = None,
            mesa_id: int | None = None) -> int:
    """`mesa_id` é ETIQUETA, não posse — quem responde pela prova continua
    sendo `usuario_id` (é o que `pertence_a()` checa). Serve pra
    `historico()` conseguir dizer "as provas DESTA mesa"; apagar a mesa
    depois deixa o simulado com mesa_id nulo, não apaga a prova (ver a
    política de FK na migração 010)."""
    r = db.exec1(
        """INSERT INTO simulado (usuario_id, mesa_id, n_questoes, minutos_alvo)
           VALUES (%(u)s, %(mesa)s, %(n)s, %(m)s) RETURNING id""",
        {"u": usuario_id, "mesa": mesa_id, "n": n_questoes, "m": minutos_alvo},
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


def finalizar(simulado_id: int, usuario_id: int, segundos_total: int) -> dict:
    """Nota sai de GROUP BY sobre tentativa, não de contador mantido à mão.
    `WHERE ... AND usuario_id` faz dupla função: escopo E checagem de posse."""
    atualizado = db.query(
        "UPDATE simulado SET segundos_total = %(s)s WHERE id = %(id)s AND usuario_id = %(u)s",
        {"s": segundos_total, "id": simulado_id, "u": usuario_id},
    )
    r = db.exec1(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE veredito = 'correta')  AS acertos,
                  count(*) FILTER (WHERE veredito = 'parcial')  AS parciais,
                  count(*) FILTER (WHERE veredito = 'incorreta') AS erros
           FROM tentativa WHERE simulado_id = %(id)s AND usuario_id = %(u)s""",
        {"id": simulado_id, "u": usuario_id},
    ) or {"total": 0, "acertos": 0, "parciais": 0, "erros": 0}
    r["nota_pct"] = round(100.0 * r["acertos"] / r["total"], 1) if r["total"] else 0.0
    return r


def relatorio(simulado_id: int, usuario_id: int) -> list[dict]:
    """Desempenho por disciplina DENTRO deste simulado — não é a v_desempenho global."""
    return db.query(
        """SELECT q.disciplina,
                  count(*)                                          AS questoes,
                  count(*) FILTER (WHERE t.veredito = 'correta')     AS acertos,
                  round(100.0 * count(*) FILTER (WHERE t.veredito = 'correta')
                        / count(*), 1)::float8                       AS pct
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.simulado_id = %(id)s AND t.usuario_id = %(u)s
           GROUP BY q.disciplina ORDER BY pct""",
        {"id": simulado_id, "u": usuario_id},
    )


def erros_do(simulado_id: int, usuario_id: int) -> list[dict]:
    """Questões erradas ou parciais, para a revisão final — com resposta dada e gabarito."""
    return db.query(
        """SELECT q.tema, q.enunciado, q.gabarito, t.resposta, t.veredito
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.simulado_id = %(id)s AND t.usuario_id = %(u)s AND t.veredito <> 'correta'
           ORDER BY t.id""",
        {"id": simulado_id, "u": usuario_id},
    )


def historico(usuario_id: int, limite: int = 10, mesa_id: int | None = None) -> list[dict]:
    """`mesa_id=None` devolve o histórico inteiro da conta (é o que a CLI e
    as versões anteriores à 010 faziam). Com mesa, só as provas etiquetadas
    com ela — as de mesa apagada (mesa_id nulo) somem da visão filtrada mas
    continuam existindo na visão geral, que é o ponto de terem sobrevivido."""
    return db.query(
        """SELECT s.id, s.n_questoes, s.minutos_alvo, s.segundos_total, s.criado_em,
                  count(t.id) FILTER (WHERE t.veredito = 'correta') AS acertos,
                  count(t.id)                                       AS respondidas,
                  round(100.0 * count(t.id) FILTER (WHERE t.veredito = 'correta')
                        / NULLIF(count(t.id), 0), 1)::float8        AS nota_pct
           -- t.usuario_id = s.usuario_id além de t.simulado_id = s.id: defesa em
           -- profundidade contra a mesma classe de bug que motivou pertence_a()
           -- acima — se algum dia outra rota inserir tentativa com simulado_id
           -- alheio de novo, ela ainda não entra na nota de quem não pediu.
           FROM simulado s LEFT JOIN tentativa t ON t.simulado_id = s.id AND t.usuario_id = s.usuario_id
           WHERE s.usuario_id = %(u)s
             AND (%(mesa)s::bigint IS NULL OR s.mesa_id = %(mesa)s)
           GROUP BY s.id ORDER BY s.criado_em DESC LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "mesa": mesa_id},
    )
