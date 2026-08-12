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

FONTE_CHUNKS SOBREVIVE À REINGESTÃO (antes não sobrevivia — gap documentado
no CLAUDE.md, corrigido aqui): `DELETE FROM chunk` + `INSERT` de novo dá IDs
novos pra tudo, e `questao.fonte_chunks` guarda ID cru, não (norma, artigo)
— sem remapear, a referência ficava órfã em silêncio (mesmo problema que
`sincronizar.py` já resolve na importação, só que aqui era pra dentro de UM
banco só). A ideia é a mesma de `sincronizar.py`: capturar (norma, artigo)
dos chunks ANTIGOS antes do DELETE, e depois de inserir os novos, traduzir
cada id antigo referenciado em `fonte_chunks` para o novo id que tem o
MESMO (norma, artigo). Referência sem correspondência nova (artigo saiu do
material, ou renumerou) fica órfã DECLARADA — reportada no fim, não
escondida — porque decidir sozinho qual chunk é o certo seria adivinhar.

SEGURANÇA: todo chunk e embedding novo é calculado ANTES de qualquer DELETE.
Uma versão anterior apagava primeiro e calculava depois — um erro no meio
(já aconteceu: mudança de API do pgvector.Vector) deixava o documento com
ZERO chunks e sem transação pra reverter (db.py usa autocommit=True). Se
--norma não for passado, ele é inferido dos chunks ATUAIS — o que também
falha nesse cenário, por isso --norma explícito existe como saída de
emergência.
"""
import argparse
import hashlib
import sys
from pathlib import Path

from core import chunking, db, embeddings

VERSAO = "reingest-v4"
LOTE = 64
LIMIAR_COLISAO = 0.05  # ver core.chunking.taxa_colisao_artigo


def extrair(caminho: Path) -> str:
    if caminho.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(caminho)).pages)
    return caminho.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", type=int, required=True)
    ap.add_argument("--arquivo", type=Path, help="padrão: documento.origem")
    ap.add_argument("--norma", help="sigla da norma; padrão: inferida dos chunks atuais")
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

    norma = a.norma
    if doc["tipo"] == "lei" and not norma:
        # Inferir dos chunks ATUAIS só funciona se eles ainda existirem — se
        # uma reingestão anterior falhou depois do DELETE (ver comentário
        # abaixo sobre por que isso não deveria mais acontecer), a inferência
        # fica impossível e trava reingest.py bem no momento em que mais se
        # precisa dele. --norma explícito é o jeito de nunca ficar preso nisso.
        r = db.exec1(
            "SELECT norma FROM chunk WHERE documento_id = %(i)s AND norma IS NOT NULL LIMIT 1",
            {"i": a.doc},
        )
        norma = r["norma"] if r else None
        if not norma:
            print("não consegui inferir a norma dos chunks atuais (podem não existir "
                  "mais). Passe --norma explicitamente, ex.: --norma CP", file=sys.stderr)
            return 1

    antes = db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id = %(i)s", {"i": a.doc})
    bruto = extrair(caminho)
    chunks = (chunking.chunk_lei(bruto, norma) if doc["tipo"] == "lei"
              else chunking.chunk_generico(bruto))
    if not chunks:
        print("o chunking não produziu nada; abortando sem alterar o banco.", file=sys.stderr)
        return 1
    if doc["tipo"] == "lei":
        taxa = chunking.taxa_colisao_artigo(chunks)
        if taxa > LIMIAR_COLISAO:
            print(f"ABORTADO: {taxa:.0%} dos chunks colidem em (norma, artigo) — "
                  f"muito acima do esperado para lei compilada. Arquivo errado para "
                  f"este documento? Nada foi alterado no banco.", file=sys.stderr)
            return 1

    print(f"{doc['titulo']}: {antes['n']} chunks no banco → {len(chunks)} recalculados")

    # TUDO que pode falhar (rede, cache, encode do modelo) roda ANTES de
    # tocar no banco. A versão anterior dava DELETE e só depois calculava
    # embedding lote a lote — um erro no meio (como o bug de API do
    # pgvector.Vector que apareceu aqui) deixava o documento com ZERO
    # chunks, sem nada para reverter, porque autocommit=True não dá
    # transação para desfazer. Calcular tudo primeiro e só then substituir
    # é o que torna esse comando seguro de repetir depois de uma falha.
    lotes_prontos = []
    for i in range(0, len(chunks), LOTE):
        lote = chunks[i:i + LOTE]
        vetores = embeddings.embed_passagens([c["texto"] for c in lote], relatorio=True)
        lotes_prontos.append((i, lote, vetores))
        print(f"  calculado {min(i + LOTE, len(chunks))}/{len(chunks)}")

    # Captura ANTES do DELETE: (norma, artigo) de cada chunk atual, e quais
    # questões referenciam algum deles em fonte_chunks. É o material bruto
    # pra remapear depois — mesmo princípio de "calcular tudo antes de tocar
    # no banco" do bloco de embeddings acima, só que para o remapeamento.
    chunks_antigos = db.query(
        "SELECT id, norma, artigo FROM chunk WHERE documento_id = %(i)s AND artigo IS NOT NULL",
        {"i": a.doc},
    )
    norma_artigo_por_id_antigo = {c["id"]: (c["norma"], c["artigo"]) for c in chunks_antigos}
    ids_antigos = list(norma_artigo_por_id_antigo)
    questoes_afetadas = db.query(
        # fonte_chunks é bigint[] (_int8) — sem o cast explícito, psycopg
        # manda uma lista de int Python como smallint[] por padrão e o
        # Postgres recusa comparar os dois tipos de array (achado rodando
        # isto de verdade, não em teoria).
        "SELECT id, fonte_chunks FROM questao WHERE fonte_chunks && %(ids)s::bigint[]",
        {"ids": ids_antigos},
    ) if ids_antigos else []

    # Substitui só os chunks. As questões apontam para documento_id e sobrevivem.
    db.query("DELETE FROM chunk WHERE documento_id = %(i)s", {"i": a.doc})

    for i, lote, vetores in lotes_prontos:
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

    if questoes_afetadas:
        mapa_novo = {
            f"{r['norma']}|{r['artigo']}": r["id"]
            for r in db.query(
                "SELECT id, norma, artigo FROM chunk WHERE documento_id = %(i)s AND artigo IS NOT NULL",
                {"i": a.doc},
            )
        }
        remapeadas = 0
        sem_correspondencia = []
        for q in questoes_afetadas:
            novo_fonte = []
            mudou = False
            for cid in q["fonte_chunks"]:
                na = norma_artigo_por_id_antigo.get(cid)
                if na is None:
                    novo_fonte.append(cid)  # não veio deste lote de remapeamento — preserva como estava
                    continue
                novo_id = mapa_novo.get(f"{na[0]}|{na[1]}")
                if novo_id is None:
                    sem_correspondencia.append((q["id"], na))
                    novo_fonte.append(cid)  # órfão DECLARADO — não escondido, ver docstring do módulo
                    continue
                mudou = mudou or novo_id != cid
                novo_fonte.append(novo_id)
            if mudou:
                db.query("UPDATE questao SET fonte_chunks = %(f)s WHERE id = %(i)s",
                         {"f": novo_fonte, "i": q["id"]})
                remapeadas += 1
        print(f"fonte_chunks remapeado em {remapeadas}/{len(questoes_afetadas)} questão(ões) "
              f"afetada(s) via (norma, artigo).")
        if sem_correspondencia:
            print(f"  aviso: {len(sem_correspondencia)} referência(s) sem chunk novo "
                  f"correspondente (artigo saiu do material ou renumerou) — fonte_chunks "
                  f"ficou com o id antigo, órfão. Confira: {sem_correspondencia[:5]}")

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
