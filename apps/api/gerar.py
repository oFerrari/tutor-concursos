#!/usr/bin/env python3
"""
Geração de questões com COBERTURA por seção.

    python gerar.py --listar
    python gerar.py --cobertura 3
    python gerar.py 3 --cobrir --por-lote 3 --max 40
    python gerar.py 3 --secao "ADMINISTRACAO PUBLICA" --qtd 6

O QUE ESTAVA ERRADO
-------------------
A versão anterior amostrava `ORDER BY length(texto) DESC LIMIT 12`: gerava
questões sobre os 12 artigos mais compridos de 434 e ignorava o resto. Além
de cobrir 3% do código, escolhia mal — os artigos mais longos do CP são os
mais burocráticos, não os mais cobrados.

O CONCEITO: COBERTURA
---------------------
Cobertura é a fração do acervo que já virou questão. Para medi-la é preciso
PROVENIÊNCIA: saber de qual artigo cada questão saiu. Por isso o modelo agora
devolve o campo `artigo`, e ele é gravado em `questao.fonte_chunks`.

Com isso a geração deixa de ser aleatória e passa a ser dirigida: percorre as
seções, sempre pegando artigos ainda descobertos, e é retomável — rodar de
novo continua de onde parou, sem repetir o que já existe.

Artigo revogado e stub curto ficam de fora do alvo: não há o que cobrar deles.
"""
import argparse
import json
import re
import sys
import unicodedata

from core import db, geracao, llm, socratic

VERSAO = "gerar-v18"

MIN_TEXTO = geracao.MIN_TEXTO   # mesma régua da geração sob demanda
ARTIGOS_POR_LOTE = 3     # artigos enviados por chamada
MAX_FALHAS = 3           # falhas consecutivas antes de desistir


def listar():
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
    print(f"{'id':>3}  {'titulo':<28} {'disciplina':<22} {'chunks':>6} {'questoes':>8}")
    for r in linhas:
        print(f"{r['id']:>3}  {r['titulo'][:28]:<28} {r['disciplina'][:22]:<22} "
              f"{r['chunks']:>6} {r['questoes']:>8}")


# Postgres aceita alias solto no ORDER BY ("ORDER BY cobertos"), mas dentro de
# uma EXPRESSAO ele procura coluna das tabelas de origem e falha. Daí a CTE:
# agrega primeiro, ordena depois, com os aliases já materializados.
SQL_COBERTURA = """
WITH cob AS (
    SELECT DISTINCT unnest(fonte_chunks) AS chunk_id
    FROM questao WHERE documento_id = %(d)s
),
agg AS (
    SELECT COALESCE(c.secao, '(sem secao)') AS secao,
           COUNT(*) AS artigos,
           COUNT(*) FILTER (WHERE length(c.texto) >= %(min)s) AS alvo,
           COUNT(*) FILTER (WHERE cb.chunk_id IS NOT NULL) AS cobertos
    FROM chunk c
    LEFT JOIN cob cb ON cb.chunk_id = c.id
    WHERE c.documento_id = %(d)s
    GROUP BY 1
)
SELECT * FROM agg
ORDER BY cobertos::float / GREATEST(alvo, 1), alvo DESC
"""


def cobertura(doc_id, mostrar=15):
    linhas = db.query(SQL_COBERTURA, {"d": doc_id, "min": MIN_TEXTO})
    if not linhas:
        print(f"documento {doc_id} sem chunks.")
        return
    tot_alvo = sum(r["alvo"] for r in linhas)
    tot_cob = sum(r["cobertos"] for r in linhas)
    print(f"cobertura do documento {doc_id}: {tot_cob}/{tot_alvo} artigos "
          f"({100 * tot_cob / max(tot_alvo, 1):.1f}%)  ·  {len(linhas)} secoes\n")
    print(f"{'cob':>4}/{'alvo':<5} {'%':>5}  secao")
    for r in linhas[:mostrar]:
        p = 100 * r["cobertos"] / max(r["alvo"], 1)
        print(f"{r['cobertos']:>4}/{r['alvo']:<5} {p:5.0f}  {r['secao'][-60:]}")
    if len(linhas) > mostrar:
        print(f"... e {len(linhas) - mostrar} secoes")


SQL_DESCOBERTOS = """
WITH cob AS (
    SELECT DISTINCT unnest(fonte_chunks) AS chunk_id
    FROM questao WHERE documento_id = %(d)s
)
-- `d.usuario_id AS dono` não é enfeite: é o que `geracao.salvar` lê pra
-- decidir se a questão nasce pública ou privada (026). Esta CLI roda sobre o
-- corpus público, mas nada impede um `--doc N` apontando pra apostila de um
-- aluno, e sem esta coluna aquele lote gravaria material privado como público.
SELECT c.id, c.texto, c.artigo, c.rubrica, c.secao, c.pagina, c.documento_id,
       d.titulo, d.disciplina, d.tipo, d.assunto, d.usuario_id AS dono
FROM chunk c
JOIN documento d ON d.id = c.documento_id
LEFT JOIN cob cb ON cb.chunk_id = c.id
WHERE c.documento_id = %(d)s
  AND cb.chunk_id IS NULL
  AND length(c.texto) >= %(min)s
  AND c.texto NOT ILIKE '%%(revogad%%'
  {filtro_secao}
ORDER BY c.secao, c.ordem
LIMIT %(lim)s
"""


def _fold(txt):
    """Remove acento e caixa. 'ADMINISTRAÇÃO' e 'administracao' viram iguais."""
    return (unicodedata.normalize("NFKD", txt or "")
            .encode("ascii", "ignore").decode().upper())


def secoes(doc_id):
    return [r["secao"] for r in db.query(
        """SELECT DISTINCT secao FROM chunk
           WHERE documento_id = %(d)s AND secao IS NOT NULL ORDER BY 1""",
        {"d": doc_id})]


def casar_secoes(doc_id, termo):
    """
    ILIKE nao ignora acento: '%ADMINISTRACAO%' nao casa 'ADMINISTRAÇÃO'.
    Resolver em Python evita depender da extensao unaccent no Postgres.
    """
    t = _fold(termo)
    return [s for s in secoes(doc_id) if t in _fold(s)]


def descobertos(doc_id, secoes_alvo=None, limite=ARTIGOS_POR_LOTE):
    filtro = "AND c.secao = ANY(%(secs)s)" if secoes_alvo else ""
    params = {"d": doc_id, "min": MIN_TEXTO, "lim": limite}
    if secoes_alvo:
        params["secs"] = secoes_alvo
    return db.query(SQL_DESCOBERTOS.format(filtro_secao=filtro), params)


def salvar(doc_id, disciplina, questoes, lote):
    """Grava pela regra compartilhada (`core.geracao.salvar`) e IMPRIME — a
    impressão é da CLI, a regra não. Antes esta função tinha a cópia da
    regra; ter duas é como elas passam a divergir, e a que divergisse seria
    a que grava proveniência (a invariante do projeto).

    `doc_id`/`disciplina` não são mais usados pra gravar: saem do chunk
    casado, que é o dado certo quando o lote atravessa normas."""
    salvas, descartes = geracao.salvar(questoes, lote)
    for motivo in descartes:
        print(f"    descartada: {motivo}")
    for q in salvas:
        print(f"    + {q['disciplina']}: {q['tema'][:52]}")
    return len(salvas)


def cobrir(doc_id, por_lote, maximo, secao=None):
    doc = db.exec1("SELECT id, titulo, disciplina FROM documento WHERE id = %(i)s",
                   {"i": doc_id})
    if not doc:
        print(f"documento {doc_id} nao existe. Use --listar.", file=sys.stderr)
        return 1

    secoes_alvo = None
    if secao:
        secoes_alvo = casar_secoes(doc_id, secao)
        # Filtro que nao casa nada e acervo totalmente coberto sao situacoes
        # OPOSTAS. Tratar as duas com a mesma mensagem fazia o programa
        # afirmar "cobertura completa" quando nada havia sido gerado.
        if not secoes_alvo:
            print(f"nenhuma secao casa com {secao!r}. Disponiveis:\n")
            for s_ in secoes(doc_id):
                print(f"  {s_}")
            print("\nDica: o termo e comparado sem acento e sem caixa.")
            return 1
        print(f"{len(secoes_alvo)} secao(oes) casaram com {secao!r}")

    total = 0
    falhas = 0
    while total < maximo:
        # Um artigo por questao pedida. Enviar 6 artigos para pedir 3 questoes
        # deixava 3 descobertos, que voltavam no lote seguinte — contexto pago
        # duas vezes sem ganho de cobertura.
        pedir = min(por_lote, maximo - total)
        lote = descobertos(doc_id, secoes_alvo, limite=pedir)
        if not lote:
            alvo = "deste filtro" if secoes_alvo else "do documento"
            print(f"todos os artigos {alvo} ja tem questao.")
            break
        sec = (lote[0]["secao"] or "(sem secao)")[-56:]
        arts = ", ".join(c["artigo"] or "?" for c in lote)
        print(f"\nsecao …{sec}\n  artigos no lote: {arts}")
        try:
            questoes = socratic.gerar_questoes(lote, pedir)
            # `falhas` só zera quando algo é de fato SALVO (mais abaixo) —
            # zerar aqui, só porque a chamada em si funcionou, é o bug que
            # deixava o loop girar pra sempre: nunca passava de 1 antes de
            # resetar de novo no próximo lote "bem-sucedido e inútil".
        except llm.ErroLLM as e:
            falhas += 1
            print(f"  lote falhou ({falhas}/{MAX_FALHAS}): {e}", file=sys.stderr)
            if falhas >= MAX_FALHAS:
                print(f"  desistindo. {total} questoes salvas ate aqui; "
                      f"rode de novo para continuar de onde parou.")
                break
            continue
        if not questoes:
            falhas += 1
            print(f"  modelo nao devolveu questao valida ({falhas}/{MAX_FALHAS}).")
            if falhas >= MAX_FALHAS:
                break
            continue
        salvas_agora = salvar(doc_id, doc["disciplina"], questoes, lote)
        if salvas_agora == 0:
            # A CHAMADA funcionou (não caiu no ErroLLM acima) mas nada foi
            # aproveitável — sem isso `falhas` fica sempre 0 e o loop tenta
            # a MESMA seção pra sempre, cada tentativa uma chamada real e
            # paga ao LLM. Foi o que aconteceu gerando pra CF (bug do
            # ordinal em _norm_artigo, corrigido acima) antes desta guarda
            # existir: ~45 min girando sem UMA questão salva.
            falhas += 1
            print(f"  lote nao rendeu nenhuma questao aproveitavel ({falhas}/{MAX_FALHAS}).")
            if falhas >= MAX_FALHAS:
                print(f"  desistindo. {total} questoes salvas ate aqui; "
                      f"rode de novo para continuar de onde parou.")
                break
            continue
        falhas = 0
        total += salvas_agora

    print(f"\n{total} questoes salvas.")
    if total:
        cobertura(doc_id, mostrar=6)
        print("\nRode: python chat.py estudar")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc_id", nargs="?", type=int)
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--cobertura", type=int, metavar="DOC")
    ap.add_argument("--cobrir", action="store_true")
    ap.add_argument("--secao", help="filtra por trecho do nome da secao (sem acento serve)")
    ap.add_argument("--secoes", type=int, metavar="DOC", help="lista as secoes do documento")
    ap.add_argument("--por-lote", type=int, default=3, dest="por_lote")
    ap.add_argument("--max", type=int, default=20, dest="maximo")
    ap.add_argument("--qtd", type=int, help="atalho: --cobrir --max QTD")
    a = ap.parse_args()

    print(f"versoes: {VERSAO} · {socratic.VERSAO}\n")

    if a.listar:
        listar(); return 0
    if a.secoes is not None:
        for s_ in secoes(a.secoes):
            print(s_)
        return 0
    if a.cobertura is not None:
        cobertura(a.cobertura); return 0
    if a.doc_id is None:
        listar(); return 0
    if a.qtd:
        return cobrir(a.doc_id, a.por_lote, a.qtd, a.secao)
    if a.cobrir or a.secao:
        return cobrir(a.doc_id, a.por_lote, a.maximo, a.secao)
    cobertura(a.doc_id)
    print("\nnada gerado. Use --cobrir para gerar, ou --secao para focar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
