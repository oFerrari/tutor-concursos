#!/usr/bin/env python3
"""
Mede precisão de core/retrieval.py contra um gabarito de (pergunta, norma,
artigo esperados) — a única peça do pipeline que não tinha nenhum número até
a primeira versão deste script.

    python avaliar_retrieval.py

Por que existe: chunking (diagnostico.py) e scheduler (harness de
integração) já foram validados. O meio — "dado uma pergunta, a busca híbrida
recupera o artigo certo?" — nunca tinha sido medido. "RAG está bom" sem isso
era opinião, não número.

O gabarito foi conferido contra o banco real (`SELECT artigo FROM chunk
WHERE rubrica ILIKE ...` / `WHERE texto ~* '...'`), não de memória — o
corpus muda de emenda em emenda e confiar em memória de treino sobre
article numbers é o mesmo erro que este módulo existe para evitar.

POR QUE (norma, artigo) E NÃO SÓ artigo: com CP + CF + ADCT no mesmo banco,
"art. 60" existe em mais de uma norma com conteúdo diferente. Checar só o
número da resposta certa por coincidência quando a norma errada também usa
aquele número — bug de avaliação mascarando bug de busca.

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

VERSAO = "avaliar_retrieval-v2"

CASOS = [
    # categoria, pergunta, norma esperada, artigo esperado
    ("dispositivo", "o que diz o art. 312 do código penal?", "CP", "312"),
    ("dispositivo", "artigo 121 do CP", "CP", "121"),
    ("dispositivo", "me explique o art. 157, o que ele diz", "CP", "157"),
    # art. 1-9 usam "º" no banco (LC 95/1998) — ninguém digita isso.
    # Ver Armadilhas de método no CLAUDE.md: bug real achado por este caso.
    ("dispositivo", "o que diz o art. 1 da constituição", "CF", "1º"),
    ("dispositivo", "art. 5 da CF", "CF", "5º"),
    ("dispositivo", "art. 1 do ADCT", "ADCT", "1º"),

    ("rubrica", "concussão", "CP", "316"),
    ("rubrica", "peculato", "CP", "312"),
    ("rubrica", "estelionato", "CP", "171"),
    ("rubrica", "prevaricação", "CP", "319"),

    ("hibrida", "funcionário público que exige vantagem indevida para si em razão do cargo", "CP", "316"),
    ("hibrida", "subtrair para si coisa alheia móvel mediante grave ameaça ou violência à pessoa", "CP", "157"),
    ("hibrida", "obter vantagem ilícita em prejuízo alheio induzindo alguém em erro mediante ardil", "CP", "171"),
    ("hibrida", "servidor público que se apropria de dinheiro que tem posse em razão do cargo", "CP", "312"),
    ("hibrida", "funcionário público que retarda ato de ofício para satisfazer interesse pessoal", "CP", "319"),
    ("hibrida", "matar alguém por motivo torpe mediante paga ou promessa de recompensa", "CP", "121"),
    ("hibrida", "ofender a dignidade de alguém com xingamento", "CP", "140"),
    ("hibrida", "imputar a alguém, sabendo falso, fato definido como crime", "CP", "138"),
    ("hibrida", "direitos sociais dos trabalhadores urbanos e rurais", "CF", "7º"),
    ("hibrida", "direito de reunião pacífica, sem armas, em locais abertos ao público", "CF", "5º"),
    ("hibrida", "emenda constitucional tendente a abolir cláusula pétrea não pode ser deliberada", "CF", "60"),
    ("hibrida", "plebiscito sobre a forma de governo, república ou monarquia", "ADCT", "2º"),
]


def refs_de(chunks):
    return [(c.get("norma"), c.get("artigo")) for c in chunks]


def main(n: int = 6):
    acertos_top1 = 0
    acertos_topn = 0
    por_categoria = {}

    print(f"{'cat':10s} {'esperado':14s} {'achou@1':8s} {'pos':4s} {'pergunta'}")
    for cat, pergunta, norma, artigo in CASOS:
        esperado = (norma, artigo)
        chunks = retrieval.buscar(pergunta, n=n)
        refs = refs_de(chunks)
        pos = refs.index(esperado) + 1 if esperado in refs else None
        top1 = bool(refs) and refs[0] == esperado

        acertos_top1 += int(top1)
        acertos_topn += int(pos is not None)
        c = por_categoria.setdefault(cat, {"top1": 0, "topn": 0, "total": 0})
        c["total"] += 1
        c["top1"] += int(top1)
        c["topn"] += int(pos is not None)

        marca = "✓" if top1 else ("~" if pos else "✗")
        rotulo = f"{norma} {artigo}"
        print(f"{cat:10s} {rotulo:14s} {marca:8s} {str(pos):4s} {pergunta[:55]}")
        if pos is None:
            print(f"           -> devolveu: {refs}")

    total = len(CASOS)
    print(f"\n{'='*70}")
    print(f"top1 (primeiro resultado é o certo): {acertos_top1}/{total} "
          f"({100*acertos_top1/total:.0f}%)")
    print(f"top{n} (certo aparece entre os {n}):      {acertos_topn}/{total} "
          f"({100*acertos_topn/total:.0f}%)")
    print()
    for cat, c in por_categoria.items():
        print(f"  {cat:10s} top1 {c['top1']}/{c['total']}  top{n} {c['topn']}/{c['total']}")


if __name__ == "__main__":
    main()
