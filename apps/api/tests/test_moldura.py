"""A moldura da página (cabeçalho, rodapé, marca d'água) não é conteúdo.

Medido em 23/09/2026 numa apostila de curso real, de 110 páginas: a linha com
nome e CPF do comprador e o endereço do curso estavam em 165 dos 219 trechos.
Isso ia pro embedding, pro prompt e pro enunciado das questões geradas, e o
número de página impresso no cabeçalho virava "conteúdo" do trecho.

A regra é por FREQUÊNCIA, nunca por padrão de um curso: linha que se repete em
metade das páginas, com os dígitos trocados por "#" pra que "Página 3 de 110" e
"Página 4 de 110" sejam a mesma linha. Por isso os textos daqui são inventados.
"""
from core import chunking, material

VERSAO = "test-moldura-v1"

CABECALHO = "Curso Fictício Preparatório · Aluno Fulano de Tal · 00000000000"
ASSUNTOS = ["posse", "detenção", "usucapião", "servidão", "enfiteuse", "superfície",
            "penhor", "hipoteca", "anticrese", "usufruto", "habitação", "laje"]
CORPO = ("O instituto da {n} tem natureza jurídica própria e se distingue dos "
         "demais pela forma como opera no caso concreto. ") * 4


def _paginas(n: int) -> list[str]:
    return [f"{CABECALHO}\n{CORPO.format(n=ASSUNTOS[i - 1])}\n\n"
            f"Outro parágrafo, sobre {ASSUNTOS[i - 1]}, que só esta página tem.\n"
            f"Página {i} de {n}"
            for i in range(1, n + 1)]


def test_cabecalho_e_numero_de_pagina_saem_de_todas_as_paginas():
    limpas = chunking.sem_moldura(_paginas(8))

    assert all(CABECALHO not in p for p in limpas)
    assert all("de 8" not in p for p in limpas)
    # O conteúdo fica: cada página fala de um assunto seu.
    assert all(f"instituto da {a}" in p for a, p in zip(ASSUNTOS, limpas))
    assert "Outro parágrafo, sobre enfiteuse" in limpas[4]


def test_linha_que_so_muda_o_numero_em_toda_pagina_e_moldura():
    """O custo aceito da regra: "Seção 3 · revisão 9" repetido com outro número
    em metade das páginas é tratado como moldura. Conteúdo de verdade não se
    repete assim; rodapé numerado, sim."""
    paginas = [f"Conteúdo próprio sobre {a}.\nSeção {i} · revisão {i * 3}"
               for i, a in enumerate(ASSUNTOS[:6], 1)]

    assert all("Seção" not in p for p in chunking.sem_moldura(paginas))


def test_documento_curto_nao_perde_nada():
    """Em duas páginas, "repete em metade" é qualquer linha que apareça duas
    vezes — um título de seção repetido sumiria."""
    paginas = _paginas(2)
    assert chunking.sem_moldura(paginas) == paginas


def test_linha_que_repete_em_poucas_paginas_e_conteudo():
    paginas = _paginas(10)
    paginas[2] += "\nPrincípio da legalidade"
    paginas[7] += "\nPrincípio da legalidade"

    limpas = chunking.sem_moldura(paginas)

    assert "Princípio da legalidade" in limpas[2] and "Princípio da legalidade" in limpas[7]


def test_trecho_sabe_a_pagina_em_que_comeca():
    paginas = [f"Assunto da página {i}. " * 60 for i in range(1, 5)]

    trechos = chunking.chunk_paginado(paginas, alvo=400, sobreposicao=50)

    assert [t["pagina"] for t in trechos] == sorted(t["pagina"] for t in trechos)
    for t in trechos:
        assert f"Assunto da página {t['pagina']}." in t["texto"]
    assert {t["pagina"] for t in trechos} == {1, 2, 3, 4}


def test_texto_sem_pagina_segue_dividindo_igual():
    """TXT, DOCX e HTML não têm página: a divisão é a mesma de antes, com
    `pagina` vazia em vez de inventada."""
    texto = "\n\n".join(f"Parágrafo {i}. " * 30 for i in range(6))

    trechos = chunking.chunk_generico(texto, alvo=400, sobreposicao=50)

    assert len(trechos) > 1
    assert all(t["pagina"] is None for t in trechos)
    assert "Parágrafo 0." in trechos[0]["texto"] and "Parágrafo 5." in trechos[-1]["texto"]


def test_material_dividido_por_pagina_nao_carrega_a_moldura():
    paginas = chunking.sem_moldura(_paginas(12))

    trechos = material._dividir("\n\n".join(paginas), "apostila.pdf", paginas)

    assert trechos and all(CABECALHO not in t["texto"] for t in trechos)
    assert all(t["pagina"] for t in trechos)


def test_palavra_solta_de_texto_justificado_nao_e_moldura():
    """Medido em 23/09/2026: em 4 de 17 apostilas o pypdf extrai o texto
    justificado com uma palavra por linha, e "de", "que", "a" aparecem em mais
    da metade das páginas. Pela frequência sozinha, sairiam do conteúdo; o que
    as separa da moldura é a posição — moldura mora na borda."""
    miolo = "\n".join(["texto", "corrido"] * 10 + ["de"] + ["mais", "texto"] * 10)
    paginas = [f"{CABECALHO}\nIntrodução sobre {a}\n{miolo}\nFim da página sobre {a}\nPágina {i}"
               for i, a in enumerate(ASSUNTOS, 1)]

    limpas = chunking.sem_moldura(paginas)

    assert all("\nde\n" in p for p in limpas)
    assert all(CABECALHO not in p and "Página" not in p for p in limpas)


def test_numero_solto_no_meio_da_pagina_fica():
    """O "12" do rodapé e o "12" da célula de tabela viram a mesma linha
    comparável ("#"); só o da borda é número de página."""
    tabela = "\n".join(["Prazo em dias"] + ["texto da tabela"] * 9 + ["15"] + ["linha"] * 9)
    paginas = [f"Sobre {a}\n{tabela}\nConclusão sobre {a}\n{i}"
               for i, a in enumerate(ASSUNTOS, 1)]

    limpas = chunking.sem_moldura(paginas)

    assert all("\n15\n" in p for p in limpas)
    assert all(not p.rstrip().endswith(("\n1", "\n2", "\n3")) for p in limpas)
