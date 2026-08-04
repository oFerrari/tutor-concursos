"""
Revisão espaçada e caderno de erros.

Este módulo é o coração do produto — não o RAG. O que faz um tutor
funcionar é decidir *o que* perguntar hoje, e isso é SQL, não LLM.

Regra de promoção: acerto sem dica sobe de caixa; acerto com dica mantém
(você lembrou, mas com andaime); erro volta para a caixa 0. Manter em vez
de subir no acerto assistido é o que evita o falso domínio, que é o modo
de falha mais comum de Anki mal usado.
"""
from datetime import date, timedelta

from . import db
from .scheduler_regras import (INTERVALOS, conta_como_erro, dias_ate_revisao,
                               proxima_caixa)

VERSAO = "scheduler-v18"

# TETO_DIARIO: quantas questões por dia. NOVAS_POR_DIA=None significa "todo o
# orçamento que sobrar depois das revisões" — cota fixa perdeu em todos os
# tetos testados, porque freia a exposição sem necessidade nos dias leves.
#
# Simulação com 428 questões, 90 dias, média de 15 sementes (dominadas):
#   teto 15:   ordem antiga   0  ·  revisão primeiro 133
#   teto 25:   ordem antiga  39  ·  revisão primeiro 220
#   teto 40:   ordem antiga 389  ·  revisão primeiro 353
#
# O ganho é enorme quando a capacidade não cobre a demanda — regime em que a
# fila vive assim que o acervo cresce. No teto 40 a ordem antiga aparece na
# frente, mas ali o simulador NÃO é confiável: ele não modela esquecimento,
# então atrasar revisão sai de graça no modelo e caro na vida real. Revisão
# primeiro se sustenta pela teoria, não por esse número.
TETO_DIARIO = 40
NOVAS_POR_DIA = None


CAMPOS_Q = "id, disciplina, tema, enunciado, gabarito, dicas, caixa, prox_revisao"


def fila(teto: int = TETO_DIARIO, novas: int | None = NOVAS_POR_DIA) -> list[dict]:
    """
    Fila do dia em duas etapas, e a ordem entre elas é o que importa:

    1. REVISÕES — questões já tentadas cujo prazo venceu. Prioridade absoluta:
       revisão atrasada é conhecimento se perdendo agora.
    2. NOVAS — nunca tentadas, com cota própria, só no espaço que sobrar.

    Uma consulta única ordenada por caixa faz material novo (caixa 0) sufocar
    as revisões para sempre. Duas etapas com orçamentos separados resolvem.
    """
    revisoes = db.query(
        f"""SELECT {CAMPOS_Q} FROM questao q
            WHERE q.prox_revisao <= CURRENT_DATE
              AND EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = q.id)
            ORDER BY q.prox_revisao ASC, q.caixa ASC
            LIMIT %(l)s""",
        {"l": teto},
    )
    resto = max(teto - len(revisoes), 0)
    sobra = resto if novas is None else min(resto, novas)
    if sobra == 0:
        return revisoes
    inéditas = db.query(
        f"""SELECT {CAMPOS_Q} FROM questao q
            WHERE q.prox_revisao <= CURRENT_DATE
              AND NOT EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = q.id)
            ORDER BY q.id
            LIMIT %(l)s""",
        {"l": sobra},
    )
    return revisoes + inéditas


def carga_hoje() -> dict:
    """Quanto venceu vs quanto cabe no teto — para o usuário ver a dívida."""
    r = db.exec1(
        """SELECT count(*) FILTER (WHERE prox_revisao <= CURRENT_DATE
                AND EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = q.id)) AS revisoes,
                  count(*) FILTER (WHERE prox_revisao <= CURRENT_DATE
                AND NOT EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = q.id)) AS ineditas
           FROM questao q"""
    ) or {"revisoes": 0, "ineditas": 0}
    r["teto"] = TETO_DIARIO
    r["atraso"] = max(0, r["revisoes"] - TETO_DIARIO)
    return r


def registrar(questao_id: int, veredito: str, resposta: str,
              dicas_usadas: int, segundos: int | None = None) -> dict:
    q = db.exec1("SELECT caixa, disciplina, tema FROM questao WHERE id = %(id)s", {"id": questao_id})
    if not q:
        raise ValueError(f"questão {questao_id} não existe")

    caixa = proxima_caixa(q["caixa"], veredito, dicas_usadas)
    prox = date.today() + timedelta(days=dias_ate_revisao(caixa))

    db.query(
        """INSERT INTO tentativa (questao_id, resposta, veredito, dicas_usadas, segundos)
           VALUES (%(q)s, %(r)s, %(v)s, %(d)s, %(s)s)""",
        {"q": questao_id, "r": resposta, "v": veredito, "d": dicas_usadas, "s": segundos},
    )
    db.query(
        "UPDATE questao SET caixa = %(c)s, prox_revisao = %(p)s WHERE id = %(id)s",
        {"c": caixa, "p": prox, "id": questao_id},
    )
    if conta_como_erro(veredito):
        db.query(
            """INSERT INTO erro_caderno (questao_id, disciplina, tema)
               VALUES (%(id)s, %(d)s, %(t)s)
               ON CONFLICT (questao_id) DO UPDATE
                 SET vezes = erro_caderno.vezes + 1, ultima = CURRENT_DATE""",
            {"id": questao_id, "d": q["disciplina"], "t": q["tema"]},
        )
    return {"caixa": caixa, "prox_revisao": prox}


def caderno_erros(limite: int = 20) -> list[dict]:
    return db.query(
        """SELECT e.*, q.enunciado
           FROM erro_caderno e JOIN questao q ON q.id = e.questao_id
           ORDER BY e.vezes DESC, e.ultima DESC LIMIT %(l)s""",
        {"l": limite},
    )


def desempenho() -> list[dict]:
    return db.query("SELECT * FROM v_desempenho_disciplina ORDER BY pct_acerto NULLS LAST")


def meta(data_prova: date) -> dict:
    r = db.exec1(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE caixa >= 3) AS dominadas,
                  COUNT(*) FILTER (WHERE prox_revisao <= CURRENT_DATE) AS pendentes_hoje
           FROM questao"""
    ) or {"total": 0, "dominadas": 0, "pendentes_hoje": 0}
    dias = max((data_prova - date.today()).days, 0)
    pendente = r["total"] - r["dominadas"]
    return {
        "dias_restantes": dias,
        "cobertura_pct": round(100 * r["dominadas"] / r["total"], 1) if r["total"] else 0.0,
        "questoes_pendentes": pendente,
        "ritmo_necessario": -(-pendente // dias) if dias else None,
        "pendentes_hoje": r["pendentes_hoje"],
    }
