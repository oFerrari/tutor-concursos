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

from . import assunto, db, llm, mesa, retrieval, socratic

VERSAO = "geracao-v14"

MIN_TEXTO = 140          # abaixo disso é stub, revogado ou remissão
MAX_POR_VEZ = 5          # teto por chamada: cota de LLM é o recurso escasso
# Quantos candidatos por questão pedida entram no pool de onde a novidade
# escolhe. 3 dá folga pra evitar repetir artigo sem sair do assunto.
POOL_POR_PEDIDO = 3


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
# `d.usuario_id` entra como `dono`: é ele que decide se a questão gerada é
# pública ou privada (026). Sai do CHUNK, não de parâmetro, pelo mesmo motivo
# que `documento_id` e `disciplina` já saíam — ver `salvar()`.
CAMPOS_LOTE = """c.id, c.documento_id, c.texto, c.artigo, c.norma, c.rubrica,
                 c.secao, c.pagina, d.titulo, d.disciplina, d.tipo, d.assunto,
                 d.usuario_id AS dono"""


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


def _chunk_do_trecho(q: dict, lote: list[dict]) -> dict | None:
    n = q.get("trecho")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(lote):
        return None
    return lote[n - 1]


def _casar(q: dict, lote: list[dict]) -> tuple[dict | None, str]:
    """`_achar` + a disciplina que a questão vai gravar.

    Documento sem disciplina (simulado de várias matérias, resumo solto) não
    pode virar `questao.disciplina` NULL — a coluna é NOT NULL e a mesa recorta
    a fila por ela. Trecho de simulado herda a matéria da questão de prova que
    está nele; sem matéria única, é descarte, nunca um rótulo inventado.
    Medido em 02/10/2026: "quero questões de juros simples" numa conta com
    simulado derrubou a rota com NotNullViolation.
    """
    chunk, motivo = _achar(q, lote)
    if chunk is None or chunk.get("disciplina"):
        return chunk, motivo
    from . import prova
    materias = prova.materias_dos_trechos([chunk["id"]]).get(chunk["id"], set())
    if len(materias) != 1:
        return None, f"trecho {chunk['id']} não tem disciplina"
    return {**chunk, "disciplina": next(iter(materias))}, ""


def _achar(q: dict, lote: list[dict]) -> tuple[dict | None, str]:
    """
    Acha o chunk de onde a questão saiu, ou diz por que ela é descarte.

    DUAS CHAVES, e a ORDEM É O TODO desta função:

    1. `trecho` apontando MATERIAL SEM ARTIGO manda, e manda inclusive sobre
       um `artigo` que o modelo tenha devolvido junto. Não é tolerância: é que
       naquele caso o `artigo` não é proveniência, é CONTEÚDO. Apostila cita
       lei — a aula de lesão corporal transcreve o art. 129 —, então o modelo
       preenche o campo com o artigo que leu DENTRO do excerto. Medido na
       primeira rodada real: 2 de 3 questões boas da apostila descartadas com
       "artigo '129' não está no lote enviado", sendo que o `trecho` apontava
       certo e o lote não tinha chunk de lei nenhum. O prompt já manda deixar
       o campo vazio nesse caso e o modelo preenche mesmo assim, que é a
       situação exata em que este projeto decide no código.

       Nada se perde: `salvar` não guarda `artigo` em coluna alguma. A
       proveniência gravada é `fonte_chunks`, e ela sai do chunk apontado.

    2. `artigo` — a chave de sempre, pra lei, com o rigor de sempre: artigo
       que não está no lote é DESCARTE. Cobertura que mente é pior que
       cobertura inexistente, e isso não muda por existir uma segunda chave.

    E o que a ordem NÃO permite: trecho apontando LEI sem citar o artigo é
    descarte (caso 3). Sem essa trava, o número seria o jeito de gravar
    questão de dispositivo sem dizer qual — o afrouxamento que este módulo
    existe pra não fazer, entrando pela porta lateral.
    """
    do_trecho = _chunk_do_trecho(q, lote)
    if do_trecho is not None and not do_trecho["artigo"]:
        return do_trecho, ""

    artigo = _norm_artigo(q.get("artigo"))
    if artigo:
        chunk = {_norm_artigo(c["artigo"]): c for c in lote if c["artigo"]}.get(artigo)
        if chunk is None:
            return None, f"artigo {q.get('artigo')!r} não está no lote enviado"
        return chunk, ""

    if do_trecho is not None:
        return None, (f"trecho {q['trecho']} é lei (art. {do_trecho['artigo']}) "
                      "e a questão não citou o artigo")
    return None, f"sem artigo e trecho {q.get('trecho')!r} fora do lote de {len(lote)}"


def salvar(questoes: list[dict], lote: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Grava as questões cuja proveniência confere; devolve (salvas, descartes).

    `documento_id`, `disciplina` e `usuario_id` saem do CHUNK casado, não de
    parâmetro: um lote montado por busca pode atravessar normas (uma pergunta
    sobre "servidor público" traz CF e Lei 8.112 juntas), e herdar a
    disciplina de um documento escolhido de fora rotularia a questão errado —
    o mesmo rótulo que a mesa usa depois pra recortar a fila.

    `usuario_id` pelo mesmo raciocínio, e com mais consequência: quem decide
    se a questão é pública ou privada (026) é o DOCUMENTO de onde ela saiu.
    Passar isso por parâmetro criaria a chamada que grava questão de apostila
    como pública por esquecimento — e o esquecimento aqui é vazamento de
    material pago pra dentro do acervo de todo mundo. Derivado do chunk, não
    existe a chamada errada.
    """
    salvas, descartes = [], []
    for q in questoes:
        chunk, motivo = _casar(q, lote)
        if chunk is None:
            descartes.append(motivo)
            continue
        tipo = q.get("tipo", "resposta_livre")
        existente = _ja_existe(q["enunciado"], chunk, tipo)
        if existente is not None:
            if existente["id"] in {s["id"] for s in salvas}:
                descartes.append(f"duplicata de q{existente['id']} na mesma leva")
            else:
                salvas.append(existente)
            continue
        nova = db.exec1(
            """INSERT INTO questao (documento_id, disciplina, tema, enunciado,
                                    gabarito, dicas, fonte_chunks, tipo, gabarito_ce,
                                    usuario_id)
               VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s,
                       %(tipo)s, %(ce)s, %(dono)s)
               RETURNING id, disciplina, tema, enunciado, gabarito, dicas,
                         tipo, gabarito_ce, usuario_id""",
            {"d": chunk["documento_id"], "disc": chunk["disciplina"], "t": q["tema"],
             "dono": chunk.get("dono"),
             "e": q["enunciado"], "g": q["gabarito"], "dic": json.dumps(q["dicas"]),
             "f": [chunk["id"]],
             # `.get` com default preserva o contrato antigo: quem chamar
             # `salvar` com dicionário sem `tipo` (código anterior à 012)
             # continua gravando discursiva, não quebra nem grava NULL.
             "tipo": tipo, "ce": q.get("gabarito_ce")},
        )
        salvas.append(nova)
    return salvas, descartes


# A MESMA PERGUNTA NÃO VIRA OUTRA LINHA. Medido em 22/09/2026: "reparação do dano
# no peculato culposo" existia 12 vezes, "emissão irregular de conhecimento de
# depósito" 30 vezes em 4 redações — o gerador não olhava o que já havia no
# trecho. Cada cópia infla os totais, divide o histórico do aluno entre linhas e
# volta na fila como se fosse inédita.
#
# O LIMIAR É 0,9 E NÃO MENOR, e a razão é medida. Sobreposição de palavras de
# conteúdo do enunciado, entre questões do MESMO trecho: de 0,90 a 0,95 todo par
# amostrado era a mesma pergunta. Abaixo disso as paráfrases se misturam com
# perguntas distintas do mesmo artigo — "pena cominada" × "conduta típica" deu
# 0,42 e uma paráfrase real também deu 0,40. Resposta (gabarito) e sentido (e5)
# foram medidos e também não separam: o e5 põe perguntas diferentes do mesmo
# artigo em 0,88–0,94. Paráfrase fica, portanto, como limitação registrada —
# apagar a pergunta sobre a pena achando que era a sobre a conduta é pior que
# manter as duas.
LIMIAR_DUPLICATA = 0.9


def _palavras(texto: str) -> set[str]:
    return {assunto._sem_acento(p) for p in assunto.palavras_de_conteudo(texto or "")}


def semelhanca(a: str, b: str) -> float:
    """Palavras de conteúdo em comum / palavras de conteúdo dos dois (Jaccard)."""
    pa, pb = _palavras(a), _palavras(b)
    return len(pa & pb) / len(pa | pb) if (pa | pb) else 0.0


def _ja_existe(enunciado: str, chunk: dict, tipo: str) -> dict | None:
    """A questão que já existe para este trecho e diz a mesma coisa, ou None.

    Mesmo dono (a privada de um aluno não responde pela pública, nem pela de
    outro), mesmo tipo (assertiva C/E e pergunta aberta sobre o mesmo ponto são
    exercícios diferentes) e fora de série com texto associado — a série é
    gravada inteira por `salvar_serie`, que não passa por aqui."""
    for c in db.query(
            """SELECT id, disciplina, tema, enunciado, gabarito, dicas, tipo,
                      gabarito_ce, usuario_id
                 FROM questao
                WHERE fonte_chunks = %(f)s::bigint[] AND tipo = %(tipo)s
                  AND usuario_id IS NOT DISTINCT FROM %(dono)s
                  AND contexto_id IS NULL
                ORDER BY id""",
            {"f": [chunk["id"]], "tipo": tipo, "dono": chunk.get("dono")}):
        if semelhanca(enunciado, c["enunciado"]) >= LIMIAR_DUPLICATA:
            return c
    return None


# Trecho utilizável: dá pra provar de onde a questão saiu, não é histórico,
# não é stub nem revogado. `NOT EXISTS` prioriza o que ainda não virou questão
# — sem isso, gerar duas vezes seguidas na mesma mesa cobraria o mesmo artigo.
#
# A ÚLTIMA LINHA É A REGRA INTEIRA DE QUEM PODE VIRAR QUESTÃO:
#   · chunk com artigo -> lei, proveniência por dispositivo, público;
#   · chunk sem artigo -> só se o documento for DESTE aluno. Aí a
#     proveniência é o número do trecho (`_casar`) e a questão nasce privada
#     (026, `salvar` tira o dono do chunk).
#
# Material sem artigo de OUTRA pessoa nunca entra, e material público sem
# artigo também não: hoje só `tipo = 'historico'` cai nesse caso, e ele já
# estava excluído por conter redação revogada.
#
# Antes desta linha o filtro era `c.artigo IS NOT NULL` puro, e havia uma
# brecha latente: apostila cujo PDF tinha "Art. N" era fatiada por artigo, o
# filtro a aceitava, e a questão ia pro acervo COMPARTILHADO. Nunca aconteceu
# (a busca por tema não olhava material privado), mas `_por_disciplina` não
# olhava dono nenhum — bastava a apostila cair no recorte da mesa.
FILTRO_UTIL = """
      d.tipo <> 'historico'
  AND length(c.texto) >= %(min)s
  AND c.texto NOT ILIKE '%%(revogad%%'
  AND (c.artigo IS NOT NULL OR d.usuario_id = %(dono)s)
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


def _por_disciplina(disciplinas: list[str] | None, limite: int,
                    dono: int | None = None) -> list[int]:
    linhas = db.query(SQL_POR_DISCIPLINA,
                      {"disc": disciplinas, "min": MIN_TEXTO, "lim": limite,
                       "dono": dono})
    return [l["id"] for l in linhas]


def _uteis(achados: list[dict], dono: int | None) -> list[dict]:
    """Dos trechos que a busca devolveu, os que podem virar questão — na ordem
    da RELEVÂNCIA, não do banco. A busca é otimizada pra explicar (histórico
    ajuda a explicar), a geração exige proveniência; este é o filtro entre as
    duas coisas, e `e_lei` é o que a mistura usa depois."""
    if not achados:
        return []
    linhas = db.query(
        f"""SELECT c.id, c.artigo IS NOT NULL AS e_lei, d.disciplina,
                   EXISTS (SELECT 1 FROM questao q WHERE c.id = ANY(q.fonte_chunks)) AS ja_tem
              FROM chunk c JOIN documento d ON d.id = c.documento_id
             WHERE c.id = ANY(%(ids)s) AND {FILTRO_UTIL}""",
        {"ids": [c["id"] for c in achados], "min": MIN_TEXTO, "dono": dono},
    )
    ranking = {c["id"]: i for i, c in enumerate(achados)}
    return sorted(linhas, key=lambda r: ranking.get(r["id"], 99))


def _dos_trechos(ids: list[int], limite: int, dono: int | None) -> list[int]:
    """Dos trechos que a resposta do tutor ACABOU de usar, os que servem de fonte.

    "Quero questões sobre isto" depois de uma leitura refazia a busca pelo
    assunto da conversa e voltava outras páginas do mesmo material — medido em
    24/09/2026: lida a parte de federação, as questões saíram de "livros
    sagrados em acervos públicos" (p. 187 e 212). "Isto" é o que foi lido.

    O dono é conferido aqui (público ou do próprio aluno), porque os ids vêm
    do histórico e não de uma busca que já filtrou. Sumário fica de fora, e a
    escolha se espalha pela janela em vez de pegar só o começo."""
    from .leitura import e_sumario
    linhas = db.query(
        """SELECT c.id, c.texto FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.id = ANY(%(i)s) AND (d.usuario_id IS NULL OR d.usuario_id = %(u)s)""",
        {"i": ids, "u": dono})
    validos = {r["id"] for r in linhas if not e_sumario(r["texto"])}
    ordem = [i for i in ids if i in validos]
    if len(ordem) <= limite:
        return ordem
    passo = len(ordem) / limite
    return [ordem[int(k * passo)] for k in range(limite)]


def disciplinas_dos_trechos(ids: list[int]) -> list[str]:
    """A matéria dos trechos que a conversa acabou de citar, a mais citada primeiro."""
    if not ids:
        return []
    return [r["disciplina"] for r in db.query(
        """SELECT d.disciplina, count(*) AS n FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.id = ANY(%(i)s) AND d.disciplina IS NOT NULL
            GROUP BY d.disciplina ORDER BY n DESC""", {"i": ids})]


def _na_materia_da_conversa(uteis: list[dict], tema: str, materias: list[str] | None) -> list[dict]:
    """Fica na matéria da conversa quando o assunto pedido está NELA.

    Medido em 28/09/2026 (bateria de descoberta, aluno simulado): numa conversa de
    Raciocínio Lógico, "tira isso e bota de tabela verdade logo" foi à busca como
    frase inteira, o 1º colocado foi a 8.112 art. 86 e saiu um cartão de "Licença
    para atividade política". A fala de reclamação é ruído para a busca; a matéria
    da conversa não é. Mas pedir "questão de peculato" no meio de lógica é trocar
    de assunto — por isso só restringe quando algum trecho da matéria da conversa
    tem palavra de conteúdo do pedido."""
    if not materias or not uteis:
        return uteis
    do_tema = {assunto._sem_acento(p) for p in assunto.palavras_de_conteudo(tema or "")}
    dela = [u for u in uteis if u.get("disciplina") in materias]
    if not dela or not do_tema:
        return uteis
    textos = {r["id"]: r["texto"] for r in db.query(
        "SELECT id, texto FROM chunk WHERE id = ANY(%(i)s)", {"i": [u["id"] for u in dela]})}
    if any(_palavras_em_comum(textos.get(u["id"]), do_tema) for u in dela):
        return dela
    return uteis


def termos_raros(tema: str, dono: int | None, k: int = 2) -> list[str]:
    """Os `k` termos do pedido que MENOS trechos do acervo dele trazem — o que diz de
    que assunto se trata. "controle de constitucionalidade": "controle" está em
    centenas de artigos, "constitucionalidade" em poucos. Termo que nenhum trecho
    traz não conta; lista vazia = o acervo não tem o assunto.

    DOIS, e não um: medido em 29/09/2026, "consegue me mandar umas questões de
    controle de constitucionalidade?" teve como termo mais raro "consegue" — lei não
    fala gíria — e o trecho escolhido foi o CP 177 (sociedade por ações). Um termo
    de ruído raro só passa se vier junto do termo do assunto."""
    from . import pedido
    termos = {assunto._sem_acento(p).lower() for p in assunto.palavras_de_conteudo(pedido.sem_o_pedido(tema))
              if len(p) >= 4}
    # Tema longo (a explicação do tutor, no pedido vago): os 12 termos mais longos
    # bastam — são os específicos — e cada contagem custa ~0,2 s.
    termos = set(sorted(termos, key=lambda t: (-len(t), t))[:12])
    return [t for _, t in contagens(tema, dono, termos)[:k]]


# TERMO FORTE: específico (6 letras ou mais) e em poucos trechos. É o que separa
# "questão de peculato" (troca de assunto legítima, vai aonde o termo estiver) de
# "bota a questão pra eu resolver direito" — "direito" aqui é advérbio, e sem
# termo forte o pedido não nomeia assunto: vale a matéria da conversa.
TERMO_FORTE_MIN_LETRAS = 6
TERMO_FORTE_MAX_TRECHOS = 150


def contagens(tema: str, dono: int | None, termos: set[str] | None = None) -> list[tuple[int, str]]:
    """(trechos que trazem o termo, termo) do pedido, do mais raro ao mais comum."""
    from . import pedido
    if termos is None:
        termos = {assunto._sem_acento(p).lower() for p in assunto.palavras_de_conteudo(pedido.sem_o_pedido(tema))
                  if len(p) >= 4}
        termos = set(sorted(termos, key=lambda t: (-len(t), t))[:12])
    contagem = []
    for t in termos:
        n = db.exec1("""SELECT count(*) AS n FROM chunk c JOIN documento d ON d.id = c.documento_id
                         WHERE (d.usuario_id IS NULL OR d.usuario_id = %(u)s)
                           AND lower(c.texto) ~ %(r)s""", {"u": dono, "r": _palavra_exata(t)})["n"]
        if n:
            contagem.append((n, t))
    return sorted(contagem)


def tem_termo_forte(tema: str, dono: int | None) -> bool:
    return any(len(t) >= TERMO_FORTE_MIN_LETRAS and n <= TERMO_FORTE_MAX_TRECHOS
               for n, t in contagens(tema, dono))


def termo_raro(tema: str, dono: int | None) -> str | None:
    raros = termos_raros(tema, dono, k=1)
    return raros[0] if raros else None


# PALAVRA EXATA, e não o índice com radical: o `portuguese` reduz
# "constitucionalidade" a "constitucional" — que está em centenas de trechos, e o
# termo "raro" virava "controle". O acento pode faltar na fala ("informatica",
# "licenca"): cada vogal e o "c" aceitam as formas acentuadas. ~0,2 s por termo.
_ACENTOS = {"a": "[aáàâã]", "e": "[eéê]", "i": "[ií]", "o": "[oóôõ]", "u": "[uúü]", "c": "[cç]"}


def _palavra_exata(termo: str) -> str:
    return r"\m" + "".join(_ACENTOS.get(ch, re.escape(ch)) for ch in termo) + r"\M"


def _todos(termos: list[str]) -> str:
    return " AND ".join(f"lower(c.texto) ~ %(r{i})s" for i in range(len(termos)))


def _pelo_termo(termos: list[str], dono: int | None, limite: int = 12) -> list[dict]:
    """Os trechos que trazem TODOS os termos, os que mais repetem o primeiro antes."""
    params = {"u": dono, "l": limite, **{f"r{i}": _palavra_exata(t) for i, t in enumerate(termos)}}
    return db.query(
        f"""SELECT c.id FROM chunk c JOIN documento d ON d.id = c.documento_id
             WHERE (d.usuario_id IS NULL OR d.usuario_id = %(u)s) AND {_todos(termos)}
             ORDER BY (length(lower(c.texto)) - length(regexp_replace(lower(c.texto), %(r0)s, '', 'g'))) DESC
             LIMIT %(l)s""", params)


def _com_o_termo(uteis: list[dict], termos: list[str]) -> list[dict]:
    if not uteis:
        return uteis
    params = {"i": [u["id"] for u in uteis], **{f"r{i}": _palavra_exata(t) for i, t in enumerate(termos)}}
    tem = {r["id"] for r in db.query(
        f"SELECT c.id FROM chunk c WHERE c.id = ANY(%(i)s) AND {_todos(termos)}", params)}
    return [u for u in uteis if u["id"] in tem]


def _por_tema(tema: str, limite: int, dono: int | None = None,
              materias: list[str] | None = None, assunto_nomeado: bool = False) -> list[int]:
    """
    Usa a MESMA busca do tutor (`retrieval.buscar`), não uma consulta
    própria: o trecho que fundamenta a resposta na conversa tem que ser o
    trecho de que a questão é cobrada, senão o aluno recebe pergunta sobre
    algo que não foi o que ele acabou de ler.

    Depois filtra pelo que serve de fonte — a busca é otimizada pra explicar
    (histórico ajuda a explicar), a geração exige proveniência.
    """
    # A BUSCA OLHA A BIBLIOTECA DO ALUNO, e por muito tempo não olhava.
    #
    # A versão anterior chamava `buscar` sem `usuario_id` de propósito, com uma
    # justificativa que estava certa e virou obsoleta: `questao` era acervo
    # estritamente compartilhado (008), então gerar da apostila enfiaria
    # material pago de um aluno no banco de todo mundo, com proveniência
    # apontando pra um chunk que os outros não podem ler.
    #
    # A consequência era a que o uso real mostrou: o tutor EXPLICAVA pela
    # apostila (`socratic.explicar` sempre leu a biblioteca) e, na hora de
    # treinar o mesmo assunto, gerava de outro lugar. "Se você está trazendo a
    # fonte de um lugar, o certo é trazer questões dali também."
    #
    # A 026 removeu a causa em vez do sintoma: a questão passou a ter dono, e
    # `salvar` o tira do próprio chunk. O que era vazamento agora é questão
    # privada, e o predicado que a esconde dos outros mora em
    # `questoes.do_aluno()`, num lugar só.
    # ASSUNTO NOMEADO: a busca vai pelo assunto, sem as palavras do pedido, e todo
    # candidato — o 1º colocado inclusive — tem de trazer o termo raro dele. Medido na
    # bateria de 29/09/2026: questões de Informática (sem material) saíam de Direito
    # Administrativo, e as de controle de constitucionalidade, de competência
    # municipal. A regra "o 1º entra sempre" é da citação precisa ("art. 312",
    # "concussão"), que o termo raro também cumpre.
    from . import pedido
    raros = termos_raros(tema, dono) if assunto_nomeado else []
    if assunto_nomeado and not raros:
        return []
    consulta = (pedido.sem_o_pedido(tema) or tema) if assunto_nomeado else tema
    achados = retrieval.buscar(consulta, n=12, usuario_id=dono)
    if not achados:
        return []
    uteis = _uteis(achados, dono)
    if raros:
        # A busca por sentido não trouxe nenhum trecho com os termos, mas o acervo tem:
        # vão os que os trazem. "controle de constitucionalidade" não traz o art. 102 da
        # CF entre os 12 primeiros.
        uteis = _com_o_termo(uteis, raros) or _uteis(_pelo_termo(raros, dono), dono)
    uteis = _no_assunto(_na_materia_da_conversa(uteis, tema, materias), tema)
    if not uteis:
        return []
    # RELEVÂNCIA DEFINE O QUE ESTÁ NO ASSUNTO; novidade só escolhe DENTRO
    # disso. A primeira versão ordenava por `(ja_tem, ranking)`, o que punha
    # todo chunk inédito à frente de todo chunk já cobrado — e o efeito
    # apareceu na primeira conversa real: pedir questão sobre PECULATO
    # devolveu uma sobre DESACATO, porque peculato já tinha questão e
    # desacato não. Era exatamente o "cobrar o artigo errado só por ser
    # inédito" que o comentário dizia evitar, e o código fazia.
    #
    # Agora o corte é em dois passos: os mais relevantes formam o pool
    # (`POOL_POR_PEDIDO` vezes o pedido, pra sobrar escolha), e só dentro
    # dele a preferência é pelo que ainda não virou questão.
    ranking = {r["id"]: i for i, r in enumerate(uteis)}
    por_relevancia = uteis

    # O PRIMEIRO COLOCADO ENTRA SEMPRE, cobrado ou não. Quando a busca é
    # precisa — citação de dispositivo ("art. 312") ou nome do crime
    # ("concussão") — `retrieval.buscar` devolve o alvo em 1º e o resto é
    # complemento. Deixar a novidade decidir aí devolvia CP 131 e 136 pra
    # quem pediu concussão, só porque o art. 316 já tinha questão: resposta
    # inédita e fora do assunto, que é o pior dos dois mundos.
    #
    # Só as vagas RESTANTES preferem o inédito, e dentro de um pool de
    # candidatos ainda relevantes — é o que evita repetir o mesmo artigo em
    # sessões seguidas sem sair do que foi perguntado.
    primeiro = por_relevancia[:1]
    resto = sorted(por_relevancia[1:max(limite * POOL_POR_PEDIDO, limite + 2)],
                   key=lambda r: (r["ja_tem"], ranking.get(r["id"], 99)))
    candidatos = primeiro + resto

    # SEGUNDA BUSCA, SÓ NO ACERVO PÚBLICO, quando a lei não chegou nem a ser
    # candidata. Não é redundância da primeira: é uma busca com OUTRO
    # universo.
    #
    # MEDIDO. Tema "lesão corporal grave: conceito e classificação", conta com
    # a apostila de Medicina Legal indexada: os 24 primeiros colocados são
    # todos da apostila, e o art. 129 do CP não aparece em nenhuma posição. A
    # causa é a 025 — o rótulo do material entrou no tsvector —, e ela está
    # certa: é o que faz "traumatologia forense" achar a aula. O efeito
    # colateral é que UM rótulo repetido em 78 chunks produz 78 acertos
    # lexicais, e o único artigo sobre o assunto não tem como competir.
    #
    # Daí a assimetria desta função, que é medida e não estética: só a LEI
    # precisa de reforço. O material afoga, nunca falta — se ele não apareceu
    # é porque não existe material do assunto, e aí não há o que reforçar.
    # Buscar no acervo público (`usuario_id=None`, o padrão seguro de
    # `retrieval.buscar`) devolve lei por construção.
    #
    # Custo: uma consulta de busca a mais, e só no caso em que a lei ficou de
    # fora. Nenhuma chamada de LLM.
    if limite >= 2 and dono and not any(r["e_lei"] for r in candidatos[:limite]):
        vistos = {c["id"] for c in candidatos}
        candidatos += [r for r in _lei_do_assunto(tema) if r["id"] not in vistos]

    return _misturar([r["id"] for r in candidatos], candidatos, limite)


def _no_assunto(uteis: list[dict], tema: str) -> list[dict]:
    """O líder da busca e, depois dele, só quem é DO ASSUNTO.

    Medido em 28/09/2026: "me dá 2 questões de conjuntos", com uma apostila de
    Raciocínio Lógico que ensina conjuntos, gerou "Conceito de Proposição" e
    "Furto Noturno". A busca é k-vizinhos sem piso: para "conjuntos" ela devolve
    a apostila E artigos da CF e do CP, e `_misturar`, que reserva uma vaga para
    a lei, pegou o artigo mais bem colocado — que não tinha nada de conjuntos.

    A trava é a de `_lei_do_assunto`, estendida à apostila: fora o 1º colocado
    (que entra sempre, pela razão de "concussão"), cada candidato precisa
    compartilhar palavra de conteúdo com o tema — na rubrica, se é lei; no
    texto, se é material do aluno. Tema sem palavra de conteúdo não filtra."""
    do_tema = {assunto._sem_acento(p) for p in assunto.palavras_de_conteudo(tema or "")}
    if not do_tema or len(uteis) < 2:
        return uteis
    textos = {r["id"]: r for r in db.query(
        "SELECT id, rubrica, texto FROM chunk WHERE id = ANY(%(i)s)", {"i": [u["id"] for u in uteis]})}
    fica = [uteis[0]]
    for u in uteis[1:]:
        c = textos.get(u["id"]) or {}
        base = c.get("rubrica") if u["e_lei"] else c.get("texto")
        if _palavras_em_comum(base, do_tema):
            fica.append(u)
    return fica


def _lei_do_assunto(tema: str) -> list[dict]:
    """
    Artigos que tratam DO ASSUNTO — ou lista vazia, que aqui é a resposta
    certa e não uma falha.

    A busca pública devolve alguma coisa pra qualquer pergunta: é ranking, não
    julgamento. Medido, com estas quatro consultas:

      "peculato"                          -> cp 312 Peculato          (certo)
      "lesão corporal grave"              -> cp 129 Lesão corporal    (certo)
      "lesão corporal grave: conceito
       e classificação"                   -> cp 131 Perigo de contágio (ERRADO,
                                             o 129 caiu pra 2º com o sufixo)
      "asfixiologia forense: mecanismos
       de asfixia mecânica"               -> cp 252 Uso de gás tóxico (ERRADO,
                                             e não existe artigo do assunto)

    Os dois últimos são o defeito que ESTE reforço criaria se aceitasse o 1º
    colocado: questão de "gás asfixiante" pra quem estuda asfixiologia forense
    é literalmente a reclamação que abriu o assunto — "trouxe questões
    aleatórias de outro assunto que não era o que estávamos conversando".

    A TRAVA É A RUBRICA, e ela é dura de propósito: o artigo entra só se a
    rubrica dele compartilhar palavra de conteúdo com o tema. "Lesão corporal"
    casa "lesão corporal grave"; "Uso de gás tóxico ou asfixiante" não casa
    "asfixiologia forense" — asfixiante e asfixiologia são palavras
    diferentes, e é justamente por não radicalizar que a comparação acerta
    aqui (radicalizar casaria as duas por "asfixi" e traria o artigo errado).

    Por que não `por_rubrica`, que já existe e é a estratégia precisa: ela
    exige TODOS os termos da consulta na rubrica (`websearch_to_tsquery` é
    AND), então "lesão corporal grave" não casa "Lesão corporal" por causa do
    "grave" — medido, devolve vazio. Sobreposição de palavras é o mesmo
    espírito com o limiar no lugar certo.

    Assunto que a lei não trata (asfixiologia, papiloscopia, balística) fica
    sem reforço, e é o comportamento correto: não há artigo pra cobrar, e
    inventar um é pior que não ter.
    """
    do_tema = {assunto._sem_acento(p) for p in assunto.palavras_de_conteudo(tema)}
    if not do_tema:
        return []
    achados = [c for c in retrieval.buscar(tema, n=6) if c.get("artigo")]
    # QUANTAS palavras em comum, não "se há alguma", e a diferença é o
    # resultado: com "lesão corporal grave: conceito e classificação", o art.
    # 131 (Perigo de contágio de moléstia GRAVE) passava o teste de "alguma" e
    # vinha à frente do 129 (LESÃO CORPORAL), que casa duas. Ordenar pela
    # contagem põe o certo na frente sem que ninguém precise decidir que
    # "grave" é palavra fraca — a alternativa era mais uma palavra na lista
    # `VAZIAS`, que é o remendo que `core/assunto.py` documenta como o que
    # nunca acaba.
    pontuados = [(_palavras_em_comum(c.get("rubrica"), do_tema), i, c)
                 for i, c in enumerate(achados)]
    escolhidos = [c for n, _, c in sorted(pontuados, key=lambda x: (-x[0], x[1])) if n]
    return _uteis(escolhidos, None)


def _palavras_em_comum(rubrica: str | None, do_tema: set[str]) -> int:
    return sum(assunto._sem_acento(p) in do_tema
               for p in set(assunto.palavras_de_conteudo(rubrica or "")))


def _misturar(ids: list[int], candidatos: list[dict], limite: int) -> list[int]:
    """
    Corta em `limite` GARANTINDO uma vaga pra lei e uma pra apostila, quando
    o assunto tem as duas — o "dos dois lugares" pedido com estas palavras.

    POR QUE NÃO DEIXAR SÓ A RELEVÂNCIA DECIDIR
    ------------------------------------------
    Medido na primeira rodada real: pedidas 3 questões sobre "lesão corporal
    grave", a busca híbrida pôs a aula da professora nos 3 primeiros lugares e
    o art. 129 em nenhum. As 3 questões saíram boas e saíram todas da
    apostila. Não é ranking errado — pra "conceito e classificação" a aula
    É mais relevante que o texto do artigo. Mas a prova cobra lei seca, e o
    efeito acumulado seria o aluno cuja apostila é boa parar de receber
    questão de dispositivo justamente nos assuntos que estuda mais.

    O contrário também vale, e era o defeito original: explicar pela apostila
    e cobrar do Código.

    A REGRA É MÍNIMO, NÃO COTA. Uma vaga de cada, e o resto continua sendo da
    relevância — não é meio a meio. Pedido de 1 questão não mistura nada
    (não há como), e assunto que existe num lugar só segue saindo inteiro
    dali: garantir vaga pra lado que não tem candidato devolveria menos
    questão do que o aluno pediu, o que é pior que a mistura imperfeita.
    """
    if limite < 2:
        return ids[:limite]
    tipo = {c["id"]: bool(c["e_lei"]) for c in candidatos}
    escolhidos = ids[:limite]
    if len({tipo.get(i) for i in escolhidos}) > 1:
        return escolhidos           # já vieram dos dois; nada a fazer
    faltando = not tipo.get(escolhidos[0], False) if escolhidos else False
    # O melhor colocado do lado ausente, se existir, ocupa a ÚLTIMA vaga —
    # nunca a primeira: quem lidera a busca entra sempre (é a trava que
    # devolveu "concussão" pra quem pediu concussão).
    for i in ids[limite:]:
        if tipo.get(i) is faltando:
            return escolhidos[:-1] + [i]
    return escolhidos


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


def salvar_serie(serie: dict, lote: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Grava o texto-base e os itens que o julgam (migração 013).

    A proveniência é checada ANTES de criar o contexto: se o trecho que o
    modelo diz ter usado não está no lote, nada é gravado. Criar o contexto
    primeiro e descobrir depois deixaria um texto-base órfão no banco — sem
    item que o referencie, invisível, e contando como material que não é.

    Mesma função de casamento das avulsas (`_casar`), de propósito: a série
    ganhou a segunda chave de proveniência junto, sem uma segunda cópia da
    regra pra divergir depois.
    """
    chunk, motivo = _casar(serie, lote)
    if chunk is None:
        return [], [motivo]

    ctx = db.exec1(
        """INSERT INTO contexto (documento_id, disciplina, texto, fonte_chunks)
           VALUES (%(d)s, %(disc)s, %(t)s, %(f)s) RETURNING id""",
        {"d": chunk["documento_id"], "disc": chunk["disciplina"],
         "t": serie["contexto"], "f": [chunk["id"]]},
    )
    salvas = []
    for item in serie["itens"]:
        nova = db.exec1(
            """INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito,
                                    dicas, fonte_chunks, tipo, gabarito_ce,
                                    contexto_id, ordem_no_contexto, usuario_id)
               VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, '[]'::jsonb, %(f)s,
                       'certo_errado', %(ce)s, %(ctx)s, %(ord)s, %(dono)s)
               RETURNING id, disciplina, tema, enunciado, gabarito, dicas, tipo,
                         gabarito_ce, contexto_id, ordem_no_contexto, usuario_id""",
            {"d": chunk["documento_id"], "disc": chunk["disciplina"], "t": item["tema"],
             "dono": chunk.get("dono"),
             "e": item["enunciado"], "g": item["gabarito"], "f": [chunk["id"]],
             "ce": item["gabarito_ce"], "ctx": ctx["id"], "ord": item["ordem_no_contexto"]},
        )
        nova["contexto"] = serie["contexto"]
        salvas.append(nova)
    return salvas, []


def _fonte(c: dict) -> str:
    """O rótulo da fonte que vai pra tela.

    Delega em `retrieval.referencia` em vez de montar a string aqui: a versão
    anterior era `f"{norma or titulo} art. {artigo}"`, que virava
    "curso-392569-aula-10.pdf art. None" no instante em que a fonte passou a
    poder ser apostila. `referencia` já sabe rotular trecho sem artigo — pelo
    assunto classificado e a página — e é a mesma regra que o tutor usa pra
    citar, então tela de questão e explicação passam a dizer o mesmo nome."""
    return retrieval.referencia(c)


def sob_demanda(disciplinas: list[str] | None = None, tema: str | None = None,
                quantidade: int = 3, tipo: str = "resposta_livre",
                com_contexto: bool | None = None,
                usuario_id: int | None = None,
                trechos: list[int] | None = None,
                pedido_do_aluno: str | None = None,
                materias_da_conversa: list[str] | None = None,
                assunto_nomeado: bool = False,
                escolhidos: tuple[list[int], bool] | None = None) -> dict:
    """
    Gera até `quantidade` questões e grava as que têm proveniência.

    `escolhidos` é o que `escolher` já devolveu (a rota do chat escolhe antes de o
    tutor escrever); sem ele, escolhe aqui.

    `tema` (a conversa, ou o que o aluno pediu) manda quando vem; sem ele,
    sorteia trecho ainda descoberto dentro do recorte da mesa — que é o caso
    "minha fila está vazia, me dá o que estudar".

    `usuario_id` abre a BIBLIOTECA DELE como fonte, além da lei (026). Sem
    ele, só acervo público — que é o que `gerar.py` (CLI em lote) quer, já
    que não gera em nome de ninguém. A questão que sair da apostila nasce
    privada; a que sair da lei nasce pública, como sempre.

    UM ARTIGO POR QUESTÃO PEDIDA, a mesma lição de `gerar.py`: mandar 6
    artigos pra pedir 3 questões deixa 3 descobertos, que voltam no lote
    seguinte — contexto pago duas vezes sem ganho de cobertura.
    """
    quantidade = max(1, min(quantidade, MAX_POR_VEZ))
    if escolhidos:
        ids, trocou_de_assunto = escolhidos
    else:
        ids, trocou_de_assunto = escolher(disciplinas, tema, quantidade, usuario_id, trechos,
                                          materias_da_conversa, assunto_nomeado)
    lote = _lote_por_ids(ids)
    return _gerar_do_lote(lote, quantidade, tipo, com_contexto, trocou_de_assunto, pedido_do_aluno)


def _da_materia(ids: list[int], materias: list[str] | None) -> list[int]:
    """Só os trechos cuja disciplina é a da matéria em foco (nome do edital ou do material).

    E NUNCA trecho de simulado: ele já É questão (037), e entra pelo banco
    (`prova.da_conversa`) antes do gerador. Gerar dele reescrevia a questão da
    banca — e o trecho mistura matérias, então a nova ficava sem disciplina."""
    if not ids:
        return ids
    if not materias:
        fora = {r["id"] for r in db.query(
            """SELECT c.id FROM chunk c JOIN documento d ON d.id = c.documento_id
                WHERE c.id = ANY(%(i)s) AND d.tipo = 'simulado'""", {"i": ids})}
        return [i for i in ids if i not in fora]
    dela = {r["id"] for r in db.query(
        """SELECT c.id FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.id = ANY(%(i)s) AND d.disciplina = ANY(%(m)s)
              AND d.tipo <> 'simulado'""", {"i": ids, "m": materias})}
    return [i for i in ids if i in dela]


# DOIS ASSUNTOS NUM PEDIDO: "questão de conjunto e porcentagem". Exigir os dois
# termos no mesmo trecho achou só a APRESENTAÇÃO do curso, que cita tudo — e a
# questão saiu de proposições (bateria de 29/09/2026). Cada parte vai por si.
RE_SEPARA_ASSUNTOS = re.compile(r"(?i)\s+e\s+|\s+ou\s+|[,;]")


def _partes(tema: str) -> list[str]:
    from . import pedido
    partes = [p.strip() for p in RE_SEPARA_ASSUNTOS.split(pedido.sem_o_pedido(tema)) if p.strip()]
    com_conteudo = [p for p in partes if any(len(w) >= 4 for w in assunto.palavras_de_conteudo(p))]
    return com_conteudo if len(com_conteudo) >= 2 else [tema]


def _pelo_indice(tema: str, usuario_id: int, quantidade: int) -> list[int]:
    """Trechos do assunto que o pedido nomeia, pelo índice: os de ENSINO,
    espalhados pelo material (um de cada parte); sem ensino, os de questão."""
    from . import indice, pedido
    alvo = indice.assunto_citado(usuario_id, pedido.sem_o_pedido(tema))
    if not alvo:
        return []
    ids = indice.trechos_do_assunto(alvo["id"], "ensino") or indice.trechos_do_assunto(alvo["id"])
    if len(ids) <= quantidade:
        return ids
    passo = len(ids) / quantidade
    return [ids[int(k * passo)] for k in range(quantidade)]


def escolher(disciplinas: list[str] | None, tema: str | None, quantidade: int,
             usuario_id: int | None, trechos: list[int] | None = None,
             materias_da_conversa: list[str] | None = None,
             assunto_nomeado: bool = False,
             materia_em_foco: list[str] | None = None,
             materia_da_conversa: list[str] | None = None) -> tuple[list[int], bool]:
    """De que trechos sairão as questões — sem modelo nenhum, só busca. (ids, trocou).

    Separado de `sob_demanda` para a rota decidir ANTES de o tutor escrever: sem
    trecho do assunto pedido, o tutor diz isso com as palavras dele. Medido em
    29/09/2026: a resposta escrita antes ("as questões estão abaixo") era trocada
    depois por uma frase fixa, que se repetia igual a cada novo pedido.

    Levanta `SemMaterial` quando não há de onde tirar."""
    quantidade = max(1, min(quantidade, MAX_POR_VEZ))
    # `materia_em_foco`: a disciplina que a conversa nomeou (e os nomes de material
    # dela). Havendo, todo trecho tem de ser DELA — medido em 29/09/2026: numa
    # conversa sobre memória RAM (Informática, sem material), "bota a questão com
    # A B C D" deu "Abolição violenta do Estado Democrático de Direito", porque
    # "tentar" e "direito" da fala casaram com o CP. A matéria barra isso sem
    # depender de palavra.
    # Sem matéria nomeada NESTA fala e sem termo forte, o pedido não nomeia assunto
    # de verdade: vale a matéria da CONVERSA (a de antes). "ROM não apaga nada, bota a
    # questão pra eu resolver direito" numa conversa de Informática deu Direitos
    # Fundamentais — "direito" era advérbio.
    if not materia_em_foco and materia_da_conversa and tema and not tem_termo_forte(tema, usuario_id):
        materia_em_foco = materia_da_conversa
    ids = _da_materia(_dos_trechos(trechos, quantidade, usuario_id), materia_em_foco) if trechos else []
    # O ÍNDICE DE ASSUNTOS (036) primeiro: o pedido que nomeia um assunto do
    # material dele sai dos trechos MARCADOS com o assunto — de qualquer parte da
    # apostila —, e não do que a busca por palavra achar. Fala curta só: o tema
    # longo (a explicação do tutor, no pedido vago) casaria com qualquer assunto.
    if not ids and tema and usuario_id and assunto_nomeado and len(tema) <= 300:
        ids = _da_materia(_pelo_indice(tema, usuario_id, quantidade), materia_em_foco)
    if not ids and tema:
        partes = _partes(tema) if assunto_nomeado else [tema]
        por_parte = [_da_materia(_por_tema(pt, quantidade, usuario_id, materias_da_conversa, assunto_nomeado),
                                 materia_em_foco) for pt in partes]
        # Intercala: o 1º de cada parte, depois o 2º de cada uma…
        vistos: set[int] = set()
        for rodada in range(quantidade):
            for lista in por_parte:
                if rodada < len(lista) and lista[rodada] not in vistos and len(ids) < quantidade:
                    vistos.add(lista[rodada])
                    ids.append(lista[rodada])
    elif not ids:
        # Com matéria em foco, o sorteio é DELA — e sem trecho dela não há questão.
        # Sem isto o pedido vago numa conversa de TI (sem material) sorteava na mesa
        # inteira: Processo Penal, 8.112, aula de Administrativo (02/10/2026).
        ids = _por_disciplina(materia_em_foco or disciplinas, quantidade, usuario_id)
        if not ids and materia_em_foco:
            raise SemMaterial("não há trecho da matéria em foco no acervo do aluno")
    # TROCA DE ASSUNTO DECLARADA. O fallback já existia e estava certo — cair
    # pro recorte é melhor que devolver vazio a quem pediu questão —, mas era
    # SILENCIOSO, e isso o transformava em mentira: relatado com transcrição, o
    # aluno conversou sobre princípios do Direito Administrativo, pediu três
    # questões, e recebeu extensão de recurso, omissão de projetista e
    # estabilidade. O tutor abriu com "vamos treinar isso" — sobre outra coisa.
    #
    # Quem chama precisa SABER que trocou, pra poder dizer. É a mesma regra que
    # o prompt já impõe pra explicação ("se os trechos não cobrirem, diga
    # isso"): silêncio sobre o que o sistema não tem é o defeito, não o
    # fallback.
    trocou_de_assunto = False
    # Assunto NOMEADO sem trecho dele: não há o que cobrar, e sortear na mesa daria
    # questão de outra matéria para quem pediu esta — a tela avisava a troca, e o
    # aluno reclamava do mesmo jeito. Só o pedido vago ("me testa") cai no sorteio.
    if not ids and tema and assunto_nomeado:
        raise SemMaterial("não há trecho desse assunto no acervo do aluno")
    if not ids and tema:
        # Na matéria da conversa, se houver: sortear na mesa inteira trazia
        # Direito Administrativo para quem pedia tabela-verdade.
        ids = (materia_em_foco and _por_disciplina(materia_em_foco, quantidade, usuario_id)) \
            or (materias_da_conversa and _por_disciplina(materias_da_conversa, quantidade, usuario_id)) \
            or _por_disciplina(disciplinas, quantidade, usuario_id)
        trocou_de_assunto = bool(ids)
    if not ids:
        raise SemMaterial(
            "o acervo ainda não tem trecho dessas disciplinas pra gerar questão"
        )
    return ids, trocou_de_assunto


def _gerar_do_lote(lote: list[dict], quantidade: int, tipo: str, com_contexto: bool | None,
                   trocou_de_assunto: bool, pedido_do_aluno: str | None) -> dict:

    # SÉRIE (texto-base + itens) é o padrão do item C/E quando se pede mais
    # de um: é a forma real da prova. Item avulso continua existindo — o
    # Cebraspe cobra os dois —, e pedir UM item só não justifica inventar
    # uma situação hipotética pra ele sozinho.
    if com_contexto is None:
        com_contexto = tipo == "certo_errado" and quantidade > 1
    if com_contexto:
        serie = socratic.gerar_serie_ce(lote[:1], quantidade)
        if serie:
            salvas, descartes = salvar_serie(serie, lote)
            return {"trocou_de_assunto": trocou_de_assunto,
                    "questoes": salvas, "descartadas": len(descartes),
                    "motivos": descartes, "contexto": serie["contexto"],
                    "fontes": [_fonte(lote[0])]}
        # Série não saiu: cai pro item avulso em vez de devolver vazio. O
        # aluno pediu questão, não pediu formato.

    questoes = socratic.gerar_questoes(lote, len(lote), tipo, pedido_do_aluno=pedido_do_aluno)
    salvas, descartes = salvar(questoes, lote)
    return {
        "trocou_de_assunto": trocou_de_assunto,
        "questoes": salvas,
        "descartadas": len(descartes),
        "motivos": descartes,
        "fontes": [_fonte(c) for c in lote],
    }
