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

VERSAO = "pedido-v1"

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


def quantas(fala: str) -> int:
    """Quantas questões a fala pede. `PADRAO` quando ela não diz.

    Dois é o padrão e não um: "me dá questões" está no plural, e uma questão só
    encerra o treino antes de ele começar. Cinco é o teto porque cada questão
    custa uma chamada de LLM e o aluno espera por todas antes de ver a primeira."""
    m = RE_QUANTIDADE.search(fala or "")
    if not m:
        return PADRAO
    bruto = m.group(1).lower()
    n = NUMERO.get(bruto, 0) or (int(bruto) if bruto.isdigit() else 0)
    return max(1, min(n or PADRAO, MAX))


def treino(fala: str) -> dict | None:
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
    if not fala or not (RE_TREINO.search(fala) or RE_FORMAL.search(fala)):
        return None
    return {"quantidade": quantas(fala),
            "tipo": "certo_errado" if RE_CERTO_ERRADO.search(fala) else None,
            "formal": bool(RE_FORMAL.search(fala))}
