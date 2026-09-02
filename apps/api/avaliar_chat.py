"""
Um ALUNO SINTÉTICO conversa com o tutor, e tudo o que acontece por dentro fica
visível: o que virou vetor, o que a busca devolveu, e o que a resposta tem de
errado.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O AGENTS.md manda, antes de mexer no prompt do tutor, "rode uma pergunta real e
LEIA a resposta" — e explica por quê: as duas piores regressões do projeto (o
rótulo `[DESEMPENHO REAL DO ALUNO]` citado como fonte, e o modelo escrevendo
questão de múltipla escolha dentro do chat) não aparecem em teste automatizado,
porque o texto continua sendo uma resposta VÁLIDA. Nada quebra; só fica ruim.

O custo disso é que a verificação depende de uma pessoa disposta a ler, lembrar
de todos os defeitos já vistos e reconhecê-los de novo. Na terceira vez ninguém
faz. Este script não substitui a leitura — ele a torna barata: encena a
conversa, mostra o que o sistema fez a cada turno e aponta o que já se sabe ser
defeito.

O QUE ELE NÃO É
---------------
Não é `pytest`, e não deve virar: quase toda checagem aqui é sobre TOM e FOCO,
que não têm resposta binária. Ele imprime evidência e suspeita; quem julga é
você. As checagens de regra que ele faz são só as que já foram vistas em uso
real e estão descritas em `docs/DECISOES.md` — não invento defeito novo.

COMO ELE OBSERVA (e por que não recalcula nada)
-----------------------------------------------
A tentação era chamar `assunto.em_foco()` aqui pra "descobrir" qual foi a
consulta. Seria uma SEGUNDA implementação do caminho, e este projeto já sabe o
que acontece com duas cópias da mesma regra: uma delas fica sem o conserto da
outra (`referencia()` fora de `formatar_contexto`, `RE_CITACAO` importada em vez
de copiada, a dedup de fontes que existia ao vivo e faltava ao reabrir).

Então ele ENVOLVE as funções reais — `retrieval.buscar`, as três estratégias e
`embed_consulta` — e anota o que passou por elas. O que você lê no relatório é o
que o código fez, não o que este script acha que ele faria. Se amanhã
`socratic.explicar` mudar de estratégia de busca, o relatório muda junto, sem
ninguém tocar aqui.

O QUE VAI PARA OS VETORES (a pergunta que originou este arquivo)
-----------------------------------------------------------------
Conversar NÃO grava vetor nenhum. `embed_consulta` diz na primeira linha:
"Consulta não vai para o cache: prefixo diferente e uso único" — o vetor da
pergunta vive em memória, casa contra as passagens e é descartado. O que está
gravado em `chunk.embedding` veio da INGESTÃO, e só o material do aluno (019)
acrescenta vetor depois disso.

Por isso a coluna que importa não é "quanto cresceu o banco", é QUAL TEXTO virou
vetor. O relatório mostra a string exata, com o prefixo `query:` que o e5 exige
— e é aí que os defeitos moram: `query: vamos`, `query: podemos testar eu nao
sei se ja estou bom boa noite`. O script confere o tamanho de `embedding_cache`
antes e depois assim mesmo, uma vez, pra que a afirmação acima seja verificada e
não repetida de boca.

USO
---
O caminho normal é `./testar.sh` na raiz, que cuida de banco, venv e chave antes de
chegar aqui. Direto, pra quem quer uma variação específica:

    python avaliar_chat.py                    # roteiro das regressões conhecidas
    python avaliar_chat.py --aluno llm        # o aluno é um LLM, conversa livre
    python avaliar_chat.py --aluno llm --turnos 8 --persona apressado
    python avaliar_chat.py --juiz             # + um LLM lê a transcrição inteira
    python avaliar_chat.py --roteiro "oi" "me explica peculato"
    python avaliar_chat.py --limpar           # apaga a conta descartável

Havendo defeito, além da transcrição carimbada sai um `.logs/defeitos.md` de nome
FIXO, só com o que falhou (turno, consulta, trechos, resposta) e um ponteiro pra
onde a causa costuma estar. É o arquivo pra entregar a um agente de IA — nome
fixo porque a frase "conserta os defeitos em .logs/defeitos.md" não pode depender
de você copiar um timestamp do terminal.
"""
import argparse
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from core import (assunto, auth, conversa, db, geracao, llm, mesa, pedido,
                  retrieval, socratic)
from core.config import CLI_USUARIO_EMAIL, EMBEDDING_MODEL
from core.llm import ErroLLM

VERSAO = "avaliar-chat-v20"

# Conta descartável, como manda o AGENTS.md: nada aqui pode encostar na conta
# real. O `ON DELETE CASCADE` da 009 limpa tudo de uma vez em `--limpar`.
EMAIL_TESTE = "teste-avaliar-chat@local"

console = Console()


# ══════════════════════════════════════════════════════════════ o aluno falso

# O roteiro PADRÃO não é inventado: são as falas exatas que produziram os
# defeitos descritos no AGENTS.md. Um roteiro fixo custa metade das chamadas de
# um aluno-LLM e, mais importante, é REPRODUZÍVEL — a mesma entrada amanhã, pra
# comparar antes e depois de mexer no prompt. O aluno-LLM serve pro que roteiro
# nenhum cobre: a fala que ninguém pensou em escrever.
ROTEIRO_REGRESSOES = [
    # 1. cumprimento seco: já recebeu parágrafo sobre eficácia das normas, e já
    #    fez a busca devolver CP 150 + CPP 569 + L8112 75 sem assunto nenhum.
    "boa noite",
    # 2. aceite sem nomear matéria: virou a consulta "podemos testar eu nao sei
    #    se ja estou bom boa noite", e gerou CF art. 200 (SUS) e CP art. 94.
    "podemos testar eu nao sei se ja estou bom",
    # 3. aqui o assunto finalmente é nomeado — o turno que DEVE buscar.
    "quero eficácia das normas constitucionais",
    # 4. resposta curta a uma pergunta do tutor: o caso do `e_eco`, em que a
    #    consulta tem de vir da fala do TUTOR e não desta.
    "acho que sim",
    # 5. citação de dispositivo: vai crua à busca, sem enriquecer com histórico.
    "e o art. 312?",
    # 6. pedido explícito de questão: o tutor deve mandar usar o botão, e NUNCA
    #    escrever a questão no chat.
    "me dá uma questão disso",
]

# CENÁRIOS: roteiros fixos, um por RISCO, cada um com linha própria no placar.
#
# Por que nomeado e fixo, se o pedido era variedade: variedade e comparabilidade
# se estorvam. Sorteio cobre mais chão e não deixa medir — a nota sobe ou desce
# por causa do roteiro, não do prompt. Cenário nomeado resolve os dois: a
# COLEÇÃO cobre o espaço, e cada cenário é comparável CONSIGO MESMO ao longo do
# tempo, porque a entrada não muda.
#
# `--livre` continua sendo o outro lado — a fala que ninguém pensou em escrever,
# agora com abertura sorteada. Os dois juntos: cenário mede, livre descobre.
CENARIOS: dict[str, tuple[str, list[str]]] = {
    "regressoes": (
        "as falas que causaram os defeitos já registrados no AGENTS.md",
        ROTEIRO_REGRESSOES),

    "cumprimento": (
        "só conversa fiada: nenhum turno nomeia matéria, e nenhum merece aula",
        ["oi", "tudo bem e você?", "nada, só passei pra ver", "vamos lá então"]),

    "direto": (
        "aluno que já sabe o que quer e vai fundo num assunto só",
        ["me explica peculato", "e a diferença com concussão?",
         "então se ele já tem a posse é peculato próprio?",
         "e se o bem for de particular?"]),

    "fora_do_acervo": (
        "pede jurisprudência e súmula, que o acervo NÃO tem — não pode inventar",
        ["o que o STJ diz sobre peculato de uso?", "tem súmula? cita o número",
         "e a posição do STF mudou em 2023?",
         "então me diz o que a lei seca diz, ao menos"]),

    "troca_de_assunto": (
        "muda de matéria no meio; a busca não pode arrastar o assunto velho",
        ["quero improbidade administrativa", "entendi",
         "agora mudei de ideia, quero falar de eficácia das normas constitucionais",
         "e isso cai na minha prova?"]),

    "meta": (
        "pergunta sobre o próprio sistema — o teste mais duro de voz humana",
        ["como você funciona?", "de onde você tira as respostas?",
         "você é uma IA ou tem professor de verdade?",
         "beleza, então me ensina algo de penal"]),

    "erra_feio": (
        "responde errado com confiança; o tutor deve partir do ERRO, não repetir",
        ["me explica peculato", "peculato é quando o servidor chega atrasado, né?",
         "ah então é qualquer crime de servidor",
         "não entendi ainda, tenta de outro jeito"]),

    # OS DOIS PRÓXIMOS SAÍRAM DE PEDIDO DIRETO DO DONO, não de defeito observado.
    # Registro a diferença porque muda como se lê o resultado: aqui não há
    # regressão pra travar — há um comportamento DESEJADO que ninguém tinha
    # verificado se existe.
    "quero_ler": (
        "aluno quer LER e entender, não responder pergunta; e quer esgotar UM assunto",
        ["quero aprender princípios fundamentais do direito administrativo",
         "não quero responder pergunta agora, só me explica o assunto",
         "quais são os pontos desse assunto que mais caem em prova?",
         "ainda tenho dúvida na legalidade, explica melhor",
         "agora sim pode me perguntar"]),

    "forense_do_zero": (
        "forense do zero na ORDEM DO EDITAL — exige --mesa \"PC-PR Investigador\"; "
        "metade tem lei (CPP 158-184), metade não (papiloscopia, balística)",
        ["quero aprender ciências forenses do zero",
         "na ordem do edital da PC-PR",
         "começa pelo primeiro tópico então",
         "e o que é papiloscopia?"]),

    # O CAMINHO NOVO: pedir treino numa frase e receber questão de verdade, com
    # proveniência e fila, sem clicar em nada. Os turnos são graduados de
    # propósito: sem quantidade, com quantidade, com formato, e por fim o
    # pedido FORMAL — que não deve gerar aqui, porque simulado tem página
    # própria.
    "pede_treino": (
        "pede treino no chat: o app gera questão com proveniência, sem botão",
        ["quero estudar peculato",
         "me testa nisso",
         "me da 3 questoes disso",
         "agora 2 itens certo ou errado",
         "quero um simulado formal cronometrado"]),

    "desanimo": (
        "desabafo, não matéria: pede tom, não conteúdo",
        ["tô desanimado, não sei se vou passar", "estudo há 2 anos e nada",
         "só tenho 20 minutos hoje", "tá, o que eu faço nesses 20 minutos?"]),
}

PERSONAS = {
    "iniciante": (
        "Você é um concurseiro iniciante conversando com um tutor de Direito por chat. "
        "Escreve como gente com pressa: minúsculas, sem acento às vezes, frases curtas. "
        "Você NÃO sabe a matéria — não explique nada, só responda, pergunte e às vezes "
        "chute errado. Às vezes responde só 'sim', 'acho que sim', 'não entendi'."
    ),
    "apressado": (
        "Você é um concurseiro que estuda de madrugada e tem pouco tempo. Escreve curto, "
        "às vezes só uma palavra. Muda de assunto sem avisar, pede questão o tempo todo, "
        "reclama quando a resposta é longa. Nunca escreve mais de duas linhas."
    ),
    "cético": (
        "Você é um concurseiro experiente e desconfiado. Testa o tutor: pergunta a fonte, "
        "duvida do que ele diz, pede o artigo exato, aponta quando a resposta fugiu do "
        "assunto. Escreve em tom seco e direto."
    ),
}

INSTRUCAO_ALUNO = (
    "Escreva APENAS a próxima mensagem do aluno, em português brasileiro, sem aspas, "
    "sem narração, sem 'Aluno:'. Uma mensagem só. Nunca quebre o personagem e nunca "
    "diga que é uma IA."
)


# COMO O ALUNO ABRE A CONVERSA — e por que isto não podia ser uma constante.
#
# `fala_do_aluno` devolvia `"oi"` sempre que não havia turno, então TODA rodada
# `--livre` começava idêntica, e a variedade só aparecia do segundo turno em
# diante. O primeiro turno é justamente o que mais decide o resto: é ele que diz
# se houve assunto pra buscar, e é onde moram os defeitos de tom ("boa noite" que
# recebia parágrafo de matéria densa).
#
# A lista cobre as FORMAS de abrir, não os assuntos — cada linha exercita um
# caminho diferente do código, e está agrupada por isso:
ABERTURAS = [
    # sem assunto nenhum: `em_foco` devolve None, NÃO deve haver busca
    "oi", "boa noite", "bom dia, tudo bem?", "voltei", "vamos estudar",
    "e aí, por onde eu começo?",
    # assunto nomeado de cara: deve buscar e acertar
    "me explica peculato", "quero entender eficácia das normas constitucionais",
    "preciso revisar improbidade administrativa",
    "tô com dúvida em crimes contra a administração pública",
    # dispositivo citado: vai CRU à busca, `por_dispositivo`
    "o que diz o art. 312?", "explica o artigo 37 da CF", "art. 5º, LXXVIII",
    # fora do acervo: deve dizer que não tem, e NÃO inventar
    "o que o STJ decidiu sobre absorção da falsidade pelo estelionato?",
    "qual a súmula sobre isso?",
    # meta-conversa: o teste mais duro de `voz_humana`
    "como você funciona?", "você é uma IA?", "de onde você tira as respostas?",
    # o aluno perguntando de si, não da matéria: a segunda fonte do prompt
    "como eu estou indo?", "o que eu erro mais?", "o que cai no meu edital?",
    # tom: nada disso nomeia matéria, e nenhum merece aula
    "tô desanimado, não sei se vou passar", "só tenho 20 minutos hoje",
    "reprovei no último concurso",
    # pedido direto de exercício, sem assunto: o caso do botão
    "me dá uma questão", "quero fazer um simulado agora",
]


def fala_do_aluno(persona: str, turnos: list[dict], n: int,
                  sorteio: random.Random | None = None) -> str:
    """A próxima fala do aluno, gerada por um LLM que NÃO conhece o prompt do
    tutor — ele vê só a conversa, como um aluno de verdade veria.

    Esse isolamento é o ponto: um avaliador que conhece as regras do avaliado
    testa se elas foram seguidas; este aqui testa se a conversa presta.

    A ABERTURA é sorteada de `ABERTURAS` em vez de gerada pelo modelo, e a razão
    é controle: primeira fala gerada por LLM sai comprida e bem-educada
    ("Olá! Gostaria de estudar Direito Constitucional, poderia me ajudar?"), que
    é exatamente o tipo de mensagem que aluno com pressa não escreve — e aí o
    caso de tom, que é o mais frágil, nunca seria exercitado."""
    if not turnos:
        return (sorteio or random).choice(ABERTURAS)
    historia = "\n".join(
        f"{'Você' if t['autor'] == 'aluno' else 'Tutor'}: {t['texto']}" for t in turnos)
    prompt = (f"Conversa até aqui:\n\n{historia}\n\n"
              f"(esta é a sua mensagem número {n}) {INSTRUCAO_ALUNO}")
    fala = llm.obter().gerar(prompt, PERSONAS[persona], max_tokens=120)
    return " ".join(fala.split())[:400]


# ══════════════════════════════════════════════════════════ o que o turno fez

class Observador:
    """Anota o que as funções REAIS de busca receberam e devolveram.

    Envolve em vez de recalcular — ver o cabeçalho do arquivo. `instalar()` é
    idempotente e `restaurar()` devolve os originais: um erro no meio da rodada
    não pode deixar o módulo remendado para o resto do processo."""

    def __init__(self):
        self.atual: dict | None = None
        self._originais: dict = {}

    def novo_turno(self) -> dict:
        self.atual = {"consulta": None, "vetorizado": None, "estrategia": None,
                      "chunks": [], "questoes": []}
        return self.atual

    def instalar(self) -> None:
        if self._originais:
            return
        self._originais = {
            "buscar": retrieval.buscar,
            "por_dispositivo": retrieval.por_dispositivo,
            "por_rubrica": retrieval.por_rubrica,
            "hibrida": retrieval.hibrida,
            "embed_consulta": retrieval.embed_consulta,
        }
        orig = self._originais

        def buscar(pergunta, *a, **kw):
            r = orig["buscar"](pergunta, *a, **kw)
            if self.atual is not None:
                self.atual["consulta"] = pergunta
                self.atual["chunks"] = r
            return r

        def marcada(nome, fn):
            def envolvida(pergunta, *a, **kw):
                r = fn(pergunta, *a, **kw)
                # Só a estratégia que REALMENTE devolveu algo conta: `buscar`
                # chama `por_dispositivo` e `por_rubrica` em cascata e descarta
                # as vazias. Registrar a primeira chamada diria "dispositivo"
                # em toda busca.
                if r and self.atual is not None and not self.atual["estrategia"]:
                    self.atual["estrategia"] = nome
                return r
            return envolvida

        def embed(texto):
            if self.atual is not None:
                # A string exata que o e5 recebe, prefixo incluído. É esta que
                # vira o vetor, e não a mensagem do aluno.
                self.atual["vetorizado"] = f"query: {texto}"
            return orig["embed_consulta"](texto)

        retrieval.buscar = buscar
        retrieval.por_dispositivo = marcada("dispositivo exato", orig["por_dispositivo"])
        retrieval.por_rubrica = marcada("rubrica", orig["por_rubrica"])
        retrieval.hibrida = marcada("híbrida (vetor + léxico)", orig["hibrida"])
        retrieval.embed_consulta = embed

    def restaurar(self) -> None:
        for nome, fn in self._originais.items():
            setattr(retrieval, nome, fn)
        self._originais = {}


def vetores_gravados() -> int:
    return db.query("SELECT count(*) AS n FROM embedding_cache WHERE modelo = %(m)s",
                    {"m": EMBEDDING_MODEL})[0]["n"]


# ═══════════════════════════════════════════════════════════════ as checagens

# Vocabulário do próprio funcionamento, que o prompt proíbe explicitamente. A
# lista é a do prompt, mais os termos que já vazaram em uso real. "contexto"
# NÃO entra: é palavra corrente em Direito ("contexto fático") e daria falso
# positivo em toda explicação decente.
VOCABULARIO_SISTEMA = [
    "escada pedagógica", "degrau", "método socrático", "socrático", "diagnóstico",
    "trechos recuperados", "trecho recuperado", "acervo", "prompt", "ferramenta",
    "chunk", "embedding", "rag", "base de dados", "meu treinamento", "modelo de linguagem",
]

# A resposta está INVOCANDO AUTORIDADE — norma, dispositivo ou tribunal? É o que
# separa "estou te ensinando Direito" de "estou te dizendo quem eu sou". Só o
# primeiro precisa de trecho por trás.
RE_AUTORIDADE = re.compile(
    r"(?i)\b(art\w*\.?\s*\d|lei\s|leis\s|c[óo]digo|constitui[çc][ãa]o|s[úu]mula|"
    r"jurisprud[êe]ncia|STF|STJ|§|inciso|par[áa]grafo|decreto|estatuto)\b")

# Quem reconhece pedido de treino é `core/pedido.py`, importado e não copiado:
# é a MESMA regra que faz a API gerar a questão, e o avaliador não pode divergir
# de quem ele avalia. Escrevi a cópia aqui primeiro e ela já divergia — deixava
# passar "me dá uma questão disso" e não reconhecia "simulado".
RE_MANDA_BOTAO = re.compile(r"(?i)quero quest[õo]es sobre isto|clique no bot[ãa]o|"
                            r"use o bot[ãa]o|bot[ãa]o (?:abaixo|logo abaixo)")

RE_ALTERNATIVA = re.compile(r"^\s*[a-eA-E]\s*[\)\.]\s+\S", re.MULTILINE)
RE_ASSINALE = re.compile(r"(?i)assinale a (alternativa|op[çc][ãa]o)")
RE_COLCHETE = re.compile(r"\[([^\]]+)\]")

# Um cumprimento merece uma linha. O número é generoso de propósito: o defeito
# relatado era "um parágrafo sobre eficácia das normas em cima de um boa noite",
# não uma frase a mais de cortesia.
TETO_CUMPRIMENTO = 320


def checar(fala: str, resposta: str, chunks: list[dict],
           historico: list[dict] | None = None,
           questoes: list[dict] | None = None) -> list[tuple[str, str]]:
    """Os defeitos que já aconteceram de verdade neste projeto, um por linha.

    Devolve `(gravidade, texto)`. Nada aqui é heurística nova: cada item tem um
    caso real por trás, registrado em `docs/DECISOES.md` ou no AGENTS.md."""
    achados = []
    baixo = resposta.lower()

    # 1. O andaime narrado. Causa conhecida: nome próprio dentro do prompt vira
    #    vocabulário do modelo ("vamos voltar um degrau na escada pedagógica").
    for termo in VOCABULARIO_SISTEMA:
        if termo in baixo:
            achados.append(("erro", f"vocabulário de sistema na resposta: {termo!r}"))

    # 2. Questão escrita no chat. O prompt manda oferecer o botão; questão solta
    #    não tem proveniência, não entra na fila e some quando a conversa rola.
    if RE_ALTERNATIVA.search(resposta) or RE_ASSINALE.search(resposta):
        achados.append(("erro", "escreveu questão de múltipla escolha na resposta"))

    # 2b. MANDOU CLICAR EM VEZ DE PERGUNTAR (socratic-v40).
    #
    #     Log real que motivou a regra: "queria 2 questões rápidas de direito
    #     constitucional" recebeu "clique no botão Quero questões sobre isto".
    #     O aluno pediu treino e levou instrução de interface — e a busca do
    #     turno tinha devolvido CF 102 e CPP 649, então nem o botão entregaria
    #     o que ele pediu.
    #
    #     A ressalva é a mesma do prompt: pedido de SIMULADO FORMAL (prova,
    #     caderno de erros, correção automática) continua sendo caso do botão,
    #     porque ali proveniência e fila SM-2 é o que a pessoa quer.
    p_treino = pedido.treino(fala)
    if p_treino and not p_treino["formal"] and RE_MANDA_BOTAO.search(resposta):
        achados.append(("erro", "aluno pediu treino e a resposta mandou clicar no botão "
                                "em vez de o app gerar a questão"))

    # 2c. PEDIU TREINO E NÃO VEIO QUESTÃO — ou veio na quantidade errada.
    #
    #     `questoes=None` quer dizer "quem chamou não sabe" (é o caso do
    #     `--reprocessar` sobre transcrições antigas, gravadas antes de o
    #     avaliador passar pela rota). Nesse caso não se afirma nada: silêncio
    #     é melhor que apontar defeito por falta de dado.
    if p_treino and not p_treino["formal"] and questoes is not None:
        if not questoes:
            achados.append(("erro", "aluno pediu treino e NENHUMA questão foi gerada"))
        else:
            # Proveniência é a razão de o app gerar em vez de o tutor escrever.
            # Sem ela a questão não entra na fila SM-2 e não conta no progresso
            # — é o que o dono recusou explicitamente.
            # A PROVENIÊNCIA SE CONFERE NO BANCO, não no payload — e a
            # primeira versão desta checagem conferia no payload, apontando
            # "SEM PROVENIÊNCIA" em questão que tinha `fonte_chunks: [6028]`
            # gravado. `sob_demanda` simplesmente não devolve a chave. Ler o
            # banco é mais forte que consertar a leitura do dicionário: o que
            # importa é o que ficou PERSISTIDO, porque é a linha gravada que a
            # fila SM-2 vai usar.
            ids = [q["id"] for q in questoes if q.get("id")]
            gravadas = {r["id"]: r["fonte_chunks"] for r in db.query(
                "SELECT id, fonte_chunks FROM questao WHERE id = ANY(%(i)s)",
                {"i": ids})} if ids else {}
            sem_fonte = [q for q in questoes if not gravadas.get(q.get("id"))]
            if sem_fonte:
                achados.append(("erro", f"{len(sem_fonte)} questão(ões) gerada(s) SEM "
                                        f"proveniência (fonte_chunks vazio)"))
            if len(questoes) != p_treino["quantidade"]:
                achados.append(("aviso", f"pediu {p_treino['quantidade']} questão(ões) e "
                                         f"veio(ram) {len(questoes)}"))

    # 3. Lei afirmada sem trecho por trás. É a única coisa que este tutor não
    #    pode fazer, e a instrução de "nenhum trecho recuperado" existe pra isso.
    if not chunks and retrieval.RE_CITACAO.search(resposta):
        achados.append(("erro", "citou artigo de lei sem nenhum trecho recuperado"))

    # 3b. O BURACO QUE A 3 DEIXAVA, e ele é o pior modo de falha do produto.
    #
    #     A 3 só dispara com `chunks` VAZIO. Medido no cenário `forense_do_zero`:
    #     o aluno perguntou "e o que é papiloscopia?", a busca devolveu seis
    #     trechos de CADEIA DE CUSTÓDIA (CPP 158-A a 158-F), e o tutor explicou
    #     papiloscopia de conhecimento próprio, sem citar nada. `chunks` não
    #     estava vazio, nenhum colchete apareceu — passou limpo pelas duas
    #     checagens, e o juiz ainda deu 4 em ancoragem olhando o turno anterior.
    #
    #     Não dá pra decidir por regra se a afirmação TEM fonte (é semântico).
    #     Dá pra apontar o formato de risco: explicação longa, declarativa, com
    #     ZERO citação, num turno em que havia trecho recuperado pra citar.
    #     Fica como AVISO e não erro, porque o tutor legitimamente responde sem
    #     citar quando fala do desempenho do aluno ou do edital dele.
    #     O `diz_assunto(fala)` saiu da condição: ele fazia a checagem calar
    #     justamente no turno 2 do cenário `quero_ler`, em que a fala é "só me
    #     explica o assunto" (nenhuma palavra de conteúdo) e a resposta afirmava
    #     conteúdo constitucional sem nenhuma fonte. Quem está sob suspeita é a
    #     RESPOSTA, não a pergunta.
    #     E PRECISA ESTAR ENSINANDO. A condição "longa e sem colchete" sozinha
    #     apontava a resposta a "como você funciona?" — "Sou seu professor
    #     particular para o concurso de Investigador da PC-PR..." —, que é
    #     legítima, vem do contexto da mesa e não afirma lei nenhuma. Dois sinais
    #     resolvem, e os dois vieram da bateria: ou a resposta INVOCA AUTORIDADE
    #     jurídica (artigo, lei, código, súmula, STF/STJ, jurisprudência), ou o
    #     aluno PEDIU explicação de matéria. Medido nos 6 casos apontados pela
    #     bateria: pega os 5 reais e solta o único falso positivo.
    ensinando = (RE_AUTORIDADE.search(resposta) or assunto.pede_exposicao(fala))
    if chunks and len(resposta) > 400 and not RE_COLCHETE.search(resposta) and ensinando:
        achados.append(("aviso", "explicou em bloco sem citar NENHUMA fonte, tendo "
                                 f"{len(chunks)} trecho(s) recuperado(s) — confira se "
                                 "afirmou matéria de conhecimento próprio"))

    # 3c. ARTIGO INVOCADO EM PROSA, sem colchete, que nenhum trecho sustenta.
    #
    #     Medido no cenário `quero_ler`, turno 2: a resposta afirmava "o art. 37,
    #     § 1º, da Constituição proíbe que nomes, símbolos ou imagens..." e os
    #     seis trechos recuperados eram L8112 art. 153, CP 321, CP 337-O, CP 319,
    #     L8112 114 e L8112 1º — nenhuma linha de CF. Passou pelas TRÊS checagens
    #     anteriores: a 3 exige `chunks` vazio, a 3b exige zero colchete (havia
    #     zero, mas a fala não "nomeava assunto" na versão de então) e a 4 só
    #     olha o que está DENTRO de colchete.
    #
    #     A regra é por NÚMERO e não por norma, de propósito: em prosa o aluno
    #     escreve "o art. 37 da Constituição" e `_identidade` espera a norma
    #     ANTES da vírgula, então casar identidade daria falso positivo em prosa
    #     legítima. Número que não existe em nenhum trecho recuperado é sinal
    #     limpo — o tutor invocou dispositivo que ninguém lhe mostrou.
    #     REFERIR não é AFIRMAR, e o corpus de regressão mostrou a diferença.
    #     "Para gerar uma questão sobre o artigo 312, utilize o botão" foi
    #     apontado como invenção: o tutor só apontava o assunto que a conversa
    #     já tinha tratado, sem dizer nada sobre o conteúdo do artigo. O teto de
    #     tamanho separa os dois casos sem precisar entender a frase — resposta
    #     de uma linha aponta, resposta de aula afirma. O caso legítimo tinha 90
    #     caracteres; o inventado ("os princípios expressos no art. 37 da
    #     Constituição, conhecidos pelo mnemônico LIMPE") passava de 500.
    numeros_recuperados = {"".join(ch for ch in str(c.get("artigo") or "") if ch.isdigit())
                           for c in chunks}
    for m in (retrieval.RE_CITACAO.finditer(RE_COLCHETE.sub("", resposta))
              if len(resposta) > 200 else []):
        so_digitos = "".join(ch for ch in m.group(1) if ch.isdigit())
        if so_digitos and so_digitos not in numeros_recuperados:
            achados.append(("erro", f"invocou art. {m.group(1)} em prosa, e nenhum trecho "
                                    f"recuperado é desse artigo"))
            break

    # 4. Colchete que o aluno não pode conferir. Quem decide isso é
    #    `socratic.com_fonte`, a MESMA função que `limpar_citacoes` usa pra apagar
    #    — e usá-la aqui não é elegância, é a única forma de o avaliador não
    #    contradizer o avaliado.
    #
    #    Eu havia escrito uma comparação por substring, e ela reprovou
    #    `[cp, art. 312, § 1º]` contra o trecho `cp, art. 312 — Peculato`. Estava
    #    errada, e de um jeito que importa: `_identidade` já decidiu, MEDINDO, que
    #    a fonte é norma + artigo e que o parágrafo acrescentado pelo modelo é
    #    refinamento sobre o que ele leu, não invenção. No caso real o § 1º do
    #    art. 312 É o peculato-furto, exatamente o que a resposta afirmava.
    #
    #    Terceira vez nesta sessão que eu recriei regra existente do projeto
    #    (antes: `palavras_de_conteudo` no lugar de `diz_assunto`, e o eco sem
    #    `e_eco`). O padrão é claro: se o avaliador precisa julgar algo, a régua
    #    já está em `core/` — importe, não reescreva.
    for citado in RE_COLCHETE.findall(resposta):
        if not socratic.com_fonte(citado, chunks):
            achados.append(("erro", f"citação sem fonte recuperada: [{citado}]"))

    # 5. Parede de texto em cima de cumprimento. O teste é `diz_assunto`, o
    #    MESMO que `assunto` usa pra decidir se a fala nomeia algo — reusado de
    #    propósito. Usar `palavras_de_conteudo` direto foi meu primeiro erro
    #    aqui, e ele apareceu na primeira rodada: "e o art. 312?" não tem
    #    palavra de conteúdo ("art" é vazia, "312" é dígito) e mesmo assim é a
    #    consulta mais precisa que este sistema aceita. `diz_assunto` já sabe
    #    disso; a cópia caseira não sabia.
    #
    #    ECO também não conta, e esse foi o segundo falso positivo — pego numa
    #    rodada real: "acho que sim", respondendo a "você já viu a diferença
    #    entre eficácia plena e limitada?", disparou o aviso em cima de uma
    #    explicação de 497 caracteres. Só que ali explicar é EXATAMENTE o certo:
    #    o aluno aceitou o convite. `e_eco` é a função que já separa "cumprimento
    #    sem assunto" de "resposta ao tutor", e é a mesma que decide de onde sai a
    #    consulta de busca — usar outra régua aqui produziria as duas leituras
    #    divergindo sobre o mesmo turno.
    #    E PEDIDO DE EXPOSIÇÃO também não conta — terceiro falso positivo desta
    #    mesma checagem, e o mais constrangedor: "não quero responder pergunta
    #    agora, só me explica o assunto" virou aviso de "742 caracteres para uma
    #    fala que não nomeia assunto". O aluno tinha pedido a resposta longa. O
    #    prompt ganhou a regra de exposição; o avaliador tem de concordar com
    #    ela, senão aponta como defeito o comportamento que o produto quer.
    if (not assunto.diz_assunto(fala) and not assunto.e_eco(fala, historico)
            and not assunto.pede_exposicao(fala)
            and len(resposta) > TETO_CUMPRIMENTO):
        achados.append(("aviso", f"{len(resposta)} caracteres para uma fala que não "
                                 f"nomeia assunto (teto {TETO_CUMPRIMENTO})"))

    # 6. O prompt manda terminar com pergunta — é o motor do diálogo. Menos
    #    quando a resposta É a instrução do botão: aí o próximo passo do aluno é
    #    clicar, não responder, e o prompt manda exatamente isso. O aviso saltava
    #    em todo pedido de questão, ou seja, num acerto — e aviso que dispara em
    #    acerto ensina você a ignorar avisos. Mesma ressalva já feita na ESCALA.
    #    E TURNO DE TREINO NÃO TERMINA COM PERGUNTA, por instrução: as QUESTÕES
    #    são a pergunta, e o prompt manda explicitamente "não pergunte de novo
    #    se ele quer". O aviso disparava nos quatro turnos do cenário
    #    `pede_treino`, ou seja, num acerto — e aviso que dispara em acerto
    #    ensina você a ignorar avisos. Mesma ressalva já feita pro botão.
    if ("?" not in resposta[-250:] and not RE_MANDA_BOTAO.search(resposta)
            and not (p_treino and not p_treino["formal"])):
        achados.append(("aviso", "não termina com pergunta"))

    return achados


# ═══════════════════════════════════════════════════════════════════ o juiz

# ════════════════════════════════════════════ a ESCALA (0 a 4 por dimensão)
#
# POR QUE ÂNCORA E NÃO NOTA SOLTA
# --------------------------------
# "Dê nota de 1 a 5 pra naturalidade" produz ruído: o modelo devolve 4 pra quase
# tudo, e a nota não se move quando o prompt melhora — que é justamente a única
# coisa que a gente quer que ela faça. O que dá sinal é ÂNCORA: cada nível
# descrito por um comportamento reconhecível, e o 0 sendo o defeito REAL que já
# aconteceu neste app. Aí o juiz não estima uma qualidade abstrata; ele casa a
# resposta com uma descrição.
#
# Só 0, 2 e 4 são descritos. Ímpar é interpolação declarada — descrever cinco
# níveis por dimensão infla o prompt sem separar melhor.
#
# EVIDÊNCIA É OBRIGATÓRIA, e é o que separa esta escala de opinião: nota sem
# turno citado não é auditável, e a primeira coisa que você vai querer fazer com
# um 2 é ir ver por quê.
#
# O QUE ESTA ESCALA NÃO É: medição. O juiz é da mesma família do avaliado
# (Gemini nos dois lados, porque é o único LLM configurado), então ele não
# estranha o que ele mesmo escreveria. Âncora e evidência reduzem isso; não
# eliminam. Uma rodada é RUÍDO — o número só vale comparado com outras rodadas
# do mesmo roteiro, e de preferência 3+ por variante de prompt.
# A RÉGUA TEM VERSÃO PRÓPRIA, e ela não é a do módulo.
#
# Nota só se compara com nota medida pela MESMA régua. Mudei as âncoras entre a
# primeira e a segunda rodada (a ressalva do botão, abaixo) e o placar agrupou as
# duas juntas: 60 e 57 na mesma média, como se fossem a mesma medida — e não são.
# Um placar que mistura réguas é pior que placar nenhum, porque parece rigor.
#
# Separada de `VERSAO` de propósito: mexer no spinner ou na cor da tabela não
# invalida histórico nenhum, e obrigar a isso faria a série reiniciar por
# cosmético. Suba SÓ quando mudar dimensão, âncora ou o texto do juiz.
ESCALA_VERSAO = "escala-v6"

ESCALA = [
    ("proporcao", "Tamanho proporcional à fala do aluno",
     "0 = despeja parágrafo de matéria densa em cima de um 'boa noite'"
     " · 2 = responde certo, mas sobra texto"
     " · 4 = cumprimento recebe uma linha; pergunta grande recebe resposta grande"),

    ("um_topico", "Um micro-tópico por resposta",
     "0 = explica dois institutos na mesma mensagem (direitos sociais e, no parágrafo"
     " seguinte, competência concorrente)"
     " · 2 = um assunto principal, com menção lateral a outro"
     " · 4 = um conceito só, do começo ao fim"),

    ("descobrir_antes", "Descobre o que o aluno sabe antes de explicar",
     "0 = despeja a explicação sem saber de onde o aluno parte, ou pergunta 'o que você"
     " sabe sobre X?', que devolve o trabalho pra ele"
     " · 2 = pergunta, mas genérica"
     " · 4 = uma pergunta curta e específica ('você já viu a diferença entre A e B?')"
     " · n/a se nenhum assunto novo foi aberto"),

    # PONTUE O PIOR TURNO, não a média — e isto está escrito na âncora porque a
    # régua já errou por não dizer: no cenário `forense_do_zero` o juiz deu 4
    # olhando um turno bem citado, enquanto o turno seguinte explicava
    # papiloscopia inteira sem nenhuma fonte. Uma invenção contamina a conversa
    # toda; a média deixa ela sumir no meio dos acertos.
    ("ancoragem", "Só afirma lei que tem trecho recuperado por trás (pontue o PIOR turno)",
     "0 = afirma conteúdo de matéria ou de lei que NÃO está nos trechos recuperados daquele"
     " turno — vale mesmo sem citar artigo nenhum, e é o defeito mais grave desta lista;"
     " também 0 se cita referência que não veio na busca"
     " · 2 = ancorado, mas cita mais fonte do que usa"
     " · 4 = tudo o que afirma tem trecho por trás, e o que não tem ele DIZ que não tem."
     " Confira turno a turno: um único turno inventado derruba a dimensão pra 0"),

    ("fidelidade", "Segue o assunto da CONVERSA, não o da palavra que casou na busca",
     "0 = troca de assunto porque um trecho repetiu uma palavra (responder sobre"
     " salário-família num diálogo sobre violência doméstica, por causa de"
     " 'dependência econômica')"
     " · 2 = menciona o trecho alheio antes de voltar"
     " · 4 = ignora o que voltou fora de assunto, e diz que o acervo não cobre aquilo"),

    # A RESSALVA DO BOTÃO, e por que ela está escrita na âncora.
    #
    # Na primeira rodada com escala, esta dimensão e `avanco` deram 0 pelo mesmo
    # motivo: o tutor mandou usar o botão "Quero questões sobre isto", e o juiz
    # anotou que "instruções sobre botões e interface quebram a ilusão de
    # conversar com um professor humano". Ele tem razão no MÉRITO — e mesmo assim
    # a nota estava errada, porque isso é decisão registrada, não deslize:
    # questão escrita solta no chat não tem proveniência, não entra na fila SM-2
    # e some quando a conversa rola.
    #
    # Sem a ressalva, toda rodada ficaria presa em ~60 por uma escolha já feita,
    # e a escala pararia de medir o que muda. Regra do projeto: decisão
    # registrada com MEDIÇÃO só cai com outra medição, e opinião de LLM não é
    # medição. Se um dia você quiser rever o botão, é conversa de produto — não
    # se resolve deixando o juiz descontar ponto por ele todo dia.
    ("voz_humana", "Soa professor, nunca sistema se descrevendo",
     "0 = usa o vocabulário do próprio funcionamento ('escada pedagógica', 'degrau',"
     " 'acervo', 'diagnóstico', 'trechos recuperados', 'contexto', 'prompt')"
     " · 2 = natural, com um deslize de jargão"
     " · 4 = nada no texto denuncia que existe um app por baixo."
     " RESSALVA: apontar o botão \"Quero questões sobre isto\" para quem pediu SIMULADO"
     " FORMAL é recurso deliberado e não desconta ponto; desconte se ele descrever COMO o"
     " app funciona por dentro, ou se mandar clicar em botão para quem só pediu treino —"
     " nesse caso o certo era fazer a pergunta no chat"),

    ("avanco", "Cada turno move a conversa adiante",
     "0 = fecha mensagens seguidas com o MESMO convite, ou repete explicação que já"
     " não funcionou"
     " · 2 = avança, mas a pergunta final é morna"
     " · 4 = termina com pergunta nova, sobre o que ACABOU de ser explicado."
     " RESSALVA: oferecer o botão UMA vez, quando o aluno pediu questão, é atender"
     " o pedido — só é repetição a partir da segunda vez seguida"),
]

ESQUEMA_ESCALA = {
    "type": "OBJECT",
    "properties": {
        "dimensoes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "chave": {"type": "STRING"},
                    # A evidência vem ANTES da nota, de propósito: o modelo
                    # escolhe o trecho e só então pontua, em vez de arredondar
                    # uma impressão e procurar justificativa depois. Mesma razão
                    # do `artigo` vir antes do enunciado em ESQUEMA_QUESTOES.
                    "evidencia": {"type": "STRING"},
                    "nota": {"type": "INTEGER"},
                },
                "required": ["chave", "evidencia", "nota"],
                "propertyOrdering": ["chave", "evidencia", "nota"],
            },
        },
        "o_que_mais_atrapalha": {"type": "STRING"},
    },
    "required": ["dimensoes", "o_que_mais_atrapalha"],
    "propertyOrdering": ["dimensoes", "o_que_mais_atrapalha"],
}

SISTEMA_JUIZ = (
    "Você audita a NATURALIDADE e a qualidade pedagógica de um tutor de concursos, lendo a "
    "transcrição de uma conversa. Você NÃO é o tutor e não deve ensinar Direito nem sugerir "
    "resposta melhor. "
    "Pontue cada dimensão de 0 a 4 usando as âncoras dadas, ou -1 para não aplicável. "
    "Toda nota exige evidência: cite o turno e um trecho curto entre aspas. Nota sem "
    "evidência da transcrição é inválida. "
    "Não seja gentil: 4 é o teto, reservado a quem cumpre a âncora inteira. Na dúvida entre "
    "dois níveis, dê o menor e explique na evidência."
)


def julgar(turnos: list[dict]) -> dict | None:
    """A escala aplicada à transcrição inteira, com evidência por dimensão."""
    historia = "\n\n".join(
        f"[turno {i//2 + 1}] {'ALUNO' if t['autor'] == 'aluno' else 'TUTOR'}: {t['texto']}"
        for i, t in enumerate(turnos))
    criterios = "\n".join(f"- {chave} ({titulo}): {ancora}" for chave, titulo, ancora in ESCALA)
    prompt = (f"Transcrição:\n\n{historia}\n\n"
              f"Pontue estas dimensões (0 a 4, ou -1 para não aplicável):\n\n{criterios}\n\n"
              f"Depois, em 'o_que_mais_atrapalha', diga em UMA frase o que mais atrapalhou "
              f"a naturalidade desta conversa.")
    # TEMPERATURA 0 no juiz, e a honestidade sobre o que isso NÃO resolveu.
    #
    # Eu baixei pra 0 esperando estabilizar a nota, porque três rodadas do mesmo
    # cenário deram 36, 93 e 57. Medi depois, e a hipótese estava errada: com
    # temperatura 0, o MESMO transcript julgado duas vezes deu 86 e 100 — a
    # dimensão `ancoragem` virou de 0 pra 4 sozinha. Gemini não é determinístico
    # a temperatura 0, então o juiz é fonte de ruído por si (~14 pontos), e o
    # tutor a 0.3 gera conversa diferente a cada rodada, somando o resto.
    #
    # Fica em 0 porque é o certo pra quem MEDE (menos uma fonte de variação, sem
    # custo), mas NÃO se apoie na nota de uma rodada nem de três: ela não separa
    # versão de prompt. O que separa é a contagem de erros de regra, que é código
    # e não opinião. Ver `docs/LIMITACOES.md`.
    d = llm.obter().gerar_json(prompt, SISTEMA_JUIZ, max_tokens=2000,
                               schema=ESQUEMA_ESCALA, temperatura=0)
    return d if isinstance(d, dict) and d.get("dimensoes") else None


def chave_curta(falas: list[str]) -> str:
    """Identidade estável de um roteiro seu, pra ele ter linha própria no placar.

    Hash e não as falas: o rótulo tem de caber numa coluna e ser IGUAL amanhã.
    Se você mudar uma vírgula do roteiro, vira outra chave — que é o certo, já
    que a nota deixou de ser comparável."""
    return hashlib.sha1("\x00".join(falas).encode()).hexdigest()[:8]


def nota_geral(julgamento: dict) -> tuple[int, int]:
    """(0-100, quantas dimensões contaram).

    Normalizado porque `descobrir_antes` pode ser n/a: sem isso, uma conversa em
    que nenhum assunto novo foi aberto seria punida por uma dimensão que não se
    aplicava a ela, e duas rodadas deixariam de ser comparáveis — que é a única
    coisa que este número precisa ser."""
    valem = [d["nota"] for d in julgamento["dimensoes"]
             if isinstance(d.get("nota"), int) and 0 <= d["nota"] <= 4]
    if not valem:
        return 0, 0
    return round(sum(valem) / (4 * len(valem)) * 100), len(valem)


# ══════════════════════════════════════════════════════════════════ a rodada

def _turno(uid: int, m: dict, conv: dict, fala: str,
           historico: list[dict], perfil: dict) -> dict:
    """Um turno como a ROTA faz, não como `socratic.explicar` faz.

    A diferença deixou de ser cosmética quando o pedido de treino passou a ser
    atendido pelo SERVIDOR (`core/pedido.py` + `geracao.sob_demanda`): chamando
    só `explicar`, o avaliador via a linha de abertura do tutor e não via se as
    questões foram geradas — ou seja, ficava cego justamente para o
    comportamento novo. Um avaliador que não passa pelo caminho de produção
    mede outra coisa.

    Reproduz a ordem da rota, e a ordem importa: o tema do treino sai do
    histórico ANTERIOR ao pedido (por isso `historico` vem por parâmetro, já
    capturado antes da gravação da fala), e falha do gerador não derruba o
    turno — vai `questoes: []` e a resposta do tutor, que já existe.
    """
    r = socratic.explicar(fala, uid, m["disciplinas"], m, historico, perfil)
    questoes: list[dict] = []
    p = pedido.treino(fala)
    if p and not p["formal"]:
        tema = assunto.em_foco(historico, disciplinas=m["disciplinas"])
        try:
            tipo = p["tipo"] or geracao.tipo_da_banca(m.get("banca"))
            questoes = geracao.sob_demanda(m["disciplinas"], tema,
                                           p["quantidade"], tipo)["questoes"]
        except (geracao.SemMaterial, ErroLLM):
            questoes = []
    return {**r, "questoes": questoes, "pedido": p}


def imprimir_fala(n: int, fala: str) -> None:
    """A fala do aluno vai pra tela ANTES de o tutor ser chamado.

    Não é enfeite: a chamada ao Gemini leva alguns segundos e, imprimindo o
    turno inteiro de uma vez só, a tela fica muda justamente enquanto o
    trabalho acontece — e quem está olhando não sabe se travou. Aqui a linha
    aparece, o spinner gira, e a resposta cai embaixo."""
    console.print(Rule(f"[bold]turno {n}", style="dim"))
    console.print(Text("ALUNO  ", style="bold cyan"), Text(fala), sep="")


def imprimir_busca(obs: dict) -> None:
    """O bloco que responde "o que foi para os vetores"."""
    t = Table(show_header=False, box=None, padding=(0, 1, 0, 3))
    t.add_column(style="dim", width=11)
    t.add_column(overflow="fold")
    if obs["vetorizado"]:
        t.add_row("vetorizado", Text(obs["vetorizado"], style="yellow"))
    elif obs["consulta"]:
        t.add_row("vetorizado", Text("nada — a busca resolveu sem vetor", style="dim"))
    else:
        t.add_row("vetorizado", Text("nada — não houve busca neste turno", style="dim"))
    if obs["consulta"] and obs["consulta"] != (obs["vetorizado"] or "")[7:]:
        t.add_row("consulta", Text(obs["consulta"], style="yellow"))
    t.add_row("estratégia", obs["estrategia"] or "—")
    if obs["chunks"]:
        for c in obs["chunks"]:
            t.add_row("", Text(f"· {retrieval.referencia(c)}", style="green"))
    else:
        t.add_row("trechos", Text("nenhum", style="dim"))
    # As questões que o SERVIDOR gerou neste turno. Aparecem aqui e não junto
    # da resposta porque são obra do app, não do tutor — e é justamente essa
    # distinção que o relatório precisa deixar visível.
    # A proveniência sai do BANCO, igual à checagem: `sob_demanda` não devolve
    # `fonte_chunks` no payload, e a primeira versão desta linha escrevia "SEM
    # PROVENIÊNCIA" em questão que tinha `[6028]` gravado. Rótulo mentiroso na
    # tela é pior que rótulo ausente — foi o que me fez caçar um bug que não
    # existia.
    qs = obs.get("questoes") or []
    fontes_gravadas = {}
    if qs:
        ids = [q["id"] for q in qs if q.get("id")]
        if ids:
            fontes_gravadas = {r["id"]: r["fonte_chunks"] for r in db.query(
                "SELECT id, fonte_chunks FROM questao WHERE id = ANY(%(i)s)", {"i": ids})}
    for q in qs:
        f = fontes_gravadas.get(q.get("id"))
        art = ", ".join(str(a) for a in f) if f else "[bold red]SEM PROVENIÊNCIA[/bold red]"
        t.add_row("questão", Text.from_markup(
            f"· {q.get('tema', '?')} [dim](chunk {art})[/dim]", style="cyan"))
    console.print(t)


def imprimir_resposta(resposta: str, achados: list[tuple[str, str]],
                      segundos: float) -> None:
    console.print(Text("TUTOR  ", style="bold magenta"), Text(resposta), sep="")
    for gravidade, texto in achados:
        estilo = "bold red" if gravidade == "erro" else "yellow"
        marca = "✗" if gravidade == "erro" else "!"
        console.print(f"       [{estilo}]{marca} {texto}[/{estilo}]")
    if not achados:
        console.print("       [green]✓ nenhuma regra conhecida violada[/green]")
    console.print(f"       [dim]{segundos:.1f}s[/dim]\n")


def _conta(email: str) -> int:
    """A conta em que a avaliação escreve — e a recusa da conta real.

    Não é zelo genérico: uma rodada grava conversa, mensagem e (com o botão de
    questões) tentativa. Rodar isto contra `CLI_USUARIO_EMAIL` sujaria o
    desempenho que o próprio tutor lê pra montar o "Números deste aluno", e o
    estrago só apareceria depois, numa resposta estranha. O AGENTS.md já manda
    testar contra usuário descartável; aqui a regra é executável."""
    if email.strip().lower() == CLI_USUARIO_EMAIL.strip().lower():
        console.print(f"[bold red]recusado:[/bold red] {email} é a conta real "
                      f"(CLI_USUARIO_EMAIL). Use uma conta descartável — o padrão "
                      f"({EMAIL_TESTE}) já é uma.")
        raise SystemExit(2)
    return auth.usuario_da_cli(email)


def rodar(falas: list[str] | None, persona: str, n_turnos: int,
          com_juiz: bool, email: str, cenario: str | None = None,
          semente: int | None = None, nome_mesa: str | None = None,
          acumular: bool = False) -> int:
    uid = _conta(email)
    # A MESA MUDA O QUE O TUTOR SABE: é dela que saem o concurso-alvo, a banca e
    # as disciplinas do edital, e é isso que o prompt recebe como "Contexto do
    # aluno". Avaliar sempre na mesa padrão (sem edital) testa o tutor cego —
    # justamente o caso que menos acontece com um aluno de verdade.
    if nome_mesa:
        escolhida = next((x for x in mesa.listar(uid)
                          if x["nome"].lower() == nome_mesa.lower()), None)
        if not escolhida:
            console.print(f"[red]mesa '{nome_mesa}' não existe nessa conta.[/red] "
                          f"Mesas: {', '.join(x['nome'] for x in mesa.listar(uid)) or '(nenhuma)'}")
            return 2
        m = mesa.contexto(uid, escolhida["id"])
    else:
        m = mesa.contexto(uid)
    perfil = auth.perfil(uid)
    conv = conversa.criar(uid, m["id"], "avaliação automática")

    # O rótulo entra no placar e é o que torna duas linhas COMPARÁVEIS: nota de
    # roteiro fixo não se compara com nota de conversa livre, e roteiro seu não
    # se compara com o das regressões. Sem isso o placar viraria uma coluna de
    # números de origens diferentes — pior que não ter placar.
    if cenario:
        rotulo_roteiro = cenario
    elif falas is None:
        rotulo_roteiro = f"llm:{persona}"
    else:
        rotulo_roteiro = "custom:" + chave_curta(falas)

    # Semente explícita torna a rodada `--livre` REPETÍVEL: a abertura sorteada
    # volta a mesma, e aí a única variável que resta é o modelo. Sem semente,
    # sorteia de verdade — que é o padrão certo, porque o valor do modo livre é
    # justamente cair onde ninguém apontou.
    sorteio = random.Random(semente) if semente is not None else random.Random()

    console.print(Panel(
        f"tutor: [bold]{llm.obter().__class__.__name__}[/bold]  ·  "
        f"aluno: [bold]{('cenário ' + cenario) if cenario else ('roteiro fixo' if falas else f'LLM ({persona})')}[/bold]  ·  "
        f"conta: {email}  ·  mesa: {m.get('nome') or '—'}\n"
        f"disciplinas do recorte: {', '.join(m['disciplinas']) if m['disciplinas'] else 'todas'}",
        title=f"avaliar_chat {VERSAO}", border_style="blue"))

    antes = vetores_gravados()
    obs = Observador()
    obs.instalar()
    turnos_planos: list[dict] = []
    total = {"erro": 0, "aviso": 0}
    try:
        for i in range(n_turnos):
            if falas:
                fala = falas[i]
            else:
                # A cota estoura tanto aqui quanto no tutor, e só o tutor estava
                # protegido: um 429 gerando a fala do ALUNO derrubava a bateria
                # inteira com traceback, no meio de `--refazer`, depois de os
                # arquivos já terem sido zerados. Falhar é aceitável; levar o
                # resto junto, não.
                try:
                    with console.status("[dim]o aluno está escrevendo…", spinner="dots"):
                        fala = fala_do_aluno(persona, turnos_planos, i + 1, sorteio)
                except ErroLLM as e:
                    console.print(f"[red]LLM indisponível ao gerar a fala do aluno "
                                  f"no turno {i+1}: {e}[/red]")
                    break
            imprimir_fala(i + 1, fala)

            historico = conversa.historico_para_prompt(conv["id"])
            conversa.gravar(conv["id"], "aluno", fala)
            atual = obs.novo_turno()
            inicio = time.monotonic()
            try:
                with console.status("[dim]buscando e chamando o tutor…", spinner="dots"):
                    r = _turno(uid, m, conv, fala, historico, perfil)
            except ErroLLM as e:
                console.print(f"[red]LLM indisponível no turno {i+1}: {e}[/red]")
                break
            segundos = time.monotonic() - inicio
            conversa.gravar(conv["id"], "tutor", r["resposta"])
            atual["questoes"] = r.get("questoes") or []

            achados = checar(fala, r["resposta"], r["fontes"], historico,
                             r.get("questoes"))
            for gravidade, _ in achados:
                total[gravidade] += 1
            imprimir_busca(atual)
            imprimir_resposta(r["resposta"], achados, segundos)

            turnos_planos.append({"autor": "aluno", "texto": fala})
            # Guarda a IDENTIDADE do chunk (titulo/norma/artigo) além do rótulo:
            # é o que `--reprocessar` precisa pra rodar `com_fonte` de novo sem
            # o banco. Só o rótulo obrigava a reconstruir o artigo por regex, e
            # reconstrução aproximada num corpus de regressão contamina o
            # resultado que ele existe pra dar.
            turnos_planos.append({"autor": "tutor", "texto": r["resposta"],
                                  "obs": {**atual,
                                          "chunks": [retrieval.referencia(c)
                                                     for c in atual["chunks"]],
                                          "questoes": [{"id": q.get("id"),
                                                        "tema": q.get("tema"),
                                                        "fonte_chunks": q.get("fonte_chunks")}
                                                       for q in (atual.get("questoes") or [])],
                                          "fontes": [{"titulo": c.get("titulo"),
                                                      "norma": c.get("norma"),
                                                      "artigo": c.get("artigo"),
                                                      "rubrica": c.get("rubrica")}
                                                     for c in atual["chunks"]]},
                                  "achados": achados})
    finally:
        obs.restaurar()

    depois = vetores_gravados()
    console.print(Rule("resumo", style="dim"))
    console.print(f"  {total['erro']} erro(s) de regra · {total['aviso']} aviso(s)")
    console.print(f"  embedding_cache: {antes} → {depois} vetores "
                  f"({'nenhum gravado — conversar não escreve vetor' if antes == depois else 'CRESCEU'})")

    julgamento = None
    if com_juiz and turnos_planos:
        console.print(Rule("escala de naturalidade", style="dim"))
        try:
            with console.status("[dim]o juiz está pontuando a conversa inteira…",
                                spinner="dots"):
                julgamento = julgar(turnos_planos)
            if julgamento:
                imprimir_escala(julgamento)
            else:
                console.print("[yellow]o juiz devolveu resposta sem dimensões[/yellow]")
        except ErroLLM as e:
            console.print(f"[red]juiz indisponível: {e}[/red]")

    if julgamento:
        _gravar_placar(julgamento, total, rotulo_roteiro, len(turnos_planos) // 2)

    destino = _gravar(turnos_planos, total, antes, depois, m)
    console.print(f"\n  transcrição: [bold]{destino}[/bold]")

    partes_cmd = ["./testar.sh"]
    if cenario:
        partes_cmd += ["--cenario", cenario]
    elif falas is None:
        partes_cmd += ["--livre", "--persona", persona, "--turnos", str(n_turnos)]
        if semente is not None:
            partes_cmd += ["--semente", str(semente)]
    else:
        partes_cmd += ["--falas"] + [f'"{f}"' for f in falas]
    if nome_mesa:
        partes_cmd += ["--mesa", f'"{nome_mesa}"']
    if email != EMAIL_TESTE:
        partes_cmd += ["--email", email]
    # AS FALAS VÃO SEMPRE, inclusive as do cenário. Guardar `None` porque "o
    # cenário já diz quais são" fez `--refazer` passar None adiante, e `rodar`
    # lê None como "aluno é um LLM" — a reprodução virava conversa improvisada
    # com o RÓTULO do cenário colado nela. Pior que não reproduzir: reproduz
    # errado e chama de reprodução. Guardar as falas também congela o cenário
    # como ele era, se alguém editar `CENARIOS` depois.
    receita = {"cenario": cenario, "falas": falas,
               "persona": persona, "turnos": n_turnos, "semente": semente,
               "mesa": nome_mesa, "email": email, "juiz": com_juiz}
    defeitos = _gravar_defeitos(turnos_planos, total, m, julgamento,
                                " ".join(partes_cmd), anexar=acumular, receita=receita)
    velho = Path(__file__).resolve().parents[2] / ".logs" / "defeitos.md"
    if not defeitos and not acumular and velho.exists():
        # Rodada limpa NÃO apaga o arquivo: ele pode guardar o defeito de OUTRO
        # cenário, e apagá-lo aqui perderia informação que ninguém pediu pra
        # perder. Mas deixá-lo em silêncio faz você ler resultado velho achando
        # que é deste comando — então diz, e diz de quando ele é.
        from datetime import datetime as _dt
        quando = _dt.fromtimestamp(velho.stat().st_mtime).strftime("%d/%m %H:%M")
        console.print(f"\n  [green]nada a apontar nesta rodada.[/green] "
                      f"[dim].logs/defeitos.md continua sendo o de {quando} — "
                      f"`--refazer` reescreve, `--cenario todos` zera.[/dim]")
    if defeitos:
        rel = defeitos.relative_to(Path(__file__).resolve().parents[2])
        console.print(f"  defeitos:    [bold]{rel}[/bold]")
        console.print(Panel(f'[bold]conserta os defeitos em {rel}[/bold]',
                            title="pra entregar a um agente de IA (Claude Code, Cursor…)",
                            subtitle="o arquivo tem turno, busca, resposta e onde olhar",
                            border_style="yellow", expand=False))
    return 1 if total["erro"] else 0


# Onde procurar a causa de cada classe de defeito. NÃO é diagnóstico — é o
# ponteiro que economiza a primeira meia hora de quem vai consertar. Cada linha
# saiu de um caso real, e a mais importante é a primeira: as três regressões de
# vocabulário deste projeto tiveram a mesma causa, que é a palavra existir DENTRO
# do prompt.
PISTAS = {
    "vocabulário de sistema": (
        "`core/socratic.py`, dentro de `explicar`: procure a palavra no PRÓPRIO texto do "
        "prompt (`grep -n '<palavra>' core/socratic.py`). As três regressões desta classe "
        "([DESEMPENHO REAL DO ALUNO], \"escada pedagógica\", e agora esta) vazaram porque a "
        "palavra estava escrita na instrução — proibir sem tirar da instrução não funciona."),
    "questão de múltipla escolha": (
        "`core/socratic.py`: a instrução manda oferecer o botão \"Quero questões sobre isto\" "
        "em vez de escrever a questão. Questão solta no chat não tem proveniência, não entra "
        "na fila SM-2 e some quando a conversa rola."),
    "citou artigo de lei sem": (
        "`core/socratic.py`, o bloco \"### Trechos de lei recuperados / Nenhum —\": a ausência "
        "de material é declarada justamente pra proibir isto. Se vazou, a instrução perdeu "
        "força ou o turno tinha outra fonte de contexto."),
    "citação sem fonte recuperada": (
        "`socratic.limpar_citacoes` + `retrieval.referencia`: as duas têm de formar o rótulo "
        "pela MESMA regra. Divergência entre elas é o modo de falha conhecido."),
    "caracteres para uma fala": (
        "`core/socratic.py`, a instrução \"RESPONDA NO TAMANHO DA PERGUNTA\". Confira antes se "
        "não é falso positivo: `assunto.e_eco` já isenta resposta a pergunta do tutor."),
    "não termina com pergunta": (
        "`core/socratic.py`, o fecho \"Termine com uma pergunta ou sugestão\". Costuma ser "
        "aceitável quando a resposta é uma instrução de botão — julgue, não conserte no reflexo."),
}


def _pista(texto: str) -> str | None:
    for chave, pista in PISTAS.items():
        if chave in texto:
            return pista
    return None


PLACAR = "placar.jsonl"


def imprimir_escala(j: dict) -> None:
    titulos = {chave: titulo for chave, titulo, _ in ESCALA}
    nota, quantas = nota_geral(j)

    t = Table(show_header=True, box=None, padding=(0, 1, 0, 2), header_style="dim")
    t.add_column("dimensão", width=17)
    t.add_column("", width=11)
    t.add_column("evidência", overflow="fold")
    for d in j["dimensoes"]:
        n = d.get("nota")
        if not isinstance(n, int) or n < 0:
            barra, estilo = "n/a", "dim"
        else:
            barra = "█" * n + "·" * (4 - n) + f" {n}"
            estilo = "red" if n <= 1 else ("yellow" if n == 2 else "green")
        t.add_row(titulos.get(d["chave"], d["chave"]),
                  Text(barra, style=estilo), Text(d.get("evidencia", ""), style="dim"))
    console.print(t)
    cor = "red" if nota < 60 else ("yellow" if nota < 80 else "green")
    console.print(f"\n  naturalidade: [bold {cor}]{nota}/100[/bold {cor}] "
                  f"[dim]({quantas} dimensões aplicáveis · uma rodada é ruído, "
                  f"compare 3+)[/dim]")
    console.print(f"  o que mais atrapalha: {j.get('o_que_mais_atrapalha', '—')}")


def _gravar_placar(j: dict, total: dict, roteiro: str, turnos: int) -> None:
    """Uma linha por rodada, pra nota de hoje poder ser comparada com a de ontem.

    JSONL e append: o valor está na SÉRIE, não na última linha. Guarda as versões
    dos módulos porque a pergunta que este arquivo existe pra responder é "o
    socratic-v36 ficou melhor que o v35?" — sem elas, é uma coluna de números sem
    causa."""
    nota, quantas = nota_geral(j)
    linha = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "roteiro": roteiro,
        "turnos": turnos,
        "nota": nota,
        "dimensoes_validas": quantas,
        "erros": total["erro"],
        "avisos": total["aviso"],
        "notas": {d["chave"]: d.get("nota") for d in j["dimensoes"]},
        "escala": ESCALA_VERSAO,
        "versoes": {"avaliar": VERSAO, "socratic": socratic.VERSAO,
                    "assunto": assunto.VERSAO, "retrieval": retrieval.VERSAO},
        "o_que_mais_atrapalha": j.get("o_que_mais_atrapalha", ""),
    }
    pasta = Path(__file__).resolve().parents[2] / ".logs"
    pasta.mkdir(exist_ok=True)
    with (pasta / PLACAR).open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def mostrar_placar(limite: int = 20) -> int:
    """O histórico. É aqui que a escala vira ferramenta em vez de nota solta."""
    arq = Path(__file__).resolve().parents[2] / ".logs" / PLACAR
    if not arq.exists():
        console.print("ainda não há placar — rode `./testar.sh` (com o juiz) ao menos uma vez.")
        return 0
    linhas = [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]

    t = Table(title=f"placar — últimas {min(limite, len(linhas))} de {len(linhas)} rodadas",
              header_style="dim")
    t.add_column("quando"); t.add_column("roteiro"); t.add_column("socratic")
    t.add_column("régua"); t.add_column("nota", justify="right")
    t.add_column("err", justify="right")
    t.add_column("o que mais atrapalha", overflow="fold", max_width=38)
    for l in linhas[-limite:]:
        nota = l.get("nota", 0)
        cor = "red" if nota < 60 else ("yellow" if nota < 80 else "green")
        t.add_row(l["quando"][5:16].replace("T", " "), l.get("roteiro", "—"),
                  l.get("versoes", {}).get("socratic", "—"),
                  l.get("escala", "escala-v1"),
                  Text(str(nota), style=f"bold {cor}"),
                  str(l.get("erros", 0)), l.get("o_que_mais_atrapalha", ""))
    console.print(t)

    # A RÉGUA ENTRA NA CHAVE junto do roteiro e da versão do prompt. Uma rodada é
    # ruído; rodadas de roteiros diferentes não se comparam; e rodadas de RÉGUAS
    # diferentes tampouco — foi o erro que este agrupamento cometeu na estreia,
    # somando 60 (âncora antiga) com 57 (âncora nova) numa média de 58,5 que não
    # significava nada.
    grupos: dict[tuple, list[int]] = {}
    for l in linhas:
        grupos.setdefault((l.get("roteiro"), l.get("versoes", {}).get("socratic"),
                           l.get("escala", "escala-v1")), []).append(l.get("nota", 0))
    console.print("\n  média por roteiro × prompt × régua "
                  "[dim](só compare linhas da MESMA régua)[/dim]:")
    for (rot, ver, reg), notas in sorted(grupos.items(), key=lambda x: tuple(map(str, x[0]))):
        aviso = "  [dim](1 rodada — ruído)[/dim]" if len(notas) == 1 else ""
        console.print(f"    {str(rot):20} {str(ver):14} {str(reg):11} "
                      f"{sum(notas)/len(notas):5.1f}  (n={len(notas)}){aviso}")
    return 0


def _gravar_defeitos(turnos, total, m, julgamento: dict | None,
                     comando: str = "./testar.sh", anexar: bool = False,
                     receita: dict | None = None) -> Path | None:
    """Só os DEFEITOS, num arquivo de nome FIXO, pra entregar a um agente de IA.

    Nome fixo (`.logs/defeitos.md`) e não carimbado de propósito: o consumidor
    é uma frase como "conserta os defeitos em .logs/defeitos.md", e ela não pode
    depender de você copiar um timestamp do terminal. A transcrição completa
    continua carimbada, porque ali o valor é justamente o histórico.

    Devolve `None` quando não houve nada — arquivo vazio de defeito é pior que
    arquivo nenhum, porque parece resultado velho.

    RODADA LIMPA NÃO ENTRA, nem com o juiz ligado. A primeira versão gravava
    sempre que houvesse julgamento, e como o juiz está ligado por padrão isso
    quer dizer SEMPRE: a bateria de 9 cenários deixou 9 seções no arquivo, das
    quais 8 estavam com zero erro e zero aviso. Um arquivo chamado `defeitos.md`
    que lista rodadas em ordem não responde a pergunta que ele existe pra
    responder — "o que ainda está quebrado?" — e obriga quem lê a filtrar na
    mão. A escala continua no arquivo, mas como CONTEXTO de um defeito, não como
    conteúdo próprio.

    A consequência é o sinal que faltava: consertado tudo, `--refazer` não
    escreve nada e o arquivo desaparece. Ausência passa a significar limpo.

    `anexar` existe por causa do `--cenario todos`: dez cenários rodavam em
    sequência e cada um sobrescrevia este arquivo, então nove relatórios eram
    jogados fora e sobrava o do último. O nome continua fixo (é o endereço que
    você passa pro agente); o que muda é que a bateria ACUMULA, com uma seção
    por cenário. Quem zera é o `--cenario todos`, uma vez, antes do primeiro."""
    if not total["erro"] and not total["aviso"]:
        return None
    raiz = Path(__file__).resolve().parents[2]
    pasta = raiz / ".logs"
    pasta.mkdir(exist_ok=True)
    destino = pasta / "defeitos.md"
    continuando = anexar and destino.exists()

    # O COMANDO QUE REPRODUZ, no topo e antes de tudo. Sem ele o arquivo diz o
    # que quebrou e não diz como voltar lá: quem for consertar tem de adivinhar
    # o cenário e a mesa, e quem consertou não tem como provar que consertou.
    # Vale mais que o resto do cabeçalho, então vem primeiro.
    titulo = (f"# defeitos do chat — {datetime.now():%Y-%m-%d %H:%M}"
              if not continuando else "---")
    L = [titulo, "",
         "**Para rodar este mesmo chat de novo, depois de consertar:**", "",
         f"```bash\n{comando}\n```", "",
         "As falas do ALUNO são idênticas a cada execução; as do tutor variam (ele roda a 0.3).",
         "Uma rodada não decide — compare 3, e olhe a CONTAGEM DE ERROS, não a nota.", "",
         "Gerado por `avaliar_chat.py`. Cada item traz o turno inteiro (a fala do aluno, o que",
         "foi buscado, a resposta) e um ponteiro para onde a causa costuma estar. O ponteiro é",
         "pista, não diagnóstico — confirme antes de mexer.", "",
         f"- versões: `{VERSAO}` · tutor `{socratic.VERSAO}` · assunto `{assunto.VERSAO}` · "
         f"retrieval `{retrieval.VERSAO}`",
         f"- mesa: {m.get('nome') or '—'} · disciplinas: "
         f"{', '.join(m['disciplinas']) if m['disciplinas'] else 'todas'}",
         f"- {total['erro']} erro(s) de regra, {total['aviso']} aviso(s)", ""]

    n = 0
    fala_atual = ""
    for t in turnos:
        if t["autor"] == "aluno":
            n += 1
            fala_atual = t["texto"]
            continue
        if not t["achados"]:
            continue
        o = t["obs"]
        L += [f"## turno {n}", "",
              f"**O aluno disse:** {fala_atual}", "",
              f"**O que foi vetorizado:** `{o['vetorizado'] or 'nada'}`  ",
              f"**Estratégia de busca:** {o['estrategia'] or 'nenhuma'}  ",
              f"**Trechos recuperados:** {', '.join(o['chunks']) if o['chunks'] else 'nenhum'}",
              "", "**O tutor respondeu:**", "",
              "> " + t["texto"].replace("\n", "\n> "), "", "**Apontado:**", ""]
        for gravidade, texto in t["achados"]:
            L.append(f"- {'**ERRO**' if gravidade == 'erro' else 'aviso'}: {texto}")
            pista = _pista(texto)
            if pista:
                L.append(f"  - onde olhar: {pista}")
        L.append("")

    if julgamento:
        nota, quantas = nota_geral(julgamento)
        titulos = {c: t for c, t, _ in ESCALA}
        L += ["## escala de naturalidade (juiz LLM — opinião ancorada, não medição)", "",
              f"**{nota}/100** em {quantas} dimensões aplicáveis. Uma rodada é ruído: "
              "compare com `.logs/placar.jsonl`.", "",
              "| dimensão | nota | evidência |", "|---|---|---|"]
        for d in julgamento["dimensoes"]:
            n = d.get("nota")
            L.append(f"| {titulos.get(d['chave'], d['chave'])} | "
                     f"{'n/a' if not isinstance(n, int) or n < 0 else f'{n}/4'} | "
                     f"{(d.get('evidencia') or '').replace('|', '/')} |")
        L += ["", f"**O que mais atrapalha:** {julgamento.get('o_que_mais_atrapalha', '—')}", ""]

    L += ["### antes de consertar", "",
          "- `docs/DECISOES.md` e `docs/LIMITACOES.md`: várias \"melhorias óbvias\" daqui já",
          "  foram medidas e revertidas. Decisão registrada com MEDIÇÃO só cai com outra medição.",
          "- Mexeu no prompt? Rode `./testar.sh` de novo e LEIA. Texto ruim é texto válido:",
          "  nenhuma dessas falhas aparece no pytest.", ""]
    if continuando:
        with destino.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(L))
    else:
        destino.write_text("\n".join(L), encoding="utf-8")

    # O COMPANHEIRO LEGÍVEL POR MÁQUINA. O `.md` é pra pessoa (e pro agente)
    # ler; `--refazer` precisa dos ARGUMENTOS, e extraí-los de volta da linha de
    # comando em markdown seria parsing frágil de algo que eu mesmo acabei de
    # serializar. Guarda também a contagem de erros: é ela que vira o "antes" da
    # comparação depois do conserto.
    lado = destino.with_suffix(".json")
    anteriores = []
    if continuando and lado.exists():
        try:
            anteriores = json.loads(lado.read_text(encoding="utf-8"))
        except ValueError:
            anteriores = []
    anteriores.append({"comando": comando, "receita": receita or {},
                       "erros": total["erro"], "avisos": total["aviso"]})
    lado.write_text(json.dumps(anteriores, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def _gravar(turnos, total, antes, depois, m) -> Path:
    """Markdown, e não JSON: o consumidor é uma pessoa lendo (ou um agente de IA
    a quem você manda o arquivo). O JSON fica junto pra quem quiser diffar duas
    rodadas."""
    raiz = Path(__file__).resolve().parents[2]
    pasta = raiz / ".logs"
    pasta.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = pasta / f"avaliar-chat-{carimbo}.md"

    linhas = [f"# avaliação do chat — {carimbo}", "",
              f"- versão: `{VERSAO}` · tutor: `{socratic.VERSAO}` · "
              f"assunto: `{assunto.VERSAO}` · retrieval: `{retrieval.VERSAO}`",
              f"- mesa: {m.get('nome') or '—'} · disciplinas: "
              f"{', '.join(m['disciplinas']) if m['disciplinas'] else 'todas'}",
              f"- {total['erro']} erro(s) de regra, {total['aviso']} aviso(s)",
              f"- embedding_cache: {antes} → {depois}", ""]
    n = 0
    for t in turnos:
        if t["autor"] == "aluno":
            n += 1
            linhas += [f"## turno {n}", "", f"**Aluno:** {t['texto']}", ""]
        else:
            o = t["obs"]
            linhas += ["<details><summary>o que o sistema fez</summary>", "",
                       f"- vetorizado: `{o['vetorizado'] or 'nada'}`",
                       f"- estratégia: {o['estrategia'] or '—'}",
                       f"- trechos: {', '.join(o['chunks']) if o['chunks'] else 'nenhum'}",
                       "", "</details>", "", f"**Tutor:** {t['texto']}", ""]
            for gravidade, texto in t["achados"]:
                linhas.append(f"> {'✗' if gravidade == 'erro' else '!'} {texto}")
            linhas.append("")
    destino.write_text("\n".join(linhas), encoding="utf-8")
    (destino.with_suffix(".json")).write_text(
        json.dumps(turnos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return destino


RE_ART_ROTULO = re.compile(r"art\. ([0-9A-Za-z\-º]+)")


def _fontes_do_registro(obs: dict) -> list[dict]:
    """Os chunks de um turno gravado, pra `checar` rodar de novo sem banco.

    Transcrição nova traz `fontes` com a identidade completa. As antigas só têm
    o RÓTULO, e daí o artigo sai por regex — aproximação declarada: `referencia`
    monta "cp, art. 312 — Peculato", então título e número voltam, a rubrica
    não. Suficiente pro que as checagens perguntam (norma + artigo), e o
    relatório avisa quando a linha veio desse caminho."""
    if obs.get("fontes"):
        return obs["fontes"]
    saida = []
    for rotulo in obs.get("chunks") or []:
        m = RE_ART_ROTULO.search(rotulo)
        titulo = rotulo.split(",")[0].strip()
        saida.append({"titulo": titulo, "norma": titulo,
                      "artigo": m.group(1) if m else None, "rubrica": None})
    return saida


def reprocessar() -> int:
    """Roda as checagens de HOJE sobre todas as conversas já gravadas.

    Isto responde "o conserto pegou?" pela metade que não precisa de LLM: as
    regras. Os ~140 turnos de resposta real gravados são um corpus de regressão
    de graça — e é o único jeito de saber se uma checagem nova só encontra o que
    devia, em vez de encher a tela de falso positivo.

    O QUE ELE NÃO PROVA, e a distinção importa: nada sobre o PROMPT. Estas são
    as respostas que o tutor deu ANTES do conserto; para saber se ele mudou, é
    preciso conversa nova (`./testar.sh --cenario todos`), que custa cota."""
    raiz = Path(__file__).resolve().parents[2]
    arquivos = sorted((raiz / ".logs").glob("avaliar-chat-*.json"))
    if not arquivos:
        console.print("nenhuma transcrição gravada ainda.")
        return 0

    t = Table(title=f"reprocessando {len(arquivos)} transcrições com {VERSAO}",
              header_style="dim")
    t.add_column("quando"); t.add_column("turnos", justify="right")
    t.add_column("antes", justify="right"); t.add_column("agora", justify="right")
    t.add_column("mudou", overflow="fold")

    somem: dict[str, int] = {}
    surgem: dict[str, int] = {}
    turnos_totais = aproximados = 0
    for arq in arquivos:
        try:
            turnos = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # O HISTÓRICO TEM DE SER REMONTADO, e esquecer isso fez o reprocessador
        # mentir na estreia: `checar` chamado sem histórico deixa `e_eco` cego,
        # a isenção de eco some e o teto de tamanho dispara em turno que estava
        # certo. Foram 9 achados fantasmas na primeira execução — mais do que
        # todos os falsos positivos que este dia consertou. Ferramenta de
        # regressão que inventa achado é pior que não ter ferramenta.
        fala, antes_n, agora_n, deltas = None, 0, 0, []
        historico: list[dict] = []
        for turno in turnos:
            if turno.get("autor") == "aluno":
                fala = turno.get("texto")
                continue
            obs = turno.get("obs") or {}
            if obs.get("chunks") and not obs.get("fontes"):
                aproximados += 1
            chunks = _fontes_do_registro(obs)
            antes = {a[1] for a in (turno.get("achados") or [])}
            agora = {a[1] for a in checar(fala or "", turno.get("texto") or "",
                                          chunks, historico, obs.get("questoes"))}
            # Só DEPOIS de checar: no turno real, o histórico que `explicar`
            # recebeu era o de ANTES desta fala.
            historico.append({"autor": "aluno", "texto": fala or ""})
            historico.append({"autor": "tutor", "texto": turno.get("texto") or ""})
            turnos_totais += 1
            antes_n += len(antes); agora_n += len(agora)
            for x in antes - agora:
                somem[x.split("—")[0].split(":")[0].strip()] = \
                    somem.get(x.split("—")[0].split(":")[0].strip(), 0) + 1
                deltas.append(f"[green]-[/green] {x[:52]}")
            for x in agora - antes:
                surgem[x.split("—")[0].split(":")[0].strip()] = \
                    surgem.get(x.split("—")[0].split(":")[0].strip(), 0) + 1
                deltas.append(f"[yellow]+[/yellow] {x[:52]}")
        if antes_n or agora_n:
            t.add_row(arq.stem[-13:], str(len(turnos) // 2), str(antes_n), str(agora_n),
                      "\n".join(deltas) or "[dim]igual[/dim]")
    console.print(t)
    console.print(f"\n  {turnos_totais} turnos reprocessados"
                  + (f" · {aproximados} com fontes reconstruídas do rótulo (aproximado)"
                     if aproximados else ""))
    if somem:
        console.print("\n  [green]deixaram de ser apontados[/green] (falso positivo removido, "
                      "ou regra afrouxada — confira qual):")
        for k, n in sorted(somem.items(), key=lambda x: -x[1]):
            console.print(f"    {n:4}x  {k}")
    if surgem:
        console.print("\n  [yellow]passaram a ser apontados[/yellow] (defeito que escapava, "
                      "ou falso positivo novo — confira qual):")
        for k, n in sorted(surgem.items(), key=lambda x: -x[1]):
            console.print(f"    {n:4}x  {k}")
    return 0


def refazer() -> int:
    """Roda de novo, e de uma vez, TODAS as rodadas que o defeitos.md registrou.

    Existe por um buraco de uso real: a bateria deixa dois cenários com defeito,
    você conserta os dois, e aí rodar um de cada vez faz o segundo APAGAR o
    registro do primeiro — o arquivo tem nome fixo. Ficava impossível ver os
    dois consertados ao mesmo tempo.

    Aqui os dois (ou dez) são refeitos na mesma passada, com os mesmos
    argumentos, e o arquivo é reescrito inteiro. No fim sai o antes × depois de
    cada um, que é a prova que o AGENTS.md pede — e a contagem de ERROS, não a
    nota, porque a nota não separa versões (ver `docs/LIMITACOES.md`)."""
    lado = Path(__file__).resolve().parents[2] / ".logs" / "defeitos.json"
    if not lado.exists():
        console.print("não há defeitos registrados — rode `./testar.sh` antes.")
        return 0
    receitas = json.loads(lado.read_text(encoding="utf-8"))
    if not receitas:
        console.print("o defeitos.json está vazio.")
        return 0

    console.print(Panel(
        "\n".join(f"· {r['comando']}   [dim](antes: {r['erros']} erro(s), "
                  f"{r['avisos']} aviso(s))[/dim]" for r in receitas),
        title=f"refazendo {len(receitas)} rodada(s)", border_style="blue"))

    # GUARDA O ANTERIOR ANTES DE ZERAR. A primeira versão apagava os dois e saía
    # rodando; a bateria estourou a cota no meio e o relatório de 9 cenários
    # virou um de 4, sem volta. As transcrições carimbadas salvaram o conteúdo,
    # mas contar com isso é sorte, não desenho. `.anterior` fica no disco até a
    # próxima execução — custa nada e é o suficiente pra desfazer.
    md = lado.with_suffix(".md")
    for orig in (md, lado):
        if orig.exists():
            orig.replace(orig.with_suffix(f".anterior{orig.suffix}"))

    antes = [(r["comando"], r["erros"], r["avisos"]) for r in receitas]
    pior = 0
    for r in receitas:
        c = r.get("receita") or {}
        console.print(Rule(f"[bold]{r['comando']}", style="blue"))
        falas_r = c.get("falas")
        if falas_r is None and c.get("cenario") in CENARIOS:
            falas_r = CENARIOS[c["cenario"]][1]      # receita antiga, sem as falas
        pior = max(pior, rodar(falas_r, c.get("persona") or "iniciante",
                               len(falas_r) if falas_r else (c.get("turnos") or 6),
                               c.get("juiz", True),
                               c.get("email") or EMAIL_TESTE,
                               cenario=c.get("cenario"), semente=c.get("semente"),
                               nome_mesa=c.get("mesa"), acumular=True))

    depois = {}
    if lado.exists():
        for r in json.loads(lado.read_text(encoding="utf-8")):
            depois[r["comando"]] = (r["erros"], r["avisos"])

    tab = Table(title="antes × depois (contagem de erros — não a nota)", header_style="dim")
    tab.add_column("rodada", overflow="fold"); tab.add_column("antes", justify="right")
    tab.add_column("depois", justify="right"); tab.add_column("")
    for cmd, e0, a0 in antes:
        e1, a1 = depois.get(cmd, (0, 0))
        if cmd not in depois:
            marca, estilo = "✓ zerou", "green"
        elif e1 < e0:
            marca, estilo = "✓ caiu", "green"
        elif e1 == e0:
            marca, estilo = "= igual", "yellow"
        else:
            marca, estilo = "✗ subiu", "red"
        tab.add_row(cmd, f"{e0}e/{a0}a", f"{e1}e/{a1}a", Text(marca, style=estilo))
    console.print(tab)
    console.print("[dim]  \"zerou\" = a rodada não gerou mais nenhum apontamento.[/dim]")
    if not md.exists():
        console.print("\n  [bold green]nenhum defeito restou — .logs/defeitos.md não existe "
                      "mais.[/bold green]")
        console.print(f"  [dim]o de antes ficou em {md.stem}.anterior{md.suffix}[/dim]")
    else:
        console.print(f"\n  ainda apontados: [bold]{md.relative_to(md.parents[1])}[/bold]")
    return pior


def limpar(email: str) -> int:
    if email.strip().lower() == CLI_USUARIO_EMAIL.strip().lower():
        console.print("[bold red]recusado:[/bold red] essa é a conta real.")
        return 2
    db.query("DELETE FROM usuario WHERE email = %(e)s", {"e": email})
    console.print(f"conta {email} apagada (o CASCADE da 009 levou o resto)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--aluno", choices=["roteiro", "llm"], default="roteiro",
                    help="roteiro fixo das regressões conhecidas (padrão) ou um LLM")
    ap.add_argument("--roteiro", nargs="+", metavar="FALA",
                    help="falas suas, em vez do roteiro padrão")
    ap.add_argument("--persona", choices=sorted(PERSONAS), default="iniciante")
    ap.add_argument("--cenario", metavar="NOME",
                    help="um dos cenários nomeados, ou 'listar' pra ver todos "
                         "(cada um tem linha própria no placar)")
    ap.add_argument("--mesa", metavar="NOME",
                    help="avalia com o contexto DESSA mesa (concurso-alvo, banca e "
                         "disciplinas do edital chegam ao prompt). Padrão: a mesa padrão.")
    ap.add_argument("--semente", type=int,
                    help="fixa o sorteio da abertura em --aluno llm, pra repetir a rodada")
    ap.add_argument("--turnos", type=int, default=0,
                    help="quantos turnos (padrão: o tamanho do roteiro, ou 6 com --aluno llm)")
    ap.add_argument("--juiz", action="store_true",
                    help="um LLM pontua a conversa na escala de naturalidade (0-100) e a "
                         "rodada entra no placar")
    ap.add_argument("--refazer", action="store_true",
                    help="roda de novo TODAS as rodadas que o defeitos.md registrou, "
                         "de uma vez, e mostra o antes × depois de cada uma")
    ap.add_argument("--reprocessar", action="store_true",
                    help="roda as checagens de hoje sobre TODAS as conversas já gravadas "
                         "em .logs/ e mostra o que mudou (não gasta LLM nem banco)")
    ap.add_argument("--placar", action="store_true",
                    help="mostra o histórico de notas e sai (sem gastar LLM)")
    ap.add_argument("--email", default=EMAIL_TESTE,
                    help=f"conta descartável em que a avaliação escreve (padrão {EMAIL_TESTE}); "
                         f"aponte para uma conta de semear_demo.py pra ter mesa e edital de "
                         f"verdade no contexto. A conta real é recusada.")
    ap.add_argument("--limpar", action="store_true", help="apaga a conta descartável e sai")
    a = ap.parse_args()

    if a.refazer:
        return refazer()
    if a.reprocessar:
        return reprocessar()
    if a.placar:
        return mostrar_placar()
    if a.cenario in ("listar", "lista", "?"):
        t = Table(title="cenários — cada um exercita um risco diferente", header_style="dim")
        t.add_column("nome"); t.add_column("turnos", justify="right")
        t.add_column("o que testa", overflow="fold")
        for nome, (desc, roteiro) in CENARIOS.items():
            t.add_row(nome, str(len(roteiro)), desc)
        console.print(t)
        console.print("\n  uso: ./testar.sh --cenario direto   ·   "
                      "todos de uma vez: ./testar.sh --cenario todos")
        return 0
    if a.limpar:
        return limpar(a.email)

    if a.cenario == "todos":
        # Roda a coleção inteira. Custa a soma dos turnos + um juiz por cenário,
        # e é a leitura mais completa que existe aqui: um `--cenario todos` antes
        # e outro depois de mexer no prompt cobre o espaço, não só as regressões.
        total_chamadas = sum(len(r) for _, r in CENARIOS.values()) + len(CENARIOS)
        console.print(f"[yellow]{len(CENARIOS)} cenários, ~{total_chamadas} chamadas de "
                      f"LLM.[/yellow]")
        alvo = Path(__file__).resolve().parents[2] / ".logs" / "defeitos.md"
        alvo.unlink(missing_ok=True)   # a bateria começa do zero e depois acumula
        pior = 0
        for nome in CENARIOS:
            console.print(Rule(f"[bold]cenário: {nome}", style="blue"))
            pior = max(pior, rodar(CENARIOS[nome][1], a.persona, len(CENARIOS[nome][1]),
                                   a.juiz, a.email, cenario=nome, semente=a.semente,
                                   nome_mesa=a.mesa, acumular=True))
        return pior

    if a.cenario:
        if a.cenario not in CENARIOS:
            console.print(f"[red]cenário '{a.cenario}' não existe.[/red] "
                          f"Veja: ./testar.sh --cenario listar")
            return 2
        falas = CENARIOS[a.cenario][1]
    elif a.roteiro:
        falas = a.roteiro
    elif a.aluno == "roteiro":
        falas = ROTEIRO_REGRESSOES
    else:
        falas = None

    n = a.turnos or (len(falas) if falas else 6)
    if falas:
        falas = falas[:n]
        n = len(falas)
    return rodar(falas, a.persona, n, a.juiz, a.email,
                 cenario=a.cenario if a.cenario in CENARIOS else None,
                 semente=a.semente, nome_mesa=a.mesa)


if __name__ == "__main__":
    sys.exit(main())
