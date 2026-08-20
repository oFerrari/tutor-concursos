"""
Citação do tutor tem que ter trecho por trás.

Puro: nem banco, nem LLM, nem embedding. A regra é de código de propósito — o
prompt já manda "cite SOMENTE as referências que acompanham cada trecho" e
instrução vaza, mesma lição da retenção do gabarito em `socratic`.

As citações usadas aqui são as que o modelo REALMENTE escreveu, medidas em cinco
respostas reais, contra as referências que realmente foram recuperadas naqueles
turnos. Fixture inventado testaria o formato que eu imagino que ele usa, e o
ponto todo é que ele não usa o que eu imagino: acrescenta ", XVI", ", § 1º",
", inciso II", troca "5o" por "5º" e às vezes larga a rubrica.
"""
from core import retrieval, socratic

VERSAO = "test-citacao-v1"

# Os trechos como o acervo os apresenta — `titulo` é o do documento ingerido, e
# varia de forma de propósito: "cp" (sem --titulo), "Código de Processo Penal" e
# "Lei 8.112/1990" (com), material do aluno sem artigo nenhum.
ACERVO = [
    {"titulo": "cp", "norma": "CP", "artigo": "312", "rubrica": "Peculato"},
    {"titulo": "cp", "norma": "CP", "artigo": "316", "rubrica": "Concussão"},
    {"titulo": "Código de Processo Penal", "norma": "CPP", "artigo": "5o"},
    {"titulo": "Código de Processo Penal", "norma": "CPP", "artigo": "12"},
    {"titulo": "cf", "norma": "CF", "artigo": "37"},
    {"titulo": "Lei 8.112/1990", "norma": "L8112", "artigo": "118",
     "rubrica": "Da Acumulação"},
    {"titulo": "curso-392722-aula-04", "norma": None, "pagina": 7},
]

# Literalmente o que saiu do modelo nas cinco perguntas medidas.
CITOU_DE_VERDADE = [
    "cp, art. 312",                            # rubrica largada
    "Código de Processo Penal, art. 12",       # igual à referência
    "Código de Processo Penal, art. 5º, inciso II",  # trecho diz "5o", ele "5º"
    "CF, art. 37, XVI",                        # caixa diferente + inciso
    "cp, art. 316, § 1º",                      # parágrafo acrescentado
]


def _com_todas(citacoes):
    return [c for c in citacoes if socratic.com_fonte(c, ACERVO)]


# ------------------------------------------------------- o que TEM de passar

def test_as_citacoes_reais_do_modelo_sobrevivem():
    """O risco desta guarda não é deixar passar lixo — é apagar fonte boa. Uma
    resposta que perde o colchete verdadeiro perde o que dá valor a ela."""
    assert _com_todas(CITOU_DE_VERDADE) == CITOU_DE_VERDADE


def test_apelido_da_norma_vale_como_identidade():
    """O mesmo documento se apresenta como "Código de Processo Penal" e "CPP", e
    os dois estão na LINHA do chunk (`titulo` e `norma`). Aceitar os dois não é
    tabela de apelidos escrita à mão — essa envelheceria calada."""
    assert socratic.com_fonte("CPP, art. 12", ACERVO)
    assert socratic.com_fonte("L8112, art. 118", ACERVO)


def test_material_do_aluno_casa_por_nome():
    """Chunk de PDF do aluno (019) não tem artigo: a referência dele é o título e
    a página. Exigir artigo apagaria a citação da própria apostila."""
    assert socratic.com_fonte("curso-392722-aula-04", ACERVO)
    assert socratic.com_fonte("curso-392722-aula-04, p. 7", ACERVO)


def test_resposta_sem_nada_a_apagar_sai_identica():
    """Byte por byte: `_costurar` mexe em espaço e pontuação, e mexer nisso sem
    motivo é risco sem prêmio."""
    texto = "O peculato exige posse em razão do cargo [cp, art. 312].  Dois espaços."
    assert socratic.limpar_citacoes(texto, ACERVO) is texto


# ------------------------------------------------------- o que TEM de cair

def test_lei_fora_do_acervo_nao_fica_citada():
    """O caso real. Conversa inteira sobre Lei Maria da Penha, e o tutor fechou
    com "[Lei Maria da Penha, art. 5º]" sem nenhum trecho dessa lei — que nem
    está no acervo. O conteúdo estava certo e a fonte era inverificável, e é a
    verificabilidade que dá valor ao colchete: um que o aluno não pode conferir
    contamina os verdadeiros da mesma resposta.

    Ele não inventou do nada — copiou dos turnos ANTERIORES dele mesmo, que estão
    no histórico (014). Por isso o filtro é na SAÍDA: a resposta filtrada é a que
    vai pro banco, e aí o histórico para de ensinar o erro."""
    assert not socratic.com_fonte("Lei Maria da Penha, art. 5º", ACERVO)
    texto = ("a relação de subordinação basta para atrair a incidência da lei "
             "protetiva [Lei Maria da Penha, art. 5º]?")
    limpo = socratic.limpar_citacoes(texto, ACERVO)
    assert "Maria da Penha" not in limpo
    # A AFIRMAÇÃO fica; só o carimbo de fonte que ela não tem é que sai. E sem
    # cicatriz de pontuação, que lê como app quebrado.
    assert limpo.endswith("atrair a incidência da lei protetiva?")


def test_artigo_errado_da_norma_certa_tambem_cai():
    """A colisão mais fácil de deixar passar: a norma foi recuperada, o artigo
    não. "[cf, art. 5º]" com apenas o art. 37 da CF no contexto é fonte inventada
    igual — e errar dispositivo é grave pra concurseiro."""
    assert not socratic.com_fonte("cf, art. 5º", ACERVO)
    assert not socratic.com_fonte("cp, art. 121", ACERVO)


def test_rotulo_de_secao_do_prompt_nao_e_fonte():
    """Regressão registrada em Decisões: uma resposta real terminou com "...está
    em 75.3% [DESEMPENHO REAL DO ALUNO]". Os rótulos já saíram do prompt; esta
    guarda pega a classe inteira, inclusive rótulo que alguém acrescente
    amanhã."""
    for falso in ("DESEMPENHO REAL DO ALUNO", "Contexto do aluno",
                  "Trechos de lei recuperados", "acervo"):
        assert not socratic.com_fonte(falso, ACERVO), falso


def test_conector_sai_junto_com_a_citacao():
    """Caminho DEFENSIVO, e declarado como tal: nas seis citações medidas, todas
    vinham no fim da oração, onde apagar o colchete não deixa cicatriz. Se vier
    no meio ("conforme [X], o vínculo..."), apagar só o colchete deixaria
    "conforme , o vínculo" — pontuação quebrada lê como app com defeito."""
    texto = ("Conforme [Lei Inexistente, art. 5º], o vínculo basta; já o concurso "
             "exige aprovação [CF, art. 37, II], e segue.")
    limpo = socratic.limpar_citacoes(texto, ACERVO)
    assert limpo == "O vínculo basta; já o concurso exige aprovação [CF, art. 37, II], e segue."


def test_sem_trecho_nenhum_nenhuma_citacao_sobrevive():
    """`explicar` responde com contexto vazio quando a fala não nomeia assunto
    (é a instrução de "nenhum trecho recuperado"). Se o modelo citar ali, é
    memória própria dele — o único lugar de onde poderia vir."""
    assert socratic.limpar_citacoes("O prazo é de cinco anos [CF, art. 37].", []) \
        == "O prazo é de cinco anos."


# ------------------------------------------------- uma regra, um dono

def test_formato_da_referencia_tem_um_dono_so():
    """`formatar_contexto` (que escreve o rótulo no prompt) e `com_fonte` (que
    confere a citação contra ele) precisam da MESMA regra de formação. Duas
    cópias divergem, e o sintoma seria a guarda apagando fonte legítima — mesmo
    motivo de `RE_CITACAO` ser importada em vez de copiada em `core/assunto.py`."""
    for c in ACERVO:
        rotulo = retrieval.referencia(c)
        assert f"[{rotulo}]" in retrieval.formatar_contexto([{**c, "texto": "x"}])
        assert socratic.com_fonte(rotulo, ACERVO), rotulo
