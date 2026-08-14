#!/usr/bin/env python3
"""
Ingere um PDF de edital: extrai data da prova e conteúdo programático.

    python edital.py corpus/edital.pdf --orgao "PC-PR" --banca FGV
    python edital.py corpus/edital.pdf --mesa "PF Agente"   # cria a mesa se não existir

Imprime os candidatos a data (não só "a resposta") e a contagem de tópicos
por disciplina — confira antes de rodar `chat.py meta`, mesmo espírito de
`diagnostico.py`: melhor esforço reportado, não decisão calada.

O edital entra numa MESA (migração 010), e é ele que define quais
disciplinas aquela mesa passa a mostrar. Sem `--mesa`, vai pra mesa padrão
da conta. Aqui `--mesa` CRIA a mesa se o nome não existir — ao contrário do
`chat.py`, onde nome desconhecido é erro: lá você está pedindo pra estudar
algo que já deveria existir, aqui você está montando o alvo agora.
"""
import argparse
import sys
from pathlib import Path

from core import auth, edital, mesa as mesa_mod
from core.config import CLI_USUARIO_EMAIL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--titulo")
    ap.add_argument("--orgao")
    ap.add_argument("--banca")
    ap.add_argument("--mesa", help="nome da mesa de estudo (criada se não existir)")
    a = ap.parse_args()

    if not a.arquivo.exists():
        print(f"arquivo não encontrado: {a.arquivo}", file=sys.stderr)
        return 1

    usuario_id = auth.usuario_da_cli(CLI_USUARIO_EMAIL)
    if a.mesa:
        m = next((x for x in mesa_mod.listar(usuario_id)
                  if x["nome"].lower() == a.mesa.lower()), None)
        m = m or mesa_mod.criar(usuario_id, a.mesa, orgao=a.orgao, banca=a.banca)
    else:
        m = mesa_mod.padrao(usuario_id)
    r = edital.ingerir(m["id"], a.arquivo, titulo=a.titulo, orgao=a.orgao, banca=a.banca)

    print(f"mesa: {m['nome']} (id {m['id']})")
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
