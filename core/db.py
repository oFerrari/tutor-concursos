"""Conexão única com o Postgres, com o adaptador do pgvector registrado."""
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import DATABASE_URL

_conn: psycopg.Connection | None = None


def conn() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
        register_vector(_conn)
    return _conn


def query(sql: str, params: dict | tuple | None = None) -> list[dict]:
    with conn().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def exec1(sql: str, params: dict | tuple | None = None) -> dict | None:
    r = query(sql, params)
    return r[0] if r else None
