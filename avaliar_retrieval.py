#!/usr/bin/env python3
"""
Mede precisão de core/retrieval.py contra um gabarito de (pergunta, artigo
esperado) — a única peça do pipeline que não tinha nenhum número até agora.

    python avaliar_retrieval.py

Por que existe: chunking (diagnostico.py) e scheduler (harness de
integração) já foram validados. O meio — "dado uma pergunta, a busca híbrida
recupera o artigo certo?" — nunca tinha sido medido. "RAG está bom" sem isso
era opinião, não número.

O gabarito foi conferido contra o banco real (`SELECT artigo FROM chunk
WHERE rubrica ILIKE ...`), não de memória — o corpus muda de emenda em
emenda e confiar em memória de treino sobre article numbers é o mesmo erro
que este módulo existe para evitar.

Três categorias, precisão esperada em ordem decrescente (é a mesma ordem de
prioridade que `retrieval.buscar()` usa):
  dispositivo — citação exata ("art. 312"). Deve ser ~100%: é busca por
                metadado, não há ambiguidade possível.
  rubrica     — nome do crime ("concussão"). Deve ser ~100% pelo mesmo motivo.
  hibrida     — pergunta conceitual, sem citar artigo nem nome do crime.
                Aqui SIM cabe imprecisão de rank — o objetivo realista é
                top-N alto (o artigo aparece no contexto que o LLM vê), não
                top-1 perfeito.
"""
from core import retrieval

VERSAO = "avaliar_retrieval-v1"

CASOS = [
    # categoria, pergunta, artigo esperado
    ("dispositivo", "o que diz o art. 312 do código penal?", "312"),
    ("dispositivo", "artigo 121 do CP", "121"),
    ("dispositivo", "me explique o art. 157, o que ele diz", "157"),

    ("rubrica", "concussão", "316"),
    ("rubrica", "peculato", "312"),
    ("rubrica", "estelionato", "171"),
    ("rubrica", "prevaricação", "319"),

    ("hibrida", "funcionário público que exige vantagem indevida para si em razão do cargo", "316"),
    ("hibrida", "subtrair para si coisa alheia móvel mediante grave ameaça ou violência à pessoa", "157"),
    ("hibrida", "obter vantagem ilícita em prejuízo alheio induzindo alguém em erro mediante ardil", "171"),
    ("hibrida", "servidor público que se apropria de dinheiro que tem posse em razão do cargo", "312"),
    ("hibrida", "funcionário público que retarda ato de ofício para satisfazer interesse pessoal", "319"),
    ("hibrida", "matar alguém por motivo torpe mediante paga ou promessa de recompensa", "121"),
    ("hibrida", "ofender a dignidade de alguém com xingamento", "140"),
    ("hibrida", "imputar a alguém, sabendo falso, fato definido como crime", "138"),
]


def artigos_de(chunks):
    return [c.get("artigo") for c in chunks]


def main(n: int = 6):
    acertos_top1 = 0
    acertos_topn = 0
    por_categoria = {}

    print(f"{'cat':10s} {'esperado':8s} {'achou@1':8s} {'pos':4s} {'pergunta'}")
    for cat, pergunta, esperado in CASOS:
        chunks = retrieval.buscar(pergunta, n=n)
        arts = artigos_de(chunks)
        pos = arts.index(esperado) + 1 if esperado in arts else None
        top1 = bool(arts) and arts[0] == esperado

        acertos_top1 += int(top1)
        acertos_topn += int(pos is not None)
        c = por_categoria.setdefault(cat, {"top1": 0, "topn": 0, "total": 0})
        c["total"] += 1
        c["top1"] += int(top1)
        c["topn"] += int(pos is not None)

        marca = "✓" if top1 else ("~" if pos else "✗")
        print(f"{cat:10s} {esperado:8s} {marca:8s} {str(pos):4s} {pergunta[:60]}")
        if pos is None:
            print(f"           -> devolveu: {arts}")

    total = len(CASOS)
    print(f"\n{'='*70}")
    print(f"top1 (primeiro resultado é o artigo certo): {acertos_top1}/{total} "
          f"({100*acertos_top1/total:.0f}%)")
    print(f"top{n} (artigo certo aparece entre os {n}):      {acertos_topn}/{total} "
          f"({100*acertos_topn/total:.0f}%)")
    print()
    for cat, c in por_categoria.items():
        print(f"  {cat:10s} top1 {c['top1']}/{c['total']}  top{n} {c['topn']}/{c['total']}")


if __name__ == "__main__":
    main()
