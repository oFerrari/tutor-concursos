"""Testes de core/edital.py — funções puras de extração, sem banco."""
from pathlib import Path

from core import llm
from core.edital import (candidatos_data_prova, estrutura_com_fallback, extrair_estrutura,
                         extrair_topicos,
                         limpar_paginacao,
                         recortar_conteudo_programatico)

# Trecho REAL do edital 001/2026 da Dataprev (banca FGV) — o layout que
# quebrou a extração em produção. Fica em arquivo, não em string aqui,
# porque o que importa é o texto com as QUEBRAS DE LINHA como o PDF
# entrega: é justamente a quebra de linha que separa cabeçalho de item.
FGV = (Path(__file__).parent / "fixtures" / "edital_fgv_dataprev.txt").read_text(encoding="utf-8")

TEXTO_EXEMPLO = """
1. DAS DISPOSIÇÕES PRELIMINARES considerando a Lei Complementar nº 259,
de 21 de julho de 2023.

9. DA PROVA OBJETIVA
9.1 As Provas Objetivas serão realizadas no dia 11 de outubro de 2026
(domingo), no turno da tarde.

20.1 A Prova Discursiva será realizada no dia 20 de dezembro de 2026
(domingo).
"""

TEXTO_PROGRAMATICO = """
ANEXO I CONTEÚDO PROGRAMÁTICO
1. DIREITO PENAL: 1.1 Princípios Fundamentais. 1.1.1 Legalidade e
Anterioridade. 1.2 Aplicação da Lei Penal. 1.2.1 Lei Penal no Tempo.
2. DIREITO CONSTITUCIONAL: 2.1 Direitos Fundamentais. 2.2 Organização
do Estado.
"""


def test_candidatos_data_prova_acha_a_data_certa():
    cands = candidatos_data_prova(TEXTO_EXEMPLO)
    assert len(cands) >= 2
    # a que menciona "prova objetiva" perto deve vir primeiro
    assert cands[0]["data"].isoformat() == "2026-10-11"


def test_candidatos_data_prova_ignora_citacao_legal():
    """'de 21 de julho de 2023' (citação de lei) não tem a palavra 'dia'
    antes — não deveria aparecer como candidato a data de prova."""
    cands = candidatos_data_prova(TEXTO_EXEMPLO)
    datas = [c["data"].isoformat() for c in cands]
    assert "2023-07-21" not in datas


def test_candidatos_data_prova_texto_vazio_devolve_lista_vazia():
    assert candidatos_data_prova("") == []


def test_candidatos_data_prova_sem_prova_objetiva_ainda_lista_mas_pontua_zero():
    texto = "reunião marcada no dia 5 de maio de 2027 para tratar de outro assunto."
    cands = candidatos_data_prova(texto)
    assert len(cands) == 1
    assert cands[0]["pontuacao"] == 0


def test_extrair_topicos_conta_disciplinas_certo():
    topicos = extrair_topicos(TEXTO_PROGRAMATICO)
    disciplinas = {t["disciplina"] for t in topicos}
    assert disciplinas == {"Direito Penal", "Direito Constitucional"}


def test_extrair_topicos_conta_so_as_folhas():
    """
    MUDANÇA DE COMPORTAMENTO, deliberada: antes contava 4 (1.1, 1.1.1, 1.2,
    1.2.1), agora conta 2 — só as folhas. "1.1 Princípios Fundamentais" é o
    guarda-chuva de "1.1.1 Legalidade e Anterioridade"; contar os dois
    inflava o denominador de "quantos tópicos existem" pela ALTURA da
    árvore, e é esse denominador que vira cobertura e ritmo necessário.

    Não é invenção nova: db/007_edital.sql já dizia "não modela hierarquia
    porque nada hoje precisa navegar a árvore, só contar folhas". O teste
    antigo travava o que o código FAZIA, não o que a migração dizia.
    """
    topicos = extrair_topicos(TEXTO_PROGRAMATICO)
    penal = [t for t in topicos if t["disciplina"] == "Direito Penal"]
    assert [t["texto"] for t in penal] == [
        "1.1.1 Legalidade e Anterioridade.",
        "1.2.1 Lei Penal no Tempo.",
    ]


def test_extrair_topicos_texto_sem_padrao_devolve_vazio():
    assert extrair_topicos("um texto qualquer sem numeração nenhuma.") == []


def test_extrair_topicos_ordem_e_sequencial_e_unica():
    topicos = extrair_topicos(TEXTO_PROGRAMATICO)
    ordens = [t["ordem"] for t in topicos]
    assert ordens == list(range(len(topicos)))


# ----------------------------------------------------------- layout da FGV
# Estes travam o defeito que apareceu com um edital de verdade: cabeçalhos
# de disciplina SEM numeração ("LÍNGUA PORTUGUESA:"), que a versão anterior
# não achava — e, pior, substituía por fantasmas tirados de número de versão
# ("...version 1.1. PLATAFORMA BÁSICA:") e de item no meio de parágrafo
# ("3. ECF:", "12. IOF:").

def _disciplinas(texto):
    return {t["disciplina"] for t in extrair_topicos(texto)}


def test_fgv_acha_as_disciplinas_sem_numeracao():
    d = _disciplinas(FGV)
    assert {"Língua Portuguesa", "Língua Inglesa", "Raciocínio Lógico",
            "Atualidades E Inteligência Artificial",
            "Legislação Acerca De Segurança Da Informação E Proteção De Dados",
            "Redes De Computadores", "Banco De Dados", "Plataforma Básica",
            "Automação", "Gestão De Servidores"} <= d


def test_fgv_nao_inventa_disciplina_de_numero_de_versao_nem_de_item():
    """`Ecf`, `Iof` e `Lalur` são itens no meio de parágrafo de
    Contabilidade Tributária — nunca disciplinas. Era o que a tela mostrava."""
    assert _disciplinas(FGV).isdisjoint({"Ecf", "Iof", "Lalur"})


def test_perfil_sem_subcabecalho_vira_uma_disciplina_POR_ITEM():
    """
    MUDANÇA DE COMPORTAMENTO deliberada. Antes, perfil que lista tópicos
    direto (sem "DISCIPLINA:" no meio) virava UMA disciplina com o nome do
    próprio cargo. Passou a virar uma disciplina por ITEM DE PRIMEIRO NÍVEL.

    O que forçou: as 13 áreas de Perito Criminal do edital da PF são todas
    assim, e a Área 3 saía como "Perito Criminal Federal – Área 3: Informática
    Forense" com 104 tópicos dentro. Fiel ao documento e inútil pro produto —
    `mesa.filtro` recorta por NOME de disciplina, e esse nome não casa com
    nada do acervo. Os itens de primeiro nível são as matérias, e é assim que
    o candidato fala delas ("estou em bancos de dados").

    O que o teste antigo protegia continua valendo e está aqui embaixo:
    nenhum tópico do perfil pode cair no cargo ANTERIOR.
    """
    d = _disciplinas(FGV)
    assert "Análise De Negócios" in d          # item 1 do PERFIL 1, agora disciplina
    assert "Análise De Negócios De Ti" not in d  # o nome do CARGO não é matéria


def test_recorte_ignora_as_regras_do_edital():
    """As regras de inscrição são centenas de itens numerados ("4.5.1",
    "10.13.6") e não são matéria de estudo. Sem o recorte pelo conteúdo
    programático, elas viravam tópico — foi assim que uma disciplina
    fantasma acumulou 257 deles."""
    corpo, achou = recortar_conteudo_programatico(FGV)
    assert achou
    assert "pagamento da taxa de inscrição" not in corpo   # antes do Anexo I
    assert "Requisitos: Certificado ou diploma" not in corpo   # Anexo II
    assert "LÍNGUA PORTUGUESA" in corpo


def test_recorte_sem_marcador_devolve_tudo_e_avisa():
    corpo, achou = recortar_conteudo_programatico("edital sem anexo nenhum")
    assert achou is False and corpo == "edital sem anexo nenhum"


def test_mobilia_de_pagina_nao_engole_disciplina():
    """
    Cada página do PDF abre com "DATAPREV | CONCURSO PÚBLICO 2026" e o
    número da página numa linha só dela. Disciplina que calha de começar no
    topo de uma página fica precedida por esse número — e era descartada
    como "frase cortada no meio", com os tópicos dela migrando pra
    disciplina anterior. MEDIDO: 3 disciplinas somem e o total continua
    parecendo plausível, que é o que torna esse erro difícil de ver.
    """
    assert {"Plataforma Básica", "Matemática Financeira",
            "Gestão De Servidores"} <= _disciplinas(FGV)


def test_limpar_paginacao_tira_rodape_repetido_e_numero_solto():
    limpo = limpar_paginacao(FGV)
    assert "CONCURSO PÚBLICO 2026" not in limpo
    assert "LÍNGUA PORTUGUESA" in limpo
    # cabeçalho de disciplina que se repete entre perfis NÃO é rodapé
    assert "SEGURANÇA DA INFORMAÇÃO" in limpo


# ------------------------------------------------------ layout do AOCP
# Edital SAEB 02/2026 (PC-BA). Mesma estrutura de conteúdo programático,
# duas diferenças que zeravam a extração inteira:
#   - item numerado com PONTO ("1. Compreensão", não "1 Compreensão");
#   - o anexo se chama "CONTEÚDOS PROGRAMÁTICOS" (plural) e o edital cita
#     esse nome VÁRIAS vezes antes de chegar nele.
AOCP = (Path(__file__).parent / "fixtures" / "edital_aocp_pcba.txt").read_text(encoding="utf-8")


def test_aocp_le_o_edital_que_antes_voltava_zero():
    topicos = extrair_topicos(AOCP)
    assert len(topicos) > 50, "edital inteiro devolvia 0 tópicos"
    assert {"Língua Portuguesa", "Raciocínio Lógico", "Informática", "Medicina Legal",
            "Direito Penal", "Direito Processual Penal", "Noções De Contabilidade",
            "Estatística"} <= _disciplinas(AOCP)


def test_aocp_item_com_ponto_conta_como_topico():
    """"1. Compreensão e interpretação de texto" é item; o `\\s+` da versão
    anterior batia no ponto e não casava com NADA neste edital."""
    portugues = [t for t in extrair_topicos(AOCP) if t["disciplina"] == "Língua Portuguesa"]
    assert len(portugues) == 10                       # itens 1 a 10, todos folha
    assert portugues[0]["texto"].startswith("1. Compreensão e interpretação de texto")


def test_recorte_pega_o_anexo_e_nao_a_referencia_cruzada():
    """O edital cita "Anexo I - Conteúdos Programáticos" logo no item 1.8 e
    de novo em 7.1.2, 7.2.9.1 e 16.14. Pegar a PRIMEIRA menção recortava um
    pedaço das regras de inscrição, e o anexo real nunca era lido."""
    corpo, achou = recortar_conteudo_programatico(AOCP)
    assert achou
    assert "LÍNGUA PORTUGUESA" in corpo
    assert "devolução da importância paga" not in corpo    # regras de inscrição
    assert "instaurar e presidir inquéritos" not in corpo  # Anexo II


def test_numero_no_fim_de_frase_nao_vira_topico():
    """"...Brasil de 1988 (Artigos 1º...)" e "de 1988. A Constituição" têm a
    FORMA de um item (número, ponto, espaço, maiúscula). O que os separa é
    abrir oração ou não — sem essa âncora, "1988" viraria tópico."""
    textos = [t["texto"] for t in extrair_topicos(AOCP)]
    assert not [t for t in textos if t.startswith("1988")]


# --------------------------------- quem decide a estrutura (cargo x matéria)
# A régua mudou depois de quatro editais reais: o parser agrupa só quando o
# EDITAL DIZ onde o cargo começa ("CARGO: X", "PERFIL N: X"). Quando não diz,
# quem lê é o modelo — separar cargo de seção, de disciplina e de rodapé num
# layout nunca visto é leitura, não casamento de padrão. Ver o comentário
# longo em `estrutura_com_fallback` e o que substituiu `RE_CARGO_NU`.

def test_parser_resolve_sozinho_quando_o_edital_declara_o_cargo(llm_falso):
    """FGV ("PERFIL N:") e AOCP ("CARGO:") não gastam cota: o marcador está
    escrito, o agrupamento é determinístico e está travado em fixture."""
    for texto in (FGV, AOCP):
        estrutura, origem = estrutura_com_fallback(texto)
        assert origem == "parser"
        assert estrutura["cargos"]
    assert llm_falso.chamadas == [], "não deveria chamar o modelo"


def test_sem_marcador_de_cargo_quem_le_e_o_modelo(llm_falso):
    """O caso que o gatilho antigo deixava passar: o parser ACHA disciplina
    (então não parecia falha) mas não acha cargo nenhum — e entregava os
    cargos somados numa lista só. Achar disciplina não é ter entendido a
    estrutura."""
    llm_falso.retorno = ('{"comuns": [0], "cargos": [{"nome": "Contador",'
                         ' "disciplinas": [{"indice": 1, "nome": "Informática"}]}]}')
    texto = ("ANEXO I - CONTEÚDO PROGRAMÁTICO\n"
             "1. LÍNGUA PORTUGUESA: 1.1 Crase. 1.2 Pontuação.\n"
             "2. INFORMÁTICA: 2.1 Windows. 2.2 Excel.\n")
    parser_sozinho = extrair_estrutura(texto)
    assert parser_sozinho["comuns"] and not parser_sozinho["cargos"]   # acha matéria, não acha cargo

    estrutura, origem = estrutura_com_fallback(texto)
    assert origem == "llm", "sem marcador de cargo, o modelo tem que ler"
    assert [c["nome"] for c in estrutura["cargos"]] == ["Contador"]


def test_agrupamento_nao_manda_topico_pro_modelo(llm_falso):
    """O erro que quebrou o PC-PR: pedir ao modelo os 246 tópicos que o
    parser JÁ tem estourava o teto de saída, o JSON vinha cortado e o
    `except` devolvia a lista somada — caladamente. Agora o modelo responde
    ÍNDICE, e os tópicos saem do parser."""
    llm_falso.retorno = ('{"comuns": [], "cargos": [{"nome": "Papiloscopista Policial",'
                         ' "disciplinas": [{"indice": 1, "nome": "Biologia Forense"}]}]}')
    texto = ("ANEXO I - CONTEÚDO PROGRAMÁTICO\n"
             "1. DIREITO PENAL: 1.1 Dolo. 1.2 Culpa.\n"
             "2. BIOLOGIA: 2.1 Citologia. 2.2 Genética.\n")
    estrutura, origem = estrutura_com_fallback(texto)
    assert origem == "llm"
    disc = estrutura["cargos"][0]["disciplinas"][0]
    # nome corrigido pelo modelo (o PDF quebra título), tópicos vindos do parser
    assert disc["disciplina"] == "Biologia Forense"
    assert [t.split()[0] for t in disc["topicos"]] == ["2.1", "2.2"]
    # o prompt mandou o CATÁLOGO de cabeçalhos, nunca os tópicos pra devolver
    assert "[1] Biologia" in llm_falso.chamadas[-1]["prompt"]


def test_indice_invalido_do_modelo_nao_derruba_a_ingestao(llm_falso):
    """Índice fora da lista é resposta inválida, não dado: some sozinho em
    vez de estourar em cima de um upload que o usuário já fez."""
    llm_falso.retorno = ('{"comuns": [0, 99], "cargos": []}')
    estrutura, origem = estrutura_com_fallback(
        "ANEXO I - CONTEÚDO PROGRAMÁTICO\n1. DIREITO PENAL: 1.1 Dolo.\n")
    assert origem == "llm"
    assert [d["disciplina"] for d in estrutura["comuns"]] == ["Direito Penal"]


def test_falha_do_modelo_fica_VISIVEL_na_origem(llm_falso):
    """Antes devolvia `parser`, idêntico a "o parser resolveu sozinho" — e o
    aluno ia embora com os cargos somados sem saber que dava pra tentar de
    novo."""
    llm_falso.excecao = llm.ErroLLM("sem cota")
    _, origem = estrutura_com_fallback(
        "ANEXO I - CONTEÚDO PROGRAMÁTICO\n1. DIREITO PENAL: 1.1 Dolo.\n")
    assert origem == "parser_apos_falha"


# ------------------------------- cabeçalho que a extração desloca (PC-PR)
# Os três casos abaixo vêm do MESMO bloco (Delegado de Polícia, PC-PR 01/2026),
# que tem 8 disciplinas e saía com 5. Cada um é um defeito distinto, e os três
# foram medidos no PDF real antes de virar regra.

def test_disciplina_colada_na_mesma_linha_do_cargo():
    """A extração do PC-PR entrega "DELEGADO  DE  POLÍCIA   1.  DIREITO
    PENAL:" — cargo e primeira disciplina na MESMA linha. Exigir início de
    linha perdia Direito Penal, que vale 20 das 100 questões da prova."""
    d = _disciplinas("ANEXO I\nDELEGADO  DE  POLÍCIA   1.  DIREITO PENAL: 1.1 Dolo. 1.2 Culpa.\n")
    assert "Direito Penal" in d


def test_numeracao_propria_vence_o_filtro_de_continuacao():
    """O guarda de continuação existe pra matar "LALUR:" no meio do item 2.4.
    Mas ele rejeita por "o texto antes terminou em dígito / ponto e vírgula",
    e num edital cuja extração espalha pontuação isso é comum e LEGÍTIMO: no
    PC-PR sumiam duas disciplinas — a 4 porque o texto antes termina em "3.19"
    e a 7 porque termina em "12.037/2009);".

    O que separa os dois casos é a numeração PRÓPRIA: "LALUR:" é palavra nua."""
    texto = ("ANEXO I - CONTEÚDO PROGRAMÁTICO\n"
             "3. LEGISLAÇÃO: 3.18 Marco Legal. 3.19\n"
             "4. DIREITO CONSTITUCIONAL: 4.1 Teoria. 4.2 Controle.\n"
             "6. LEGISLAÇÃO ESTADUAL: 6.7 LGPD (Lei n.º 12.037/2009);\n"
             "7. DIREITOS HUMANOS: 7.1 Teoria Geral. 7.2 Sistemas.\n")
    d = _disciplinas(texto)
    assert {"Direito Constitucional", "Direitos Humanos"} <= d


def test_palavra_nua_depois_de_item_pendurado_continua_barrada():
    """A contraprova do teste acima: sem numeração própria, o cabeçalho falso
    que motivou o guarda segue fora. Se este teste passar a falhar, a regra
    nova virou peneira."""
    texto = ("ANEXO I - CONTEÚDO PROGRAMÁTICO\n"
             "2. CONTABILIDADE: 2.3 Formas de pagamento; 2.4\n"
             "LALUR: forma de escrituração fiscal do lucro real.\n")
    assert "Lalur" not in _disciplinas(texto)


# --------------------------------------------------- Cesgranrio (TRANSPETRO)
# TERCEIRA banca, terceiro layout, e a lição de método se repetiu pela terceira
# vez: cada edital novo é um caso de teste novo. Este trouxe QUATRO defeitos
# distintos, e nenhum deles aparecia nos dois anteriores.
CESGRANRIO = (Path(__file__).parent / "fixtures"
              / "edital_cesgranrio_transpetro.txt").read_text(encoding="utf-8")


def test_cesgranrio_enfase_e_marcador_de_cargo():
    """"ÊNFASE 8: CIÊNCIA DE DADOS" é a forma da Cesgranrio de dizer onde o
    cargo começa — o mesmo papel de "PERFIL 3:" (FGV) e "CARGO:" (AOCP).

    Sem isso o edital da TRANSPETRO (33 ênfases) devolvia ZERO cargo, e o que
    entrava no lugar era lixo: a tela mostrava "4 disciplinas · 67 tópicos",
    duas delas chamadas "I- Matemática" e "Dados" — que são SUBSEÇÕES de dentro
    da ênfase de Ciência de Dados, não matérias do concurso."""
    est = extrair_estrutura(CESGRANRIO)
    nomes = {c["nome"] for c in est["cargos"]}
    assert len(nomes) == 5, nomes
    assert "Ciência De Dados" in nomes
    assert "Engenharia De Telecomunicações" in nomes
    # E o marcador NÃO vira disciplina: "Ênfase 8" como nome de matéria é o
    # sintoma de o cargo ter sido lido como cabeçalho de conteúdo.
    assert not [d for d in _disciplinas(CESGRANRIO) if d.lower().startswith("ênfase")]


def test_cesgranrio_numero_quebrado_pelo_pdf_ainda_casa():
    """O pypdf separa o dígito das dezenas do das unidades neste edital:
    "ÊNFASE 1 0 :", "ÊNFASE 1 4:", "ÊNFASE 2 2:".

    Com `\\d{0,2}` (que era o padrão) 12 das 33 ênfases casavam e 21 sumiam — e o
    efeito é o pior formato de erro, o mesmo da mobília de página no FGV: os
    tópicos da ênfase que não casou caem na ênfase ANTERIOR, e o total continua
    plausível. Nenhuma contagem denuncia."""
    from core.edital import RE_CARGO
    for linha in ("ÊNFASE 1 0 : COMERCIALIZAÇÃO E LOGÍSTICA – TRANSPORTE MARÍTIMO",
                  "ÊNFASE 2 2:  ENGENHARIA DE TELECOMUNICAÇÕES",
                  "ÊNFASE 1 4:  ENFERMAGEM DO TRABALHO",
                  "ÊNFASE 8: CIÊNCIA DE DADOS"):
        assert RE_CARGO.search(linha), linha


def test_cesgranrio_bloco_sem_numeracao_nao_perde_o_conteudo():
    """A Cesgranrio escreve várias ênfases em PROSA, sem numerar nada — as
    matérias são rótulos em caixa alta e os tópicos vêm separados por ponto ou
    ponto-e-vírgula.

    `RE_SUBITEM` não acha nada nisso, e `extrair_estrutura` só aceita disciplina
    COM tópico: as ênfases de Administração e de Advocacia (as duas maiores em
    conteúdo do edital) saíam com zero disciplina e zero tópico, sem nada
    denunciar, porque as outras 31 enchiam o número."""
    est = extrair_estrutura(CESGRANRIO)
    automacao = next(c for c in est["cargos"] if c["nome"] == "Engenharia De Automação")
    # A ênfase 17 é UMA lista de matérias separada por ponto-e-vírgula, sem
    # cabeçalho nenhum: vira uma disciplina com o nome do cargo e os itens dela.
    assert automacao["disciplinas"], "ênfase em prosa perdeu o conteúdo"
    assert sum(len(d["topicos"]) for d in automacao["disciplinas"]) >= 10


def test_cesgranrio_numeral_romano_sai_do_nome_da_disciplina():
    """A ênfase de Ciência de Dados numera as seções em ROMANO ("I- MATEMÁTICA:",
    "VIII- PROCESSAMENTO DE LINGUAGEM NATURAL (NLP):"). O romano entrava no nome
    e a disciplina virava "I- Matemática" — e nome de disciplina é o que
    `mesa.filtro` usa pra recortar a fila, por ILIKE dos dois lados. Prefixo
    sobrando é disciplina que nunca casa com o acervo."""
    disc = _disciplinas(CESGRANRIO)
    assert "Matemática" in disc
    assert not [d for d in disc if d.startswith(("I-", "II-", "III-", "VIII-", "XI-"))]


def test_cesgranrio_data_da_prova_nao_e_o_prazo_de_recurso():
    """Relatado na tela: "Prova em 2026-12-01" quando a prova é 29/11/2026.

    01/12 é o fim do prazo de RECURSO contra o gabarito, e o título da seção
    ("DA REVISÃO DA NOTA DA PROVA OBJETIVA") cai na janela de contexto dela.
    Empatava 3 a 3 com a data real, e empate se resolve pela ordem no documento
    — o item 9.1 está na página 32 e o cronograma na 79."""
    cands = candidatos_data_prova(CESGRANRIO)
    assert cands[0]["data"].isoformat() == "2026-11-29", cands[:3]


def test_cesgranrio_conhecimentos_basicos_ficam_comuns():
    """Português e Inglês valem pra TODAS as 33 ênfases: vêm antes do primeiro
    marcador de cargo, então são comuns — é a regra posicional de sempre. Os
    números são os do edital: 12 itens de Português, 2 de Inglês."""
    est = extrair_estrutura(CESGRANRIO)
    comuns = {d["disciplina"]: len(d["topicos"]) for d in est["comuns"]}
    assert comuns == {"Língua Portuguesa": 12, "Língua Inglesa": 2}, comuns


def test_cesgranrio_nao_mexeu_nas_outras_duas_bancas():
    """A trava que importa quando se aprende um layout novo. Cada regex nova
    quebrou o edital seguinte neste módulo — está documentado. Os números
    abaixo foram medidos no HEAD antes de qualquer alteração para a Cesgranrio,
    e são IDÊNTICOS depois: FGV 4 cargos/20 disciplinas/104 tópicos, AOCP 2/13/86.

    Se este teste falhar, o layout novo custou o antigo."""
    for texto, esperado in ((FGV, (4, 20, 104)), (AOCP, (2, 13, 86))):
        est = extrair_estrutura(texto)
        cargos = len(est["cargos"])
        disc = len(est["comuns"]) + sum(len(c["disciplinas"]) for c in est["cargos"])
        top = (sum(len(d["topicos"]) for d in est["comuns"])
               + sum(len(d["topicos"]) for c in est["cargos"] for d in c["disciplinas"]))
        assert (cargos, disc, top) == esperado, (cargos, disc, top)
