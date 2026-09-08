#!/usr/bin/env python3
"""
Semeia uma CONTA DESCARTÁVEL com 3 mesas e 15 dias de estudo simulado, pra
conferir se os números do cartão de mesa (e do painel) ficam coerentes com
uso real — não só nas pontas 0% e 100% que o pytest trava.

NÃO toca na conta real: o padrão é `demo-15dias@local`, e `--limpar` apaga
(ON DELETE CASCADE da migração 009 leva tentativa/progresso/erro_caderno e
a cadeia mesa→edital→tópico). `--email` aponta pra outra conta de teste
quando o objetivo é OLHAR o resultado na tela, com um login que já existe.

Semear numa conta existente ACRESCENTA — não apaga o que já está lá. Uma
conta de teste normalmente tem edital ingerido e rascunhos de curadoria, e
destruir isso pra montar uma demonstração seria trocar dado real por dado
inventado sem ninguém pedir. Nome de mesa repetido faz `mesa.criar` levantar
erro, então rodar duas vezes falha alto em vez de duplicar calado.

A regra de promoção é a de PRODUÇÃO (core/scheduler_regras), e a escolha do
dia é a mesma de duas etapas da fila (revisão vencida primeiro, novas com o
orçamento que sobra). O que este script NÃO reaproveita é `scheduler.fila`,
porque ela pergunta CURRENT_DATE ao Postgres — pra simular dias passados o
relógio precisa ser uma variável, então a seleção roda aqui com `dia` e só
o resultado é gravado, com `criada_em` retroagido.

    python semear_demo.py                              # cria e semeia
    python semear_demo.py --email voce@teste --senha 12345678
    python semear_demo.py --limpar                     # apaga a conta padrão
"""
import argparse
import random
from datetime import date, timedelta


from core import auth, db, mesa as mesa_mod, scheduler, scheduler_regras as R

EMAIL = "demo-15dias@local"
SENHA = "demo-15-dias-2026"
DIAS = 15
TETO = 20          # mesmo teto diário de scheduler.TETO_DIARIO
NOVAS = 8

# (nome, órgão, banca, [(disciplina, nº de tópicos no edital)])
# Português/RLM/Bancários existem no edital e NÃO no acervo — é o caso real
# de quem sobe um edital de TI ou bancária num acervo só de Direito, e é
# justamente onde o cartão precisa continuar dizendo a verdade.
MESAS = [
    ("Polícia Federal 2026 — Agente", "Polícia Federal", "Cebraspe", [
        ("Direito Constitucional", 40), ("Direito Penal", 30),
        ("Direito Administrativo", 25), ("Língua Portuguesa", 18),
        ("Informática", 15)]),
    ("Analista Judiciário — TRF", "TRF 4ª Região", "Cebraspe", [
        ("Direito Constitucional", 35), ("Língua Portuguesa", 22),
        ("Raciocínio Lógico", 16)]),
    ("Banco do Brasil — Escriturário", "Banco do Brasil", "FGV", [
        ("Conhecimentos Bancários", 24), ("Língua Portuguesa", 20),
        ("Matemática Financeira", 18)]),
]

# Qual mesa foi estudada em cada um dos 15 dias. None = não estudou (a
# ofensiva quebrada é parte do que se quer ver na tela).
AGENDA = [0, 0, 1, None, 0, 0, 1, 0, None, 1, 0, 0, 1, None, 0]


def limpar(email: str):
    n = db.query("DELETE FROM usuario WHERE email = %(e)s RETURNING id", {"e": email})
    print(f"apagado: {len(n)} usuário(s) ({email})")


def _conta(email: str, senha: str) -> int:
    """
    Cria a conta, ou reaproveita a que já existe garantindo a senha pedida —
    o ponto de semear numa conta nomeada é conseguir ENTRAR nela pela tela, e
    uma senha que não é a informada transformaria isso em suporte.
    """
    existente = db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": email})
    if not existente:
        return auth.registrar(email, senha)["id"]
    db.query("UPDATE usuario SET senha_hash = %(h)s WHERE id = %(i)s",
             {"h": auth.hash_senha(senha), "i": existente["id"]})
    print(f"conta {email} já existia (id {existente['id']}) — semeando por cima, "
          f"senha redefinida; nada do que estava lá foi apagado")
    return existente["id"]


def semear(email: str, senha: str, semente: int):
    uid = _conta(email, senha)
    print(f"conta {email} (id {uid}) — senha {senha}\n")

    hoje = date.today()
    ids = []
    for nome, orgao, banca, discs in MESAS:
        m = mesa_mod.criar(uid, nome, orgao, banca)
        eid = db.exec1(
            """INSERT INTO edital (mesa_id, titulo, data_prova, arquivo)
               VALUES (%(m)s, %(t)s, %(d)s, 'demo.pdf') RETURNING id""",
            {"m": m["id"], "t": f"Edital {nome}", "d": hoje + timedelta(days=90)},
        )["id"]
        for disciplina, n in discs:
            db.query(
                """INSERT INTO topico (edital_id, disciplina, ordem, texto)
                   SELECT %(e)s, %(d)s, g, %(d)s || ' — tópico ' || g
                     FROM generate_series(1, %(n)s) g""",
                {"e": eid, "d": disciplina, "n": n},
            )
        ids.append(m["id"])

    # Pool de questões por mesa: o mesmo recorte que a fila usaria.
    pools = {}
    for mid in ids:
        disc = mesa_mod.disciplinas(mid)
        linhas = db.query(
            # `usuario_id IS NULL`: a conta de demonstração é semeada com o acervo
            # PÚBLICO. Sem isso ela pegaria questão gerada da apostila de outro
            # aluno (026) e a tela de demo mostraria material privado alheio.
            f"""SELECT id FROM questao q
                 WHERE {mesa_mod.filtro('q.disciplina')} AND q.usuario_id IS NULL
                 ORDER BY id""",
            {"disc": disc},
        )
        pools[mid] = [l["id"] for l in linhas]

    rnd = random.Random(semente)
    estado = {}   # questao_id -> [caixa, dia_da_proxima, vezes]

    for dia, alvo in enumerate(AGENDA):
        if alvo is None:
            continue
        mid = ids[alvo]
        pool = pools[mid]
        if not pool:
            continue
        vencidas = [q for q in pool if q in estado and estado[q][1] <= dia]
        novas = [q for q in pool if q not in estado]
        escolhidas = sorted(vencidas, key=lambda q: estado[q][1])[:TETO]
        escolhidas += novas[:max(0, min(TETO - len(escolhidas), NOVAS))]

        quando = hoje - timedelta(days=DIAS - 1 - dia)
        for q in escolhidas:
            caixa, _, vezes = estado.get(q, [0, dia, 0])
            # Mesma curva de aprendizado de simular.py: aluno que nunca
            # aprende faz qualquer regra de promoção parecer ruim.
            pc = min(0.92, 0.55 + 0.16 * vezes)
            r = rnd.random()
            if r < pc:
                veredito, dicas = "correta", (0 if rnd.random() < 0.6 else rnd.randint(1, 2))
            elif r < pc + 0.14:
                veredito, dicas = "parcial", rnd.randint(0, 2)
            else:
                veredito, dicas = "incorreta", 3
            nova_caixa = R.proxima_caixa(caixa, veredito, dicas)
            estado[q] = [nova_caixa, dia + R.dias_ate_revisao(nova_caixa), vezes + 1]

            antes = db.exec1("SELECT COALESCE(max(id), 0) AS m FROM tentativa")["m"]
            scheduler.registrar(uid, q, veredito, "resposta simulada", dicas,
                                segundos=rnd.randint(35, 190))
            # `registrar` carimba now()/today; retroagir é o que faz "15 dias"
            # existir. prox_revisao vem da caixa nova contada a partir do dia
            # simulado, não de hoje.
            db.query(
                "UPDATE tentativa SET criada_em = %(w)s WHERE id > %(a)s AND usuario_id = %(u)s",
                {"w": f"{quando} 20:{rnd.randint(10, 59)}:00", "a": antes, "u": uid},
            )
            db.query(
                """UPDATE progresso SET prox_revisao = %(p)s
                    WHERE usuario_id = %(u)s AND questao_id = %(q)s""",
                {"p": quando + timedelta(days=R.dias_ate_revisao(nova_caixa)),
                 "u": uid, "q": q},
            )
        print(f"dia {dia + 1:>2} ({quando})  mesa {alvo + 1}  "
              f"{len(escolhidas):>2} questões ({len(vencidas)} revisão, "
              f"{len(escolhidas) - min(len(vencidas), TETO)} novas)")

    print()
    relatorio(uid)


def relatorio(uid: int):
    print("=" * 78)
    print("CARTÃO DE MESA — o que /mesas devolve")
    print("=" * 78)
    for m in mesa_mod.listar(uid):
        marca = f"{m['topicos_cobertos']} / {m['topicos']} tópicos" if m["topicos"] else \
                f"{m['dominadas']} / {m['questoes']} questões"
        pct = m["cobertura_topicos_pct"] if m["topicos"] else m["cobertura_pct"]
        print(f"\n  {(m['banca'] or '—').upper()}")
        print(f"  {m['nome']}")
        print(f"  {marca:<26} {round(pct):>3}%   [{'█' * round(pct / 4):<25}]")
        print(f"  último estudo: {m['ultimo_estudo']}")
        print(f"  (por questão: {m['dominadas']}/{m['questoes']} = {m['cobertura_pct']}% · "
              f"{len(m['disciplinas'] or [])} disciplinas)")

    print("\n" + "=" * 78)
    print("CAIXAS — onde o acervo parou depois de 15 dias")
    print("=" * 78)
    for linha in db.query(
        """SELECT q.disciplina, p.caixa, count(*) AS n
             FROM progresso p JOIN questao q ON q.id = p.questao_id
            WHERE p.usuario_id = %(u)s GROUP BY 1, 2 ORDER BY 1, 2""",
        {"u": uid},
    ):
        print(f"  {linha['disciplina']:<26} caixa {linha['caixa']}  {linha['n']:>3}")
    t = db.exec1("SELECT count(*) AS n FROM tentativa WHERE usuario_id = %(u)s", {"u": uid})
    print(f"  total de tentativas: {t['n']}")

    print("\n" + "=" * 78)
    print("PAINEL — desempenho e meta, por mesa (os mesmos números do /stats)")
    print("=" * 78)
    for m in mesa_mod.listar(uid):
        disc = m["disciplinas"]
        d = scheduler.desempenho(uid, disciplinas=disc)
        print(f"\n  {m['nome']}")
        print(f"    {d}")
        print(f"    meta: {scheduler.meta(uid, mesa_id=m['id'], disciplinas=disc)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default=EMAIL)
    ap.add_argument("--senha", default=SENHA)
    ap.add_argument("--limpar", action="store_true")
    ap.add_argument("--semente", type=int, default=7)
    a = ap.parse_args()
    limpar(a.email) if a.limpar else semear(a.email, a.senha, a.semente)
