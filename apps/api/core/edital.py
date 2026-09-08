"""
Edital — extrai data da prova e conteúdo programático de um PDF de edital,
para `scheduler.meta()` usar dado real em vez de exigir digitar a data
na mão toda vez.

MELHOR ESFORÇO, NÃO CONTRATO. Layout de edital varia por banca — o que
segue foi medido contra três padrões reais, cada um com um fixture em
`tests/fixtures/`: disciplina numerada ("1. DIREITO PENAL:", PC-PR),
disciplina sem numeração ("LÍNGUA PORTUGUESA:", FGV/Dataprev) e item com
ponto ("1. Compreensão", AOCP/PC-BA). Por isso `ingerir()` devolve
os candidatos a data com pontuação, não só "a resposta" — mesmo espírito de
`diagnostico.py`: reportar para o operador conferir, não decidir calado.

O PIPELINE, e cada etapa existe por um defeito medido (ver o comentário de
cada uma): limpar mobília de página -> recortar o conteúdo programático ->
achar cabeçalhos NO TEXTO CRU (a quebra de linha é o sinal) -> normalizar
só o corpo de cada bloco -> contar as folhas numeradas.

TRÊS APROXIMAÇÕES DECLARADAS, não escondidas:

1. Sem separação por CARGO, e no edital da Dataprev isso deixou de ser
   detalhe: são TREZE perfis (Desenvolvimento de Software, Advocacia,
   Contabilidade, Engenharia...), cada um com seu conteúdo específico, e
   todos entram na mesma mesa. Quem vai prestar UM perfil recebe um plano
   de estudo com o conteúdo dos outros doze junto. O Módulo I
   (Português/Inglês/RLM) é comum a todos e esse está certo; o Módulo II
   deveria ser filtrado pelo perfil escolhido, e não é. Exigiria coluna
   `cargo` em `topico` e a pessoa dizendo qual perfil vai prestar — está
   em "Aberto" no CLAUDE.md.

2. Só FOLHA da árvore numerada vira tópico ("4" seguido de "4.1" é pai, e
   não conta). É o que db/007_edital.sql já dizia — "não modela hierarquia
   porque nada hoje precisa navegar a árvore, só contar folhas" — mas que
   a primeira implementação não fazia, contando pai e filho e inflando o
   denominador pela ALTURA da árvore.

3. "Cobertura por tópico" é estimada por DISCIPLINA, não por tópico
   individual. Não há vínculo direto questão→tópico no schema (exigiria
   marcar cada questão gerada com o tópico de origem). A aproximação:
   cobertura_pct da disciplina inteira (já existente em
   v_desempenho_disciplina) se aplica IGUALMENTE a todos os tópicos dela —
   assume dificuldade uniforme, o que não é verdade, mas é a melhor
   estimativa sem construir o vínculo fino agora.
"""
import re
from collections import Counter
from datetime import date
from pathlib import Path

from . import db, mesa as mesa_mod, questoes

VERSAO = "edital-v8"

MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5,
         "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
         "novembro": 11, "dezembro": 12}

# "no dia D de MÊS de AAAA" — distingue de citação legal ("Lei nº X, DE D
# de MÊS de AAAA"), que não tem a palavra "dia" antes do número.
RE_DATA_EVENTO = re.compile(
    r"\bdia\s+(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\s+de\s+(20\d{2})", re.I)

# DATA NUMÉRICA "d/m/aaaa" — como a CEBRASPE escreve no cronograma. O edital da
# PF não traz NENHUMA data em prosa: a aplicação das provas está numa tabela do
# Anexo I, "Aplicação das provas objetiva e discursiva 27/7/2025". Sem este
# padrão a tela dizia "Sem data de prova reconhecida" num edital que tem a data
# escrita — e sem data não há meta, não há prazo, não há ritmo necessário.
#
# Dia e mês com 1 OU 2 dígitos: o cronograma mistura "27/7/2025" e "13/01/2026"
# na mesma tabela. Exigir dois dígitos perderia metade das linhas.
RE_DATA_NUMERICA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")

# CABEÇALHO DE DISCIPLINA — nome em CAIXA ALTA seguido de ":", ANCORADO NO
# INÍCIO DA LINHA, com numeração opcional.
#
# A âncora de início de linha é a correção mais importante deste módulo, e
# custou um edital inteiro extraído errado pra ficar óbvia. A versão
# anterior rodava sobre o texto já normalizado (toda quebra de linha virada
# em espaço) e exigia "N. NOME:". Resultado no edital da FGV/Dataprev, cujos
# cabeçalhos NÃO são numerados ("LÍNGUA PORTUGUESA:"):
#
#   - nenhuma disciplina real foi encontrada;
#   - "PLATAFORMA BÁSICA" entrou porque a frase anterior terminava em
#     "...Framework version 1.1." — o "1." de um número de VERSÃO virou o
#     número da disciplina;
#   - "ECF" e "IOF" entraram porque "3. ECF:" e "12. IOF:" são itens no MEIO
#     de um parágrafo de Contabilidade Tributária.
#
# Começar a linha é o único sinal que separa cabeçalho de item numerado no
# meio de frase, e era exatamente o sinal que `_normalizar()` destruía antes
# da regex rodar. Por isso a detecção de cabeçalho acontece sobre o texto
# CRU, e só o corpo de cada bloco é normalizado depois.
# SEGUNDA ÂNCORA (a alternativa com `{2,}`): o cabeçalho pode não começar a
# linha. Medido no PC-PR, cujo texto extraído traz
# "DELEGADO  DE  POLÍCIA   1.  DIREITO  PENAL:" — cargo e primeira disciplina
# na MESMA linha. Exigir início de linha perdia justamente Direito Penal, que
# vale 20 das 100 questões da prova de Delegado.
#
# Aqui a numeração é OBRIGATÓRIA, e é ela que segura o portão. O falso positivo
# que a âncora de linha existe pra evitar ("...version 1.1. PLATAFORMA
# BÁSICA:", "3. ECF:" no meio de um parágrafo de Contabilidade Tributária) vive
# no meio de FRASE, separado por UM espaço; cabeçalho colado pela extração vem
# depois do espaçamento largo da linha justificada, 2+ espaços. Travado nos
# fixtures da FGV: `Ecf`, `Iof`, `Lalur` e `1988` continuam fora.
# DUAS ADIÇÕES, do edital 04/2026 da TRANSPETRO (Cesgranrio), cada uma
# consertando conteúdo que SUMIA.
#
# E uma TERCEIRA que foi TENTADA E REVERTIDA, registrada porque parecia obviamente
# certa: deixar o nome do cabeçalho ATRAVESSAR UMA QUEBRA DE LINHA. O pypdf
# devolve "ADMINISTRAÇÃO\nMERCADOLÓGICA:" e "LICITAÇÕES E\nCONTRATAÇÕES:", e como
# as classes de caractere não cruzam `\n`, casava só o RABO — as disciplinas
# viravam "Mercadológica" e "Contratações", e nome truncado nunca casa no
# `mesa.filtro`. Medido, a permissão fez DUAS coisas piores que o problema:
#   · engoliu a seção no nome — "CONHECIMENTOS BÁSICOS\nLÍNGUA PORTUGUESA:"
#     virou a disciplina "Conhecimentos Básicos Língua Portuguesa";
#   · matou um CARGO: o nome esticado passa do começo da linha seguinte, e o
#     desempate de `_marcas` (que descarta marca iniciada antes do fim da
#     anterior) descartava a marca de ÊNFASE. Cinco ênfases viraram quatro.
# E não consertou nada mensurável: com a adição 2 abaixo, os cabeçalhos
# quebrados são achados pelo rótulo em linha, com o nome inteiro. Reverter foi
# o que devolveu o quinto cargo.
#
# 1. RÓTULO NO MEIO DA LINHA SEM NÚMERO. A Cesgranrio escreve as matérias como
#    rótulo em caixa alta dentro do parágrafo, sem numerar: "...(Supply Chain
#    Management). CONTRATAÇÃO: Artigos 28 ao 91...". A âncora é PONTUAÇÃO QUE
#    FECHA ORAÇÃO seguida de um espaço — o mesmo julgamento de `RE_SUBITEM`
#    ("o item precisa abrir uma oração"), aplicado ao rótulo. Sem ela, a ênfase
#    de Administração saía com 3 disciplinas onde o edital lista 14.
#
#    A PONTUAÇÃO PRECISA VIR DEPOIS DE LETRA MINÚSCULA OU FECHA-PARÊNTESE, e
#    essa exigência não é enfeite: sem ela o ponto do PRÓPRIO NÚMERO servia de
#    âncora e o bug documentado da FGV voltava inteiro — "...Contabilidade
#    Tributária. 3. ECF:" e "12. IOF:" viravam disciplinas "Ecf" e "Iof" outra
#    vez. Peguei rodando `test_edital.py`, que existe exatamente pra isso.
#    Com a exigência, o "." de "3." é precedido por dígito e não ancora nada;
#    o "." de "Management)." é precedido por ")" e ancora.
#
# 2. Numeral ROMANO como prefixo ("I- MATEMÁTICA:", "VIII- PROCESSAMENTO DE
#    LINGUAGEM NATURAL (NLP):"), que é como a ênfase de Ciência de Dados
#    numera. Antes o romano entrava no NOME e a disciplina virava
#    "I- Matemática".
RE_DISCIPLINA = re.compile(
    r"(?:^[ \t]*(?:\d{1,2}[.)]\s+|[IVXL]{1,5}[.)\-–][ \t]*)?"
    r"|(?<=\S)[ \t]{2,}\d{1,2}[.)][ \t]+"
    r"|(?<=[a-zà-ÿ)\]][.;)])[ \t](?:[IVXL]{1,5}[.)\-–][ \t]*)?)"
    r"([A-ZÀ-Ü][A-ZÀ-Ü0-9 \t\-/&(),]{2,70}?)[ \t]*:",
    re.MULTILINE)

# MARCADOR DE CARGO. Três bancas escrevem diferente e as três cabem aqui:
# "PERFIL 3: DESENVOLVIMENTO DE SOFTWARE" (FGV, 13 perfis no mesmo edital),
# "CARGO: DELEGADO DE POLÍCIA CIVIL" (AOCP, 3 cargos) e "ÊNFASE 8: CIÊNCIA DE
# DADOS" (Cesgranrio — o edital 04/2026 da TRANSPETRO tem 33 ênfases). É o
# marcador que separa "o que todo mundo estuda" do "o que ESTE cargo estuda" —
# sem ele os 13 perfis viravam 52 disciplinas numa mesa só, e as 33 ênfases da
# TRANSPETRO viravam lixo: medido antes do conserto, a tela mostrava
# "4 disciplinas · 67 tópicos", sendo duas delas "I- Matemática" e "Dados" —
# que são SUBSEÇÕES de dentro da ênfase de Ciência de Dados, não matérias.
#
# ÊNFASE entra sem hesitação porque é o caso que este parser existe pra
# atender: o edital DIZ onde o cargo começa, com marcador literal e numerado.
# É o oposto do cabeçalho nu que fez `RE_CARGO_NU` ser revertida logo abaixo.
#
# `[ÊE]NFASE` com as duas grafias porque o pypdf às vezes devolve a maiúscula
# acentuada sem o acento, e a alternativa (normalizar o texto antes) destruiria
# a quebra de linha, que é o dado de que `RE_DISCIPLINA` depende.
# `[ \t\d]{0,5}` e não `\s*\d{0,2}\s*` porque o pypdf QUEBRA O NÚMERO deste
# edital: "ÊNFASE 1 0 :", "ÊNFASE 1 4:", "ÊNFASE 2 2:" — o dígito das dezenas
# vem separado do das unidades por espaço. Com o padrão antigo, 12 das 33
# ênfases casavam e 21 sumiam, e o efeito era o pior possível: os tópicos de
# uma ênfase que não casou caem na ênfase ANTERIOR, sem nada denunciar na
# contagem total. Mesma classe do defeito da mobília de página no FGV.
RE_CARGO = re.compile(
    r"^[ \t]*(?:\d+(?:\.\d+)*[ \t]*[-–—][ \t]*)?"
    r"(?:CARGO|PERFIL|[ÊE]NFASE)[ \t\d]{0,5}[:\-–—][ \t]*(.+?)[ \t]*:?[ \t]*$",
    re.MULTILINE | re.IGNORECASE)

# NÃO EXISTE `RE_CARGO_NU`, e a ausência é decisão — foi tentada e revertida.
# A ideia era pegar o cargo escrito como CABEÇALHO NU (a linha em maiúsculas
# sem "CARGO:"/"PERFIL N:" na frente, como no PC-PR: "DELEGADO DE POLÍCIA").
# Medida contra os PDFs REAIS, a regra achou:
#   · Jateí/MS: 16 "cargos" onde existem 3 — incluindo "PÁGINA 26 DE 32"
#     (mobília de página), "NÍVEL SUPERIOR" (seção) e "LÍNGUA PORTUGUESA"
#     (DISCIPLINA);
#   · PC-PR: 3 cargos chamados "Econômica", "Cibernética", "Cibernética" —
#     pedaços de cabeçalho de disciplina que o PDF quebra em duas linhas.
# E fez um estrago a mais, silencioso: o Jateí ANTES caía no fallback de LLM
# (os cabeçalhos dele não têm ":", então o parser achava zero e o modelo lia).
# Produzir lixo SUPRIMIU o fallback — o parser passou a "achar" alguma coisa.
#
# A lição não é "a regex estava mal calibrada", é que o problema não é de
# casamento de padrão: distinguir cargo de seção, de disciplina e de rodapé
# num layout nunca visto é LEITURA. Quatro editais, quatro layouts, e cada
# regex nova quebrava o edital seguinte. Por isso a decisão passou a ser
# "o parser agrupa só quando o edital DIZ onde o cargo começa; quando não
# diz, quem lê é o modelo" — ver `estrutura_com_fallback`.

# Linhas que são ESTRUTURA do documento, não matéria de estudo.
RE_ESTRUTURA = re.compile(r"^(M[OÓ]DULO|ANEXO|CARGO|PERFIL|[ÊE]NFASE)\b", re.IGNORECASE)

# O conteúdo programático costuma viver num anexo próprio. Recortar antes de
# procurar disciplina evita que o CORPO do edital (regras de inscrição, que
# são centenas de itens numerados "4.5.1", "10.13.6") entre como tópico de
# estudo — foi assim que uma disciplina fantasma acumulou 257 "tópicos".
# Singular E plural: a FGV escreve "ANEXO I – CONTEÚDO PROGRAMÁTICO", o
# AOCP escreve "ANEXO I – DOS CONTEÚDOS PROGRAMÁTICOS".
# "OBJETOS DE AVALIAÇÃO" é como a CEBRASPE chama a mesma seção — o edital da
# PF (131 páginas) tem "23 DOS OBJETOS DE AVALIAÇÃO (HABILIDADES E
# CONHECIMENTOS)" e a palavra "programático" não aparece NENHUMA vez nele.
# Sem esta alternativa o recorte não achava marcador e o parser varria o
# documento inteiro: 441.052 caracteres em vez de ~40.000, e aí as tabelas de
# vagas viravam marcador de cargo ("Perito Criminal Federal – Área 1:
# Contábil-Financeira 54 6 54" é uma LINHA DE TABELA, não um cabeçalho).
RE_INICIO_CONTEUDO = re.compile(
    r"\b(?:CONTE[ÚU]DOS?\s+PROGRAM[ÁA]TICOS?|OBJETOS?\s+DE\s+AVALIA[ÇC][ÃA]O)\b",
    re.IGNORECASE)
RE_ANEXO = re.compile(r"^[ \t]*ANEXO\s+[IVXLC]+\b", re.MULTILINE | re.IGNORECASE)

# "1", "1.", "1.1", "1.1.1" etc. seguido de texto iniciando em maiúscula.
#
# TRÊS EXIGÊNCIAS, cada uma de um edital real que quebrou:
#
# 1. UM NÍVEL TAMBÉM CONTA ({0,3}, não {1,3}). Exigir dois níveis fazia
#    disciplina inteira DESAPARECER quando o edital numera plano ("REDES DE
#    COMPUTADORES: 1 Conceitos... 2 Elementos..." — nenhum "N.N", nenhum
#    tópico, disciplina some da lista). Sumir é pior que contar de menos.
#
# 2. O PONTO DEPOIS DO NÚMERO É OPCIONAL (`\.?`). A FGV escreve "1
#    Compreensão"; o AOCP escreve "1. Compreensão". Sem isso o edital
#    inteiro da PC-BA devolvia ZERO tópico — o `\s+` batia no ponto e
#    falhava em todo item do documento.
#
# 3. O NÚMERO PRECISA ABRIR UMA ORAÇÃO: início do bloco, ou logo depois de
#    pontuação. É o que separa item de número solto no meio de frase.
#    Sem essa âncora, "...Constituição de 1988. A Constituição do Estado"
#    viraria um tópico chamado "1988", porque tem número, ponto, espaço e
#    maiúscula — exatamente a forma de um item.
RE_SUBITEM = re.compile(
    r"(?:^|(?<=[.,;:)\]]\s))(\d+(?:\.\d+){0,3})\.?\s+(?=[A-ZÀ-Ü])")


def _normalizar(texto: str) -> str:
    """PDF extraído de docx costuma vir com espaço/quebra de linha entre
    quase toda palavra — colapsar em espaço simples antes de qualquer regex
    que dependa de frase contígua."""
    return re.sub(r"\s+", " ", texto)


def candidatos_data_prova(texto: str, janela: int = 250) -> list[dict]:
    """
    Lista de datas candidatas a "dia da prova", ordenadas por pontuação de
    proximidade a "prova objetiva"/"realizad*". Devolve TODOS os
    candidatos, não decide sozinho qual é o certo — layout varia por
    banca, e a primeira posição pode estar errada num edital diferente
    deste que serviu de referência.
    """
    flat = _normalizar(texto)
    candidatos = []
    fim_anterior = 0
    # As duas formas entram na MESMA lista e competem pela mesma pontuação de
    # contexto: o edital pode ter as duas (prosa no corpo, tabela no anexo) e
    # quem decide é a proximidade de "prova objetiva", não o formato.
    achados = sorted(
        [(m, "prosa") for m in RE_DATA_EVENTO.finditer(flat)]
        + [(m, "num") for m in RE_DATA_NUMERICA.finditer(flat)],
        key=lambda x: x[0].start())
    for m, forma in achados:
        # A janela nunca cruza o candidato anterior — sem isso, duas datas
        # próximas (comum: "Prova Objetiva dia X... Prova Discursiva dia Y"
        # em sequência) "emprestam" pontuação uma da outra, e a segunda
        # data rouba o crédito de "prova objetiva" que pertence à primeira.
        ini = max(0, m.start() - janela, fim_anterior)
        # Data NUMÉRICA não olha pra frente. Em tabela de cronograma a linha é
        # "ATIVIDADE  DATA", então o que vem depois da data é a atividade da
        # linha SEGUINTE — e a janela roubava o crédito dela: "…locais de
        # provas 14/7/2025 Aplicação da prova objetiva…" fazia 14/7 empatar com
        # 27/7, que é a data real da prova, e o empate era decidido por ordem
        # no documento. Em prosa o "depois" ainda serve ("dia 11 de outubro de
        # 2026, quando serão aplicadas as provas").
        contexto = flat[ini:m.start() + (0 if forma == "num" else 40)]
        baixo = contexto.lower()
        # "Aplicação da(s) prova(s)" é como a tabela de cronograma nomeia a linha
        # que importa, e vale MAIS que "prova objetiva" solta na janela: 5
        # contra 3. Não é calibragem de gosto — é o desempate de um erro medido
        # no edital da TRANSPETRO, que a tela mostrava como "Prova em
        # 2026-12-01" quando a prova é 29/11/2026.
        #
        # O que acontecia: 01/12 é o fim do prazo de RECURSO contra o gabarito, e
        # o título da seção ("9.1. DA REVISÃO DA NOTA DA PROVA OBJETIVA") cai
        # dentro da janela de 250 caracteres dela. Empate em 3 a 3 com a data
        # real, e empate se resolve pela ordem no documento — o item 9.1 está na
        # página 32, o cronograma na 79. A data errada ganhava por chegar antes.
        #
        # E as palavras de RECURSO subtraem, que é a outra metade do conserto:
        # recurso, gabarito e revisão marcam PRAZO SOBRE a prova, não a prova.
        # Penalidade e não descarte — um cronograma pode nomear a linha da prova
        # perto da linha do gabarito, e descartar perderia a data certa.
        pontos = (baixo.count("prova objetiva") * 3
                  + baixo.count("provas objetivas") * 3
                  + baixo.count("realizad")
                  + baixo.count("aplicação das provas") * 5
                  + baixo.count("aplicação da prova") * 5
                  - baixo.count("recurso") * 3
                  - baixo.count("gabarito") * 2
                  - baixo.count("revisão") * 2)
        fim_anterior = m.end()
        try:
            mes = int(m.group(2)) if forma == "num" else MESES[m.group(2).lower()]
            d = date(int(m.group(3)), mes, int(m.group(1)))
        except (ValueError, KeyError):
            continue
        candidatos.append({"data": d, "pontuacao": pontos,
                           "contexto": contexto[-140:].strip()})
    candidatos.sort(key=lambda c: -c["pontuacao"])
    return candidatos


RE_SO_NUMERO = re.compile(r"^\s*\d{1,4}\s*$")


def limpar_paginacao(texto: str) -> str:
    """
    Tira número de página solto e cabeçalho/rodapé repetido em toda página.

    NÃO é cosmético — é o que decide se uma disciplina existe. O PDF entrega
    cada página começando por "DATAPREV | CONCURSO PÚBLICO 2026" e o número
    da página numa linha só dela. Uma disciplina que calha de abrir no topo
    de uma página fica precedida por essa linha numérica, e
    `_continuacao_de_paragrafo()` a descarta achando que é frase cortada no
    meio. Medido no edital da Dataprev: com a mobília, TRÊS disciplinas
    reais somem e os tópicos delas migram pra disciplina anterior — o pior
    tipo de erro, porque o total continua parecendo certo.

    Rodapé é detectado por repetição (linha curta que se repete muitas
    vezes), não por conteúdo: o texto do rodapé muda a cada banca. O limite
    de tamanho e o "não termina em dois-pontos" protegem cabeçalho de
    disciplina que se repete entre perfis ("BANCO DE DADOS: 1 Modelagem...")
    de ser confundido com rodapé.
    """
    # MOBÍLIA TEM DE TER MAIS DE UMA PALAVRA, e isto não é refinamento: sem a
    # regra, um PDF que extrai UMA PALAVRA POR LINHA faz o filtro comer o edital.
    #
    # Medido no `Edital PC-PR 2026.pdf` (pypdf devolve "Histórico\n \nimportância
    # \n \npara\n \no\n \nDireito."): das 245 linhas que a regra antiga
    # classificava como mobília, 245 eram de uma palavra só — "de" (360x), "e"
    # (343x), e também CONTEÚDO: "Lei" (93x), "Crimes" (47x), "Direitos" (43x),
    # "Polícia" (27x). Nenhum cabeçalho ou rodapé de verdade no meio.
    #
    # O estrago aparecia lá na frente, disfarçado: o tópico "8.1.2 Histórico e
    # importância para o Direito" virava "8.1.2 Histórico importância Direito", e
    # o 8.4.1 sumia inteiro. Total de tópicos continuava plausível — o pior
    # formato de erro, o mesmo que o docstring acima já descreve pra disciplina.
    #
    # Rodapé real é multipalavra ("Página 3 de 106", "PODER JUDICIÁRIO"); número
    # solto já sai por `RE_SO_NUMERO`. Exigir duas palavras não afrouxa nada que
    # a regra pegava antes e devolve o texto que ela não devia ter tocado.
    linhas = texto.splitlines()
    repetidas = Counter(l.strip() for l in linhas if l.strip())
    mobilia = {t for t, n in repetidas.items()
               if n >= 4 and len(t) <= 60 and not t.endswith(":")
               and len(t.split()) > 1}
    return "\n".join(l for l in linhas
                     if not RE_SO_NUMERO.match(l) and l.strip() not in mobilia)


def recortar_conteudo_programatico(texto: str) -> tuple[str, bool]:
    """
    Devolve (trecho, achou). Sem o marcador, devolve o texto inteiro e
    `False` — cabe a quem chamou avisar que a extração rodou sobre o edital
    todo, que é bem mais ruidoso. Reportar, não decidir calado.

    A ÚLTIMA menção, não a primeira. O edital cita o próprio anexo várias
    vezes antes de chegar nele ("Integram o presente Edital: Anexo I -
    Conteúdos Programáticos", "conforme conteúdo programático constante do
    Anexo I", "salvo se listadas nos conteúdos programáticos..."). Pegar a
    primeira recortava um pedaço das REGRAS de inscrição e o anexo de
    verdade nunca era lido — foi assim que o edital da PC-BA devolveu zero
    tópico. Referência cruzada vem antes; o anexo em si é o último.
    """
    ultima = None
    for m in RE_INICIO_CONTEUDO.finditer(texto):
        ultima = m
    if not ultima:
        return texto, False
    seguinte = RE_ANEXO.search(texto, ultima.end())
    return texto[ultima.end():seguinte.start() if seguinte else len(texto)], True


def _continuacao_de_paragrafo(texto: str, inicio: int) -> bool:
    """
    Início de linha NÃO garante cabeçalho: o PDF quebra linha no meio da
    frase, e uma linha pode começar com uma palavra em caixa alta seguida
    de ":" sem ser título nenhum. Caso real: "...2.3 Formas de pagamento;
    2.4 / LALUR: forma de escrituração fiscal" — "LALUR:" abre a linha, mas
    é continuação do item 2.4 da linha anterior.

    O sinal é o que vem ANTES: parágrafo encerrado termina em pontuação
    ("...formalidade."); frase cortada no meio termina pendurada — em
    número, vírgula ou ponto e vírgula, como o "2.4" acima.
    """
    NUMERADO = re.compile(r"[ \t]*\d{1,2}[.)][ \t]")
    # NUMERAÇÃO PRÓPRIA vence o filtro, e isso é o que separa os dois casos.
    # "LALUR:" — o falso positivo que motivou este guarda — é palavra NUA: não
    # tem número, então continua sendo barrado. "4. DIREITO CONSTITUCIONAL:"
    # traz o próprio número e é cabeçalho, ainda que o texto anterior termine
    # pendurado.
    #
    # Medido no PC-PR: o bloco do Delegado perdia DUAS das oito disciplinas por
    # aqui — a 4 porque o texto antes termina em "3.19" (dígito: o número do
    # último subitem, que a extração jogou adiante) e a 7 porque termina em
    # "12.037/2009);" (ponto e vírgula, de uma citação de lei). Num edital cuja
    # extração espalha a pontuação assim, "terminou em ; ou dígito" é frequente
    # e legítimo — o sinal sozinho não distingue mais nada.
    if NUMERADO.match(texto, inicio):
        return False
    anterior = texto[:inicio].rstrip()
    return bool(anterior) and anterior[-1] in "0123456789,;–-"


def _marcas(texto: str) -> list[tuple[int, int, str, str]]:
    """(início, fim, tipo, nome) de cada marcador, em ordem de posição.
    tipo ∈ {"cargo", "disciplina"}."""
    marcas = [(m.start(), m.end(), "cargo", m.group(1)) for m in RE_CARGO.finditer(texto)]
    for m in RE_DISCIPLINA.finditer(texto):
        if RE_ESTRUTURA.match(m.group(1).strip()):
            continue
        if _continuacao_de_paragrafo(texto, m.start()):
            continue
        marcas.append((m.start(), m.end(), "disciplina", m.group(1)))
    marcas.sort()
    # A linha do cargo casa nas duas regexes; fica a primeira (a do cargo,
    # que captura o nome em vez do literal "PERFIL N").
    limpo: list[tuple[int, int, str, str]] = []
    for marca in marcas:
        if limpo and marca[0] < limpo[-1][1]:
            continue
        limpo.append(marca)
    return limpo


def _nome(bruto: str) -> str:
    # `.` e `-` soltos na ponta vêm da extração do PDF: o título promovido de
    # item numerado termina no ponto do próprio item ("Fundamentos da
    # computação."), e o hífen às vezes aparece separado ("Perícia Médico
    # -Legal"). Nome de disciplina é o que a mesa usa pra RECORTAR (`mesa.filtro`
    # casa por ILIKE dos dois lados), então pontuação sobrando estraga o casamento.
    limpo = re.sub(r"\s+([-–])", r"\1", re.sub(r"\s+", " ", bruto))
    return limpo.strip(" :.;,").title()


# Tópico mais curto que isso é ruído de pontuação ("etc", "e"); mais longo é
# parágrafo inteiro, e parágrafo não é unidade de estudo.
MIN_TOPICO_SOLTO = 12
MAX_TOPICO_SOLTO = 320
MIN_PARTES_SOLTAS = 3


def _topicos_por_pontuacao(bruto: str) -> list[str]:
    """
    Tópicos de um bloco SEM NUMERAÇÃO NENHUMA — a última tentativa, e só
    depois de a numerada falhar.

    A Cesgranrio escreve várias ênfases em prosa corrida, separando as matérias
    por dois-pontos e os tópicos por ponto-e-vírgula ou ponto:

      "ADMINISTRAÇÃO FINANCEIRA E ORÇAMENTÁRIA: Matemática Financeira, Valor do
       Dinheiro no Tempo, Risco X Retorno, Análise de Investimentos, ...
       ADMINISTRAÇÃO DA PRODUÇÃO E COMPRAS: Estratégia de Suprimento ..."

    Sem isso, `RE_SUBITEM` não acha nada, `_topicos_do_bloco` devolve lista
    vazia e a disciplina é DESCARTADA por `extrair_estrutura` (que só aceita
    disciplina com tópico). Medido: as ênfases de Administração e de Advocacia
    do edital da TRANSPETRO — as duas maiores em conteúdo — saíam com ZERO
    disciplina e zero tópico, e nada na contagem denunciava, porque as outras 31
    ênfases enchiam o número.

    Só roda quando NÃO há item numerado, e é isso que a torna segura de
    adicionar: FGV e AOCP numeram tudo, então elas nunca chegam aqui — o
    fallback não pode regredir o que já funciona, só cobrir o que sumia.

    Ponto-e-vírgula tem precedência sobre ponto quando o bloco usa os dois: é o
    separador que a banca escolheu de propósito (a ÊNFASE 17 é uma lista de 20
    matérias separadas por ";" e nada mais), e cortar por ponto ali quebraria
    abreviação no meio.
    """
    bloco = _normalizar(bruto).strip()
    if not bloco:
        return []
    if bloco.count(";") >= MIN_PARTES_SOLTAS - 1:
        partes = re.split(r";\s*", bloco)
    else:
        # Só ponto que FECHA oração (minúscula, dígito ou fecha-parêntese antes)
        # e é seguido de espaço: evita cortar "Lei nº 13.303" e "art. 28".
        partes = re.split(r"(?<=[a-zà-ÿ0-9)\]])\.\s+", bloco)
    topicos = [p.strip(" .;,") for p in partes]
    topicos = [t for t in topicos if MIN_TOPICO_SOLTO <= len(t) <= MAX_TOPICO_SOLTO]
    # Uma parte só não é lista: é um fragmento de frase, e promovê-lo a
    # "disciplina com um tópico" produziria matéria que não existe.
    return topicos if len(topicos) >= MIN_PARTES_SOLTAS else []


def _topicos_do_bloco(bruto: str) -> list[str]:
    # lstrip: o primeiro item do bloco precisa encostar no início da string
    # pra RE_SUBITEM aceitá-lo pela alternativa `^` (ele é o único que não
    # vem depois de pontuação — vem depois do cabeçalho).
    bloco = _normalizar(bruto).lstrip()
    subitens = list(RE_SUBITEM.finditer(bloco))
    if not subitens:
        return _topicos_por_pontuacao(bruto)
    topicos = []
    for j, s in enumerate(subitens):
        fim = subitens[j + 1].start() if j + 1 < len(subitens) else len(bloco)
        # Só FOLHA vira tópico: "4" seguido de "4.1" é o pai do próximo, e
        # contar os dois inflaria a mesma matéria duas vezes — o denominador
        # de "quantos tópicos existem" tem que ser o que se estuda, não a
        # árvore inteira.
        if j + 1 < len(subitens) and subitens[j + 1].group(1).startswith(s.group(1) + "."):
            continue
        texto = bloco[s.start():fim].strip()
        if texto:
            topicos.append(texto)
    return topicos


def _disciplinas_do_bloco_plano(bruto: str) -> list[dict]:
    """
    Bloco de cargo SEM subcabeçalho nomeado: os itens de PRIMEIRO NÍVEL viram
    as disciplinas, e as folhas de cada um viram os tópicos dele.

    Medido no edital da PF: cada uma das 13 áreas de Perito Criminal é uma
    lista numerada plana — "1 Fundamentos da computação. 1.1 Organização e
    arquitetura de computadores. ... 2 Bancos de dados. 2.1 ...". Não há
    cabeçalho de matéria pra `RE_DISCIPLINA` achar, então o cargo saía com UMA
    disciplina chamada "Perito Criminal Federal – Área 3: Informática Forense"
    e 104 tópicos dentro. Fiel ao documento e inútil pro estudo: `mesa.filtro`
    recorta por NOME de disciplina, e esse nome não casa com nada do acervo.

    Os itens de primeiro nível são as matérias — é assim que o candidato fala
    delas ("estou em bancos de dados"). Promover é o mesmo julgamento que já
    está em `extrair_estrutura` pro PERFIL 1 da FGV, um nível abaixo.

    Item de primeiro nível SEM filho vira uma disciplina com ele mesmo como
    único tópico, em vez de sumir: perder conteúdo é pior que uma disciplina
    de um tópico só.
    """
    bloco = _normalizar(bruto).lstrip()
    subitens = list(RE_SUBITEM.finditer(bloco))
    grupos: list[dict] = []
    for j, s in enumerate(subitens):
        fim = subitens[j + 1].start() if j + 1 < len(subitens) else len(bloco)
        corpo_item = bloco[s.end():fim].strip()
        if "." not in s.group(1):
            # O título é o texto até o primeiro ponto — depois dele já começa o
            # conteúdo ("Fundamentos da computação. 1.1 Organização...").
            titulo = re.split(r"(?<=[a-zà-ÿ)])\.\s", corpo_item, maxsplit=1)[0]
            grupos.append({"disciplina": _nome(titulo[:90]),
                           "topicos": [], "proprio": bloco[s.start():fim].strip()})
        elif grupos:
            grupos[-1]["topicos"].append(bloco[s.start():fim].strip())

    for g in grupos:
        if not g["topicos"] and g["proprio"]:
            g["topicos"] = [g["proprio"]]
        g.pop("proprio")
    return [g for g in grupos if g["disciplina"] and g["topicos"]]


def _redistribuir_compartilhados(cargos: list[dict]) -> list[dict]:
    """
    Bloco cujo cabeçalho nomeia DOIS OU MAIS cargos vale pra cada um deles.

    O PC-PR 01/2026 tem três cargos e QUATRO cabeçalhos, porque um deles é
    "AGENTE DE POLÍCIA JUDICIÁRIA E PAPILOSCOPISTA POLICIAL" — os
    Conhecimentos Gerais que esses dois dividem (Português, RLM, Realidade do
    Paraná), e que o Delegado não estuda. Sem este passo o aluno via quatro
    opções onde existem três cargos, e escolher "Papiloscopista Policial"
    entregava um plano SEM Português — o edital cobra 25 questões dele.

    Não dá pra resolver isso jogando o bloco em `comuns`: comum é o que vale
    pra TODO MUNDO, e este não vale pro Delegado. A estrutura ("comuns + um
    cargo") não tem onde pendurar "comum a alguns", então a saída é
    distribuir: cada cargo nomeado recebe uma cópia, e o bloco guarda-chuva
    some da lista de escolhas.

    "CONTER O NOME" NÃO BASTA, e essa versão ingênua apagou 13 cargos de um
    edital real. No da PF os nomes curtos "Perito Criminal" e "Perito Criminal
    Federal" existem como marcador (vêm de linha de tabela de vagas cortada), e
    os dois são substring de "Perito Criminal Federal – Área 1:
    Contábil-FINANCEIRA". Com a regra "2+ nomes contidos", cada um dos treze
    peritos virava guarda-chuva e era REMOVIDO da escolha — o aluno via 4
    cargos onde o edital tem 17, e nenhum deles era perito.

    A regra certa é ENUMERAÇÃO, não continência: o cabeçalho guarda-chuva é
    feito só dos outros nomes colados por conector. Tirando os nomes contidos,
    "Agente de Polícia Judiciária E Papiloscopista Policial" deixa " E " —
    nada. "Perito Criminal Federal – Área 1: Contábil-Financeira" deixa
    "Área 1 Contábil Financeira", que é conteúdo próprio: é um cargo, não uma
    lista de cargos.
    """
    def e_enumeracao(nome: str, contidos: list[str]) -> bool:
        resto = nome
        for n in sorted(contidos, key=len, reverse=True):   # maior primeiro
            resto = resto.replace(n, " ")
        sobra = [w for w in re.sub(r"[^0-9A-Za-zÀ-ÿ]+", " ", resto).split()
                 if w.lower() not in {"e", "ou", "de", "do", "da", "dos", "das"}]
        return not sobra

    guarda_chuva = []
    proprios = []
    for c in cargos:
        alvos = [o for o in cargos if o is not c and o["nome"] in c["nome"]]
        umbrella = len(alvos) >= 2 and e_enumeracao(c["nome"], [o["nome"] for o in alvos])
        (guarda_chuva if umbrella else proprios).append((c, alvos))

    for bloco, alvos in guarda_chuva:
        for alvo in alvos:
            # Na frente: o compartilhado vem ANTES no edital, e a ordem das
            # disciplinas é a ordem em que a pessoa vai lê-las na curadoria.
            alvo["disciplinas"] = bloco["disciplinas"] + alvo["disciplinas"]
    return [c for c, _ in proprios]


def extrair_estrutura(texto: str) -> dict:
    """
    {"comuns": [{"disciplina", "topicos"}], "cargos": [{"nome", "disciplinas"}]}

    A REGRA DE AGRUPAMENTO É POSICIONAL, e os dois editais reais concordam
    com ela: o conteúdo programático abre com o que vale pra TODO MUNDO
    ("CONHECIMENTOS COMUNS PARA TODOS OS CARGOS" no AOCP, "MODULO I ...
    PARA TODOS OS CARGOS/PERFIS" na FGV) e só depois começam os blocos de
    cargo. Então: disciplina antes do primeiro marcador de cargo é comum;
    depois dele, pertence ao cargo aberto.

    Isso é o que faltava pra "1015 tópicos em 52 disciplinas" virar uma
    escolha em vez de uma soma — os 13 perfis da Dataprev estavam todos
    empilhados na mesma mesa.

    Perfil que lista tópicos direto, sem subcabeçalho de disciplina (o
    PERFIL 1 da FGV é assim), vira uma disciplina com o nome do próprio
    cargo: melhor um nome largo demais que os tópicos caírem no cargo
    anterior.
    """
    corpo, _ = recortar_conteudo_programatico(limpar_paginacao(texto))
    marcas = _marcas(corpo)
    comuns: list[dict] = []
    cargos: list[dict] = []
    atual: dict | None = None

    for i, (_, fim, tipo, bruto) in enumerate(marcas):
        # O teto no último bloco é rede de segurança pra quando o recorte do
        # conteúdo programático não encontrou marcador: sem ele, a última
        # disciplina engoliria o resto do documento inteiro.
        prox = marcas[i + 1][0] if i + 1 < len(marcas) else min(len(corpo), fim + 8000)
        topicos = _topicos_do_bloco(corpo[fim:prox])
        if tipo == "cargo":
            atual = {"nome": _nome(bruto), "disciplinas": []}
            cargos.append(atual)
            if topicos:
                # Bloco plano (sem subcabeçalho): os itens de primeiro nível
                # são as matérias. Só aceita a promoção se ela render MAIS de
                # uma — com uma só, o nome do cargo é a etiqueta mais honesta,
                # que é o comportamento antigo (PERFIL 1 da FGV).
                partes = _disciplinas_do_bloco_plano(corpo[fim:prox])
                atual["disciplinas"].extend(
                    partes if len(partes) > 1
                    else [{"disciplina": atual["nome"], "topicos": topicos}])
        elif topicos:
            (atual["disciplinas"] if atual else comuns).append(
                {"disciplina": _nome(bruto), "topicos": topicos})

    return {"comuns": comuns, "cargos": _redistribuir_compartilhados(cargos)}


def achatar(estrutura: dict, cargo: str | None = None) -> list[dict]:
    """
    Estrutura -> [{"disciplina", "ordem", "texto"}], que é a forma que
    `topico` guarda. `cargo=None` junta tudo (comportamento anterior à
    seleção de cargo); com cargo, junta comuns + só aquele cargo — é isso
    que a curadoria persiste.
    """
    grupos = list(estrutura["comuns"])
    for c in estrutura["cargos"]:
        if cargo is None or c["nome"] == cargo:
            grupos += c["disciplinas"]
    topicos: list[dict] = []
    for g in grupos:
        for t in g["topicos"]:
            topicos.append({"disciplina": g["disciplina"], "ordem": len(topicos), "texto": t})
    return topicos


def extrair_topicos(texto: str) -> list[dict]:
    """Todos os tópicos, de todos os cargos — a visão achatada de sempre.
    Quem quer escolher cargo usa `extrair_estrutura()` + `achatar()`."""
    return achatar(extrair_estrutura(texto))


# ------------------------------------------------------------ fallback LLM
_DISCIPLINA_SCHEMA = {
    "type": "object",
    "properties": {"disciplina": {"type": "string"},
                   "topicos": {"type": "array", "items": {"type": "string"}}},
    "required": ["disciplina", "topicos"],
}
ESQUEMA_ESTRUTURA = {
    "type": "object",
    "properties": {
        "comuns": {"type": "array", "items": _DISCIPLINA_SCHEMA},
        "cargos": {"type": "array", "items": {
            "type": "object",
            "properties": {"nome": {"type": "string"},
                           "disciplinas": {"type": "array", "items": _DISCIPLINA_SCHEMA}},
            "required": ["nome", "disciplinas"]}},
    },
    "required": ["comuns", "cargos"],
}

# Teto de texto mandado ao modelo. Edital inteiro estoura contexto e cota
# sem necessidade: o que interessa é o conteúdo programático, que o
# recorte já isolou.
#
# 60k e não 30k porque 30k CORTAVA edital real: o conteúdo programático do
# PC-PR tem 37.736 caracteres, e o bloco do Papiloscopista — o último —
# simplesmente não chegava ao modelo. Truncar entrada não dá erro, dá
# resposta incompleta, que é a falha mais difícil de ver.
MAX_CHARS_LLM = 60_000


# AGRUPAMENTO: o modelo diz DE QUEM é cada disciplina que o parser achou.
#
# TRÊS tentativas morreram aqui. Ficam registradas porque cada uma parecia a
# solução óbvia da anterior, e o custo de redescobrir isso é alto:
#
# 1ª — pedir ao modelo a estrutura inteira, nomes E tópicos. Medido no PC-PR:
#      246 tópicos = ~5.500 tokens de saída contra teto de 8.000; JSON cortado,
#      parse estourava, `except` devolvia o parser e a tela dizia "lido pela
#      estrutura do edital". Chamou, falhou, ninguém soube.
#
# 2ª — ÍNDICES do catálogo do parser (esta versão). Saída ~200 tokens, modelo
#      classifica certo, tópicos determinísticos.
#
# 3ª — o modelo NOMEIA os cabeçalhos e o código FATIA os tópicos entre eles,
#      pra não depender do recall do parser. Revertida: não existe âncora
#      confiável no texto que o pypdf devolve. Medido no PC-PR — a extração
#      PERDE PALAVRAS CURTAS em linha justificada (`ECONÔMICA\n \n \nESTADO\n
#      \n \nPARANÁ` não tem os dois "DO"; `CIBERNÉTICA\n \n \nCRIMES` perdeu o
#      "E"), então string exata não casa; com folga entre as palavras,
#      "DIREITO PENAL" casa em "2. DIREITO PROCESSUAL PENAL"; e âncora de
#      início de linha não vale porque o extrator junta cabeçalhos na mesma
#      linha ("CONHECIMENTOS GERAIS   1. LÍNGUA PORTUGUESA:").
#      Essa perda de palavra é também a origem das disciplinas chamadas
#      "Paraná" e "Digitais": são o rabo do título, o pedaço que sobrou.
#
# LIMITE CONHECIDO da versão que ficou: a qualidade tem teto no RECALL DO
# PARSER. No PC-PR ele entrega 24 dos 32 cabeçalhos reais — somem "1. DIREITO
# PENAL", "4. DIREITO CONSTITUCIONAL", "7. DIREITOS HUMANOS" e "LÍNGUA
# PORTUGUESA", e o Delegado aparece com 5 matérias onde tem 8. O modelo não
# pode devolver o que nunca viu. É por isso que a curadoria tem "Meu cargo não
# está aqui" e campo pra acrescentar matéria na mão: enquanto a leitura tem
# teto, o aluno precisa de um caminho que não dependa dela ter acertado.
ESQUEMA_AGRUPAMENTO = {
    "type": "object",
    "properties": {
        "comuns": {"type": "array", "items": {"type": "integer"}},
        "cargos": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "nome": {"type": "string"},
                "disciplinas": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"indice": {"type": "integer"}, "nome": {"type": "string"}},
                    "required": ["indice", "nome"]}},
            },
            "required": ["nome", "disciplinas"]}},
    },
    "required": ["comuns", "cargos"],
}


def _agrupar_com_llm(corpo: str, achadas: list[dict]) -> dict:
    """Recebe as disciplinas que o PARSER achou (em ordem de documento) e
    devolve a mesma estrutura de sempre, agora agrupada por cargo.

    Os tópicos nunca passam pelo modelo: saem daqui exatamente como o parser
    os leu. O modelo só responde "de quem é" e "como se chama de verdade" —
    e o `nome` importa porque o catálogo chega com títulos truncados pela
    extração do PDF ("Digitais", "Paraná")."""
    from . import llm

    catalogo = "\n".join(f"[{i}] {d['disciplina']}" for i, d in enumerate(achadas))
    sistema = (
        "Você lê o conteúdo programático de um edital de concurso público brasileiro.\n"
        "Recebe uma LISTA NUMERADA de cabeçalhos de disciplina já extraídos do documento, "
        "na ordem em que aparecem, e devolve a QUEM cada um pertence.\n\n"
        "Use SOMENTE os índices da lista — não invente disciplina, não descarte nenhuma.\n"
        "- `comuns`: índices das disciplinas cobradas de TODOS os candidatos.\n"
        "- `cargos`: um item por CARGO do edital, com os índices das disciplinas só dele.\n"
        "CARGO é o posto que a pessoa vai ocupar (\"Contador\", \"Papiloscopista Policial\"), "
        "nunca uma matéria, nunca uma seção (\"Conhecimentos Específicos\", \"Nível Superior\") "
        "e nunca mobília de página (\"Página 26 de 32\"). O cabeçalho do cargo pode vir sem a "
        "palavra \"cargo\": uma linha em maiúsculas sozinha, logo antes do conteúdo dele.\n"
        "Se um bloco vale para MAIS DE UM cargo, repita os índices em cada cargo citado.\n\n"
        "O campo `nome` de cada disciplina é o título COMPLETO como está no documento. "
        "A lista pode trazer o cabeçalho pela metade, porque a extração do PDF come palavras "
        "curtas e quebra título em duas linhas: \"Digitais\" é o fim de \"Tecnologia e Sistemas "
        "de Informação e de Comunicação, Segurança Cibernética e Crimes Digitais\", e "
        "\"Paraná\" é o fim de \"Realidade Étnica, Social, Histórica, Geográfica, Cultural, "
        "Política e Econômica do Estado do Paraná\". Devolva o título inteiro."
    )
    lido = llm.obter().gerar_json(
        f"CABEÇALHOS ENCONTRADOS:\n{catalogo}\n\nCONTEÚDO PROGRAMÁTICO:\n{corpo[:MAX_CHARS_LLM]}",
        sistema, max_tokens=4000, schema=ESQUEMA_AGRUPAMENTO)

    def por_indice(i, nome=None):
        # Índice fora da lista é resposta inválida, não dado — some em silêncio
        # em vez de derrubar a ingestão inteira por causa de um item.
        if not isinstance(i, int) or not 0 <= i < len(achadas):
            return None
        d = achadas[i]
        # Nome vazio cai no do parser: melhor título truncado que nenhum.
        return {"disciplina": (nome or "").strip() or d["disciplina"], "topicos": d["topicos"]}

    comuns = [x for x in (por_indice(i) for i in lido.get("comuns") or []) if x]
    cargos = []
    for c in lido.get("cargos") or []:
        ds = [x for x in (por_indice(d.get("indice"), d.get("nome"))
                          for d in c.get("disciplinas") or []) if x]
        if ds:
            cargos.append({"nome": c.get("nome") or "Cargo", "disciplinas": ds})
    return {"comuns": comuns, "cargos": _redistribuir_compartilhados(cargos)}


def estrutura_com_fallback(texto: str) -> tuple[dict, str]:
    """
    Devolve (estrutura, origem) com origem ∈ {"parser", "llm"}.

    A REGRA: o parser agrupa por cargo SÓ QUANDO O EDITAL DIZ onde o cargo
    começa ("CARGO: X", "PERFIL N: X" — `RE_CARGO`). Quando não diz, quem
    lê é o modelo.

    O gatilho ANTES era "o parser não achou disciplina nenhuma", e ele
    media a coisa errada. Achar disciplina não é sinal de ter entendido a
    estrutura: no PC-PR o parser achava 24 disciplinas e ZERO cargos, e
    entregava os três cargos somados — Biologia e Química (só do
    Papiloscopista) no plano de quem vai prestar Delegado. Como havia
    disciplina, o modelo nunca era chamado. O gatilho protegia a cota e
    deixava passar exatamente o erro que mais custa ao aluno.

    Tentei fechar esse buraco com mais regex (cabeçalho nu em maiúsculas) e
    o resultado está documentado lá em cima, junto de `RE_CARGO`: 16 cargos
    falsos no Jateí, nomes truncados no PC-PR, e o fallback de LLM
    SUPRIMIDO porque o parser passou a "achar" lixo. Quatro editais, quatro
    layouts — separar cargo de seção, de disciplina e de rodapé num layout
    nunca visto é leitura, não casamento de padrão. É por isso que a régua
    agora é "o edital declarou o cargo?" e não "sobrou alguma coisa?".

    O parser continua primeiro e continua barato: quando o marcador existe
    ele resolve em milissegundos, sem cota, de forma determinística e
    testável (FGV e AOCP, travados em fixture). O modelo entra UMA vez por
    edital enviado — não por questão, não por sessão —, e o que ele devolve
    ainda passa pela curadoria antes de virar agendamento de revisão.

    Custo aceito de propósito: concurso de cargo único, que o parser
    resolveria sozinho, também gasta uma chamada. É o preço de não
    conseguir distinguir "tem um cargo só" de "tem vários escritos de um
    jeito que eu não reconheço" — e essa distinção é justamente a que exige
    ler o documento.

    DOIS CAMINHOS quando o modelo entra, e a diferença é quanto o parser já
    conseguiu ler:
      · achou as disciplinas (PC-PR: 24, com 246 tópicos) — falta saber DE
        QUEM são. `_agrupar_com_llm` pede só isso: índices. Os tópicos saem
        do parser, sem passar pelo modelo.
      · não achou nada (Jateí: os cabeçalhos não têm ":") — aí não há o que
        agrupar, e o modelo extrai o conteúdo inteiro.

    Falha do LLM não derruba a ingestão — devolve o que o parser tinha, mas
    com origem `parser_apos_falha`, não `parser`. A diferença importa na
    tela: "lido pela estrutura do edital" e "o modelo falhou, isto aqui é a
    leitura mecânica" pedem reações opostas do aluno (seguir em frente vs.
    tentar de novo), e antes as duas apareciam iguais. Falhar caladamente
    entregando o resultado PIOR é o pior dos dois mundos.
    """
    estrutura = extrair_estrutura(texto)
    if estrutura["cargos"]:
        return estrutura, "parser"

    from . import llm
    corpo, _ = recortar_conteudo_programatico(limpar_paginacao(texto))

    # `comuns` não-vazio significa que o edital tem ITEM NUMERADO — é isso que
    # o parser sabe achar, e é isso que permite fatiar os tópicos daqui em vez
    # de pedi-los ao modelo. Num edital de parágrafo corrido (Jateí) não há o
    # que fatiar, e a extração inteira volta a ser do modelo.
    if estrutura["comuns"]:
        try:
            agrupada = _agrupar_com_llm(corpo, estrutura["comuns"])
            # Modelo que não achou cabeçalho nenhum é resposta inútil, não
            # dado: melhor a lista somada do parser, que ao menos tem conteúdo.
            if agrupada["comuns"] or agrupada["cargos"]:
                return agrupada, "llm"
            return estrutura, "parser_apos_falha"
        except (llm.ErroLLM, ValueError, KeyError, TypeError, AttributeError):
            return estrutura, "parser_apos_falha"

    sistema = (
        "Você extrai o conteúdo programático de editais de concurso público brasileiros. "
        "Devolva SOMENTE o que está escrito no texto — nunca invente disciplina nem tópico, "
        "e nunca resuma: cada item numerado do edital vira um tópico. "
        "Disciplinas cobradas de TODOS os candidatos vão em `comuns`; as específicas de cada "
        "cargo/perfil vão dentro do cargo correspondente. Se o edital tem um cargo só, "
        "`cargos` pode ter um item só; se não separa por cargo, deixe `cargos` vazio.\n\n"
        # As quatro instruções abaixo não são genéricas: cada uma nomeia um
        # erro que uma tentativa de regex cometeu num edital REAL. Ficam
        # explícitas porque este caminho existe justamente para os layouts
        # que ninguém previu, e o modelo precisa saber o que NÃO é cargo.
        "CARGO é o posto que a pessoa vai ocupar (\"Contador\", \"Delegado de Polícia\", "
        "\"Assistente Técnico Legislativo\"). NÃO são cargos, e não podem virar item de "
        "`cargos`:\n"
        "- MATÉRIA de estudo (\"Língua Portuguesa\", \"Informática\", \"Raciocínio Lógico\") "
        "— isso é disciplina;\n"
        "- SEÇÃO do documento (\"Conhecimentos Gerais\", \"Conhecimentos Específicos\", "
        "\"Nível Superior\", \"Nível Médio\", \"Anexo I\") — é divisória, não posto;\n"
        "- MOBÍLIA de página (\"Página 26 de 32\", nome do órgão repetido no topo, rodapé "
        "com endereço ou site) — ignore por completo;\n"
        "- PEDAÇO de um título que o PDF quebrou em duas linhas (\"Cibernética e Crimes "
        "Digitais\" sozinho é a segunda metade de um cabeçalho) — junte as linhas antes de "
        "decidir.\n"
        "O cargo pode aparecer SEM a palavra \"cargo\" na frente: uma linha em maiúsculas "
        "sozinha, logo antes do conteúdo dele, já é o cabeçalho do cargo.\n"
        "Se um bloco vale para MAIS DE UM cargo (\"AGENTE DE POLÍCIA JUDICIÁRIA E "
        "PAPILOSCOPISTA POLICIAL\"), repita essas disciplinas dentro de CADA cargo citado.\n\n"
        # Achado no Jateí: o conteúdo específico do Analista TEM subcabeçalhos
        # ("FINANÇAS PÚBLICAS:", "ECONOMIA:", "CONTABILIDADE PÚBLICA:") e saiu
        # com 5 disciplinas; o do Contador e o do Assistente são um parágrafo
        # corrido, sem subcabeçalho nenhum, e saíram como UMA disciplina
        # chamada "Conhecimentos Específicos" — que é o nome da SEÇÃO, não de
        # matéria nenhuma. Nomear pelo cargo é o que o projeto já faz quando o
        # PERFIL 1 da FGV lista tópicos direto (ver `extrair_estrutura`).
        "DENTRO do bloco de um cargo, cada subcabeçalho de matéria vira uma disciplina "
        "(\"FINANÇAS PÚBLICAS\", \"ECONOMIA\", \"CONTABILIDADE PÚBLICA\"). Se o bloco NÃO tem "
        "subcabeçalho — é um parágrafo corrido de conteúdo —, então ele é UMA disciplina só, "
        "e o nome dela é o NOME DO CARGO. Nunca use \"Conhecimentos Específicos\", "
        "\"Conhecimentos Gerais\" ou \"Conteúdo Programático\" como nome de disciplina: "
        "isso é divisória do documento, não matéria de estudo."
    )
    try:
        lido = llm.obter().gerar_json(
            corpo[:MAX_CHARS_LLM], sistema, max_tokens=8000, schema=ESQUEMA_ESTRUTURA)
        # Mesmo tratamento do bloco guarda-chuva que o parser recebe: a
        # instrução acima pede pra repetir, mas instrução de prompt vaza —
        # e aqui a correção em código custa uma passada numa lista.
        lido["cargos"] = _redistribuir_compartilhados(lido.get("cargos") or [])
        return lido, "llm"
    except (llm.ErroLLM, ValueError, KeyError, TypeError):
        return estrutura, "parser_apos_falha"


# --------------------------------------------------------------- borda (db)
def ingerir(mesa_id: int, caminho, titulo: str | None = None, orgao: str | None = None,
            banca: str | None = None) -> dict:
    """O edital pertence à MESA, não ao usuário (migração 010) — a mesma
    pessoa pode visar dois concursos ao mesmo tempo, cada um com sua data e
    seu conteúdo programático, e é o edital de cada mesa que define quais
    disciplinas aquela mesa mostra (ver core/mesa.py)."""
    from pypdf import PdfReader
    caminho = Path(caminho)
    reader = PdfReader(str(caminho))
    texto = "\n\n".join((p.extract_text() or "") for p in reader.pages)

    candidatos = candidatos_data_prova(texto)
    data_prova = candidatos[0]["data"] if candidatos else None
    topicos = extrair_topicos(texto)

    eid = db.exec1(
        """INSERT INTO edital (mesa_id, titulo, orgao, banca, data_prova, arquivo)
           VALUES (%(m)s, %(t)s, %(o)s, %(b)s, %(d)s, %(a)s) RETURNING id""",
        {"m": mesa_id, "t": titulo or caminho.stem, "o": orgao, "b": banca,
         "d": data_prova, "a": str(caminho)},
    )["id"]
    for t in topicos:
        db.query(
            """INSERT INTO topico (edital_id, disciplina, ordem, texto)
               VALUES (%(e)s, %(d)s, %(o)s, %(tx)s)""",
            {"e": eid, "d": t["disciplina"], "o": t["ordem"], "tx": t["texto"]},
        )

    return {
        "edital_id": eid,
        "data_prova": data_prova,
        "candidatos_data": candidatos[:5],
        "topicos": len(topicos),
        "disciplinas": sorted({t["disciplina"] for t in topicos}),
    }


def mais_recente(mesa_id: int) -> dict | None:
    """O mais recente da MESA. Reingerir um edital corrigido substitui o
    anterior aqui e em `mesa.disciplinas()` — as duas coisas leem o mesmo
    "último", senão a meta usaria uma data e o filtro de disciplina outra."""
    return db.exec1(
        "SELECT id, titulo, orgao, banca, data_prova, cargo FROM edital WHERE mesa_id = %(m)s "
        "ORDER BY criado_em DESC, id DESC LIMIT 1",
        {"m": mesa_id},
    )


def cobertura(edital_id: int, usuario_id: int) -> list[dict]:
    """
    Por disciplina do edital: quantos tópicos existem e a cobertura DESTE
    usuário (aproximação 2 do docstring do módulo — por disciplina, não por
    tópico individual). `caixa` mudou de tabela (agora vive em `progresso`,
    por usuário) — por isso o LEFT JOIN em vez do antigo WHERE direto em
    questao.
    """
    topicos = db.query(
        "SELECT disciplina, count(*) AS n FROM topico WHERE edital_id = %(e)s GROUP BY disciplina",
        {"e": edital_id},
    )
    resultado = []
    for t in topicos:
        r = db.exec1(
            f"""SELECT count(DISTINCT q.id) AS total,
                       count(DISTINCT q.id) FILTER (WHERE p.caixa >= 3) AS dominadas
                FROM questao q
                LEFT JOIN progresso p ON p.questao_id = q.id AND p.usuario_id = %(u)s
                WHERE q.disciplina ILIKE %(d)s AND {questoes.do_aluno('q')}""",
            {"d": f"%{t['disciplina']}%", "u": usuario_id, "dono": usuario_id},
        ) or {"total": 0, "dominadas": 0}
        cobertura_pct = 100 * r["dominadas"] / r["total"] if r["total"] else 0.0
        resultado.append({
            "disciplina": t["disciplina"],
            "topicos_no_edital": t["n"],
            "questoes_disciplina": r["total"],
            "cobertura_pct": round(cobertura_pct, 1),
            "topicos_pendentes_estimado": round(t["n"] * (1 - cobertura_pct / 100)),
        })
    return resultado


def probabilidade_fechamento(edital_id: int, usuario_id: int, data_prova: date | None = None,
                             disciplinas: list[str] | None = None) -> dict:
    """
    APROXIMAÇÃO por extrapolação linear de ritmo — não é um modelo
    estatístico (não modela variância nem esquecimento; mesma limitação já
    documentada em simular.py). "Se o ritmo dos últimos dias continuar,
    que fração da velocidade necessária isso representa" é a pergunta que
    este número responde — não "qual a chance real de passar".

    `data_prova` opcional SOBRESCREVE a do banco — quando o operador corrige
    a data manualmente (extração automática errou, ver candidatos_data_prova),
    esse número tem que refletir a correção, não a data original errada.
    """
    if data_prova is None:
        ed = db.exec1("SELECT data_prova FROM edital WHERE id = %(e)s", {"e": edital_id})
        data_prova = ed["data_prova"] if ed else None
    if not data_prova:
        return {"erro": "edital sem data_prova reconhecida — sem data não dá pra estimar ritmo"}

    dias_restantes = max((data_prova - date.today()).days, 0)
    cob = cobertura(edital_id, usuario_id)
    topicos_totais = sum(c["topicos_no_edital"] for c in cob)
    topicos_pendentes = sum(c["topicos_pendentes_estimado"] for c in cob)
    topicos_cobertos = topicos_totais - topicos_pendentes

    # `dias_estudando` escopado nas disciplinas DESTA mesa, não na conta
    # inteira: uma mesa aberta hoje, numa conta que estuda há 6 meses,
    # espalharia a cobertura recém-começada sobre 180 dias e reportaria um
    # ritmo perto de zero — número errado com cara de medida.
    primeira = db.exec1(
        f"""SELECT min(t.criada_em)::date AS d
              FROM tentativa t JOIN questao q ON q.id = t.questao_id
             WHERE t.usuario_id = %(u)s AND {mesa_mod.filtro('q.disciplina')}""",
        {"u": usuario_id, "disc": disciplinas})
    dias_estudando = max((date.today() - primeira["d"]).days, 1) if primeira and primeira["d"] else 0

    ritmo_atual = topicos_cobertos / dias_estudando if dias_estudando else 0.0
    ritmo_necessario = topicos_pendentes / dias_restantes if dias_restantes else None

    if topicos_pendentes <= 0:
        probabilidade = 100.0
    elif dias_restantes <= 0 or ritmo_atual <= 0:
        probabilidade = 0.0
    else:
        probabilidade = min(100.0, round(100 * ritmo_atual / ritmo_necessario, 1))

    return {
        "dias_restantes": dias_restantes,
        "topicos_totais": topicos_totais,
        "topicos_pendentes_estimado": topicos_pendentes,
        "ritmo_atual_topicos_dia": round(ritmo_atual, 2),
        "ritmo_necessario_topicos_dia": round(ritmo_necessario, 2) if ritmo_necessario is not None else None,
        "probabilidade_fechamento_pct": probabilidade,
    }


def ajustar_disciplinas(edital_id: int, remover: list[str] | None = None,
                        adicionar: list[str] | None = None) -> dict:
    """
    Tira ou acrescenta disciplina num edital JÁ CONFIRMADO, sem subir o PDF de
    novo.

    Existe porque a curadoria só acontecia UMA vez: depois de confirmar, mudar
    de ideia sobre uma matéria exigia reingerir o edital inteiro — e o aluno
    muda de ideia no meio do estudo, que é justamente quando ele sabe o que
    está sobrando. O mesmo princípio da curadoria, agora contínuo: vale a lista
    que o aluno mantém, não a que a leitura achou.

    ADICIONAR grava um tópico ÚNICO com o nome da disciplina como texto, e a
    razão é estrutural: `mesa.disciplinas()` sai de `SELECT DISTINCT
    topico.disciplina`, então disciplina sem nenhum tópico não existe pro
    recorte — seria uma linha que o aluno vê na tela e o filtro ignora. Um
    tópico declarado é honesto; zero tópico seria mentira silenciosa.

    REMOVER apaga os tópicos daquela disciplina (é o que a define). Não toca em
    `questao` nem em `progresso`: o que o aluno já respondeu é histórico dele,
    não do edital — mesma decisão da migração 010 pra `simulado -> mesa`.
    """
    tirados = 0
    for nome in remover or []:
        r = db.query("DELETE FROM topico WHERE edital_id = %(e)s AND disciplina = %(d)s",
                     {"e": edital_id, "d": nome})
        tirados += r if isinstance(r, int) else 0

    postos = []
    for nome in adicionar or []:
        nome = re.sub(r"\s+", " ", nome).strip()
        if not nome:
            continue
        # Já existe? Não duplica — o aluno pode clicar duas vezes, e uma
        # disciplina repetida apareceria duas vezes na cobertura.
        ja = db.exec1("SELECT 1 FROM topico WHERE edital_id = %(e)s AND disciplina = %(d)s LIMIT 1",
                      {"e": edital_id, "d": nome})
        if ja:
            continue
        prox = db.exec1("SELECT COALESCE(MAX(ordem), -1) + 1 AS n FROM topico WHERE edital_id = %(e)s",
                        {"e": edital_id})["n"]
        db.query("""INSERT INTO topico (edital_id, disciplina, ordem, texto)
                    VALUES (%(e)s, %(d)s, %(o)s, %(t)s)""",
                 {"e": edital_id, "d": nome, "o": prox,
                  "t": f"{nome} (acrescentada por você — sem tópicos do edital)"})
        postos.append(nome)

    return {"removidas": remover or [], "adicionadas": postos, "topicos_apagados": tirados}


# Limites de escrita. Não são estética: o `titulo` vai pro cabeçalho de várias
# telas e pro prompt do tutor, e `disciplina` é o que `mesa.filtro` compara com
# ILIKE contra o acervo. Texto colado de PDF chega com centenas de caracteres e
# quebra de linha no meio; sem teto, um "edital" declarado à mão viraria uma
# parede de texto em todo lugar que o exibe.
MAX_TITULO = 200
MAX_DISCIPLINA = 120
# 60 é folgado pro pior edital real que já passou por aqui (o da Dataprev tem 52
# disciplinas somando os treze perfis). O teto existe pra recusar colagem
# acidental de um documento inteiro, não pra limitar concurso de verdade.
MAX_DISCIPLINAS = 60


def criar_manual(mesa_id: int, titulo: str | None = None, data_prova=None,
                 disciplinas: list[str] | None = None,
                 nome_da_mesa: str | None = None) -> dict:
    """Edital declarado à MÃO — sem PDF (017).

    A decisão que sustenta isto: **um edital declarado à mão É um edital**. A
    alternativa era guardar "data prevista" numa coluna nova da mesa e ensinar
    `scheduler.meta` a olhar em dois lugares — e aí o recorte viria de uma fonte
    e o prazo de outra, que é exatamente o defeito que a 010 evitou ao fazer
    disciplina e data saírem do MESMO "último edital". Criando um `edital` de
    verdade, todo o encanamento existente serve sem reescrita: `mais_recente`
    acha a data, `cobertura` conta, `mesa.disciplinas` recorta, `/meta` mostra.

    Um `topico` por disciplina, com o próprio nome como texto — o mesmo que a
    curadoria (011) já faz quando o extrator não detalhou os tópicos daquela
    matéria. Sem essa linha a escolha não entraria no recorte, porque é de
    `topico.disciplina` que `mesa.disciplinas()` sai.

    TUDO É OPCIONAL de propósito, e cada combinação é um caso real de quem
    estuda antes do edital sair:
      · só matérias      -> estudo avulso sem prazo
      · só data          -> "a prova deve ser em novembro", ainda sem programa
      · só título        -> a mesa ganha nome de concurso no cabeçalho
    Exigir os três transformaria um chute legítimo em bloqueio. O que NÃO se
    aceita é o vazio completo — criar um edital sem título, sem data e sem
    matéria é gravar uma linha que não diz nada.

    Data no PASSADO é aceita: quem estuda por um edital vencido esperando o
    próximo é caso corrente, e `scheduler.meta` já sabe dizer que o prazo passou
    (é a tela que avisa, não o banco que recusa).
    """
    # O que a PESSOA pediu, antes de qualquer fallback: a guarda de "vazio
    # completo" tem que olhar pro pedido, não pro que o servidor preencheu por
    # ela. Medido: com o fallback aplicado primeiro, um `POST {}` criava um
    # edital chamado como a mesa — a linha que não diz nada que esta função
    # existe pra recusar.
    pediu_titulo = (titulo or "").strip()
    # Nome de matéria é comparado com ILIKE contra o acervo: espaço duplo e
    # quebra de linha colada de PDF fariam o filtro não casar nada, e o sintoma
    # seria fila vazia sem explicação. Normaliza aqui, uma vez, na escrita.
    limpas, vistas = [], set()
    for d in (disciplinas or []):
        nome = " ".join((d or "").split())[:MAX_DISCIPLINA]
        if nome and nome.lower() not in vistas:
            vistas.add(nome.lower())
            limpas.append(nome)
    if len(limpas) > MAX_DISCIPLINAS:
        raise ValueError(
            f"são {len(limpas)} matérias, e o limite é {MAX_DISCIPLINAS}. "
            "Se você colou um documento inteiro no campo, escolha só os nomes das matérias.")
    if not pediu_titulo and not data_prova and not limpas:
        raise ValueError("dê um nome, uma data prevista ou pelo menos uma matéria")
    # Só agora o fallback: título vazio herda o nome da mesa, porque o cabeçalho
    # de /meta precisa de algo pra exibir e "sem título" é pior que o nome que a
    # pessoa já deu ao concurso quando criou a mesa.
    titulo = pediu_titulo[:MAX_TITULO] or (nome_da_mesa or "").strip()[:MAX_TITULO]

    # ORDEM À PROVA DE FALHA: cria o novo ANTES de apagar o antigo. `db` roda em
    # autocommit e não tem rollback (ver "Armadilhas de método" no CLAUDE.md), e
    # `mais_recente` ordena por criado_em/id DESC — então o novo já vence no
    # instante em que entra. Apagando primeiro, uma falha aqui deixaria a mesa
    # SEM edital nenhum, pior do que começou.
    novo = db.exec1(
        """INSERT INTO edital (mesa_id, titulo, data_prova, arquivo)
           VALUES (%(m)s, %(t)s, %(d)s, NULL)
        RETURNING id, titulo, orgao, banca, data_prova, cargo""",
        {"m": mesa_id, "t": titulo or None, "d": data_prova or None})
    for i, nome in enumerate(limpas):
        db.exec1(
            """INSERT INTO topico (edital_id, disciplina, ordem, texto)
               VALUES (%(e)s, %(d)s, %(o)s, %(d)s) RETURNING id""",
            {"e": novo["id"], "d": nome, "o": i})
    # Só agora os anteriores saem. `topico` deles morre pelo CASCADE da 007.
    antigos = db.query(
        "SELECT id FROM edital WHERE mesa_id = %(m)s AND id <> %(n)s",
        {"m": mesa_id, "n": novo["id"]})
    if antigos:
        db.query("DELETE FROM edital WHERE mesa_id = %(m)s AND id <> %(n)s",
                 {"m": mesa_id, "n": novo["id"]})
    novo["disciplinas"] = limpas
    novo["substituiu"] = len(antigos)
    return novo


def remover(mesa_id: int) -> dict | None:
    """Tira o edital da mesa — ela volta a ser estudo avulso (017).

    Existe porque o alvo manual NÃO soma ao edital: quando o PDF está lá, ele
    vence inteiro (é dele que sai a data da prova, e disciplina de um lugar com
    prazo de outro é o defeito que a 010 evitou). Consequência: a tela de alvo
    manual só tem como valer se o edital sair, e aceitar a escolha sem tirar o
    edital era pedir um trabalho que o servidor ignora.

    Devolve O QUE FOI EMBORA (título, data, cargo, contagem de tópicos) porque
    a operação é irreversível pelo servidor: os bytes do PDF não ficam
    guardados, só o extraído. Quem chama precisa poder dizer ao aluno o que ele
    perdeu, e não um "ok" que esconde a perda.

    `topico` desaparece pelo `ON DELETE CASCADE` da 007 — não há limpeza escrita
    na mão aqui, pelo mesmo motivo da migração 009: lógica de limpeza ad-hoc é
    onde bug mora. `simulado.mesa_id` não é afetado (aponta pra mesa, não pro
    edital), então prova já feita continua no histórico.

    Não recebe `usuario_id` de propósito: `edital` não tem essa coluna desde a
    010 — o edital pertence à MESA e a mesa ao usuário. Quem autoriza é o
    chamador, resolvendo a mesa por `mesa.obter`/`mesa_atual` (que já filtram
    por usuario_id). Passar um id aqui seria a denormalização que a 010 tirou.
    """
    atual = mais_recente(mesa_id)
    if not atual:
        return None
    # Uma consulta só, e ANTES do delete: depois do CASCADE não há mais tópico
    # pra contar, e informar "0 tópicos removidos" seria pior que não informar.
    quantos = db.exec1(
        "SELECT count(*) AS n FROM topico WHERE edital_id = %(e)s", {"e": atual["id"]})["n"]
    # Apaga TODOS os editais da mesa, não só o mais recente: `mais_recente`
    # devolve um, mas nada impede a mesa ter histórico, e deixar um antigo pra
    # trás faria a mesa continuar com `origem_alvo='edital'` — a tela diria
    # "removido" e o recorte seguiria vindo do PDF. Falha silenciosa exata que
    # esta função existe pra não criar.
    db.query("DELETE FROM edital WHERE mesa_id = %(m)s", {"m": mesa_id})
    return {"titulo": atual["titulo"], "data_prova": atual["data_prova"],
            "cargo": atual.get("cargo"), "topicos": quantos}


def corrigir_data_prova(edital_id: int, data_prova) -> dict | None:
    """
    Troca a data da prova de um edital já confirmado.

    Existe por um caso concreto: o edital da PF em `corpus/` é de 2025 e a
    prova JÁ PASSOU. `scheduler.meta` devolvia "0 dias restantes" e
    "probabilidade 0%" — números verdadeiros e inúteis, porque não há mais
    prazo pra medir ritmo contra. Sem uma forma de apontar uma data futura, a
    mesa inteira fica sem meta: o aluno que estuda por um edital antigo (pra
    concurso que vai reabrir, o caso mais comum de preparação) não tinha saída
    nenhuma além de reingerir o PDF, que traria a mesma data velha de novo.

    Mesma lógica que a CLI já tinha (`chat.py meta 2026-11-15`, data manual
    sempre vence a do edital), agora com onde gravar em vez de só no argumento
    do comando — porque no navegador não há argumento pra repetir toda vez.
    """
    return db.exec1(
        "UPDATE edital SET data_prova = %(d)s WHERE id = %(e)s "
        "RETURNING id, titulo, orgao, banca, data_prova, cargo",
        {"d": data_prova, "e": edital_id},
    )
