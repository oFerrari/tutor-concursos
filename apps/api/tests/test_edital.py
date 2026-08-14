"""Testes de core/edital.py — funções puras de extração, sem banco."""
from pathlib import Path

from core.edital import (candidatos_data_prova, extrair_topicos, limpar_paginacao,
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


def test_fgv_perfil_vira_disciplina_quando_nao_tem_subcabecalho():
    """PERFIL 1 lista os tópicos direto, sem "DISCIPLINA:" no meio. Sem
    tratar o marcador de perfil, esses tópicos cairiam na disciplina
    anterior — em Legislação, que não tem nada a ver."""
    assert "Análise De Negócios De Ti" in _disciplinas(FGV)


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
