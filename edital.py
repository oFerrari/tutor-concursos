#!/usr/bin/env python3
"""
Ingere um PDF de edital: extrai data da prova e conteúdo programático.

    python edital.py corpus/edital.pdf --orgao "PC-PR" --banca FGV

Imprime os candidatos a data (não só "a resposta") e a contagem de tópicos
por disciplina — confira antes de rodar `chat.py meta`, mesmo espírito de
`diagnostico.py`: melhor esforço reportado, não decisão calada.
"""
import argparse
import sys
from pathlib import Path

from core import edital


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--titulo")
    ap.add_argument("--orgao")
    ap.add_argument("--banca")
    a = ap.parse_args()

    if not a.arquivo.exists():
        print(f"arquivo não encontrado: {a.arquivo}", file=sys.stderr)
        return 1

    r = edital.ingerir(a.arquivo, titulo=a.titulo, orgao=a.orgao, banca=a.banca)

    print(f"edital_id={r['edital_id']}")
    print(f"\ndata da prova escolhida: {r['data_prova']}")
    if len(r["candidatos_data"]) > 1:
        print("outros candidatos (conferir se a escolha acima está certa):")
        for c in r["candidatos_data"][1:]:
            print(f"  {c['data']} (pontuação {c['pontuacao']}) — ...{c['contexto']}")
    elif not r["candidatos_data"]:
        print("NENHUM candidato a data encontrado — rode `chat.py meta AAAA-MM-DD` "
              "manualmente ou confira o layout deste edital.")

    print(f"\n{r['topicos']} tópicos em {len(r['disciplinas'])} disciplinas:")
    for d in r["disciplinas"]:
        print(f"  - {d}")

    if r["topicos"] == 0:
        print("\nAVISO: nenhum tópico reconhecido. O padrão 'N. DISCIPLINA:' + "
              "subitens 'N.N' não bateu neste edital — layout desta banca é "
              "diferente do que core/edital.py espera.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
