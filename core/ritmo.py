"""
Intervenção proativa — a borda com banco de `ritmo_regras.py`.

Uma sugestão só, priorizada: reincidência concreta (já sei o quê revisar)
antes de disciplina fraca (tendência, menos acionável) antes de sequência de
acertos (elogio/estímulo, o menos urgente dos três). Ver `priorizar()` em
ritmo_regras.py para o porquê de nunca mostrar mais de uma por vez.
"""
from . import db, scheduler
from .ritmo_regras import (JANELA_SEQUENCIA, priorizar, sugestao_disciplina_fraca,
                            sugestao_reincidencia, sugestao_sequencia)

VERSAO = "ritmo-v1"


def _ultimos_vereditos(limite: int = JANELA_SEQUENCIA) -> list[tuple[str, int]]:
    rows = db.query(
        "SELECT veredito, dicas_usadas FROM tentativa ORDER BY criada_em DESC LIMIT %(l)s",
        {"l": limite},
    )
    return [(r["veredito"], r["dicas_usadas"]) for r in rows]


def sugestao() -> str | None:
    return priorizar(
        sugestao_reincidencia(scheduler.caderno_erros(limite=5)),
        sugestao_disciplina_fraca(scheduler.desempenho()),
        sugestao_sequencia(_ultimos_vereditos()),
    )
