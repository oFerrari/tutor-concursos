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
from .config import INTERVALOS


def fila(limite: int = 20) -> list[dict]:
    """Pendentes de hoje, priorizando caixa baixa e atraso maior."""
    return db.query(
        """SELECT id, disciplina, tema, enunciado, gabarito, dicas, caixa, prox_revisao
           FROM questao
           WHERE prox_revisao <= CURRENT_DATE
           ORDER BY caixa ASC, prox_revisao ASC
           LIMIT %(l)s""",
        {"l": limite},
    )


def registrar(questao_id: int, veredito: str, resposta: str,
              dicas_usadas: int, segundos: int | None = None) -> dict:
    acertou = veredito == "correta"
    q = db.exec1("SELECT caixa, disciplina, tema FROM questao WHERE id = %(id)s", {"id": questao_id})
    if not q:
        raise ValueError(f"questão {questao_id} não existe")

    if acertou:
        caixa = min(q["caixa"] + 1, len(INTERVALOS) - 1) if dicas_usadas == 0 else q["caixa"]
    else:
        caixa = 0
    prox = date.today() + timedelta(days=INTERVALOS[caixa])

    db.query(
        """INSERT INTO tentativa (questao_id, resposta, veredito, dicas_usadas, segundos)
           VALUES (%(q)s, %(r)s, %(v)s, %(d)s, %(s)s)""",
        {"q": questao_id, "r": resposta, "v": veredito, "d": dicas_usadas, "s": segundos},
    )
    db.query(
        "UPDATE questao SET caixa = %(c)s, prox_revisao = %(p)s WHERE id = %(id)s",
        {"c": caixa, "p": prox, "id": questao_id},
    )
    if not acertou:
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
