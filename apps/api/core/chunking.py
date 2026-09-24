"""
Divisão do material em chunks.

Lei seca e material didático pedem estratégias diferentes:

- Lei: quebrar por dispositivo (Art., §, inciso) e guardar o identificador.
  Um artigo é uma unidade semântica completa; cortá-lo por contagem de
  caracteres destrói exatamente a informação que o estudante procura.
- Aula/resumo: janela deslizante com sobreposição, respeitando parágrafos.

DUAS COISAS QUE O CORTE INGÊNUO PERDE, e que este módulo recupera:

1. A RUBRICA (nomen iuris). No Planalto o nome do crime vem numa linha
   ANTES do artigo:

       Concussão
       Art. 316. Exigir, para si ou para outrem...

   Cortando em `^Art.`, "Concussão" cai no fim do chunk do art. 315 — e
   buscar por nome de crime deixa de funcionar para os ~200 tipos penais.
   A rubrica é destacada da cauda e devolvida ao artigo a que pertence.

2. A HIERARQUIA (TÍTULO / CAPÍTULO / SEÇÃO). Dá agrupamento temático de
   graça, que depois serve para mapear artigo a tópico do edital e para
   amostrar o documento por seção na hora de gerar questões.

Ambas entram no campo `texto`, não só em coluna separada: o embedding e o
tsvector são calculados sobre `texto`, então o que não estiver ali não é
recuperável nem por semântica nem por palavra-chave.
"""
import math
import re
from collections import Counter

VERSAO = "chunking-v14"

RE_ARTIGO = re.compile(r"(?im)^\s*Art\.?\s*(\d+[\-\wºo]*)")
RE_PARAGRAFO = re.compile(r"(?im)^\s*(?:§\s*(\d+[\wºo]*)|Par[áa]grafo\s+[úu]nico)")
RE_INCISO = re.compile(r"(?im)^\s*([IVXLCDM]+)\s*[-–—)]")

# --------------------------------------------------------------- normalização
# HTML do Planalto quebra linha no meio da frase. Isso parte rubricas
# ("Emprego irregular de verbas / ou rendas públicas") e separa o § do seu
# número (" §" / "1º Se o agente..."), fazendo os regexes acima perderem
# dispositivo. Desfazer a quebra artificial vem ANTES de qualquer corte.
RE_FIM_FRASE = re.compile(r"[.:;!?]$")
RE_ART_SOLTO = re.compile(r"(?i)\bart\.?$")


def normalizar_lei(texto: str) -> str:
    """Junta linhas quebradas artificialmente, preservando parágrafos em branco."""
    linhas = texto.split("\n")
    saida: list[str] = []
    for linha in linhas:
        atual = linha.rstrip()
        if not saida or not saida[-1].strip() or not atual.strip():
            saida.append(atual)
            continue
        ant = saida[-1].rstrip()
        prim = atual.lstrip()[:1]
        junta = (
            # continuação de frase: linha seguinte começa em minúscula
            (prim.islower() and not RE_FIM_FRASE.search(ant))
            # "§" órfão antes do próprio número
            or ant.endswith("§")
            # "Art." separado do número
            or RE_ART_SOLTO.search(ant)
            # parêntese aberto e não fechado: a frase continua na linha
            # seguinte, mesmo que ela comece com dígito ("...Lei nº" / "7.209")
            or ant.count("(") > ant.count(")")
            # nome de TÍTULO/CAPÍTULO quebrado entre linhas de caixa alta
            or (_eh_caixa_alta(ant) and _eh_caixa_alta(atual)
                and not RE_FIM_FRASE.search(ant)
                and not RE_NIVEL.match(atual))
        )
        if junta:
            saida[-1] = f"{ant} {atual.lstrip()}"
        else:
            saida.append(atual)
    return "\n".join(saida)


NIVEIS = ("TITULO", "CAPITULO", "SECAO", "SUBSECAO")
RE_NIVEL = re.compile(r"(?i)^\s*(t[íi]tulo|cap[íi]tulo|subse[çc][ãa]o|se[çc][ãa]o)\b\s*(.*)$")

# Linhas de nota legislativa que não são rubrica
RE_NOTA = re.compile(
    r"(?i)(reda[çc][ãa]o dada|inclu[íi]d[oa]|revogad[oa]|vide|vigor|vig[êe]ncia|"
    r"vetado|lei n|decreto|renumerad|ac?rescentad)"
)
MAX_LINHAS_CAUDA = 6


def _sem_nota(linha: str) -> str:
    """
    Remove notas legislativas em parênteses no fim da linha.

    A Parte Geral do CP foi reescrita pela Lei 7.209/1984, então as rubricas
    vêm com a nota colada:

        Lei excepcional ou temporária (Incluído pela Lei nº 7.209, de 11.7.1984)

    Sem tirar o parêntese, a rubrica legítima é confundida com nota e
    descartada — o que apagava a rubrica de toda a Parte Geral.
    """
    l = linha.strip()
    for _ in range(3):
        m = re.search(r"\(([^()]*)\)\s*$", l)
        if m and RE_NOTA.search(m.group(1)):
            l = l[:m.start()].rstrip()
            continue
        # nota truncada: parêntese abriu e não fechou até o fim da linha
        m = re.search(r"\(([^()]*)$", l)
        if m and RE_NOTA.search(m.group(1)):
            l = l[:m.start()].rstrip()
            continue
        break
    return l


def _eh_titulo_hierarquia(linha: str) -> bool:
    return bool(RE_NIVEL.match(linha.strip()))


def _eh_caixa_alta(linha: str) -> bool:
    l = linha.strip()
    return bool(l) and l == l.upper() and any(c.isalpha() for c in l)


def _eh_rubrica(linha: str) -> bool:
    """
    Rubrica é linha curta, sem pontuação final, iniciando em maiúscula, que
    não é artigo, parágrafo, inciso, pena, nota legislativa nem cabeçalho.
    A nota entre parênteses é descartada antes da avaliação.
    """
    l = _sem_nota(linha)
    if not l or len(l) > 90:
        return False
    if l.endswith((".", ":", ";", ",")):
        return False
    if not l[0].isupper():
        return False
    if RE_ARTIGO.match(l) or _eh_titulo_hierarquia(l):
        return False
    # Linha de cominação de pena é "Pena - reclusão, de..." (com travessão).
    # Exigir o travessão é essencial: sem isso a regra derruba rubricas
    # legítimas que começam com a palavra — "Pena cumprida no estrangeiro",
    # "Penas restritivas de direitos", "Pena de multa".
    if re.match(r"(?i)^(pena[s]?\s*[-–—:]|par[áa]grafo|§|[IVXLCDM]+\s*[-–—)]|\()", l):
        return False
    if RE_NOTA.search(l):
        return False
    if _eh_caixa_alta(l) and len(l.split()) > 5:
        return False        # nome de TÍTULO, não rubrica de artigo
    return True


def _so_nota(linha: str) -> bool:
    """Linha que é apenas nota legislativa, sem conteúdo próprio."""
    return bool(linha.strip()) and not _sem_nota(linha)


def _cortar_cauda(bloco: str) -> tuple[str, str]:
    """
    Separa do fim do bloco as linhas que pertencem ao PRÓXIMO artigo
    (cabeçalhos de hierarquia e rubrica). Para na primeira linha que faz
    parte do artigo corrente, para nunca comer o corpo.

    Linha só-de-nota é PULADA, não é motivo de parada. O Planalto insere a
    nota da lei entre a rubrica e o artigo:

        Feminicídio
        (Incluído pela Lei nº 14.994, de 2024)
        Art. 121-A. Matar mulher...

    Parar na nota perdia a rubrica de artigos recentes — feminicídio,
    121-B, 122, 144 — que são justamente os mais cobrados.
    """
    linhas = bloco.rstrip().split("\n")
    cauda: list[str] = []
    notas: list[str] = []
    while linhas and len(cauda) < MAX_LINHAS_CAUDA:
        ult = linhas[-1]
        if not ult.strip():
            linhas.pop()
            continue
        if _so_nota(ult):
            l = linhas.pop()
            # Subindo, as notas encontradas ANTES da rubrica pertencem ao
            # artigo seguinte; as encontradas depois são do artigo corrente.
            notas.insert(0, l)   # v12: guarda toda nota descartada
            continue
        if _eh_titulo_hierarquia(ult) or _eh_caixa_alta(ult) or _eh_rubrica(ult):
            cauda.insert(0, linhas.pop())
            continue
        break

    corpo = "\n".join(linhas).strip()
    # Artigo revogado tem como corpo apenas a nota ("Art. 217 - / (Revogado
    # pela Lei...)"). Descartar a nota o esvazia e o chunk é perdido — então
    # a nota volta. Saber que um artigo foi revogado é conteúdo de prova.
    if len(corpo) < 20 and notas:
        corpo = (corpo + "\n" + "\n".join(notas)).strip()
    return corpo, "\n".join(cauda).strip()


def _ler_cauda(cauda: str, hierarquia: dict) -> str | None:
    """
    Interpreta a cauda: atualiza `hierarquia` (mutável, estado corrente do
    documento) e devolve a rubrica encontrada, se houver.

    No Planalto o cabeçalho vem em duas linhas:
        TÍTULO XI
        DOS CRIMES CONTRA A ADMINISTRAÇÃO PÚBLICA
    """
    linhas = [l.strip() for l in cauda.split("\n") if l.strip()]
    rubrica = None
    i = 0
    while i < len(linhas):
        m = RE_NIVEL.match(linhas[i])
        if m:
            bruto = m.group(1).upper()
            nivel = ("TITULO" if bruto.startswith("T")
                     else "SUBSECAO" if bruto.startswith("SUBSE")
                     else "CAPITULO" if bruto.startswith("CAP")
                     else "SECAO")
            rotulo = linhas[i].strip()
            i += 1
            nome: list[str] = []
            while i < len(linhas) and _eh_caixa_alta(linhas[i]) and not RE_NIVEL.match(linhas[i]):
                nome.append(linhas[i].strip())
                i += 1
            hierarquia[nivel] = f"{rotulo} — {' '.join(nome)}" if nome else rotulo
            for menor in NIVEIS[NIVEIS.index(nivel) + 1:]:
                hierarquia.pop(menor, None)
            continue
        if _eh_rubrica(linhas[i]) and not _eh_caixa_alta(linhas[i]):
            rubrica = _sem_nota(linhas[i])
        i += 1
    return rubrica


def _secao(hierarquia: dict) -> str | None:
    ativos = [hierarquia[n] for n in NIVEIS if n in hierarquia]
    return " / ".join(ativos) if ativos else None


def chunk_lei(texto: str, norma: str) -> list[dict]:
    """Um chunk por artigo, com rubrica e hierarquia anexadas ao artigo certo."""
    texto = normalizar_lei(texto)
    marcas = list(RE_ARTIGO.finditer(texto))
    if not marcas:
        return chunk_generico(texto)

    # Corpo de cada artigo e a cauda que pertence ao artigo seguinte.
    corpos: list[str] = []
    caudas: list[str] = [texto[:marcas[0].start()]]
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        corpo, cauda = _cortar_cauda(texto[m.start():fim])
        corpos.append(corpo)
        caudas.append(cauda)

    hierarquia: dict[str, str] = {}
    saida = []
    for i, m in enumerate(marcas):
        rubrica = _ler_cauda(caudas[i], hierarquia)
        secao = _secao(hierarquia)
        corpo = corpos[i]
        if len(corpo) < 20:
            continue

        # Cabeçalho vai DENTRO do texto: é o que torna a rubrica pesquisável.
        cabecalho = "\n".join(p for p in (secao, rubrica) if p)
        par = RE_PARAGRAFO.search(corpo)
        inc = RE_INCISO.search(corpo)
        saida.append({
            "texto": f"{cabecalho}\n{corpo}" if cabecalho else corpo,
            "norma": norma,
            "artigo": m.group(1),
            "paragrafo": (par.group(1) if par and par.group(1) else ("unico" if par else None)),
            "inciso": inc.group(1) if inc else None,
            "rubrica": rubrica,
            "secao": secao,
        })
    return saida


def taxa_colisao_artigo(chunks: list[dict]) -> float:
    """
    Fração dos chunks cujo (norma, artigo) JÁ apareceu antes na mesma lista.

    Por quê: chunk_lei() assume "uma versão vigente por artigo" — é assim
    que o Planalto publica lei compilada, e chunk_artigo_idx é montado com
    essa suposição (nunca virou UNIQUE de propósito, mas o produto inteiro
    conta com isso: por_dispositivo() devolve TODOS os chunks com aquele
    artigo, e se houver mais de um, cita fonte errada sem avisar).

    Um livro de histórico de emendas constitucionais reinicia "Art. 1º,
    Art. 2º..." a cada emenda, e ainda repete "Redação Anterior" do mesmo
    artigo — chunk_lei() não tem como saber que esse tipo de documento
    pediria chunk_generico() em vez dela; quem chama (ingest.py) precisa
    checar essa taxa DEPOIS e decidir.
    """
    if not chunks:
        return 0.0
    vistos = set()
    colisoes = 0
    for c in chunks:
        chave = (c.get("norma"), c.get("artigo"))
        if chave in vistos:
            colisoes += 1
        else:
            vistos.add(chave)
    return colisoes / len(chunks)


# CABEÇALHO, RODAPÉ E MARCA D'ÁGUA NÃO SÃO MATÉRIA. Medido em 22/09/2026 numa
# apostila real: 160–167 de 219 trechos começavam com as mesmas cinco linhas —
# nome da aula, concurso, site do curso, número da página e a marca d'água com
# o CPF e o NOME do aluno que comprou o PDF. Três efeitos, todos ruins: o CPF ia
# ao LLM externo em todo prompt que usava o trecho; o vetor de cada trecho ficava
# parecido com o de todos os outros; e o braço lexical casava o nome da matéria
# em tudo, porque ele estava em todo trecho.
#
# A regra é por FREQUÊNCIA dentro do MESMO documento, não por lista: linha que
# aparece em pelo menos metade das páginas é moldura da página, seja qual for o
# curso, o concurso ou o aluno. Os números viram "#" na comparação, então
# "35" e "36", ou "07180871192 - FULANO" em qualquer PDF de qualquer comprador,
# contam como a mesma linha repetida.
FRACAO_DE_PAGINAS_MOLDURA = 0.5
PAGINAS_MINIMAS_MOLDURA = 3
# Quantas linhas não vazias, de cada borda da página, podem ser moldura. Medido
# em 23/09/2026 em 17 PDFs de dois sites: a moldura mais funda estava a 7 linhas
# da borda; palavra solta de texto justificado (o pypdf extrai "de", "que", "a"
# numa linha só em algumas apostilas) ficava a 40+ linhas, e aparecia em mais da
# metade das páginas — sem esta faixa, a regra apagava palavras do conteúdo.
LINHAS_DE_BORDA_MOLDURA = 8


def _linha_comparavel(linha: str) -> str:
    return re.sub(r"\d+", "#", " ".join(linha.split()))


def _na_borda(pagina: str) -> list[tuple[str, bool]]:
    """Cada linha da página e se ela está na faixa da borda (linha em branco,
    nunca: ela não conta na distância e não é moldura)."""
    linhas = pagina.splitlines()
    cheias = [i for i, l in enumerate(linhas) if l.strip()]
    borda = set(cheias[:LINHAS_DE_BORDA_MOLDURA] + cheias[-LINHAS_DE_BORDA_MOLDURA:])
    return [(l, i in borda) for i, l in enumerate(linhas)]


def sem_moldura(paginas: list[str]) -> list[str]:
    """As páginas sem cabeçalho, rodapé e marca d'água.

    Moldura é linha que aparece NA BORDA de pelo menos metade das páginas. Só a
    ocorrência da borda sai: o mesmo "12" solto no meio da página é célula de
    tabela, não número de página.

    Documento curto (menos de `PAGINAS_MINIMAS_MOLDURA` páginas) volta intacto:
    sem páginas bastantes, repetição não distingue moldura de conteúdo. Linha em
    branco fica — é ela que separa parágrafo para o chunker."""
    if len(paginas) < PAGINAS_MINIMAS_MOLDURA:
        return paginas
    marcadas = [_na_borda(p) for p in paginas]
    presenca = Counter()
    for linhas in marcadas:
        presenca.update({_linha_comparavel(l) for l, borda in linhas if borda})
    corte = max(PAGINAS_MINIMAS_MOLDURA, math.ceil(len(paginas) * FRACAO_DE_PAGINAS_MOLDURA))
    moldura = {l for l, n in presenca.items() if n >= corte}
    if not moldura:
        return paginas
    return ["\n".join(l for l, borda in linhas
                      if not (borda and _linha_comparavel(l) in moldura))
            for linhas in marcadas]


# Fração das palavras do trecho ANTIGO que o novo precisa conter pra ser "o
# mesmo trecho, recortado de outro jeito". Reindexar troca o corte (moldura
# que saiu, alvo de tamanho que mudou), não o conteúdo; abaixo da metade, o
# trecho antigo não sobreviveu e dizer que sobreviveu seria proveniência falsa.
LIMIAR_CORRESPONDENCIA = 0.5


def _palavras_de_conteudo(texto: str) -> set[str]:
    return set(re.findall(r"\w{4,}", texto.lower()))


def correspondente(antigo: str, novos: list[str]) -> int | None:
    """Índice do trecho novo que continua o `antigo`, ou None se nenhum continua.

    Por CONTEÚDO e não por posição: a ordem muda quando o corte muda, e
    `questao.fonte_chunks` guarda id cru — reindexar sem remapear deixava a
    questão do aluno apontando pra trecho apagado."""
    palavras = _palavras_de_conteudo(antigo)
    if not palavras or not novos:
        return None
    cobertura = [len(palavras & _palavras_de_conteudo(n)) / len(palavras) for n in novos]
    melhor = max(range(len(novos)), key=cobertura.__getitem__)
    return melhor if cobertura[melhor] >= LIMIAR_CORRESPONDENCIA else None


def chunk_paginado(paginas: list[str], alvo: int = 1100, sobreposicao: int = 150) -> list[dict]:
    """O corte de `chunk_generico`, sabendo em que página cada trecho começa.

    A página é a do primeiro parágrafo NOVO do trecho — a sobreposição herdada do
    anterior não conta, porque é dele. `chunk.pagina` estava vazio em 100% dos
    trechos, e o tutor, perguntado "em que página está isso?", não tinha como
    responder."""
    itens = [(p.strip(), n) for n, pagina in enumerate(paginas, 1)
             for p in re.split(r"\n\s*\n", pagina) if p.strip()]
    chunks, atual, pagina = [], "", None
    for p, n in itens:
        if len(atual) + len(p) + 2 <= alvo:
            if not atual:
                pagina = n
            atual = f"{atual}\n\n{p}" if atual else p
        else:
            if atual:
                chunks.append((atual, pagina))
            atual = (atual[-sobreposicao:] + "\n\n" + p) if atual else p
            pagina = n
    if atual:
        chunks.append((atual, pagina))
    return [{"texto": c, "norma": None, "artigo": None, "paragrafo": None,
             "inciso": None, "rubrica": None, "secao": None, "pagina": n}
            for c, n in chunks if len(c) > 80]


def chunk_generico(texto: str, alvo: int = 1100, sobreposicao: int = 150) -> list[dict]:
    """Texto sem páginas (TXT, HTML, link): o mesmo corte, sem número de página."""
    return [{**c, "pagina": None} for c in chunk_paginado([texto], alvo, sobreposicao)]
