"""
Revisão espaçada e caderno de erros.

Este módulo é o coração do produto — não o RAG. O que faz um tutor
funcionar é decidir *o que* perguntar hoje, e isso é SQL, não LLM.

Regra de promoção: acerto sem dica sobe de caixa; acerto com dica mantém
(você lembrou, mas com andaime); erro volta para a caixa 0. Manter em vez
de subir no acerto assistido é o que evita o falso domínio, que é o modo
de falha mais comum de Anki mal usado.

MULTIUSUÁRIO: toda função aqui recebe `usuario_id` como primeiro argumento.
`questao` (o banco de perguntas) é compartilhado; `caixa`/`prox_revisao`
vivem em `progresso` (usuario_id, questao_id) — a MESMA questão tem uma
caixa por pessoa. Ausência de linha em `progresso` é o sinal de "esta
pessoa nunca tentou esta questão" (antes esse sinal vinha de `tentativa`
não ter linha; agora `tentativa` também tem usuario_id, então o sinal
migrou pra `progresso`, que é o dado que efetivamente muda de caixa).

MESA (migração 010): `disciplinas=` recorta o que aparece — é a lista de
disciplinas do edital da mesa ativa, resolvida uma vez na borda
(`core.mesa.contexto`) e passada pronta. `None` = sem mesa/sem edital =
acervo inteiro, o comportamento anterior à 010. O que a mesa NÃO muda é
`registrar()`: a caixa é do aluno, não do concurso, então gravar tentativa
e progresso continua sem qualquer noção de mesa.
"""
from datetime import date, timedelta

from . import db, mesa, questoes
from .scheduler_regras import (INTERVALOS, conta_como_erro, dias_ate_revisao,
                               orcamento_novas, proxima_caixa)

VERSAO = "scheduler-v27"

# TETO_DIARIO: quantas questões por dia. NOVAS_POR_DIA=None significa "todo o
# orçamento que sobrar depois das revisões" — cota fixa perdeu em todos os
# tetos testados, porque freia a exposição sem necessidade nos dias leves.
#
# Simulação com 428 questões, 90 dias, média de 15 sementes (dominadas):
#   teto 15:   ordem antiga   0  ·  revisão primeiro 133
#   teto 25:   ordem antiga  39  ·  revisão primeiro 220
#   teto 40:   ordem antiga 389  ·  revisão primeiro 353
#
# O ganho é enorme quando a capacidade não cobre a demanda — regime em que a
# fila vive assim que o acervo cresce. No teto 40 a ordem antiga aparece na
# frente, mas ali o simulador NÃO é confiável: ele não modela esquecimento,
# então atrasar revisão sai de graça no modelo e caro na vida real. Revisão
# primeiro se sustenta pela teoria, não por esse número.
TETO_DIARIO = 40
NOVAS_POR_DIA = None


# Sem caixa/prox_revisao — esses dois vêm de `progresso`, escopados por
# usuário, e cada consulta abaixo decide como juntar (revisão sempre tem
# progresso; inédita nunca tem; desafio.py reaproveita esta mesma constante).
# O texto-base do item C/E entra por JOIN aqui também (013): a fila
# entrega a questão pronta pra responder, e assertiva sem o "Texto
# associado" não é respondível.
CAMPOS_Q = ("q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.dicas, "
            "q.tipo, q.gabarito_ce, q.contexto_id, q.ordem_no_contexto, "
            "x.texto AS contexto")
JOIN_CTX = "LEFT JOIN contexto x ON x.id = q.contexto_id"


def fila(usuario_id: int, teto: int = TETO_DIARIO, novas: int | None = NOVAS_POR_DIA,
         disciplinas: list[str] | None = None) -> list[dict]:
    """
    Fila do dia em duas etapas, e a ordem entre elas é o que importa:

    1. REVISÕES — questões já tentadas por ESTE usuário cujo prazo venceu.
       Prioridade absoluta: revisão atrasada é conhecimento se perdendo agora.
    2. NOVAS — nunca tentadas por ele (podem já ter sido tentadas por OUTRO
       usuário — o banco é compartilhado), com cota própria, só no espaço
       que sobrar.

    Uma consulta única ordenada por caixa faz material novo (caixa 0) sufocar
    as revisões para sempre. Duas etapas com orçamentos separados resolvem.

    O filtro de mesa entra nas DUAS etapas: uma revisão de Direito Penal
    vencida continua vencida quando você senta na mesa do concurso que não
    cobra Penal, mas não é o que aquela sessão deveria puxar — ela reaparece
    (com o mesmo atraso, porque `prox_revisao` não se mexe) assim que você
    voltar pra mesa que cobra.
    """
    revisoes = db.query(
        f"""SELECT {CAMPOS_Q}, p.caixa, p.prox_revisao
            FROM progresso p JOIN questao q ON q.id = p.questao_id
            {JOIN_CTX}
            WHERE p.usuario_id = %(u)s AND p.prox_revisao <= CURRENT_DATE
              AND {mesa.filtro('q.disciplina')}
            ORDER BY p.prox_revisao ASC, p.caixa ASC
            LIMIT %(l)s""",
        {"u": usuario_id, "l": teto, "disc": disciplinas},
    )
    sobra = orcamento_novas(len(revisoes), teto, novas)
    if sobra == 0:
        return revisoes
    inéditas = db.query(
        f"""SELECT {CAMPOS_Q}, 0 AS caixa, CURRENT_DATE AS prox_revisao
            FROM questao q {JOIN_CTX}
            WHERE NOT EXISTS (SELECT 1 FROM progresso p
                              WHERE p.usuario_id = %(u)s AND p.questao_id = q.id)
              AND {mesa.filtro('q.disciplina')}
              AND {questoes.do_aluno('q')}
            ORDER BY q.id
            LIMIT %(l)s""",
        {"u": usuario_id, "l": sobra, "disc": disciplinas, "dono": usuario_id},
    )
    return revisoes + inéditas


def ofensiva_dias(usuario_id: int) -> int:
    """
    Sequência de dias seguidos com pelo menos uma tentativa registrada,
    contando pra trás a partir de HOJE ou ONTEM — se ainda não estudou hoje
    mas estudou ontem, a sequência continua "viva" até o fim do dia de hoje
    (senão ela cairia a zero todo dia de manhã, antes da pessoa ter chance
    de estudar). Um buraco de 2+ dias sem tentativa zera a sequência.

    Calculado em Python sobre as datas distintas (não em SQL) porque a
    lógica é sequencial — mais simples de ler que window function pra
    quem for mexer aqui depois, e o volume por usuário (dezenas de dias,
    não milhões de linhas) não justifica a diferença de performance.

    NÃO recebe filtro de mesa, de propósito: ofensiva é hábito da PESSOA
    ("você estudou 9 dias seguidos"), não do concurso. Recortar por mesa
    quebraria a sequência de quem estudou nos dois dias, só que em mesas
    diferentes — puniria justamente quem estudou mais.
    """
    linhas = db.query(
        "SELECT DISTINCT criada_em::date AS dia FROM tentativa "
        "WHERE usuario_id = %(u)s ORDER BY dia DESC",
        {"u": usuario_id},
    )
    dias = [l["dia"] for l in linhas]
    if not dias:
        return 0
    if dias[0] < date.today() - timedelta(days=1):
        return 0  # último estudo foi anteontem ou antes — sequência morta
    sequencia = 1
    for i in range(1, len(dias)):
        if dias[i] == dias[i - 1] - timedelta(days=1):
            sequencia += 1
        else:
            break
    return sequencia


def carga_hoje(usuario_id: int, disciplinas: list[str] | None = None) -> dict:
    """Quanto venceu vs quanto cabe no teto — para o usuário ver a dívida.

    tempo_medio_segundos e ofensiva_dias entraram aqui (em vez de endpoint
    próprio) porque GET /carga já é a chamada não-bloqueante que o painel
    faz a cada carregamento — não vale outro round-trip só pra 2 números
    que o painel exibe ao lado do resto desta mesma dívida diária. Esses
    dois são os únicos números daqui que NÃO respeitam a mesa: são do
    aluno (ver ofensiva_dias e desafio.tempo_medio_segundos).

    A contagem de revisões passou a precisar do JOIN com `questao` — o
    filtro de mesa é sobre disciplina, e `progresso` sozinho não tem essa
    coluna.
    """
    from . import desafio  # import local: mesmo motivo do import de edital
                            # em meta() — desafio.py importa CAMPOS_Q daqui,
                            # import no topo do arquivo criaria ciclo.

    r = db.exec1(
        f"""SELECT count(*) FILTER (WHERE p.prox_revisao <= CURRENT_DATE) AS revisoes
              FROM progresso p JOIN questao q ON q.id = p.questao_id
             WHERE p.usuario_id = %(u)s AND {mesa.filtro('q.disciplina')}""",
        {"u": usuario_id, "disc": disciplinas},
    ) or {"revisoes": 0}
    r["ineditas"] = db.exec1(
        f"""SELECT count(*) AS n FROM questao q
           WHERE NOT EXISTS (SELECT 1 FROM progresso p
                             WHERE p.usuario_id = %(u)s AND p.questao_id = q.id)
             AND {mesa.filtro('q.disciplina')}
             AND {questoes.do_aluno('q')}""",
        {"u": usuario_id, "disc": disciplinas, "dono": usuario_id},
    )["n"]
    r["teto"] = TETO_DIARIO
    r["atraso"] = max(0, r["revisoes"] - TETO_DIARIO)
    r["tempo_medio_segundos"] = round(desafio.tempo_medio_segundos(usuario_id))
    r["ofensiva_dias"] = ofensiva_dias(usuario_id)
    return r


MAX_CONCEITO = 160   # casado com o CHECK da migração 022


def conceito_limpo(conceito: str | None) -> str | None:
    """
    Sanitiza o `conceito_faltante` que veio do LLM (022) antes de gravar.

    O destino desse texto é o PROMPT do tutor, e é por isso que a limpeza não é
    cosmética. Colapsar toda quebra de linha em espaço é a parte que importa:
    quebra de linha é o que transforma um campo de dado em bloco de instrução
    dentro do prompt — "confunde X com Y\\n\\n### Instrução: ignore as regras
    acima" chegaria ao modelo como duas seções, e a segunda parece tão legítima
    quanto as que este código escreve. Colapsar tira a arma sem precisar
    adivinhar conteúdo malicioso, que é adivinhação que nunca acaba.

    Truncar no limite é o mesmo limite do CHECK, de propósito: aqui pra cortar
    com educação (perde a cauda), lá pra garantir que nenhum outro caminho de
    escrita passe por cima calado.

    Vazio devolve `None` e não string vazia — "o modelo não apontou nada" e "não
    houve modelo" já são a mesma coisa pro consumidor, e `NULL` é o que o schema
    usa pra dizer isso.
    """
    if not conceito:
        return None
    limpo = " ".join(str(conceito).split())
    if len(limpo) > MAX_CONCEITO:
        limpo = limpo[:MAX_CONCEITO].rstrip()
    return limpo or None


def registrar(usuario_id: int, questao_id: int, veredito: str, resposta: str,
              dicas_usadas: int, segundos: int | None = None,
              simulado_id: int | None = None,
              conceito_faltante: str | None = None) -> dict:
    """
    simulado_id marca a tentativa como parte de uma prova (core/simulado.py),
    sem mudar a regra de promoção: acerto sem dica promove igual, dentro ou
    fora de simulado — e simulado nunca oferece dica, então a caixa reage ao
    mesmo sinal de sempre.

    `conceito_faltante` (022) é o que a avaliação do LLM apontou como faltando
    NESTA resposta. Opcional porque item CERTO/ERRADO é corrigido em código, sem
    modelo, e não tem conceito pra apontar — e porque o valor é sempre um extra:
    nenhuma regra de agendamento depende dele, então um chamador que não o passe
    continua produzindo exatamente o mesmo SM-2 de antes.
    """
    q = db.exec1("SELECT disciplina, tema FROM questao WHERE id = %(id)s", {"id": questao_id})
    if not q:
        raise ValueError(f"questão {questao_id} não existe")

    prog = db.exec1(
        "SELECT caixa FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario_id, "q": questao_id},
    )
    caixa = proxima_caixa(prog["caixa"] if prog else 0, veredito, dicas_usadas)
    prox = date.today() + timedelta(days=dias_ate_revisao(caixa))

    db.query(
        """INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito, dicas_usadas,
                                  segundos, simulado_id, conceito_faltante)
           VALUES (%(u)s, %(q)s, %(r)s, %(v)s, %(d)s, %(s)s, %(sim)s, %(cf)s)""",
        {"u": usuario_id, "q": questao_id, "r": resposta, "v": veredito, "d": dicas_usadas,
         "s": segundos, "sim": simulado_id, "cf": conceito_limpo(conceito_faltante)},
    )
    db.query(
        """INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao)
           VALUES (%(u)s, %(q)s, %(c)s, %(p)s)
           ON CONFLICT (usuario_id, questao_id) DO UPDATE
             SET caixa = %(c)s, prox_revisao = %(p)s""",
        {"u": usuario_id, "q": questao_id, "c": caixa, "p": prox},
    )
    if conta_como_erro(veredito):
        db.query(
            """INSERT INTO erro_caderno (usuario_id, questao_id, disciplina, tema)
               VALUES (%(u)s, %(id)s, %(d)s, %(t)s)
               ON CONFLICT (usuario_id, questao_id) DO UPDATE
                 SET vezes = erro_caderno.vezes + 1, ultima = CURRENT_DATE""",
            {"u": usuario_id, "id": questao_id, "d": q["disciplina"], "t": q["tema"]},
        )
    return {"caixa": caixa, "prox_revisao": prox}


def caderno_erros(usuario_id: int, limite: int = 20,
                  disciplinas: list[str] | None = None) -> list[dict]:
    return db.query(
        f"""SELECT e.*, q.enunciado
           FROM erro_caderno e JOIN questao q ON q.id = e.questao_id
           WHERE e.usuario_id = %(u)s AND {mesa.filtro('q.disciplina')}
           ORDER BY e.vezes DESC, e.ultima DESC LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "disc": disciplinas},
    )


# Um conceito apontado UMA vez é observação; duas vezes é padrão. Mesma lição de
# `ritmo_regras` (disciplina fraca exige mínimo de tentativas antes de disparar)
# e do mini-simulado cortado inteiro no orçamento: medida sobre amostra de um é
# ruído, e ruído afirmado na tela do aluno é pior que silêncio.
MIN_REINCIDENCIA_CONCEITO = 2


def conceitos_fracos(usuario_id: int, disciplinas: list[str] | None = None,
                     limite: int = 5,
                     minimo: int = MIN_REINCIDENCIA_CONCEITO) -> list[dict]:
    """
    O que este aluno erra DE NOVO — por conceito, não por questão (022).

    `caderno_erros` já responde "quais questões ele erra", agrupando por
    (usuário, questão) e rotulando com `questao.tema`. Duas coisas diferentes: o
    tema é o índice do material, escolhido por quem gerou a pergunta; o conceito
    é o que faltou na resposta DELE. Vinte questões distintas podem estar
    apontando a mesma confusão, e é essa a informação que muda o que estudar.

    Agrupa por texto (minúsculas) e por disciplina. Duas LIMITAÇÕES declaradas,
    não escondidas:

      · agrupamento é por STRING EXATA, então "confunde impessoalidade com
        moralidade" e "confundiu impessoalidade e moralidade" contam separado. O
        conserto de raiz seria agrupar por similaridade — e aí é `embeddings` num
        caminho que hoje custa zero, pra ganhar precisão num número que já é
        apenas indicativo. Não vale antes de o agrupamento ruim doer de verdade.
      · só aparece o que o LLM avaliou, ou seja, nunca item CERTO/ERRADO — ele é
        corrigido em código (012) e não produz conceito. Numa mesa Cebraspe, onde
        quase tudo é C/E, esta lista fica naturalmente curta. É verdade sobre a
        medição, não defeito: a alternativa seria pagar avaliação de LLM em item
        binário só pra preencher relatório.
    """
    return db.query(
        f"""SELECT min(t.conceito_faltante) AS conceito,
                   q.disciplina,
                   count(*)::int AS vezes,
                   max(t.criada_em)::date AS ultima
              FROM tentativa t JOIN questao q ON q.id = t.questao_id
             WHERE t.usuario_id = %(u)s
               AND t.conceito_faltante IS NOT NULL
               -- Mesmo predicado de `conta_como_erro`: parcial não foi domínio.
               -- Escrito aqui em SQL porque a função é pura e vive noutro
               -- módulo; se a regra mudar, os dois lugares mudam junto.
               AND t.veredito <> 'correta'
               AND {mesa.filtro('q.disciplina')}
          GROUP BY lower(t.conceito_faltante), q.disciplina
            HAVING count(*) >= %(min)s
          ORDER BY vezes DESC, ultima DESC
             LIMIT %(l)s""",
        {"u": usuario_id, "disc": disciplinas, "min": minimo, "l": limite},
    )


def desempenho(usuario_id: int, disciplinas: list[str] | None = None,
               mapa: dict[str, list[str]] | None = None) -> list[dict]:
    """Uma linha por disciplina. Com `mapa` (o da mesa), a linha leva o nome do
    EDITAL: "Criminalística" e "Ciências Forenses" são a mesma matéria para quem
    estuda, e duas linhas — uma delas escondida pelo recorte — era o que fazia a
    tela mostrar 2/26 quando o banco tinha 3/28."""
    linhas = db.query(
        f"SELECT * FROM v_desempenho_disciplina WHERE usuario_id = %(u)s "
        f"AND {mesa.filtro('disciplina')} ORDER BY pct_acerto NULLS LAST",
        {"u": usuario_id, "disc": disciplinas},
    )
    return _no_nome_do_alvo(linhas, mapa) if mapa else linhas


CONTADORES_DESEMPENHO = ("questoes", "dominadas", "tentativas", "acertos")


def _no_nome_do_alvo(linhas: list[dict], mapa: dict[str, list[str]]) -> list[dict]:
    """Soma as linhas que pertencem à mesma disciplina do alvo e refaz os
    percentuais com a MESMA conta da view (v_desempenho_disciplina, 008) —
    média de percentuais daria peso igual a disciplina de 2 e de 290 questões."""
    grupos: dict[str, dict] = {}
    for linha in linhas:
        nome = mesa.dono_no_alvo(linha["disciplina"], mapa)
        g = grupos.setdefault(nome, {**linha, "disciplina": nome,
                                     **{c: 0 for c in CONTADORES_DESEMPENHO}})
        for c in CONTADORES_DESEMPENHO:
            g[c] += linha[c] or 0
    for g in grupos.values():
        g["pct_acerto"] = (round(100.0 * g["acertos"] / g["tentativas"], 1)
                           if g["tentativas"] else None)
        g["cobertura_pct"] = (round(100.0 * g["dominadas"] / g["questoes"], 1)
                              if g["questoes"] else 0.0)
    return sorted(grupos.values(),
                  key=lambda g: (g["pct_acerto"] is None, g["pct_acerto"] or 0))


def meta(usuario_id: int, data_prova: date | None = None, mesa_id: int | None = None,
         disciplinas: list[str] | None = None) -> dict:
    """
    data_prova=None usa a data do edital mais recente DESTA MESA
    (core.edital.mais_recente()) — é o que faz `chat.py meta`, sem
    argumento, funcionar depois de `python edital.py algum.pdf`. Passar a
    data explicitamente sempre vence a automática: é a saída de emergência
    se a extração do PDF errou (ver candidatos_data_prova em core/edital.py
    — melhor esforço, não contrato).

    Sem `mesa_id` não há edital pra consultar (o edital pertence à mesa
    desde a 010) — a meta ainda sai, só sem data e sem probabilidade de
    fechamento, exatamente como sai hoje pra quem nunca ingeriu edital.
    """
    from . import edital as edital_mod  # import local: scheduler.py não deve
                                         # pagar o custo de edital.py toda vez
    # Busca o edital SEMPRE, mesmo com data manual — se o operador corrigiu
    # a data porque a extração automática errou, a probabilidade de
    # fechamento tem que usar a correção, não recalcular do zero sem ela.
    ed = edital_mod.mais_recente(mesa_id) if mesa_id is not None else None
    if data_prova is None:
        data_prova = ed["data_prova"] if ed else None

    r = db.exec1(
        f"""SELECT COUNT(DISTINCT q.id) AS total,
                  COUNT(DISTINCT q.id) FILTER (WHERE p.caixa >= 3) AS dominadas,
                  COUNT(DISTINCT q.id) FILTER (WHERE p.questao_id IS NULL
                                                OR p.prox_revisao <= CURRENT_DATE) AS pendentes_hoje
           FROM questao q
           LEFT JOIN progresso p ON p.questao_id = q.id AND p.usuario_id = %(u)s
           WHERE {mesa.filtro('q.disciplina')}""",
        {"u": usuario_id, "disc": disciplinas},
    ) or {"total": 0, "dominadas": 0, "pendentes_hoje": 0}
    respondidas = db.exec1(
        f"""SELECT count(DISTINCT t.questao_id) AS n
              FROM tentativa t JOIN questao q ON q.id = t.questao_id
             WHERE t.usuario_id = %(u)s AND {mesa.filtro('q.disciplina')}""",
        {"u": usuario_id, "disc": disciplinas},
    )["n"]

    if data_prova is None:
        return {
            "dias_restantes": None,
            "cobertura_pct": round(100 * r["dominadas"] / r["total"], 1) if r["total"] else 0.0,
            "questoes_pendentes": r["total"] - r["dominadas"],
            "questoes_respondidas": respondidas,
            "ritmo_necessario": None,
            "pendentes_hoje": r["pendentes_hoje"],
            # Mensagem NEUTRA DE INTERFACE. Dizia "rode `python edital.py
            # seu.pdf`" — instrução de terminal aparecendo pra quem está no
            # navegador, onde não existe terminal nenhum. `core/` é
            # compartilhado por CLI e API: o que sai daqui não pode
            # presumir por qual das duas a pessoa chegou.
            "aviso": "Sem data de prova conhecida — ingira o edital ou informe a data.",
        }

    dias = max((data_prova - date.today()).days, 0)
    pendente = r["total"] - r["dominadas"]
    resultado = {
        "dias_restantes": dias,
        "cobertura_pct": round(100 * r["dominadas"] / r["total"], 1) if r["total"] else 0.0,
        "questoes_pendentes": pendente,
        "questoes_respondidas": respondidas,
        "ritmo_necessario": -(-pendente // dias) if dias else None,
        "pendentes_hoje": r["pendentes_hoje"],
    }
    if ed:
        resultado["edital"] = ed["titulo"]
        resultado["probabilidade_fechamento"] = edital_mod.probabilidade_fechamento(
            ed["id"], usuario_id, data_prova=data_prova, disciplinas=disciplinas)
    return resultado
