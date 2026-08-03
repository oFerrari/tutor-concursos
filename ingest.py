#!/usr/bin/env python3
"""
Ingestão de material.

    python ingest.py acervo/cp.pdf --disciplina "Direito Penal" --tipo lei --norma "CP"
    python ingest.py acervo/aula07.pdf --disciplina "Informática" --tipo aula
    python ingest.py acervo/aula07.pdf --disciplina "Informática" --tipo aula --gerar 8

Roda como worker: é batch, nunca está no caminho da requisição HTTP.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from core import chunking, db, embeddings, socratic

LOTE = 32


def extrair(caminho: Path) -> list[tuple[int, str]]:
    """Devolve [(pagina, texto)]. Página 0 para arquivos sem paginação."""
    if caminho.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(caminho))
        return [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
    return [(0, caminho.read_text(encoding="utf-8", errors="ignore"))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--disciplina", required=True)
    ap.add_argument("--tipo", default="aula", choices=["lei", "aula", "resumo", "jurisprudencia"])
    ap.add_argument("--norma", help="sigla da norma, obrigatória quando --tipo lei (ex.: CF, CP, CPP)")
    ap.add_argument("--titulo")
    ap.add_argument("--gerar", type=int, default=0, help="gerar N questões após ingerir")
    a = ap.parse_args()

    if not a.arquivo.exists():
        print(f"arquivo não encontrado: {a.arquivo}", file=sys.stderr)
        return 1
    if a.tipo == "lei" and not a.norma:
        print("--norma é obrigatório para --tipo lei", file=sys.stderr)
        return 1

    digest = hashlib.sha256(a.arquivo.read_bytes()).hexdigest()
    if db.exec1("SELECT id FROM documento WHERE hash = %(h)s", {"h": digest}):
        print("este arquivo já foi ingerido (hash idêntico). Nada a fazer.")
        return 0

    titulo = a.titulo or a.arquivo.stem
    paginas = extrair(a.arquivo)
    bruto = "\n\n".join(t for _, t in paginas)
    if len(bruto.strip()) < 200:
        print("texto extraído é curto demais — PDF provavelmente é imagem escaneada.", file=sys.stderr)
        print("rode OCR antes (ocrmypdf) e tente de novo.", file=sys.stderr)
        return 1

    chunks = (chunking.chunk_lei(bruto, a.norma) if a.tipo == "lei"
              else chunking.chunk_generico(bruto))
    print(f"{titulo}: {len(paginas)} páginas → {len(chunks)} chunks")

    doc = db.exec1(
        """INSERT INTO documento (titulo, disciplina, tipo, origem, hash)
           VALUES (%(t)s, %(d)s, %(tp)s, %(o)s, %(h)s) RETURNING id""",
        {"t": titulo, "d": a.disciplina, "tp": a.tipo, "o": str(a.arquivo), "h": digest},
    )
    doc_id = doc["id"]

    ids = []
    for i in range(0, len(chunks), LOTE):
        lote = chunks[i:i + LOTE]
        vetores = embeddings.embed_passagens([c["texto"] for c in lote])
        for j, (c, v) in enumerate(zip(lote, vetores)):
            r = db.exec1(
                """INSERT INTO chunk (documento_id, ordem, texto, norma, artigo,
                                      paragrafo, inciso, rubrica, secao, embedding)
                   VALUES (%(d)s, %(o)s, %(tx)s, %(n)s, %(a)s, %(p)s, %(i)s,
                           %(r)s, %(s)s, %(e)s)
                   RETURNING id""",
                {"d": doc_id, "o": i + j, "tx": c["texto"], "n": c["norma"],
                 "a": c["artigo"], "p": c["paragrafo"], "i": c["inciso"],
                 "r": c.get("rubrica"), "s": c.get("secao"), "e": v},
            )
            ids.append(r["id"])
        print(f"  indexados {min(i + LOTE, len(chunks))}/{len(chunks)}")

    if a.gerar:
        amostra = db.query(
            """SELECT c.id, c.texto, c.artigo, c.paragrafo, c.pagina,
                      d.titulo, d.disciplina, d.tipo
               FROM chunk c JOIN documento d ON d.id = c.documento_id
               WHERE c.documento_id = %(d)s
               ORDER BY length(c.texto) DESC LIMIT 12""",
            {"d": doc_id},
        )
        print(f"gerando {a.gerar} questões…")
        try:
            for q in socratic.gerar_questoes(amostra, a.gerar):
                db.query(
                    """INSERT INTO questao (documento_id, disciplina, tema, enunciado,
                                            gabarito, dicas, fonte_chunks)
                       VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s)""",
                    {"d": doc_id, "disc": a.disciplina, "t": q["tema"], "e": q["enunciado"],
                     "g": q["gabarito"], "dic": json.dumps(q["dicas"]), "f": [c["id"] for c in amostra]},
                )
                print(f"  + {q['tema']}")
        except Exception as e:
            print(f"geração falhou ({e}). O material já está indexado; rode de novo depois.",
                  file=sys.stderr)

    print(f"pronto. documento_id={doc_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
