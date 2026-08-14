"""
Intervenção proativa — a borda com banco de `ritmo_regras.py`.

Uma sugestão só, priorizada: reincidência concreta (já sei o quê revisar)
antes de disciplina fraca (tendência, menos acionável) antes de sequência de
acertos (elogio/estímulo, o menos urgente dos três). Ver `priorizar()` em
ritmo_regras.py para o porquê de nunca mostrar mais de uma por vez.
"""
from . import db, mesa, scheduler
from .ritmo_regras import (JANELA_SEQUENCIA, priorizar, sugestao_disciplina_fraca,
                            sugestao_reincidencia, sugestao_sequencia)

VERSAO = "ritmo-v3"


def _ultimos_vereditos(usuario_id: int, limite: int = JANELA_SEQUENCIA,
                       disciplinas: list[str] | None = None) -> list[tuple[str, int]]:
    """Recortado pela mesa, ao contrário de `scheduler.ofensiva_dias`: aqui
    o que se mede não é o hábito ("estudou hoje?"), é o desempenho recente
    NAQUILO que esta sessão cobra — elogiar uma sequência de acertos feita
    noutro concurso não diz nada sobre o que está na mesa agora."""
    rows = db.query(
        f"""SELECT t.veredito, t.dicas_usadas
              FROM tentativa t JOIN questao q ON q.id = t.questao_id
             WHERE t.usuario_id = %(u)s AND {mesa.filtro('q.disciplina')}
             ORDER BY t.criada_em DESC LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "disc": disciplinas},
    )
    return [(r["veredito"], r["dicas_usadas"]) for r in rows]


def sugestao(usuario_id: int, disciplinas: list[str] | None = None) -> str | None:
    return priorizar(
        sugestao_reincidencia(scheduler.caderno_erros(usuario_id, limite=5,
                                                      disciplinas=disciplinas)),
        sugestao_disciplina_fraca(scheduler.desempenho(usuario_id, disciplinas)),
        sugestao_sequencia(_ultimos_vereditos(usuario_id, disciplinas=disciplinas)),
    )
