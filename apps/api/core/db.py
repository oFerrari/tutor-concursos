"""Conexão única com o Postgres, com o adaptador do pgvector registrado."""
import os
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import DATABASE_URL

VERSAO = "db-v2"

_conn: psycopg.Connection | None = None


def fuso_local() -> str | None:
    """O fuso IANA do processo: `TZ`, senão o link de /etc/localtime. PURO de banco.

    O BANCO TEM DE CONTAR O DIA COMO O PYTHON CONTA. O Postgres do compose roda em
    UTC e `date.today()` é local: das 20h à meia-noite (UTC−4) `CURRENT_DATE` já
    era amanhã. Medido na bateria de estudo de 02/10/2026: a questão errada às
    20h45, marcada para amanhã, voltava à fila do dia na mesma noite, e o estudo
    da noite contava no dia seguinte (`criada_em::date`).
    """
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz and "/" in tz:
        return tz
    try:
        alvo = str(Path("/etc/localtime").resolve())
        return alvo.split("zoneinfo/", 1)[1] if "zoneinfo/" in alvo else None
    except OSError:
        return None


def _conectar() -> psycopg.Connection:
    fuso = fuso_local()
    c = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row,
                        **({"options": f"-c TimeZone={fuso}"} if fuso else {}))
    register_vector(c)
    return c


def conn() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = _conectar()
    return _conn


def query(sql: str, params: dict | tuple | None = None) -> list[dict]:
    with conn().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def exec1(sql: str, params: dict | tuple | None = None) -> dict | None:
    r = query(sql, params)
    return r[0] if r else None


def conexao_isolada() -> psycopg.Connection:
    """Conexão NOVA, independente da global — para trabalho longo em thread.

    `conn()` devolve UMA conexão de módulo, e ela é o certo pro caminho
    normal: um request curto por vez. Ingestão de material é o oposto disso —
    o embedding roda local na CPU (ver "Pilha"), um PDF de 800 trechos leva
    MINUTOS, e o loop grava lote a lote. Usar a conexão global aí a segura
    durante todo esse tempo: qualquer outro request do app espera na fila
    atrás de uma indexação.

    Quem abre é responsável por fechar (`with`). `register_vector` também
    aqui, senão o INSERT do embedding falha nesta conexão mesmo funcionando
    na outra — o adaptador é registrado por CONEXÃO, não por processo.
    """
    return _conectar()
