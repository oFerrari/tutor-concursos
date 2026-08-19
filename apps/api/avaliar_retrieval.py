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

Quatro categorias, precisão esperada em ordem decrescente (as três primeiras
seguem a ordem de prioridade que `retrieval.buscar()` usa):
  dispositivo — citação exata ("art. 312"). Deve ser ~100%: é busca por
                metadado, não há ambiguidade possível.
  rubrica     — nome do crime ("concussão"). Deve ser ~100% pelo mesmo motivo.
  hibrida     — pergunta conceitual, sem citar artigo nem nome do crime.
                Aqui SIM cabe imprecisão de rank — o objetivo realista é
                top-N alto (o artigo aparece no contexto que o LLM vê), não
                top-1 perfeito.
  administrativo — a categoria que nasceu de uma FALHA REAL observada em uso,
                não de hipótese: o tutor perguntado sobre "administração
                direta e indireta" respondeu sem nunca ver o art. 37 da CF,
                que é o caput do assunto. Ver o comentário no bloco dos casos.

MEDIDA DE 14/08/2026, acervo de 2433 chunks (CP, CF, ADCT, livro de emendas,
CPP, Lei 8.112) — a linha de base contra a qual comparar qualquer mexida em
retrieval.py/embeddings.py:

    top1  21/32 (66%)      top6  30/32 (94%)
    dispositivo    top1 5/6    top6 6/6
    rubrica        top1 4/4    top6 4/4
    hibrida        top1 7/12   top6 10/12
    administrativo top1 5/10   top6 10/10

COMO ESTE NÚMERO SE MOVEU, na ordem em que aconteceu:

  91% (20/22)  antes dos casos de administrativo existirem.
  88% (28/32)  ao acrescentá-los. A busca não piorou — a MÉTRICA ficou
               honesta: os dois zeros novos já falhavam, só não havia caso
               que os apontasse. Métrica que só mede o que já funciona não
               arbitra nada ("medir ausência não é medir defeito").
  88% (28/32)  depois de PESO_HISTORICO = 0.5. Zero mudança no número, e
               ainda assim valeu: o livro de emendas deixou de ocupar 4 das
               6 vagas de "princípios da administração pública" (uma delas
               uma página de legenda de símbolos). Contexto melhor com a
               mesma pontuação — por isso a métrica sozinha não decide tudo.
  94% (30/32)  depois de PESO_LEXICAL = 1.5. Os DOIS casos do art. 37 da CF
               passaram a entrar no top-6. Ver o comentário em retrieval.py:
               chunk de 13k caracteres dilui o embedding, o braço lexical
               casa a frase exata, e pesá-lo mais corrige o viés na fusão.

Os dois top6 que continuam perdidos são CP 312 (peculato) e CP 140 (injúria)
— concorrência de conteúdo com a Lei 8.112 e o CPP, já documentada no
CLAUDE.md e não endereçada aqui.

CUIDADO AO AJUSTAR PESO CONTRA ESTE GABARITO: são 32 casos. 1.5 foi
escolhido por ser o MENOR valor que corrige (2, 3 e 5 não melhoram nada
além dele); número escolhido por maximizar a nota num gabarito pequeno é
ajuste ao gabarito, não à busca.
"""
from core import retrieval

VERSAO = "avaliar_retrieval-v3"

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

    # ------------------------------------------------ Direito Administrativo
    # Categoria própria porque o defeito que ela mede é diferente do resto:
    # a matéria de prova "Direito Administrativo" mora em DOIS lugares do
    # acervo — a Lei 8.112 (rotulada assim) e o Capítulo VII da CF (rotulado
    # "Direito Constitucional", porque a norma é a Constituição). O aluno
    # pergunta pela matéria; o acervo está organizado por norma.
    #
    # E os quatro primeiros casos batem TODOS no art. 37 da CF, que tem
    # 13.059 caracteres — dez vezes a média do acervo (1.245). É o teste de
    # esforço da decisão "chunk = artigo": ela está certa para o artigo
    # típico e é justamente nos artigos-monstro (37 e 5º da CF) que o
    # embedding médio dilui o assunto. Sem estes casos no gabarito, "a busca
    # está em 91%" continuaria verdadeiro e continuaria escondendo isto.
    ("administrativo", "administração direta e indireta", "CF", "37"),
    ("administrativo", "princípios da administração pública", "CF", "37"),
    ("administrativo", "investidura em cargo público depende de aprovação em concurso", "CF", "37"),
    ("administrativo", "é vedada a acumulação remunerada de cargos públicos", "CF", "37"),
    ("administrativo", "servidor nomeado adquire estabilidade após três anos de exercício", "CF", "41"),
    ("administrativo", "formas de provimento de cargo público", "L8112", "8o"),
    ("administrativo", "posse do servidor e prazo para entrar em exercício", "L8112", "13"),
    ("administrativo", "servidor nomeado fica sujeito a estágio probatório", "L8112", "20"),
    ("administrativo", "vencimento é a retribuição pecuniária pelo exercício do cargo", "L8112", "40"),
    ("administrativo", "licença ao servidor para tratamento de saúde com perícia médica", "L8112", "202"),
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
