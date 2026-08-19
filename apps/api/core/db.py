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
    c = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
    register_vector(c)
    return c
