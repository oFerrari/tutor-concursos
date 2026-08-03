#!/usr/bin/env python3
"""
Reingestão incremental de um documento já ingerido.

    python reingest.py --doc 3
    python reingest.py --doc 3 --arquivo acervo/cp.txt

Para que serve: quando o CHUNKING muda (rubrica capturada, normalização de
linha), o texto de alguns chunks muda e o de outros não. Reprocessar tudo
é desperdício de CPU. Aqui os chunks são recalculados, mas o embedding vem
do cache para todo texto que continua igual — e as QUESTÕES do documento
são preservadas, porque só a tabela chunk é substituída.

Ao contrário de `DELETE FROM documento`, isto não apaga seu progresso.
"""
import argparse
import hashlib
import sys
from pathlib import Path

from core import chunking, db, embeddings

LOTE = 64


def extrair(caminho: Path) -> str:
    if caminho.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(caminho)).pages)
    return caminho.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=int, required=True)
    ap.add_argument("--arquivo", type=Path, help="padrão: documento.origem")
    a = ap.parse_args()

    doc = db.exec1(
        "SELECT id, titulo, tipo, origem, disciplina FROM documento WHERE id = %(i)s",
        {"i": a.doc},
    )
    if not doc:
        print(f"documento {a.doc} não existe.", file=sys.stderr)
        return 1

    caminho = a.arquivo or Path(doc["origem"] or "")
    if not caminho.exists():
        print(f"arquivo não encontrado: {caminho}. Use --arquivo.", file=sys.stderr)
        return 1

    norma = None
    if doc["tipo"] == "lei":
        r = db.exec1(
            "SELECT norma FROM chunk WHERE documento_id = %(i)s AND norma IS NOT NULL LIMIT 1",
            {"i": a.doc},
        )
        norma = r["norma"] if r else None
        if not norma:
            print("não consegui inferir a norma dos chunks atuais.", file=sys.stderr)
            return 1

    antes = db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id = %(i)s", {"i": a.doc})
    bruto = extrair(caminho)
    chunks = (chunking.chunk_lei(bruto, norma) if doc["tipo"] == "lei"
              else chunking.chunk_generico(bruto))
    if not chunks:
        print("o chunking não produziu nada; abortando sem alterar o banco.", file=sys.stderr)
        return 1

    print(f"{doc['titulo']}: {antes['n']} chunks no banco → {len(chunks)} recalculados")

    # Substitui só os chunks. As questões apontam para documento_id e sobrevivem.
    db.query("DELETE FROM chunk WHERE documento_id = %(i)s", {"i": a.doc})

    for i in range(0, len(chunks), LOTE):
        lote = chunks[i:i + LOTE]
        vetores = embeddings.embed_passagens([c["texto"] for c in lote], relatorio=True)
        for j, (c, v) in enumerate(zip(lote, vetores)):
            db.query(
                """INSERT INTO chunk (documento_id, ordem, texto, norma, artigo,
                                      paragrafo, inciso, rubrica, secao, embedding)
                   VALUES (%(d)s, %(o)s, %(tx)s, %(n)s, %(a)s, %(p)s, %(i)s,
                           %(r)s, %(s)s, %(e)s)""",
                {"d": a.doc, "o": i + j, "tx": c["texto"], "n": c["norma"],
                 "a": c["artigo"], "p": c["paragrafo"], "i": c["inciso"],
                 "r": c.get("rubrica"), "s": c.get("secao"), "e": v},
            )
        print(f"  gravados {min(i + LOTE, len(chunks))}/{len(chunks)}")

    novo_hash = hashlib.sha256(caminho.read_bytes()).hexdigest()
    db.query("UPDATE documento SET hash = %(h)s WHERE id = %(i)s",
             {"h": novo_hash, "i": a.doc})

    r = db.exec1(
        """SELECT count(*) total, count(rubrica) rubrica, count(secao) secao,
                  count(paragrafo) paragrafo
           FROM chunk WHERE documento_id = %(i)s""",
        {"i": a.doc},
    )
    print(f"pronto: {r['total']} chunks · {r['rubrica']} com rubrica · "
          f"{r['secao']} com seção · {r['paragrafo']} com parágrafo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
