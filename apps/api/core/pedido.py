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

VERSAO = "pedido-v8"

# Pedido de TREINO. `quest(?:[ãa]o|[õo]es)` e não `quest[õo]es?`: o singular
# leva "ã" e o plural "õ", e quem tem pressa digita sem acento — a primeira
# versão desta regex deixou passar "me dá uma questão disso".
RE_TREINO = re.compile(
    r"(?i)\b(quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|it(?:em|ens)|me\s+test[ae]|"
    r"testa\s+meu|treina[r]?|treino|me\s+pergunt[ae]|"
    # "PODEMOS TESTAR" é pedido de treino, e faltava. Medido: o aluno disse
    # "podemos testar eu nao sei se ja estou bom", isto devolveu None, nenhuma
    # questão foi gerada — e o tutor respondeu "as questões estão logo abaixo".
    # Promessa que a tela não cumpre, que é pior que não oferecer.
    #
    # O verbo vem ANCORADO num marcador de intenção (podemos/quero/vamos/…) de
    # propósito: "testar" solto aparece em pergunta de CONTEÚDO ("como testar a
    # validade de uma prova?"), e aí gerar questão seria trocar a dúvida dele
    # por um exercício que ninguém pediu.
    r"(?:podemos|vamos|bora|quero|queria|posso|gostaria\s+de)\s+(?:me\s+)?testar|"
    r"pergunt[ae]\s+(?:algo|alguma))\b")

# SIMULADO FORMAL é outro pedido, e continua sendo do botão: ali a pessoa quer
# prova cronometrada, correção no fim e caderno de erros — o `core/simulado.py`,
# não um punhado de questões no meio da conversa.
# "PROVA" SOZINHA NÃO É PEDIDO DE PROVA — e a versão anterior (`prova\s`)
# achava que era. No Processo Penal e nas Ciências Forenses, "prova" é o
# substantivo mais comum da matéria: prova pericial, prova testemunhal, prova
# emprestada, prova ilícita, meios de prova, ônus da prova. Medido, com frases
# reais dessas disciplinas, SEIS de oito viravam pedido de simulado formal:
#
#   "me explica prova testemunhal"            -> formal=True
#   "quem tem o ônus da prova?"               -> formal=True
#   "o que é prova emprestada"                -> formal=True
#
# E `formal=True` não é rótulo inofensivo: `api.py` NÃO gera questão nesse
# caminho (`if p and not p["formal"]`) e ainda acende `simulado_pedido` na
# tela. Ou seja, o aluno pedia explicação sobre prova pericial — que é uma
# disciplina inteira do edital dele, com apostila subida — e recebia um empurrão
# pra tela de Simulado.
#
# Agora "prova" só conta com MOLDURA DE EXAME: um verbo de intenção colado
# ("fazer uma prova", "quero prova") ou um qualificador de exame depois
# ("prova cronometrada"). "Simulado" e "caderno de erros" seguem valendo
# sozinhos — não têm outro sentido.
RE_FORMAL = re.compile(
    r"(?i)(\bsimulado\b|\bcaderno\s+de\s+erros\b|\bcorre[çc][ãa]o\s+autom[áa]tica\b|"
    r"\b(?:fazer|faz|quero|queria|bora|vamos|simular|aplicar|marcar)\s+"
    r"(?:uma\s+|a\s+|um\s+)?prova\b|"
    r"\bprova\s+(?:cronometrada|simulada|completa|inteira|de\s+verdade)\b)")

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


# O adiamento, e o que ele governa. Curta e fechada como as outras listas deste
# módulo: quem carrega a decisão é a POSIÇÃO (o marcador antes da palavra de
# treino), não o vocabulário.
RE_ADIADO = re.compile(
    r"(?i)\b(?:depois|mais\s+tarde|mais\s+pra\s+frente|em\s+seguida|no\s+fim|ao\s+final|"
    r"talvez|quem\s+sabe|se\s+der|futuramente)\b[^.!?]{0,40}?"
    r"\b(quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|it(?:em|ens)|treino|treinar|simulado)\b")


def _adiado(fala: str) -> bool:
    """A fala fala de treino PRA DEPOIS, não pra agora?"""
    return bool(RE_ADIADO.search(fala or ""))


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
    # PEDIDO ADIADO NÃO É PEDIDO. Relatado com log: "me introduza ao assunto,
    # depois trazendo exemplos pra depois TALVEZ questões" gerou duas questões
    # na hora — e o aluno acabara de dizer, na mesma frase, a ordem que queria
    # (introdução, exemplos, e só então talvez treino). A palavra "questões"
    # estava lá; o pedido, não.
    #
    # Só vale quando o adiamento GOVERNA a palavra de treino (ela vem depois
    # dele na frase): "depois me dá questões" adia; "me dá 5 questões, depois a
    # gente vê a teoria" pede agora e fala de outra coisa em seguida.
    if _adiado(fala):
        return None
    return {"quantidade": quantas(fala),
            "tipo": "certo_errado" if RE_CERTO_ERRADO.search(fala) else None,
            "formal": bool(RE_FORMAL.search(fala))}


# ---------------------------------------------------------------------------
# "O QUE EU JÁ ESTUDEI E O QUE FALTA?" — pergunta sobre ELE, não sobre matéria
# ---------------------------------------------------------------------------
#
# Relatado com print: "ele tá consultando material sendo que eu fiz uma pergunta
# sobre meu desempenho pessoal". A lista de CONSULTADO trazia "Princípios do
# Direito Administrativo" e uma apostila de direitos sociais numa pergunta que
# não é de conteúdo nenhum — a resposta certa mora em `### Números deste aluno`
# e no programa do edital, que já vão no prompt sem busca alguma.
#
# A causa é a de sempre: `hibrida()` é k-vizinhos sem piso de relevância, então
# uma fala sem assunto não devolve vazio, devolve seis trechos com cara de
# fonte. E "estudei", "falta" e "zerar" passam por palavra de conteúdo em
# `assunto.py` — corretamente, aliás: "falta grave" é matéria de 8.112 e de
# execução penal, e cegar a busca pra "falta" custaria mais do que isto custa.
#
# Por isso a decisão é de PEDIDO e não de vocabulário: a pergunta inteira é
# sobre o estado do aluno, e a busca não tem o que fazer nela.
#
# EXIGE CABEÇA INTERROGATIVA para os verbos de ver/estudar. "já vi" solto é
# resposta ("ja vi sim, se você puder citar só os principais"), não pergunta —
# e tratá-la como pergunta de progresso desligaria a busca no meio de uma aula.
_CABECA = r"(?:o\s+que|quais|quanto|quantos|quantas|qual)"
_PROGRESSO = re.compile(
    r"(?i)("
    rf"{_CABECA}[^?.!]{{0,40}}\b(?:j[áa]\s+)?(?:estudei|vi|cobri|aprendi|passei)\b"
    # "o que falta" PRECISA de escopo de estudo ou de fim de frase: "o que falta
    # para configurar o crime de peculato?" é pergunta de matéria, e calar a
    # busca nela seria trocar um defeito por outro pior.
    r"|\bo\s+que\s+(?:me\s+)?(?:falta|est[áa]\s+faltando|ta\s+faltando)\b"
    r"(?:[^?.!]{0,30}\b(?:edital|mat[ée]ria|disciplina|t[óo]pico|conte[úu]do|"
    r"estudar|ver|prova|assunto)\b|\s*[?.!]*$)"
    r"|\bfalta(?:m|ndo)?\s+(?:pra|para)\s+(?:eu\s+|mim\s+)?(?:zerar|terminar|fechar|"
    r"acabar|concluir)\b"
    r"|\bcomo\s+(?:eu\s+)?(?:estou|to|t[ôo])\s+(?:indo|me\s+saindo)\b"
    r"|\bmeu[s]?\s+(?:desempenho|progresso|rendimento|aproveitamento|n[úu]meros|"
    r"percentual|avan[çc]o|hist[óo]rico)\b"
    r"|\bminha\s+(?:cobertura|evolu[çc][ãa]o|m[ée]dia|ofensiva)\b"
    r")")


def sobre_desempenho(fala: str) -> bool:
    """A pergunta é sobre o PRÓPRIO progresso do aluno?

    Sendo, `socratic.explicar` não busca material: a resposta sai dos números
    que já viajam no prompt. Não buscar é o conserto inteiro — o que incomodou
    não foi o texto da resposta, foi a lista de fontes dizendo que a contagem de
    tentativas dele veio de uma apostila de princípios.

    Falso negativo aqui é barato (volta a buscar, como era até agora); falso
    POSITIVO cala a busca numa pergunta de conteúdo, então a regra pede
    interrogativa explícita ou possessivo de primeira pessoa, nunca só o verbo.
    """
    return bool(_PROGRESSO.search(fala or ""))


# ---------------------------------------------------------------------------
# "VOCÊ LEMBRA O QUE A GENTE ESTUDOU?" — pergunta sobre o APP, não sobre matéria
# ---------------------------------------------------------------------------
#
# Relatado com log: "você consegue me dizer quando foi a última vez que a gente
# conversou sobre isso?" recuperou CP arts. 214, 216, 220, 223, 224 — crimes
# sexuais, numa conversa sobre papiloscopia. A busca acertou as palavras
# ("conversou", "última vez") e errou tudo o mais, pelo mesmo mecanismo de
# sempre: k-vizinhos sem piso de relevância não devolve vazio.
#
# É irmã de `sobre_desempenho` e ficou separada de propósito: uma pergunta sobre
# o QUE ele estudou se responde com os números; esta se responde dizendo o que o
# sistema guarda. As duas têm em comum só o fato de a busca não ter o que fazer
# nelas.
RE_MEMORIA = re.compile(
    r"(?i)("
    r"\bvoc[êe]\s+(?:se\s+)?(?:lembra|recorda|guarda|tem)\b[^?.!]{0,30}"
    r"\b(?:mem[óo]ria|hist[óo]rico|conversas?|sess[õo]es|estudamos|estudei|falamos)\b"
    r"|\b(?:quando|qual\s+dia|que\s+dia)\b[^?.!]{0,40}"
    r"\b(?:a\s+gente|n[óo]s|voc[êe]\s+e\s+eu)\b[^?.!]{0,20}"
    r"\b(?:conversamos|conversou|falamos|estudamos|vimos)\b"
    r"|\bvoc[êe]\s+(?:n[ãa]o\s+)?(?:tem|guarda|salva|grava)\b[^?.!]{0,20}"
    r"\b(?:mem[óo]ria|hist[óo]rico|registro)\b"
    r"|\b[úu]ltima\s+vez\s+que\s+(?:a\s+gente|n[óo]s|eu)\b"
    r")")


def sobre_memoria(fala: str) -> bool:
    """A pergunta é sobre o que o SISTEMA guarda, não sobre a matéria?"""
    return bool(RE_MEMORIA.search(fala or ""))


# DESABAFO NÃO É CONSULTA. Relato do dono: "o cara pode vir aqui e querer só
# desabafar, nem por isso você precisa puxar nada do material". E a busca não
# fica de fora sozinha: "to cansado, não aguento mais estudar" tem "cansado" e
# "aguento" como palavras de conteúdo, então virava consulta e devolvia seis
# trechos de lei debaixo de um desabafo — o retrato do robô que o produto não
# quer ser.
#
# Primeira pessoa é o que separa desabafo de matéria: "cansaço" aparece em
# jornada de trabalho na 8.112 e em excludentes de culpabilidade; "tô cansado"
# não aparece em lei nenhuma.
RE_DESABAFO = re.compile(
    r"(?i)("
    r"\b(?:t[ôo]|to|estou|tava|tô\s+muito|ando)\s+(?:muito\s+|meio\s+|bem\s+)?"
    r"(?:cansad[oa]|exaust[oa]|desanimad[oa]|perdid[oa]|travad[oa]|ansios[oa]|"
    r"estressad[oa]|sem\s+cabe[çc]a|sem\s+[âa]nimo|de\s+saco\s+cheio)\b"
    r"|\bn[ãa]o\s+(?:aguento|consigo|t[ôo]\s+conseguindo|dou\s+conta)\b"
    r"|\b(?:desisti|vou\s+desistir|t[ôo]\s+surtando|surtando|pirando)\b"
    r"|\b(?:que\s+dia|semana)\s+(?:dif[íi]cil|horr[íi]vel|pesad[oa])\b"
    r"|\bdesabafar\b"
    r")")


def desabafo(fala: str) -> bool:
    """A fala é desabafo, não pedido de matéria?

    Não decide o que RESPONDER — isso é do prompt, que já tem a regra de tom.
    Decide só que não há o que buscar: seis artigos debaixo de "tô cansado" é
    o sistema respondendo a uma pessoa com um índice remissivo.
    """
    return bool(RE_DESABAFO.search(fala or ""))


# PERGUNTA SOBRE O SISTEMA NÃO BUSCA MATERIAL. Medido no cenário `meta`: "como
# você funciona?" passava por `em_foco` inteira, virava consulta vetorial e
# devolvia seis trechos de lei sorteados — e seis artigos no prompt são um
# convite pro modelo discorrer sobre eles debaixo de uma pergunta que não é de
# matéria. É o mesmo mecanismo de `sobre_memoria` e `desabafo`: k-vizinhos sem
# piso de relevância nunca devolve vazio.
#
# Irmã de `sobre_memoria` e separada dela de propósito: "você lembra do que eu
# estudei?" se responde com o registro do aluno; esta se responde dizendo o que
# você é, em uma linha, sem abrir o manual do app.
#
# O ALVO É "VOCÊ", NÃO "COMO FUNCIONA". "como funciona a prescrição?" e "de
# onde vem a competência do STF?" são pedido de MATÉRIA e não podem cair aqui —
# por isso cada alternativa exige o pronome de segunda pessoa ou a palavra que
# só cabe na máquina (IA, robô, modelo, chatbot).
RE_SISTEMA = re.compile(
    r"(?i)("
    r"\bcomo\s+(?:voc[êe]|tu)\s+(?:funciona|trabalha|faz|pensa|responde|foi\s+feit[oa])\b"
    r"|\bde\s+onde\s+(?:voc[êe]|tu)\s+(?:tira|tirou|pega|puxa|busca|saca)\b"
    r"|\bvoc[êe]\s+[ée]\s+(?:uma\s+)?(?:ia|i\.a|intelig[êe]ncia\s+artificial|rob[ôo]|"
    r"m[áa]quina|chatgpt|gpt|gemini|modelo|chatbot|bot)\b"
    r"|\b(?:quem|o\s+que)\s+(?:te|lhe)\s+(?:criou|fez|treinou|programou)\b"
    r"|\bvoc[êe]\s+(?:[ée]\s+)?(?:humano|pessoa|professor\s+de\s+verdade|gente)\b"
    r"|\bque\s+(?:ia|modelo|intelig[êe]ncia)\s+(?:voc[êe]\s+)?(?:usa|[ée])\b"
    r")")


def sobre_o_sistema(fala: str) -> bool:
    """A pergunta é sobre o que VOCÊ é, não sobre a matéria?

    Não decide o que responder — isso é do prompt, que tem a regra de não abrir
    o manual do app. Decide só que a busca não tem o que fazer aqui.
    """
    return bool(RE_SISTEMA.search(fala or ""))


def dispensa_busca(fala: str) -> bool:
    """Pergunta que não tem o que fazer com material recuperado.

    Porta ÚNICA pra quem chama: a rota pergunta uma coisa só, e acrescentar um
    terceiro caso amanhã não exige mexer em `socratic.explicar` de novo.
    """
    return (sobre_desempenho(fala) or sobre_memoria(fala) or desabafo(fala)
            or sobre_o_sistema(fala))
