"""
Leitura em sequência: o material do aluno lido NA ORDEM dele, dentro do chat.

POR QUE ISTO EXISTE (24/09/2026)
--------------------------------
Numa conversa real o aluno pediu, cinco vezes e com palavras diferentes, a
mesma coisa: "estudar na ordem", "todo o conteúdo do tópico 2.1", "na ordem
de aprendizado que os materiais que eu subi trazem", "não quero responder
perguntas", "como se estivesse lendo a apostila, sem pausas". Recebeu uma frase
de conceito e uma pergunta por turno, e a conversa derivou para o inquérito
policial do CPP — porque a busca por SENTIDO não conhece ordem: cada turno
voltava com os seis trechos mais parecidos com a fala, de qualquer lugar.

A busca vetorial continua sendo o caminho de quem PERGUNTA. Quem pede para
AVANÇAR ("continua", "segue", "certo" logo depois de uma leitura) recebe os
próximos trechos do mesmo material, por `chunk.ordem` — um SELECT barato, sem
embedding, e o prompt recebe só a janela da vez.

O MARCADOR NÃO É ESTADO NOVO. Cada resposta do tutor já grava em
`mensagem.fontes` os trechos que usou; a leitura marca os dela com
`sequencial` e `ordem`, e "onde paramos" é a última mensagem assim
(`conversa.ultima_leitura`). Sem migração, sem coluna para invalidar.

Tudo que decide aqui é PURO e testável sem banco; só `janela`,
`documento_para` e `planejar` tocam o banco.
"""
import re

from . import assunto, db, retrieval

VERSAO = "leitura-v4"

# Quanto texto do material entra por turno. Um trecho tem ~1100 caracteres
# (`chunking.chunk_paginado`); três a quatro dão uma seção de apostila — o
# bastante para uma explicação inteira, pouco o bastante para caber com folga
# no prompt e na resposta.
JANELA_CHARS = 4500
MAX_TRECHOS = 6
# MEDIDO em 24/09/2026 com o modelo real: a resposta fica perto de 300 palavras
# qualquer que seja o tamanho do trecho. Com 3500 caracteres isso era 60–80% do
# texto; dobrada para 7000 (14000 no começo), a mesma resposta virou 15% —
# resumo, o contrário do "igual ao PDF" pedido. A janela média e a META DE
# TAMANHO (`meta_de_palavras`) no prompt é que fazem a aula cobrir o trecho.
PROPORCAO_DA_AULA = 0.7

# Quanto do trecho seguinte vai como "a seguir no material": só para o tutor
# anunciar o próximo passo sem inventá-lo.
CHARS_DO_PROXIMO = 300

# COMEÇAR A LER. As frases são as da conversa real e as vizinhas delas; nenhuma
# fala de disciplina ou concurso. "na ordem" só conta seguido do que se lê
# (material, apostila, edital…), de "de aprendizado", ou encerrando a oração:
# "ordem" é também matéria — "na ordem social", "a ordem econômica", "a ordem
# de vocação hereditária" são perguntas, não pedido de leitura.
RE_INICIO = re.compile(
    r"(?i)(?:\bna\s+ordem\b(?=\s*(?:$|[,.;!?]|d[oa]s?\s+(?:material|materiais|apostila|aula|edital"
    r"|conte[uú]do|curso|livro)|de\s+aprendizado|que\b|e\b|entend|pra\b|para\b))"
    r"|\bcomo\s+(?:se\s+(?:estivesse|fosse)\s+)?(?:lendo\s+)?(?:uma\s+|a\s+)?apostila"
    r"|\bleitura\s+corrida|\bler\s+o\s+material|\baula\s+expositiva"
    # Medido em 24/09/2026, falas que pediam leitura e não disparavam:
    # "seguir a ordem do edital", "um aulão", "como se tivesse lendo um pdf",
    # "aprender todo o conceito disso".
    r"|\b(?:seguir|sigo|siga|segue|seguindo)\s+(?:a\s+|na\s+)?ordem\s+d[oa]s?\s+"
    r"(?:edital|material|materiais|apostila|aula|conte[uú]do|curso|livro)"
    r"|\baul[aã]o\b|\b(?:lendo|ler)\s+(?:um|uma|o|a)?\s*(?:pdf|livro|apostila|material)\b"
    r"|\btodo\s+o\s+conceito"
    # "vamo lê o conteúdo de constitucional pela apostila" (bateria de 24/09/2026)
    r"|\bpel[ao]\s+(?:apostila|material|pdf|livro)\b"
    r"|\bdo\s+come[cç]o\b|\bdesde\s+o\s+in[ií]cio"
    r"|\btodo\s+o\s+conte[uú]do|\bconte[uú]do\s+(?:inteiro|completo|todo)"
    r"|\bsem\s+(?:pausas?|perguntas?)\b"
    r"|\bn[aã]o\s+quero\s+(?:responder\s+)?perguntas?"
    r"|\bs[oó]\s+(?:quero\s+)?(?:a\s+)?(?:explica[cç][aã]o|hist[oó]ria))")

# AVANÇAR, dito como pedido: vale mesmo que o turno anterior tenha sido uma
# dúvida no meio da leitura — "continua" retoma de onde a leitura parou.
# Aceita até duas palavras de muleta antes ("em continua o conteúdo de…",
# "ok, continua", "então segue") — medido em 24/09/2026, "em continua" caía na
# busca. Muleta é lista fechada: "não continua" não pode virar avanço.
RE_AVANCO = re.compile(
    r"(?i)^\s*(?:(?:em|ent[aã]o|ok|okay|certo|agora|bom|beleza|blz|t[aá]|show|entendi|vamos)"
    r"\b[\s,.!]*){0,2}(?:pode\s+)?(?:continu[aeo]r?|segu[eai]r?|pr[oó]xim[oa]|avan[cç]a(?:r)?"
    r"|prossig\w*|prossegu\w*"
    r"|vamos\s+(?:em\s+frente|l[aá])|manda\s+(?:mais|o\s+resto)|e\s+depois|mais)\b")

# RETOMAR: "volta pro Administrativo, continua de onde parou", "retoma de onde
# paramos" — não começa com "continua", e caía na busca (bateria de 24/09/2026).
RE_RETOMA = re.compile(
    r"(?i)\b(?:de\s+onde\s+(?:parou|paramos|parei)|onde\s+(?:parou|paramos|parei)|retoma\w*"
    r"|volta\w*\s+(?:pr[oa]|para\s+[oa]|ao|[aà])\b)")

# CONCORDAR não é pedir nada — só vira "continua" quando o turno anterior foi
# de leitura. Depois de uma pergunta do tutor, "certo" é resposta a ela.
RE_CONCORDA = re.compile(
    r"(?i)^\s*(?:certo|ok(?:ay)?|entendi|blz|beleza|sim|show|t[aá]|fechou|perfeito"
    r"|legal|uhum|aham|hum+)\W*$")

# MESMA JANELA, MAIS FUNDO: o aluno não quer o próximo trecho, quer este melhor.
RE_APROFUNDA = re.compile(
    r"(?i)\b(?:aprofund\w*|detalh\w*|explica\s+melhor|mais\s+devagar|n[aã]o\s+entendi"
    r"|resum\w*\s+demais|muito\s+resumid\w*|mais\s+complet\w*|complet\w*\s+(?:como|igual)\b)")

# PLANEJAR NÃO É LER. "Um mapa mental e uma trilha de aprendizagem seguindo a
# ordem do edital" disparou leitura em 24/09/2026 e abriu uma apostila; o pedido
# era o do tipo 3 do prompt (mapa/planejamento).
RE_PLANEJAMENTO = re.compile(
    r"(?i)\b(?:mapa\s+mental|mapa\s+da\s+mat[eé]ria|trilha|plano\s+de\s+estudos?|cronograma"
    r"|roteiro\s+de\s+estudos?)\b")

# "Do começo" recomeça o material mesmo que ele já tenha sido lido em parte.
RE_DO_COMECO = re.compile(r"(?i)\b(?:do\s+come[cç]o|desde\s+o\s+in[ií]cio|do\s+zero|de\s+novo)\b")

# Linha de sumário: título, pontilhado ou reticências, número de página.
RE_LINHA_DE_SUMARIO = re.compile(r"(?:\.{4,}|…{2,}|(?:\.\s){3,})\s*\d{1,3}\s*$")
LINHAS_DE_SUMARIO = 3

# O vocabulário de PEDIR LEITURA não é assunto: "quero ler como apostila, sem
# pausas" não nomeia matéria nenhuma, e não pode trocar o material em leitura.
VOCABULARIO_DE_LEITURA = set("""
ordem apostila leitura corrida lendo ler material materiais conteudo conteúdo inteiro
completo todo toda pausa pausas pergunta perguntas explicacao explicação historia
história aula expositiva comeco começo inicio início aprender estudar entender ver
primeiro momento neste nesse falei sequencia sequência aprendizado subi trazem
""".split())


def meta_de_palavras(trechos: list[dict]) -> int:
    """Quantas palavras a aula deste turno deve ter: ~70% do texto de conteúdo
    da janela (sumário fora). Sem a meta, o modelo resume."""
    palavras = sum(len(c["texto"].split()) for c in trechos if not e_sumario(c["texto"]))
    return max(150, int(palavras * PROPORCAO_DA_AULA))


def e_sumario(texto: str) -> bool:
    """O trecho é (ou contém) o sumário da aula? Vira roteiro, e não conta na
    janela: um sumário de duas páginas comeria a vez do conteúdo."""
    return sum(1 for l in (texto or "").splitlines()
               if RE_LINHA_DE_SUMARIO.search(l.strip())) >= LINHAS_DE_SUMARIO


def intencao(fala: str | None, ultima_foi_leitura: bool, ha_leitura: bool) -> str | None:
    """"inicio", "continua", "aprofunda" ou None (turno de busca comum). PURO.

    `ultima_foi_leitura`: o turno anterior do tutor foi de leitura.
    `ha_leitura`: existe leitura em andamento nesta conversa, ainda que o turno
    anterior tenha sido uma dúvida respondida pela busca."""
    fala = fala or ""
    if RE_PLANEJAMENTO.search(fala):
        return None
    if RE_INICIO.search(fala) or RE_RETOMA.search(fala):
        return "inicio"
    if ha_leitura and RE_AVANCO.search(fala):
        return "continua"
    if ultima_foi_leitura and RE_APROFUNDA.search(fala):
        return "aprofunda"
    if ultima_foi_leitura and RE_CONCORDA.match(fala):
        return "continua"
    return None


def nomeia_outro_assunto(fala: str | None) -> bool:
    """A fala de "começar a ler" traz assunto próprio, além do pedido de leitura?
    Sem assunto próprio ("já falei, como apostila, sem pausas"), é a leitura em
    andamento que continua — recomeçar do zero seria punir a insistência."""
    sobra = [p for p in assunto.palavras_de_conteudo(fala or "")
             if assunto._sem_acento(p) not in {assunto._sem_acento(v) for v in VOCABULARIO_DE_LEITURA}]
    return len(sobra) >= 2


def _selecionar(linhas: list[dict], limite: int = JANELA_CHARS) -> tuple[list[dict], dict | None]:
    """A janela e o trecho seguinte a ela, das linhas já em ordem. PURO."""
    janela, total = [], 0
    teto = MAX_TRECHOS * (2 if limite > JANELA_CHARS else 1)
    for c in linhas:
        sumario = e_sumario(c["texto"])
        if janela and not sumario and (total + len(c["texto"]) > limite
                                       or len(janela) >= teto):
            return janela, c
        janela.append(c)
        if not sumario:
            total += len(c["texto"])
    return janela, None


# A LEITURA NÃO PODE REPETIR NEM CORTAR FRASE. `chunk_paginado` começa cada trecho
# com os últimos 150 caracteres do anterior (sobreposição, boa para a BUSCA), e
# o PDF quebra frase na virada de página. Lidos em sequência, os dois apareceram
# no mesmo dia (24/09/2026): um turno terminou em "que serve para esclarecer e",
# o seguinte abriu em "prestar informações à Justiça". Avisar o modelo do corte
# foi pior — ele passou a PULAR o começo do trecho novo, conteúdo que nunca
# tinha explicado. A emenda é feita aqui, pela mesma regra dos dois lados: o
# turno que termina no meio da frase leva o resto dela, e o seguinte a pula.
RE_FIM_DE_FRASE = re.compile(r"""[.!?:;]["'”»)\]]*\s*$""")
RE_PRIMEIRO_FIM = re.compile(r"""[.!?]["'”»)\]]*(?=\s|$)""")
MAX_EMENDA = 600


def sem_sobreposicao(anterior: str | None, texto: str) -> str:
    """`texto` sem o pedaço do fim de `anterior` que ele repete no começo. PURO."""
    if not anterior:
        return texto
    for tam in range(min(len(anterior), len(texto), 400), 20, -1):
        if texto.startswith(anterior[-tam:]):
            return texto[tam:].lstrip()
    return texto


def _resto_da_frase(texto: str) -> tuple[str, str]:
    """(o pedaço até o primeiro fim de frase, o restante). PURO. Sem fim de frase
    por perto, não há o que emendar: o corte fica, e é melhor que colar metade
    de uma página."""
    m = RE_PRIMEIRO_FIM.search(texto[:MAX_EMENDA])
    if not m:
        return "", texto
    return texto[:m.end()], texto[m.end():].lstrip()


def emendar(trechos: list[dict], anterior: str | None, seguinte: dict | None) -> list[dict]:
    """Os trechos da janela prontos para ler em sequência. PURO — devolve
    cópias; `chunk.texto` no banco não muda."""
    prontos, antes = [], anterior
    for c in trechos:
        texto = sem_sobreposicao(antes, c["texto"])
        if antes is not None and not RE_FIM_DE_FRASE.search(antes.rstrip()):
            _, texto = _resto_da_frase(texto)
        prontos.append({**c, "texto": texto})
        antes = c["texto"]
    if prontos and seguinte and not RE_FIM_DE_FRASE.search(prontos[-1]["texto"].rstrip()):
        cabeca, _ = _resto_da_frase(sem_sobreposicao(antes, seguinte["texto"]))
        if cabeca:
            prontos[-1] = {**prontos[-1], "texto": f"{prontos[-1]['texto'].rstrip()} {cabeca}"}
    return prontos


def janela(documento_id: int, depois_de: int, usuario_id: int) -> tuple[list[dict], dict | None]:
    """Os próximos trechos do material, em ordem, e o que vem depois deles."""
    linhas = db.query(
        f"""SELECT {retrieval.CAMPOS}
              FROM chunk c JOIN documento d ON d.id = c.documento_id
             WHERE c.documento_id = %(d)s AND c.ordem > %(o)s AND {retrieval.DONO}
             ORDER BY c.ordem
             LIMIT {MAX_TRECHOS * 3}""",
        {"d": documento_id, "o": depois_de, "uid": usuario_id})
    # O COMEÇO de um material é capa, sumário e apresentação do curso e do
    # professor em qualquer apostila — medido na Aula 00 de Ciências Forenses:
    # os trechos 2 a 4 eram "seja bem-vindo(a)", e-mail e Instagram, e o turno
    # saiu com 65 palavras. Janela dobrada no começo chega ao conteúdo.
    if depois_de < 0:
        return _selecionar(linhas, JANELA_CHARS * 2)
    return _selecionar(linhas)


def mesma_janela(ids: list[int], usuario_id: int) -> list[dict]:
    return db.query(
        f"""SELECT {retrieval.CAMPOS}
              FROM chunk c JOIN documento d ON d.id = c.documento_id
             WHERE c.id = ANY(%(i)s) AND {retrieval.DONO}
             ORDER BY c.ordem""", {"i": ids, "uid": usuario_id})


def documento_para(consulta: str | None, usuario_id: int, mesa_id: int | None) -> int | None:
    """O material DO ALUNO dono do trecho mais bem colocado na busca, entre aula
    e resumo dele. Lei seca e jurisprudência não se leem "como apostila" — são
    poço de consulta. É o ÚLTIMO recurso de `escolher_material`: ver lá por quê."""
    if not consulta:
        return None
    for c in retrieval.buscar(consulta, n=12, usuario_id=usuario_id, mesa_id=mesa_id):
        if c.get("dono") == usuario_id and c.get("tipo") in ("aula", "resumo"):
            return c["documento_id"]
    return None


def nomes_da_disciplina(disciplina: str, mapa: dict | None) -> list[str]:
    return list({disciplina, *((mapa or {}).get(disciplina) or [])})


def da_disciplina(documento_id: int, disciplina: str, mapa: dict | None) -> bool:
    r = db.exec1("SELECT disciplina FROM documento WHERE id = %(i)s", {"i": documento_id})
    return bool(r and r["disciplina"] in nomes_da_disciplina(disciplina, mapa))


def primeiro_material_da_disciplina(disciplina: str, mapa: dict | None,
                                    usuario_id: int) -> int | None:
    """O primeiro material da disciplina, pela ordem do título ("aula-00"
    antes de "aula-01"). `disciplina` é o nome do EDITAL; o mapa da mesa diz
    quais nomes do acervo moram nela ("Criminalística" em "Ciências Forenses")."""
    nomes = nomes_da_disciplina(disciplina, mapa)
    r = db.exec1(
        """SELECT id FROM documento
            WHERE usuario_id = %(u)s AND disciplina = ANY(%(n)s)
              AND tipo IN ('aula', 'resumo') AND status = 'pronto'
            ORDER BY titulo LIMIT 1""", {"u": usuario_id, "n": nomes})
    return r["id"] if r else None


def escolher_material(fala: str | None, consulta: str | None, historico: list[dict] | None,
                      material_recente: int | None, disciplinas: list[str] | None,
                      mapa: dict | None, usuario_id: int, mesa_id: int | None,
                      foco: str | None = None, marcadores: dict | None = None) -> int | None:
    """Qual material do aluno ler, quando a leitura começa.

    A BUSCA É O ÚLTIMO RECURSO, e foi medido por quê (24/09/2026, conversa real
    repetida com o modelo): "eu queria estudar na ordem, entender o conceito
    inteiro da matéria, depois fazer questões" fala SOBRE estudar e não nomeia
    matéria nenhuma; buscada, devolveu a lista de gabaritos da apostila de
    Direito Administrativo — no meio de uma conversa sobre Ciências Forenses.
    O modelo recebeu esse trecho e escreveu sobre perícia do mesmo jeito,
    atribuindo à apostila errada.

    Por isso, nesta ordem: a disciplina que a própria fala nomeia; o material
    do aluno que o tutor acabou de citar (é dele que a conversa trata); a
    disciplina nomeada nas falas recentes; e só então a busca."""
    # A MATÉRIA EM FOCO manda (`assunto.disciplina_em_foco`): o material citado há
    # pouco pode ser de outra — medido em 24/09/2026, o aluno trocou para
    # Legislação Institucional e o último material citado era de Constitucional.
    # Sem material da matéria em foco, não se lê nada: ler a apostila de outra
    # matéria seria ensinar o assunto errado com cara de leitura.
    citada = foco or assunto.disciplina_citada(fala or "", disciplinas)
    if citada:
        # O material dela que foi LIDO por último, se houver: "continua o
        # conteúdo de Administrativo" retoma de onde parou, não do primeiro.
        for doc in sorted((marcadores or {}), key=lambda d: marcadores[d]["quando"], reverse=True):
            if da_disciplina(doc, citada, mapa):
                return doc
        return primeiro_material_da_disciplina(citada, mapa, usuario_id)
    if material_recente and (not foco or da_disciplina(material_recente, foco, mapa)):
        return material_recente
    for t in reversed((historico or [])[-8:]):
        if t.get("autor") == "aluno" and (d := assunto.disciplina_citada(t.get("texto") or "",
                                                                         disciplinas)):
            achado = primeiro_material_da_disciplina(d, mapa, usuario_id)
            if achado:
                return achado
    return documento_para(consulta, usuario_id, mesa_id)


def proximo_material(documento_id: int, usuario_id: int) -> dict | None:
    """O material seguinte da mesma disciplina, pela ordem do título ("aula-00",
    "aula-01"): é a ordem em que o curso foi montado."""
    atual = db.exec1("SELECT disciplina, titulo FROM documento WHERE id = %(i)s",
                     {"i": documento_id})
    if not atual or not atual["disciplina"]:
        return None
    return db.exec1(
        """SELECT id, titulo, assunto FROM documento
            WHERE usuario_id = %(u)s AND disciplina = %(d)s AND tipo IN ('aula', 'resumo')
              AND status = 'pronto' AND titulo > %(t)s
            ORDER BY titulo LIMIT 1""",
        {"u": usuario_id, "d": atual["disciplina"], "t": atual["titulo"]})


def planejar(fala: str | None, consulta: str | None, ultima: dict | None,
             usuario_id: int | None, mesa_id: int | None, *,
             historico: list[dict] | None = None, material_recente: int | None = None,
             disciplinas: list[str] | None = None, mapa: dict | None = None,
             foco: str | None = None, marcadores: dict | None = None) -> dict | None:
    """O plano de leitura deste turno, ou None para seguir pela busca comum.

    `ultima` é `conversa.ultima_leitura`: {"documento_id", "ordem", "ids",
    "foi_a_ultima"} ou None. `marcadores` é `conversa.marcadores_de_leitura`:
    onde o aluno parou em CADA material, em qualquer conversa — é o que faz
    voltar a uma matéria retomar dela em vez de recomeçar."""
    if not usuario_id:
        return None
    qual = intencao(fala, bool(ultima and ultima["foi_a_ultima"]), bool(ultima))
    # "Continua o conteúdo de Administrativo" sem leitura nesta conversa: é
    # pedido para ler a matéria nomeada, retomando de onde parou nela.
    if not qual and foco and RE_AVANCO.search(fala or "") and not RE_PLANEJAMENTO.search(fala or ""):
        qual = "inicio"
    if not qual:
        return None

    if qual == "aprofunda":
        trechos = mesma_janela(ultima["ids"], usuario_id)
        return {"intencao": qual, "trechos": trechos, "seguinte": None,
                "comeco": False, "fim": False, "proximo_material": None} if trechos else None

    # Leitura de OUTRA matéria não continua quando a conversa mudou de matéria.
    if ultima and foco and not da_disciplina(ultima["documento_id"], foco, mapa):
        ultima = None
        if qual in ("continua", "aprofunda"):
            qual = "inicio"
    if ultima and (qual == "continua" or not nomeia_outro_assunto(fala)):
        documento_id, depois_de = ultima["documento_id"], ultima["ordem"]
    else:
        documento_id = escolher_material(fala, consulta, historico, material_recente,
                                         disciplinas, mapa, usuario_id, mesa_id, foco, marcadores)
        if documento_id is None:
            return None
        if ultima and ultima["documento_id"] == documento_id:
            depois_de = ultima["ordem"]
        else:
            depois_de = (marcadores or {}).get(documento_id, {}).get("ordem", -1)
    if RE_DO_COMECO.search(fala or ""):
        depois_de = -1

    trechos, seguinte = janela(documento_id, depois_de, usuario_id)
    anterior = (db.exec1("SELECT texto FROM chunk WHERE documento_id = %(d)s AND ordem = %(o)s",
                         {"d": documento_id, "o": depois_de}) if depois_de >= 0 else None)
    trechos = emendar(trechos, anterior["texto"] if anterior else None, seguinte)
    return {"intencao": qual, "trechos": trechos, "seguinte": seguinte,
            "comeco": depois_de < 0, "fim": not trechos,
            "proximo_material": proximo_material(documento_id, usuario_id) if not seguinte else None,
            "documento_id": documento_id}
