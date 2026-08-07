#!/usr/bin/env python3
"""
Diagnóstico do chunking — SEM banco, SEM embeddings, SEM cota de API.

    python diagnostico.py acervo/cp.txt --norma CP

MEDIR A COISA CERTA
-------------------
"Quantos artigos têm rubrica?" não mede o chunking: mede o CP. A maioria das
rubricas nomeia um BLOCO de artigos ("Penas restritivas de direitos" encabeça
os arts. 43 a 48), então artigo sem rubrica é o caso normal, não defeito.

O defeito real é PERDA DE INFORMAÇÃO: existir no arquivo uma linha de rubrica
que o chunking não atribuiu a nenhum artigo. Então a auditoria funciona assim:

  candidata = linha não vazia, que não é artigo nem cabeçalho, e cuja próxima
              linha não vazia é um "Art."  (é a posição onde rubrica aparece)

  aceita    = candidata que passou por chunking._eh_rubrica
  rejeitada = candidata descartada, agrupada POR MOTIVO

Ver o motivo é o que permite distinguir filtro correto ("é o fim do texto do
artigo anterior, termina em ponto") de filtro exagerado (foi o que aconteceu
com "Pena cumprida no estrangeiro", derrubada por uma regra ampla demais).
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from core import chunking

VERSAO = "diagnostico-v12"


def carregar(caminho: Path) -> str:
    if caminho.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(caminho)).pages)
    return caminho.read_text(encoding="utf-8", errors="ignore")


def _prox_nao_vazia(linhas, i):
    """
    Próxima linha com conteúdo, PULANDO nota legislativa isolada — igual ao
    que _cortar_cauda faz. Sem esse alinhamento a auditoria fica defasada do
    código auditado e acusa descasamento onde não existe. Ferramenta de
    medição também é código e também envelhece.
    """
    j = i + 1
    while j < len(linhas) and (not linhas[j].strip() or chunking._so_nota(linhas[j])):
        j += 1
    return j if j < len(linhas) else None


def _ant_nao_vazia(linhas, i):
    j = i - 1
    while j >= 0 and not linhas[j].strip():
        j -= 1
    return j if j >= 0 else None


def candidatas(linhas):
    """Linhas na POSIÇÃO onde rubrica aparece: imediatamente antes de um Art."""
    out = []
    for i, l in enumerate(linhas):
        s = l.strip()
        if not s or chunking.RE_ARTIGO.match(s) or chunking.RE_NIVEL.match(s):
            continue
        j = _prox_nao_vazia(linhas, i)
        if j is not None and chunking.RE_ARTIGO.match(linhas[j].strip()):
            out.append((i, s, chunking.RE_ARTIGO.match(linhas[j].strip()).group(1)))
    return out


def motivo(linha):
    """
    Por que _eh_rubrica rejeitou. Duplica a lógica de propósito: diagnóstico
    que reusa a função testada não consegue explicar a decisão dela.
    """
    l = chunking._sem_nota(linha)
    if not l:
        return "vazia após remover nota (era só nota legislativa)"
    if len(l) > 90:
        return "longa demais (>90 char) — é texto de artigo"
    if l.endswith((".", ":", ";", ",")):
        return "termina em pontuação — fim do texto do artigo anterior"
    if not l[0].isupper():
        return "não começa em maiúscula"
    if re.match(r"(?i)^(pena[s]?\s*[-–—:]|par[áa]grafo|§|[IVXLCDM]+\s*[-–—)]|\()", l):
        return "é cominação de pena, parágrafo, inciso ou nota"
    if chunking.RE_NOTA.search(l):
        return "contém nota legislativa não removível"
    if chunking._eh_caixa_alta(l) and len(l.split()) > 5:
        return "caixa alta longa — é cabeçalho, não rubrica"
    # _ler_cauda exclui QUALQUER linha em caixa alta da rubrica (é cabeçalho
    # sem prefixo TÍTULO/CAPÍTULO, como "DISPOSIÇÕES FINAIS"). Sem replicar
    # isso aqui, a auditoria acusava descasamento onde não havia bug.
    if chunking._eh_caixa_alta(l):
        return "caixa alta — cabeçalho de seção sem prefixo"
    return "ACEITA"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--norma", default="LEI")
    ap.add_argument("--tipo", default="lei", choices=["lei", "aula"])
    ap.add_argument("--mostrar", type=int, default=8)
    a = ap.parse_args()

    if not a.arquivo.exists():
        print(f"nao encontrei {a.arquivo}", file=sys.stderr)
        return 1

    print(f"versoes: {chunking.VERSAO} · {VERSAO}\n")
    bruto = carregar(a.arquivo)
    chunks = (chunking.chunk_lei(bruto, a.norma) if a.tipo == "lei"
              else chunking.chunk_generico(bruto))
    if not chunks:
        print("o chunking nao produziu nada.", file=sys.stderr)
        return 1

    total = len(chunks)
    com_rub = sum(1 for c in chunks if c.get("rubrica"))
    pc = lambda n, d: f"{100 * n / d:5.1f}%" if d else "  n/a"

    print(f"arquivo   : {a.arquivo}  ({len(bruto):,} caracteres)")
    marcas = len(chunking.RE_ARTIGO.findall(chunking.normalizar_lei(bruto)))
    print(f"artigos no texto : {marcas}")
    print(f"chunks    : {total}", end="")
    print(f"   >>> {marcas - total} ARTIGO(S) DESCARTADO(S) por corpo curto"
          if marcas > total else "   (nenhum artigo perdido)")
    print(f"rubrica   : {com_rub:4}  {pc(com_rub, total)}  (artigo sem rubrica e normal)")
    print(f"secao     : {sum(1 for c in chunks if c.get('secao')):4}  "
          f"{pc(sum(1 for c in chunks if c.get('secao')), total)}")
    print(f"paragrafo : {sum(1 for c in chunks if c.get('paragrafo')):4}  "
          f"{pc(sum(1 for c in chunks if c.get('paragrafo')), total)}")

    linhas = chunking.normalizar_lei(bruto).split("\n")
    cands = candidatas(linhas)
    motivos = Counter(motivo(s) for _, s, _ in cands)
    aceitas = motivos.get("ACEITA", 0)

    print(f"\n{'=' * 74}")
    print("AUDITORIA DE RUBRICA — o defeito e perder linha, nao artigo sem nome")
    print("=" * 74)
    print(f"candidatas (linha imediatamente antes de um Art.) : {len(cands)}")
    print(f"aceitas como rubrica                              : {aceitas}")
    print(f"atribuidas a algum chunk                          : {com_rub}")
    if aceitas != com_rub:
        print(f"  >>> DESCASAMENTO de {abs(aceitas - com_rub)}: aceita pelo filtro mas")
        print(f"      nao chegou ao chunk (ou o inverso). Isso e bug de atribuicao.")
    print(f"\nrejeitadas por motivo:")
    for m, n in motivos.most_common():
        if m != "ACEITA":
            print(f"  {n:4}  {m}")

    duvidosas = [(i, s, art) for i, s, art in cands
                 if motivo(s) not in ("ACEITA",
                                      "termina em pontuação — fim do texto do artigo anterior",
                                      "longa demais (>90 char) — é texto de artigo",
                                      "não começa em maiúscula")]
    if duvidosas:
        print(f"\n{'=' * 74}\nrejeicoes que merecem olhar ({len(duvidosas)})\n{'=' * 74}")
        for i, s, art in duvidosas[:a.mostrar]:
            print(f"\nlinha {i} · antes do art. {art}")
            print(f"  motivo: {motivo(s)}")
            print(f"  {s[:110]!r}")
    else:
        print("\nnenhuma rejeicao duvidosa: toda linha na posicao de rubrica foi")
        print("aceita ou rejeitada por criterio claramente correto.")

    sem_rub = [c for c in chunks if not c.get("rubrica")]
    por_art = {art: (i, s) for i, s, art in cands}
    orfaos = [c for c in sem_rub if c["artigo"] in por_art
              and motivo(por_art[c["artigo"]][1]) == "ACEITA"]
    print(f"\nartigos sem rubrica: {len(sem_rub)}")
    print(f"  destes, com candidata ACEITA que nao foi atribuida: {len(orfaos)}  "
          f"<- unico numero que indica bug")
    for c in orfaos[:5]:
        i, s = por_art[c["artigo"]]
        print(f"    art {c['artigo']}: linha {i} {s[:70]!r}")

    secoes = Counter(c.get("secao") or "(sem secao)" for c in chunks)
    print(f"\nsecoes distintas: {len(secoes)}  ·  "
          f"maior: {secoes.most_common(1)[0][1]} artigos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
