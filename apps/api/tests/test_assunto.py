"""
O assunto em foco — o texto que vai à BUSCA, não à tela.

Estes testes são PUROS (nem banco, nem LLM, nem embedding) porque o módulo é,
no mesmo molde de `test_scheduler_regras.py` e `test_ritmo_regras.py`. E foram
escritos a partir de uma conversa REAL, com as falas literais que produziram o
defeito — inclusive os erros de digitação. Fixture limpo demais mente tanto
quanto métrica errada, e "vamos" foi exatamente a fala que quebrou tudo.
"""
from core import assunto

VERSAO = "test-assunto-v2"

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


# ------------------------------------------------- a prova de fogo (log real)

# As falas LITERAIS da conversa 465, a pior que o produto já produziu: dez
# minutos inteiros sobre Lei Maria da Penha terminando em duas questões de
# Direito Administrativo — L8112 art. 55 (ajuda de custo) e art. 94 (mandato
# eletivo). Os turnos do tutor estão inteiros de propósito: é a citação de fonte
# no fim deles ("[Lei Maria da Penha, art. 5º]") que trava o segundo defeito.
MARIA_DA_PENHA = [
    ("aluno", "boa noite"),
    ("tutor", "Boa noite! Por onde você quer começar hoje? Temos Direito"
              " Administrativo, Direito Constitucional, Direito Penal e Legislação"
              " Penal Extravagante, entre outras matérias do seu edital."),
    ("aluno", "queria estudar lei maria da penha"),
    ("tutor", "A Lei Maria da Penha cai forte na sua prova dentro de Direito Penal"
              " e Legislação Penal Extravagante pela FGV, cobrando muito a definição"
              " de violência doméstica e os mecanismos de proteção à mulher. Antes de"
              " entrarmos nos detalhes que a banca mais exige, você já sabe me dizer"
              " qual é a natureza da ação penal nos crimes de lesão corporal leve"
              " praticados no âmbito dessa lei?"),
    ("aluno", "não sei não quais são?"),
    ("tutor", "Na Lei Maria da Penha, a regra geral trazida pelo STF é que a ação"
              " penal nos crimes de lesão corporal leve praticados contra a mulher em"
              " âmbito doméstico é pública incondicionada. Se uma mulher sofreu lesão"
              " corporal leve praticada pelo companheiro e no dia seguinte diz que"
              " quer retirar a queixa, o Ministério Público pode arquivar o caso?"),
    ("aluno", "não"),
    ("tutor", "Exato! Como a ação penal é pública incondicionada, a vontade da vítima"
              " de retirar a queixa não tem valor para parar o processo. Qual é a"
              " única hipótese em que a ação penal nesses casos de lesão corporal"
              " seria pública condicionada à representação, segundo o STF?"),
    ("aluno", "quando nao for crime realizado em ambito doméstico?"),
    ("tutor", "Não exatamente. Fora do âmbito doméstico ou familiar, a lesão corporal"
              " leve já segue a regra geral do Código Penal, mas o ponto central da"
              " Lei Maria da Penha é justamente o âmbito doméstico. A restrição vale"
              " para qualquer crime de lesão corporal leve praticado no âmbito"
              " doméstico ou familiar contra a mulher, certo?"),
    ("aluno", "sim"),
    ("tutor", "Ótimo! Você sabe me dizer se a proteção da Lei Maria da Penha se"
              " estende a relações de namoro em que o casal não mora na mesma casa?"),
    ("aluno", "sim desde que haja vinculo ou afeto"),
    ("tutor", "Exato! O STJ tem entendimento pacificado de que o vínculo de afeto,"
              " mesmo sem coabitação, é suficiente para configurar o âmbito doméstico"
              " e familiar [Lei Maria da Penha, art. 5º]. Você sabe se o fato de o"
              " casal já ter terminado o relacionamento impede a aplicação da lei"
              " caso ocorra uma agressão motivada pelo término?"),
    ("aluno", "não impede"),
    ("tutor", "Exato! O STJ entende que a relação íntima de afeto anterior — mesmo"
              " após o término — atrai a incidência da lei, desde que a agressão"
              " decorra dessa relação [Lei Maria da Penha, art. 5º]. Você lembra qual"
              " é o critério principal trazido pelo art. 5º da Lei Maria da Penha"
              " para definir se a agressão configura violência doméstica ou familiar,"
              " além da coabitação e do vínculo de afeto?"),
    ("aluno", "dependencia?"),
    ("tutor", "Exato, a unidade doméstica ou a dependência econômica entre o agressor"
              " e a vítima também configuram o âmbito da violência doméstica, mesmo"
              " sem coabitação ou vínculo de afeto amoroso, como ocorre entre parentes"
              " que moram juntos ou empregada e patrão que residam no mesmo local"
              " [Lei Maria da Penha, art. 5º, II e III]. Você já viu como a lei trata"
              " a exigência de convivência sob o mesmo teto?"),
]

LOG = [{"autor": a, "texto": t} for a, t in MARIA_DA_PENHA]


def test_conversa_inteira_sobre_um_assunto_nao_sai_dele():
    """O defeito, pelo caminho do BOTÃO ("quero questões sobre isto").

    Sem fala nova do aluno, `em_foco` costurava as três últimas respostas dele e
    a consulta virava

        'dependencia? não impede sim desde que haja vinculo ou afeto'

    quatro palavras de conteúdo, nenhuma delas assunto, e todas as quatro caindo
    em pensão e ajuda de custo do estatuto do servidor. A busca devolveu L8112
    55/94/222/198 e as questões saíram de Direito Administrativo. Medido depois
    da correção, a mesma conversa devolve crimes contra a família, crimes contra
    a liberdade individual e CF art. 226 — o acervo não tem a Maria da Penha
    (`docs/LIMITACOES.md`), e isto é o mais perto que ele chega."""
    foco = assunto.em_foco(LOG, None)
    assert foco is not None
    assert "doméstica" in foco.lower()
    # E os fragmentos de diálogo que viraram a consulta ficam FORA dela.
    for fragmento in ("não impede", "vinculo ou afeto", "dependencia?"):
        assert fragmento not in foco.lower()


def test_citacao_do_tutor_nao_sequestra_a_busca():
    """Segundo defeito, que só apareceu depois de o primeiro ser consertado.

    O tutor fecha a resposta com a FONTE — "[Lei Maria da Penha, art. 5º, II e
    III]" — e uma citação dentro da consulta faz `retrieval.buscar` trocar busca
    semântica por dispositivo EXATO. O resultado medido foi o art. 5º de tudo o
    que existe no acervo: ADCT, CF, territorialidade do CP, inquérito do CPP e
    requisitos de investidura da 8.112. Cinco artigos sem nada em comum além do
    número — e com cara de acerto, porque o número bate."""
    foco = assunto.em_foco(LOG, None)
    assert not assunto.cita_dispositivo(foco)
    assert "[" not in foco


def test_resposta_ao_tutor_herda_o_assunto_do_tutor():
    """As falas em que contar palavras (e novidade lexical) falhava.

    "dependencia?" e "sim desde que haja vinculo ou afeto" são RESPOSTAS que
    acrescentam palavra nova — responder a uma pergunta de conhecimento é
    exatamente isso. Nenhuma das duas pode virar consulta sozinha: "dependência"
    e "vínculo" moram em ajuda de custo e pensão no acervo que existe."""
    for i, m in enumerate(MARIA_DA_PENHA):
        if m[0] != "aluno":
            continue
        anteriores, fala = LOG[:i], m[1]
        if not assunto.e_eco(fala, anteriores):
            continue
        foco = (assunto.em_foco(anteriores, fala) or "").lower()
        # A consulta é a fala do TUTOR — e não precisa conter "Maria da Penha"
        # pra estar no assunto: "ação penal, lesão corporal, representação" é
        # consulta boa. Exigir as palavras seria proxy ruim, e reprovava um
        # acerto. O que precisa valer é a ORIGEM da consulta.
        do_tutor = [x[1].lower()[:40] for x in MARIA_DA_PENHA if x[0] == "tutor"]
        assert any(foco.startswith(inicio) for inicio in do_tutor), fala
        assert not foco.startswith(fala.lower()), fala


def test_aluno_retoma_a_iniciativa_e_troca_de_assunto():
    """A escapatória, e por que ela não pode faltar: o prompt manda o tutor
    terminar TODA resposta com pergunta, então quase toda fala do aluno vem
    depois de uma. Sem `pede_assunto`, "agora quero controle de
    constitucionalidade" seria lida como resposta e o aluno ficaria preso na
    Maria da Penha — o defeito oposto, e igualmente ruim."""
    troca = "agora quero controle de constitucionalidade"
    assert not assunto.e_eco(troca, LOG)
    foco = assunto.em_foco(LOG, troca).lower()
    assert foco.startswith("agora quero controle")
    assert "penha" not in foco and "doméstic" not in foco


# ---------------------------------------------------------------------------
# Terceira leva de meta-conversa: "resumão", "detalhado", "trouxesse"
# ---------------------------------------------------------------------------

# Conversa 525, literal, do começo do assunto até o pedido que envenenou a
# busca. Cortada onde importa — o que decide é o PAR (fala do aluno, turno
# anterior do tutor), e é isso que precisa estar aqui.
PRINCIPIOS = [
    ('aluno', 'boa noite'),
    ('tutor',
     'Boa noite! Vamos começar nossa preparação para a PC-PR com a FGV. Por onde você quer '
     'ir hoje? Podemos focar em Direito Constitucional, Direito Penal, Direito '
     'Administrativo ou alguma das outras matérias do seu edital.'),
    ('aluno', 'direito administrativo'),
    ('tutor',
     'Vamos começar por Direito Administrativo, focando no primeiro tópico do seu edital '
     'para a PC-PR: conceito, fontes e princípios, além da LINDB. Para direcionar bem o '
     'estudo, você já tem facilidade com a diferença entre os princípios expressos e os '
     'implícitos da Administração Pública na cobrança da FGV?'),
    ('aluno', 'eu acho que sim, mais ou menos'),
    ('tutor',
     'Isso é doutrina e não está no seu material; confira na sua apostila: os princípios '
     'expressos estão previstos de forma explícita na Constituição, enquanto os implícitos '
     'são reconhecidos pela doutrina e jurisprudência para dar sustentação à atuação '
     'estatal, como a supremacia do interesse público e a autotutela. Você já pegou alguma '
     'questão da FGV cobrando a autotutela da Administração Pública?'),
    ('aluno',
     'mais você como uma IA não consegue trazer pra mim alguns conceitos e explicações '
     'sobre os principios expressos e implicitos?'),
    ('tutor',
     'Sim, trago direto. O art. 37, *caput*, da Constituição traz os princípios expressos '
     'da administração pública direta e indireta: legalidade, impessoalidade, moralidade, '
     'publicidade e eficiência. Já os implícitos, como a supremacia do interesse público '
     'sobre o privado e a autotutela, são construções doutrinárias que decorrem do sistema '
     'constitucional e dão base ao poder estatal. Quer que eu siga para o próximo ponto do '
     'edital, que trata da LINDB aplicada ao Direito Administrativo?'),
    ('aluno',
     'calma você mal falou de principios expressos e explicitos e ja quer mudar de '
     'assunto?'),
    ('tutor',
     'Tem razão, vamos aprofundar os princípios expressos para não deixar nenhuma brecha '
     'para a FGV. Os princípios expressos são aqueles listados expressamente no texto '
     'constitucional: legalidade, impessoalidade, moralidade, publicidade e eficiência. A '
     'legalidade significa que a administração só pode atuar quando autorizada por lei; a '
     'impessoalidade exige que a atuação seja voltada ao interesse público, sem '
     'favorecimentos ou perseguições pessoais; a moralidade impõe atuação ética e proba; a '
     'publicidade exige transparência dos atos administrativos; e a eficiência cobra '
     'qualidade, rapidez e rendimento na prestação dos serviços públicos. Você lembra qual '
     'desses cinco princípios é o único que foi inserido na Constituição por uma emenda '
     'posterior e não constava no texto original de 1988?'),
    ('aluno', 'sei é a eficiencia'),
    ('tutor',
     'Exato, a eficiência foi incluída pela Emenda Constitucional nº 19/1998, trazendo '
     'para a Administração Pública a exigência de resultados, qualidade e rapidez. Podemos '
     'seguir para os princípios implícitos, como a autotutela e a supremacia do interesse '
     'público, ou você prefere ver como a FGV costuma cobrar o princípio da impessoalidade '
     'em provas de carreiras policiais?'),
    ('aluno', 'podemos sim'),
    ('tutor',
     'Vamos seguir para os princípios implícitos, começando pela autotutela. Este é um '
     'conceito da doutrina, que não está expresso em um artigo único, mas que fundamenta o '
     'poder que a Administração Pública tem de anular seus próprios atos quando forem '
     'ilegais, ou revogá-los por motivo de conveniência e oportunidade, sem precisar ir ao '
     'Judiciário para isso. Você já viu a Súmula 473 do Supremo Tribunal Federal, que '
     'trata justamente desse poder de anulação e revogação?'),
    ('aluno',
     'ja vi sim, se você puder citar só os principais que mais caem em prova, implicitos e '
     'um resumo com um caso real de cada ja ta bom'),
    ('tutor',
     'Os princípios implícitos que mais caem em provas de carreiras policiais cobrados '
     'pela banca são: - Supremacia do interesse público sobre o privado - '
     'Indisponibilidade do interesse público - Autotutela - Continuidade dos serviços '
     'públicos - Razoabilidade e proporcionalidade Sobre a supremacia, pense em uma '
     'desapropriação: o Estado desapropria um terreno particular para construir uma '
     'delegacia. O interesse da coletividade em ter segurança pública prevalece sobre o '
     'direito individual de propriedade. Sobre a indisponibilidade, imagine um delegado '
     'que descobre provas de um crime cometido por um amigo íntimo; ele não pode '
     'simplesmente rasgar o inquérito para protegê-lo, porque os bens e interesses '
     'públicos não pertencem ao agente, que não pode abrir mão deles. Quer que eu siga '
     'para o próximo tópico de Direito Administrativo?'),
    ('aluno', 'e o restante não vai explicar?'),
    ('tutor',
     'Vamos explicar agora o princípio da continuidade dos serviços públicos, que estava '
     'na lista. Ele garante que as atividades essenciais da administração não podem parar, '
     'por isso a lei impõe limites ao direito de greve de servidores em áreas como a '
     'segurança pública. Você sabe se o direito de greve é permitido para os policiais '
     'civis na sua prova?'),
    ('aluno', 'nao é permitido'),
    ('tutor',
     'Exato. Como os policiais civis exercem atividade essencial de segurança pública, o '
     'Supremo Tribunal Federal entende que o direito de greve é vedado para as carreiras '
     'policiais civis e militares, justamente para garantir a continuidade dos serviços '
     'públicos. Quer que eu siga para os princípios da razoabilidade e da '
     'proporcionalidade?'),
    ('aluno', 'agora eu queria que trouxesse um resumão com tudo de uma vez ja'),
    ('tutor',
     'Vamos ao resumão completo dos princípios implícitos que caem na sua prova: - '
     'Supremacia do interesse público: o interesse da coletividade está acima do '
     'particular, como ocorre na desapropriação de um imóvel para construir uma delegacia. '
     '- Indisponibilidade do interesse público: o agente não é dono da coisa pública e não '
     'pode abrir mão dela, como o delegado que não pode arquivar um inquérito por amizade. '
     '- Autotutela: a administração pode anular seus próprios atos ilegais ou revogar os '
     'inconvenientes sem precisar do Judiciário, conforme a Súmula 473 do Supremo Tribunal '
     'Federal. - Continuidade dos serviços públicos: a atividade essencial não pode parar, '
     'justificando, por exemplo, a proibição de greve para policiais civis. - '
     'Razoabilidade e proporcionalidade: exigem adequação entre os meios e os fins, '
     'impedindo exageros da administração pública. Quer que eu siga para os poderes '
     'administrativos?'),
]

LOG_PRINCIPIOS = [{"autor": a, "texto": t} for a, t in PRINCIPIOS]
PEDIDO_DE_RESUMO = "queria um resumão mais detalhado com 2 exemplos de cada"


def test_pedido_de_resumo_nao_vira_consulta():
    """A fala que envenenou a busca numa aula inteira de Direito Administrativo.

    `em_foco` devolvia a PRÓPRIA fala somada às anteriores do aluno — "agora eu
    queria que trouxesse um resumão com tudo de uma vez" —, uma consulta sem uma
    palavra de matéria. Voltaram CP art. 150 (violação de domicílio), CP art. 28
    (embriaguez) e CF art. 220 (comunicação social), e o tutor avisou ao aluno
    que o assunto "não está no seu material". Estava na apostila; não no que a
    busca trouxe.

    "resumão", "detalhado" e "trouxesse" não são assunto. Pedir o formato da
    resposta é meta-conversa como "me explica" — só com palavras que a lista
    ainda não tinha."""
    assert assunto.palavras_de_conteudo(PEDIDO_DE_RESUMO) == []
    assert not assunto.diz_assunto(PEDIDO_DE_RESUMO)

    foco = assunto.em_foco(LOG_PRINCIPIOS, PEDIDO_DE_RESUMO) or ""
    assert not foco.lower().startswith("queria um resum"), foco
    # A consulta passa a ser o turno do TUTOR, que é onde o assunto está escrito
    # por extenso — mesma regra do caso Maria da Penha.
    assert "princípios implícitos" in foco.lower(), foco


def test_pedir_o_formato_da_resposta_nao_e_assunto_novo():
    """Vale pras duas falas do mesmo tipo, não só pra que gerou o relato — uma
    lista que conserta um caso literal e deixa o vizinho passar não conserta
    nada."""
    for fala in ["agora eu queria que trouxesse um resumão com tudo de uma vez ja",
                 "me traz um resumo detalhado",
                 "traga os principais"]:
        assert assunto.palavras_de_conteudo(fala) == [], fala

    # "citar" NÃO entrou na lista, e é decisão: citação é ato processual no CPP
    # ("citação do réu"), e cegar a busca pra ela custa mais que a diluição.
    assert assunto.palavras_de_conteudo("cite os principais") == ["cite"]

    # E o contrário continua valendo: pedido COM assunto troca o foco.
    assert assunto.palavras_de_conteudo("me traz um resumo de improbidade") == ["improbidade"]


def test_risada_nao_e_assunto():
    """"ola boa noite se é que ta de noite kkk" virou consulta de busca: todas as
    outras palavras estão em `VAZIAS`, sobrou "kkk", e voltaram CP 111, CP 150 e
    a Lei 8.112 art. 70 — debaixo de uma saudação.

    É forma livre (kkk, kkkkkk, rsrs, hahaha), então lista não resolve: resolve
    regra. E a risada colada num pedido real não pode levar o pedido junto."""
    assert assunto.palavras_de_conteudo("ola boa noite se é que ta de noite kkk") == []
    assert assunto.palavras_de_conteudo("rsrs") == []
    assert assunto.em_foco([], "ola boa noite se é que ta de noite kkk") is None

    assert assunto.palavras_de_conteudo("me explica peculato kkk") == ["peculato"]
    assert assunto.palavras_de_conteudo("hahaha adorei") == ["adorei"]
    # "hurto" não é risada, é erro de digitação de uma palavra de matéria.
    assert assunto.palavras_de_conteudo("hurto ou furto?") == ["hurto", "furto"]
