"""
O ASSUNTO EM FOCO de uma conversa — o texto que efetivamente vai à BUSCA.

POR QUE ESTE MÓDULO EXISTE
--------------------------
A migração 014 deu memória ao MODELO e deixou o BUSCADOR amnésico. O prompt
passou a receber os 8 últimos turnos; `retrieval.buscar` continuou recebendo a
mensagem isolada, como antes de existir conversa. E `hibrida()` não tem piso de
relevância — é k-vizinhos-mais-próximos, então SEMPRE devolve 6 chunks, por mais
alheios que sejam. Consulta sem assunto não devolve vazio: devolve lixo com cara
de resposta, que é bem pior.

Medido numa conversa real, inteira sobre eficácia e aplicabilidade das normas
constitucionais:

  · o aluno escreveu "vamos" e clicou em "quero questões sobre isto". A tela
    mandava a ÚLTIMA FALA DELE como tema, então rodou `buscar("vamos")` — e
    voltaram CP art. 352 (evasão mediante violência) e CF art. 200
    (competências do SUS). Duas questões impecavelmente fundamentadas sobre
    assunto que ninguém pediu.

  · noutro turno ele escreveu "você deveria perguntar se eu já sei algo do
    assunto... talvez seja melhor você me explicar". Voltaram CPP arts. 188,
    190, 203 e 212 — INTERROGATÓRIO e INQUIRIÇÃO. A busca acertou as palavras
    ("perguntar", "responder", "explicar") e errou o assunto por completo.

  · e no turno em que ele escreveu "eficácia limitada existem 2 tipos", a busca
    trouxe a apostila certa dele, seis vezes, e o log até trocou o rótulo de
    "consultado" pra "citado".

O terceiro caso é a prova de que o buscador NÃO está quebrado: turno com assunto
na frase acerta, turno curto ou meta devolve lixo. O defeito é a frase que
chega, não quem busca — e por isso o conserto mora aqui e não em `retrieval.py`.

O QUE ESTE MÓDULO NÃO É
-----------------------
Não é extração de tema por LLM. Custaria a cota mais escassa do projeto e 1-2s
em TODO turno pra decidir o que regra resolve — a mesma escolha já feita em
`ritmo_regras` ("intervenção proativa é regra, não o LLM decidindo quando
falar"). E resposta de modelo não se trava em teste; isto aqui se trava.

É HEURÍSTICA, e declarada como tal (mesmo espírito de `core/edital.py`): fala
curta demais pra nomear um assunto é descartada e a anterior assume o foco.
Erra pra MENOS — deixa de enriquecer a consulta — em vez de errar pra mais.

A INICIATIVA DO TURNO, E POR QUE ELA SUBSTITUIU CONTAR PALAVRAS
---------------------------------------------------------------
A versão anterior olhava só as palavras da fala. Isso levou o produto ao pior
resultado que ele já deu: uma conversa de dez minutos INTEIRA sobre Lei Maria da
Penha gerou duas questões de Direito Administrativo (L8112 art. 55, "ajuda de
custo", e art. 94, "mandato eletivo"). A consulta era

    'dependencia? não impede sim desde que haja vinculo ou afeto'

Nenhuma palavra de "lei maria da penha" — e ela estava na conversa, no SEGUNDO
turno. `CONTEUDO_SUFICIENTE` parou de enriquecer ao juntar 4 palavras de
conteúdo, e as quatro eram fragmentos de diálogo (dependencia, impede, vinculo,
afeto) que caem exatamente em pensão e ajuda de custo do estatuto do servidor. A
contagem estava certa; o que ela contava não era assunto.

Tentei consertar por limiar de tamanho e MEDI que não dá: com `FRAGMENTO = 3`,
"me explica eficácia limitada" (2 palavras de conteúdo) é classificada como
fragmento e o tutor arrasta assunto abandonado de volta; com `FRAGMENTO = 2`,
"vinculo afeto" passa por assunto e o defeito continua. `eficácia limitada` e
`vinculo afeto` têm o MESMO tamanho e um é assunto e o outro não — contagem de
palavras não separa os dois, em nenhum ponto de corte.

O que separa é ESTRUTURAL, e o banco já guarda de graça desde a 014: num diálogo
socrático o aluno RESPONDE em pedaços e o assunto é dito uma vez, no começo, e
nunca mais. Então a pergunta certa não é "esta fala é grande?", é "esta fala é
INICIATIVA ou RESPOSTA?".

O teste disso está em `e_eco`, e é o TURNO que decide: o tutor detém a iniciativa
enquanto está perguntando, e o aluno a retoma com um pedido explícito. Sendo
resposta, a consulta é o turno do TUTOR — que é onde o assunto está escrito por
extenso, e não em pedaços.

A IDEIA QUE PARECIA MELHOR QUE ESSA, E MORREU MEDIDA
----------------------------------------------------
Antes de chegar em `pede_assunto` eu escrevi (e este docstring afirmou, por um
patch) que bastava NOVIDADE LEXICAL: "é eco se não acrescenta nenhuma palavra de
conteúdo além das que o tutor acabou de usar". Sem limiar, sem lista, elegante —
e ERRADA. Ela "passou" nas sete falas do log porque eu comparei cada fala do
aluno com o turno do tutor SEGUINTE, o que repete a resposta dele de volta
("Exato, a unidade doméstica ou a **dependência econômica**..."). Circular, e
indisponível na hora de decidir. Pareando com o turno ANTERIOR — o único que
existe quando a decisão é tomada — ela cai em 3 das 6 respostas:

    ECO                          <- 'não'
    ECO                          <- 'não impede'
    NOVAS ['dependencia']        <- 'dependencia?'
    NOVAS ['afeto','vinculo']    <- 'sim desde que haja vinculo ou afeto'
    NOVAS ['ambito','crime',…]   <- 'quando nao for crime realizado em ambito
                                     doméstico?'

O motivo é óbvio depois de ver: RESPONDER a uma pergunta de conhecimento É dizer
a palavra que o tutor não disse — era exatamente o que ele estava perguntando
("qual o critério, além da coabitação e do vínculo de afeto?" → "dependencia?").
Novidade lexical mede ACERTO do aluno, não iniciativa. Fica registrado porque a
próxima pessoa vai ter a mesma ideia, e ela é boa o bastante pra convencer.
"""
import re
import unicodedata

# A MESMA regra de citação que `por_dispositivo` usa pra decidir se a pergunta
# aponta um artigo. Reusar em vez de copiar: duas versões de "isto é uma
# citação?" divergem, e o sintoma seria a busca por dispositivo funcionando num
# caminho e não no outro.
from . import pedido
from .retrieval import RE_CITACAO

VERSAO = "assunto-v16"

# Teto da consulta. Embedding é MÉDIA do que entra: parede de texto dilui o
# assunto exatamente como o art. 37 (13.059 caracteres) já se dilui no próprio
# vetor — o viés que `PESO_LEXICAL = 1.5` existe pra corrigir. Enriquecer a
# consulta é bom; afogá-la não.
MAX_CHARS = 400

# Teto de turnos ANTERIORES do aluno que podem entrar junto do atual.
TURNOS_EXTRA = 2

# Mas o que decide de fato é este: enriquece ENQUANTO a consulta ainda estiver
# fraca, e para quando ela já disser um assunto. Contar turnos não bastava, e os
# dois casos que provaram isso estão em `tests/test_assunto.py`:
#
#   · "queria saber como a fgv cobra" é substantiva e não tem assunto PRÓPRIO
#     (uma palavra de conteúdo). Um turno de reforço não alcançava "eficácia
#     limitada" — precisava de dois.
#   · numa conversa que começou em Direito Penal e migrou pra Constitucional,
#     dois turnos de reforço trazem PECULATO de volta pra dentro da busca, e a
#     questão sai da matéria que o aluno já abandonou.
#
# Nenhum número fixo de turnos serve pros dois. "Pare quando já houver assunto"
# serve, porque é a pergunta certa: o reforço existe pra suprir falta de
# assunto, não pra somar contexto por hábito.
CONTEUDO_SUFICIENTE = 4

# Palavras de conteúdo necessárias pra uma fala "dizer" um assunto. UMA basta, e
# a assimetria dos erros é que decide isso: exigir duas descartaria "matar
# alguém" (uma palavra de conteúdo, e a pergunta mais literal que existe sobre o
# art. 121), e fala descartada sai da consulta INTEIRA. Guardar uma fala fraca
# só dilui um pouco; descartar uma pergunta real faz o aluno receber resposta
# sobre outra coisa. O trabalho de separar "vamos" de uma pergunta curta é da
# lista `VAZIAS`, não do limiar.
MIN_CONTEUDO = 1
MIN_LETRAS = 3

# Verbos com que o aluno RETOMA a iniciativa. Casada contra a fala crua, não
# contra `palavras_de_conteudo` — várias delas são (corretamente) palavras
# vazias pra efeito de busca. Fechada e curta de propósito: quem carrega a
# decisão é a estrutura do turno, não esta lista (ver `e_eco`).
PEDIDO = set("""
quero queria gostaria pode podia poderia explica explique explicar explicame
fala fale falar diga dizer ensina ensine ensinar mostra mostre mostrar
estudar estuda ver vermos vamos comecar iniciar entender entenda aprender
duvida pergunta perguntar sobre assunto materia
""".split())

# Estruturais + o vocabulário de CONVERSA e de META-conversa. Não é lista de
# stopwords de linguística: é a lista do que aparece quando o aluno fala SOBRE o
# estudo em vez de falar da MATÉRIA. Foi justamente esse vocabulário que trouxe
# os artigos de interrogatório do CPP.
#
# Fica de fora de propósito o que parece meta e é matéria: "direito", "penal",
# "tipo" (tipo penal), "pena", "norma", "prazo". Errar aqui é caro nos dois
# sentidos, e a assimetria manda: manter uma palavra a mais só dilui um pouco a
# consulta; tirar "direito" cegaria a busca pro nome de metade das disciplinas.
VAZIAS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos
pelas para pra pro com sem sob sobre ate entre e ou mas porem porque pois que se
como quando onde qual quais quem cujo cuja ja nao sim tambem so muito pouco mais
menos todo toda todos todas isso isto esse essa esses essas este esta estes
estas aquele aquela aquilo ele ela eles elas eu tu voce vocês nos meu minha meus
minhas seu sua seus suas dele dela deles delas me te lhe nem ao aos la ali aqui
ser sou eh era foi fui somos sao ter tem tinha temos tenho havia estar esta
estou estao estava ir vai vou vamos vamo ia indo quero queria quer queremos
pode podia poderia posso podemos deveria deve devo devemos sei sabe saber sabia
achar acho acha achei lembro lembrava lembra lembrar entendi entendo entender
entendeu explicar explica explique explicando explicacao perguntar pergunta
perguntei responder resposta respondendo dizer diz disse falar fala falando ver
vejo veja vendo fazer faz faca fazendo dar dou prefiro preferia gostaria
obrigado obrigada ola oi bom boa bem certo errado talvez realmente verdade
assunto tema materia materias conteudo conteudos ponto pontos coisa coisas
geito jeito agora hoje amanha depois antes ainda denovo novamente melhor pior
comecar comeco continuar continua parar para vez vezes parte partes exemplo
exemplos caso casos questao questoes exercicio exercicios prova provas simulado
simulados banca bancas edital editais concurso concursos estudar estudo estudos
aula aulas cai cair cobra cobrar cobrado cobranca dica dicas duvida duvidas
algo alguem algum alguma alguns algumas nenhum nenhuma tudo nada mesmo mesma
outro outra outros outras cada qualquer oferecer oferece oferecendo seja sejam
fosse fossem sendo sido tratar trata trate tratando art artigo artigos ok
beleza entao ai ta tao pouca quase bastante primeiro segundo terceiro
noite dia tarde manha ola oi opa bora saudacoes testar testa teste testando
testes treinar treino treinando praticar pratica praticando revisar revisao
revisando
resumo resumao resumos resumido resumida resumidamente resumir resuma resume
detalhado detalhada detalhados detalhadas detalhe detalhes detalhar detalha
aprofundar aprofunda aprofunde traga trazer traz trouxe trouxesse tragam
principais
""".split())

# A TERCEIRA LEVA veio de uma conversa inteira sobre princípios administrativos
# (conversa 525), e é o mesmo defeito com palavras novas. Reproduzido com o log
# real, `em_foco` para
#
#     "queria um resumão mais detalhado com 2 exemplos de cada"
#
# devolvia A PRÓPRIA FALA somada às anteriores do aluno — "agora eu queria que
# trouxesse um resumão com tudo de uma vez" —, uma consulta sem UMA palavra de
# matéria. "resumao", "detalhado" e "trouxesse" contavam como conteúdo, então a
# fala "dizia assunto" e o reforço foi buscar mais meta-conversa. A busca
# devolveu CP art. 150 (violação de domicílio), CP art. 28 (embriaguez) e CF
# art. 220 (comunicação social) numa aula de Direito Administrativo — e o tutor
# só respondeu bem porque a regra de doutrina o deixa ensinar conceito sem
# trecho, avisando. Ele avisou: "isto é doutrina e não está no seu material".
# Estava, na apostila — só não no que a busca trouxe.
#
# "principais" entrou junto ("cite só os principais"); "citar" NÃO, e a razão é
# a assimetria de sempre: citação é ato processual no CPP, e cegar a busca pra
# ele custa mais do que a diluição que ele causa.
#
# ESTA LISTA NUNCA VAI ESTAR COMPLETA, e é importante não se enganar sobre isso:
# ela cresceu duas vezes atrás de casos reais ("vamos", depois "boa noite /
# podemos testar / bora"), e vai crescer de novo — não existe enumeração de todas
# as formas de dizer "vamos lá". O que garante o resultado NÃO é ela: é o
# fallback pra fala do TUTOR em `em_foco`, que funciona mesmo quando a lista
# falha, porque o assunto passa a vir de onde ele foi nomeado. A lista é conforto
# (consulta mais limpa quando acerta); o fallback é a garantia.


def _sem_acento(palavra: str) -> str:
    """Compara contra `VAZIAS` sem depender de o aluno acentuar. "voce" e "você"
    são a mesma palavra vazia, e ninguém digita acento com pressa.

    Isto NÃO contradiz a decisão de não instalar `unaccent` no Postgres: ali o
    custo era extensão, índice funcional e reingestão de milhares de chunks pra
    resolver uma fração do problema; aqui é uma função de três linhas sobre uma
    lista fechada que mora em memória."""
    nfkd = unicodedata.normalize("NFKD", palavra)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


RE_PALAVRA = re.compile(r"[^\W\d_]+", re.UNICODE)


# RISADA E INTERJEIÇÃO NÃO SÃO ASSUNTO, e isto entrou porque "ola boa noite se
# é que ta de noite kkk" virou consulta de busca: TODAS as outras palavras
# estavam em `VAZIAS`, sobrou "kkk", e a busca devolveu CP 111, CP 150 e a Lei
# 8.112 art. 70 pra uma saudação. Como é forma livre (kkk, kkkkkk, rsrs,
# hahaha), a lista não resolve — a REGRA resolve.
RE_RISADA = re.compile(r"(?i)^(?:k{2,}|(?:ha|he|hi|hu){2,}|(?:rs){1,}|hehe|huehue)$")


def palavras_de_conteudo(texto: str) -> list[str]:
    """As palavras da fala que carregam assunto — o resto é andaime de conversa."""
    achadas = RE_PALAVRA.findall((texto or "").lower())
    return [p for p in achadas
            if len(p) >= MIN_LETRAS and _sem_acento(p) not in VAZIAS
            and not RE_RISADA.match(p)]


def disciplina_citada(texto: str, disciplinas: list[str] | None) -> str | None:
    """Qual disciplina do EDITAL esta fala nomeia, se alguma.

    Existe pra responder "na ordem do edital": o `topico` guarda o programa
    inteiro, em ordem, e sem saber DE QUAL disciplina se trata não há como
    mandar o pedaço certo ao prompt sem mandar os 487 tópicos.

    Casa por todas as palavras de conteúdo do nome, sem acento: "quero ciências
    forenses do zero" acha "Ciências Forenses". Prefere o nome MAIS LONGO que
    casar, senão "Direito Penal" ganharia de "Direito Penal e Legislação Penal
    Extravagante" no edital da PC-PR, que tem as duas.

    NÃO contradiz `_com_assunto`, que descarta nome de disciplina como assunto de
    BUSCA. São perguntas diferentes: lá é "o que procurar no acervo" (e a gaveta
    não é o que a pessoa quer estudar); aqui é "de que gaveta ela está falando",
    que é exatamente o que o programa do edital indexa."""
    if not texto or not disciplinas:
        return None
    palavras = {_sem_acento(p) for p in RE_PALAVRA.findall(texto.lower())}

    def equivale(alvo: str) -> bool:
        # Nomes de disciplina variam entre substantivo e adjetivo no uso real:
        # "processo penal" precisa casar "Direito Processual Penal". O prefixo
        # longo evita aproximações entre palavras curtas ou só vagamente afins.
        return any(alvo == p or (min(len(alvo), len(p)) >= 7
                                and alvo[:7] == p[:7]) for p in palavras)

    achadas = []
    for d in disciplinas:
        alvo = {_sem_acento(x) for x in palavras_de_conteudo(d)}
        # "Direito" é a categoria comum, não a parte distintiva do nome.
        # Exigi-la faria "processo penal" não identificar a disciplina que o
        # aluno acabou de nomear.
        distintivas = alvo - {"direito"} if len(alvo) > 1 else alvo
        if distintivas and all(equivale(x) for x in distintivas):
            achadas.append(d)
    return max(achadas, key=len) if achadas else None


def _disciplina_aproximada(texto: str | None, disciplinas: list[str] | None) -> str | None:
    """`disciplina_citada`, e se ela não achar, o nome LONGO dito pela metade.

    "legislação institucional da pc pr" não casava "Legislação Estadual E
    Institucional": `disciplina_citada` exige todas as palavras distintivas, e o
    aluno falou duas de três (24/09/2026). Nome de três ou mais palavras
    distintivas casa com pelo menos duas e 60% delas; nome curto continua
    exigindo o nome inteiro — "penal" sozinho não pode escolher entre "Direito
    Penal" e "Processual Penal"."""
    exata = disciplina_citada(texto or "", disciplinas)
    if exata or not texto or not disciplinas:
        return exata
    palavras = {_sem_acento(p) for p in RE_PALAVRA.findall(texto.lower())}
    melhor, nota = None, 0
    for d in disciplinas:
        alvo = {_sem_acento(x) for x in palavras_de_conteudo(d)} - {"direito"}
        if len(alvo) < 3:
            continue
        casadas = sum(1 for a in alvo if any(
            a == p or (min(len(a), len(p)) >= 7 and a[:7] == p[:7]) for p in palavras))
        if casadas >= 2 and casadas / len(alvo) >= 0.6 and casadas > nota:
            melhor, nota = d, casadas
    return melhor


# O VOCABULÁRIO DE ESTUDAR, não o de uma matéria: "seguir a ordem", "todo o
# conceito disso", "um aulão", "como se tivesse lendo um pdf" — as falas de
# 24/09/2026 que continuavam a matéria anterior sem nomeá-la. Lista de palavras
# de conversa sobre o estudo, como `PEDIDO` e `VAZIAS`; nenhuma é de disciplina.
VOCABULARIO_DE_ESTUDO = set("""
seguir sigo siga segue seguindo ordem conceito conceitos tudo todo toda inteiro inteira
completo completa disso nisso isso dele dela deles delas aquilo aulao aula aulas resumo
resumao resumir trazendo trazer traga traz tivesse lendo leitura ler pdf apostila livro
material materiais conteudo explicacao historia sequencia parte partes detalhe detalhes
detalhado edital topico item ponto comeco inicio pausa pausas pergunta perguntas
resumos conceito consegue conseguir consegues nada falando fala trazendo mais alem
cobre cobrem querer impossivel varias varios paginas pagina ensinar ensina ensinando
mapa mental trilha aprendizagem plano cronograma roteiro estudo estudos
""".split())


def traz_assunto_proprio(fala: str | None, disciplinas: list[str] | None = None) -> bool:
    """A fala nomeia assunto, além de pedir, de falar do estudo e de nomear a
    gaveta? "me explica peculato" sim; "certo, queria aprender todo o conceito
    disso" não; "então você não consegue me ensinar nada de legislação?" também
    não — "legislação" é pedaço do nome da disciplina, não assunto dentro dela
    (mesmo princípio de `_com_assunto`)."""
    gaveta = {_sem_acento(x) for d in (disciplinas or []) for x in palavras_de_conteudo(d)}
    return any(_sem_acento(p) not in PEDIDO and _sem_acento(p) not in VOCABULARIO_DE_ESTUDO
               and _sem_acento(p) not in gaveta
               for p in palavras_de_conteudo(fala or ""))


# Aceitar sem escolher: "pode ser", "sim", "bora".
RE_ACEITE = re.compile(r"(?i)^\s*(?:pode\s+ser|pode|sim|s|bora|vamos|claro|isso|quero|ok|okay|"
                       r"blz|beleza|certo|fechou|t[aá]|uhum|aham)\W*$")


def disciplina_da_conversa(historico: list[dict] | None,
                           disciplinas: list[str] | None,
                           fala: str | None = None) -> str | None:
    """A última disciplina nomeada na conversa — pelo aluno, ou pelo tutor quando
    ele nomeou UMA só (a proposta que o aluno aceita com "pode ser"). Medido em
    24/09/2026: "Quer seguir por Direito Administrativo?" → "pode ser" → "sim";
    olhando só as falas do aluno, a matéria de antes (Legislação) continuava
    valendo, e a leitura seguinte abriu uma apostila de Constitucional. Fala do
    tutor que cita duas ou mais disciplinas não decide nada."""
    for t in reversed((historico or [])[-12:]):
        texto = t.get("texto") or ""
        if t.get("autor") == "aluno":
            if (d := _disciplina_aproximada(texto, disciplinas)):
                return d
        elif t.get("autor") == "tutor":
            # Do tutor, só o NOME INTEIRO: a regra frouxa de `disciplina_citada`
            # (prefixo de 7 letras) lia "esfera administrativa", numa aula de
            # perícia, como o tutor nomeando "Direito Administrativo" — e a
            # leitura de Ciências Forenses pulava para Administrativo (medido na
            # bateria de 24/09/2026).
            normal = " ".join(_sem_acento(p) for p in RE_PALAVRA.findall(texto.lower()))
            citadas = [d for d in disciplinas or []
                       if " ".join(_sem_acento(p) for p in RE_PALAVRA.findall(d.lower())) in normal]
            if len(citadas) == 1:
                return citadas[0]
            # "Constitucional ou Administrativo?" → "pode ser": a escolha está em
            # aberto (o prompt manda o tutor escolher). Voltar mais para trás
            # ressuscitava a matéria sem material de antes da oferta.
            if len(citadas) >= 2 and RE_ACEITE.match(fala or ""):
                return None
    return None


def disciplina_em_foco(fala: str | None, historico: list[dict] | None,
                       disciplinas: list[str] | None) -> str | None:
    """A disciplina de que a conversa trata AGORA, se alguém a nomeou.

    A fala atual primeiro. Sem nome nela, as falas recentes do ALUNO — mas só
    quando a atual não traz assunto próprio: "certo, queria aprender todo o
    conceito disso" continua a matéria de antes; "o que é peculato?" não, e
    herdar a disciplina anterior faria a pergunta nova ser respondida como se
    fosse da matéria errada. Falas do tutor ficam fora: ele cita várias
    disciplinas no mesmo turno ("Ciências Forenses, Constitucional ou…")."""
    if not disciplinas:
        return None
    propria = _disciplina_aproximada(fala, disciplinas)
    if propria or traz_assunto_proprio(fala, disciplinas):
        return propria
    return disciplina_da_conversa(historico, disciplinas, fala)


RE_TROCA_DISCIPLINA = re.compile(r"(?i)^\s*(?:e\s+)?(?:no|na|em)\b")


def troca_de_disciplina(texto: str | None,
                        disciplinas: list[str] | None) -> bool:
    """A fala curta muda de gaveta, em vez de responder à pergunta anterior."""
    return bool(texto and RE_TROCA_DISCIPLINA.search(texto)
                and disciplina_citada(texto, disciplinas))


def cita_dispositivo(texto: str) -> bool:
    """"art. 312", "artigo 5º" — a pergunta aponta um dispositivo específico.

    Existe aqui pra `socratic.explicar` poder decidir SEM buscar duas vezes: uma
    pergunta assim vai à busca CRUA, porque `por_dispositivo` lê o número da
    própria string. Enriquecer com histórico nesse caso é o pior tipo de
    regressão — um "art. 140" de três turnos atrás sequestraria a pergunta nova,
    e a resposta viria confiante sobre o artigo errado."""
    return bool(RE_CITACAO.search(texto or ""))


def diz_assunto(texto: str) -> bool:
    """A fala nomeia um assunto por si, ou é continuação ("vamos", "sim",
    "lembrava")? Citação de dispositivo conta como assunto mesmo sendo curta:
    "art. 312" tem uma palavra vazia e um número, e é a consulta mais precisa
    que este sistema aceita."""
    if cita_dispositivo(texto):
        return True
    return len(palavras_de_conteudo(texto)) >= MIN_CONTEUDO


# PERGUNTA QUE O ALUNO FAZ, na forma de quem pergunta — e não de quem responde.
# "?" sozinho não serve: responder ao tutor em forma de pergunta é comum e está
# medido ("dependencia?", "quando nao for crime realizado em ambito
# doméstico?"). O que separa é a ABERTURA: pedir definição, diferença, modo ou
# motivo, ou "e o/a <assunto>?" puxando o próximo ponto.
RE_PERGUNTA_DO_ALUNO = re.compile(
    r"(?i)^\s*(?:e\s+)?(?:o\s+qu[eê]\s+(?:[eé]|s[aã]o|significa|diz|caracteriza|configura)"
    r"|qual|quais|como\s+(?:funciona|fica|[eé]|se)|por\s*qu[eê]|pra\s+qu[eê]|para\s+qu[eê])\b"
    r"|^\s*e\s+(?:o|a|os|as)\s+\w")


def pede_assunto(fala: str | None) -> bool:
    """O aluno TOMA a iniciativa nesta fala — cita dispositivo ou pede algo?

    É o único ponto textual do classificador, e ele é a ESCAPATÓRIA, não a
    regra: existe pra que "agora quero controle de constitucionalidade", dito no
    meio de um assunto, troque o assunto em vez de ser lido como resposta. Errar
    aqui pra menos custa uma consulta enriquecida com o turno anterior; errar
    pra mais custa o aluno preso num assunto que ele abandonou."""
    if not fala:
        return False
    if cita_dispositivo(fala):
        return True
    # PEDIR TREINO É INICIATIVA, não resposta. Sem isto, "me testa nisso" era
    # classificado como eco (vinha depois de uma pergunta do tutor, e nenhuma
    # palavra dele está em `PEDIDO`), o caminho do eco assumia, e a consulta
    # virava a fala do TUTOR — que, num turno de treino, é a linha de
    # apresentação ("Vamos treinar isso; as questões estão logo abaixo") e não
    # nomeia matéria nenhuma. Medido: as questões saíram sobre apropriação
    # indébita e competência originária numa conversa sobre peculato.
    #
    # Quem pede algo retomou a iniciativa, por definição — é a mesma leitura
    # que `PEDIDO` já faz de "quero", "explica", "vamos ver".
    # `apos_treino=True` de propósito: aqui a pergunta é "esta fala retoma a
    # iniciativa?", e "manda cinco" retoma tanto quanto "me dá 5 questões". O
    # risco de errar pra mais é baixo — a fala continua saindo das candidatas a
    # ASSUNTO em `em_foco`, que é onde o estrago aconteceria.
    if pedido.treino(fala, apos_treino=True):
        return True
    # PERGUNTA NOVA COM ASSUNTO PRÓPRIO também é iniciativa. Medido em
    # 23/09/2026 (`./testar.sh --falas`, peculato): "o que é peculato culposo?"
    # e "e o peculato mediante erro de outrem?" vinham depois de uma pergunta
    # do tutor, caíam no eco, e a consulta virava a resposta ANTERIOR dele. O
    # art. 313 não veio, e o tutor afirmou que o peculato mediante erro "está
    # no art. 312". Sem assunto próprio ("quais são?") continua sendo eco.
    if RE_PERGUNTA_DO_ALUNO.search(fala) and [
            x for x in palavras_de_conteudo(fala) if _sem_acento(x) not in PEDIDO]:
        return True
    cruas = {_sem_acento(x) for x in RE_PALAVRA.findall(fala.lower())}
    if not (PEDIDO & cruas):
        return False
    # PEDIDO SEM OBJETO NÃO É INICIATIVA — é eco. Foi o buraco que deixou passar
    # a pior consulta já registrada aqui, com log completo:
    #
    #   tutor:  "...item 9.1 do seu edital: Conceito, fontes e princípios do
    #            Direito Administrativo. Você já sabe diferenciar os princípios
    #            expressos dos implícitos, como a Autotutela?"
    #   aluno:  "não você pode me explicar e mostrar como isso cai em concurso?"
    #
    # A fala do aluno tem "explicar", que está em `PEDIDO`, então `pede_assunto`
    # dizia True, `e_eco` dizia False, e a consulta virou a própria frase dele —
    # que não nomeia matéria nenhuma. (A palavra de conteúdo que sobrou foi
    # "mostrar", a única fora de `VAZIAS`.) Resultado: CPP 580, CP 337-O e ADCT
    # 19 numa conversa sobre princípios administrativos, e três questões geradas
    # sobre extensão de recurso, projetista e estabilidade.
    #
    # O assunto ESTAVA na conversa — o tutor o havia nomeado. Mas a fala dele só
    # é consultada quando NENHUMA do aluno qualifica, e uma fala de palha
    # qualificava.
    #
    # A distinção que resolve: "me explica peculato" nomeia; "me explica isso"
    # não. Então exige-se que o pedido traga algo ALÉM do próprio vocabulário de
    # pedir. Isto NÃO enfraquece a escapatória que a função existe pra ser —
    # "agora quero controle de constitucionalidade" continua trocando o assunto,
    # porque "controle" e "constitucionalidade" não são palavras de pedir.
    return bool([x for x in palavras_de_conteudo(fala)
                 if _sem_acento(x) not in PEDIDO])


# Pronomes que apontam para o foco anterior em vez de nomear um foco novo.
# Não entram em `VAZIAS` como conserto genérico: aqui a pergunta é específica
# — "o pedido de treino trouxe tema próprio ou está dizendo *isso*?".
REFERENCIA_VAGA_TREINO = {
    "disso", "disto", "nisso", "nisto", "daquilo", "naquilo",
}


def pedido_de_treino_nomeia_assunto(
        fala: str | None, disciplinas: list[str] | None = None) -> bool:
    """O pedido de treino diz DE QUÊ, em vez de apontar para trás?

    A regra anterior dizia que pedido de treino nunca nomeia assunto. O turno
    real que derrubou essa premissa foi "quero questões de ciências forenses":
    a rota descartou a fala inteira, herdou Direito Constitucional do histórico
    e gerou questões de Mutação Constitucional e Controle Interno.

    Nome de disciplina do edital é evidência explícita. Sem ele, sobra o
    conteúdo real depois de retirar apenas referências vagas; assim "questões
    de peculato" nomeia foco, enquanto "questões disso" continua herdando o
    assunto anterior.
    """
    # `apos_treino=False`: continuação elíptica ("manda cinco", "agora uma")
    # nunca traz tema próprio, mesmo que alguma palavra escape de `VAZIAS`.
    if not fala or not pedido.treino(fala):
        return False
    if disciplina_citada(fala, disciplinas):
        return True
    return any(_sem_acento(p) not in REFERENCIA_VAGA_TREINO
               for p in palavras_de_conteudo(fala))


# O aluno PEDINDO exposição em vez de sabatina. Lista fechada e curta, como
# `PEDIDO`, e pela mesma razão: quem carrega a decisão não é ela.
EXPOSICAO = (
    "explica", "explique", "explicar", "explicame", "me explique", "detalha", "detalhe",
    "resume", "resuma", "resumo", "aprofunda", "aprofunde", "desenvolve", "desenvolva",
    "quero ler", "so me explica", "só me explica", "sem pergunta", "sem perguntas",
    "nao quero responder", "não quero responder", "nao quero pergunta",
    "não quero pergunta", "me ensina", "me ensine", "fala sobre", "discorre",
    "visao geral", "visão geral", "pontos principais", "o que mais cai", "que mais caem",
    "mais cobrado", "mais cobrados", "mais cai",
)


def pede_exposicao(fala: str | None) -> bool:
    """O aluno pediu pra LER/entender, em vez de responder pergunta?

    Existe pra que o avaliador não contradiga o prompt. A regra "responda no
    tamanho da pergunta" tem exceção declarada — quando ele pede explicação, a
    resposta longa é o acerto —, e sem esta função a checagem de tamanho
    apontava como defeito exatamente o comportamento pedido: medido em
    "não quero responder pergunta agora, só me explica o assunto", que virou
    aviso de "742 caracteres para uma fala que não nomeia assunto".

    Casa contra a fala CRUA, sem acento, porque metade destas palavras é
    (corretamente) vazia para efeito de busca."""
    if not fala:
        return False
    baixo = _sem_acento(fala.lower())
    return any(_sem_acento(e) in baixo for e in EXPOSICAO)


def _falas_antes(turnos: list[dict], pergunta: str | None) -> list[dict]:
    """Os turnos que ANTECEDEM a fala atual do aluno.

    Os dois caminhos que chamam `em_foco` diferem justo aqui, e ignorar isso foi
    o que me fez "validar" a regra errada: no CHAT a fala atual é `pergunta` e
    não está na lista, então tudo antecede; no BOTÃO ("quero questões sobre
    isto") não existe fala nova — a última do aluno já está dentro de `turnos`,
    seguida da resposta do tutor. Comparar a fala com o turno do tutor que veio
    DEPOIS dela é circular: esse turno repete a resposta do aluno de volta
    ("Exato, a unidade doméstica ou a dependência econômica...")."""
    if pergunta and pergunta.strip():
        return turnos
    for i in range(len(turnos) - 1, -1, -1):
        if turnos[i].get("autor") == "aluno":
            return turnos[:i]
    return turnos


def e_eco(pergunta: str | None, turnos: list[dict] | None,
          disciplinas: list[str] | None = None) -> bool:
    """
    A fala atual RESPONDE ao tutor, em vez de propor assunto?

    Duas condições, as duas necessárias:

      1. o último turno antes dela é do TUTOR e contém pergunta ("?") — o tutor
         detém a iniciativa;
      2. a fala não retoma a iniciativa (`pede_assunto`).

    O QUE EU TENTEI ANTES E MEDI QUE NÃO FUNCIONA, pra ninguém repetir: usar
    novidade lexical na condição 2 — "é eco se não acrescenta nenhuma palavra de
    conteúdo além das que o tutor acabou de usar". Parece a regra perfeita, sem
    limiar nenhum, e cai em 3 das 6 respostas do log real:

        ECO                          <- 'não'
        ECO                          <- 'não impede'
        NOVAS ['dependencia']        <- 'dependencia?'
        NOVAS ['afeto','vinculo']    <- 'sim desde que haja vinculo ou afeto'
        NOVAS ['ambito','crime',…]   <- 'quando nao for crime realizado em ambito
                                         doméstico?'

    O motivo é óbvio depois de ver: RESPONDER a uma pergunta de conhecimento É
    dizer a palavra que o tutor não disse. Era exatamente o que o tutor estava
    perguntando ("qual o critério, além da coabitação e do vínculo de afeto?" →
    "dependencia?"). Novidade lexical mede acerto do aluno, não iniciativa.

    Por que a condição 1 não pode ser usada sozinha, embora seja a mais limpa: o
    prompt manda o tutor TERMINAR toda resposta com pergunta, então quase todo
    turno do aluno vem depois de uma — e tratar todos como resposta tira dele a
    capacidade de trocar de assunto, que é o defeito oposto e igualmente ruim
    (`test_recencia_lidera_e_assunto_abandonado_nao_volta`).
    """
    fala = pergunta
    turnos = turnos or []
    if not (fala and fala.strip()):
        fala = next((t.get("texto") for t in reversed(turnos)
                     if t.get("autor") == "aluno"), None)
    if pede_assunto(fala) or troca_de_disciplina(fala, disciplinas):
        return False
    anteriores = [t for t in _falas_antes(turnos, pergunta)
                  if t.get("autor") in ("aluno", "tutor")]
    if not anteriores:
        return False
    ultimo = anteriores[-1]
    return ultimo.get("autor") == "tutor" and "?" in (ultimo.get("texto") or "")


def _com_assunto(falas: list[str], disciplinas: list[str] | None) -> list[str]:
    """
    Falas que nomeiam algo ALÉM do nome da disciplina, mais recente primeiro.

    O filtro por disciplina existe porque a resposta do tutor a um "boa noite" é
    "por onde você quer começar, Direito Constitucional ou Direito Penal?" —
    curta e certa. Sem o filtro, "direito/constitucional/penal" contava como
    assunto e a busca devolvia artigo sorteado DENTRO da matéria (CPP art. 2º pra
    quem não pediu nada): errado de um jeito pior que vazio, porque tem cara de
    acerto. Disciplina é a GAVETA, não o que a pessoa quer estudar — e o prompt
    já a recebe pelo "Contexto do aluno".
    """
    vazias_extra = set()
    for d in disciplinas or []:
        vazias_extra.update(_sem_acento(x) for x in palavras_de_conteudo(d))
    return [
        f for f in reversed(falas)
        if diz_assunto(f) and [x for x in palavras_de_conteudo(f)
                               if _sem_acento(x) not in vazias_extra]
    ]


RE_FONTE = re.compile(r"\[[^\]]*\]")


def _sem_citacao(trecho: str) -> str:
    """Tira do texto HERDADO DO TUTOR as citações de dispositivo.

    Necessário, e descoberto medindo: o tutor fecha a resposta com a fonte
    ("[Lei Maria da Penha, art. 5º, II e III]"), e `retrieval.buscar` lê citação
    na consulta como pedido de dispositivo EXATO. Com a citação dentro, a busca
    deixava de ser semântica e devolvia o art. 5º de tudo o que existe no acervo
    — ADCT, CF, territorialidade do CP, inquérito do CPP, requisitos da 8.112 —
    cinco artigos sem relação entre si além do número. Pior que a falha que eu
    estava consertando, porque cada acerto de número parece acerto de assunto.

    Só vale no caminho do ECO. Citação escrita pelo ALUNO continua intocada e
    continua indo crua à busca: ali ela É o pedido (ver `cita_dispositivo`)."""
    limpo = RE_FONTE.sub(" ", trecho or "")
    limpo = RE_CITACAO.sub(" ", limpo)
    return " ".join(limpo.split())


def _truncar(trecho: str) -> str:
    """Corta na última palavra inteira que cabe. Meia palavra ("adm") não casa
    lexicalmente com nada e ainda entra no vetor como ruído."""
    if len(trecho) <= MAX_CHARS:
        return trecho
    cortado = trecho[:MAX_CHARS]
    espaco = cortado.rfind(" ")
    return (cortado[:espaco] if espaco > 0 else cortado).strip()


def em_foco(turnos: list[dict] | None = None, pergunta: str | None = None,
            disciplinas: list[str] | None = None) -> str | None:
    """
    A consulta de busca desta conversa: a fala atual mais os turnos do aluno
    que ainda dizem do que se trata. `None` quando ninguém nomeou assunto
    nenhum — e aí quem chama deve cair no recorte da mesa, NUNCA buscar por
    "vamos".

    PREFERE a fala do ALUNO, e cai na do TUTOR quando nenhuma fala do aluno nomeia
    assunto. Essa segunda metade foi acrescentada depois, por um caso real que a
    primeira versão errava inteiro:

        aluno:  "boa noite"
        tutor:  "...você já domina a diferença entre os direitos sociais de
                 eficácia plena e as normas de eficácia limitada?"
        aluno:  "podemos testar eu nao sei se ja estou bom"

    Nenhuma das duas falas do aluno nomeia matéria. A consulta virou "podemos
    testar eu nao sei se ja estou bom boa noite", a busca devolveu lixo e as
    questões geradas foram CF art. 200 (SUS) e CP art. 94 (reabilitação) — no meio
    de uma conversa sobre eficácia das normas constitucionais. O MESMO estrago do
    "vamos", por outra fresta.

    A lição não é "faltou palavra na lista `VAZIAS`". Nenhuma lista cobre toda
    forma de dizer "vamos lá" — o defeito era estrutural: quando o aluno não
    nomeia o assunto, quem nomeou foi o TUTOR, e a proposta dele É o assunto da
    conversa. Excluir o tutor sempre transformava "o aluno aceitou o convite" em
    "ninguém falou de nada".

    A razão original de excluí-lo continua de pé onde ela vale: a prosa do tutor
    tem centenas de palavras e, quando o aluno JÁ disse do que quer falar,
    dominaria a consulta com o vocabulário da resposta anterior, prendendo a busca
    no que já foi dito. Por isso é FALLBACK e não fonte de igual peso — só entra
    quando não há nada do aluno.

    Os eventos ("respondeu e errou") ficam fora dos dois casos: são fatos da
    sessão, não pedido — entram no prompt (016) e não deveriam decidir de qual
    artigo se cobra.
    """
    def falas_de(autor: str) -> list[str]:
        return [t.get("texto") or "" for t in (turnos or []) if t.get("autor") == autor]

    # ECO: quem detém a iniciativa é o tutor, e a fala do aluno é resposta. O
    # assunto é o que o TUTOR está perguntando — costurar as últimas respostas do
    # aluno é o que fez uma conversa INTEIRA sobre Lei Maria da Penha gerar
    # questão de ajuda de custo (L8112 art. 55) e mandato eletivo (art. 94).
    if e_eco(pergunta, turnos, disciplinas):
        candidatas = _com_assunto(falas_de("tutor"), disciplinas)[:1]
        if not candidatas:
            return None
        herdado = _sem_citacao(candidatas[0])
        return _truncar(herdado) or None

    # Uma troca explícita já contém o novo foco inteiro. Somar falas antigas
    # reintroduziria justamente a disciplina que o aluno abandonou.
    if troca_de_disciplina(pergunta, disciplinas):
        return _truncar(" ".join((pergunta or "").split())) or None

    # A disciplina atual explicitamente pedida já é foco suficiente. Sem esta
    # saída, "quais são os assuntos de Ciências Forenses?" tinha 3 termos de
    # conteúdo (menos que CONTEUDO_SUFICIENTE=4) e ganhava Processo Legislativo
    # do turno anterior como reforço. Nome de disciplina solto como RESPOSTA
    # continua fora: `pede_assunto` exige que o aluno retome a iniciativa.
    if (pergunta and disciplina_citada(pergunta, disciplinas)
            and pede_assunto(pergunta)):
        return _truncar(" ".join(pergunta.split())) or None

    # PEDIDO DE TREINO PODE OU NÃO NOMEAR ASSUNTO. "Me testa nisso" aponta
    # para trás; "quero questões de Ciências Forenses" nomeia o foco atual e
    # precisa vencer qualquer matéria antiga do histórico.
    #
    # Medido no cenário `pede_treino` logo que ele nasceu: a conversa era
    # "quero estudar peculato" → "me testa nisso" → "me da 3 questoes disso", e
    # as questões saíram sobre apropriação indébita, competência originária e
    # julgamento nos tribunais. Duas coisas se somaram: a fala do pedido tem
    # "disso"/"nisso" como palavra de conteúdo (então passa por `diz_assunto`),
    # e a resposta do tutor a um pedido é uma linha de APRESENTAÇÃO ("Vamos
    # treinar isso; as questões estão logo abaixo") que não nomeia matéria
    # nenhuma — então o fallback pro tutor também não salvava.
    #
    # Com os pedidos vagos fora, `em_foco` alcança "quero estudar peculato".
    # Com pedido explícito, a própria fala atual vence por recência.
    # PERGUNTA SOBRE O SISTEMA TAMBÉM NÃO NOMEIA ASSUNTO, e pelo mesmo motivo.
    # Medido no cenário `meta`, turno 4: as três falas anteriores eram "como você
    # funciona?", "de onde você tira as respostas?" e "você é uma IA?" — nenhuma
    # busca, porque `dispensa_busca` as pega. Mas elas ficam no HISTÓRICO, e
    # "respostas", "professor" e "verdade" passam por `diz_assunto`: a consulta de
    # "me ensina algo de penal" saiu como "...você é uma IA ou tem professor de
    # verdade? de onde você tira as respostas?" e a busca devolveu falso
    # testemunho e prova pericial. O aluno pediu Direito Penal e recebeu o artigo
    # que casou com a palavra "perícia" da pergunta sobre a MÁQUINA.
    if pedido_de_treino_nomeia_assunto(pergunta, disciplinas):
        return _truncar(" ".join((pergunta or "").split())) or None

    do_aluno = [f for f in falas_de("aluno")
                if (not pedido.treino(f, apos_treino=True)
                    or pedido_de_treino_nomeia_assunto(f, disciplinas))
                and not pedido.sobre_o_sistema(f)]
    if pergunta and not pedido.treino(pergunta, apos_treino=True):
        do_aluno.append(pergunta)

    # Recência primeiro: é o que o aluno quer AGORA.
    candidatas = [f for f in reversed(do_aluno) if diz_assunto(f)][:1 + TURNOS_EXTRA]
    if not candidatas:
        # Só a ÚLTIMA fala do tutor, e uma só: as anteriores são assuntos que a
        # conversa já deixou para trás, e trazê-las é o "arrastar peculato de
        # volta" que `CONTEUDO_SUFICIENTE` existe pra evitar.
        #
        # E NOME DE DISCIPLINA NÃO CONTA como assunto aqui. Apareceu ao consertar
        # o tom do tutor: com o prompt novo, a primeira resposta a um "boa noite"
        # é "por onde você quer começar, Direito Constitucional ou Direito
        # Penal?" — curta e certa. Só que aí o fallback achava "assunto" nela
        # ("direito", "constitucional", "penal") e a busca por isso devolvia
        # artigo sorteado DENTRO da matéria: CPP art. 2º pra quem não pediu nada.
        # Errado de um jeito pior que vazio, porque tem cara de acerto.
        #
        # Nome de disciplina o prompt já recebe pelo "Contexto do aluno"; ele não
        # é o que a pessoa quer estudar, é a gaveta. Sem assunto de verdade, o
        # certo é NÃO buscar — e aí o tutor pergunta de que assunto se trata, que
        # é o que a instrução de "nenhum trecho recuperado" manda fazer.
        candidatas = _com_assunto(falas_de("tutor"), disciplinas)[:1]
    if not candidatas:
        return None

    partes: list[str] = []
    conteudo = 0
    for fala in candidatas:
        trecho = " ".join(fala.split())
        if not trecho:
            continue
        if not partes:
            # A FALA MAIS RECENTE SEMPRE ENTRA, truncada se preciso. A primeira
            # versão descartava turno maior que `MAX_CHARS` e devolvia `None` —
            # ou seja, a pergunta mais desenvolvida que o aluno pode escrever era
            # justamente a que caía fora da busca.
            partes.append(_truncar(trecho))
        else:
            if conteudo >= CONTEUDO_SUFICIENTE:
                break
            if len(" ".join(partes)) + 1 + len(trecho) > MAX_CHARS:
                # Reforço é cortado por TURNO INTEIRO, nunca no meio: meia
                # pergunta antiga muda de sentido, e a fala atual já está dentro.
                break
            partes.append(trecho)
        conteudo += len(palavras_de_conteudo(trecho))
    return " ".join(partes) or None
