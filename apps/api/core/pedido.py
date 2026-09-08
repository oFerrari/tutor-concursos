"""
O QUE O ALUNO ESTÁ PEDINDO neste turno — treino? quantas? formal? (PURO)

POR QUE ESTE MÓDULO EXISTE
--------------------------
"Queria 2 questões rápidas de direito constitucional" recebia de volta "clique
no botão 'Quero questões sobre isto'". O aluno pediu treino e levou instrução de
interface. Duas saídas erradas foram consideradas antes desta:

  · o TUTOR escrever a questão no chat. Resolve o atrito e joga fora o que dá
    valor à questão: sem `fonte_chunks` não há proveniência, sem gravar não há
    fila SM-2, sem fila não há repetição espaçada — e sem nada disso a resposta
    do aluno não conta no progresso dele. O chat fica bonito e o estudo fica
    pior, que é o oposto do produto.

  · deixar o botão e caprichar no texto. É a mesma parada de conversa com outra
    redação.

A saída é o SERVIDOR acionar o gerador que o botão já acionava. Mesma
proveniência, mesma fila, mesmo progresso — sem o clique. Para isso é preciso
reconhecer o pedido na fala, e é isso que este módulo faz.

É REGRA, NÃO LLM, e pelo mesmo motivo de `assunto.py` e `ritmo_regras.py`:
custaria a cota mais escassa do projeto e 1-2s em TODO turno pra decidir o que
regex resolve — e resposta de modelo não se trava em teste. Isto aqui se trava.

O QUE ELE NÃO DECIDE
--------------------
Não decide o TEMA. Isso é de `assunto.em_foco`, que já é o dono da pergunta
"sobre o que é esta conversa" — e a razão está registrada: a tela mandava a
última fala do aluno como tema, ela era "vamos", e voltaram CP 352 e CF 200.
Aqui só se responde "ele quer treinar, e quantas".
"""
import re

VERSAO = "pedido-v3"

# Pedido de TREINO. `quest(?:[ãa]o|[õo]es)` e não `quest[õo]es?`: o singular
# leva "ã" e o plural "õ", e quem tem pressa digita sem acento — a primeira
# versão desta regex deixou passar "me dá uma questão disso".
RE_TREINO = re.compile(
    r"(?i)\b(quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|it(?:em|ens)|me\s+test[ae]|"
    r"testa\s+meu|treina[r]?|treino|me\s+pergunt[ae]|"
    r"pergunt[ae]\s+(?:algo|alguma))\b")

# SIMULADO FORMAL é outro pedido, e continua sendo do botão: ali a pessoa quer
# prova cronometrada, correção no fim e caderno de erros — o `core/simulado.py`,
# não um punhado de questões no meio da conversa.
RE_FORMAL = re.compile(
    r"(?i)\b(simulado|prova\s|caderno\s+de\s+erros|corre[çc][ãa]o\s+autom[áa]tica)\b")

# Formato explícito. Item CERTO/ERRADO é o estilo Cebraspe (012) e o aluno pede
# pelo nome; quando ele não pede, quem decide é a banca da mesa
# (`geracao.tipo_da_banca`), que já é a regra do projeto.
RE_CERTO_ERRADO = re.compile(r"(?i)\b(certo\s*(?:ou|e|/)\s*errado|c/e|cebraspe|cespe)\b")

# Quantidade em dígito ("3 questões") ou por extenso, que é como se fala.
NUMERO = {"uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3, "três": 3,
          "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
          "dez": 10}
RE_QUANTIDADE = re.compile(
    r"(?i)\b(\d{1,2}|" + "|".join(NUMERO) + r")\s+"
    r"(?:quest|exerc|item|itens|pergunt)", re.UNICODE)

# Teto. `geracao.MAX_POR_VEZ` já corta do outro lado; este existe pra que "me dá
# 50 questões" não vire uma promessa que o gerador vai quebrar em silêncio.
MAX = 5
PADRAO = 2


RE_QUANTIDADE_SOLTA = re.compile(
    r"(?i)\b(\d{1,2}|" + "|".join(NUMERO) + r")\b")


def _valor(bruto: str) -> int:
    """"tres" -> 3, "3" -> 3, qualquer outra coisa -> 0."""
    b = bruto.lower()
    return NUMERO.get(b, 0) or (int(b) if b.isdigit() else 0)


def quantas(fala: str) -> int:
    """Quantas questões a fala pede. `PADRAO` quando ela não diz.

    Dois é o padrão e não um: "me dá questões" está no plural, e uma questão só
    encerra o treino antes de ele começar. Cinco é o teto porque cada questão
    custa uma chamada de LLM e o aluno espera por todas antes de ver a primeira."""
    # Primeiro a forma completa ("3 questões"), que é inequívoca. Só depois o
    # número solto — em "agora só uma" não há substantivo pra ancorar, e ler o
    # primeiro número da frase seria errado em "art. 312" se este caminho
    # valesse fora do contexto de treino (não vale: ver `RE_CONTINUA`).
    # SOMA as quantidades quando a fala pede em partes. Relatado: "traga 1
    # questão sobre principios explicitos e uma sobre explicito" — duas
    # questões, e a regra devolvia 1, porque parava no primeiro número. Pedir
    # "uma de cada" é a forma natural de pedir cobertura de dois pontos, e
    # entregar metade é o tipo de erro que a pessoa não reporta: ela só acha
    # que o app é ruim.
    #
    # Só soma o que vier ANCORADO em substantivo ("1 questão", "uma pergunta"):
    # somar número solto pegaria "art. 37" e "3 anos de pena".
    texto = fala or ""
    primeira = RE_QUANTIDADE.search(texto)
    if primeira:
        total = _valor(primeira.group(1))
        # A SEGUNDA QUANTIDADE VEM ELÍPTICA: em "1 questão sobre X e uma sobre
        # Y", o "uma" não tem substantivo depois — ele está subentendido. Por
        # isso não basta procurar outra ocorrência ANCORADA; é preciso somar
        # número solto que venha DEPOIS do primeiro ancorado.
        #
        # Ancorar no primeiro é o que torna isso seguro: número antes dele pode
        # ser "art. 312" ou "3 anos de pena", e o filtro de dispositivo abaixo
        # cobre o que aparecer depois.
        for m in RE_QUANTIDADE_SOLTA.finditer(texto, primeira.end()):
            antes = texto[max(0, m.start() - 12):m.start()].lower()
            if re.search(r"art\w*\.?\s*$|§\s*$|inciso\s*$|caixa\s*$", antes):
                continue
            total += _valor(m.group(1))
        if total:
            return max(1, min(total, MAX))

    m = RE_QUANTIDADE.search(fala or "") or RE_QUANTIDADE_SOLTA.search(fala or "")
    if not m:
        # "outra"/"outro" no singular é UMA a mais, não o padrão de duas.
        if re.search(r"(?i)\boutr[ao]\b", fala or ""):
            return 1
        return PADRAO
    bruto = m.group(1).lower()
    n = NUMERO.get(bruto, 0) or (int(bruto) if bruto.isdigit() else 0)
    return max(1, min(n or PADRAO, MAX))


# CONTINUAÇÃO de um pedido de treino. Fala que só ajusta a quantidade ou pede
# mais do mesmo, sem repetir a palavra "questão" — é como se fala depois de já
# ter recebido um lote.
#
# Medido no cenário `quantas`: depois de "me da 4 questoes", as falas "agora só
# uma" e "manda cinco" não geravam NADA, porque nenhuma contém as palavras da
# `RE_TREINO`. O aluno acha que pediu; o app acha que ele mudou de assunto.
#
# Não é lista de sinônimos: é a forma ELÍPTICA, que só quer dizer isso DEPOIS de
# um turno de treino. Fora desse contexto, "manda cinco" não é pedido de
# questão — e por isso `apos_treino` é obrigatório pra este caminho valer.
RE_CONTINUA = re.compile(
    r"(?i)^\s*(?:e\s+|agora\s+|entao\s+|então\s+|ok,?\s+)?"
    r"(?:mais|manda|mande|quero|vai|va|vá|s[óo]|apenas|de novo|denovo|outra|outras)?"
    r"[\s,]*(?:\d{1,2}|" + "|".join(NUMERO) + r"|outra|outras|mais)\b")


def veio_de_treino(historico: list[dict] | None) -> bool:
    """A última fala do ALUNO já era pedido de treino?

    É o contexto que `treino(..., apos_treino=True)` exige, e mora aqui pra que
    a rota e o avaliador não tenham cada um a sua ideia de "o turno anterior era
    treino" — o erro que este projeto já cometeu com `diz_assunto`, `e_eco` e
    `com_fonte` no mesmo dia.

    SEGUE A CORRENTE, e a primeira versão não seguia — olhava só a última fala
    do aluno e exigia dela um pedido COMPLETO. Medido no cenário `quantas`: a
    conversa era "me da 4 questoes" → "agora só uma" → "manda cinco", e a
    terceira não gerava nada, porque a anterior a ela ("agora só uma") era
    elíptica e não contava como treino. A corrente arrebentava no segundo elo.

    Anda de trás pra frente pelas falas do aluno: para com `True` no primeiro
    pedido completo, e com `False` na primeira fala que não é nem pedido nem
    continuação. Ou seja, "me explica melhor" no meio ENCERRA a sequência — que
    é o certo: depois de voltar a explicar, "manda cinco" já não é pedido de
    questão."""
    for m in reversed(historico or []):
        if m.get("autor") != "aluno":
            continue
        fala = m.get("texto") or ""
        if treino(fala) is not None:
            return True
        if not RE_CONTINUA.match(fala.strip()):
            return False
    return False


def treino(fala: str, apos_treino: bool = False) -> dict | None:
    """
    `None` quando a fala não pede treino. Senão, o pedido decodificado:
    `{"quantidade": n, "tipo": ... | None, "formal": bool}`.

    `formal=True` NÃO é caso deste caminho: é pedido de simulado, que tem
    página, cronômetro e correção no fim. Quem chama deve deixar o botão/rota de
    simulado responder — devolver aqui serve pra quem chama saber que o pedido
    FOI reconhecido e não deve ser tratado como conversa comum.

    `tipo=None` significa "não pediu formato": quem decide é a banca da mesa.
    """
    # O PORTÃO ACEITA OS DOIS, e a primeira versão não: exigia `RE_TREINO`, e
    # "quero um simulado formal" devolvia `None` — o pedido mais explícito de
    # todos passava como conversa comum. Simulado e prova não contêm a palavra
    # "questão", que era o que a regex procurava.
    if not fala:
        return None
    if not (RE_TREINO.search(fala) or RE_FORMAL.search(fala)):
        # Só a forma elíptica, e só logo depois de um turno de treino.
        if not (apos_treino and RE_CONTINUA.match(fala.strip())):
            return None
    return {"quantidade": quantas(fala),
            "tipo": "certo_errado" if RE_CERTO_ERRADO.search(fala) else None,
            "formal": bool(RE_FORMAL.search(fala))}
