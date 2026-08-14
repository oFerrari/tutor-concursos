"""
Desafio diário — meta automática que mescla três blocos numa sessão só:

1. REINCIDENTES — pontos fracos do caderno de erros, os que mais voltam.
2. NOVAS — questões nunca tentadas POR ESTE usuário (podem já ter sido
   tentadas por outro — o banco de questões é compartilhado).
3. MINI-SIMULADO — amostra sob condição de prova (sem dica, corrige no final).

Por que isto não é a fila (`scheduler.fila`): a fila prioriza revisão
vencida para não deixar conhecimento se perder — é o motor de fundo,
roda todo dia sem pedir permissão. O desafio é uma COMPOSIÇÃO deliberada e
do tamanho de uma sessão, pensada para caber num tempo estimado; ele não
substitui a fila, empresta dela o vocabulário (mesmos campos de questão) e
reaproveita os módulos que já fazem a resolução de verdade
(`chat._estudar_lista` para os dois primeiros blocos, `chat.simulado` para
o terceiro) — este módulo só decide O QUE entra na lista.

Estimativa de tempo vem do histórico real DESTE usuário
(`avg(tentativa.segundos)`), não de um palpite fixo — mesmo motivo que
levou `v_desempenho_disciplina` a existir: medir, não estimar às cegas.
Sem histórico ainda (usuário novo), cai num default documentado abaixo.
"""
from . import db, mesa
from .scheduler import CAMPOS_Q, JOIN_CTX

VERSAO = "desafio-v4"

# Sem tentativa nenhuma DESTE usuário ainda não há média para calcular. 90s é
# chute conservador para uma resposta dissertativa curta — melhor superestimar
# o tempo de um desafio novo do que prometer 5 minutos e entregar 15.
SEGUNDOS_PADRAO = 90

# Mini-simulado com 2 questões não é simulado, é um par de questões sem
# dica. O bloco tem tamanho mínimo pra existir: abaixo disso ele sai
# INTEIRO do desafio e o tempo vai pros outros dois, que rendem mais por
# minuto. Cortar até virar enfeite é pior que cortar de vez.
MIN_SIMULADO = 3


def tempo_medio_segundos(usuario_id: int) -> float:
    """Sem filtro de mesa, de propósito: é a velocidade de resposta da
    PESSOA (o número que vira "~25 min estimados"), não uma característica
    do concurso — mesmo critério de `scheduler.ofensiva_dias`."""
    r = db.exec1(
        "SELECT avg(segundos)::float8 AS media FROM tentativa "
        "WHERE usuario_id = %(u)s AND segundos IS NOT NULL",
        {"u": usuario_id},
    )
    return r["media"] if r and r["media"] else float(SEGUNDOS_PADRAO)


def orcamento_blocos(cabem: int, n_reincidentes: int, n_novas: int,
                     n_simulado: int) -> tuple[int, int, int]:
    """
    Como cortar os três blocos quando o tempo não dá pra tudo. FUNÇÃO PURA
    — nem banco nem relógio, testável sozinha (mesmo molde de
    `scheduler_regras` e `ritmo_regras`).

    A ORDEM DO CORTE é a decisão de produto aqui, e ela não é arbitrária:

      1. REINCIDENTES ficam. É o que a pessoa erra de novo e de novo; num
         orçamento apertado é o que mais rende por minuto.
      2. NOVAS vêm depois. Material inédito é o mais caro cognitivamente —
         é o primeiro a sair de uma sessão de "só tenho 20 minutos e estou
         cansado", não o último.
      3. MINI-SIMULADO é o primeiro a cair, E CAI INTEIRO (ver MIN_SIMULADO):
         ele existe pra medir sob condição de prova, e medida sobre amostra
         de 2 questões é ruído — a mesma lição de "percentual sobre amostra
         pequena é ruído, não tendência" que já vale em `ritmo_regras`.

    `cabem <= 0` devolve zeros: quem pediu 0 minuto recebe desafio vazio, e
    a tela diz isso — melhor que entregar 1 questão fingindo que coube.
    """
    if cabem <= 0:
        return 0, 0, 0
    reincidentes = min(n_reincidentes, cabem)
    novas = min(n_novas, cabem - reincidentes)
    simulado = min(n_simulado, cabem - reincidentes - novas)
    return reincidentes, novas, (simulado if simulado >= MIN_SIMULADO else 0)


def _novas(usuario_id: int, limite: int, excluir: set[int],
           disciplinas: list[str] | None = None) -> list[dict]:
    if limite <= 0:
        return []
    return db.query(
        f"""SELECT {CAMPOS_Q}, 0 AS caixa, CURRENT_DATE AS prox_revisao
            FROM questao q {JOIN_CTX}
            WHERE NOT EXISTS (SELECT 1 FROM progresso p
                              WHERE p.usuario_id = %(u)s AND p.questao_id = q.id)
              AND q.id <> ALL(%(ex)s)
              AND {mesa.filtro('q.disciplina')}
            ORDER BY q.id LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "ex": list(excluir) or [-1], "disc": disciplinas},
    )


def _reincidentes(usuario_id: int, limite: int,
                  disciplinas: list[str] | None = None) -> list[dict]:
    if limite <= 0:
        return []
    # erro_caderno TAMBÉM tem colunas disciplina/tema (é a cópia resumida,
    # não a fonte) — sem qualificar com "q.", o SELECT * de CAMPOS_Q bate em
    # AmbiguousColumn contra as do erro_caderno.
    return db.query(
        f"""SELECT {CAMPOS_Q}, p.caixa, p.prox_revisao
            FROM questao q {JOIN_CTX}
            JOIN erro_caderno e ON e.questao_id = q.id AND e.usuario_id = %(u)s
            JOIN progresso p ON p.questao_id = q.id AND p.usuario_id = %(u)s
            WHERE {mesa.filtro('q.disciplina')}
            ORDER BY e.vezes DESC, e.ultima DESC LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "disc": disciplinas},
    )


def _mini_simulado(limite: int, excluir: set[int],
                   disciplinas: list[str] | None = None) -> list[dict]:
    """
    Amostra ALEATÓRIA sobre o acervo compartilhado todo (mesmo espírito de
    simulado.selecionar: é a prova real que não escolhe o que cai) — por
    isso NÃO recebe usuario_id, só exclui o que já entrou nos outros dois
    blocos. Recebe `disciplinas` porque "a prova não escolhe o que cai"
    vale DENTRO do edital: sortear Direito Penal num concurso que não cobra
    Penal não é imprevisibilidade, é ruído. Busca um pouco mais que o
    pedido porque parte pode colidir com o que já entrou em
    reincidentes/novas — pedir 2x cobre isso sem precisar de retry em loop
    para acervos pequenos.
    """
    if limite <= 0:
        return []
    candidatos = db.query(
        f"""SELECT {CAMPOS_Q}
            FROM questao q {JOIN_CTX}
            WHERE q.id <> ALL(%(ex)s) AND {mesa.filtro('q.disciplina')}
            ORDER BY random() LIMIT %(l)s""",
        {"l": limite * 2, "ex": list(excluir) or [-1], "disc": disciplinas},
    )
    return candidatos[:limite]


def montar(usuario_id: int, n_reincidentes: int = 3, n_novas: int = 5,
           n_simulado: int = 5, disciplinas: list[str] | None = None,
           minutos: int | None = None) -> dict:
    """
    Monta o desafio do dia. Cada bloco pode vir menor (ou vazio) que o
    pedido se o acervo não tiver material suficiente — não é erro, é reflexo
    honesto do que existe (e com mesa, "o que existe" já é o recorte do
    edital dela).

    `minutos` é o ORÇAMENTO de tempo — o "só tenho 20 minutos hoje". Ele não
    é um limite aproximado de fachada: o número de questões sai da
    velocidade REAL desta pessoa (`avg(tentativa.segundos)`), então 20
    minutos de quem responde em 40s rende o dobro de quem responde em 80s.
    Prometer "10 questões em 20 minutos" pra todo mundo seria o mesmo erro
    que `simular.py` documenta — número fixo onde existe medida.
    """
    media = tempo_medio_segundos(usuario_id)
    if minutos is not None:
        cabem = int(minutos * 60 // media)
        n_reincidentes, n_novas, n_simulado = orcamento_blocos(
            cabem, n_reincidentes, n_novas, n_simulado)

    reincidentes = _reincidentes(usuario_id, n_reincidentes, disciplinas)
    usados = {q["id"] for q in reincidentes}

    novas = _novas(usuario_id, n_novas, usados, disciplinas)
    usados |= {q["id"] for q in novas}

    mini_simulado = _mini_simulado(n_simulado, usados, disciplinas)

    total = len(reincidentes) + len(novas) + len(mini_simulado)
    return {
        "reincidentes": reincidentes,
        "novas": novas,
        "mini_simulado": mini_simulado,
        "total_questoes": total,
        "estimativa_minutos": round(media * total / 60) if total else 0,
        # Devolvido pra tela poder dizer "você pediu 20, cabem 18" em vez de
        # entregar menos calada. Pedido e entregue divergem quando o acervo
        # acaba antes do tempo — que é informação, não defeito.
        "minutos_pedidos": minutos,
    }
