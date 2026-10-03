#!/usr/bin/env python3
"""
BATERIA DE DECISÕES: todas as falas reais, pela lógica do chat, SEM modelo.

    python bateria_decisoes.py              # conta real (só LEITURA no banco)
    python bateria_decisoes.py --email x@y  # outra conta

Para cada fala do aluno, com o estado da conversa NAQUELE momento (histórico e
o que já tinha sido lido), refaz o que o chat decide antes de chamar o modelo:
ler o material ou buscar, a matéria em foco, os trechos que iriam ao prompt,
se viram cartões (e de onde) ou resolução. Depois confere o que não pode
acontecer — cada conferência nasceu de um defeito real:

  pontual_virou_aula     pergunta pontual ("o que é X?") abriu a leitura
  aula_nao_abriu         pedido de explicação, com material da matéria, não abriu a leitura
  leitura_trocou         "continua" leu OUTRO material sem o aluno trocar de matéria
  leu_capa               a leitura caiu em capa/apresentação (seção `outro` do índice)
  materia_trocou_sozinha a matéria em foco mudou sem o aluno citar matéria
  mistura_de_materias    trechos de outra matéria no prompt, com matéria em foco
  cartao_sem_pedido      cartões numa fala que pede resolução ou explicação
  cartao_de_outra_materia cartões de outra matéria que a da conversa

Não grava nada. Saída em `.logs/decisoes.md` (ausência = nada achado) e um
resumo no terminal. Não substitui ler as respostas do modelo: é a camada de
DECISÃO, que é onde estava a maioria dos defeitos medidos.
"""
import argparse
import collections
import re
import sys
from pathlib import Path

from core import assunto, conversa, db, geracao, leitura, mesa, pedido, prova, retrieval, socratic

VERSAO = "bateria-decisoes-v2"
SAIDA = Path(__file__).resolve().parents[2] / ".logs" / "decisoes.md"


def _historico(msgs: list[dict], k: int) -> list[dict]:
    return [{"autor": m["autor"], "texto": m["texto"]} for m in msgs[max(0, k - conversa.JANELA):k]
            if m["autor"] in ("aluno", "tutor", "evento")]


def _ultima_leitura(msgs: list[dict], k: int) -> dict | None:
    respostas = [m for m in msgs[:k] if m["autor"] == "tutor"][::-1][:20]
    for i, r in enumerate(respostas):
        lidas = [f for f in (r["fontes"] or []) if f.get("sequencial") and f.get("ordem") is not None]
        if lidas:
            return {"documento_id": lidas[-1]["documento_id"], "ordem": max(f["ordem"] for f in lidas),
                    "ids": [f["id"] for f in lidas], "foi_a_ultima": i == 0}
    return None


def _material_recente(msgs: list[dict], k: int) -> int | None:
    for r in [m for m in msgs[:k] if m["autor"] == "tutor"][::-1][:6]:
        materiais = [f for f in (r["fontes"] or []) if f.get("material") and f.get("documento_id")]
        citados = [f for f in materiais if f.get("citada")]
        if citados or materiais:
            return (citados or materiais)[0]["documento_id"]
    return None


def _materias_do_trecho(chunks: list[dict]) -> dict[int, set[str]]:
    """Matéria de cada trecho: a das questões (simulado) ou a do documento."""
    de_prova = prova.materias_dos_trechos([c["id"] for c in chunks if c.get("tipo") == "simulado"])
    return {c["id"]: de_prova.get(c["id"]) or ({c["disciplina"]} if c.get("disciplina") else set())
            for c in chunks}


def _da_materia(nomes: set[str], foco: str, mapa: dict) -> bool:
    alvo = {assunto._sem_acento(x).lower() for x in [foco, *mapa.get(foco, [])]}
    return any(assunto._sem_acento(n).lower() in alvo for n in nomes)


def turno(uid, mesa_id, ctx, msgs, k):
    fala = msgs[k]["texto"]
    hist = _historico(msgs, k)
    disciplinas, mapa = ctx["disciplinas"], ctx["mapa"]
    ultima = _ultima_leitura(msgs, k)
    marcadores = conversa.marcadores_de_leitura(uid)
    # A mesma ordem de `socratic.explicar`.
    if not assunto.cita_dispositivo(fala) and pedido.dispensa_busca(fala):
        consulta = None
    else:
        consulta = fala if assunto.cita_dispositivo(fala) else assunto.em_foco(hist, fala, disciplinas)
    foco = assunto.disciplina_em_foco(fala, hist, disciplinas)
    foco_da_conversa = foco
    if (ultima and ultima.get("foi_a_ultima") and not assunto.disciplina_citada(fala, disciplinas)
            and leitura.intencao(fala, True, True) in ("continua", "aprofunda")):
        foco = None
    tem_material = bool(foco and leitura.primeiro_material_da_disciplina(foco, mapa, uid))
    plano = (None if foco and not tem_material else
             leitura.planejar(fala, consulta or assunto.em_foco(hist, fala, disciplinas), ultima, uid, mesa_id,
                              historico=hist, material_recente=_material_recente(msgs, k),
                              disciplinas=disciplinas, mapa=mapa, foco=foco, marcadores=marcadores,
                              mesa_edital=mesa_id))
    if plano:
        chunks = plano["trechos"]
    else:
        chunks = (socratic._sem_prova_de_outra_materia(
            retrieval.buscar(consulta, n=6, usuario_id=uid, mesa_id=mesa_id, fala=fala),
            [foco_da_conversa, *mapa.get(foco_da_conversa, [])] if foco_da_conversa else None)
            if consulta else [])
    # Cartões: a mesma decisão da rota (sem gerar nada).
    ultima_do_tutor = next((m["texto"] for m in reversed(msgs[:k]) if m["autor"] == "tutor"), None)
    p = (pedido.treino(fala, apos_treino=pedido.veio_de_treino(hist))
         or pedido.aceitou_oferta_de_questoes(fala, ultima_do_tutor))
    cartoes = None
    if p and not p["formal"]:
        # O MESMO caminho da rota (api.py, bloco do treino): disciplina pedida, pedido
        # vago, explicação COM fonte como assunto, matéria em foco e da conversa.
        tema = assunto.em_foco(hist, pergunta=fala, disciplinas=disciplinas)
        pedida = assunto.disciplina_citada(fala, disciplinas)
        vago = not (pedida or assunto.pedido_de_treino_nomeia_assunto(fala, disciplinas))
        nomeado = (pedido.assunto_eliptico(fala)
                   or (pedido.assunto_da_oferta(ultima_do_tutor)
                       if not pedido.treino(fala, apos_treino=pedido.veio_de_treino(hist)) else None))
        if nomeado:
            tema, vago = nomeado, False
        ultima_msg = next((m for m in reversed(msgs[:k]) if m["autor"] == "tutor"), None)
        com_fonte = bool(ultima_msg and ultima_msg.get("fontes"))
        if vago and ultima_do_tutor and com_fonte and geracao.termos_raros(ultima_do_tutor, uid):
            tema = ultima_do_tutor
        dc = assunto.disciplina_da_conversa(hist, disciplinas, fala)
        try:
            da_prova = prova.da_conversa(uid, fala if not vago else (tema or fala), p["quantidade"],
                                         disciplinas=[pedida] if pedida else None)
            if len(da_prova) >= p["quantidade"]:
                ids = []
            else:
                ids, _ = geracao.escolher(
                    [pedida, *mapa.get(pedida, [])] if pedida else m_recorte(ctx), tema,
                    p["quantidade"] - len(da_prova), uid,
                    trechos=conversa_citados(msgs, k) if vago else None,
                    materias_da_conversa=([dc, *mapa.get(dc, [])] if dc
                                          else geracao.disciplinas_dos_trechos(conversa_citados(msgs, k))),
                    assunto_nomeado=bool(tema),
                    # na escolha das questões vale também a matéria do material da conversa (como a rota)
                    materia_em_foco=([fc, *mapa.get(fc, [])] if (fc := assunto.disciplina_em_foco(
                        fala, hist, disciplinas, do_material=socratic._disciplina_do_material(
                            _material_recente(msgs, k), disciplinas, mapa))) else None),
                    materia_da_conversa=([dc, *mapa.get(dc, [])] if dc else None))
            cartoes = {"prova": da_prova, "trechos": ids, "quantidade": p["quantidade"]}
        except geracao.SemMaterial:
            cartoes = {"prova": da_prova if "da_prova" in locals() else [], "trechos": [],
                       "quantidade": p["quantidade"]}
    foco_cartoes = (assunto.disciplina_em_foco(fala, hist, disciplinas, do_material=socratic._disciplina_do_material(
        _material_recente(msgs, k), disciplinas, mapa)) if cartoes is not None else None)
    return {"fala": fala, "foco": foco_da_conversa, "foco_cartoes": foco_cartoes, "plano": plano, "chunks": chunks, "ultima": ultima,
            "cartoes": cartoes, "resolucao": pedido.resolucao(fala), "tem_material": tem_material}


def conversa_citados(msgs: list[dict], k: int, respostas: int = 3) -> list[int]:
    """`conversa.trechos_citados_recentes`, sobre a lista em memória."""
    for r in [m for m in msgs[:k] if m["autor"] == "tutor"][::-1][:respostas]:
        citados = [f["id"] for f in (r.get("fontes") or []) if f.get("citada") and f.get("id")]
        if citados:
            return citados
    return []


def m_recorte(ctx):
    return ctx.get("recorte") or ctx.get("disciplinas")


def conferir(t, anterior, ctx):
    fala, achados = t["fala"], []
    mapa = ctx["mapa"]
    plano = t["plano"]
    if plano and plano["intencao"] == "inicio" and leitura.RE_PONTUAL.search(fala) \
            and not leitura.RE_INICIO.search(fala):
        achados.append(("pontual_virou_aula", ""))
    if (leitura.RE_EXPLICACAO.search(fala) and not leitura.RE_PONTUAL.search(fala) and not plano
            and t["tem_material"]):
        achados.append(("aula_nao_abriu", f"foco {t['foco']}"))
    if plano and plano["intencao"] == "continua" and t["ultima"] and plano["trechos"] \
            and plano["trechos"][0]["documento_id"] != t["ultima"]["documento_id"] \
            and not assunto.disciplina_citada(fala, ctx["disciplinas"]):
        achados.append(("leitura_trocou", ""))
    if plano and plano["trechos"]:
        fora = leitura._paginas_fora_da_aula(plano["trechos"][0]["documento_id"])
        if any(c.get("pagina") and any(a <= c["pagina"] <= b for a, b in fora) for c in plano["trechos"]):
            achados.append(("leu_capa", f"p. {[c.get('pagina') for c in plano['trechos']]}"))
    # Troca legítima: o aluno citou a matéria (mesmo com erro de digitação ou pela
    # metade) ou aceitou a que o tutor propôs ("sim", "pode ser").
    if anterior and anterior["foco"] and t["foco"] and t["foco"] != anterior["foco"] \
            and not assunto._disciplina_aproximada(fala, ctx["disciplinas"]) \
            and not assunto.RE_ACEITE.match(fala):
        achados.append(("materia_trocou_sozinha", f"{anterior['foco']} → {t['foco']}"))
    if t["foco"] and t["chunks"] and not plano:
        mat = _materias_do_trecho(t["chunks"])
        outros = [c for c in t["chunks"] if mat.get(c["id"]) and not _da_materia(mat[c["id"]], t["foco"], mapa)
                  and c.get("tipo") != "lei"]
        if len(outros) >= 2:
            achados.append(("mistura_de_materias",
                            f"foco {t['foco']}: " + "; ".join(sorted({", ".join(mat[c['id']]) for c in outros}))))
    if t["cartoes"] is not None and (t["resolucao"] or leitura.RE_EXPLICACAO.search(fala)):
        achados.append(("cartao_sem_pedido", ""))
    if t["cartoes"] and t["foco"]:
        ids = t["cartoes"]["trechos"]
        cs = db.query("""SELECT c.id, d.disciplina, d.tipo FROM chunk c JOIN documento d ON d.id = c.documento_id
                          WHERE c.id = ANY(%(i)s)""", {"i": ids}) if ids else []
        mat = _materias_do_trecho(cs)
        if any(mat.get(c["id"]) and not _da_materia(mat[c["id"]], t["foco"], mapa) for c in cs):
            achados.append(("cartao_de_outra_materia", f"foco {t['foco']}"))
        qs = db.query("SELECT disciplina FROM questao WHERE id = ANY(%(i)s)", {"i": t["cartoes"]["prova"]}) \
            if t["cartoes"]["prova"] else []
        if any(not _da_materia({q["disciplina"]}, t["foco"], mapa) for q in qs):
            achados.append(("cartao_de_outra_materia", f"prova, foco {t['foco']}"))
    return achados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    a = ap.parse_args()
    u = (db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": a.email}) if a.email else
         db.exec1("SELECT id FROM usuario WHERE email NOT LIKE '%%@local' ORDER BY id LIMIT 1"))
    if not u:
        print("conta não encontrada")
        return 1
    uid = u["id"]
    contagem, exemplos, total = collections.Counter(), collections.defaultdict(list), 0
    for cv in db.query("SELECT id, mesa_id FROM conversa WHERE usuario_id = %(u)s ORDER BY id", {"u": uid}):
        ctx = mesa.contexto(uid, cv["mesa_id"]) if cv["mesa_id"] else {"disciplinas": [], "mapa": {}}
        msgs = db.query("SELECT id, autor, texto, fontes FROM mensagem WHERE conversa_id = %(c)s ORDER BY id",
                        {"c": cv["id"]})
        anterior = None
        for k, m in enumerate(msgs):
            if m["autor"] != "aluno":
                continue
            try:
                t = turno(uid, cv["mesa_id"], ctx, msgs, k)
            except Exception as e:  # noqa: BLE001 — uma fala ruim não para a bateria
                contagem["erro_de_execucao"] += 1
                exemplos["erro_de_execucao"].append(f"conversa {cv['id']}: {m['texto'][:80]!r} — {e}")
                continue
            total += 1
            for nome, detalhe in conferir(t, anterior, ctx):
                contagem[nome] += 1
                exemplos[nome].append(f"conversa {cv['id']} · {t['fala'][:110]!r} {detalhe}".rstrip())
            anterior = t
    print(f"falas: {total}")
    for nome, n in contagem.most_common():
        print(f"  {nome}: {n}")
    if contagem:
        linhas = [f"# Bateria de decisões ({VERSAO})", "", f"{total} falas reais, sem modelo.", ""]
        for nome, n in contagem.most_common():
            linhas += [f"## {nome} ({n})", ""] + [f"- {x}" for x in exemplos[nome][:40]] + [""]
        SAIDA.parent.mkdir(exist_ok=True)
        SAIDA.write_text("\n".join(linhas), encoding="utf-8")
        print(f"→ {SAIDA}")
    elif SAIDA.exists():
        SAIDA.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
