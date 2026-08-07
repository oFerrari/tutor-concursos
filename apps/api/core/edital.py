"""
Edital — extrai data da prova e conteúdo programático de um PDF de edital,
para `scheduler.meta()` usar dado real em vez de exigir digitar a data
na mão toda vez.

MELHOR ESFORÇO, NÃO CONTRATO. Layout de edital varia por banca (FGV,
Cebraspe, FCC, ...) — o que segue funciona para o padrão mais comum
(conteúdo programático como "N. DISCIPLINA:" seguido de subitens numerados
"N.N", "N.N.N"), não para todos. Por isso `ingerir()` devolve os
candidatos a data com pontuação, não só "a resposta" — mesmo espírito de
`diagnostico.py`: reportar para o operador conferir, não decidir calado.

DUAS APROXIMAÇÕES DECLARADAS, não escondidas:

1. Sem separação por CARGO. Concurso com mais de um cargo (comum) repete
   disciplinas com conteúdo próprio por cargo — "DIREITO CONSTITUCIONAL"
   do Delegado e do Agente, por exemplo. Este módulo não distingue: os
   tópicos de nome de disciplina igual se somam num grupo só. Infla um
   pouco a contagem, não perde tópico.

2. "Cobertura por tópico" é estimada por DISCIPLINA, não por tópico
   individual. Não há vínculo direto questão→tópico no schema (exigiria
   marcar cada questão gerada com o tópico de origem). A aproximação:
   cobertura_pct da disciplina inteira (já existente em
   v_desempenho_disciplina) se aplica IGUALMENTE a todos os tópicos dela —
   assume dificuldade uniforme, o que não é verdade, mas é a melhor
   estimativa sem construir o vínculo fino agora.
"""
import re
from datetime import date
from pathlib import Path

from . import db

VERSAO = "edital-v2"

MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5,
         "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
         "novembro": 11, "dezembro": 12}

# "no dia D de MÊS de AAAA" — distingue de citação legal ("Lei nº X, DE D
# de MÊS de AAAA"), que não tem a palavra "dia" antes do número.
RE_DATA_EVENTO = re.compile(
    r"\bdia\s+(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\s+de\s+(20\d{2})", re.I)

# "1. DIREITO PENAL:" — número, ponto, título em caixa alta, dois pontos.
# SEM âncora de início de linha: _normalizar() já colapsou toda quebra de
# linha em espaço antes desta regex rodar, então "^|\n" nunca bate a não
# ser bem no início do texto — o padrão numérico+caixa-alta já é
# suficientemente distintivo sem precisar de posição.
RE_DISCIPLINA = re.compile(r"\b(\d{1,2})\.\s+([A-ZÀ-Ü][A-ZÀ-Ü \-/]{2,60}):")

# "1.1", "1.1.1" etc. seguido de texto iniciando em maiúscula.
RE_SUBITEM = re.compile(r"\b(\d+(?:\.\d+){1,3})\s+(?=[A-ZÀ-Ü])")


def _normalizar(texto: str) -> str:
    """PDF extraído de docx costuma vir com espaço/quebra de linha entre
    quase toda palavra — colapsar em espaço simples antes de qualquer regex
    que dependa de frase contígua."""
    return re.sub(r"\s+", " ", texto)


def candidatos_data_prova(texto: str, janela: int = 250) -> list[dict]:
    """
    Lista de datas candidatas a "dia da prova", ordenadas por pontuação de
    proximidade a "prova objetiva"/"realizad*". Devolve TODOS os
    candidatos, não decide sozinho qual é o certo — layout varia por
    banca, e a primeira posição pode estar errada num edital diferente
    deste que serviu de referência.
    """
    flat = _normalizar(texto)
    candidatos = []
    fim_anterior = 0
    for m in RE_DATA_EVENTO.finditer(flat):
        # A janela nunca cruza o candidato anterior — sem isso, duas datas
        # próximas (comum: "Prova Objetiva dia X... Prova Discursiva dia Y"
        # em sequência) "emprestam" pontuação uma da outra, e a segunda
        # data rouba o crédito de "prova objetiva" que pertence à primeira.
        ini = max(0, m.start() - janela, fim_anterior)
        contexto = flat[ini:m.start() + 40]
        pontos = (contexto.lower().count("prova objetiva") * 3
                  + contexto.lower().count("realizad"))
        fim_anterior = m.end()
        try:
            d = date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            continue
        candidatos.append({"data": d, "pontuacao": pontos,
                           "contexto": contexto[-140:].strip()})
    candidatos.sort(key=lambda c: -c["pontuacao"])
    return candidatos


def extrair_topicos(texto: str) -> list[dict]:
    """
    [{"disciplina": ..., "ordem": N, "texto": "1.1.1 Princípios..."}]

    Funciona para o padrão "N. DISCIPLINA:" + subitens "N.N"/"N.N.N".
    Ver limitações (1) e (2) no docstring do módulo.
    """
    flat = _normalizar(texto)
    marcas = list(RE_DISCIPLINA.finditer(flat))
    topicos = []
    for i, m in enumerate(marcas):
        disciplina = re.sub(r"\s+", " ", m.group(2)).strip().title()
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else min(len(flat), m.end() + 8000)
        bloco = flat[m.end():fim]
        subitens = list(RE_SUBITEM.finditer(bloco))
        for j, s in enumerate(subitens):
            fim_s = subitens[j + 1].start() if j + 1 < len(subitens) else len(bloco)
            corpo = bloco[s.start():fim_s].strip()
            if corpo:
                topicos.append({"disciplina": disciplina, "ordem": len(topicos), "texto": corpo})
    return topicos


# --------------------------------------------------------------- borda (db)
def ingerir(usuario_id: int, caminho, titulo: str | None = None, orgao: str | None = None,
            banca: str | None = None) -> dict:
    """Cada usuário tem seu próprio edital — dois concurseiros estudando o
    mesmo acervo compartilhado podem visar provas diferentes, em datas
    diferentes."""
    from pypdf import PdfReader
    caminho = Path(caminho)
    reader = PdfReader(str(caminho))
    texto = "\n\n".join((p.extract_text() or "") for p in reader.pages)

    candidatos = candidatos_data_prova(texto)
    data_prova = candidatos[0]["data"] if candidatos else None
    topicos = extrair_topicos(texto)

    eid = db.exec1(
        """INSERT INTO edital (usuario_id, titulo, orgao, banca, data_prova, arquivo)
           VALUES (%(u)s, %(t)s, %(o)s, %(b)s, %(d)s, %(a)s) RETURNING id""",
        {"u": usuario_id, "t": titulo or caminho.stem, "o": orgao, "b": banca,
         "d": data_prova, "a": str(caminho)},
    )["id"]
    for t in topicos:
        db.query(
            """INSERT INTO topico (edital_id, disciplina, ordem, texto)
               VALUES (%(e)s, %(d)s, %(o)s, %(tx)s)""",
            {"e": eid, "d": t["disciplina"], "o": t["ordem"], "tx": t["texto"]},
        )

    return {
        "edital_id": eid,
        "data_prova": data_prova,
        "candidatos_data": candidatos[:5],
        "topicos": len(topicos),
        "disciplinas": sorted({t["disciplina"] for t in topicos}),
    }


def mais_recente(usuario_id: int) -> dict | None:
    return db.exec1(
        "SELECT id, titulo, data_prova FROM edital WHERE usuario_id = %(u)s "
        "ORDER BY criado_em DESC LIMIT 1",
        {"u": usuario_id},
    )


def cobertura(edital_id: int, usuario_id: int) -> list[dict]:
    """
    Por disciplina do edital: quantos tópicos existem e a cobertura DESTE
    usuário (aproximação 2 do docstring do módulo — por disciplina, não por
    tópico individual). `caixa` mudou de tabela (agora vive em `progresso`,
    por usuário) — por isso o LEFT JOIN em vez do antigo WHERE direto em
    questao.
    """
    topicos = db.query(
        "SELECT disciplina, count(*) AS n FROM topico WHERE edital_id = %(e)s GROUP BY disciplina",
        {"e": edital_id},
    )
    resultado = []
    for t in topicos:
        r = db.exec1(
            """SELECT count(DISTINCT q.id) AS total,
                      count(DISTINCT q.id) FILTER (WHERE p.caixa >= 3) AS dominadas
               FROM questao q
               LEFT JOIN progresso p ON p.questao_id = q.id AND p.usuario_id = %(u)s
               WHERE q.disciplina ILIKE %(d)s""",
            {"d": f"%{t['disciplina']}%", "u": usuario_id},
        ) or {"total": 0, "dominadas": 0}
        cobertura_pct = 100 * r["dominadas"] / r["total"] if r["total"] else 0.0
        resultado.append({
            "disciplina": t["disciplina"],
            "topicos_no_edital": t["n"],
            "questoes_disciplina": r["total"],
            "cobertura_pct": round(cobertura_pct, 1),
            "topicos_pendentes_estimado": round(t["n"] * (1 - cobertura_pct / 100)),
        })
    return resultado


def probabilidade_fechamento(edital_id: int, usuario_id: int, data_prova: date | None = None) -> dict:
    """
    APROXIMAÇÃO por extrapolação linear de ritmo — não é um modelo
    estatístico (não modela variância nem esquecimento; mesma limitação já
    documentada em simular.py). "Se o ritmo dos últimos dias continuar,
    que fração da velocidade necessária isso representa" é a pergunta que
    este número responde — não "qual a chance real de passar".

    `data_prova` opcional SOBRESCREVE a do banco — quando o operador corrige
    a data manualmente (extração automática errou, ver candidatos_data_prova),
    esse número tem que refletir a correção, não a data original errada.
    """
    if data_prova is None:
        ed = db.exec1("SELECT data_prova FROM edital WHERE id = %(e)s", {"e": edital_id})
        data_prova = ed["data_prova"] if ed else None
    if not data_prova:
        return {"erro": "edital sem data_prova reconhecida — sem data não dá pra estimar ritmo"}

    dias_restantes = max((data_prova - date.today()).days, 0)
    cob = cobertura(edital_id, usuario_id)
    topicos_totais = sum(c["topicos_no_edital"] for c in cob)
    topicos_pendentes = sum(c["topicos_pendentes_estimado"] for c in cob)
    topicos_cobertos = topicos_totais - topicos_pendentes

    primeira = db.exec1("SELECT min(criada_em)::date AS d FROM tentativa WHERE usuario_id = %(u)s",
                        {"u": usuario_id})
    dias_estudando = max((date.today() - primeira["d"]).days, 1) if primeira and primeira["d"] else 0

    ritmo_atual = topicos_cobertos / dias_estudando if dias_estudando else 0.0
    ritmo_necessario = topicos_pendentes / dias_restantes if dias_restantes else None

    if topicos_pendentes <= 0:
        probabilidade = 100.0
    elif dias_restantes <= 0 or ritmo_atual <= 0:
        probabilidade = 0.0
    else:
        probabilidade = min(100.0, round(100 * ritmo_atual / ritmo_necessario, 1))

    return {
        "dias_restantes": dias_restantes,
        "topicos_totais": topicos_totais,
        "topicos_pendentes_estimado": topicos_pendentes,
        "ritmo_atual_topicos_dia": round(ritmo_atual, 2),
        "ritmo_necessario_topicos_dia": round(ritmo_necessario, 2) if ritmo_necessario is not None else None,
        "probabilidade_fechamento_pct": probabilidade,
    }
