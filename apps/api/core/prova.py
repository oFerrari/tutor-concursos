"""
QUESTÕES DE PROVA: o simulado que o aluno sobe vira banco de questões (037).

O QUE FAZ
---------
Lê o texto do material de tipo 'simulado' e separa cada questão: número,
texto-base (quando há), enunciado, alternativas, gabarito e comentário. Grava
em `questao` com `origem='prova'`, literal — o modelo não reescreve nada.

SEM MODELO, PELA ESTRUTURA. Prova de concurso tem forma fixa: número da questão
("12."), alternativas ("A) …"), e o gabarito numa de três formas — junto da
questão ("Gabarito: C"), numa tabela ("1 2 3 … / C E D …") ou num arquivo só de
respostas, subido à parte. O modelo só entra para RESOLVER a questão que veio
sem gabarito nenhum, e isso fica marcado (`gabarito_fonte='tutor'`).

O NÚMERO É SEQUENCIAL. Enunciado de prova cita listas numeradas ("1. Cavalo de
troia … 4. Zumbi"); aceitar todo "N." como começo de questão quebraria a prova
em pedaços. Só vale o número seguinte ao último aceito.

A DISCIPLINA vem dos títulos do próprio simulado ("Língua Portuguesa",
"Raciocínio Lógico-Matemático"), casados com as disciplinas do edital da mesa;
o assunto, do índice de assuntos (036) do trecho em que a questão está.

O QUE FICA PARA DEPOIS: servir a mesma questão em outro formato (C/E, por
extenso, híbrido). O banco guarda o literal — alternativas e letra — para que
esses modos saiam daqui sem duplicar nada.
"""
import json
import math
import re

from . import assunto, db, llm

VERSAO = "prova-v6"

LETRAS = "ABCDEF"
MIN_QUESTOES = 3          # menos que isso não é prova (e um arquivo de gabarito tem 0)
LOTE_RESOLVER = 10        # questões sem gabarito por chamada ao modelo
MAX_LINHAS_ALTERNATIVA = 4

# --------------------------------------------------------------- texto (PURO)
RE_INICIO = re.compile(r"^\s*(?:quest[ãa]o\s+)?0*(\d{1,3})\s*[.)\-–]\s+(\S.*)$", re.I)
RE_ALTERNATIVA = re.compile(r"^\s*\(?([A-Fa-f])\s*[).\-–]\s*(\S.*)$")
RE_GABARITO_INLINE = re.compile(
    r"(?i)^\s*(?:gabarito|resposta(?:\s+correta)?|alternativa\s+correta)\s*[:\-–]\s*"
    r"(?:letra\s+|alternativa\s+)?\(?([A-F]|certo|errado|correto|errada|certa)\b\)?")
RE_COMENTARIO = re.compile(r"(?i)^\s*coment[áa]rios?(?:\s+do\s+professor)?\s*:?\s*$")
# "Portanto, gabarito letra C." / "o gabarito é a alternativa B." — fecha o comentário.
RE_FECHO = re.compile(r"(?i)\b(?:portanto|logo|assim|desse\s+modo|pelo\s+exposto)\b[^.\n]{0,90}"
                      r"(?:gabarito|alternativa\s+correta|letra)[^.\n]*\.")
RE_JULGUE = re.compile(r"(?i)\bjulgue\b|\bcerto\s+ou\s+errado\b|\(\s*\)\s*certo")
RE_COMECO_DE_TEXTO = re.compile(r"(?i)^\s*(?:leia|texto|considere|observe|analise|com\s+base|julgue)\b")
RE_TEXTO_PARA = re.compile(r"(?i)quest(?:ão|ões|oes)\s+(\d{1,3})\s*(?:a|e|até|-)\s*(\d{1,3})")


def _letra_ou_ce(valor: str) -> str | None:
    v = (valor or "").strip().upper()
    if v in ("CERTO", "CERTA", "CORRETO"):
        return "C*"
    if v in ("ERRADO", "ERRADA"):
        return "E*"
    return v if len(v) == 1 and v in LETRAS else None


def tabela_de_gabarito(texto: str) -> dict[int, str]:
    """{número: letra} das tabelas e listas de gabarito do texto. PURO.

    Duas formas: a TABELA (uma linha de números seguidos, a de baixo com o mesmo
    tanto de letras — "1 2 3 … 10" / "C E D … B") e a LISTA ("1-C 2-E", "01. A",
    "1) C"). Letra solta no meio de um parágrafo não conta: a lista exige três
    pares ou mais na mesma linha, ou uma linha que seja só o par."""
    gab: dict[int, str] = {}
    linhas = [l.strip() for l in (texto or "").split("\n")]

    def numeros(l):
        ns = l.split()
        if len(ns) >= 3 and all(n.isdigit() for n in ns):
            ns = [int(n) for n in ns]
            return ns if all(b - a == 1 for a, b in zip(ns, ns[1:])) else None
        return None

    def letras(l):
        xs = l.upper().split()
        return xs if len(xs) >= 3 and all(len(x) == 1 and x in LETRAS for x in xs) else None

    # Linhas de números seguidas de linhas de letras — uma a uma ("1 … 10" /
    # "C E …"), ou o bloco inteiro de números antes do de letras, que é como a
    # tabela de várias linhas sai do PDF (medido no simulado comentado do aluno).
    i = 0
    while i < len(linhas):
        bloco_n = []
        while i < len(linhas) and numeros(linhas[i]):
            bloco_n.append(numeros(linhas[i]))
            i += 1
        bloco_l = []
        while bloco_n and i < len(linhas) and letras(linhas[i]):
            bloco_l.append(letras(linhas[i]))
            i += 1
        if bloco_n and len(bloco_l) == len(bloco_n) and all(len(a) == len(b) for a, b in zip(bloco_n, bloco_l)):
            for ns, ls in zip(bloco_n, bloco_l):
                gab.update(zip(ns, ls))
        if not bloco_n:
            i += 1
    # LISTA ("1-C 2-E 3-A", ou uma linha por par) só completa a tabela, nunca a
    # sobrescreve, e precisa de números crescentes: "4 – 1 – 3 – 2" num comentário
    # sobre associação não é gabarito (trocava o da questão 20 no simulado real).
    for l in linhas:
        pares = [(int(n), x.upper()) for n, x in
                 re.findall(r"\b0*(\d{1,3})\s*[-–.:)]\s*([A-F])\b(?![a-zà-ú])", l)]
        so_par = re.fullmatch(r"0*(\d{1,3})\s*[-–.:)]\s*([A-Fa-f])", l)
        if len(pares) >= 3 and all(b[0] > a[0] for a, b in zip(pares, pares[1:])):
            for n, x in pares:
                gab.setdefault(n, x)
        elif so_par:
            gab.setdefault(int(so_par.group(1)), so_par.group(2).upper())
    return gab


def _cabecalho_de_disciplina(linha: str, disciplinas: list[str]) -> str | None:
    """A linha É um título de disciplina ("Língua Portuguesa") — e não só a menciona.

    Linha de PDF em duas colunas é curta e quebrada no meio da frase ("da
    principiologia do Direito Penal"); bastar conter o nome trocava a disciplina
    de metade da prova (medido no simulado real)."""
    l = " ".join(linha.split()).rstrip(":")
    if not l or l.endswith((".", "?", ";")) or RE_ALTERNATIVA.match(l):
        return None
    for d in sorted(disciplinas, key=len, reverse=True):
        if _nome_norm(l) == _nome_norm(d) or (_nome_norm(l).endswith(_nome_norm(d))
                                               and len(l.split()) <= len(d.split()) + 3):
            return d
    return None


RE_MARCA_GABARITO = re.compile(r"(?i)\s*(gabarito\s*:\s*(?:letra\s+|alternativa\s+)?\(?(?:[A-F]|certo|errado|correto)\b\)?)")
RE_MARCA_COMENTARIO = re.compile(r"(?i)\s*(coment[áa]rios?(?:\s+do\s+professor)?\s*:)")
RE_MARCA_ALTERNATIVA = re.compile(r"\s+([A-F])\)\s+(?=\S)")
RE_MARCA_QUESTAO = re.compile(r"\s(\d{1,3})\.\s+(?![A-F]\))(?=[A-ZÀ-ÖØ-Þ<“\"(])")


def ressegmentar(texto: str) -> str:
    """Põe cada marca da prova no começo de uma linha. PURO.

    O texto do PDF já chega REMONTADO (`chunking.desquebrar`, para o justificado
    que saía uma palavra por linha), e isso junta linhas que a prova separava:
    "…boa ou má. 1. Levando…", "E) Repetir… Gabarito: C COMENTÁRIO DO PROFESSOR:
    Caveiras…". Medido no simulado comentado do aluno (30/09/2026): 0 de 100
    questões achadas. O número de questão no meio de uma frase que não é questão
    ("em 2021. A banca…") não estraga nada: só vale o número seguinte."""
    # O número da questão PRIMEIRO: as outras marcas, depois, ganham linha própria
    # mesmo quando um número solto ("A = 5. Gabarito: E") ficou colado nelas.
    t = RE_MARCA_QUESTAO.sub(lambda m: "\n" + m.group(1) + ". ", texto or "")
    t = RE_MARCA_GABARITO.sub(lambda m: "\n" + m.group(1) + "\n", t)
    t = RE_MARCA_COMENTARIO.sub(lambda m: "\n" + m.group(1) + "\n", t)
    return RE_MARCA_ALTERNATIVA.sub(lambda m: "\n" + m.group(1) + ") ", t)


def _nome_norm(t: str) -> str:
    return assunto._sem_acento(re.sub(r"\s+", " ", t or "")).lower().strip()


def titulo_de_disciplina(trecho: str, disciplinas: list[str], mapa: dict | None = None,
                         so_conhecida: bool = False) -> tuple[str | None, str]:
    """(disciplina, resto) de um trecho que pode começar com o título de uma seção
    da prova ("CONHECIMENTOS GERAIS Língua Portuguesa Leia o texto…"). PURO.

    O título vira a disciplina do EDITAL quando casa com uma (ou com um nome de
    material ligado a ela pelo mapa da mesa: "Direito Penal" → "Direito Penal e
    Legislação Penal Extravagante"); senão, fica o título do próprio simulado."""
    t = " ".join((trecho or "").split())
    t = re.sub(r"^(?:[A-ZÀ-ÖØ-Þ]{2,}\s+){1,4}(?=[A-ZÀ-ÖØ-Þ][a-zà-ÿ])", "", t)
    nomes = [(d, d) for d in disciplinas] + [(v, k) for k, vs in (mapa or {}).items() for v in vs]
    for nome, canonico in sorted(nomes, key=lambda x: -len(x[0])):
        if _nome_norm(t).startswith(_nome_norm(nome)):
            return canonico, t[len(nome):].strip()
    palavras = t.split()
    if t and len(palavras) <= 18 and "." not in t and t[0].isupper():
        conhecida = (assunto.disciplina_citada(t, disciplinas)
                     or next((k for k, vs in (mapa or {}).items() for v in vs if _nome_norm(v) == _nome_norm(t)), None))
        if conhecida or not so_conhecida:
            return conhecida or t, ""
    return None, t


def separar(texto: str, disciplinas: list[str] | None = None, mapa: dict | None = None) -> list[dict]:
    """As questões do texto, na ordem. Cada uma: {numero, texto_base, enunciado,
    alternativas: [(letra, texto)], gabarito ('A'..'F', 'C*'/'E*' para C/E, ou
    None), comentario, disciplina}. PURO.

    O bloco de cada questão vai do número dela ao número seguinte. Dentro dele:
    enunciado até a primeira alternativa; alternativas até o gabarito; e o que
    sobra é comentário — menos a cauda depois do fecho ("Portanto, gabarito letra
    C.") ou de um título de disciplina, que é o texto-base da questão seguinte."""
    disciplinas = disciplinas or []
    linhas = ressegmentar(texto).split("\n")
    # PROVA COMENTADA (gabarito junto de cada questão): a questão seguinte só
    # começa depois do gabarito da atual. Sem isso, um "2." numa lista dentro do
    # comentário da questão 1 abriria a questão 2 no lugar errado.
    comentada = sum(1 for l in linhas if RE_GABARITO_INLINE.match(l)) >= MIN_QUESTOES
    inicios, esperado, pendente, alternativas_da_pendente = [], None, None, 0
    for i, l in enumerate(linhas):
        if pendente and RE_ALTERNATIVA.match(l):
            alternativas_da_pendente += 1
        if comentada and RE_GABARITO_INLINE.match(l) and pendente:
            # Entre dois gabaritos, vale o ÚLTIMO "N." com o número esperado: o
            # comentário da anterior pode trazer uma lista numerada ("2. reler").
            inicios.append(pendente)
            esperado, pendente = pendente[1] + 1, None
            continue
        m = RE_INICIO.match(l)
        if not m:
            continue
        n = int(m.group(1))
        # "01 - B" é linha de gabarito, não enunciado.
        if re.fullmatch(r"(?i)\(?[A-F]\)?\.?|certo|errado|anulada", m.group(2).strip()):
            continue
        if not comentada:
            if esperado is None and n <= 3 or n == esperado:
                inicios.append((i, n, m.group(2)))
                esperado = n + 1
            continue
        if esperado is None and n <= 3 or n == esperado:
            pendente, alternativas_da_pendente = (i, n, m.group(2)), 0
        elif pendente and n == pendente[1] + 1 and alternativas_da_pendente >= 2:
            # A pendente tem alternativas e ficou sem gabarito: vale como está, e
            # esta é a seguinte. Sem alternativas, era uma lista do comentário.
            inicios.append(pendente)
            esperado, pendente, alternativas_da_pendente = n, (i, n, m.group(2)), 0
    if pendente:
        inicios.append(pendente)
    if not inicios:
        return []

    disciplina = None
    for l in linhas[:inicios[0][0]]:
        disciplina = _cabecalho_de_disciplina(l, disciplinas) or disciplina
    preambulo = "\n".join(linhas[:inicios[0][0]])
    # O título colado ao texto-base ("CONHECIMENTOS GERAIS Língua Portuguesa Leia…"):
    # procura no último parágrafo antes da questão 1.
    for bloco in reversed([b for b in re.split(r"\n\s*\n|(?<=\d)\n", preambulo) if b.strip()][-3:]):
        d, resto = titulo_de_disciplina(bloco, disciplinas, mapa, so_conhecida=True)
        if d:
            disciplina, preambulo = d, resto
            break
    base_seguinte = _texto_base(preambulo, disciplinas)
    questoes = []
    for k, (i, n, primeira) in enumerate(inicios):
        fim = inicios[k + 1][0] if k + 1 < len(inicios) else len(linhas)
        bloco = [primeira] + linhas[i + 1:fim]
        enunciado, alternativas, gabarito, comentario, cauda, sobra = [], [], None, [], [], []
        estado = "enunciado"
        for l in bloco:
            if estado in ("enunciado", "alternativas"):
                mg = RE_GABARITO_INLINE.match(l)
                if mg:
                    gabarito = _letra_ou_ce(mg.group(1))
                    estado = "comentario"
                    continue
                ma = RE_ALTERNATIVA.match(l)
                esperada = LETRAS[len(alternativas)] if len(alternativas) < len(LETRAS) else None
                if ma and ma.group(1).upper() == esperada:
                    alternativas.append([ma.group(1).upper(), ma.group(2).strip(), 0])
                    estado = "alternativas"
                    continue
                if estado == "alternativas" and l.strip():
                    # Alternativa de mais de uma linha continua; o que vem depois
                    # da última (prova sem comentário) é da questão seguinte.
                    if (alternativas and alternativas[-1][2] < MAX_LINHAS_ALTERNATIVA
                            and not RE_COMENTARIO.match(l) and not RE_COMECO_DE_TEXTO.match(l)
                            and not _cabecalho_de_disciplina(l, disciplinas)):
                        alternativas[-1][1] += " " + l.strip()
                        alternativas[-1][2] += 1
                    else:
                        estado = "sobra"
                        sobra.append(l)
                    continue
                if estado == "enunciado":
                    enunciado.append(l)
                continue
            if estado == "sobra":
                mg = RE_GABARITO_INLINE.match(l)
                if mg:                       # gabarito depois de uma linha solta
                    gabarito = _letra_ou_ce(mg.group(1))
                    if alternativas:
                        alternativas[-1][1] += " " + " ".join(x.strip() for x in sobra)
                    estado, sobra = "comentario", []
                    continue
                ma = RE_ALTERNATIVA.match(l)
                esperada = LETRAS[len(alternativas)] if len(alternativas) < len(LETRAS) else None
                if ma and alternativas and ma.group(1).upper() == esperada:
                    # A alternativa anterior era só mais longa: as linhas soltas são dela.
                    alternativas[-1][1] += " " + " ".join(x.strip() for x in sobra)
                    alternativas.append([ma.group(1).upper(), ma.group(2).strip(), 0])
                    estado, sobra = "alternativas", []
                    continue
                sobra.append(l)
                continue
            comentario.append(l)
        # A cauda do comentário que pertence à próxima questão (título, texto-base).
        cort = None
        for j, l in enumerate(comentario):
            d = _cabecalho_de_disciplina(l, disciplinas)
            if d:
                cort, nova_disc = j, d
                break
        if sobra:
            comentario, cauda = [], sobra
        elif cort is not None:
            disciplina_depois = nova_disc
            comentario, cauda = comentario[:cort], comentario[cort:]
        elif comentario:
            # O título da seção seguinte colado no fim do comentário, em uma ou duas
            # linhas: "…a letra C. Realidade Étnica, Social, … do Estado do Paraná".
            # Só vale se casar com disciplina do edital (ou nome de material dela).
            corpo = " ".join(" ".join(comentario).split())
            fim = re.search(r"[.!?:]\s+([A-ZÀ-ÖØ-Þ][^.!?:]{3,200})$", corpo)
            if fim and titulo_de_disciplina(fim.group(1), disciplinas, mapa, so_conhecida=True)[0]:
                comentario, cauda = [corpo[:fim.start(1)]], [fim.group(1)]
            else:
                corpo = "\n".join(comentario)
                fechos = list(RE_FECHO.finditer(corpo))
                if fechos and corpo[fechos[-1].end():].strip():
                    antes, depois = corpo[:fechos[-1].end()], corpo[fechos[-1].end():]
                    comentario, cauda = antes.split("\n"), depois.split("\n")
        q = {
            "numero": n,
            "texto_base": base_seguinte,
            "enunciado": _limpo("\n".join(enunciado)),
            "alternativas": [(a, _limpo(t)) for a, t, _ in alternativas],
            "gabarito": gabarito,
            "comentario": _limpo("\n".join(l for l in comentario if not RE_COMENTARIO.match(l))),
            "disciplina": disciplina,
        }
        if cort is not None:
            disciplina = disciplina_depois
        for l in cauda:
            disciplina = _cabecalho_de_disciplina(l, disciplinas) or disciplina
        resto_da_cauda = "\n".join(cauda)
        # Só disciplina CONHECIDA: "Leia o texto abaixo:" é curto e não é título.
        d, resto = titulo_de_disciplina(resto_da_cauda, disciplinas, mapa, so_conhecida=True)
        if d:
            disciplina, resto_da_cauda = d, resto
        base_seguinte = _texto_base(resto_da_cauda, disciplinas)
        questoes.append(q)

    # Texto-base declarado para várias ("Texto para as questões 3 a 5").
    for q in questoes:
        faixa = RE_TEXTO_PARA.search(q["texto_base"] or "")
        if faixa:
            a, b = int(faixa.group(1)), int(faixa.group(2))
            for outra in questoes:
                if a < outra["numero"] <= b and not outra["texto_base"]:
                    outra["texto_base"] = q["texto_base"]
    return [q for q in questoes if q["enunciado"]]


def _texto_base(trecho: str, disciplinas: list[str]) -> str | None:
    """O que vem antes do número da questão e é dela: "Leia o texto abaixo: …".
    Títulos de disciplina e de seção saem; menos de 80 caracteres não é texto."""
    linhas = [l for l in (trecho or "").split("\n")
              if l.strip() and not _cabecalho_de_disciplina(l, disciplinas)
              and not re.fullmatch(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ\s\-–|0-9º]{3,}", l.strip())]
    texto = _limpo("\n".join(linhas))
    return texto if len(texto) >= 80 else None


def _limpo(t: str) -> str:
    t = re.sub(r"[ \t]+", " ", t or "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def tipo_da_questao(q: dict) -> str | None:
    """'multipla_escolha', 'certo_errado' ou None (fica de fora por ora). PURO.

    Item C/E: sem alternativas e com gabarito Certo/Errado — ou "C"/"E" num
    enunciado que manda julgar. "C" num item com alternativas é a letra C."""
    if len(q["alternativas"]) >= 2:
        return "multipla_escolha"
    g = q.get("gabarito")
    if g in ("C*", "E*") or (g in ("C", "E") and RE_JULGUE.search(q["enunciado"] + (q["texto_base"] or ""))):
        return "certo_errado"
    return None


def e_so_gabarito(texto: str, disciplinas: list[str] | None = None) -> bool:
    """O arquivo traz respostas e não questões (o "gabarito à parte")."""
    return len(separar(texto, disciplinas)) < MIN_QUESTOES and len(tabela_de_gabarito(texto)) >= MIN_QUESTOES


# --------------------------------------------------------------- banco
def _texto_do_documento(documento_id: int) -> str:
    """O texto do ARQUIVO original (já sem moldura), e não dos trechos: trecho de
    PDF pode sobrepor o vizinho, e a sobreposição duplicaria o enunciado."""
    from . import material
    r = db.exec1("SELECT origem, titulo, arquivo FROM documento WHERE id = %(d)s", {"d": documento_id})
    if r and r["arquivo"] is not None:
        nome = r["origem"] or r["titulo"] or "material"
        dados = bytes(r["arquivo"])
        try:
            paginas = material._extrair_paginas(nome, dados)
            return "\n".join(paginas) if paginas is not None else material._extrair(nome, dados)
        except Exception:  # noqa: BLE001 — arquivo ilegível: cai nos trechos
            pass
    return "\n\n".join(c["texto"] for c in db.query(
        "SELECT texto FROM chunk WHERE documento_id = %(d)s ORDER BY ordem", {"d": documento_id}))


def _mesa_do(doc: dict) -> tuple[list[str], dict]:
    """(disciplinas do edital, mapa edital → nomes de material) da mesa do simulado.

    Simulado SEM mesa (o pool comum da biblioteca) usa as mesas do aluno, a mais
    recente primeiro: sem isso as seções da prova não casavam com nada e todas as
    questões saíam com a disciplina "Geral" (medido na bateria de 02/10/2026)."""
    try:
        from . import mesa
        mesas = ([doc["mesa_id"]] if doc.get("mesa_id") else
                 [r["id"] for r in db.query("SELECT id FROM mesa WHERE usuario_id = %(u)s ORDER BY id DESC",
                                            {"u": doc["usuario_id"]})])
        disciplinas, mapa = [], {}
        for mid in mesas:
            ctx = mesa.contexto(doc["usuario_id"], mid)
            disciplinas += [d for d in ctx.get("disciplinas") or [] if d not in disciplinas]
            for k, v in (ctx.get("mapa") or {}).items():
                mapa.setdefault(k, v)
        return disciplinas, mapa
    except Exception:  # noqa: BLE001 — sem mesa, a disciplina sai do título ou do documento
        return [], {}


def _disciplinas_da_mesa(doc: dict) -> list[str]:
    return _mesa_do(doc)[0]


def _chunk_da_questao(chunks: list[dict], q: dict) -> int | None:
    """O trecho REAL em que a questão está: o que traz o começo do enunciado."""
    alvo = re.sub(r"\s+", " ", q["enunciado"]).strip()[:60]
    for n in (60, 35, 20):
        pedaco = alvo[:n]
        for c in chunks:
            if pedaco and pedaco in c["norm"]:
                return c["id"]
    return None


def _tema(chunk_id: int, q: dict, disciplina: str | None) -> str:
    """A disciplina da seção da questão. O índice de assuntos não lê simulado
    (rotulava mal; ver `indice.indexar_assuntos`)."""
    return disciplina or f"Questão {q['numero']}"


def materias_dos_trechos(ids: list[int]) -> dict[int, set[str]]:
    """{trecho: disciplinas das questões de prova que estão nele}. Trecho que não é
    de simulado não aparece."""
    if not ids:
        return {}
    saida: dict[int, set[str]] = {}
    for r in db.query("""SELECT c AS id, q.disciplina FROM questao q, unnest(q.fonte_chunks) AS c
                          WHERE q.origem = 'prova' AND c = ANY(%(i)s)""", {"i": ids}):
        saida.setdefault(r["id"], set()).add(r["disciplina"])
    return saida


def rotulos_dos_trechos(ids: list[int]) -> dict[int, str]:
    """{trecho: "questão 28 · Raciocínio Lógico-Matemático"} — a citação de um trecho
    de simulado diz QUAL questão ele é, e de que matéria."""
    if not ids:
        return {}
    por: dict[int, list] = {}
    for r in db.query("""SELECT c AS id, q.numero_na_prova AS n, q.disciplina FROM questao q,
                                unnest(q.fonte_chunks) AS c
                          WHERE q.origem = 'prova' AND c = ANY(%(i)s) ORDER BY q.numero_na_prova""", {"i": ids}):
        por.setdefault(r["id"], []).append(r)
    rot = {}
    for cid, qs in por.items():
        nums = ", ".join(str(q["n"]) for q in qs[:3])
        rot[cid] = f"questão {nums} · {qs[0]['disciplina']}" if len(qs) == 1 else f"questões {nums} · {qs[0]['disciplina']}"
    return rot


def _resolver(pendentes: list[dict]) -> dict[int, str]:
    """O modelo resolve as questões que vieram sem gabarito. {número: letra}."""
    if not pendentes:
        return {}
    esq = {"type": "OBJECT", "properties": {"respostas": {"type": "ARRAY", "items": {"type": "OBJECT",
           "properties": {"numero": {"type": "INTEGER"}, "letra": {"type": "STRING", "enum": list(LETRAS)}},
           "required": ["numero", "letra"]}}}, "required": ["respostas"]}
    sis = ("Você resolve questões de concurso. Para cada uma, devolva a letra da alternativa correta. "
           "Leia o texto-base quando houver. Responda só com o JSON.")
    saida: dict[int, str] = {}
    for i in range(0, len(pendentes), LOTE_RESOLVER):
        lote = pendentes[i:i + LOTE_RESOLVER]
        prompt = "\n\n".join(
            f"QUESTÃO {q['numero']}\n" + (f"Texto-base: {q['texto_base']}\n" if q["texto_base"] else "") +
            q["enunciado"] + "\n" + "\n".join(f"{a}) {t}" for a, t in q["alternativas"]) for q in lote)
        try:
            r = llm.obter("indice").gerar_json(prompt, sis, max_tokens=2000, schema=esq, temperatura=0.0) or {}
        except llm.ErroLLM as e:
            print(f"[prova] sem modelo para resolver ({str(e)[:80]})")
            break
        validos = {q["numero"]: {a for a, _ in q["alternativas"]} for q in lote}
        for x in r.get("respostas") or []:
            if x.get("numero") in validos and x.get("letra") in validos[x["numero"]]:
                saida[x["numero"]] = x["letra"]
    return saida


def importar(documento_id: int, com_modelo: bool = True) -> dict:
    """Extrai as questões do simulado e grava/atualiza no banco. Idempotente:
    reimportar atualiza pela chave (documento, número), não duplica.

    Arquivo SÓ DE GABARITO: em vez de questões, liga-se ao simulado do mesmo
    aluno que tem questões sem resposta com aqueles números, e reimporta ele."""
    doc = db.exec1("""SELECT id, usuario_id, mesa_id, disciplina, tipo, gabarito_de FROM documento
                       WHERE id = %(d)s""", {"d": documento_id})
    if not doc or doc["tipo"] != "simulado" or not doc["usuario_id"]:
        return {"status": "ignorado"}
    disciplinas = _disciplinas_da_mesa(doc)
    texto = _texto_do_documento(documento_id)
    if e_so_gabarito(texto, disciplinas):
        alvo = _simulado_que_responde(doc, tabela_de_gabarito(texto))
        if not alvo:
            return {"status": "gabarito_sem_simulado"}
        db.query("UPDATE documento SET gabarito_de = %(a)s WHERE id = %(d)s", {"a": alvo, "d": documento_id})
        return {"status": "gabarito", "de": alvo, **importar(alvo, com_modelo)}

    questoes = separar(texto, disciplinas, _mesa_do(doc)[1])
    gab = tabela_de_gabarito(texto)
    for r in db.query("SELECT id FROM documento WHERE gabarito_de = %(d)s", {"d": documento_id}):
        gab.update(tabela_de_gabarito(_texto_do_documento(r["id"])))
    for q in questoes:
        if not q["gabarito"] and q["numero"] in gab:
            q["gabarito"], q["fonte"] = gab[q["numero"]], "arquivo"
        elif q["gabarito"]:
            q["fonte"] = "arquivo"
        q["tipo"] = tipo_da_questao(q)
        if q["tipo"] == "multipla_escolha" and q["gabarito"] not in {a for a, _ in q["alternativas"]}:
            q["gabarito"] = None            # letra de gabarito que não é alternativa: não vale
    pendentes = [q for q in questoes if q["tipo"] == "multipla_escolha" and not q["gabarito"]]
    if com_modelo and pendentes and _cabe_no_orcamento(math.ceil(len(pendentes) / LOTE_RESOLVER)):
        for n, letra in _resolver(pendentes).items():
            for q in pendentes:
                if q["numero"] == n:
                    q["gabarito"], q["fonte"] = letra, "tutor"

    chunks = [{"id": c["id"], "norm": re.sub(r"\s+", " ", c["texto"])} for c in db.query(
        "SELECT id, texto FROM chunk WHERE documento_id = %(d)s ORDER BY ordem", {"d": documento_id})]
    gravadas, sem_gabarito, sem_trecho = 0, 0, 0
    for q in questoes:
        if not q["tipo"]:
            continue
        if not q["gabarito"]:
            sem_gabarito += 1
            continue
        chunk_id = _chunk_da_questao(chunks, q)
        if not chunk_id:
            sem_trecho += 1          # sem trecho real não há proveniência: fica de fora
            continue
        _gravar(doc, q, chunk_id, disciplinas)
        gravadas += 1
    db.query("""UPDATE documento SET questoes_extraidas = %(n)s, questoes_sem_gabarito = %(s)s
                 WHERE id = %(d)s""", {"n": gravadas, "s": sem_gabarito, "d": documento_id})
    return {"status": "ok", "questoes": gravadas, "sem_gabarito": sem_gabarito,
            "sem_trecho": sem_trecho, "achadas": len(questoes)}


def _cabe_no_orcamento(chamadas: int) -> bool:
    from . import indice
    return indice.gasto_hoje() + chamadas <= indice.ORCAMENTO_DIA


def _simulado_que_responde(doc: dict, gab: dict[int, str]) -> int | None:
    """O simulado deste aluno que o gabarito responde: o mais recente que tem
    questões sem resposta, de preferência com mais números em comum."""
    candidatos = db.query(
        """SELECT d.id FROM documento d WHERE d.usuario_id = %(u)s AND d.tipo = 'simulado'
              AND d.id <> %(d)s AND coalesce(d.questoes_sem_gabarito, 0) > 0
            ORDER BY d.id DESC LIMIT 5""", {"u": doc["usuario_id"], "d": doc["id"]})
    melhor, nota = None, 0
    for c in candidatos:
        nums = {q["numero"] for q in separar(_texto_do_documento(c["id"]), _disciplinas_da_mesa(doc))
                if not q["gabarito"]}
        comuns = len(nums & set(gab))
        if comuns > nota:
            melhor, nota = c["id"], comuns
    return melhor


def _gravar(doc: dict, q: dict, chunk_id: int, disciplinas: list[str]) -> None:
    disciplina = q["disciplina"] or doc.get("disciplina") or "Geral"
    ce = None
    letra = None
    if q["tipo"] == "certo_errado":
        ce = q["gabarito"] in ("C", "C*")
    else:
        letra = q["gabarito"]
    justificativa = q["comentario"] or (
        f"Gabarito: {'Certo' if ce else 'Errado'}." if q["tipo"] == "certo_errado" else f"Gabarito: letra {letra}.")
    contexto_id = None
    if q["texto_base"]:
        existente = db.exec1("SELECT id FROM contexto WHERE documento_id = %(d)s AND texto = %(t)s",
                             {"d": doc["id"], "t": q["texto_base"]})
        contexto_id = existente["id"] if existente else db.exec1(
            """INSERT INTO contexto (documento_id, disciplina, texto, fonte_chunks)
               VALUES (%(d)s, %(disc)s, %(t)s, %(f)s) RETURNING id""",
            {"d": doc["id"], "disc": disciplina, "t": q["texto_base"], "f": [chunk_id]})["id"]
    params = {"d": doc["id"], "disc": disciplina, "tema": _tema(chunk_id, q, q["disciplina"]),
              "e": q["enunciado"], "g": justificativa, "f": [chunk_id], "tipo": q["tipo"], "ce": ce,
              "letra": letra, "fonte": q["fonte"], "n": q["numero"], "ctx": contexto_id,
              "ordem": 1 if contexto_id else None}
    # O dono sai do DOCUMENTO do trecho, nunca de parâmetro (026).
    r = db.exec1(
        """INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito, dicas, fonte_chunks,
                                tipo, gabarito_ce, gabarito_letra, gabarito_fonte, origem,
                                numero_na_prova, contexto_id, ordem_no_contexto, usuario_id)
           SELECT %(d)s, %(disc)s, %(tema)s, %(e)s, %(g)s, '{}', %(f)s, %(tipo)s, %(ce)s, %(letra)s,
                  %(fonte)s, 'prova', %(n)s, %(ctx)s, %(ordem)s, d.usuario_id
             FROM chunk c JOIN documento d ON d.id = c.documento_id WHERE c.id = %(f)s[1]
           ON CONFLICT (documento_id, numero_na_prova) WHERE origem = 'prova' DO UPDATE SET
                disciplina = EXCLUDED.disciplina, tema = EXCLUDED.tema, enunciado = EXCLUDED.enunciado,
                gabarito = EXCLUDED.gabarito, fonte_chunks = EXCLUDED.fonte_chunks, tipo = EXCLUDED.tipo,
                gabarito_ce = EXCLUDED.gabarito_ce, gabarito_letra = EXCLUDED.gabarito_letra,
                gabarito_fonte = EXCLUDED.gabarito_fonte, contexto_id = EXCLUDED.contexto_id,
                ordem_no_contexto = EXCLUDED.ordem_no_contexto
           RETURNING id""", params)
    if not r:
        return
    db.query("DELETE FROM questao_alternativa WHERE questao_id = %(q)s", {"q": r["id"]})
    for a, t in q["alternativas"] if q["tipo"] == "multipla_escolha" else []:
        db.query("INSERT INTO questao_alternativa (questao_id, letra, texto) VALUES (%(q)s, %(a)s, %(t)s)",
                 {"q": r["id"], "a": a, "t": t})


def pendentes() -> list[int]:
    return [r["id"] for r in db.query(
        """SELECT id FROM documento WHERE tipo = 'simulado' AND status = 'pronto'
              AND (questoes_extraidas IS NULL OR coalesce(questoes_sem_gabarito, 0) > 0)
            ORDER BY id DESC""")]


def da_conversa(usuario_id: int, tema: str, quantidade: int, disciplinas: list[str] | None = None) -> list[int]:
    """Questões de PROVA do aluno sobre o assunto pedido, ainda não respondidas.
    Mesma trava do gerador: o enunciado traz os termos raros do pedido."""
    from . import geracao
    raros = geracao.termos_raros(tema, usuario_id)
    if not raros:
        return []
    cond = " AND ".join(f"lower(q.enunciado || ' ' || q.gabarito || ' ' || q.tema) ~ %(r{i})s"
                        for i in range(len(raros)))
    params = {"u": usuario_id, "n": quantidade, "disc": disciplinas,
              **{f"r{i}": geracao._palavra_exata(t) for i, t in enumerate(raros)}}
    return [r["id"] for r in db.query(
        f"""SELECT q.id FROM questao q
             WHERE q.origem = 'prova' AND q.usuario_id = %(u)s AND {cond}
               AND (%(disc)s::text[] IS NULL OR q.disciplina = ANY(%(disc)s))
               AND NOT EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = q.id AND t.usuario_id = %(u)s)
             ORDER BY q.documento_id DESC, q.numero_na_prova
             LIMIT %(n)s""", params)]


if __name__ == "__main__":     # python -m core.prova → reimporta o que faltou (gabarito, extração)
    print(json.dumps({d: importar(d) for d in pendentes()}, ensure_ascii=False))
