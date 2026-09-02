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


def test_pedir_treino_no_chat_gera_questao_com_proveniencia_e_sem_botao(client, usuario):
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
    """
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
