"""
Acesso direto ao banco de questões — compartilhado entre usuários, sem
usuario_id (a questão em si não pertence a ninguém; progresso é que é
pessoal, e mora em `progresso`/`tentativa`).

Extraído como módulo próprio porque `api.py` precisa buscar uma questão
por id fora do contexto de fila/simulado/desafio (rota de diálogo turno a
turno), e nenhum módulo existente já tinha essa consulta simples pronta.
"""
from . import db

VERSAO = "questoes-v1"

CAMPOS = "id, disciplina, tema, enunciado, gabarito, dicas"


def obter(questao_id: int) -> dict | None:
    return db.exec1(f"SELECT {CAMPOS} FROM questao WHERE id = %(id)s", {"id": questao_id})


def obter_varias(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.query(f"SELECT {CAMPOS} FROM questao WHERE id = ANY(%(ids)s)", {"ids": ids})
    return {r["id"]: r for r in rows}
