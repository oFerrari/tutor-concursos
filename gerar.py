#!/usr/bin/env python3
"""
Gera questões para um documento já ingerido.

    python gerar.py --listar
    python gerar.py 1 --qtd 3

Existe porque `ingest.py` recusa reingerir o mesmo arquivo (hash), então
quando a geração falha o material fica indexado sem questões. Isto conserta
sem reprocessar embeddings.
"""
import argparse
import json
import sys

from core import db, llm, socratic


def listar() -> None:
    linhas = db.query(
        """SELECT d.id, d.titulo, d.disciplina, d.tipo,
                  COUNT(DISTINCT c.id) AS chunks,
                  COUNT(DISTINCT q.id) AS questoes
           FROM documento d
           LEFT JOIN chunk c ON c.documento_id = d.id
           LEFT JOIN questao q ON q.documento_id = d.id
           GROUP BY d.id ORDER BY d.id"""
    )
    if not linhas:
        print("nenhum documento ingerido.")
        return
    print(f"{'id':>3}  {'título':<32} {'disciplina':<24} {'chunks':>6} {'questões':>8}")
    for r in linhas:
        print(f"{r['id']:>3}  {r['titulo'][:32]:<32} {r['disciplina'][:24]:<24} "
              f"{r['chunks']:>6} {r['questoes']:>8}")


def gerar(doc_id: int, qtd: int) -> int:
    doc = db.exec1("SELECT id, titulo, disciplina FROM documento WHERE id = %(i)s", {"i": doc_id})
    if not doc:
        print(f"documento {doc_id} não existe. Use --listar.", file=sys.stderr)
        return 1

    amostra = db.query(
        """SELECT c.id, c.texto, c.artigo, c.paragrafo, c.pagina,
                  d.titulo, d.disciplina, d.tipo
           FROM chunk c JOIN documento d ON d.id = c.documento_id
           WHERE c.documento_id = %(d)s
           ORDER BY length(c.texto) DESC LIMIT 12""",
        {"d": doc_id},
    )
    if not amostra:
        print(f"documento {doc_id} não tem chunks indexados.", file=sys.stderr)
        return 1

    print(f"gerando {qtd} questões de '{doc['titulo']}' ({len(amostra)} chunks de contexto)…")
    try:
        questoes = socratic.gerar_questoes(amostra, qtd)
    except llm.ErroLLM as e:
        print(f"falhou: {e}", file=sys.stderr)
        return 1

    if not questoes:
        print("o modelo não devolveu nenhuma questão válida.", file=sys.stderr)
        return 1

    for q in questoes:
        db.query(
            """INSERT INTO questao (documento_id, disciplina, tema, enunciado,
                                    gabarito, dicas, fonte_chunks)
               VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s)""",
            {"d": doc_id, "disc": doc["disciplina"], "t": q["tema"], "e": q["enunciado"],
             "g": q["gabarito"], "dic": json.dumps(q["dicas"]),
             "f": [c["id"] for c in amostra]},
        )
        print(f"  + [{q['tema']}] {len(q['dicas'])} dicas")
    print(f"{len(questoes)} questões salvas. Rode: python chat.py estudar")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc_id", nargs="?", type=int)
    ap.add_argument("--qtd", type=int, default=5)
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()

    if a.listar or a.doc_id is None:
        listar()
        return 0
    return gerar(a.doc_id, a.qtd)


if __name__ == "__main__":
    sys.exit(main())
