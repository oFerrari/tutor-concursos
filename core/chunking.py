"""
Divisão do material em chunks.

Lei seca e material didático pedem estratégias diferentes:

- Lei: quebrar por dispositivo (Art., §, inciso) e guardar o identificador.
  Um artigo é uma unidade semântica completa; cortá-lo por contagem de
  caracteres destrói exatamente a informação que o estudante procura.
- Aula/resumo: janela deslizante com sobreposição, respeitando parágrafos.
"""
import re

RE_ARTIGO = re.compile(r"(?im)^\s*Art\.?\s*(\d+[\-\wºo]*)")
RE_PARAGRAFO = re.compile(r"(?im)^\s*(?:§\s*(\d+[\wºo]*)|Par[áa]grafo\s+[úu]nico)")
RE_INCISO = re.compile(r"(?im)^\s*([IVXLCDM]+)\s*[-–—)]")


def chunk_lei(texto: str, norma: str) -> list[dict]:
    """Um chunk por artigo, com parágrafos e incisos anexados ao artigo pai."""
    marcas = list(RE_ARTIGO.finditer(texto))
    if not marcas:
        return chunk_generico(texto)

    saida = []
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        corpo = texto[m.start():fim].strip()
        if len(corpo) < 20:
            continue
        par = RE_PARAGRAFO.search(corpo)
        inc = RE_INCISO.search(corpo)
        saida.append({
            "texto": corpo,
            "norma": norma,
            "artigo": m.group(1),
            "paragrafo": (par.group(1) if par and par.group(1) else ("unico" if par else None)),
            "inciso": inc.group(1) if inc else None,
        })
    return saida


def chunk_generico(texto: str, alvo: int = 1100, sobreposicao: int = 150) -> list[dict]:
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    chunks, atual = [], ""
    for p in paragrafos:
        if len(atual) + len(p) + 2 <= alvo:
            atual = f"{atual}\n\n{p}" if atual else p
        else:
            if atual:
                chunks.append(atual)
            atual = (atual[-sobreposicao:] + "\n\n" + p) if atual else p
    if atual:
        chunks.append(atual)
    return [{"texto": c, "norma": None, "artigo": None, "paragrafo": None, "inciso": None}
            for c in chunks if len(c) > 80]
