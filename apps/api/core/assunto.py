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
"""
import re
import unicodedata

# A MESMA regra de citação que `por_dispositivo` usa pra decidir se a pergunta
# aponta um artigo. Reusar em vez de copiar: duas versões de "isto é uma
# citação?" divergem, e o sintoma seria a busca por dispositivo funcionando num
# caminho e não no outro.
from .retrieval import RE_CITACAO

VERSAO = "assunto-v1"

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
""".split())


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


def palavras_de_conteudo(texto: str) -> list[str]:
    """As palavras da fala que carregam assunto — o resto é andaime de conversa."""
    achadas = RE_PALAVRA.findall((texto or "").lower())
    return [p for p in achadas
            if len(p) >= MIN_LETRAS and _sem_acento(p) not in VAZIAS]


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


def _truncar(trecho: str) -> str:
    """Corta na última palavra inteira que cabe. Meia palavra ("adm") não casa
    lexicalmente com nada e ainda entra no vetor como ruído."""
    if len(trecho) <= MAX_CHARS:
        return trecho
    cortado = trecho[:MAX_CHARS]
    espaco = cortado.rfind(" ")
    return (cortado[:espaco] if espaco > 0 else cortado).strip()


def em_foco(turnos: list[dict] | None = None, pergunta: str | None = None) -> str | None:
    """
    A consulta de busca desta conversa: a fala atual mais os turnos do aluno
    que ainda dizem do que se trata. `None` quando ninguém nomeou assunto
    nenhum — e aí quem chama deve cair no recorte da mesa, NUNCA buscar por
    "vamos".

    Só falas do ALUNO. A prosa do tutor tem centenas de palavras e dominaria a
    consulta com o vocabulário da RESPOSTA anterior, prendendo a busca no que já
    foi dito em vez do que está sendo perguntado. Os eventos ("respondeu e
    errou") ficam fora pelo motivo inverso: são fatos da sessão, não pedido —
    entram no prompt (016) e não deveriam decidir de qual artigo se cobra.
    """
    falas = [t.get("texto") or "" for t in (turnos or [])
             if t.get("autor") == "aluno"]
    if pergunta:
        falas.append(pergunta)

    # Recência primeiro: é o que o aluno quer AGORA.
    candidatas = [f for f in reversed(falas) if diz_assunto(f)][:1 + TURNOS_EXTRA]
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
