"""Bateria de conversas com o modelo REAL sobre o material de uma conta, SEM gravar nada.

Complementa o `./testar.sh` (aluno sintético, conta descartável, sem material
próprio): aqui a conversa roda sobre a biblioteca e o edital de uma conta de
verdade — que é onde leitura em sequência e "sem material" acontecem. Nada é
gravado: nem conversa, nem mensagem, nem diário (o marcador de leitura é
mantido em memória). Gasta uma chamada ao modelo por turno.

    python bateria_conversa.py cenarios/leitura_e_sem_material.json --email voce@x

Criada em 24/09/2026, a partir das conversas reais em que a leitura não
disparava e o tutor ensinava de memória matéria sem material.

Cada turno: (fala, expectativa). Expectativas:
  "sem"            sem material: nenhum trecho, e a resposta diz que não há material
  "ler:<disc>"     turno de leitura de material dessa disciplina
  "busca"          turno comum (não é leitura)
  None             só observa
"""
import argparse, json, re, sys, time
from core import auth, db, diario, mesa, socratic

VERSAO = "bateria-conversa-v1"

ap = argparse.ArgumentParser()
ap.add_argument("cenarios")
ap.add_argument("--email", required=True, help="conta cujo material e edital a conversa usa")
ap.add_argument("--mesa", type=int, help="id da mesa (padrão: a mais recente da conta)")
ARGS = ap.parse_args()
_u = db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": ARGS.email})
if not _u:
    sys.exit(f"conta {ARGS.email} não existe")
UID = _u["id"]
_mesa = ARGS.mesa or db.exec1("SELECT id FROM mesa WHERE usuario_id = %(u)s ORDER BY id DESC LIMIT 1",
                              {"u": UID})["id"]
diario.anotar = lambda *a, **k: None   # nada vai ao diário da conta
M = mesa.contexto(UID, _mesa)

def rodar(nome, turnos):
    hist, fontes_tutor, falhas = [], [], 0
    def ultima():
        for i, fs in enumerate(reversed(fontes_tutor)):
            lidas = [f for f in fs if f.get("sequencial") and f.get("ordem") is not None]
            if lidas:
                return {"documento_id": lidas[-1]["documento_id"], "ordem": max(f["ordem"] for f in lidas),
                        "ids": [f["id"] for f in lidas], "foi_a_ultima": i == 0}
    def marcadores():
        mk = {}
        for n, fs in enumerate(fontes_tutor):
            lidas = [f for f in fs if f.get("sequencial") and f.get("ordem") is not None]
            if lidas:
                mk[lidas[-1]["documento_id"]] = {"ordem": max(f["ordem"] for f in lidas), "quando": n}
        return mk
    def recente():
        for fs in reversed(fontes_tutor[-6:]):
            mats = [f for f in fs if f.get("dono") is not None and f.get("tipo") in ("aula", "resumo")]
            cit = [f for f in mats if f.get("citada")]
            if cit or mats:
                return (cit or mats)[0]["documento_id"]
    print(f"\n################ {nome}")
    for fala, espera in turnos:
        t = time.time()
        try:
            r = socratic.explicar(fala, UID, M["disciplinas"], M, hist[-16:], auth.perfil(UID),
                                  leitura_atual=ultima(), material_recente=recente(),
                                  marcadores=marcadores())
        except Exception as e:
            print(f"  ✗ {fala!r}: EXCEÇÃO {e}"); falhas += 1; continue
        fontes_tutor.append(r["fontes"])
        hist += [{"autor": "aluno", "texto": fala}, {"autor": "tutor", "texto": r["resposta"]}]
        seq = [f for f in r["fontes"] if f.get("sequencial")]
        cit = [f for f in r["fontes"] if f.get("citada")]
        tipo = (f"LEITURA {seq[0].get('disciplina')}/{seq[0].get('assunto')} ordens {[f['ordem'] for f in seq]}"
                if seq else f"busca {len(r['fontes'])} trechos, {len(cit)} citados")
        ok = True
        if espera == "sem":
            ok = not r["fontes"] and bool(re.search(r"(?i)n[aã]o (h[aá]|tem|temos|est[aá]|traz\w*|tenho)|ainda n[aã]o|sem material|vazi[oa]", r["resposta"]))
        elif espera and espera.startswith("ler:"):
            ok = bool(seq) and espera[4:].lower() in (seq[0].get("disciplina") or "").lower()
        elif espera == "busca":
            ok = not seq
        falhas += not ok
        marca = "  " if espera is None else ("✓ " if ok else "✗ ")
        print(f"{marca}[{time.time()-t:4.1f}s {len(r['resposta'].split()):4}p] {fala!r}\n      → {tipo}\n      » {re.sub(r'\\s+', ' ', r['resposta'])[:260]}")
    print(f"  == {nome}: {falhas} falha(s)")
    return falhas

CENARIOS = json.load(open(ARGS.cenarios))
total = sum(rodar(c["nome"], [tuple(t) for t in c["turnos"]]) for c in CENARIOS)
print(f"\nTOTAL DE FALHAS: {total}")
