#!/usr/bin/env python3
"""
Converte o HTML compilado do Planalto pra texto puro, pronto pro pipeline
de ingestão (ver corpus/README.md, passo 2 — "extraia o texto puro").

    python corpus/html_para_texto.py corpus/Del3689Compilado.html corpus/cpp.txt \
        --cortar-em "Rio de Janeiro, em 3 de outubro de 1941"

Não é um extrator geral de HTML — só o suficiente pro formato específico
do Planalto (FrontPage antigo: tabela de cabeçalho, <font>, parágrafo por
<p>, <br> solto). Lido em cp1252, não utf-8: é o que o <meta charset> da
página declara — ler como utf-8 corrompe todo acento (achado testando:
"Presidência" virava "Presidncia").

--cortar-em é OBRIGATÓRIO, não adivinhado: cada lei tem uma assinatura/
aviso/eventual anexo diferente depois do último artigo de verdade (mesma
lição do corpus/README.md, "corte pelo MARCADOR, não por posição no
arquivo"). Achado convertendo a Lei 8.112: o HTML compilado inclui, depois
da assinatura real (Brasília, 11/12/1990, Fernando Collor), um SEGUNDO
bloco — "partes vetadas mantidas pelo Congresso" — que reintroduz "Art. 87",
"Art. 250" etc. dentro de um <blockquote>. Sem cortar antes disso,
`chunk_lei()` (core/chunking.py) leria esses números de novo como
artigos NOVOS, colidindo com os originais — exatamente o que
`taxa_colisao_artigo()` existe para detectar, mas é melhor não gerar o
lixo do que confiar só no alarme depois.
"""
import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path

VERSAO = "html_para_texto-v1"

# Tags que abrem uma quebra de linha própria — sem isso o texto de células/
# parágrafos diferentes cola numa linha só, e normalizar_lei() (chunking.py)
# perde a fronteira entre rubrica e artigo, ou entre artigos.
TAGS_QUEBRA = {"p", "br", "tr", "div", "li", "table", "h1", "h2", "h3", "h4", "title"}

# <strike>/<s>/<del>: Planalto usa tachado pra mostrar a REDAÇÃO REVOGADA de
# artigo emendado, ao lado da redação vigente com o MESMO número de artigo.
# Achado convertendo a Lei 8.112: sem descartar o conteúdo, RE_ARTIGO
# (core/chunking.py) casava os dois — 23,9% de colisão de (norma, artigo),
# muito acima do LIMIAR_COLISAO de ingest.py/reingest.py (5%). Não é o
# mesmo caso do `documento.tipo = 'historico'` (aquele é pra um LIVRO
# inteiro de histórico de emendas); aqui a redação revogada é só descartada
# da ingestão como lei vigente — mesmo princípio já documentado no
# CLAUDE.md: "não arrisca art. X devolver a versão REVOGADA em vez da vigente".
TAGS_IGNORAR_CONTEUDO = {"script", "style", "strike", "s", "del"}


def _tem_tachado(attrs) -> bool:
    """
    Segundo mecanismo de tachado do mesmo achado acima: parte da Lei 8.112
    marca redação revogada com `<span style="text-decoration:line-through">`
    em vez da tag <strike> — mesma colisão de artigo se não for descartado
    também, só que por atributo CSS em vez de nome de tag.
    """
    for nome, valor in attrs:
        if nome == "style" and valor and "line-through" in valor.replace(" ", "").lower():
            return True
    return False


class _ExtraiTexto(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        # Pilha (tag, ignorar) em vez de um contador simples: tachado por
        # CSS pode estar em QUALQUER tag (span, font, p), não só nas de
        # TAGS_IGNORAR_CONTEUDO — um contador único não saberia dizer se o
        # fechamento corrente corresponde à abertura que ligou o "ignorar".
        self._pilha: list[tuple[str, bool]] = []

    def _ignorando(self) -> bool:
        return any(ignorar for _, ignorar in self._pilha)

    def handle_starttag(self, tag, attrs):
        ignorar = tag in TAGS_IGNORAR_CONTEUDO or _tem_tachado(attrs)
        self._pilha.append((tag, ignorar))
        if tag in TAGS_QUEBRA and not self._ignorando():
            self.partes.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in TAGS_QUEBRA and not self._ignorando():
            self.partes.append("\n")

    def handle_endtag(self, tag):
        # HTML do FrontPage não fecha tudo perfeitamente — procura de trás
        # pra frente pela tag que abriu e descarta ela e o que sobrou acima
        # (recuperação tolerante, não um parser XML estrito).
        for i in range(len(self._pilha) - 1, -1, -1):
            if self._pilha[i][0] == tag:
                del self._pilha[i:]
                break
        if tag in TAGS_QUEBRA and not self._ignorando():
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._ignorando():
            self.partes.append(data)

    def texto(self) -> str:
        # \xa0 (&nbsp;, muito usado pra indentar no HTML do Planalto) não é
        # espaço "normal" pra todo consumidor de string — normaliza pro
        # espaço comum antes de qualquer regex de chunking ver isto.
        return "".join(self.partes).replace("\xa0", " ")


def converter(caminho_html: Path) -> str:
    bruto = caminho_html.read_text(encoding="cp1252", errors="replace")
    p = _ExtraiTexto()
    p.feed(bruto)
    return p.texto()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--cortar-em", required=True,
                    help="tudo a partir desta string (inclusive) é descartado — "
                         "assinatura/aviso/anexo variam por lei, ver o docstring deste módulo")
    a = ap.parse_args()

    texto = converter(a.entrada)
    pos = texto.find(a.cortar_em)
    if pos == -1:
        print(f"AVISO: marcador {a.cortar_em!r} não encontrado — nada foi cortado. "
              f"Confira {a.saida} na mão antes de ingerir.", file=sys.stderr)
    else:
        texto = texto[:pos]

    a.saida.write_text(texto, encoding="utf-8")
    print(f"{a.entrada} -> {a.saida}: {len(texto)} caracteres")
    return 0


if __name__ == "__main__":
    sys.exit(main())
