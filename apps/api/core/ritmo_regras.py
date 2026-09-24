"""
Regras de intervenção proativa — FUNÇÕES PURAS, sem banco.

Mesmo princípio de scheduler_regras.py: a decisão "vale interromper o aluno
agora?" não precisa de SQL, só dos dados já buscados. Isolada assim, dá pra
testar os limiares (o "N" de "5 acertos seguidos", o "50%" de desempenho
fraco) sem banco — e trocar um número não exige rodar `chat.py estudar` na
mão pra sentir o efeito.

Por que regra e não LLM decidindo: o LLM já existe para a conversa livre
(`socratic.explicar`). Decidir QUANDO intervir é uma pergunta de limiar sobre
número — pedir pro modelo julgar isso a cada questão custaria cota e
devolveria uma decisão que muda de sessão pra sessão sem ninguém pedir.
"""

JANELA_SEQUENCIA = 5           # acertos seguidos sem dica para sugerir subir o nível
MINIMO_TENTATIVAS_DISCIPLINA = 5   # abaixo disso, "50% de acerto" é ruído de amostra pequena
TETO_PCT_FRACA = 50.0
MINIMO_VEZES_REINCIDENCIA = 3
ERROS_SEGUIDOS = 3             # erros consecutivos que fazem valer PARAR a fila


def sugestao_sequencia(ultimos: list[tuple[str, int]],
                        janela: int = JANELA_SEQUENCIA) -> str | None:
    """
    `ultimos` = [(veredito, dicas_usadas), ...] das tentativas mais recentes
    primeiro. Só sugere com a janela CHEIA — sequência de 2 acertos num total
    de 2 tentativas não é sequência, é a amostra inteira.
    """
    if len(ultimos) < janela:
        return None
    if all(v == "correta" and d == 0 for v, d in ultimos[:janela]):
        return (f"{janela} acertos seguidos sem dica — bora subir o nível? "
                f"tenta um simulado ou pede questões mais difíceis.")
    return None


def sugestao_disciplina_fraca(desempenho: list[dict],
                               minimo_tentativas: int = MINIMO_TENTATIVAS_DISCIPLINA,
                               teto_pct: float = TETO_PCT_FRACA) -> str | None:
    """
    `desempenho` no formato de scheduler.desempenho() (uma linha por
    disciplina). Exige `minimo_tentativas` para não apontar disciplina fraca
    com base em 1 ou 2 respostas — mesma lição do simulador: aleatoriedade
    com amostra pequena engana.
    """
    candidatas = [d for d in desempenho
                  if d["tentativas"] >= minimo_tentativas
                  and (d["pct_acerto"] or 0) < teto_pct]
    if not candidatas:
        return None
    pior = min(candidatas, key=lambda d: d["pct_acerto"])
    return (f"{pior['disciplina']} está em {pior['pct_acerto']:.0f}% de acerto "
            f"({pior['tentativas']} {'tentativa' if pior['tentativas'] == 1 else 'tentativas'}) "
            "— vale focar aqui hoje.")


def sugestao_reincidencia(erros: list[dict],
                           minimo_vezes: int = MINIMO_VEZES_REINCIDENCIA) -> str | None:
    """`erros` no formato de scheduler.caderno_erros(), já ordenado por
    vezes DESC — o primeiro item é sempre o pior, não precisa reordenar."""
    if not erros or erros[0]["vezes"] < minimo_vezes:
        return None
    pior = erros[0]
    return (f'"{pior["tema"]}" já errou {pior["vezes"]} vezes — '
            f"considere revisar esse ponto antes de seguir.")


def sugestao_erros_seguidos(ultimos: list[dict],
                            janela: int = ERROS_SEGUIDOS) -> dict | None:
    """
    A única regra que manda INTERROMPER, e não só sugerir.

    `ultimos` = tentativas mais recentes primeiro, cada uma com `veredito`,
    `tema` e `disciplina`. Dispara com `janela` erros consecutivos.

    POR QUE ESTA É DIFERENTE DAS OUTRAS TRÊS: elas descrevem uma TENDÊNCIA
    (disciplina fraca há semanas, tema que reincide) e cabem num aviso
    passivo que o aluno lê quando quiser. Esta descreve um estado AGORA —
    três erros seguidos é alguém batendo a cabeça neste minuto, e continuar
    a fila só produz mais erro e mais caixa zerada. O custo de não
    interromper é assimétrico: um aviso ignorado custa uma linha de tela;
    dez minutos errando em sequência custa a sessão e a confiança.

    Devolve DICT e não string porque a interrupção precisa levar o aluno a
    algum lugar — o texto sozinho seria mais um aviso que ele fecha. O
    `tema` só entra quando os erros são do MESMO ponto: "você errou 3
    seguidas" é observação, "você errou 3 seguidas de peculato" é
    diagnóstico, e só o segundo dá o que perguntar ao tutor.
    """
    if len(ultimos) < janela:
        return None
    recentes = ultimos[:janela]
    if any(t.get("veredito") == "correta" for t in recentes):
        return None

    temas = {t.get("tema") for t in recentes if t.get("tema")}
    disciplinas = {t.get("disciplina") for t in recentes if t.get("disciplina")}
    assunto = temas.pop() if len(temas) == 1 else (
        disciplinas.pop() if len(disciplinas) == 1 else None)

    if assunto:
        return {
            "motivo": "erros_seguidos",
            "texto": (f"Pausa. Você errou as últimas {janela} questões de {assunto} — "
                      f"continuar agora só zera caixa e estraga a métrica."),
            "pergunta": f"Errei {janela} questões seguidas de {assunto}. "
                        f"Onde meu raciocínio está desviando?",
        }
    return {
        "motivo": "erros_seguidos",
        "texto": (f"Pausa. Foram {janela} erros seguidos — vale parar de responder e "
                  f"entender o que está travando antes de continuar."),
        "pergunta": f"Errei {janela} questões seguidas. Me ajuda a achar o que estou "
                    f"confundindo?",
    }


def priorizar(*candidatos: str | None) -> str | None:
    """
    Devolve só UMA sugestão, a primeira que existir na ordem dos argumentos —
    passar as três nunca vira as três de uma vez. Intervenção proativa que
    empilha três avisos por sessão deixa de ser proativa e vira ruído; melhor
    o aluno ver um aviso certeiro do que uma lista que ele aprende a ignorar.
    Ordem de prioridade é escolha de quem chama (reincidência concreta antes
    de tendência de disciplina antes de elogio de sequência, por exemplo).
    """
    for c in candidatos:
        if c:
            return c
    return None
