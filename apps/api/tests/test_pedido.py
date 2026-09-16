"""
Pedido de treino reconhecido por REGRA, e o que ele dispara (`core/pedido.py`).

O que estes testes travam não é a regex — é a decisão de produto por trás dela:
quem pede questão recebe QUESTÃO DE VERDADE, com proveniência e fila, sem
clicar em nada.

Três desenhos foram tentados antes deste, e dois caíram:
  · "mande usar o botão" — parada de conversa; 16 casos disso nas conversas
    gravadas do `avaliar_chat.py`;
  · "o tutor escreve a questão no chat" — resolvia o atrito jogando fora
    `fonte_chunks`, a fila SM-2 e o progresso.
O terceiro é este: o servidor aciona o mesmo gerador que o botão acionava.
"""
import json
import re

import pytest

from core import db, pedido

VERSAO = "test-pedido-v1"


@pytest.mark.parametrize("fala, quantidade", [
    ("me dá uma questão disso", 1),
    ("queria 2 questões rapidas de direito constitucional", 2),
    ("me da 4 questoes", 4),
    ("quero cinco exercícios", 5),
    # Sem número: 2 e não 1, porque "me dá questões" está no plural e uma
    # questão só encerra o treino antes de ele começar.
    ("me testa nisso", 2),
    ("quero treinar", 2),
    # Teto: cada questão custa uma chamada de LLM, e o aluno espera por todas
    # antes de ver a primeira. `geracao.MAX_POR_VEZ` corta do outro lado; este
    # teto existe pra não prometer o que o gerador vai quebrar em silêncio.
    ("me da 50 questoes", 5),
])
def test_quantidade_pedida_e_respeitada(fala, quantidade):
    p = pedido.treino(fala)
    assert p is not None, f"não reconheceu pedido de treino em {fala!r}"
    assert p["quantidade"] == quantidade


def test_singular_com_til_nao_escapa():
    """`quest[õo]es?` deixava passar "questão": o singular leva "ã" e o plural
    "õ". Pegou em teste manual, não em revisão — a regex parecia certa."""
    for fala in ("me dá uma questão", "me da uma questao", "quero questões",
                 "quero questoes"):
        assert pedido.treino(fala) is not None, fala


def test_simulado_formal_e_reconhecido_mas_nao_e_caso_de_gerar_no_chat():
    """Simulado tem página, cronômetro e correção no fim — é `core/simulado.py`,
    não um punhado de questões no meio da conversa. A primeira versão exigia a
    palavra "questão" no portão e devolvia `None` pra "quero um simulado
    formal": o pedido mais explícito de todos passava como conversa comum."""
    for fala in ("quero um simulado formal", "quero uma prova cronometrada",
                 "quero ver meu caderno de erros"):
        p = pedido.treino(fala)
        assert p is not None, fala
        assert p["formal"] is True, fala


def test_conversa_comum_nao_dispara_treino():
    """O custo de errar pra mais é alto: gerar questão gasta cota de LLM e
    ESCREVE no acervo compartilhado. Falar de matéria não é pedir treino."""
    for fala in ("boa noite", "me explica peculato", "acho que sim",
                 "quero aprender ciências forenses do zero", "e o art. 312?"):
        assert pedido.treino(fala) is None, fala


def test_formato_explicito_vence_a_banca():
    """Item CERTO/ERRADO é o estilo Cebraspe (012) e o aluno pede pelo nome.
    Sem pedido, quem decide é `geracao.tipo_da_banca` — a regra que já existe."""
    assert pedido.treino("me dá 3 itens certo ou errado")["tipo"] == "certo_errado"
    assert pedido.treino("me dá 3 questões")["tipo"] is None


def test_pedir_treino_no_chat_gera_questao_com_proveniencia_e_sem_botao(
        client, usuario, llm_falso):
    """Fim a fim: o aluno pede treino numa frase e recebe questão DE VERDADE.

    É a asserção que protege a decisão do dono — "não vamos sacrificar a
    proveniência, a fila do SM-2 e o histórico de longo prazo". Se alguém
    amanhã trocar isto por questão escrita no texto do tutor, este teste cai:
    `fonte_chunks` fica nulo e a questão não existe na tabela.

    O TEMA sai do histórico ANTERIOR ao pedido, e isso também está travado
    aqui. Usar o histórico já atualizado fazia `em_foco` ler "me da 3 questoes
    disso", achar "disso" como palavra de conteúdo e gerar sobre apropriação
    indébita e inquérito policial numa conversa sobre peculato — a mesma classe
    do "vamos" que fez nascer o `core/assunto.py`.

    LLM FALSO, e a lição é minha: escrevi este teste contra o Gemini de verdade
    e ele passava sozinho e falhava na suíte. A causa não era o código — era o
    provedor devolvendo 503 (medido: chamada trivial de 10 tokens levando 33-42s
    ou falhando). Teste ponta a ponta que depende de plano gratuito estar de pé
    flakeia pra sempre, e o que ele afirma — proveniência, gravação, fila, e o
    tutor não mandando clicar — não precisa de modelo real nenhum.
    """
    # O duplê devolve uma questão por artigo que ESTIVER no material, que é o
    # único comportamento do modelo real do qual a gravação depende. Mesmo
    # padrão de `test_geracao._modelo_que_responde_sobre_o_lote`.
    def gerar(prompt, sistema="", json_mode=False, max_tokens=1200, schema=None,
              temperatura=None):
        if not json_mode and not schema:
            return "Vamos treinar isso; as questões estão logo abaixo."
        arts = list(dict.fromkeys(
            a.strip() for a in re.findall(r"\[[^\]]*?art\. ([^\]—]+)", prompt)))
        return json.dumps([
            {"artigo": a, "tema": f"Tema {a}", "enunciado": "Enunciado?",
             "gabarito": "Gabarito.", "dicas": ["d1", "d2", "d3"]} for a in arts])
    llm_falso.gerar = gerar
    r1 = client.post("/perguntar", headers=usuario["headers"],
                     json={"pergunta": "quero estudar peculato"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["questoes"] == [], "explicar não deve gerar questão"
    cid = r1.json()["conversa_id"]

    r2 = client.post("/perguntar", headers=usuario["headers"],
                     json={"pergunta": "me da 2 questoes disso", "conversa_id": cid})
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert len(d["questoes"]) >= 1, "pedido de treino não gerou questão"

    for q in d["questoes"]:
        linha = db.exec1("SELECT fonte_chunks, documento_id FROM questao WHERE id = %(i)s",
                         {"i": q["id"]})
        assert linha, "a questão não foi GRAVADA — sem gravação não há fila SM-2"
        assert linha["fonte_chunks"], "questão sem proveniência"
        assert linha["documento_id"], "questão sem documento de origem"
        # Elegível como NOVA na fila: nunca tentada por este aluno.
        assert db.exec1("SELECT count(*) AS n FROM progresso WHERE questao_id = %(q)s",
                        {"q": q["id"]})["n"] == 0

    baixo = d["resposta"].lower()
    assert "botão" not in baixo and "botao" not in baixo, \
        "o tutor mandou clicar em vez de o app gerar"


# --------------------------------------------- continuação elíptica (v2)
def _hist(*falas_do_aluno):
    """Histórico alternando aluno/tutor, como `historico_para_prompt` devolve."""
    out = []
    for f in falas_do_aluno:
        out += [{"autor": "aluno", "texto": f}, {"autor": "tutor", "texto": "..."}]
    return out


@pytest.mark.parametrize("fala, quantidade", [
    ("agora só uma", 1),
    ("manda cinco", 5),
    ("mais 3", 3),
    ("outra", 1),          # "outra" é UMA a mais, não o padrão de duas
])
def test_continuacao_conta_como_pedido_depois_de_treino(fala, quantidade):
    """Depois de um lote, o aluno ajusta a quantidade sem repetir "questão".

    Medido no cenário `quantas`: depois de "me da 4 questoes", as falas "agora
    só uma" e "manda cinco" não geravam NADA — nenhuma contém as palavras da
    `RE_TREINO`. O aluno acha que pediu; o app acha que ele mudou de assunto.
    Nenhuma lista de sinônimos resolve isso, porque a forma é elíptica: só quer
    dizer "mais questões" DEPOIS de um turno de treino."""
    p = pedido.treino(fala, apos_treino=True)
    assert p is not None, fala
    assert p["quantidade"] == quantidade


@pytest.mark.parametrize("fala", ["agora só uma", "manda cinco", "mais 3", "outra",
                                  "5 anos de pena", "e o art. 312?"])
def test_continuacao_nao_vale_fora_do_contexto(fala):
    """`apos_treino` é obrigatório, e é o que impede o pior erro: gerar questão
    porque alguém escreveu um número. "5 anos de pena" e "e o art. 312?" são
    conversa de matéria — gerar ali gastaria cota e escreveria no acervo por
    causa de um dígito."""
    assert pedido.treino(fala) is None, fala


def test_corrente_de_continuacoes_nao_arrebenta():
    """"me da 4" → "agora só uma" → "manda cinco": os três são treino.

    A primeira versão de `veio_de_treino` olhava só a última fala do aluno e
    exigia dela um pedido COMPLETO — então o terceiro turno não gerava nada,
    porque o segundo era elíptico. A corrente arrebentava no segundo elo."""
    assert pedido.veio_de_treino(_hist("quero peculato", "me da 4 questoes")) is True
    assert pedido.veio_de_treino(
        _hist("quero peculato", "me da 4 questoes", "agora só uma")) is True
    assert pedido.veio_de_treino(
        _hist("me da 4 questoes", "agora só uma", "mais 2")) is True


def test_explicacao_no_meio_encerra_a_corrente():
    """Voltar a explicar quebra a sequência, e é o certo: depois disso "manda
    cinco" não é mais pedido de questão, é continuação da explicação."""
    assert pedido.veio_de_treino(_hist("me da 4 questoes", "me explica melhor")) is False
    assert pedido.veio_de_treino(_hist("quero estudar peculato")) is False


def test_continuacao_nao_vira_assunto_de_busca():
    """A fala de continuação não pode decidir de qual artigo se cobra.

    Mesma razão do "vamos": "manda cinco" não nomeia assunto, e deixá-la entrar
    como candidata faria a busca cobrar de artigo sorteado. O assunto é o da
    CONVERSA — aqui, peculato."""
    from core import assunto
    h = _hist("quero estudar peculato", "me da 4 questoes")
    assert assunto.em_foco(h, disciplinas=["Direito Penal"]) == "quero estudar peculato"
    assert assunto.em_foco(h, "manda cinco", ["Direito Penal"]) == "quero estudar peculato"


@pytest.mark.parametrize("fala, quantidade", [
    # Relatado: "traga 1 questão sobre principios explicitos e uma sobre
    # explicito" veio com UMA. A segunda quantidade é elíptica — "uma
    # [questão] sobre Y" —, então procurar outra ocorrência ANCORADA não
    # bastava.
    ("traga 1 questão sobre principios explicitos e uma sobre explicito", 2),
    ("traga 2 questões de penal e 3 de processo", 5),
    # Ancorar no primeiro é o que torna a soma segura: número ANTES dele pode
    # ser dispositivo ou pena.
    ("e o art. 312? me da uma questao", 1),
    ("me da uma questao do art. 312", 1),
    ("quero 2 questões sobre o art. 37", 2),
])
def test_quantidade_pedida_em_partes_e_somada(fala, quantidade):
    """Pedir "uma de cada" é a forma natural de cobrir dois pontos.

    Entregar metade é o erro que a pessoa não reporta: ela só acha que o app é
    ruim. E somar número solto sem âncora pegaria "art. 312" e "3 anos de
    pena" — daí a soma começar depois do primeiro ancorado e pular o que vem
    logo após "art.", "§", "inciso" ou "caixa"."""
    assert pedido.quantas(fala) == quantidade


# ─────────────────────────────── "testar" e a palavra "prova"

@pytest.mark.parametrize("fala", [
    "podemos testar eu nao sei se ja estou bom",
    "quero testar",
    "vamos testar isso",
    "bora testar",
    "podemos me testar",
])
def test_podemos_testar_e_pedido_de_treino(fala):
    """MEDIDO numa bateria real: o aluno disse "podemos testar eu nao sei se ja
    estou bom", `treino()` devolveu None (nenhuma questão gerada) — e o tutor
    respondeu "as questões estão logo abaixo". Promessa que a tela não cumpre,
    que é pior do que não oferecer.

    O verbo vem ancorado num marcador de intenção de propósito: "testar" solto
    aparece em pergunta de CONTEÚDO, e isso está travado logo abaixo."""
    p = pedido.treino(fala)
    assert p and not p["formal"], p


@pytest.mark.parametrize("fala", [
    "como testar a validade de uma prova pericial?",
    "o perito vai testar a amostra",
])
def test_testar_dentro_de_pergunta_de_conteudo_nao_e_pedido(fala):
    """Trocar a dúvida do aluno por um exercício que ninguém pediu."""
    assert pedido.treino(fala) is None


@pytest.mark.parametrize("fala", [
    "me explica prova testemunhal",
    "o que é prova emprestada no processo penal",
    "quais são os meios de prova admitidos",
    "prova ilícita por derivação",
    "quem tem o ônus da prova no processo penal?",
    "me explica cadeia de custódia da prova",
    "como testar a validade de uma prova pericial?",
])
def test_a_palavra_prova_sozinha_nao_e_pedido_de_simulado(fala):
    """`RE_FORMAL` era `prova\\s`, e no Processo Penal / Ciências Forenses
    "prova" é o substantivo mais comum da matéria. MEDIDO: seis de oito frases
    reais dessas disciplinas viravam pedido de simulado formal.

    E `formal=True` não é rótulo inofensivo — `api.py` não gera questão nesse
    caminho e ainda acende `simulado_pedido` na tela. O aluno pedia explicação
    sobre prova pericial (disciplina inteira do edital dele, com apostila
    subida) e recebia um empurrão pra tela de Simulado."""
    p = pedido.treino(fala)
    assert not (p and p["formal"]), p


@pytest.mark.parametrize("fala", [
    "quero um simulado formal cronometrado",
    "bora fazer uma prova cronometrada",
    "vamos fazer uma prova",
    "quero prova",
    "abre meu caderno de erros",
])
def test_pedido_de_simulado_de_verdade_continua_reconhecido(fala):
    """O outro lado da mesma régua: apertar `RE_FORMAL` não pode cegar o
    pedido explícito, que é o caso que a fez nascer ("quero um simulado formal"
    devolvia None quando a regex só procurava a palavra "questão")."""
    p = pedido.treino(fala)
    assert p and p["formal"], p


# ---------------------------------------------------------------------------
# Pergunta sobre o PRÓPRIO progresso (não busca material)
# ---------------------------------------------------------------------------

PROGRESSO = [
    "o que eu ja estudei de direito administrativo e o que ta faltando pra mim zerar o edital?",
    "quais conteudos eu ja vi das outras materias?",
    "ta mais eu quero saber o que eu ja estudei e o que falta",
    "como estou indo?",
    "me mostra meu desempenho",
    "quanto eu ja cobri do edital?",
    "o que me falta ver ainda",
]

CONTEUDO = [
    # "já vi" solto é RESPOSTA ao tutor, não pergunta de progresso — e calar a
    # busca aqui desligaria o material no meio de uma aula.
    "ja vi sim, se você puder citar só os principais que mais caem em prova",
    "quero estudar atos administrativos",
    # "o que falta" com escopo de MATÉRIA: perguntas reais de tipicidade.
    "o que falta para configurar o crime de peculato?",
    "o que falta para caracterizar a improbidade?",
    "me explica a falta grave na lei 8.112",
    "o que é papiloscopia?",
    "qual a diferença entre anulação e revogação?",
]


def test_pergunta_sobre_o_proprio_progresso_e_reconhecida():
    """Relatado com print: a lista de CONSULTADO trazia "Princípios do Direito
    Administrativo" embaixo de uma contagem de tentativas do aluno.

    A resposta dessa pergunta mora nos números que já vão no prompt; a busca não
    tem o que fazer nela, e `hibrida()` não devolve vazio — devolve seis trechos
    com cara de fonte."""
    for fala in PROGRESSO:
        assert pedido.sobre_desempenho(fala), fala


def test_pergunta_de_materia_continua_buscando():
    """O falso POSITIVO é o caro: calar a busca numa pergunta de conteúdo
    entrega resposta sem material. Por isso a regra exige interrogativa
    explícita ou possessivo de primeira pessoa, nunca só o verbo."""
    for fala in CONTEUDO:
        assert not pedido.sobre_desempenho(fala), fala
