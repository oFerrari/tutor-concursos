"""
Desafio diário — meta automática que mescla três blocos numa sessão só:

1. REINCIDENTES — pontos fracos do caderno de erros, os que mais voltam.
2. NOVAS — questões nunca tentadas.
3. MINI-SIMULADO — amostra sob condição de prova (sem dica, corrige no final).

Por que isto não é a fila (`scheduler.fila`): a fila prioriza revisão
vencida para não deixar conhecimento se perder — é o motor de fundo,
roda todo dia sem pedir permissão. O desafio é uma COMPOSIÇÃO deliberada e
do tamanho de uma sessão, pensada para caber num tempo estimado; ele não
substitui a fila, empresta dela o vocabulário (mesmos campos de questão) e
reaproveita os módulos que já fazem a resolução de verdade
(`chat._estudar_lista` para os dois primeiros blocos, `chat.simulado` para
o terceiro) — este módulo só decide O QUE entra na lista.

Estimativa de tempo vem do histórico real (`avg(tentativa.segundos)`), não
de um palpite fixo — mesmo motivo que levou `v_desempenho_disciplina` a
existir: medir, não estimar às cegas. Sem histórico ainda (usuário novo),
cai num default documentado abaixo.
"""
from . import db, scheduler
from .scheduler import CAMPOS_Q

VERSAO = "desafio-v1"

# Sem tentativa nenhuma no banco ainda não há média para calcular. 90s é
# chute conservador para uma resposta dissertativa curta — melhor superestimar
# o tempo de um desafio novo do que prometer 5 minutos e entregar 15.
SEGUNDOS_PADRAO = 90


def tempo_medio_segundos() -> float:
    r = db.exec1("SELECT avg(segundos)::float8 AS media FROM tentativa WHERE segundos IS NOT NULL")
    return r["media"] if r and r["media"] else float(SEGUNDOS_PADRAO)


def _novas(limite: int, excluir: set[int]) -> list[dict]:
    if limite <= 0:
        return []
    return db.query(
        f"""SELECT {CAMPOS_Q} FROM questao q
            WHERE NOT EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = q.id)
              AND q.id <> ALL(%(ex)s)
            ORDER BY q.id LIMIT %(l)s""",
        {"l": limite, "ex": list(excluir) or [-1]},
    )


def _reincidentes(limite: int) -> list[dict]:
    if limite <= 0:
        return []
    # erro_caderno TAMBÉM tem colunas disciplina/tema (é a cópia resumida,
    # não a fonte) — sem qualificar com "q.", o SELECT * de CAMPOS_Q bate em
    # AmbiguousColumn contra as do erro_caderno.
    campos = ", ".join(f"q.{c.strip()}" for c in CAMPOS_Q.split(","))
    return db.query(
        f"""SELECT {campos} FROM questao q
            JOIN erro_caderno e ON e.questao_id = q.id
            ORDER BY e.vezes DESC, e.ultima DESC LIMIT %(l)s""",
        {"l": limite},
    )


def _mini_simulado(limite: int, excluir: set[int]) -> list[dict]:
    """
    Amostra ALEATÓRIA sobre o acervo todo (mesmo espírito de simulado.selecionar:
    é a prova real que não escolhe o que cai). Busca um pouco mais que o pedido
    porque parte pode colidir com o que já entrou em reincidentes/novas — pedir
    2x cobre isso sem precisar de retry em loop para acervos pequenos.
    """
    if limite <= 0:
        return []
    candidatos = db.query(
        f"""SELECT {CAMPOS_Q} FROM questao q
            WHERE q.id <> ALL(%(ex)s)
            ORDER BY random() LIMIT %(l)s""",
        {"l": limite * 2, "ex": list(excluir) or [-1]},
    )
    return candidatos[:limite]


def montar(n_reincidentes: int = 3, n_novas: int = 5, n_simulado: int = 5) -> dict:
    """Monta o desafio do dia. Cada bloco pode vir menor (ou vazio) que o
    pedido se o acervo não tiver material suficiente — não é erro, é reflexo
    honesto do que existe."""
    reincidentes = _reincidentes(n_reincidentes)
    usados = {q["id"] for q in reincidentes}

    novas = _novas(n_novas, usados)
    usados |= {q["id"] for q in novas}

    mini_simulado = _mini_simulado(n_simulado, usados)

    total = len(reincidentes) + len(novas) + len(mini_simulado)
    return {
        "reincidentes": reincidentes,
        "novas": novas,
        "mini_simulado": mini_simulado,
        "total_questoes": total,
        "estimativa_minutos": round(tempo_medio_segundos() * total / 60) if total else 0,
    }
