"""
Gerar questão A PARTIR DO ACERVO, sob demanda — e gravar com proveniência.

POR QUE ESTE MÓDULO EXISTE
--------------------------
Até aqui a fila só sabia servir o que já estava na tabela `questao`, e essa
tabela só crescia por `gerar.py`, rodado à mão. O efeito é geral, não de uma
matéria: QUALQUER mesa cujo edital cobre disciplina sem questão gerada abre
vazia — a de TI, a bancária, a fiscal, e também a de Direito Administrativo,
que tem 245 chunks da Lei 8.112 no acervo e tinha zero questão. O material
estava lá; faltava alguém transformá-lo em pergunta.

Como o modelo já sabe gerar questão a partir de trecho de lei (é o que
`socratic.gerar_questoes` faz desde o começo), o vazio era de encanamento,
não de capacidade.

O QUE ESTE MÓDULO **NÃO** RELAXA
--------------------------------
A invariante de proveniência. `salvar()` é a mesma regra que `gerar.py`
usava: questão cujo `artigo` não está no lote enviado é DESCARTADA, nunca
gravada — cobertura que mente é pior que cobertura inexistente. Gerar no
meio de uma sessão não é motivo pra afrouxar isso; é motivo pra reusar a
mesma função em vez de escrever uma segunda, mais permissiva, no caminho
novo (que é como as duas versões de uma regra passam a divergir).

Duas exclusões na hora de escolher o trecho, pelo mesmo motivo:
  · `tipo = 'historico'` — chunk por janela de parágrafo, sem (norma,
    artigo). Não há proveniência possível, e pior: pode conter redação
    REVOGADA. Questão gerada dali cobraria lei que não vale mais.
  · texto curto (`MIN_TEXTO`) e artigo revogado — não há o que cobrar.

A QUESTÃO GERADA ENTRA NO ACERVO COMPARTILHADO
----------------------------------------------
Não é rascunho de sessão: é gravada em `questao`, sem `usuario_id`, como
qualquer outra (migração 008). Gerar custa cota de LLM; negar
reaproveitamento faria a próxima pessoa pagar a mesma pergunta de novo. E
só gravada ela entra em `progresso`/SM-2 — questão que existe só na tela é
questão que não volta pra revisão, ou seja, não é estudo espaçado.
"""
import json
import re

from . import db, llm, mesa, retrieval, socratic

VERSAO = "geracao-v2"

MIN_TEXTO = 140          # abaixo disso é stub, revogado ou remissão
MAX_POR_VEZ = 5          # teto por chamada: cota de LLM é o recurso escasso


class SemMaterial(Exception):
    """O acervo não tem trecho utilizável pro que foi pedido — diferente de
    'o modelo falhou'. Quem chama precisa distinguir pra dizer a verdade na
    tela: 'não temos material dessa matéria' e 'a IA não respondeu agora'
    pedem ações opostas do aluno."""


def _norm_artigo(a) -> str:
    """LC 95/1998: Art. 1º-9º levam ordinal, Art. 10+ não — e o modelo às
    vezes devolve sem. Mesma normalização de `retrieval.por_dispositivo()`
    e do antigo `gerar._norm_artigo`, pelo mesmo motivo: sem ela a questão
    é descartada por "proveniência não confere" mesmo estando certa."""
    return re.sub(r"[ºo]$", "", (a or "").strip())


# Colunas que `salvar()` precisa do chunk. `retrieval` não devolve
# `documento_id` (não interessa a quem só vai ler o texto), e a questão
# precisa dele — daí a releitura por id em vez de carregar tudo sempre.
CAMPOS_LOTE = """c.id, c.documento_id, c.texto, c.artigo, c.norma, c.rubrica,
                 c.secao, c.pagina, d.titulo, d.disciplina, d.tipo"""


def _lote_por_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    linhas = db.query(
        f"""SELECT {CAMPOS_LOTE} FROM chunk c JOIN documento d ON d.id = c.documento_id
             WHERE c.id = ANY(%(ids)s)""",
        {"ids": ids},
    )
    ordem = {cid: i for i, cid in enumerate(ids)}
    return sorted(linhas, key=lambda c: ordem.get(c["id"], 0))


def salvar(questoes: list[dict], lote: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Grava as questões cuja proveniência confere; devolve (salvas, descartes).

    `documento_id` e `disciplina` saem do CHUNK casado, não de parâmetro:
    um lote montado por busca pode atravessar normas (uma pergunta sobre
    "servidor público" traz CF e Lei 8.112 juntas), e herdar a disciplina de
    um documento escolhido de fora rotularia a questão errado — o mesmo
    rótulo que a mesa usa depois pra recortar a fila.
    """
    por_artigo = {_norm_artigo(c["artigo"]): c for c in lote if c["artigo"]}
    salvas, descartes = [], []
    for q in questoes:
        chunk = por_artigo.get(_norm_artigo(q.get("artigo")))
        if chunk is None:
            descartes.append(f"artigo {q.get('artigo')!r} não está no lote enviado")
            continue
        nova = db.exec1(
            """INSERT INTO questao (documento_id, disciplina, tema, enunciado,
                                    gabarito, dicas, fonte_chunks, tipo, gabarito_ce)
               VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s,
                       %(tipo)s, %(ce)s)
               RETURNING id, disciplina, tema, enunciado, gabarito, dicas,
                         tipo, gabarito_ce""",
            {"d": chunk["documento_id"], "disc": chunk["disciplina"], "t": q["tema"],
             "e": q["enunciado"], "g": q["gabarito"], "dic": json.dumps(q["dicas"]),
             "f": [chunk["id"]],
             # `.get` com default preserva o contrato antigo: quem chamar
             # `salvar` com dicionário sem `tipo` (código anterior à 012)
             # continua gravando discursiva, não quebra nem grava NULL.
             "tipo": q.get("tipo", "resposta_livre"), "ce": q.get("gabarito_ce")},
        )
        salvas.append(nova)
    return salvas, descartes


# Trecho utilizável: tem artigo (proveniência), não é histórico, não é stub
# nem revogado. `NOT EXISTS` prioriza o que ainda não virou questão — sem
# isso, gerar duas vezes seguidas na mesma mesa cobraria o mesmo artigo.
FILTRO_UTIL = """
      d.tipo <> 'historico'
  AND c.artigo IS NOT NULL
  AND length(c.texto) >= %(min)s
  AND c.texto NOT ILIKE '%%(revogad%%'
"""

SQL_POR_DISCIPLINA = f"""
SELECT c.id
  FROM chunk c JOIN documento d ON d.id = c.documento_id
 WHERE {FILTRO_UTIL}
   AND NOT EXISTS (SELECT 1 FROM questao q WHERE c.id = ANY(q.fonte_chunks))
   AND {mesa.filtro('d.disciplina')}
 ORDER BY random()
 LIMIT %(lim)s
"""


def _por_disciplina(disciplinas: list[str] | None, limite: int) -> list[int]:
    linhas = db.query(SQL_POR_DISCIPLINA,
                      {"disc": disciplinas, "min": MIN_TEXTO, "lim": limite})
    return [l["id"] for l in linhas]


def _por_tema(tema: str, limite: int) -> list[int]:
    """
    Usa a MESMA busca do tutor (`retrieval.buscar`), não uma consulta
    própria: o trecho que fundamenta a resposta na conversa tem que ser o
    trecho de que a questão é cobrada, senão o aluno recebe pergunta sobre
    algo que não foi o que ele acabou de ler.

    Depois filtra pelo que serve de fonte — a busca é otimizada pra explicar
    (histórico ajuda a explicar), a geração exige proveniência.
    """
    achados = retrieval.buscar(tema, n=12)
    if not achados:
        return []
    uteis = db.query(
        f"""SELECT c.id,
                   EXISTS (SELECT 1 FROM questao q WHERE c.id = ANY(q.fonte_chunks)) AS ja_tem
              FROM chunk c JOIN documento d ON d.id = c.documento_id
             WHERE c.id = ANY(%(ids)s) AND {FILTRO_UTIL}""",
        {"ids": [c["id"] for c in achados], "min": MIN_TEXTO},
    )
    # Preserva a ordem da busca (relevância), só empurrando pro fim o que já
    # virou questão — melhor cobrar de novo o artigo certo do que cobrar o
    # artigo errado só por ser inédito.
    ranking = {c["id"]: i for i, c in enumerate(achados)}
    ordenados = sorted(uteis, key=lambda r: (r["ja_tem"], ranking.get(r["id"], 99)))
    return [r["id"] for r in ordenados[:limite]]


BANCAS_CERTO_ERRADO = ("cebraspe", "cespe", "unb")


def tipo_da_banca(banca: str | None) -> str:
    """
    A banca decide o FORMATO do item, e a mesa já sabe qual é.

    Não é firula: treinar discursiva pra uma prova Cebraspe é treinar o
    exercício errado. O item C/E tem um vício próprio (marcar Certo sem ler
    a alteração de prazo ou de "poderá/deverá"), e só se treina esse vício
    respondendo nesse formato.

    Função pura e separada pra poder ser testada sem banco e pra o padrão
    ficar visível — banca desconhecida cai em discursiva, que é o
    comportamento de antes da 012.
    """
    b = (banca or "").strip().lower()
    return "certo_errado" if any(x in b for x in BANCAS_CERTO_ERRADO) else "resposta_livre"


def sob_demanda(disciplinas: list[str] | None = None, tema: str | None = None,
                quantidade: int = 3, tipo: str = "resposta_livre") -> dict:
    """
    Gera até `quantidade` questões e grava as que têm proveniência.

    `tema` (a conversa, ou o que o aluno pediu) manda quando vem; sem ele,
    sorteia trecho ainda descoberto dentro do recorte da mesa — que é o caso
    "minha fila está vazia, me dá o que estudar".

    UM ARTIGO POR QUESTÃO PEDIDA, a mesma lição de `gerar.py`: mandar 6
    artigos pra pedir 3 questões deixa 3 descobertos, que voltam no lote
    seguinte — contexto pago duas vezes sem ganho de cobertura.
    """
    quantidade = max(1, min(quantidade, MAX_POR_VEZ))
    ids = _por_tema(tema, quantidade) if tema else _por_disciplina(disciplinas, quantidade)
    if not ids and tema:
        # A busca por tema não achou trecho utilizável, mas a mesa pode ter
        # material — cair pro recorte é melhor que devolver vazio a quem
        # pediu questão. O que NÃO se faz é inventar sem fonte.
        ids = _por_disciplina(disciplinas, quantidade)
    if not ids:
        raise SemMaterial(
            "o acervo ainda não tem trecho de lei dessas disciplinas pra gerar questão"
        )

    lote = _lote_por_ids(ids)
    try:
        questoes = socratic.gerar_questoes(lote, len(lote), tipo)
    except llm.ErroLLM:
        raise
    salvas, descartes = salvar(questoes, lote)
    return {
        "questoes": salvas,
        "descartadas": len(descartes),
        "motivos": descartes,
        "fontes": [f"{c['norma'] or c['titulo']} art. {c['artigo']}" for c in lote],
    }
