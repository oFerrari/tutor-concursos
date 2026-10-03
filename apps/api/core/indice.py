"""
OS ASSUNTOS DO MATERIAL, e de que assuntos cada trecho trata (036).

POR QUE ESTE MÓDULO EXISTE
--------------------------
O material do aluno era uma sequência de trechos soltos com UM rótulo para o
arquivo inteiro. "Resumão de voz passiva", "questões de habeas corpus" e
"onde está X" dependiam de a busca por sentido acertar um trecho solto — e
assunto que começa em cima e retoma embaixo, ou que volta nas questões
comentadas do fim, não era juntado em lugar nenhum.

COMO
----
1. ESTRUTURA: o modelo lê o começo da apostila (capa, sumário) e os títulos do
   corpo, e devolve a lista de assuntos com as páginas e o papel (ensino,
   questões, outro). Uma chamada por material.
2. MARCAÇÃO: lotes de 30 trechos; o modelo diz de quais assuntos da lista cada
   trecho TRATA e se ensina ou é questão. A página entra como PISTA (a seção em
   que o trecho cai), e trecho de ensino sem assunto dentro de uma seção fica
   com o da seção.
3. RESERVA, sem modelo (sem cota, modelo fora): o sumário e os títulos dão a
   lista, e a marcação é pela seção (página) e pela expressão no texto. O
   documento fica `reserva` e é refeito com o modelo quando houver cota.

O QUE A MEDIÇÃO DECIDIU (bateria nas 18 apostilas da conta real, 29/09/2026):
regras + vetores locais 60–75%; o modelo leve 72–77%, julgado à mão, com voz
passiva achada em 18 dos 24 trechos que a mencionam e só 3 trechos misturando
habeas corpus com mandado de segurança (o agrupamento por vetor juntava os dois
em 82). Ver `docs/DECISOES.md`.

COTA: o modelo é `config.LLM_INDICE`, nunca o do tutor, e há um orçamento
diário (`INDICE_ORCAMENTO_DIA`) contado pela telemetria (030).
"""
import json
import math
import os
import re
import time
import unicodedata

from . import assunto, db, llm

VERSAO = "indice-v5"

LOTE = 30                 # trechos por chamada: 60 estourou o limite de tokens/min (medido)
PAUSA_S = float(os.getenv("INDICE_PAUSA_S", "8"))
ORCAMENTO_DIA = int(os.getenv("INDICE_ORCAMENTO_DIA", "150"))
CHARS_POR_TRECHO = 1600
TRAVA_INDICE = 36036      # pg_try_advisory_lock(TRAVA_INDICE, documento_id)
PAPEIS = ("ensino", "questoes", "outro")


def _sem_acento(t: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(ch) != "Mn").lower()


# ------------------------------------------------------------------ texto (PURO)
RE_LETRA = re.compile(r"^\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ])\s*$")
# Uma letra maiúscula só é palavra do título se não vier colada a minúscula: em
# "ERBO As formas", o "A" é o começo de "As", não um artigo do título.
RE_RESTO = re.compile(r"^\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+(?![a-záéíóúâêôãõç]))*)(.*)$")


def juntar_versalete(texto: str) -> str:
    """Título em versalete sai do PDF com a 1ª letra de cada palavra numa linha
    ("F\\nORMAS\\n N\\nOMINAIS DO\\n V\\nERBO As formas…"). Junta: "FORMAS NOMINAIS
    DO VERBO", e o texto que vinha colado segue na linha seguinte. PURO."""
    linhas, saida, i = (texto or "").split("\n"), [], 0
    while i < len(linhas):
        partes, j, resto = [], i, ""
        while j + 1 < len(linhas) and RE_LETRA.match(linhas[j]) and RE_RESTO.match(linhas[j + 1]):
            m = RE_RESTO.match(linhas[j + 1])
            partes.append(RE_LETRA.match(linhas[j]).group(1) + m.group(1))
            j += 2
            if m.group(2).strip():
                resto = m.group(2).strip()
                break
        if partes:
            saida.append(" ".join(partes))
            if resto:
                saida.append(resto)
            i = j
        else:
            saida.append(linhas[i])
            i += 1
    return "\n".join(saida)


RE_NOTA = re.compile(r"(?i)\b(?:STF|STJ|Rel\.|DJ|Min\.|RE|HC|ADI|ADPF|Decisão)\b.*\d")


def titulos(chunks: list[dict]) -> list[tuple[int | None, str]]:
    """(página, título) do corpo: linha curta em caixa alta, sem ponto final, sem
    número no meio, que não se repete (repetido em toda página é cabeçalho). PURO."""
    achados, vistos = [], {}
    for c in chunks:
        for l in juntar_versalete(c.get("texto") or "").split("\n"):
            l = l.strip()
            letras = [ch for ch in l if ch.isalpha()]
            if not (6 <= len(l) <= 90) or len(letras) < 5 or l.endswith((".", ",", ";", ":")):
                continue
            if re.search(r"\.{4,}", l) or RE_NOTA.search(l):
                continue
            if re.search(r"\d", re.sub(r"^\d+(\.\d+)*\s*[-.)]?\s*", "", l)):
                continue
            if sum(ch.isupper() for ch in letras) / len(letras) > 0.85 and len(l.split()) >= 2:
                vistos[l] = vistos.get(l, 0) + 1
                achados.append((c.get("pagina"), l))
    return [(p, t) for p, t in achados if vistos[t] <= 2]


RE_ENTRADA = re.compile(r"(?:^|\.{3,}|\n)\s*(?:\d{1,2}\s*[-.)]\s*)?"
                        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n.]{3,90}?)\s+(\d{1,3})\s*(?=\n|\.{3,}|$)")
RE_QUESTOES = re.compile(r"(?i)\b(?:quest[õo]es|exerc[íi]cios|gabarito|lista\s+de|simulado)\b")
RE_OUTRO = re.compile(r"(?i)\b(?:apresenta[çc][ãa]o|considera[çc][õo]es\s+iniciais|bibliografia|"
                      r"refer[êe]ncias|aviso)\b")


def sumario(chunks: list[dict]) -> list[tuple[str, int]]:
    """(título, página) do SUMÁRIO da própria apostila — "1) Noções iniciais de
    Verbos ..... 3" —, procurado nos primeiros trechos depois de "Índice" ou
    "Sumário". Menos de 3 entradas = sem sumário. PURO."""
    for k, c in enumerate(chunks[:8]):
        texto = c.get("texto") or ""
        m = re.search(r"(?i)\b(?:[íi]ndice|sum[áa]rio)\b", texto)
        if not m:
            continue
        resto = texto[m.end():]
        if k + 1 < len(chunks):
            resto += "\n" + (chunks[k + 1].get("texto") or "").split("\n\n")[0]
        ents = [(e.group(1).strip(" -"), int(e.group(2))) for e in RE_ENTRADA.finditer(resto)]
        ents = [(t, p) for t, p in ents if p >= 1]
        if len(ents) >= 3:
            return ents
    return []


GENERICAS = {"nocoes", "iniciais", "introducao", "conceito", "conceitos", "sentidos", "aspectos",
             "gerais", "geral", "explicacao", "exemplo", "exemplos", "aplicacao", "tipo", "tipos",
             "resumo", "parte", "capitulo", "aula", "modulo", "topico"}


def chave(nome: str) -> list[str]:
    """As palavras que dizem DE QUE o assunto trata, sem as genéricas de título. PURO."""
    palavras = [p for p in (_sem_acento(x) for x in assunto.palavras_de_conteudo(nome or ""))
                if p not in GENERICAS and len(p) >= 4]
    # NOME COMPOSTO conta inteiro: em "Tabela-Verdade", "verdade" é palavra vazia de
    # conversa ("na verdade") e sumia — sobrava "tabela", curta demais para casar, e
    # "me explica do zero tabela-verdade" não achava a seção (bateria longa, 03/10/2026).
    for composto in re.findall(r"\w{3,}-\w{3,}", nome or ""):
        for p in (_sem_acento(x.lower()) for x in composto.split("-")):
            if len(p) >= 4 and p not in GENERICAS and p not in palavras:
                palavras.append(p)
    return palavras


def menciona(texto_normalizado: str, palavras: list[str]) -> bool:
    """O texto (já sem acento e minúsculo) traz o assunto? Uma palavra só precisa
    ser longa (7+); várias, todas (prefixo, para plural e flexão). PURO."""
    if not palavras:
        return False
    if len(palavras) == 1:
        return len(palavras[0]) >= 7 and re.search(rf"\b{re.escape(palavras[0])}", texto_normalizado) is not None
    return all(re.search(rf"\b{re.escape(p[:max(5, len(p) - 2)])}", texto_normalizado) for p in palavras)


def _papel_do_nome(nome: str) -> str:
    return "questoes" if RE_QUESTOES.search(nome) else "outro" if RE_OUTRO.search(nome) else "ensino"


# TÍTULO NUMERADO de material SEM PÁGINA (.txt, .html): "3. Tabela-verdade". Curto,
# começa em maiúscula depois do número, sem ponto final. A reserva só aceitava título
# em caixa alta com página, e material assim ficava sem índice nenhum — "me explica
# tabela-verdade" não achava a seção (bateria longa, 03/10/2026).
RE_TITULO_NUMERADO = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2})*\s*[.)\-–]?\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^.!?;:\n]{2,68})$")


def titulos_sem_pagina(chunks: list[dict]) -> list[tuple[int, str]]:
    """(ordem do trecho, título) dos títulos numerados ou em caixa alta. PURO."""
    achados, vistos = [], set()
    for c in sorted(chunks, key=lambda c: c.get("ordem", 0)):
        for l in juntar_versalete(c.get("texto") or "").split("\n"):
            l = l.strip()
            m = RE_TITULO_NUMERADO.match(l)
            nome = m.group(1).strip() if m and len(l.split()) <= 9 else None
            if not nome:
                letras = [ch for ch in l if ch.isalpha()]
                if 6 <= len(l) <= 70 and len(letras) >= 5 and len(l.split()) >= 2 and not l.endswith((".", ",", ";", ":")) \
                        and sum(ch.isupper() for ch in letras) / len(letras) > 0.85 and not re.search(r"\d", l):
                    nome = l.title()
            if nome and nome.lower() not in vistos:      # a sobreposição repete o título no trecho seguinte
                vistos.add(nome.lower())
                achados.append((c.get("ordem", 0), nome))
    return achados


def estrutura_reserva(chunks: list[dict]) -> list[dict]:
    """A lista de assuntos SEM modelo: o sumário, ou os títulos do corpo. PURO."""
    if chunks and not any(c.get("pagina") for c in chunks):
        itens = [{"nome": t, "pagina_inicio": None, "pagina_fim": None, "origem": "titulo", "_ordem": o}
                 for o, t in titulos_sem_pagina(chunks)]
        for a in itens:
            a["papel"] = _papel_do_nome(a["nome"])
        return [a for a in itens if a["papel"] != "ensino" or chave(a["nome"])]
    ultima = max((c.get("pagina") or 0 for c in chunks), default=0) or None
    ents = sumario(chunks)
    if ents:
        itens = [{"nome": t, "pagina_inicio": p, "origem": "sumario"} for t, p in ents]
    else:
        itens = [{"nome": t.title(), "pagina_inicio": p, "origem": "titulo"} for p, t in titulos(chunks) if p]
    itens = sorted(itens, key=lambda a: a["pagina_inicio"] or 0)
    for k, a in enumerate(itens):
        seguinte = itens[k + 1]["pagina_inicio"] if k + 1 < len(itens) else None
        a["pagina_fim"] = max(a["pagina_inicio"], (seguinte or ultima or a["pagina_inicio"]) - (1 if seguinte else 0))
        a["papel"] = _papel_do_nome(a["nome"])
    return [a for a in itens if a["papel"] != "ensino" or chave(a["nome"])]


def secao_da_pagina(lista: list[dict], pagina: int | None) -> dict | None:
    """O assunto de ENSINO em cuja faixa de páginas o trecho cai. PURO."""
    if pagina is None:
        return None
    dentro = [a for a in lista if a.get("papel") == "ensino" and a.get("pagina_inicio") is not None
              and a["pagina_inicio"] <= pagina <= (a.get("pagina_fim") or a["pagina_inicio"])]
    return dentro[-1] if dentro else None


def secao_da_ordem(lista: list[dict], ordem: int | None) -> dict | None:
    """Sem página: o assunto de ENSINO do último título antes do trecho. PURO."""
    if ordem is None:
        return None
    antes = [a for a in lista if a.get("_ordem") is not None and a["_ordem"] <= ordem]
    return antes[-1] if antes and antes[-1].get("papel") == "ensino" else None


def marcar_reserva(lista: list[dict], chunks: list[dict]) -> dict[int, list[tuple[str, str, str]]]:
    """{chunk_id: [(assunto, papel, origem)]} SEM modelo: a seção pela página, e
    todo assunto de ensino cuja expressão aparece no texto. PURO."""
    ensino = [a for a in lista if a.get("papel") == "ensino"]
    marcas: dict[int, list[tuple[str, str, str]]] = {}
    sem_pagina = any("_ordem" in a for a in lista)
    for c in chunks:
        texto = _sem_acento(re.sub(r"\s+", " ", juntar_versalete(c.get("texto") or "")))
        secao = secao_da_ordem(lista, c.get("ordem")) if sem_pagina else secao_da_pagina(lista, c.get("pagina"))
        if sem_pagina:
            # sem página, a seção de questões é a do último título antes do trecho
            atual = [a for a in lista if a.get("_ordem", 10 ** 9) <= (c.get("ordem") or 0)]
            em_q = bool(atual and atual[-1].get("papel") == "questoes")
            ms = [] if em_q or not secao else [(secao["nome"], "ensino", "secao")]
            for a in ensino:
                if all(a["nome"] != m[0] for m in ms) and menciona(texto, chave(a["nome"])):
                    ms.append((a["nome"], "questao" if em_q else "ensino", "expressao"))
            if ms:
                marcas[c["id"]] = ms
            continue
        em_questoes = any(a.get("papel") == "questoes" and a.get("pagina_inicio") is not None
                          and a["pagina_inicio"] <= (c.get("pagina") or -1) <= (a.get("pagina_fim") or a["pagina_inicio"])
                          for a in lista)
        papel = "questao" if em_questoes else "ensino"
        ms = []
        if secao and not em_questoes:
            ms.append((secao["nome"], "ensino", "secao"))
        for a in ensino:
            if all(a["nome"] != m[0] for m in ms) and menciona(texto, chave(a["nome"])):
                ms.append((a["nome"], papel, "expressao"))
        if ms:
            marcas[c["id"]] = ms
    return marcas


# ------------------------------------------------------------------ com o modelo
ESQ_ESTRUTURA = {"type": "OBJECT", "properties": {"assuntos": {"type": "ARRAY", "items": {"type": "OBJECT",
    "properties": {"nome": {"type": "STRING"}, "pagina_inicio": {"type": "INTEGER"},
                   "pagina_fim": {"type": "INTEGER"},
                   "papel": {"type": "STRING", "enum": list(PAPEIS)}},
    "required": ["nome", "pagina_inicio", "pagina_fim", "papel"]}}}, "required": ["assuntos"]}
SIS_ESTRUTURA = (
    "Você recebe o começo de uma apostila de concurso (capa, sumário) e os títulos achados no corpo, com a "
    "página de cada um. Monte a lista de ASSUNTOS de estudo da apostila, na ordem, cada um com a página em "
    "que começa e a em que termina. Nome ESPECÍFICO, como o aluno pesquisaria ('Habeas corpus', 'Voz "
    "passiva'), nunca o genérico ('Noções iniciais', 'Parte 2'). Assuntos que a apostila separa são itens "
    "separados (habeas corpus e mandado de segurança são dois). Listas de questões e gabaritos têm papel "
    "'questoes'; capa, apresentação, avisos e bibliografia, 'outro'. Ignore cabeçalho de tabela e nota de "
    "rodapé. Entre 3 e 40 itens.")
ESQ_MARCAS = {"type": "OBJECT", "properties": {"trechos": {"type": "ARRAY", "items": {"type": "OBJECT",
    "properties": {"n": {"type": "INTEGER"}, "assuntos": {"type": "ARRAY", "items": {"type": "STRING"}},
                   "papel": {"type": "STRING", "enum": ["ensino", "questao", "outro"]}},
    "required": ["n", "assuntos", "papel"]}}}, "required": ["trechos"]}
SIS_MARCAS = (
    "Para cada trecho de apostila, diga de quais assuntos da LISTA ele TRATA: ensina, explica, exemplifica, "
    "ou é questão (enunciado, alternativas, comentário) cujo foco é o assunto. Só citar de passagem NÃO "
    "conta; nota de rodapé e bibliografia não contam. Cada trecho vem com a SEÇÃO em que cai pela página: "
    "é uma pista forte — fique com ela, a não ser que o conteúdo seja claramente de outro assunto da lista. "
    "Use os nomes da lista, exatos; de 0 a 3 assuntos. papel: 'ensino', 'questao' ou 'outro' (capa, "
    "sumário, apresentação, aviso, bibliografia — esses ficam sem assunto).")


def gasto_hoje() -> int:
    """Chamadas do índice no dia da cota (meia-noite do Pacífico), pela telemetria.
    Conta também o mapa de domínio (038): mesmo modelo, mesma cota."""
    r = db.exec1("""SELECT count(*) AS n FROM telemetria_llm
                     WHERE (origem_chamada LIKE 'indice.%%' OR origem_chamada LIKE 'dominio.%%')
                     AND criado_em >= (date_trunc('day', now() AT TIME ZONE 'America/Los_Angeles')
                                       AT TIME ZONE 'America/Los_Angeles')""")
    return r["n"] if r else 0


def _chamar(prompt: str, sistema: str, schema: dict) -> dict:
    return llm.obter("indice").gerar_json(prompt, sistema, max_tokens=12000, schema=schema,
                                          temperatura=0.0) or {}


def _estrutura_modelo(doc: dict, chunks: list[dict]) -> list[dict]:
    comeco = "\n\n".join(juntar_versalete(c["texto"]) for c in chunks[:3])[:7000]
    tits = "\n".join(f"p. {p}: {t}" for p, t in titulos(chunks)[:120])
    ultima = max((c.get("pagina") or 0 for c in chunks), default=0)
    r = _chamar(f"APOSTILA: {doc.get('assunto') or doc.get('titulo')} ({doc.get('disciplina') or '?'}), "
                f"páginas 1 a {ultima}\n\nCOMEÇO DA APOSTILA:\n{comeco}\n\nTÍTULOS NO CORPO:\n{tits}",
                SIS_ESTRUTURA, ESQ_ESTRUTURA)
    lista = []
    for a in r.get("assuntos") or []:
        nome = (a.get("nome") or "").strip()[:200]
        if nome and a.get("papel") in PAPEIS:
            ini = a.get("pagina_inicio") if isinstance(a.get("pagina_inicio"), int) else None
            fim = a.get("pagina_fim") if isinstance(a.get("pagina_fim"), int) else ini
            lista.append({"nome": nome, "pagina_inicio": ini, "pagina_fim": max(fim or 0, ini or 0) or None,
                          "papel": a["papel"], "origem": "modelo"})
    if not any(a["papel"] == "ensino" for a in lista):
        raise llm.ErroLLM("estrutura sem assunto de ensino")
    return lista


def _marcar_modelo(lista: list[dict], chunks: list[dict]) -> dict[int, list[tuple[str, str, str]]]:
    ensino = [a for a in lista if a["papel"] == "ensino"]
    nomes = {a["nome"] for a in ensino}
    marcas: dict[int, list[tuple[str, str, str]]] = {}
    for i in range(0, len(chunks), LOTE):
        if i:
            time.sleep(PAUSA_S)        # tokens por minuto: lotes seguidos estouram o limite
        lote = chunks[i:i + LOTE]

        def linha(k, c):
            s = secao_da_pagina(lista, c.get("pagina"))
            return (f"[{k}] (p. {c.get('pagina')}; seção: {s['nome'] if s else 'nenhuma'})\n"
                    f"{juntar_versalete(c['texto'])[:CHARS_POR_TRECHO]}")
        r = _chamar("LISTA DE ASSUNTOS:\n" + "\n".join(f"- {a['nome']}" for a in ensino) + "\n\n" +
                    "\n\n".join(linha(k, c) for k, c in enumerate(lote)), SIS_MARCAS, ESQ_MARCAS)
        vistos = set()
        for t in r.get("trechos") or []:
            n = t.get("n")
            if not isinstance(n, int) or not 0 <= n < len(lote) or n in vistos:
                continue
            vistos.add(n)
            c = lote[n]
            if t.get("papel") == "outro":
                continue                       # capa, sumário, aviso: sem assunto
            papel = "questao" if t.get("papel") == "questao" else "ensino"
            ms = [(nome, papel, "modelo") for nome in dict.fromkeys(t.get("assuntos") or []) if nome in nomes][:3]
            if not ms and papel == "ensino":
                s = secao_da_pagina(lista, c.get("pagina"))
                if s:
                    ms = [(s["nome"], "ensino", "secao")]
            if ms:
                marcas[c["id"]] = ms
        # trecho que o modelo não devolveu: fica com a reserva dele
        faltaram = [c for k, c in enumerate(lote) if k not in vistos]
        marcas.update(marcar_reserva(lista, faltaram))
    return marcas


# ------------------------------------------------------------------ gravar e ler
def _gravar(documento_id: int, lista: list[dict], marcas: dict[int, list[tuple[str, str, str]]],
            status: str) -> None:
    with db.conexao_isolada() as c, c.cursor() as cur:
        cur.execute("DELETE FROM material_assunto WHERE documento_id = %s", (documento_id,))
        ids = {}
        for k, a in enumerate(lista):
            cur.execute("""INSERT INTO material_assunto (documento_id, ordem, nome, pagina_inicio,
                                                         pagina_fim, papel, origem)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (documento_id, k, a["nome"], a.get("pagina_inicio"), a.get("pagina_fim"),
                         a["papel"], a["origem"]))
            ids.setdefault(a["nome"], cur.fetchone()["id"])
        for chunk_id, ms in marcas.items():
            for nome, papel, origem in ms:
                if nome in ids:
                    cur.execute("""INSERT INTO chunk_assunto (chunk_id, assunto_id, papel, origem)
                                   VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                                (chunk_id, ids[nome], papel, origem))
        cur.execute("UPDATE documento SET assuntos_status = %s, assuntos_em = now() WHERE id = %s",
                    (status, documento_id))


def indexar_assuntos(documento_id: int, com_modelo: bool = True) -> str:
    """Monta a lista de assuntos do material e marca cada trecho. Devolve o status
    gravado: 'pronto' (modelo), 'reserva' (sem modelo) ou 'falha'. Um por vez por
    documento (trava no banco), e erro nunca sobe: quem chama é a fila de indexação."""
    doc = db.exec1("""SELECT id, usuario_id, titulo, assunto, disciplina, tipo FROM documento
                       WHERE id = %(i)s""", {"i": documento_id})
    # SIMULADO fica de fora (01/10/2026): o índice é de APOSTILA, que tem seções.
    # Num simulado de 12 disciplinas ele achou 3 "assuntos", e os rótulos errados
    # viraram citação ("Interpretação de texto" numa questão de juros) e nome de
    # cartão ("Parônimos" numa de pontuação). O assunto da questão de prova é a
    # disciplina da seção dela (`core/prova.py`).
    if not doc or not doc["usuario_id"] or doc["tipo"] in ("edital", "simulado"):
        return "ignorado"
    with db.conexao_isolada() as c, c.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s, %s) AS meu", (TRAVA_INDICE, documento_id))
        if not cur.fetchone()["meu"]:
            return "ocupado"
        try:
            chunks = db.query("SELECT id, ordem, pagina, texto FROM chunk WHERE documento_id = %(d)s ORDER BY ordem",
                              {"d": documento_id})
            if not chunks:
                return "vazio"
            chamadas = 1 + math.ceil(len(chunks) / LOTE)
            if com_modelo and gasto_hoje() + chamadas <= ORCAMENTO_DIA:
                try:
                    lista = _estrutura_modelo(doc, chunks)
                    _gravar(documento_id, lista, _marcar_modelo(lista, chunks), "pronto")
                    return "pronto"
                except llm.ErroLLM as e:
                    print(f"[indice] {documento_id}: modelo indisponível ({str(e)[:80]}); reserva")
            lista = estrutura_reserva(chunks)
            _gravar(documento_id, lista, marcar_reserva(lista, chunks), "reserva")
            return "reserva"
        except Exception as e:  # noqa: BLE001 — a fila não pode morrer por um material
            print(f"[indice] {documento_id}: falhou ({e})")
            db.query("UPDATE documento SET assuntos_status = 'falha' WHERE id = %(i)s", {"i": documento_id})
            return "falha"
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s, %s)", (TRAVA_INDICE, documento_id))


def pendentes() -> list[int]:
    """Materiais de aluno sem índice do modelo (pendente, reserva ou falha), os mais novos antes."""
    return [r["id"] for r in db.query(
        """SELECT id FROM documento WHERE usuario_id IS NOT NULL AND coalesce(tipo, '') NOT IN ('edital', 'simulado')
              AND status = 'pronto' AND assuntos_status IN ('pendente', 'reserva', 'falha')
            ORDER BY id DESC""")]


def processar_pendentes() -> dict:
    """Indexa os pendentes até o orçamento do dia; o que não couber fica para amanhã."""
    feitos = {}
    for d in pendentes():
        n = db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id = %(d)s", {"d": d})["n"]
        if gasto_hoje() + 1 + math.ceil(n / LOTE) > ORCAMENTO_DIA:
            break
        feitos[d] = indexar_assuntos(d)
    return feitos


def assunto_citado(usuario_id: int, fala: str, documento_ids: list[int] | None = None) -> dict | None:
    """O assunto de ENSINO, nos materiais do aluno, que a fala nomeia — o que casa
    mais palavras. {id, nome, documento_id} ou None."""
    texto = _sem_acento(re.sub(r"\s+", " ", fala or ""))
    if not texto.strip():
        return None
    linhas = db.query(
        """SELECT a.id, a.nome, a.documento_id FROM material_assunto a JOIN documento d ON d.id = a.documento_id
            WHERE d.usuario_id = %(u)s AND a.papel = 'ensino'
              AND (%(docs)s::bigint[] IS NULL OR a.documento_id = ANY(%(docs)s))""",
        {"u": usuario_id, "docs": documento_ids})
    melhor, nota = None, 0
    for a in linhas:
        ch = chave(a["nome"])
        if ch and menciona(texto, ch) and len(ch) > nota:
            melhor, nota = dict(a), len(ch)
    return melhor


def trechos_do_assunto(assunto_id: int, papel: str | None = None) -> list[int]:
    """Os trechos marcados com o assunto, na ordem do material."""
    return [r["chunk_id"] for r in db.query(
        """SELECT ca.chunk_id FROM chunk_assunto ca JOIN chunk c ON c.id = ca.chunk_id
            WHERE ca.assunto_id = %(a)s AND (%(p)s::text IS NULL OR ca.papel = %(p)s)
            ORDER BY c.ordem""", {"a": assunto_id, "p": papel})]


def assuntos_dos_trechos(ids: list[int]) -> dict[int, list[str]]:
    """{chunk_id: [nomes dos assuntos]} — para o rótulo da fonte e do prompt."""
    if not ids:
        return {}
    saida: dict[int, list[str]] = {}
    for r in db.query("""SELECT ca.chunk_id, a.nome FROM chunk_assunto ca
                          JOIN material_assunto a ON a.id = ca.assunto_id
                         WHERE ca.chunk_id = ANY(%(i)s) ORDER BY a.ordem""", {"i": ids}):
        saida.setdefault(r["chunk_id"], []).append(r["nome"])
    return saida


if __name__ == "__main__":       # python -m core.indice  → indexa os pendentes no orçamento do dia
    print(json.dumps(processar_pendentes(), ensure_ascii=False))
