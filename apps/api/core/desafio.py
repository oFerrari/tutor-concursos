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
import re

from . import db, mesa
from .scheduler import CAMPOS_Q, JOIN_CTX

VERSAO = "desafio-v5"

_RE_HORAS = re.compile(r"^(\d+)h\+?$")


def minutos_do_perfil(perfil: dict | None) -> int | None:
    """
    Converte `usuario.perfil["horas"]` (migração 015, "1h"/"2h"/"4h"/"6h+"
    ou o personalizado "Nh" da migração de auth.py) num orçamento de
    minutos pra UMA sessão de desafio. `None` se a pessoa nunca respondeu
    o onboarding — aí `/desafio` cai no comportamento antigo ("sessão
    cheia", sem corte).

    Aproximação DECLARADA: "horas por dia" é um total diário, e o desafio
    é UMA sessão — tratar as duas coisas como a mesma grandeza (1h/dia vira
    exatamente 60min de UM desafio) supõe que a pessoa estuda numa sentada
    só. Pra quem divide 6h em várias sessões ao longo do dia, isso
    superestima o tamanho de cada uma. Ainda assim é estritamente melhor
    que o que existia antes (zero conexão — 1h/dia e 6h/dia recebiam o
    MESMO desafio) e usa a mesma máquina já calibrada por velocidade real
    (`orcamento_blocos`/`tempo_medio_segundos`), não um número novo
    chutado. Corrigir a aproximação exigiria saber quantas sessões por dia
    a pessoa pretende fazer — pergunta que o onboarding não faz hoje.
    """
    if not perfil:
        return None
    m = _RE_HORAS.match(str(perfil.get("horas", "")))
    return int(m.group(1)) * 60 if m else None


# "Começando" pesa pra reincidentes (reforça o que já viu, em vez de
# empilhar material inédito em cima de base ainda instável); "Avançado"
# pesa pra novas (cobre o acervo mais rápido, já tem onde pendurar
# conteúdo novo). "Intermediário" e perfil ausente mantêm 3/5/5 — o default
# de sempre, não uma escolha nova. Números pequenos e simples de propósito:
# isto é uma correção de ênfase, não uma fórmula — inventar uma proporção
# elaborada sobre uma escala de 3 valores seria precisão falsa.
_PESO_NIVEL = {
    "Começando": (5, 3, 5),
    "Avançado": (2, 7, 5),
}


def proporcao_por_nivel(perfil: dict | None, n_reincidentes: int, n_novas: int,
                        n_simulado: int) -> tuple[int, int, int]:
    """Só reajusta quando os TRÊS ainda estão no default (3/5/5) — se algum
    dia um chamador passar valores explícitos diferentes, essa escolha
    explícita vence o perfil, não o contrário."""
    if (n_reincidentes, n_novas, n_simulado) != (3, 5, 5):
        return n_reincidentes, n_novas, n_simulado
    nivel = (perfil or {}).get("nivel")
    return _PESO_NIVEL.get(nivel, (n_reincidentes, n_novas, n_simulado))

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
