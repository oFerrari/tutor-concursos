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

VERSAO = "pedido-v19"

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

# "ITEM" DO PROGRAMA NÃO É ITEM CERTO/ERRADO. "Próximo item do edital", "item por
# item", "item 2.1" falam do edital; com a leitura na ordem do edital (035) elas
# viraram fala comum, e "item" bastava para gerar duas questões (28/09/2026).
RE_ITEM_DO_PROGRAMA = re.compile(
    r"(?i)\bit(?:em|ens)\s+(?:do|da|de|deste|desse)\s+(?:edital|programa|conte[uú]do|mat[eé]ria)\b"
    r"|\bitem\s+(?:por|a)\s+item\b|\bpr[oó]xim[oa]s?\s+it(?:em|ens)\b|\bitem\s+\d")

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


RE_NUMERO_COM_UNIDADE = re.compile(
    r"(?i)\b\d+\s*(?:minutos?|min\b|horas?|h\b|dias?|semanas?|meses|m[êe]s|anos?|%|por\s*cento|"
    r"p[áa]ginas?|reais|pontos?)")


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
    # Número com UNIDADE não é quantidade: "tenho 20 minutos e quero questões" pede o
    # padrão, não cinco (avaliação offline de 03/10/2026).
    texto = RE_NUMERO_COM_UNIDADE.sub(" ", fala or "")
    fala = texto
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
# A forma elíptica é CURTA. Medido em 28/09/2026: o aluno colou um enunciado que
# começava com "Um levantamento interno realizado na Guarda Municipal...", logo
# depois de um turno de treino, e o "Um" casou com `RE_CONTINUA` como se fosse
# "manda uma". Saiu um card de Proposições debaixo da questão de conjuntos dele.
MAX_PALAVRAS_ELIPTICA = 6


# "E DE CONJUNTOS?" logo depois de um pedido: o mesmo pedido, outro assunto
# (bateria longa, 03/10/2026: não gerava nada).
# Só "de"/"sobre": "e no processo penal?" é TROCA de matéria, não pedido (teste
# `test_assunto_troca_de_disciplina`).
RE_ELIPTICA_ASSUNTO = re.compile(r"(?i)^\s*(?:e|agora|ent[ãa]o|tamb[ée]m)\s+(?:de|sobre|do|da|dos|das)\s+\w")


def _eliptica(fala: str) -> bool:
    fala = (fala or "").strip()
    return bool(RE_CONTINUA.match(fala) or RE_ELIPTICA_ASSUNTO.match(fala)) \
        and len(fala.split()) <= MAX_PALAVRAS_ELIPTICA


# O adiamento, e o que ele governa. Curta e fechada como as outras listas deste
# módulo: quem carrega a decisão é a POSIÇÃO (o marcador antes da palavra de
# treino), não o vocabulário.
PALAVRA_TREINO_RE = r"quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|it(?:em|ens)|treino|treinar|simulados?"
RE_ADIADO = re.compile(
    r"(?i)\b(?:depois|mais\s+tarde|mais\s+pra\s+frente|em\s+seguida|no\s+fim|ao\s+final|"
    r"talvez|quem\s+sabe|se\s+der|futuramente)\b[^.!?]{0,40}?"
    r"\b(quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|it(?:em|ens)|treino|treinar|simulado)\b")

# QUER ESCOLHER O ASSUNTO ANTES DE TREINAR. A palavra "questões" aparece, mas
# ainda não há ordem de geração: "quero questões de Ciências Forenses; quais
# são os assuntos?" pede o mapa para então escolher. Gerar na hora faz o app
# decidir por ele — foi exatamente o relato que trouxe esta regra.
RE_ESCOLHA_ASSUNTO = re.compile(
    r"(?i)\b(?:quais?|que)\s+(?:s[ãa]o\s+)?(?:os\s+|as\s+)?"
    r"(?:assuntos?|temas?|t[óo]picos?|conte[úu]dos?)\b")


# ADIADO DEPOIS DA PALAVRA: "quero uma questão, mas só depois da explicação". O
# adiamento vem atrás, e é CONDIÇÃO ("só depois de", "depois que", "após a"). Sem
# preposição é sequência, e o pedido vale agora: "me dá 5 questões, depois a gente
# vê a teoria" (avaliação offline de 03/10/2026).
RE_ADIADO_DEPOIS = re.compile(
    rf"(?i)\b(?:{PALAVRA_TREINO_RE})\b[^.!?]{{0,60}}?\b(?:s[óo]\s+)?"
    r"(?:depois\s+(?:d[aoe]s?|que)|ap[óo]s\s+(?:a|o|as|os|voc[êe]))\b")


def _adiado(fala: str) -> bool:
    """A fala fala de treino PRA DEPOIS, não pra agora?"""
    return bool(RE_ADIADO.search(fala or "") or RE_ADIADO_DEPOIS.search(fala or ""))


# TERMO JURÍDICO COM "QUESTÃO": "questão prejudicial", "questão de ordem" são
# instituto, não pedido de treino. "Explique o que é uma questão prejudicial no
# processo penal" gerava cartão (avaliação offline de 03/10/2026). Lista fechada
# e sem "de direito"/"de fato": "questões de direito penal" é pedido.
RE_TERMO_JURIDICO = re.compile(
    r"(?i)\bquest(?:[ãa]o|[õo]es)\s+(?:prejudicia(?:l|is)|de\s+ordem|incidenta(?:l|is)|"
    r"preliminar(?:es)?|de\s+alta\s+indaga[çc][ãa]o)\b")


# PEDIDO NEGADO NÃO É PEDIDO. Relatado na bateria de 22/09/2026: "Tenho 20
# minutos por dia. Só quero planejar a semana, sem iniciar aula ou questões
# agora." gerou cinco questões — `treino("não quero questões")` devolvia
# {"quantidade": 2}. A palavra estava lá; a ordem era a contrária.
#
# Mesmo formato de `_adiado`: a negação só vale quando GOVERNA a palavra de
# treino, e só dentro da mesma oração — vírgula, ponto e "mas" encerram o
# alcance. "não entendi, me dá mais questões" nega o entender, não o pedido.
PALAVRA_TREINO = r"quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|it(?:em|ens)|treino|treinar|simulados?"
RE_PALAVRA_TREINO = re.compile(rf"(?i)\b(?:{PALAVRA_TREINO})\b")
RE_NEGACAO = re.compile(
    r"(?i)\b(?:n[ãa]o|sem|nem|nada\s+de|chega\s+de|par[ae]\s+de|dispenso)\b")
RE_FIM_DE_ORACAO = re.compile(r"(?i)[,.;:!?]|\bmas\b")
# Verbo de pedir ENTRE a negação e a palavra de treino devolve o pedido: em
# "sem dica me dá 3 questões" o "sem" nega a dica e o "me dá" pede as questões.
# Só não devolve quando vem colado à negação — "não me dá questões" e "não
# quero questões" são a própria recusa.
RE_VERBO_DE_PEDIR = re.compile(
    r"(?i)\b(?:me\s+)?(?:d[áa]|dar|manda|mande|mandar|traz|traga|trazer|passa|passe|"
    r"passar|gera|gere|gerar|fa[çz]a|fazer|cria|crie|criar|solta|solte|quero|queria)\b")
# Negação em pergunta retórica é pedido: "por que você não me dá questões?".
RE_PERGUNTA_RETORICA = re.compile(r"(?i)\bpor\s*qu[eê]\s+(?:voc[êe]\s+)?n[ãa]o\b")


def _negado(fala: str) -> bool:
    """A fala RECUSA o treino em vez de pedi-lo?"""
    if not fala or RE_PERGUNTA_RETORICA.search(fala):
        return False
    for m in RE_PALAVRA_TREINO.finditer(fala):
        antes = RE_FIM_DE_ORACAO.split(fala[:m.start()])[-1]
        negacoes = list(RE_NEGACAO.finditer(antes))
        if not negacoes:
            continue
        entre = antes[negacoes[-1].end():]
        verbo = RE_VERBO_DE_PEDIR.search(entre)
        if verbo is None or not entre[:verbo.start()].strip():
            return True
    return False


# PEDIDO DE RESOLUÇÃO — o aluno quer VER a questão resolvida, não receber outra.
#
# Medido em 28/09/2026: "resolva pra mim questões de probabilidade" casou com
# `RE_TREINO` pela palavra "questões" e gerou dois cards para ELE responder; um
# deles saiu da apresentação do curso. E um enunciado colado inteiro, com
# alternativas, é o mesmo pedido sem o verbo: "resolve isto".
#
# O verbo é IMPERATIVO dirigido ao tutor ("resolva", "resolve essa", "me mostra
# como resolve"). "quero questões PARA RESOLVER" continua sendo treino: ali quem
# resolve é ele.
RE_RESOLUCAO = re.compile(
    r"(?i)("
    # O objeto precisa ser QUESTÃO (ou "isso", "pra mim"): "como o STF resolve o
    # conflito?" é pergunta de matéria, não pedido de resolução.
    r"\bresolv[ae]\s+(?:pra\s+mim|para\s+mim|p/\s*mim|a[íi]\b|isso|isto|"
    r"(?:(?:ess[ae]s?|est[ae]s?|as?|os?|umas?|duas|dois|tr[êe]s|\d+)\s+)?(?:\w+\s+)?"
    r"(?:quest|exerc|problema|conta|equa|item|itens))"
    # "quero que vc resolva", "resolve aí", "resolve pra mim?": o verbo no FIM da
    # fala é o pedido inteiro (medido: fala real de 28/09/2026 que não casava).
    r"|^\s*(?:agora\s+|ent[ãa]o\s+|pode\s+|por\s+favor\s+|s[óo]\s+)?resolv[ae]\s*(?:a[íi]|vc|voc[êe]|tu)?\s*[?.!]*\s*$"
    r"|\bque\s+(?:vc|voc[êe]|tu)\s+(?:resolva|calcule|fa[çc]a\s+a\s+conta)\b"
    r"|\bme\s+(?:mostr[ae]|ensin[ae]|explic[ae])\s+(?:como\s+)?(?:se\s+)?(?:resolv|calcul|faz\s+(?:a|essa)\s+conta)"
    r"|\bcomo\s+(?:eu\s+)?(?:se\s+)?(?:resolv[eo]|calcul[ao]|fa[çz]o\s+(?:a|essa)\s+conta)\b"
    r"|\b(?:quest[õo]es|quest[ãa]o|exerc[íi]cios?|exemplos?)\s+(?:resolvid[ao]s?|comentad[ao]s?)\b"
    r"|\bcad[êe]\s+(?:o|a)\s+(?:c[áa]lculo|conta|f[óo]rmula|resolu[çc][ãa]o)\b"
    # A QUESTÃO QUE JÁ ESTÁ NA CONVERSA (01/10/2026): "e da questão anterior?" foi
    # lido como pedido de 2 questões NOVAS e trouxe cartões de Língua Portuguesa
    # no meio de Raciocínio Lógico; "sim já com a resolução" (aceitando a questão
    # oferecida) não virou resolução.
    r"|\bquest[ãa]o\s+(?:anterior|de\s+cima|passada|acima|de\s+antes)\b"
    r"|\bresolv[ae]\s+(?:a\s+|tamb[ée]m\s+a\s+)?(?:anterior|de\s+cima|outra|primeira|segunda)\b"
    r"|\bcom\s+(?:a\s+)?resolu[çc][ãa]o\b|\bj[áa]\s+resolvid[ao]s?\b"
    r"|\b(?:mostr[ae]|fa[çz]a|faz)\s+(?:a|essa)\s+(?:conta|resolu[çc][ãa]o)\b"
    r"|\bcalcul[ae]\s+(?:pra\s+mim|a|o|quant)"
    r"|\bqual\s+(?:[ée]\s+)?(?:o\s+)?gabarito\b"
    r")")

# ENUNCIADO COLADO: texto longo com alternativas em sequência (uma letra por
# linha, "A)", "(B)") ou com a moldura de prova ("Alternativas", "julgue o
# item", "assinale"). Um aluno não escreve isso para conversar.
RE_ALTERNATIVA_NA_LINHA = re.compile(r"(?m)^\s*\(?[A-Ea-e]\s*[).\-–:]?\s*(?:$|\S)")
RE_MOLDURA_DE_PROVA = re.compile(
    r"(?i)\b(?:alternativas|julgue\s+o\s+item|assinale\s+a|marque\s+a\s+(?:op|alt)|"
    r"certo\s+ou\s+errado)\b")
MIN_CHARS_ENUNCIADO = 120


# PROBLEMA COLADO SEM ALTERNATIVAS: enunciado comprido, com dados numéricos, que
# termina em pergunta. Medido: a mesma questão da guarda municipal, colada sem as
# alternativas, virou um parágrafo corrido que terminava perguntando outra coisa.
MIN_CHARS_PROBLEMA = 200
RE_NUMERO = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def questao_colada(fala: str) -> bool:
    fala = fala or ""
    if len(fala) < MIN_CHARS_ENUNCIADO:
        return False
    if (len(fala) >= MIN_CHARS_PROBLEMA and "?" in fala[-200:]
            and len(RE_NUMERO.findall(fala)) >= 2):
        return True
    letras = [m.group(0).strip()[:2] for m in RE_ALTERNATIVA_NA_LINHA.finditer(fala)
              if re.match(r"\(?[A-Ea-e](?:\W|$)", m.group(0).strip())]
    return len(letras) >= 3 or bool(RE_MOLDURA_DE_PROVA.search(fala))


def resolucao(fala: str) -> bool:
    """O aluno pediu para o TUTOR resolver (ou mostrar a conta de) uma questão?

    Não gera nada: decide que o turno é de resolução — passo a passo, com a
    conta, o gabarito e o macete — e que nenhum card de treino sai dele."""
    return bool(RE_RESOLUCAO.search(fala or "")) or questao_colada(fala)


# PEDIDO DE FORMA VISUAL — mapa mental, esquema, tabela, quadro. Não muda o que
# buscar, muda como escrever: `socratic` acrescenta a notação que a tela desenha.
RE_FORMATO_VISUAL = re.compile(
    r"(?i)\b(?:mapas?\s+ment(?:al|ais)|esquemas?|esquematiz|tabelas?|quadros?\s+"
    r"(?:comparativos?|resumos?|sin[óo]ticos?)|diagramas?|fluxogramas?|organogramas?|bizus?|"
    r"f[óo]rmulas?)\b")


def formato_visual(fala: str) -> bool:
    return bool(RE_FORMATO_VISUAL.search(fala or ""))


# ACEITAR A OFERTA É PEDIR. Medido em 28/09/2026 (bateria de descoberta, fala
# real): o tutor perguntou se o aluno queria ver questões, ele disse que sim, e
# nenhum cartão veio — o prompt mandava o tutor OFERECER e esperar o pedido
# "com todas as letras", e a resposta à oferta não contava como pedido. A oferta
# é reconhecida na fala do TUTOR (a última), e o aceite é curto: "sim", "manda".
RE_OFERTA_DE_QUESTOES = re.compile(
    r"(?i)\b(?:quer(?:\s+que\s+eu)?|posso|topa\s+que\s+eu|vamos|bora)\s+"
    r"(?:te\s+)?(?:monte|montar|prepare|preparar|mande|mandar|traga|trazer|gere|gerar|passe|passar|"
    r"fa[çc]a|fazer|separe|separar|d[êe]|dar|resolver|treinar|praticar)\b[^?]{0,80}?"
    r"\b(?:quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|itens|treino|treinar|praticar)")
RE_ACEITE = re.compile(
    r"(?i)^\s*(?:sim|s|ss|claro|pode|pode\s+ser|bora|vamos|manda|mande|quero|ok|okay|beleza|blz|"
    r"isso|com\s+certeza|por\s+favor|fechou|demorou|aham|uhum|opa|show|partiu|vai)\b"
    r"[\s,!.]*(?:(?:sim|pode|manda|por\s+favor|bora|quero|claro|mesmo|ai|a[íi])\b[\s,!.]*){0,3}$")


RE_CORRECAO_DE_PEDIDO = re.compile(r"(?i)\bn[ãa]o\s+(?:te\s+)?pedi\b[^.?!]*?\b(?:eu\s+)?pedi\b")
# Número sozinho respondendo à oferta: "quer que eu monte três?" → "5". Conversa
# real de 02/10/2026: o "5" seguiu como conversa e o tutor voltou à matéria anterior.
RE_SO_QUANTIDADE = re.compile(
    r"(?i)^\s*(?:(?:sim|pode|manda|quero)[\s,]+)?(\d{1,2}|uma?|duas|dois|tr[êe]s|quatro|cinco)"
    r"(?:\s+(?:quest(?:[ãa]o|[õo]es)|por\s+favor|pf|pfv))?[\s.!]*$")


def assunto_da_oferta(ultima_do_tutor: str | None) -> str | None:
    """O assunto que a OFERTA do tutor nomeia ("Quer que eu monte três questões de
    conectivos?" → "conectivos"). É o assunto do aceite: "5" ou "sim" não dizem nada,
    e a fala anterior do aluno podia ser "chega de questões" (bateria longa, 03/10/2026)."""
    m = RE_OFERTA_DE_QUESTOES.search(ultima_do_tutor or "")
    if not m:
        return None
    frase = next((f for f in re.split(r"(?<=[.!?])\s+", ultima_do_tutor) if RE_OFERTA_DE_QUESTOES.search(f)), "")
    resto = sem_o_pedido(re.sub(r"(?i)^.*?\b(?:quest(?:[ãa]o|[õo]es)|exerc[íi]cios?|itens)\b", "", frase))
    return _so_o_assunto(resto)


RE_BORDA_DO_ASSUNTO = re.compile(r"(?i)^(?:\s*\b(?:e|agora|ent[ãa]o|tamb[ée]m|de|sobre|do|da|dos|das|em|no|na|nos|nas)\b)+|"
                                 r"(?:\b(?:antes|agora|depois|tamb[ée]m|a[íi]|por\s+favor)\b\s*)+$")


def _so_o_assunto(texto: str | None) -> str | None:
    t = (texto or "").strip(" ?.!,")
    t = RE_BORDA_DO_ASSUNTO.sub("", t).strip(" ?.!,")
    return t or None


def assunto_eliptico(fala: str | None) -> str | None:
    """"e de conjuntos?" → "conjuntos": o assunto da forma elíptica, sem a borda."""
    if not RE_ELIPTICA_ASSUNTO.match(fala or ""):
        return None
    return _so_o_assunto(fala)


def sem_oferta_de_questoes(texto: str) -> str:
    """O texto sem a FRASE que oferece questões (para quando elas já vieram). PURO."""
    saida = texto or ""
    for f in re.split(r"(?<=[.!?])\s+", saida):
        if RE_OFERTA_DE_QUESTOES.search(f):
            saida = saida.replace(f, "")          # tira a frase, mantém os parágrafos
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", saida)).strip()


def aceitou_oferta_de_questoes(fala: str, ultima_do_tutor: str | None) -> dict | None:
    """O pedido de treino que o aceite de uma oferta representa, ou None.
    A quantidade e o formato são os que o TUTOR ofereceu ("três itens C/E") — ou
    a que o aluno respondeu com um número."""
    oferta = RE_OFERTA_DE_QUESTOES.search(ultima_do_tutor or "")
    numero = RE_SO_QUANTIDADE.match(fala or "")
    if not oferta or not (RE_ACEITE.match(fala or "") or numero):
        return None
    trecho = (ultima_do_tutor or "")[oferta.start():oferta.end() + 60]
    if numero:
        return {"quantidade": quantas(f"{numero.group(1)} questões"),
                "tipo": "certo_errado" if RE_CERTO_ERRADO.search(trecho) else None, "formal": False}
    return {"quantidade": quantas(trecho),
            "tipo": "certo_errado" if RE_CERTO_ERRADO.search(trecho) else None,
            "formal": False}


# O ASSUNTO DO PEDIDO, sem o pedido. "me manda questões de controle de
# constitucionalidade" ia à busca inteira, e "manda"/"questões" traziam o CPP 482
# ("Do Questionário e sua Votação") — medido na bateria de 29/09/2026.
RE_VOCABULARIO_DE_PEDIDO = re.compile(
    rf"(?i)\b(?:{PALAVRA_TREINO}|exerc[íi]cios?|me|mim|pra|para|eu|vc|voc[êe]|tu|pfv|pf|por\s+favor|"
    r"logo|a[íi]|agora|mais|outra|outras|umas?|duas|dois|tr[êe]s|quatro|cinco|\d+|"
    r"d[áa]|dar|manda|mande|mandar|traz|traga|passa|passe|gera|gere|faz|fa[çc]a|cria|crie|"
    r"quero|queria|preciso|bota|coloca|treinar|treino|praticar|resolver|responder|dif[íi]ceis?|"
    r"f[áa]ceis?|certo\s+ou\s+errado|alternativas?|"
    # A CONVERSA em volta do pedido: referência ("disso"), avaliação ("fácil",
    # "errada"), vocativo ("mano") e verbo de tentar. Medido em 29/09/2026: "é a RAM
    # que é volátil, bota uma questão disso" teve "disso" e "fácil" como termos
    # raros, e a questão saiu do CP.
    r"disso|disto|nisso|nisto|daquilo|naquilo|isso|isto|essa|esse|esta|este|"
    r"f[áa]cil|dif[íi]cil|errad[ao]s?|cert[ao]s?|nada|mano|cara|v[ée]i|p[ôo]|testar|tentar|"
    r"ver|saber|sei|entender|entendi|aprender|aprendi|n[íi]vel|m[ée]di[ao]|banca)\b")


def sem_o_pedido(fala: str | None) -> str:
    return " ".join(RE_VOCABULARIO_DE_PEDIDO.sub(" ", fala or "").split())


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
        if not _eliptica(fala):
            return False
    return False


RE_PEDE_EXPLICACAO = re.compile(r"(?i)\b(?:explic\w*|me\s+ensin\w*|detalh\w*|aprofund\w*)\b")
RE_PEDIDO_DIRETO = re.compile(
    rf"(?i)\b(?:(?:me\s+)?(?:d[áa]|dar|manda|mande|traz|traga|passa|passe|gera|gere|quero|queria|"
    rf"fa[çz]a|bota|coloca|solta)\b[^.!?]{{0,25}}|(?:\d+|uma|um|duas|dois|tr[êe]s|algumas|umas)\s+)"
    rf"(?:{PALAVRA_TREINO})\b")


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
    fala = RE_TERMO_JURIDICO.sub(" ", RE_ITEM_DO_PROGRAMA.sub(" ", fala))
    if not (RE_TREINO.search(fala) or RE_FORMAL.search(fala)):
        # Só a forma elíptica, e só logo depois de um turno de treino.
        if not (apos_treino and _eliptica(fala)):
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
    # CORREÇÃO DO PEDIDO: "eu não pedi questão de direito, eu pedi de informática"
    # nega a primeira matéria e PEDE a segunda. A negação colada a "questão" fazia
    # `_negado` recusar tudo (conversa real de 02/10/2026).
    if RE_CORRECAO_DE_PEDIDO.search(fala):
        return {"quantidade": quantas(fala), "tipo": "certo_errado" if RE_CERTO_ERRADO.search(fala) else None,
                "formal": False}
    if _adiado(fala) or _negado(fala):
        return None
    if RE_ESCOLHA_ASSUNTO.search(fala):
        return None
    # PEDIR RESOLUÇÃO NÃO É PEDIR TREINO: quem resolve é o tutor, na resposta.
    if resolucao(fala):
        return None
    # PEDIU EXPLICAÇÃO, e "exercício" só aparece na reclamação: "tu ja pulou
    # exercicio, explica direito essa parte de contagem" gerou cartão (bateria de
    # 29/09/2026). Com pedido de explicação, só é treino o pedido DIRETO — verbo de
    # pedir ou quantidade colados à palavra de treino.
    if RE_PEDE_EXPLICACAO.search(fala) and not RE_PEDIDO_DIRETO.search(fala):
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
    # "me explica como funciona o sistema/o app/o tutor" (01/10/2026): sem isto,
    # o pedido de explicação abria a leitura de uma apostila.
    r"|\bcomo\s+funciona\s+(?:o\s+|esse\s+|este\s+)?(?:sistema|app|aplicativo|tutor|site|chat|plataforma)\b"
    r"|\bde\s+onde\s+(?:voc[êe]|tu)\s+(?:tira|tirou|pega|puxa|busca|saca)\b"
    r"|\bvoc[êe]\s+[ée]\s+(?:uma\s+)?(?:ia|i\.a|intelig[êe]ncia\s+artificial|rob[ôo]|"
    r"m[áa]quina|chatgpt|gpt|gemini|modelo|chatbot|bot)\b"
    r"|\b(?:quem|o\s+que)\s+(?:te|lhe)\s+(?:criou|fez|treinou|programou)\b"
    r"|\bvoc[êe]\s+(?:[ée]\s+)?(?:humano|pessoa|professor\s+de\s+verdade|gente)\b"
    r"|\bque\s+(?:ia|modelo|intelig[êe]ncia)\s+(?:voc[êe]\s+)?(?:usa|[ée])\b"
    # O QUE VOCÊ SABE FAZER / O QUE TE FALTA. Medido em 28/09/2026: "do que vc
    # é capaz de fazer? como tutor" e "o que falta pra vc se transforma num
    # tutor completo?" foram à busca e voltaram seis trechos de Poder
    # Judiciário e Proposições como CONSULTADO — e a segunda virou uma pergunta
    # de Constitucional que ninguém fez.
    r"|\b(?:do\s+)?que\s+(?:voc[êe]|vc|tu)\s+(?:[ée]|es)\s+capaz\b"
    r"|\bo\s+que\s+(?:voc[êe]|vc|tu)\s+(?:sabe|consegue|pode)\s+(?:fazer|me\s+ajudar)\b"
    r"|\bcomo\s+(?:voc[êe]|vc|tu)\s+(?:pode|consegue)\s+me\s+ajudar\b"
    r"|\b(?:suas|tuas)\s+(?:fun[çc][õo]es|funcionalidades|capacidades|limita[çc][õo]es)\b"
    r"|\bfalta\s+(?:pra|para)\s+(?:voc[êe]|vc|tu)\s+(?:ser|se\s+tornar|virar|se\s+transforma(?:r)?|"
    r"ficar)\b"
    r")")

# PERGUNTA SOBRE A BIBLIOTECA também não busca: "quais apostilas eu tenho?" se
# responde com `### Material que o aluno subiu`, que já vai no prompt inteiro.
# Buscando, seis trechos sorteados apareciam como CONSULTADO debaixo de uma
# lista de arquivos. "o que tem no acervo SOBRE peculato" é pergunta de
# matéria, e por isso "sobre" fica de fora.
RE_BIBLIOTECA = re.compile(
    r"(?i)\b(?:quais?|que|quantos|quantas|o\s+que)\b[^?.!]{0,25}"
    r"\b(?:materia(?:l|is)|apostilas?|pdfs?|arquivos?|acervo|biblioteca)\b[^?.!]{0,25}"
    r"\b(?:tenho|eu\s+tenho|tem|h[áa]|subi|existe|existem|voc[êe]\s+tem)\b"
    r"|\b(?:o\s+que|que)\s+(?:voc[êe]|vc)\s+tem\s+de\s+(?:materia(?:l|is)|apostilas?)\b"
    r"|\b(?:o\s+que|que)\s+(?:tem|h[áa]|existe)\s+(?:no|na)\s+(?:meu\s+|minha\s+|seu\s+|sua\s+)?"
    r"(?:acervo|biblioteca|material)\s*[?.!]*$"
    # O verbo ANTES do nome, como se fala no celular: "quais a gente tem material?",
    # "saber sobre o que você tem material" (bateria de 29/09/2026, falas reais; a
    # segunda foi à busca e pôs a Lei 8.112 art. 5º como CONSULTADO da lista de
    # apostilas).
    r"|\b(?:quais?|que)\b[^?.!]{0,20}\b(?:tenho|tem|temos|h[áa])\s+(?:de\s+)?"
    r"(?:materia(?:l|is)|apostilas?|pdfs?|arquivos?)\b")


def sobre_a_biblioteca(fala: str) -> bool:
    """A pergunta é sobre QUAIS materiais ele tem, e não sobre o que eles dizem?

    "sobre" só tira da biblioteca quando introduz ASSUNTO ("o que tem no acervo
    sobre peculato"); "saber sobre o que você tem" é a própria pergunta."""
    fala = fala or ""
    return bool(RE_BIBLIOTECA.search(fala)) and not re.search(
        r"(?i)\bsobre\b(?!\s+(?:o\s+que|quais?)\b)", fala)


def sobre_o_sistema(fala: str) -> bool:
    """A pergunta é sobre o que VOCÊ é, não sobre a matéria?

    Não decide o que responder — isso é do prompt, que tem a regra de não abrir
    o manual do app. Decide só que a busca não tem o que fazer aqui.
    """
    return bool(RE_SISTEMA.search(fala or ""))


# "DE ONDE VEIO ISSO?" — a fonte da resposta ANTERIOR, não um assunto novo.
# Medido em 28/09/2026 (bateria de descoberta, fala real): "qual aula e página do
# meu material sustentam o que você explicou?" foi à busca, voltou com seis
# artigos do CPP, e a resposta disse "a aula 00 aborda isso nos primeiros
# tópicos" — sem página. A página estava gravada nas fontes do turno anterior.
# Exige a REFERÊNCIA ao que foi dito ("isso", "o que você explicou"): "onde está
# nacionalidade no meu material?" é pergunta de localização, e fica com a busca.
RE_FONTE_DA_RESPOSTA = re.compile(
    r"(?i)\b(?:p[áa]ginas?|aulas?|apostilas?|materia(?:l|is)|fontes?|trechos?)\b[^?]{0,60}"
    r"\b(?:sustent\w*|embas\w*|fundament\w*|isso|isto|explicou|disse|falou|"
    r"(?:sua|essa|esta)\s+(?:resposta|explica[çc][ãa]o))\b"
    r"|\bde\s+onde\s+(?:voc[êe]\s+|vc\s+)?(?:tirou|veio|saiu)\s+(?:isso|isto|ess[ae]|est[ae])\b")


def pede_fonte(fala: str) -> bool:
    return bool(RE_FONTE_DA_RESPOSTA.search(fala or ""))


# CONVERSA FIADA COM RISADA não é consulta. Medido na bateria de 29/09/2026: "se ta
# descolado em chat kkk" foi à busca — "descolado" e "chat" passam por palavra de
# conteúdo — e a resposta puxou tabela-verdade. Riso + fala curta + nenhum pedido
# de conteúdo; "kkk mas me explica peculato" continua sendo consulta.
RE_RISO = re.compile(r"(?i)(?:^|\s)(?:k{3,}|rs(?:rs)*|ha(?:ha)+|he(?:he)+|hua(?:hua)*)(?=\W|$)")
RE_PEDE_CONTEUDO = re.compile(
    r"(?i)\b(?:explic\w*|me\s+(?:fala|diz|ensina|d[áa]|manda|mostra)|o\s+que\s+[ée]|como\s+(?:funciona|faz|se|[ée])|"
    r"qual|quais|quero|queria|resolv\w*|estud\w*|aula|quest(?:[ãa]o|[õo]es)|artigo|art\.|lei\b)")
MAX_PALAVRAS_FIADA = 15


def conversa_fiada(fala: str) -> bool:
    fala = fala or ""
    return (bool(RE_RISO.search(fala)) and not RE_PEDE_CONTEUDO.search(fala)
            and len(fala.split()) <= MAX_PALAVRAS_FIADA)


def dispensa_busca(fala: str) -> bool:
    """Pergunta que não tem o que fazer com material recuperado.

    Porta ÚNICA pra quem chama: a rota pergunta uma coisa só, e acrescentar um
    terceiro caso amanhã não exige mexer em `socratic.explicar` de novo.
    """
    return (sobre_desempenho(fala) or sobre_memoria(fala) or desabafo(fala)
            or sobre_o_sistema(fala) or sobre_a_biblioteca(fala) or pede_fonte(fala)
            or conversa_fiada(fala))
