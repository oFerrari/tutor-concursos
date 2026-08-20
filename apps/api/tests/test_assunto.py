"""
O assunto em foco — o texto que vai à BUSCA, não à tela.

Estes testes são PUROS (nem banco, nem LLM, nem embedding) porque o módulo é,
no mesmo molde de `test_scheduler_regras.py` e `test_ritmo_regras.py`. E foram
escritos a partir de uma conversa REAL, com as falas literais que produziram o
defeito — inclusive os erros de digitação. Fixture limpo demais mente tanto
quanto métrica errada, e "vamos" foi exatamente a fala que quebrou tudo.
"""
from core import assunto

VERSAO = "test-assunto-v1"

# A conversa que expôs o bug: começou em Direito Penal, migrou pra
# Constitucional (eficácia das normas), passou por dois turnos de meta-conversa
# e terminou num "vamos" que virou consulta de busca vetorial.
CONVERSA_REAL = [
    "ola",
    "queria estudar direito constituional, aplicabilidade das normas",
    "na verdade você deveria perguntar se eu ja seu algo do assunto não? antes de"
    " me oferecer questões? talvez seja melhor você me explicar um pouco do que se trata",
    "lembrava, mais eu sei que eficacia limitada existem 2 tipo não é verdade?",
    "queria saber como a fgv cobra",
]


def _turnos(falas, autor="aluno"):
    return [{"autor": autor, "texto": f} for f in falas]


# ------------------------------------------------------------ o bug, travado

def test_vamos_nunca_vira_consulta():
    """O defeito exato, com a fala exata.

    `buscar("vamos")` devolvia CP art. 352 (evasão) e CF art. 200 (SUS) — e
    devolvia com confiança total, porque `hibrida()` é k-vizinhos e não tem piso
    de relevância. Se algum dia esta asserção falhar, o produto voltou a gerar
    questão de assunto sorteado no meio de uma conversa."""
    foco = assunto.em_foco(_turnos(CONVERSA_REAL), "vamos")
    assert foco is not None
    assert "vamos" not in foco.lower()
    # E o que ele PRECISA conter é o assunto que a conversa construiu. Note que
    # "aplicabilidade" (dois turnos mais atrás) NÃO é exigido: "eficácia
    # limitada" é o termo mais específico dos dois, e `CONTEUDO_SUFICIENTE` para
    # de enriquecer ao alcançá-lo. Consulta boa não é consulta longa.
    assert "eficacia limitada" in foco.lower()


def test_meta_conversa_nao_e_assunto():
    """"você deveria perguntar se eu já sei algo do assunto... melhor me
    explicar" trouxe CPP 188/190/203/212 — interrogatório e inquirição. A busca
    acertou as palavras e errou a matéria."""
    meta = CONVERSA_REAL[2]
    assert not assunto.diz_assunto(meta)
    # Sozinha ela não dá consulta nenhuma: é melhor cair no recorte da mesa que
    # buscar por "perguntar/responder/explicar".
    assert assunto.em_foco([], meta) is None


def test_continuacoes_curtas_nao_dizem_assunto():
    for fala in ("vamos", "sim", "ok", "beleza", "esse mesmo", "pode ser",
                 "não entendi", "pode explicar melhor?", "certo", "e agora?"):
        assert not assunto.diz_assunto(fala), fala


# ------------------------------------ o oposto: não descartar pergunta real

def test_pergunta_curta_e_legitima_sobrevive():
    """A razão de `MIN_CONTEUDO` ser 1. "matar alguém" tem UMA palavra de
    conteúdo (alguém é vazia) e é a pergunta mais literal que existe sobre o
    art. 121 — exigir duas a descartaria da consulta inteira."""
    foco = assunto.em_foco(_turnos(["me fale de peculato"]), "matar alguém")
    assert foco is not None and foco.lower().startswith("matar alguém")


def test_nomes_de_disciplina_nao_sao_palavras_vazias():
    """"direito", "penal", "norma", "prazo", "pena" e "tipo" (tipo penal) parecem
    genéricas e são o nome da matéria. Tirá-las da lista cegaria a busca."""
    for palavra in ("direito", "penal", "norma", "prazo", "pena", "tipo",
                    "administrativo", "constitucional"):
        assert assunto.palavras_de_conteudo(palavra) == [palavra], palavra


def test_ignora_acento_ausente():
    """Ninguém digita acento com pressa: "voce" e "você" são a mesma vazia."""
    assert assunto.palavras_de_conteudo("voce nao podia") == []
    assert assunto.palavras_de_conteudo("você não podia") == []


# --------------------------------------------------------------- quem entra

def test_fala_do_tutor_nao_atropela_a_do_aluno():
    """A prosa do tutor tem centenas de palavras e, quando o aluno JÁ disse do que
    quer falar, dominaria a consulta com o vocabulário da RESPOSTA anterior —
    prendendo a busca no que já foi dito em vez do que está sendo perguntado."""
    turnos = (_turnos(["me explica eficácia limitada"])
              + _turnos(["peculato é a apropriação de dinheiro público"], autor="tutor"))
    foco = assunto.em_foco(turnos, "vamos")
    assert "eficácia limitada" in foco.lower()
    assert "peculato" not in foco.lower()


def test_tutor_e_o_FALLBACK_quando_o_aluno_nunca_nomeou_assunto():
    """Este teste dizia o oposto — que fala de tutor NUNCA entra — e um caso real
    provou o contrário:

        aluno:  "boa noite"
        tutor:  "...você já domina a diferença entre os direitos sociais de
                 eficácia plena e as normas de eficácia limitada?"
        aluno:  "podemos testar eu nao sei se ja estou bom"

    Nenhuma fala do ALUNO nomeia matéria. A consulta virou "podemos testar eu nao
    sei se ja estou bom boa noite", a busca devolveu lixo, e as questões geradas
    foram CF art. 200 (SUS) e CP art. 94 (reabilitação) — no meio de uma conversa
    sobre eficácia das normas. O mesmo estrago do "vamos", por outra fresta.

    A lição NÃO é "faltou palavra na lista VAZIAS": nenhuma lista cobre toda forma
    de dizer "vamos lá". Quando o aluno não nomeia o assunto, quem nomeou foi o
    TUTOR — e a proposta dele É o assunto da conversa. Excluí-lo sempre
    transformava "o aluno aceitou o convite" em "ninguém falou de nada"."""
    tutor = ("Boa noite! Quando você pensa nas questões de Direito Constitucional, "
             "você já domina a diferença entre os direitos sociais de eficácia plena "
             "e as normas de eficácia limitada?")
    turnos = _turnos(["boa noite"]) + _turnos([tutor], autor="tutor")
    foco = assunto.em_foco(turnos, "podemos testar eu nao sei se ja estou bom")
    assert foco is not None
    assert "eficácia limitada" in foco.lower()
    # E a saudação/meta não entra: era ela que estava virando a consulta.
    assert "boa noite" not in foco.lower().replace(tutor.lower(), "")


def test_saudacao_e_convite_nao_dizem_assunto():
    """As falas exatas do caso acima, e as vizinhas que iam pelo mesmo caminho.

    Este teste é CONFORTO, não garantia, e a distinção importa: a lista `VAZIAS`
    já cresceu duas vezes atrás de caso real e vai crescer de novo, porque não
    existe enumeração de todas as formas de dizer "vamos lá". Quem garante o
    resultado é `test_tutor_e_o_FALLBACK_...` acima — ele passa mesmo quando esta
    lista falha."""
    for fala in ("boa noite", "bom dia", "boa tarde", "oi", "opa",
                 "podemos testar eu nao sei se ja estou bom",
                 "vamos treinar", "quero praticar", "bora revisar"):
        assert not assunto.diz_assunto(fala), fala


def test_evento_da_sessao_nao_decide_de_onde_cobrar():
    """Evento (016) é fato — "respondeu e errou" —, não pedido. Vai pro prompt,
    não pra busca."""
    turnos = _turnos(["Você propôs 2 questões sobre concussão"], autor="evento")
    assert assunto.em_foco(turnos, "vamos") is None


def test_recencia_lidera_e_assunto_abandonado_nao_volta():
    """A conversa começou em Direito Penal. Depois de migrar pra Constitucional,
    a janela de turnos ainda contém Penal — e ele NÃO pode voltar pra consulta,
    senão a questão sai da matéria que o aluno deixou pra trás."""
    falas = ["me explica peculato e concussão",
             "agora quero controle de constitucionalidade",
             "e a eficácia das normas constitucionais"]
    foco = assunto.em_foco(_turnos(falas), "vamos").lower()
    assert foco.startswith("e a eficácia")
    assert "peculato" not in foco


def test_teto_de_caracteres_corta_no_turno_inteiro():
    """Embedding é média do que entra: parede de texto dilui o assunto. E o corte
    é por turno — meia pergunta muda de sentido."""
    longa = "processo administrativo disciplinar " * 20
    foco = assunto.em_foco(_turnos([longa, longa]), longa)
    assert len(foco) <= assunto.MAX_CHARS
    assert not foco.endswith("adm")


# --------------------------------------------------- citação de dispositivo

def test_citacao_de_dispositivo_e_reconhecida():
    """`socratic.explicar` usa isto pra mandar a pergunta CRUA à busca. Sem esse
    desvio, um "art. 140" de três turnos atrás sequestraria a pergunta nova
    dentro de `por_dispositivo`, e a resposta viria confiante sobre o artigo
    errado."""
    for fala in ("art. 312", "artigo 5º", "o que diz o Art 121 do CP?", "arts. 33 e 34"):
        assert assunto.cita_dispositivo(fala), fala
    for fala in ("me explica peculato", "vamos", "eficácia limitada"):
        assert not assunto.cita_dispositivo(fala), fala


def test_citacao_sozinha_conta_como_assunto():
    """"art. 312" tem uma palavra vazia e um número — o contador de conteúdo
    diria que não é assunto, e é a consulta mais precisa que o sistema aceita."""
    assert assunto.diz_assunto("art. 312")
    assert assunto.em_foco([], "art. 312") == "art. 312"


def test_regra_de_citacao_e_a_mesma_do_retrieval():
    """Duas versões de "isto é uma citação?" divergem, e o sintoma seria a busca
    por dispositivo funcionando num caminho e não no outro."""
    from core import retrieval
    assert assunto.RE_CITACAO is retrieval.RE_CITACAO


# --------------------------------------------------------------- degenerados

def test_sem_nada_devolve_none():
    """`None` é o sinal de "ninguém nomeou assunto" — quem chama cai no recorte
    da mesa. Nunca uma string vazia, que iria à busca como consulta válida."""
    assert assunto.em_foco() is None
    assert assunto.em_foco([], None) is None
    assert assunto.em_foco([], "   ") is None
    assert assunto.em_foco(_turnos(["", "   "]), "ok") is None
