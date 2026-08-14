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

from . import db, mesa as mesa_mod

VERSAO = "edital-v5"

MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5,
         "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
         "novembro": 11, "dezembro": 12}

# "no dia D de MÊS de AAAA" — distingue de citação legal ("Lei nº X, DE D
# de MÊS de AAAA"), que não tem a palavra "dia" antes do número.
RE_DATA_EVENTO = re.compile(
    r"\bdia\s+(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\s+de\s+(20\d{2})", re.I)

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
RE_DISCIPLINA = re.compile(
    r"^[ \t]*(?:\d{1,2}[.)]\s+)?([A-ZÀ-Ü][A-ZÀ-Ü0-9 \t\-/&(),]{2,70}?)[ \t]*:",
    re.MULTILINE)

# "PERFIL 3: DESENVOLVIMENTO DE SOFTWARE" — marcador de CARGO, não de
# disciplina. Vira disciplina mesmo assim porque há perfis (o 1, por
# exemplo) cujo conteúdo é uma lista numerada direta, sem subcabeçalho: sem
# isso os tópicos dele cairiam na disciplina anterior, que é pior que um
# nome de disciplina largo demais. Perfis COM subcabeçalhos ganham um bloco
# vazio aqui, que morre sozinho por não ter subitem.
RE_PERFIL = re.compile(
    r"^[ \t]*PERFIL\s+\d{1,2}\s*[:\-–—]\s*(.+?)[ \t]*:?[ \t]*$",
    re.MULTILINE | re.IGNORECASE)

# Linhas que são ESTRUTURA do documento, não matéria de estudo.
RE_ESTRUTURA = re.compile(r"^(M[OÓ]DULO|ANEXO|CARGO|PERFIL)\b", re.IGNORECASE)

# O conteúdo programático costuma viver num anexo próprio. Recortar antes de
# procurar disciplina evita que o CORPO do edital (regras de inscrição, que
# são centenas de itens numerados "4.5.1", "10.13.6") entre como tópico de
# estudo — foi assim que uma disciplina fantasma acumulou 257 "tópicos".
# Singular E plural: a FGV escreve "ANEXO I – CONTEÚDO PROGRAMÁTICO", o
# AOCP escreve "ANEXO I – DOS CONTEÚDOS PROGRAMÁTICOS".
RE_INICIO_CONTEUDO = re.compile(r"\bCONTE[ÚU]DOS?\s+PROGRAM[ÁA]TICOS?\b", re.IGNORECASE)
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
    for m in RE_DATA_EVENTO.finditer(flat):
        # A janela nunca cruza o candidato anterior — sem isso, duas datas
        # próximas (comum: "Prova Objetiva dia X... Prova Discursiva dia Y"
        # em sequência) "emprestam" pontuação uma da outra, e a segunda
        # data rouba o crédito de "prova objetiva" que pertence à primeira.
        ini = max(0, m.start() - janela, fim_anterior)
        contexto = flat[ini:m.start() + 40]
        pontos = (contexto.lower().count("prova objetiva") * 3
                  + contexto.lower().count("realizad"))
        fim_anterior = m.end()
        try:
            d = date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
        except ValueError:
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
    linhas = texto.splitlines()
    repetidas = Counter(l.strip() for l in linhas if l.strip())
    mobilia = {t for t, n in repetidas.items()
               if n >= 4 and len(t) <= 60 and not t.endswith(":")}
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
    anterior = texto[:inicio].rstrip()
    return bool(anterior) and anterior[-1] in "0123456789,;–-"


def _cabecalhos(texto: str) -> list[tuple[int, int, str]]:
    """(início, fim, nome) de cada cabeçalho, em ordem de posição."""
    marcas = [(m.start(), m.end(), m.group(1)) for m in RE_PERFIL.finditer(texto)]
    for m in RE_DISCIPLINA.finditer(texto):
        if RE_ESTRUTURA.match(m.group(1).strip()):
            continue
        if _continuacao_de_paragrafo(texto, m.start()):
            continue
        marcas.append((m.start(), m.end(), m.group(1)))
    marcas.sort()
    # A linha do PERFIL casa nas duas regexes; fica a primeira (a do perfil,
    # que captura o nome do cargo em vez do literal "PERFIL N").
    limpo: list[tuple[int, int, str]] = []
    for marca in marcas:
        if limpo and marca[0] < limpo[-1][1]:
            continue
        limpo.append(marca)
    return limpo


def extrair_topicos(texto: str) -> list[dict]:
    """
    [{"disciplina": ..., "ordem": N, "texto": "1.1.1 Princípios..."}]

    Cabeçalho de disciplina é detectado no texto CRU (ver RE_DISCIPLINA — a
    quebra de linha é o sinal); só o corpo de cada bloco é normalizado, que
    é onde a quebra de linha atrapalha. Ver limitações (1) e (2) no
    docstring do módulo.
    """
    corpo, _ = recortar_conteudo_programatico(limpar_paginacao(texto))
    marcas = _cabecalhos(corpo)
    topicos = []
    for i, (_, fim, bruto) in enumerate(marcas):
        disciplina = re.sub(r"\s+", " ", bruto).strip(" :").title()
        # O teto no último bloco é rede de segurança pra quando o recorte do
        # conteúdo programático não encontrou marcador: sem ele, a última
        # disciplina engoliria o resto do documento inteiro.
        prox = marcas[i + 1][0] if i + 1 < len(marcas) else min(len(corpo), fim + 8000)
        # lstrip: o primeiro item do bloco precisa encostar no início da
        # string pra RE_SUBITEM aceitá-lo pela alternativa `^` (ele é o
        # único que não vem depois de pontuação — vem depois do cabeçalho).
        bloco = _normalizar(corpo[fim:prox]).lstrip()
        subitens = list(RE_SUBITEM.finditer(bloco))
        for j, s in enumerate(subitens):
            fim_s = subitens[j + 1].start() if j + 1 < len(subitens) else len(bloco)
            # Só FOLHA vira tópico: "4" seguido de "4.1" é o pai do próximo,
            # e contar os dois inflaria a mesma matéria duas vezes — o
            # denominador de "quantos tópicos existem" tem que ser o que se
            # estuda, não a árvore inteira.
            if j + 1 < len(subitens) and subitens[j + 1].group(1).startswith(s.group(1) + "."):
                continue
            texto_topico = bloco[s.start():fim_s].strip()
            if texto_topico:
                topicos.append({"disciplina": disciplina, "ordem": len(topicos),
                                "texto": texto_topico})
    return topicos


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
        "SELECT id, titulo, orgao, banca, data_prova FROM edital WHERE mesa_id = %(m)s "
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
            """SELECT count(DISTINCT q.id) AS total,
                      count(DISTINCT q.id) FILTER (WHERE p.caixa >= 3) AS dominadas
               FROM questao q
               LEFT JOIN progresso p ON p.questao_id = q.id AND p.usuario_id = %(u)s
               WHERE q.disciplina ILIKE %(d)s""",
            {"d": f"%{t['disciplina']}%", "u": usuario_id},
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
