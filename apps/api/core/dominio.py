"""
MAPA DE DOMÍNIO — o edital da mesa, assunto por assunto: o que o aluno já
percorreu (leu com o tutor ou respondeu questão), onde está no ciclo de revisão
e o que pede atenção.

DE ONDE VEM A LIGAÇÃO trecho/questão -> assunto do edital (`topico`), em ordem:

  1. `assunto_no_edital` (038): o assunto do ÍNDICE do material (036) ligado a
     um assunto do edital. O modelo lê, uma chamada por material, a lista de
     nomes do índice contra a lista de assuntos do edital da disciplina
     (`ligar`). Sem cota, a reserva por palavras distintivas grava
     `origem='texto'`, refeita quando houver.
  2. o trecho ligado a um subitem do edital (035);
  3. `questao_no_edital` (039): a questão que não chega por trecho (a de PROVA,
     cujo trecho é do simulado, sem índice; a gerada de lei) é ligada pelo
     ENUNCIADO, um lote por disciplina, pelo mesmo modelo e com a mesma reserva.

Empate ou pouco em comum = sem assunto. Ligar errado faz o mapa mentir; a
contagem do que ficou sem assunto vai para a tela.

Medido em 02/10/2026 (conta real, 110 assuntos no edital, 119 nomes no índice):
pela camada 2 só 1 de 108 questões chegava a um assunto; palavras em comum
põem "Verbos" em "Modos de organização discursiva" ("modo"); os vetores
locais erram com folga grande ("Princípios fundamentais" -> "Direitos e
garantias"). Por isso o modelo na camada 1, e as palavras só como reserva.

Ciclo do assunto = o da sua questão MAIS FRACA (menor caixa) e a revisão mais
próxima: o assunto não está dominado enquanto uma questão dele volta amanhã.
Dominado = caixa >= 3 (15 dias), o mesmo limiar de `scheduler.meta`.
"""
import math
from datetime import date, datetime

from . import assunto, db, indice, llm, scheduler_regras as R
from .cobertura import _edital, cabecalho

VERSAO = "dominio-v5"

CAIXA_DOMINIO = 3
# ESTUDADO = leu a maior parte do material do assunto (02/10/2026). Antes, um trecho
# lido ou uma questão respondida marcava o assunto inteiro: na bateria de estudo o
# aluno leu menos de 10% dos trechos e todo assunto com material saía "estudado".
LIMIAR_LIDO = 0.7
MAX_HISTORICO = 8
TRAVA_DOMINIO = 38038      # pg_try_advisory_lock(TRAVA_DOMINIO, edital_id)
CHARS_DO_TOPICO = 260
CHARS_DO_ENUNCIADO = 350
LOTE_QUESTOES = 12          # 25 enunciados estouraram 4000 tokens de resposta (02/10/2026)
# Reserva por palavras: o melhor precisa de pontos e de folga sobre o segundo.
MIN_PONTOS = 1.5
FOLGA = 1.5


# ------------------------------------------------------------------ puros
def raizes(texto: str) -> set[str]:
    """Raízes de 6 letras sem acento e sem o plural das palavras de conteúdo. PURO.
    Sem tirar o "s", "verbos" (verbos) e "verbo" (verbo) eram raízes diferentes."""
    saida = set()
    for p in assunto.palavras_de_conteudo(texto or ""):
        if len(p) < 4 or p.isdigit():
            continue
        p = assunto._sem_acento(p)
        saida.add((p[:-1] if p.endswith("s") else p)[:6])
    return saida


def pesos(topicos: list[dict]) -> dict[str, float]:
    """Raridade de cada raiz entre os assuntos de UMA disciplina. PURO."""
    n = len(topicos)
    df: dict[str, int] = {}
    for t in topicos:
        for r in raizes(t["texto"]):
            df[r] = df.get(r, 0) + 1
    return {r: math.log(1 + n / c) for r, c in df.items()}


def por_palavras(texto: str, topicos: list[dict], idf: dict[str, float]) -> int | None:
    """O assunto com mais palavras distintivas em comum, com folga; senão None. PURO."""
    sinal = raizes(texto)
    notas = sorted(((sum(idf.get(r, 0) for r in sinal & raizes(t["texto"])), t["id"]) for t in topicos),
                   reverse=True)
    if not notas or notas[0][0] < MIN_PONTOS:
        return None
    if len(notas) > 1 and notas[0][0] < notas[1][0] * FOLGA:
        return None
    return notas[0][1]


def letra(veredito: str, dicas: int) -> str:
    """c = acerto limpo, d = acerto com dica ou meio acerto, e = erro. PURO."""
    if veredito == "correta":
        return "c" if not dicas else "d"
    return "d" if veredito == "parcial" else "e"


def nivel(trechos: int, lidos: int, questoes: int, contato: bool) -> str:
    """nenhum · contato (encostou: leu pouco ou só respondeu) · lido (leu ≥ LIMIAR_LIDO
    do material) · so_questoes (não há material do assunto; estudou por questões). PURO."""
    if trechos:
        if lidos / trechos >= LIMIAR_LIDO:
            return "lido"
        return "contato" if (lidos or questoes or contato) else "nenhum"
    if questoes:
        return "so_questoes"
    return "contato" if contato else "nenhum"


def estado(estudado: bool, caixa: int | None, faltam: int | None) -> str:
    """ns não estudado · nr estudado sem revisão · sc em dia · td hoje ·
    od atrasado · st sem contato (atrasado mais que o intervalo da caixa). PURO."""
    if caixa is None:
        return "nr" if estudado else "ns"
    if faltam is None or faltam > 0:
        return "sc"
    if faltam == 0:
        return "td"
    return "od" if -faltam <= R.dias_ate_revisao(caixa) else "st"


def _dias(quando, hoje: date) -> int | None:
    if quando is None:
        return None
    d = quando.date() if isinstance(quando, datetime) else quando
    return (hoje - d).days


# ------------------------------------------------------------------ banco
def _topicos(edital_id: int) -> dict[str, list[dict]]:
    por: dict[str, list[dict]] = {}
    for t in db.query("SELECT id, disciplina, ordem, texto FROM topico WHERE edital_id = %(e)s ORDER BY ordem",
                      {"e": edital_id}):
        por.setdefault(t["disciplina"], []).append(t)
    return por


def _do_edital(mesa: dict, por_disc: dict[str, list[dict]]) -> dict[str, str]:
    """Nome de disciplina (do material ou da questão) -> disciplina do edital."""
    saida = {d: d for d in por_disc}
    for d, nomes in (mesa.get("mapa") or {}).items():
        if d in por_disc:
            for n in nomes:
                saida.setdefault(n, d)
    return saida


def _sem_ligacao(mesa: dict, usuario_id: int, edital_id: int, refazer_texto: bool) -> list[dict]:
    """Assuntos do índice dos materiais do aluno ainda sem ligação a este edital."""
    return db.query(
        """SELECT ma.id, ma.nome, ma.documento_id, d.disciplina
             FROM material_assunto ma JOIN documento d ON d.id = ma.documento_id
            WHERE d.usuario_id = %(u)s AND ma.papel <> 'outro' AND d.tipo <> 'simulado'
              AND NOT EXISTS (SELECT 1 FROM assunto_no_edital ae
                               WHERE ae.assunto_id = ma.id AND ae.edital_id = %(e)s
                                 AND NOT (%(r)s AND ae.origem = 'texto'))
            ORDER BY ma.documento_id, ma.ordem""",
        {"u": usuario_id, "e": edital_id, "r": refazer_texto})


# Liga por trecho = algum trecho dela tem assunto do índice já ligado a um assunto do edital.
_LIGA_POR_TRECHO = """EXISTS (SELECT 1 FROM unnest(q.fonte_chunks) AS c(id)
                               JOIN chunk_assunto ca ON ca.chunk_id = c.id
                               JOIN assunto_no_edital ae ON ae.assunto_id = ca.assunto_id
                              WHERE ae.edital_id = %(e)s AND ae.topico_id IS NOT NULL)"""


def _questoes_sem_ligacao(usuario_id: int, edital_id: int, refazer_texto: bool) -> list[dict]:
    """Questões do aluno (dele, ou que ele respondeu) sem caminho até o edital."""
    return db.query(
        f"""SELECT q.id, q.disciplina, q.tema, q.enunciado FROM questao q
             WHERE (q.usuario_id = %(u)s OR EXISTS (SELECT 1 FROM tentativa t
                                                     WHERE t.usuario_id = %(u)s AND t.questao_id = q.id))
               AND NOT {_LIGA_POR_TRECHO}
               AND NOT EXISTS (SELECT 1 FROM questao_no_edital qe
                                WHERE qe.questao_id = q.id AND qe.edital_id = %(e)s
                                  AND NOT (%(r)s AND qe.origem = 'texto'))
             ORDER BY q.disciplina, q.id""",
        {"u": usuario_id, "e": edital_id, "r": refazer_texto})


ESQ_LIGACAO_Q = {"type": "OBJECT", "properties": {"ligacoes": {"type": "ARRAY", "items": {"type": "OBJECT",
    "properties": {"questao": {"type": "INTEGER"}, "topico": {"type": "INTEGER"}},
    "required": ["questao", "topico"]}}}, "required": ["ligacoes"]}
SIS_LIGACAO_Q = (
    "Você recebe os ASSUNTOS DO EDITAL de uma disciplina de concurso, numerados, e questões dessa "
    "disciplina, também numeradas. Para cada questão, diga qual assunto do edital ela cobra — o que o "
    "candidato precisa ter estudado para acertá-la. Use topico 0 quando nenhum assunto do edital a cobre. "
    "Responda todas as questões, com os números dados.")


def _ligar_questoes_modelo(itens: list[dict], topicos: list[dict]) -> dict[int, int | None]:
    edital = "\n".join(f"{t['id']}: {t['texto'][:CHARS_DO_TOPICO]}" for t in topicos)
    questoes = "\n".join(f"{i['id']}: {' '.join((i['enunciado'] or '').split())[:CHARS_DO_ENUNCIADO]}"
                         for i in itens)
    r = llm.obter("indice").gerar_json(f"### Assuntos do edital\n{edital}\n\n### Questões\n{questoes}",
                                       SIS_LIGACAO_Q, max_tokens=6000, schema=ESQ_LIGACAO_Q,
                                       temperatura=0.0) or {}
    validos, pedidos = {t["id"] for t in topicos}, {i["id"] for i in itens}
    return {x["questao"]: (x["topico"] if x.get("topico") in validos else None)
            for x in r.get("ligacoes") or [] if x.get("questao") in pedidos}


ESQ_LIGACAO = {"type": "OBJECT", "properties": {"ligacoes": {"type": "ARRAY", "items": {"type": "OBJECT",
    "properties": {"assunto": {"type": "INTEGER"}, "topico": {"type": "INTEGER"}},
    "required": ["assunto", "topico"]}}}, "required": ["ligacoes"]}
SIS_LIGACAO = (
    "Você recebe os ASSUNTOS DO EDITAL de uma disciplina de concurso, numerados, e os assuntos de uma "
    "apostila dessa disciplina, também numerados. Para cada assunto da apostila, diga em qual assunto do "
    "edital ele se encaixa — aquele cujo programa o inclui, mesmo que com outras palavras ('Verbos' cabe em "
    "'Classes de palavras'; 'Habeas corpus' cabe em 'Remédios constitucionais'). Use topico 0 quando "
    "nenhum assunto do edital o inclui. Responda todos os assuntos da apostila, com os números dados.")


def _ligar_modelo(itens: list[dict], topicos: list[dict]) -> dict[int, int | None]:
    edital = "\n".join(f"{t['id']}: {t['texto'][:CHARS_DO_TOPICO]}" for t in topicos)
    apostila = "\n".join(f"{i['id']}: {i['nome']}" for i in itens)
    r = llm.obter("indice").gerar_json(f"### Assuntos do edital\n{edital}\n\n### Assuntos da apostila\n{apostila}",
                                       SIS_LIGACAO, max_tokens=4000, schema=ESQ_LIGACAO, temperatura=0.0) or {}
    validos = {t["id"] for t in topicos}
    pedidos = {i["id"] for i in itens}
    saida: dict[int, int | None] = {}
    for x in r.get("ligacoes") or []:
        a, t = x.get("assunto"), x.get("topico")
        if a in pedidos:
            saida[a] = t if t in validos else None
    return saida


def ligar(mesa: dict, usuario_id: int, com_modelo: bool = True) -> dict:
    """Liga os assuntos do índice ainda soltos ao edital da mesa. Uma chamada ao
    modelo por material; sem cota ou sem resposta, a reserva por palavras.
    Uma vez por edital (trava no banco); erro nunca sobe."""
    ed = _edital(mesa["id"])
    if not ed:
        return {"ligados": 0}
    with db.conexao_isolada() as c, c.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s, %s) AS meu", (TRAVA_DOMINIO, ed["id"]))
        if not cur.fetchone()["meu"]:
            return {"ocupado": True}
        try:
            por_disc = _topicos(ed["id"])
            do_edital = _do_edital(mesa, por_disc)
            idf = {d: pesos(ts) for d, ts in por_disc.items()}
            grupos: dict[tuple[int, str], list[dict]] = {}
            for i in _sem_ligacao(mesa, usuario_id, ed["id"], refazer_texto=com_modelo):
                d = do_edital.get(i["disciplina"] or "")
                if d:
                    grupos.setdefault((i["documento_id"], d), []).append(i)
            n = 0
            for (_, d), itens in grupos.items():
                resposta, origem = {}, "texto"
                if com_modelo and indice.gasto_hoje() + 1 <= indice.ORCAMENTO_DIA:
                    try:
                        resposta, origem = _ligar_modelo(itens, por_disc[d]), "modelo"
                    except llm.ErroLLM as e:
                        print(f"[dominio] modelo indisponível ({str(e)[:80]}); reserva")
                for i in itens:
                    if origem == "modelo" and i["id"] not in resposta:
                        continue          # o modelo pulou: fica pendente
                    t = resposta.get(i["id"]) if origem == "modelo" else por_palavras(i["nome"], por_disc[d], idf[d])
                    db.query("""INSERT INTO assunto_no_edital (assunto_id, edital_id, topico_id, origem)
                                VALUES (%(a)s, %(e)s, %(t)s, %(o)s)
                                ON CONFLICT (assunto_id, edital_id) DO UPDATE
                                   SET topico_id = EXCLUDED.topico_id, origem = EXCLUDED.origem, em = now()""",
                             {"a": i["id"], "e": ed["id"], "t": t, "o": origem})
                    n += 1
            # Depois dos assuntos: uma questão pode passar a chegar pelo trecho.
            lotes: dict[str, list[dict]] = {}
            for q in _questoes_sem_ligacao(usuario_id, ed["id"], refazer_texto=com_modelo):
                d = do_edital.get(q["disciplina"] or "")
                if d:
                    lotes.setdefault(d, []).append(q)
            for d, qs in lotes.items():
                for i in range(0, len(qs), LOTE_QUESTOES):
                    lote = qs[i:i + LOTE_QUESTOES]
                    resposta, origem = {}, "texto"
                    if com_modelo and indice.gasto_hoje() + 1 <= indice.ORCAMENTO_DIA:
                        try:
                            resposta, origem = _ligar_questoes_modelo(lote, por_disc[d]), "modelo"
                        except llm.ErroLLM as e:
                            print(f"[dominio] modelo indisponível ({str(e)[:80]}); reserva")
                    for q in lote:
                        if origem == "modelo" and q["id"] not in resposta:
                            continue
                        t = resposta.get(q["id"]) if origem == "modelo" else \
                            por_palavras(f"{q['tema']} {q['enunciado']}", por_disc[d], idf[d])
                        db.query("""INSERT INTO questao_no_edital (questao_id, edital_id, topico_id, origem)
                                    VALUES (%(q)s, %(e)s, %(t)s, %(o)s)
                                    ON CONFLICT (questao_id, edital_id) DO UPDATE
                                       SET topico_id = EXCLUDED.topico_id, origem = EXCLUDED.origem, em = now()""",
                                 {"q": q["id"], "e": ed["id"], "t": t, "o": origem})
                        n += 1
            return {"ligados": n}
        except Exception as e:  # noqa: BLE001 — tarefa de fundo
            print(f"[dominio] ligar falhou ({e})")
            return {"falha": str(e)[:120]}
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s, %s)", (TRAVA_DOMINIO, ed["id"]))


def pendente(mesa: dict, usuario_id: int) -> bool:
    ed = _edital(mesa["id"])
    return bool(ed and (_sem_ligacao(mesa, usuario_id, ed["id"], refazer_texto=False)
                        or _questoes_sem_ligacao(usuario_id, ed["id"], refazer_texto=False)))


def mapa(mesa: dict, usuario_id: int, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    ed = _edital(mesa["id"])
    if not ed:
        return {"disciplinas": [], "totais": None, "intervalos": R.INTERVALOS}
    por_disc = _topicos(ed["id"])
    do_edital = _do_edital(mesa, por_disc)

    def topicos_dos_trechos(ids: list[int]) -> dict[int, int]:
        """trecho -> assunto do edital, pelas camadas 1 e 2."""
        if not ids:
            return {}
        saida: dict[int, int] = {}
        for r in db.query(
                """SELECT DISTINCT ON (st.chunk_id) st.chunk_id, s.topico_id
                     FROM edital_subitem_trecho st JOIN edital_subitem s ON s.id = st.subitem_id
                     JOIN topico t ON t.id = s.topico_id
                    WHERE t.edital_id = %(e)s AND st.chunk_id = ANY(%(i)s)""", {"e": ed["id"], "i": ids}):
            saida[r["chunk_id"]] = r["topico_id"]
        # O índice manda: é a ligação feita pela leitura do material inteiro.
        # Trecho com mais de um assunto fica com o do papel 'ensino' primeiro.
        for r in db.query(
                """SELECT DISTINCT ON (ca.chunk_id) ca.chunk_id, ae.topico_id
                     FROM chunk_assunto ca JOIN assunto_no_edital ae ON ae.assunto_id = ca.assunto_id
                    WHERE ae.edital_id = %(e)s AND ae.topico_id IS NOT NULL AND ca.chunk_id = ANY(%(i)s)
                    ORDER BY ca.chunk_id, (ca.papel = 'ensino') DESC""", {"e": ed["id"], "i": ids}):
            saida[r["chunk_id"]] = r["topico_id"]
        return saida

    info: dict[int, dict] = {}

    def de(tid: int) -> dict:
        return info.setdefault(tid, {"hist": [], "q": 0, "caixas": {}, "revisoes": {}, "contato": None})

    # ---- questões que o aluno já respondeu
    tentativas = db.query(
        """SELECT t.questao_id, t.veredito, t.dicas_usadas, t.criada_em, q.origem,
                  q.disciplina, q.enunciado, q.fonte_chunks, p.caixa, p.prox_revisao
             FROM tentativa t JOIN questao q ON q.id = t.questao_id
             LEFT JOIN progresso p ON p.usuario_id = t.usuario_id AND p.questao_id = t.questao_id
            WHERE t.usuario_id = %(u)s ORDER BY t.criada_em""", {"u": usuario_id})
    do_trecho = topicos_dos_trechos(sorted({c for t in tentativas for c in (t["fonte_chunks"] or [])}))
    pelo_enunciado = {r["questao_id"]: r["topico_id"] for r in db.query(
        """SELECT questao_id, topico_id FROM questao_no_edital
            WHERE edital_id = %(e)s AND questao_id = ANY(%(q)s)""",
        {"e": ed["id"], "q": list({t["questao_id"] for t in tentativas})})} if tentativas else {}
    da_questao: dict[int, int | None] = {}
    sem_assunto: dict[str, set[int]] = {}
    for t in tentativas:
        qid = t["questao_id"]
        d = do_edital.get(t["disciplina"] or "")
        if qid not in da_questao:
            tid = next((do_trecho[c] for c in t["fonte_chunks"] or [] if c in do_trecho), None)
            da_questao[qid] = tid if tid is not None else pelo_enunciado.get(qid)
        tid = da_questao[qid]
        if tid is None:
            if d:
                sem_assunto.setdefault(d, set()).add(qid)
            continue
        i = de(tid)
        i["hist"].append(letra(t["veredito"], t["dicas_usadas"]))
        i["q"] += 1
        if t["caixa"] is not None:
            i["caixas"][qid] = t["caixa"]
            i["revisoes"][qid] = t["prox_revisao"]
        i["contato"] = max(filter(None, [i["contato"], t["criada_em"]]))

    # ---- trechos lidos com o tutor (leitura em sequência ou fonte citada)
    lidos = db.query(
        """SELECT (f->>'id')::bigint AS chunk_id, max(m.criada_em) AS quando
             FROM conversa cv JOIN mensagem m ON m.conversa_id = cv.id,
                  jsonb_array_elements(m.fontes) f
            WHERE cv.usuario_id = %(u)s AND m.autor = 'tutor'
              AND ((f->>'sequencial')::boolean OR (f->>'citada')::boolean)
            GROUP BY 1""", {"u": usuario_id})
    do_lido = topicos_dos_trechos([r["chunk_id"] for r in lidos])
    for r in lidos:
        tid = do_lido.get(r["chunk_id"])
        if tid is not None:
            i = de(tid)
            i["contato"] = max(filter(None, [i["contato"], r["quando"]]))

    # ---- o material de cada assunto: trechos de ENSINO do índice ligados a ele
    ids_lidos = {r["chunk_id"] for r in lidos}
    trechos_do: dict[int, set[int]] = {}
    materiais_do: dict[int, dict[tuple, dict]] = {}
    for r in db.query(
            """SELECT ae.topico_id, ca.chunk_id, d.id AS documento_id, coalesce(d.assunto, d.titulo) AS material,
                      ma.nome, ma.pagina_inicio, ma.pagina_fim
                 FROM assunto_no_edital ae
                 JOIN material_assunto ma ON ma.id = ae.assunto_id
                 JOIN documento d ON d.id = ma.documento_id
                 JOIN chunk_assunto ca ON ca.assunto_id = ma.id AND ca.papel = 'ensino'
                WHERE ae.edital_id = %(e)s AND ae.topico_id IS NOT NULL AND d.usuario_id = %(u)s""",
            {"e": ed["id"], "u": usuario_id}):
        trechos_do.setdefault(r["topico_id"], set()).add(r["chunk_id"])
        m = materiais_do.setdefault(r["topico_id"], {}).setdefault((r["documento_id"], r["nome"]), {
            "documento_id": r["documento_id"], "material": r["material"], "assunto": r["nome"],
            "pagina_inicio": r["pagina_inicio"], "pagina_fim": r["pagina_fim"], "trechos": 0, "lidos": 0})
        m["trechos"] += 1
        m["lidos"] += r["chunk_id"] in ids_lidos

    # ---- montagem
    disciplinas = []
    for d, ts in por_disc.items():
        assuntos = []
        for t in ts:
            i = info.get(t["id"])
            caixa = min(i["caixas"].values()) if i and i["caixas"] else None
            prox = min(filter(None, i["revisoes"].values()), default=None) if i else None
            faltam = (prox - hoje).days if prox else None
            trechos = trechos_do.get(t["id"], set())
            n_lidos = len(trechos & ids_lidos)
            niv = nivel(len(trechos), n_lidos, i["q"] if i else 0, bool(i))
            assuntos.append({
                "id": t["id"], "nome": t["texto"], "item": cabecalho(t["texto"]),
                "estado": estado(niv != "nenhum", caixa, faltam),
                "nivel": niv, "estudado": niv in ("lido", "so_questoes"),
                "material_trechos": len(trechos), "material_lidos": n_lidos,
                "leitura_pct": round(100 * n_lidos / len(trechos)) if trechos else None,
                "materiais": sorted(materiais_do.get(t["id"], {}).values(),
                                    key=lambda m: (m["documento_id"], m["pagina_inicio"] or 0)),
                "estagio": R.dias_ate_revisao(caixa) if caixa is not None else 0,
                # Dominar exige ter ESTUDADO: questão em dia com o material do assunto
                # sem ler é acerto de questão, não domínio do assunto.
                "dominado": caixa is not None and caixa >= CAIXA_DOMINIO and niv in ("lido", "so_questoes"),
                "questoes_em_dia": caixa is not None and caixa >= CAIXA_DOMINIO,
                "proxima_em": faltam, "ultimo_contato": _dias(i["contato"], hoje) if i else None,
                "questoes": i["q"] if i else 0,
                # EVIDÊNCIA: questões DIFERENTES do assunto no ciclo. Na conta real, 33 de
                # 53 assuntos ligados tinham uma só — "dominado" era o veredito de uma
                # questão. Fica verde, e a tela diz em quantas se apoia.
                "questoes_distintas": len(i["caixas"]) if i else 0,
                "historico": "".join(i["hist"][-MAX_HISTORICO:]) if i else ""})
        disciplinas.append({"nome": d, "assuntos": assuntos, "total": len(assuntos),
                            **_contas(assuntos), "questoes_sem_assunto": len(sem_assunto.get(d, ()))})
    todos = [a for d in disciplinas for a in d["assuntos"]]
    return {"edital": ed["id"], "intervalos": R.INTERVALOS, "limiar_lido": LIMIAR_LIDO,
            "disciplinas": disciplinas,
            "totais": {"total": len(todos), **_contas(todos),
                       "hoje": sum(a["estado"] == "td" for a in todos)}}


def _contas(assuntos: list[dict]) -> dict:
    """As contas de uma lista de assuntos — as MESMAS para o mapa, o Meu edital e o
    Panorama, para nenhuma tela contar diferente da outra. PURO."""
    dom = sum(a["dominado"] for a in assuntos)
    tocados = sum(a["nivel"] != "nenhum" for a in assuntos)
    return {"estudados": sum(a["estudado"] for a in assuntos),
            "em_andamento": sum(a["nivel"] == "contato" for a in assuntos),
            "dominados": dom,
            # camada amarela: já começou e ainda não domina
            "em_construcao": sum(a["nivel"] != "nenhum" and not a["dominado"] for a in assuntos),
            "tocados": tocados,
            "com_material": sum(a["material_trechos"] > 0 for a in assuntos),
            "material_nao_lido": sum(a["material_trechos"] > 0 and a["nivel"] != "lido" for a in assuntos)}


def resumo_para_prompt(mesa: dict, usuario_id: int) -> str | None:
    """Uma linha por disciplina: quantos assuntos do edital têm material, quanto foi
    lido e quais não têm material. É o que responde "o que me falta?" sem busca —
    pelas mesmas contas do mapa (substituiu o resumo por subitem do 035, que dava
    "sem material" para assunto com apostila)."""
    m = mapa(mesa, usuario_id)
    if not m["totais"]:
        return None
    linhas = []
    for d in m["disciplinas"]:
        sem = [a["item"][:80] for a in d["assuntos"] if not a["material_trechos"]]
        nunca = [a["item"][:80] for a in d["assuntos"] if a["nivel"] == "nenhum"]
        questoes = sum(a["questoes"] for a in d["assuntos"])
        linhas.append(
            f"- {d['nome']}: {d['tocados']} de {d['total']} assuntos COMEÇADOS"
            + f" ({d['estudados']} estudados, {d['dominados']} dominados; {questoes} questões respondidas)"
            + f"; {d['com_material']} com material"
            + (f" ({d['com_material'] - d['material_nao_lido']} já lidos)" if d["com_material"] else "")
            + (f"; NUNCA TOCADOS: {'; '.join(nunca[:6])}{'…' if len(nunca) > 6 else ''}" if nunca else "")
            + (f"; SEM MATERIAL: {'; '.join(sem[:6])}{'…' if len(sem) > 6 else ''}" if sem else ""))
    zeradas = [d["nome"] for d in m["disciplinas"] if not d["tocados"]]
    linhas.append("Disciplinas sem NENHUM assunto começado: " + (", ".join(zeradas) if zeradas else "nenhuma"))
    return "\n".join(linhas)
