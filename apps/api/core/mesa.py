"""
Mesa de estudo — o alvo (concurso) que dá contexto à sessão.

MESA É FILTRO, NÃO SILO (ver o porquê longo em db/010_mesa.sql). `progresso`,
`tentativa` e `erro_caderno` continuam por `usuario_id`: a memória SM-2 é do
ALUNO, não do concurso. O que a mesa faz é RECORTAR o que aparece — fila,
dashboard, caderno e simulado passam a ver só as disciplinas do edital dela.

De onde saem essas disciplinas: de `topico.disciplina` do EDITAL MAIS
RECENTE da mesa — não da união de todos os editais dela. É a mesma escolha
que `edital.mais_recente()` já fazia pra `scheduler.meta()`: reingerir um
edital corrigido tem que SUBSTITUIR o anterior, não somar disciplinas de uma
versão que o próprio operador já descartou.

Mesa sem edital devolve `None` em `disciplinas()`, e `None` significa SEM
FILTRO — o acervo inteiro, exatamente o comportamento de antes da migração
010. Mesa recém-criada (antes de subir o PDF) é o caso normal disso, e é
degradação graciosa, não defeito.
"""
from . import db

VERSAO = "mesa-v1"

NOME_PADRAO = "Mesa principal"

CAMPOS = "id, usuario_id, nome, orgao, banca, criado_em"


class ErroMesa(Exception):
    pass


# --------------------------------------------------------------- o filtro
def filtro(coluna: str) -> str:
    """
    Predicado SQL reaproveitado por scheduler/desafio/simulado/ritmo —
    UM lugar só, porque "o que esta mesa cobre" precisa dar a MESMA
    resposta na fila, no stats e no simulado (a mesma classe de erro que
    fez a 008 nascer com dois denominadores diferentes de cobertura).

    Quem usa precisa passar `disc` nos parâmetros da query, SEMPRE — a
    lista de disciplinas da mesa, ou `None` pra não filtrar nada.

    CASAMENTO NOS DOIS SENTIDOS, não igualdade: o nome vem do edital
    ("Noções De Direito Administrativo", extraído por heurística de PDF em
    core/edital.py) e precisa bater com o nome do acervo ("Direito
    Administrativo", digitado no `--disciplina` da ingestão). Um lado
    contém o outro em qualquer direção — é a mesma aproximação que
    `edital.cobertura()` já fazia com ILIKE, só que sem depender de qual
    dos dois nomes é o mais longo. Não casa falso-positivo entre irmãs
    ("Direito Penal" e "Direito Processual Penal" não se contêm).

    Custo: ILIKE por linha, sem índice. O acervo é de centenas de questões
    (não milhões), e a alternativa — materializar a disciplina da mesa numa
    coluna — cria estado que precisa ser invalidado quando o edital muda.
    """
    return f"""(%(disc)s::text[] IS NULL OR EXISTS (
                  SELECT 1 FROM unnest(%(disc)s::text[]) AS md(nome)
                   WHERE {coluna} ILIKE '%%' || md.nome || '%%'
                      OR md.nome ILIKE '%%' || {coluna} || '%%'))"""


def contar_questoes(disciplinas_: list[str] | None) -> int:
    """
    Quantas questões do acervo caem no recorte. Serve pra tela EXPLICAR o
    vazio em vez de mostrá-lo: uma mesa de TI (ou bancária, ou fiscal) num
    acervo que só tem Direito ingerido devolve zero, e isso é a verdade
    sobre o ACERVO, não sobre a mesa nem sobre o edital.

    Fora de `contexto()` de propósito: `contexto` roda na dependência de
    TODA requisição escopada por mesa, e isto é um COUNT com ILIKE que só
    duas telas precisam. Quem quer o número pede em `GET /mesa`.
    """
    r = db.exec1(
        f"SELECT count(*) AS n FROM questao q WHERE {filtro('q.disciplina')}",
        {"disc": disciplinas_},
    )
    return r["n"] if r else 0


def disciplinas(mesa_id: int | None) -> list[str] | None:
    """Disciplinas do edital mais recente da mesa. `None` = sem filtro."""
    if mesa_id is None:
        return None
    linhas = db.query(
        """SELECT DISTINCT t.disciplina
             FROM topico t
             JOIN edital e ON e.id = t.edital_id
            WHERE e.id = (SELECT id FROM edital WHERE mesa_id = %(m)s
                          ORDER BY criado_em DESC, id DESC LIMIT 1)
            ORDER BY 1""",
        {"m": mesa_id},
    )
    return [l["disciplina"] for l in linhas] or None


# ------------------------------------------------------------------- CRUD
def criar(usuario_id: int, nome: str, orgao: str | None = None,
          banca: str | None = None) -> dict:
    nome = (nome or "").strip()
    if not nome:
        raise ErroMesa("mesa precisa de um nome")
    existente = db.exec1(
        "SELECT id FROM mesa WHERE usuario_id = %(u)s AND lower(nome) = lower(%(n)s)",
        {"u": usuario_id, "n": nome},
    )
    if existente:
        raise ErroMesa(f"você já tem uma mesa chamada \"{nome}\"")
    return db.exec1(
        f"""INSERT INTO mesa (usuario_id, nome, orgao, banca)
            VALUES (%(u)s, %(n)s, %(o)s, %(b)s) RETURNING {CAMPOS}""",
        {"u": usuario_id, "n": nome, "o": orgao, "b": banca},
    )


def obter(usuario_id: int, mesa_id: int) -> dict | None:
    """SEMPRE escopado por usuario_id: pedir a mesa de outra pessoa devolve
    None (que a API vira 404), não a mesa. Mesmo espírito de
    `simulado.pertence_a()` — o id numérico identifica, não autoriza."""
    return db.exec1(
        f"SELECT {CAMPOS} FROM mesa WHERE id = %(id)s AND usuario_id = %(u)s",
        {"id": mesa_id, "u": usuario_id},
    )


def listar(usuario_id: int) -> list[dict]:
    """
    Cada mesa com o resumo do edital vigente MAIS o progresso dentro do
    recorte dela — é o cartão inteiro da tela de mesas (banca, prova,
    tópicos, barra de cobertura, "último estudo").

    `cobertura_pct` usa a MESMA definição de `v_desempenho_disciplina` e de
    `scheduler.meta()` (dominadas = caixa >= 3, sobre o acervo inteiro das
    disciplinas da mesa), só que agregada. Ter duas definições de cobertura
    convivendo é como a 008 quase nasceu errada; aqui o número do cartão e
    o número do painel têm que ser o mesmo número.

    N+1 consultas de propósito: cada mesa tem uma lista de disciplinas
    diferente, então não há um GROUP BY único que sirva. Uma conta tem
    unidades de mesas, não milhares — e a alternativa (materializar
    cobertura numa coluna) criaria estado a invalidar toda vez que alguém
    responde uma questão.
    """
    mesas = db.query(
        """SELECT m.id, m.nome, m.orgao, m.banca, m.criado_em,
                  e.id AS edital_id, e.titulo AS edital_titulo, e.data_prova,
                  COALESCE(e.topicos, 0) AS topicos
             FROM mesa m
             LEFT JOIN LATERAL (
                  SELECT ed.id, ed.titulo, ed.data_prova,
                         (SELECT count(*) FROM topico t WHERE t.edital_id = ed.id) AS topicos
                    FROM edital ed
                   WHERE ed.mesa_id = m.id
                   ORDER BY ed.criado_em DESC, ed.id DESC LIMIT 1) e ON true
            WHERE m.usuario_id = %(u)s
            ORDER BY m.criado_em, m.id""",
        {"u": usuario_id},
    )
    for m in mesas:
        disc = disciplinas(m["id"])
        m["disciplinas"] = disc
        r = db.exec1(
            f"""SELECT count(DISTINCT q.id) AS questoes,
                       count(DISTINCT q.id) FILTER (WHERE p.caixa >= 3) AS dominadas
                  FROM questao q
                  LEFT JOIN progresso p ON p.questao_id = q.id AND p.usuario_id = %(u)s
                 WHERE {filtro('q.disciplina')}""",
            {"u": usuario_id, "disc": disc},
        ) or {"questoes": 0, "dominadas": 0}
        m["questoes"] = r["questoes"]
        m["dominadas"] = r["dominadas"]
        m["cobertura_pct"] = (round(100.0 * r["dominadas"] / r["questoes"], 1)
                              if r["questoes"] else 0.0)
        # "Último estudo" DENTRO do recorte: a conta pode ter estudado hoje
        # noutra mesa, e dizer "há 2 horas" num concurso que você não abre
        # há um mês seria a tela mentindo com dado verdadeiro.
        ultimo = db.exec1(
            f"""SELECT max(t.criada_em) AS quando
                  FROM tentativa t JOIN questao q ON q.id = t.questao_id
                 WHERE t.usuario_id = %(u)s AND {filtro('q.disciplina')}""",
            {"u": usuario_id, "disc": disc},
        )
        m["ultimo_estudo"] = ultimo["quando"] if ultimo else None
    return mesas


def atualizar(usuario_id: int, mesa_id: int, nome: str | None = None,
              orgao: str | None = None, banca: str | None = None) -> dict | None:
    atual = obter(usuario_id, mesa_id)
    if not atual:
        return None
    novo_nome = (nome or "").strip() or atual["nome"]
    if novo_nome.lower() != atual["nome"].lower():
        colide = db.exec1(
            "SELECT id FROM mesa WHERE usuario_id = %(u)s AND lower(nome) = lower(%(n)s)",
            {"u": usuario_id, "n": novo_nome},
        )
        if colide:
            raise ErroMesa(f"você já tem uma mesa chamada \"{novo_nome}\"")
    return db.exec1(
        f"""UPDATE mesa SET nome = %(n)s,
                            orgao = COALESCE(%(o)s, orgao),
                            banca = COALESCE(%(b)s, banca)
             WHERE id = %(id)s AND usuario_id = %(u)s RETURNING {CAMPOS}""",
        {"id": mesa_id, "u": usuario_id, "n": novo_nome, "o": orgao, "b": banca},
    )


def apagar(usuario_id: int, mesa_id: int) -> bool:
    """Leva junto o edital e os tópicos dela (CASCADE). NÃO leva progresso,
    tentativa nem caderno de erros — esses são do aluno, não da mesa, e é
    justamente por isso que apagar uma mesa é uma operação barata aqui:
    você perde o recorte, não o que aprendeu. O histórico de simulados
    sobrevive com `mesa_id` nulo (ON DELETE SET NULL, ver migração 010)."""
    if not obter(usuario_id, mesa_id):
        return False
    db.query("DELETE FROM mesa WHERE id = %(id)s AND usuario_id = %(u)s",
             {"id": mesa_id, "u": usuario_id})
    return True


def padrao(usuario_id: int) -> dict:
    """
    A mesa mais antiga da conta, criando "Mesa principal" se ainda não
    houver nenhuma — mesmo padrão de `auth.usuario_da_cli()`: o recurso
    aparece quando é preciso, sem exigir um ritual de criação antes do
    primeiro uso. É o que a CLI usa (não tem header pra mandar) e o
    fallback da API quando `X-Mesa-Id` não vem.
    """
    m = db.exec1(
        f"SELECT {CAMPOS} FROM mesa WHERE usuario_id = %(u)s ORDER BY criado_em, id LIMIT 1",
        {"u": usuario_id},
    )
    return m or criar(usuario_id, NOME_PADRAO)


def contexto(usuario_id: int, mesa_id: int | None = None) -> dict:
    """
    Mesa + disciplinas resolvidas UMA vez, pra passar adiante — as funções
    de core/ recebem a LISTA pronta (`disciplinas=`), não o mesa_id, pra não
    repetir a mesma consulta em cada uma delas dentro de uma requisição só.
    """
    m = obter(usuario_id, mesa_id) if mesa_id is not None else padrao(usuario_id)
    if not m:
        return {}
    return {**m, "disciplinas": disciplinas(m["id"])}
