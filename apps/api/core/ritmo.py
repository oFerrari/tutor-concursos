"""
Intervenção proativa — a borda com banco de `ritmo_regras.py`.

Uma sugestão só, priorizada: reincidência concreta (já sei o quê revisar)
antes de disciplina fraca (tendência, menos acionável) antes de sequência de
acertos (elogio/estímulo, o menos urgente dos três). Ver `priorizar()` em
ritmo_regras.py para o porquê de nunca mostrar mais de uma por vez.
"""
from . import db, mesa, scheduler
from .ritmo_regras import (ERROS_SEGUIDOS, JANELA_SEQUENCIA, priorizar,
                            sugestao_disciplina_fraca, sugestao_erros_seguidos,
                            sugestao_reincidencia, sugestao_sequencia)

VERSAO = "ritmo-v4"


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


def _ultimas_tentativas(usuario_id: int, limite: int = ERROS_SEGUIDOS,
                        disciplinas: list[str] | None = None) -> list[dict]:
    """Como `_ultimos_vereditos`, mas trazendo TEMA e DISCIPLINA junto — a
    interrupção precisa saber sobre o QUE foram os erros pra ter o que
    perguntar ao tutor. "Errou 3 seguidas" é observação; "errou 3 seguidas
    de peculato" é diagnóstico."""
    return db.query(
        f"""SELECT t.veredito, q.tema, q.disciplina
              FROM tentativa t JOIN questao q ON q.id = t.questao_id
             WHERE t.usuario_id = %(u)s AND {mesa.filtro('q.disciplina')}
             ORDER BY t.criada_em DESC, t.id DESC LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "disc": disciplinas},
    )


def intervencao(usuario_id: int, disciplinas: list[str] | None = None) -> dict | None:
    """
    A regra que manda PARAR — separada de `sugestao()` porque o produto que
    ela gera é outro: `sugestao` devolve texto pra um aviso passivo na tela,
    `intervencao` devolve texto MAIS uma pergunta pronta pro tutor, porque
    interromper sem oferecer para onde ir é só atrapalhar.

    Continua sendo REGRA e não o LLM julgando (mesma decisão do módulo): "os
    últimos 3 vereditos foram erro" é um limiar sobre número, e perguntar
    isso ao modelo a cada questão custaria cota e mudaria de sessão pra
    sessão sem ninguém pedir.
    """
    return sugestao_erros_seguidos(_ultimas_tentativas(usuario_id, disciplinas=disciplinas))


def sugestao(usuario_id: int, disciplinas: list[str] | None = None) -> str | None:
    return priorizar(
        sugestao_reincidencia(scheduler.caderno_erros(usuario_id, limite=5,
                                                      disciplinas=disciplinas)),
        sugestao_disciplina_fraca(scheduler.desempenho(usuario_id, disciplinas)),
        sugestao_sequencia(_ultimos_vereditos(usuario_id, disciplinas=disciplinas)),
    )
