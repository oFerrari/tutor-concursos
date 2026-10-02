"""
Cobertura do edital por SUBITEM: o que do programa está no material do aluno, onde
(apostila e páginas), e o que falta. Migração 035.

POR QUE ISTO EXISTE (28/09/2026)
--------------------------------
O edital só se ligava ao material pela disciplina. A promessa "domina o seu
edital" pede mais: "o item 2.1 está nas páginas 3 a 17 da sua Aula 00", "o item
2.3 não está em material nenhum seu", "ler na ordem do edital".

COMO SE DECIDE — o que o protótipo mediu num edital real com 17 apostilas
--------------------------------------------------------------------------
1. Candidatos por EXPRESSÃO (`phraseto_tsquery`) e por SENTIDO (e5), dentro do
   material da disciplina. O sentido sozinho não decide nada — as notas ficam
   todas entre 0,82 e 0,87 —, mas traz candidato que a expressão perde ("sigilo
   de dados e comunicações" não aparece assim, literal, em apostila nenhuma).
2. Sem sumário e sem trecho-ÍNDICE: o trecho que casa com subitens de muitos itens
   diferentes é apresentação de curso ou cronograma, que cita tudo de passagem.
3. O MODELO CONFIRMA, uma chamada por item do edital: de cada candidato, "este
   trecho ensina o subitem?". Só por texto a medição deu ~85% e cobertura falsa
   ("Polícia Civil do Estado do Paraná" coberta por uma aula sobre a CF federal).
   Sem cota, fica o resultado por texto — conservador — com `metodo='texto'`,
   para a próxima verificação refazer.

QUANDO RODA. Subir material só MARCA a disciplina como pendente
(`marcar_pendente`); a verificação com o modelo roda depois, uma vez por
disciplina (`verificar_pendentes`). Catorze apostilas subidas de uma vez não
podem virar catorze verificações do edital inteiro.
"""
import re

from . import assunto, db, embeddings, leitura, mesa as mesa_mod

VERSAO = "cobertura-v4"

# Subitem que é só a palavra da categoria herda o cabeçalho do item:
# "Medicina Legal: conceito, divisões e importância" procura "medicina legal".
RE_GENERICO = re.compile(
    r"(?i)^(?:conceitos?|no[cç][oõ]es|aspectos|disposi[cç][oõ]es|fun[cç][oõ]es|import[aâ]ncia"
    r"|divis[oõ]es|caracter[ií]sticas|tipos|esp[eé]cies|objeto|m[eé]todos|fundamentos"
    r"|defini[cç][aã]o|classifica[cç][aã]o)\b")
# QUESTÃO NÃO ENSINA. As apostilas terminam cada aula com questões comentadas, e
# ali os termos se concentram mais que na teoria: os candidatos de "habeas
# corpus" eram todos questões (28/09/2026), e o modelo, com razão, recusou.
# Marcas de questão, não de banca específica: basta duas.
RE_MARCA_DE_QUESTAO = re.compile(
    r"(?im)\bgabarito\b|coment[aá]rios?\s*:|^\s*\(?[a-e]\)\s|\bletra\s+[a-e]\b"
    r"|\((?:[A-Z][A-Za-z]{2,}(?:/[A-Z][\w-]*)+)\s*[-/]?\s*\d{4}\)")
MARCAS_PARA_SER_QUESTAO = 2
CANDIDATOS_POR_SUBITEM = 4
CANDIDATOS_POR_SENTIDO = 2
# Trecho que toca subitens de tantos itens diferentes é índice, não aula.
ITENS_PARA_SER_INDICE = 5
CHARS_DO_TRECHO_NO_PROMPT = 450
TRECHOS_PARA_COBERTO = 2


# ------------------------------------------------------------------ puros
def cabecalho(texto_do_topico: str) -> str:
    """"2.1. Medicina Legal: conceito…" → "Medicina Legal"."""
    cab = (texto_do_topico or "").partition(":")[0]
    return re.sub(r"^\s*[\d.]+\s*", "", cab).strip(" .;")


def subitens(texto_do_topico: str) -> list[str]:
    """O tópico quebrado nos ";" depois do ":". Tópico sem lista é um subitem só."""
    cab, dois_pontos, corpo = (texto_do_topico or "").partition(":")
    partes = [p.strip(" .;") for p in re.split(r";", corpo)] if dois_pontos else []
    partes = [p for p in partes if len(p) > 3]
    return partes or [cabecalho(texto_do_topico) or (texto_do_topico or "").strip()]


def atomos(sub: str, cab: str) -> list[str]:
    """As expressões a procurar: o subitem quebrado por vírgula, sem as genéricas.
    NÃO quebra no "e": "direitos individuais e coletivos" é uma coisa só."""
    partes = [p.strip(" .") for p in sub.split(",") if p.strip(" .")]
    fortes = [p for p in partes if not RE_GENERICO.match(p) and assunto.palavras_de_conteudo(p)]
    return fortes or ([cab] if cab else [sub])


def paginas(numeros: list[int]) -> str:
    """[3, 4, 5, 9] -> "3–5, 9"."""
    ordem = sorted(set(n for n in numeros if n))
    faixas, i = [], 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and ordem[j + 1] == ordem[j] + 1:
            j += 1
        faixas.append(f"{ordem[i]}" if i == j else f"{ordem[i]}–{ordem[j]}")
        i = j + 1
    return ", ".join(faixas)


# ------------------------------------------------------------------ banco
def _documentos(usuario_id: int, disciplina: str, mapa: dict | None) -> list[int]:
    return [r["id"] for r in db.query(
        """SELECT id FROM documento
            WHERE usuario_id = %(u)s AND disciplina = ANY(%(n)s)
              AND tipo IN ('aula', 'resumo') AND status = 'pronto'""",
        {"u": usuario_id, "n": leitura.nomes_da_disciplina(disciplina, mapa)})]


def _por_expressao(expressao: str, docs: list[int]) -> list[dict]:
    """Trechos com a expressão; sem nenhum e com mais de duas palavras, o começo
    dela ("princípios fundamentais da Constituição da República…")."""
    tentativas = [expressao]
    conteudo = assunto.palavras_de_conteudo(expressao)
    if len(conteudo) > 2:
        tentativas.append(" ".join(conteudo[:2]))
    for t in tentativas:
        linhas = db.query(
            """SELECT c.id, c.documento_id, c.ordem, c.pagina, c.texto FROM chunk c
                WHERE c.documento_id = ANY(%(d)s)
                  AND to_tsvector('portuguese', c.texto) @@ phraseto_tsquery('portuguese', %(e)s)""",
            {"d": docs, "e": t})
        if linhas:
            return linhas
    return []


def _por_sentido(sub: str, cab: str, docs: list[int], n: int) -> list[dict]:
    emb = embeddings.embed_consulta(f"{sub} ({cab})" if cab else sub)
    return db.query(
        """SELECT c.id, c.documento_id, c.ordem, c.pagina, c.texto FROM chunk c
            WHERE c.documento_id = ANY(%(d)s) AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %(e)s::vector LIMIT %(n)s""",
        {"d": docs, "e": emb, "n": n})


def e_questao(texto: str) -> bool:
    return len(RE_MARCA_DE_QUESTAO.findall(texto or "")) >= MARCAS_PARA_SER_QUESTAO


def _regiao(trechos: list[dict]) -> list[dict]:
    """A corrida mais longa de trechos próximos (até 3 de distância) — onde o
    assunto MORA dentro da apostila, e não onde ele é citado de passagem."""
    melhor, atual = [], []
    for l in sorted(trechos, key=lambda l: l["ordem"]):
        if atual and l["ordem"] - atual[-1]["ordem"] > 3:
            atual = []
        atual.append(l)
        if len(atual) > len(melhor):
            melhor = list(atual)
    return melhor


def _candidatos(sub: str, cab: str, docs: list[int], perfil: dict[int, dict]) -> tuple[list[dict], int]:
    """Candidatos do subitem e quantos vieram por expressão.

    A ESCOLHA é o que decide, e foi medido: "nacionalidade" aparece em 146 trechos,
    quase todos de passagem; mandar os primeiros quatro deu ao modelo só menções, e
    ele recusou uma aula inteira sobre o tema. Os candidatos saem da apostila onde
    a expressão se CONCENTRA (a de assunto igual ao subitem primeiro; depois a
    densidade relativa ao tamanho) e, dentro dela, da região mais densa. A segunda
    apostila contribui um trecho — o assunto pode estar dividido em duas aulas."""
    por_trecho: dict[int, dict] = {}
    for a in atomos(sub, cab):
        for l in _por_expressao(a, docs):
            if not leitura.e_sumario(l["texto"]) and not e_questao(l["texto"]):
                por_trecho[l["id"]] = l
    por_doc: dict[int, list[dict]] = {}
    for l in por_trecho.values():
        por_doc.setdefault(l["documento_id"], []).append(l)
    alvo = " ".join(assunto._sem_acento(p) for p in assunto.palavras_de_conteudo(f"{sub} {cab}"))

    def nota(d):
        rotulo = assunto._sem_acento(" ".join(assunto.palavras_de_conteudo(perfil[d]["assunto"] or "")))
        bate = bool(rotulo) and (rotulo in alvo or all(w in alvo.split() for w in rotulo.split()))
        return (bate, len(por_doc[d]) / max(perfil[d]["trechos"], 1) ** 0.5)

    ordem_docs = sorted(por_doc, key=nota, reverse=True)
    escolhidos: list[dict] = []
    for i, d in enumerate(ordem_docs[:2]):
        regiao = _regiao(por_doc[d])
        quantos = CANDIDATOS_POR_SUBITEM - 1 if i == 0 else 1
        passo = max(1, len(regiao) // quantos)
        escolhidos += regiao[::passo][:quantos]
    lexicais = len(escolhidos)
    for l in _por_sentido(sub, cab, docs, CANDIDATOS_POR_SENTIDO):
        if (l["id"] not in {e["id"] for e in escolhidos} and not leitura.e_sumario(l["texto"])
                and not e_questao(l["texto"])):
            escolhidos.append({**l, "_sentido": True})
    return escolhidos, lexicais


def _estado(n_trechos: int) -> str:
    return ("coberto" if n_trechos >= TRECHOS_PARA_COBERTO else
            "citado" if n_trechos == 1 else "sem_material")


def _confirmar(item: str, disciplina: str, pedidos: list[tuple[int, str, list[dict]]]) -> dict[int, list[int]]:
    """O modelo julga CADA par (subitem, candidato): ensina ou não. Uma chamada por
    item do edital. `pedidos` = [(n, subitem, candidatos)]; devolve {n: [ids]}, só
    com ids que estavam entre os candidatos daquele subitem.

    VEREDITO POR PAR, e não "liste os que ensinam" — medido em 28/09/2026 no mesmo
    item, em lote: pedindo a lista, o modelo deixava subitens vazios que, pedidos
    sozinhos, ele confirmava (Poder Judiciário: 0 no lote, 4 sozinho, nas duas
    rodadas). Com um veredito obrigatório por par ele julgou 100% dos pares, e o
    item de 9 subitens deu o mesmo resultado nas duas rodadas. Temperatura zero:
    é classificação, não redação."""
    from . import llm
    blocos = []
    for n, sub, cands in pedidos:
        trechos = "\n".join(f"  [T{c['id']}] {' '.join(c['texto'].split())[:CHARS_DO_TRECHO_NO_PROMPT]}"
                            for c in cands)
        blocos.append(f"SUBITEM {n}: {sub}\n{trechos}")
    sistema = (
        "Você confere o programa de um edital de concurso contra trechos do material de "
        "estudo de um aluno. Para CADA par (subitem, trecho listado sob ele) dê um veredito: "
        "ensina=true se o trecho explica aquele conteúdo — o conceito, a regra, o instituto; "
        "ensina=false se só menciona o termo de passagem, é sumário, índice, apresentação do "
        "curso ou do professor, cronograma, questão sem explicação, ou é de outro assunto que "
        "usa as mesmas palavras (norma federal não cobre subitem de norma estadual, e vice-"
        "versa). Julgue cada par sozinho. Na dúvida, false: dizer que o material cobre o que "
        "não cobre é o pior erro possível aqui.")
    esquema = {"type": "object", "properties": {"vereditos": {"type": "array", "items": {
        "type": "object", "properties": {"subitem": {"type": "integer"}, "trecho": {"type": "integer"},
                                         "ensina": {"type": "boolean"}},
        "required": ["subitem", "trecho", "ensina"]}}}, "required": ["vereditos"]}
    prompt = (f"Disciplina: {disciplina}\nItem do edital: {item}\n\n" + "\n\n".join(blocos) +
              "\n\nOs ids aparecem como [T<número>]; devolva só o número.")
    r = llm.obter().gerar_json(prompt, sistema, max_tokens=3000, schema=esquema, temperatura=0.0)
    validos = {n: {c["id"] for c in cands} for n, _, cands in pedidos}
    confirmados: dict[int, list[int]] = {n: [] for n, _, _ in pedidos}
    for v in (r or {}).get("vereditos") or []:
        n, t = v.get("subitem"), v.get("trecho")
        if v.get("ensina") is True and n in validos and type(t) is int and t in validos[n] \
                and t not in confirmados[n]:
            confirmados[n].append(t)
    return confirmados


def _gravar(topico_id: int, ordem: int, texto: str, estado: str, metodo: str,
            trechos: list[int]) -> None:
    sid = db.exec1(
        """INSERT INTO edital_subitem (topico_id, ordem, texto, estado, metodo, atualizado_em)
           VALUES (%(t)s, %(o)s, %(x)s, %(e)s, %(m)s, now())
           ON CONFLICT (topico_id, ordem) DO UPDATE
              SET texto = EXCLUDED.texto, estado = EXCLUDED.estado,
                  metodo = EXCLUDED.metodo, atualizado_em = now()
           RETURNING id""",
        {"t": topico_id, "o": ordem, "x": texto, "e": estado, "m": metodo})["id"]
    db.query("DELETE FROM edital_subitem_trecho WHERE subitem_id = %(s)s", {"s": sid})
    for c in trechos:
        db.query("INSERT INTO edital_subitem_trecho (subitem_id, chunk_id) VALUES (%(s)s, %(c)s) "
                 "ON CONFLICT DO NOTHING", {"s": sid, "c": c})


def _edital(mesa_id: int) -> dict | None:
    return db.exec1("SELECT id FROM edital WHERE mesa_id = %(m)s ORDER BY criado_em DESC LIMIT 1",
                    {"m": mesa_id})


def mapear(mesa_id: int, usuario_id: int, disciplinas: list[str] | None = None,
           com_modelo: bool = True) -> dict:
    """Verifica os subitens do edital da mesa (todos, ou só das `disciplinas`)."""
    ed = _edital(mesa_id)
    if not ed:
        return {"subitens": 0, "chamadas": 0}
    alvo = mesa_mod.disciplinas(mesa_id)
    mapa = mesa_mod.mapa_do_acervo(mesa_id, usuario_id, alvo)
    topicos = db.query("SELECT id, disciplina, texto FROM topico WHERE edital_id = %(e)s ORDER BY ordem",
                       {"e": ed["id"]})
    if disciplinas:
        topicos = [t for t in topicos if t["disciplina"] in disciplinas]
    por_disciplina: dict[str, list[dict]] = {}
    for t in topicos:
        por_disciplina.setdefault(t["disciplina"], []).append(t)
    total, chamadas = 0, 0
    for disciplina, tops in por_disciplina.items():
        docs = _documentos(usuario_id, disciplina, mapa)
        perfil = {r["id"]: r for r in db.query(
            """SELECT d.id, d.assunto, (SELECT count(*) FROM chunk c WHERE c.documento_id = d.id) AS trechos
                 FROM documento d WHERE d.id = ANY(%(d)s)""", {"d": docs})}
        preparo = []                              # (topico, [(n, sub, cands, n_lexicais)])
        itens_por_trecho: dict[int, set[int]] = {}
        for t in tops:
            cab = cabecalho(t["texto"])
            subs = []
            for n, sub in enumerate(subitens(t["texto"]), 1):
                cands, lex = _candidatos(sub, cab, docs, perfil) if docs else ([], 0)
                subs.append((n, sub, cands, lex))
                for c in cands:
                    itens_por_trecho.setdefault(c["id"], set()).add(t["id"])
            preparo.append((t, subs))
        indice = {c for c, itens in itens_por_trecho.items() if len(itens) >= ITENS_PARA_SER_INDICE}
        for t, subs in preparo:
            limpos = [(n, sub, [c for c in cands if c["id"] not in indice][:CANDIDATOS_POR_SUBITEM], lex)
                      for n, sub, cands, lex in subs]
            confirmados, metodo = None, "texto"
            pedidos = [(n, sub, cands) for n, sub, cands, _ in limpos if cands]
            if com_modelo and pedidos:
                try:
                    confirmados = _confirmar(cabecalho(t["texto"]) or t["texto"], disciplina, pedidos)
                    metodo = "modelo"
                    chamadas += 1
                except Exception:         # sem cota ou resposta ruim: fica o texto
                    confirmados = None
            for n, sub, cands, lex in limpos:
                if confirmados is not None:
                    ids = confirmados.get(n, [])
                else:
                    # SÓ TEXTO, conservador: só a evidência por expressão conta.
                    ids = [c["id"] for c in cands if not c.get("_sentido")]
                _gravar(t["id"], n, sub, _estado(len(ids)), metodo, ids)
                total += 1
    return {"subitens": total, "chamadas": chamadas}


def marcar_pendente(usuario_id: int, disciplina: str | None) -> int:
    """Material da disciplina mudou: os subitens dela, nas mesas do aluno, voltam
    a "não verificado". Não chama modelo — ver o docstring do módulo."""
    if not disciplina:
        return 0
    marcados = 0
    for m in db.query("SELECT id FROM mesa WHERE usuario_id = %(u)s", {"u": usuario_id}):
        alvo = mesa_mod.disciplinas(m["id"]) or []
        mapa = mesa_mod.mapa_do_acervo(m["id"], usuario_id, alvo)
        donas = [a for a in alvo if disciplina in leitura.nomes_da_disciplina(a, mapa)]
        if donas:
            marcados += len(db.query(
                """UPDATE edital_subitem s SET estado = 'pendente', atualizado_em = now()
                     FROM topico t JOIN edital e ON e.id = t.edital_id
                    WHERE s.topico_id = t.id AND e.mesa_id = %(m)s AND t.disciplina = ANY(%(d)s)
                    RETURNING s.id""", {"m": m["id"], "d": donas}))
    return marcados


def pendentes(mesa_id: int) -> list[str]:
    """Disciplinas da mesa com subitem ainda não verificado (ou nunca mapeado)."""
    ed = _edital(mesa_id)
    if not ed:
        return []
    return [r["disciplina"] for r in db.query(
        """SELECT DISTINCT t.disciplina FROM topico t
            LEFT JOIN edital_subitem s ON s.topico_id = t.id
           WHERE t.edital_id = %(e)s
             AND (s.id IS NULL OR s.estado = 'pendente'
                  -- O resultado só por texto (sem cota) volta a ser verificado,
                  -- mas no máximo a cada 6 h: sem esse espaço, cada visita à tela
                  -- sem cota pagaria dezenas de 429.
                  OR (s.metodo = 'texto' AND s.atualizado_em < now() - interval '6 hours'))""",
        {"e": ed["id"]})]


# Uma verificação por mesa de cada vez: a tela pede o mapa a cada visita, e duas
# abas abertas não podem pagar duas vezes as mesmas chamadas ao modelo.
TRAVA_COBERTURA = 35


def verificar_pendentes(mesa_id: int, usuario_id: int, tudo: bool = False) -> dict:
    """Para BackgroundTasks: verifica as disciplinas pendentes (ou `tudo`).
    Silencioso; quem perde a trava desiste, porque quem ganhou faz o mesmo."""
    vazio = {"subitens": 0, "chamadas": 0}
    try:
        with db.conexao_isolada() as c, c.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s, %s) AS meu", (TRAVA_COBERTURA, mesa_id))
            if not cur.fetchone()["meu"]:
                return vazio
            faltam = None if tudo else pendentes(mesa_id)
            if faltam == []:
                return vazio
            return mapear(mesa_id, usuario_id, faltam)
    except Exception:
        return vazio


def resumo_por_disciplina(mesa_id: int) -> list[dict]:
    """Quantos subitens de cada disciplina têm material, sem e ainda sem verificar."""
    ed = _edital(mesa_id)
    if not ed:
        return []
    return db.query(
        """SELECT t.disciplina,
                  count(s.id) AS subitens,
                  count(s.id) FILTER (WHERE s.estado = 'coberto') AS cobertos,
                  count(s.id) FILTER (WHERE s.estado = 'citado') AS citados,
                  count(s.id) FILTER (WHERE s.estado = 'sem_material') AS sem_material,
                  count(s.id) FILTER (WHERE s.estado = 'pendente') AS pendentes
             FROM topico t LEFT JOIN edital_subitem s ON s.topico_id = t.id
            WHERE t.edital_id = %(e)s
            GROUP BY t.disciplina ORDER BY min(t.ordem)""", {"e": ed["id"]})


def resumo_geral_para_prompt(mesa_id: int) -> str | None:
    """Uma linha por disciplina — é o que responde "o que me falta?" sem busca."""
    linhas = [r for r in resumo_por_disciplina(mesa_id) if r["subitens"]]
    if not linhas:
        return None
    return "\n".join(
        f"- {r['disciplina']}: {r['cobertos']} de {r['subitens']} subitens com material"
        + (f", {r['citados']} só citados" if r["citados"] else "")
        + (f", {r['sem_material']} SEM MATERIAL" if r["sem_material"] else "")
        + (f", {r['pendentes']} ainda não verificados" if r["pendentes"] else "")
        for r in linhas)


def mapa_do_edital(mesa_id: int, usuario_id: int, disciplina: str | None = None) -> list[dict]:
    """O mapa para a tela e para o prompt: itens em ordem, cada subitem com estado e
    onde está (apostila e páginas). Só trechos do próprio aluno."""
    ed = _edital(mesa_id)
    if not ed:
        return []
    linhas = db.query(
        """SELECT t.id AS topico_id, t.disciplina, t.ordem AS t_ordem, t.texto AS topico,
                  s.id AS subitem_id, s.ordem, s.texto, s.estado, s.metodo,
                  d.id AS documento_id, d.assunto, d.titulo, c.pagina, c.ordem AS c_ordem
             FROM topico t
             LEFT JOIN edital_subitem s ON s.topico_id = t.id
             LEFT JOIN edital_subitem_trecho st ON st.subitem_id = s.id
             LEFT JOIN chunk c ON c.id = st.chunk_id
             LEFT JOIN documento d ON d.id = c.documento_id AND d.usuario_id = %(u)s
            WHERE t.edital_id = %(e)s AND (%(disc)s::text IS NULL OR t.disciplina = %(disc)s)
            ORDER BY t.ordem, s.ordem, d.id, c.ordem""",
        {"e": ed["id"], "u": usuario_id, "disc": disciplina})
    itens: dict[int, dict] = {}
    for r in linhas:
        item = itens.setdefault(r["topico_id"], {
            "topico_id": r["topico_id"], "disciplina": r["disciplina"], "texto": r["topico"],
            "item": cabecalho(r["topico"]), "subitens": {}})
        if r["subitem_id"] is None:
            continue
        sub = item["subitens"].setdefault(r["subitem_id"], {
            "id": r["subitem_id"], "ordem": r["ordem"], "texto": r["texto"],
            "estado": r["estado"], "metodo": r["metodo"], "_docs": {}})
        if r["documento_id"]:
            doc = sub["_docs"].setdefault(r["documento_id"], {
                "documento_id": r["documento_id"], "assunto": r["assunto"] or r["titulo"],
                "_paginas": [], "_ordens": []})
            doc["_paginas"].append(r["pagina"])
            doc["_ordens"].append(r["c_ordem"])
    saida = []
    for item in itens.values():
        subs = []
        for sub in item["subitens"].values():
            materiais = [{"documento_id": d["documento_id"], "assunto": d["assunto"],
                          "paginas": paginas(d["_paginas"])} for d in sub.pop("_docs").values()]
            subs.append({**sub, "materiais": materiais})
        saida.append({**item, "subitens": sorted(subs, key=lambda s: s["ordem"])})
    return saida


def proximo_subitem(mesa_id: int, usuario_id: int, disciplina: str,
                    lidos: set[int]) -> tuple[dict | None, list[str]]:
    """O próximo ponto do edital, NA ORDEM OFICIAL, que tem material e ainda não
    foi lido (nenhum dos trechos dele está em `lidos`), e os pontos sem material.

    Devolve ({"item", "texto", "documento_id", "ordem"}, sem_material): a leitura
    abre o material onde o ponto começa — o primeiro trecho dele na apostila."""
    sem_material, proximo = [], None
    for item in mapa_do_edital(mesa_id, usuario_id, disciplina):
        for s in item["subitens"]:
            if s["estado"] == "sem_material":
                sem_material.append(s["texto"])
            if proximo or s["estado"] not in ("coberto", "citado"):
                continue
            trechos = db.query(
                """SELECT c.id, c.documento_id, c.ordem FROM edital_subitem_trecho st
                     JOIN chunk c ON c.id = st.chunk_id
                     JOIN documento d ON d.id = c.documento_id AND d.usuario_id = %(u)s
                    WHERE st.subitem_id = %(s)s ORDER BY c.documento_id, c.ordem""",
                {"s": s["id"], "u": usuario_id})
            if trechos and not any(t["id"] in lidos for t in trechos):
                primeiro = trechos[0]
                proximo = {"item": item["item"], "texto": s["texto"],
                           "documento_id": primeiro["documento_id"], "ordem": primeiro["ordem"]}
    return proximo, sem_material


def localizar(mesa_id: int, usuario_id: int, fala: str | None, limite: int = 4) -> str | None:
    """Os pontos do edital que a FALA menciona, com onde estão no material.

    "Onde está nacionalidade?" não nomeia a disciplina, e o programa com as
    páginas só entrava no prompt com ela nomeada — o tutor respondeu "na aula
    05", sem página (28/09/2026). Casa o subitem inteiro, sem acento e por
    palavra, dentro da fala; subitem genérico ("conceito, divisões…") não casa."""
    if not fala:
        return None
    normal = lambda t: " " + " ".join(assunto._sem_acento(p) for p in
                                      assunto.RE_PALAVRA.findall(t.lower())) + " "
    na_fala = normal(fala)
    achados = []
    for item in mapa_do_edital(mesa_id, usuario_id):
        for s in item["subitens"]:
            alvo = normal(s["texto"])
            if len(alvo.split()) and not RE_GENERICO.match(s["texto"]) and alvo in na_fala:
                achados.append((item, s))
    if not achados:
        return None
    linhas = []
    for item, s in achados[:limite]:
        # O ITEM DO EDITAL e a APOSTILA vão rotulados: sem rótulo, o modelo leu o
        # nome do item ("Direitos e garantias fundamentais") como se fosse o da
        # apostila, que era a aula de Nacionalidade.
        ponto = f"- \"{s['texto']}\" (edital: {item['disciplina']}, item \"{item['item']}\")"
        if s["estado"] in ("coberto", "citado") and s["materiais"]:
            onde = "; ".join(f"apostila \"{m['assunto']}\"" + (f", p. {m['paginas']}" if m["paginas"] else "")
                             for m in s["materiais"])
            linhas.append(f"{ponto} → está em: {onde}"
                          + (" (só citado, não é aula)" if s["estado"] == "citado" else ""))
        elif s["estado"] == "sem_material":
            linhas.append(f"{ponto} → SEM MATERIAL")
        else:
            linhas.append(f"{ponto} → ainda não verificado")
    return "\n".join(linhas)


def resumo_para_prompt(mesa_id: int, usuario_id: int, disciplina: str) -> str | None:
    """Uma linha por item: cada subitem com onde está, ou "sem material". É o que
    deixa o tutor responder "onde está X" e "o que me falta" com o dado, e não
    com a busca do turno."""
    itens = mapa_do_edital(mesa_id, usuario_id, disciplina)
    if not itens:
        return None
    linhas = []
    for item in itens:
        partes = []
        for s in item["subitens"]:
            if s["estado"] in ("coberto", "citado"):
                onde = "; ".join(f"{m['assunto']}, p. {m['paginas']}" if m["paginas"] else m["assunto"]
                                 for m in s["materiais"])
                partes.append(f"{s['texto']} ({'só citado em ' if s['estado'] == 'citado' else ''}{onde})")
            elif s["estado"] == "sem_material":
                partes.append(f"{s['texto']} (SEM MATERIAL)")
            else:
                partes.append(f"{s['texto']} (ainda não verificado)")
        linhas.append(f"- {item['item']}: " + "; ".join(partes) if partes else f"- {item['item']}")
    return "\n".join(linhas)
