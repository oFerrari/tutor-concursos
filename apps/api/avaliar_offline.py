"""Regressões e históricos sem LLM: ./tutor avaliar_offline.py.

Padrão: 20 falas recentes, até 90 segundos. --rapido pula replay de retrieval.
Não treina o modelo: verifica decisões atuais e sinaliza respostas históricas.
Banco em transação READ ONLY. Rede Python e todos os provedores LLM bloqueados.
Saída 0 = verificações atuais passaram; 1 = falhas; 2 = execução incompleta.
"""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import time
from unittest.mock import patch

VERSAO = "avaliar-offline-v1"
AQUI = Path(__file__).resolve().parent
CASOS = AQUI / "cenarios/regressoes_offline.json"
SAIDA = AQUI.parents[1] / ".logs/avaliacao-offline"


class BloqueioOffline(RuntimeError):
    pass


class TempoEsgotado(BaseException):
    # Não pode ser engolido pelo fallback `except Exception` de um módulo.
    pass


@contextmanager
def offline():
    """Sem fallback pago ou downloads. Psycopg usa libpq, não socket Python.

    Não é sandbox para código arbitrário/subprocessos: vale para este runner
    e seus módulos em processo. Nenhum subprocesso é executado aqui.
    """
    from core import llm

    def negar(*a, **kw):
        raise BloqueioOffline("chamada de modelo/rede bloqueada no modo offline")

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1"}))
        stack.enter_context(patch.object(socket.socket, "connect", negar))
        stack.enter_context(patch.object(socket.socket, "connect_ex", negar))
        stack.enter_context(patch.object(llm, "obter", negar))
        for classe in (llm.LLM, llm.Gemini, llm.Ollama, llm._ComReserva):
            for metodo in ("gerar", "gerar_json", "gerar_em_fluxo"):
                stack.enter_context(patch.object(classe, metodo, negar))
        yield


def regras(casos):
    """Expectativa escrita por humano, não calculada pelo código avaliado."""
    from core import assunto, pedido
    resultados = []
    for c in casos:
        p = pedido.treino(c["fala"])
        obtido = p["quantidade"] if p and not p["formal"] else None
        erros = []
        if obtido != c["quantidade"]:
            erros.append(f"questões: esperado {c['quantidade']}, obtido {obtido}")
        if "foco" in c:
            foco = assunto.disciplina_em_foco(c["fala"], c["historico"], c["disciplinas"])
            if foco != c["foco"]:
                erros.append(f"foco: esperado {c['foco']}, obtido {foco}")
        resultados.append({"id": c["id"], "fala": c["fala"], "erros": erros})
    return resultados


def chave(achado):
    return f"{achado['camada']}:{achado['conversa']}:{achado['mensagem']}:{achado['regra']}"


def comparar(atual, anterior):
    def chaves(r):
        return ({chave(x) for x in r.get("achados", [])}
                | {f"regra:{c['id']}" for c in r.get("regras", []) if c["erros"]})
    novos, antigos = chaves(atual), chaves(anterior)
    return {"novos": len(novos-antigos), "recorrentes": len(novos & antigos),
            # Ausência pode significar janela/corpus diferentes, não correção.
            "nao_observados_neste_recorte": len(antigos-novos)}


def salvar(r, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    ultimo = pasta / "ultimo.json"
    try:
        anterior = json.loads(ultimo.read_text())
    except (OSError, ValueError):
        anterior = {}
    r["comparacao"] = comparar(r, anterior)
    corpo = json.dumps(r, ensure_ascii=False, indent=2)
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (pasta / f"{carimbo}.json").write_text(corpo, encoding="utf-8")
    temporario = pasta / ".ultimo.tmp"
    temporario.write_text(corpo, encoding="utf-8")
    temporario.replace(ultimo)
    falhas = [c for c in r["regras"] if c["erros"]]
    linhas = ["# Avaliação offline", "", f"Versão: {VERSAO} · {r['quando']}", "",
        f"Código de saída: {r['saida']}. LLM: bloqueado. Banco: somente leitura.",
        f"Regras: {len(r['regras'])-len(falhas)}/{len(r['regras'])} passaram. "
        f"Histórico: {r['turnos']} de {r['selecionados']} falas selecionadas "
        f"({r['total_disponivel']} disponíveis). Replay de decisões: {r['decisoes']}.",
        f"Duração: {r['segundos']} s. Novos: {r['comparacao']['novos']}; "
        f"recorrentes: {r['comparacao']['recorrentes']}.", "",
        "## Falhas atuais com expectativa independente", ""]
    for c in falhas:
        linhas += [f"- **{c['id']}**: {c['fala']!r} — {'; '.join(c['erros'])}"]
    if not falhas:
        linhas += ["Nenhuma nos casos executados."]
    for camada, titulo in (("decisao_atual", "Replay de decisões atuais (triagem)"),
                            ("historico", "Respostas antigas (não provam falha atual)")):
        linhas += ["", f"## {titulo}", ""]
        grupos = Counter(x["regra"] for x in r["achados"] if x["camada"] == camada)
        for regra, n in grupos.most_common():
            exemplos = [x for x in r["achados"] if x["camada"] == camada and x["regra"] == regra]
            linhas += [f"### {regra} ({n})", ""]
            for x in exemplos[:3]:
                linhas += [f"- Conversa {x['conversa']}, mensagem {x['mensagem']}: "
                           f"{x['fala']!r}. {x['detalhe']}"]
        if not grupos:
            linhas += ["Não executado no modo rápido." if camada == "decisao_atual"
                       and r["modo"] in ("rapido", "regras") else "Nenhum achado no recorte executado."]
    linhas += ["", "## Limites e execução", "",
        "- Histórico usa respostas gravadas; não valida um prompt novo.",
        "- Replay usa código, corpus e marcadores atuais com falas antigas; "
        "não reconstrói o banco do passado. Achados exigem conferência.",
        "- Ausente nesta janela não significa corrigido. JSON guarda os exemplos completos.",
        "- Sem julgamento semântico, navegador ou garantia de zero alucinação.",
        "- Próximos testes sugeridos: casos que falharam; não refazer bateria paga inteira."]
    linhas += [f"- Execução incompleta: {e}" for e in r["erros_execucao"]]
    (pasta / "ultimo.md").write_text("\n".join(linhas)+"\n", encoding="utf-8")


def historicos(r, usuario, limite, rapido, conversa_id=None):
    import bateria_decisoes as bateria
    from avaliar_chat import checar
    from core import db, mesa

    # Escolha explícita se houver mais de uma conta com histórico.
    usuarios = db.query("SELECT DISTINCT usuario_id AS id FROM conversa ORDER BY usuario_id")
    if usuario is None:
        if len(usuarios) != 1:
            raise ValueError("informe --usuario ID: nenhuma ou múltiplas contas com histórico")
        usuario = usuarios[0]["id"]
    r["usuario"] = usuario
    filtro = "c.usuario_id=%(u)s AND m.autor='aluno'"
    params = {"u": usuario, "n": limite, "c": conversa_id}
    if conversa_id is not None:
        filtro += " AND c.id=%(c)s"
    r["total_disponivel"] = db.exec1(
        f"SELECT count(*) AS n FROM mensagem m JOIN conversa c ON c.id=m.conversa_id WHERE {filtro}", params)["n"]
    selecionadas = db.query(
        f"SELECT m.id, c.id AS conversa, c.mesa_id FROM mensagem m "
        f"JOIN conversa c ON c.id=m.conversa_id WHERE {filtro} ORDER BY m.id DESC LIMIT %(n)s", params)
    r["selecionados"] = len(selecionadas)
    if not selecionadas:
        raise ValueError("nenhuma fala no recorte solicitado")
    conversas, anteriores = {}, {}
    for s in reversed(selecionadas):
        cid = s["conversa"]
        if cid not in conversas:
            msgs = db.query("SELECT id, autor, texto, fontes FROM mensagem "
                            "WHERE conversa_id=%(c)s ORDER BY id", {"c": cid})
            ctx = mesa.contexto(usuario, s["mesa_id"]) if s["mesa_id"] else {}
            conversas[cid] = (msgs, ctx)
        msgs, ctx = conversas[cid]
        k = next(i for i, m in enumerate(msgs) if m["id"] == s["id"])
        fala = msgs[k]["texto"]
        respostas = []
        for m in msgs[k+1:]:
            if m["autor"] == "aluno":
                break
            if m["autor"] == "tutor":
                respostas.append(m)
        for resposta in respostas:
            for nivel, detalhe in checar(fala, resposta["texto"], resposta["fontes"] or [],
                                        bateria._historico(msgs, k), questoes=None):
                r["achados"].append({"camada": "historico", "conversa": cid,
                    "mensagem": s["id"], "regra": detalhe, "gravidade": nivel,
                    "fala": fala, "detalhe": resposta["texto"][:650]})
        if not rapido:
            if not ctx:
                raise ValueError(f"conversa {cid} sem mesa disponível; use --rapido")
            t = bateria.turno(usuario, s["mesa_id"], ctx, msgs, k)
            for nome, detalhe in bateria.conferir(t, anteriores.get(cid), ctx):
                r["achados"].append({"camada": "decisao_atual", "conversa": cid,
                    "mensagem": s["id"], "regra": nome, "gravidade": "erro",
                    "fala": fala, "detalhe": detalhe})
            r["decisoes"] += 1
            anteriores[cid] = t
        r["turnos"] += 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--usuario", type=int)
    ap.add_argument("--conversa", type=int)
    ap.add_argument("--limite", type=int, default=20)
    ap.add_argument("--segundos", type=int, default=90)
    ap.add_argument("--rapido", action="store_true", help="só regras e respostas gravadas, sem embeddings")
    ap.add_argument("--so-regras", action="store_true", help="expectativas independentes, sem banco")
    ap.add_argument("--caso", action="append", help="ID do caso de regressão; pode repetir")
    ap.add_argument("--saida", type=Path, default=SAIDA)
    a = ap.parse_args(argv)
    if a.limite < 1 or a.segundos < 1:
        ap.error("limite e segundos precisam ser positivos")
    inicio = time.monotonic()
    r = {"versao": VERSAO, "quando": datetime.now(timezone.utc).isoformat(),
         "regras": [], "achados": [], "turnos": 0, "selecionados": 0,
         "total_disponivel": 0, "decisoes": 0, "erros_execucao": [],
         "modo": "regras" if a.so_regras else "rapido" if a.rapido else "decisoes", "limite": a.limite}
    r["codigo"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        for p in [Path(__file__), CASOS, AQUI / "bateria_decisoes.py",
                  *[AQUI / f"core/{n}.py" for n in ("pedido", "assunto", "socratic", "retrieval", "leitura")]]}
    def esgotou(*_):
        raise TempoEsgotado("limite de tempo; rode --rapido ou um recorte menor")
    handler = signal.signal(signal.SIGALRM, esgotou)
    signal.alarm(a.segundos)
    try:
        with offline():
            casos = json.loads(CASOS.read_text())
            if a.caso:
                desconhecidos = set(a.caso) - {c["id"] for c in casos}
                if desconhecidos:
                    raise ValueError(f"casos desconhecidos: {sorted(desconhecidos)}")
                casos = [c for c in casos if c["id"] in a.caso]
            r["regras"] = regras(casos)
            if not a.so_regras:
                from core import db
                with db.conn().transaction():
                    db.query("SET TRANSACTION READ ONLY")
                    db.query("SET LOCAL statement_timeout = '15s'")
                    historicos(r, a.usuario, a.limite, a.rapido, a.conversa)
    except (Exception, TempoEsgotado) as e:
        r["erros_execucao"].append(f"{type(e).__name__}: {e}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, handler)
    r["saida"] = (2 if r["erros_execucao"] else
        1 if any(c["erros"] for c in r["regras"]) or
        any(x["camada"] == "decisao_atual" for x in r["achados"]) else 0)
    r["segundos"] = round(time.monotonic()-inicio, 2)
    salvar(r, a.saida)
    print(f"Offline: {r['turnos']}/{r['selecionados']} falas, "
          f"{sum(bool(c['erros']) for c in r['regras'])} regras falharam, "
          f"{len(r['achados'])} achados, {r['segundos']} s. Saída {r['saida']}.")
    print(a.saida / "ultimo.md")
    return r["saida"]


if __name__ == "__main__":
    raise SystemExit(main())
