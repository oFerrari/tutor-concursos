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

VERSAO = "mesa-v3"

NOME_PADRAO = "Mesa principal"

CAMPOS = ("id, usuario_id, nome, orgao, banca, criado_em, "
          "disciplinas_manuais, biblioteca_compartilhada")


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
    """
    O alvo desta mesa. Três respostas possíveis, e as três dizem coisas
    diferentes (migração 017):

      lista do EDITAL — veio do PDF. Tem PRECEDÊNCIA sobre o manual: é o
                        documento oficial, e é dele que `scheduler.meta`
                        tira a data da prova. Deixar o manual sobrepor faria
                        o recorte vir de um lugar e o prazo de outro — o
                        mesmo defeito que a 010 evitou ao fazer disciplina e
                        data saírem do MESMO "último edital".
      lista MANUAL    — o aluno declarou o alvo na mão, porque o edital
                        ainda não saiu. Metade do tempo de preparação de
                        verdade é assim.
      None            — ninguém declarou nada. NÃO filtra, de propósito:
                        escopo vazio deixaria fila, desafio, simulado e
                        stats todos vazios, e a mesa inútil no dia 1.

    O cartão do lobby distingue os três — sem alvo ele não mostra barra nem
    percentual, porque o número ali seria o progresso do ALUNO no acervo
    inteiro exibido como se fosse progresso DA MESA.
    """
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
    do_edital = [l["disciplina"] for l in linhas]
    if do_edital:
        return do_edital

    r = db.exec1("SELECT disciplinas_manuais FROM mesa WHERE id = %(m)s", {"m": mesa_id})
    return sorted(r["disciplinas_manuais"]) if r and r["disciplinas_manuais"] else None


def origem_do_alvo(mesa_id: int) -> str:
    """"edital" | "manual" | "nenhum" — a tela precisa dizer DE ONDE veio o
    recorte, senão "5 disciplinas" parece a mesma coisa nos dois casos e o
    aluno não sabe se ainda falta subir o PDF."""
    tem_edital = db.exec1(
        "SELECT 1 x FROM topico t JOIN edital e ON e.id = t.edital_id "
        "WHERE e.mesa_id = %(m)s LIMIT 1", {"m": mesa_id})
    if tem_edital:
        return "edital"
    r = db.exec1("SELECT disciplinas_manuais FROM mesa WHERE id = %(m)s", {"m": mesa_id})
    return "manual" if (r and r["disciplinas_manuais"]) else "nenhum"


def disciplinas_do_acervo(usuario_id: int | None = None) -> list[str]:
    """O que existe pra escolher. Sai do ACERVO, não de lista fixa: uma mesa
    de TI num banco só de Direito precisa ver que não há o que escolher, em
    vez de escolher "Informática" e receber fila vazia sem explicação.

    O PREDICADO DE DONO não é opcional aqui, e a razão é a migração 019: desde
    ela `documento` guarda material PRIVADO, então um `SELECT DISTINCT
    disciplina FROM documento` cru mostra a matéria que OUTRO aluno cadastrou —
    "tcc", "meu resumo do TRT" — na tela de quem nem sabe que ele existe. É a
    mesma classe de vazamento que `retrieval.DONO` fecha na busca e
    `material.sugestoes` fecha no seletor. `usuario_id=None` devolve só público:
    default seguro, o vazamento exige id explícito e não um esquecimento.

    `IS NOT NULL` porque a 020 deixou `disciplina` nullable: sem isso o
    `DISTINCT` devolve uma linha NULL, que vira um chip VAZIO na tela e um
    `None` dentro do conjunto de nomes válidos de `atualizar`."""
    return [r["disciplina"] for r in db.query(
        """SELECT DISTINCT disciplina FROM documento
            WHERE disciplina IS NOT NULL
              AND (usuario_id IS NULL OR usuario_id = %(u)s)
            ORDER BY 1""", {"u": usuario_id})]


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


def _topicos_cobertos(edital_id: int | None, usuario_id: int) -> int:
    """
    Import LOCAL, não no topo: `core/edital.py` já importa este módulo (usa
    `filtro()` em `probabilidade_fechamento`). Importar de volta lá em cima
    fecharia o ciclo e quebraria a carga do pacote.
    """
    if not edital_id:
        return 0
    from . import edital as edital_mod
    return sum(c["topicos_no_edital"] - c["topicos_pendentes_estimado"]
               for c in edital_mod.cobertura(edital_id, usuario_id))


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

    `topicos_cobertos` é o MESMO número que `probabilidade_fechamento()` já
    usa pra estimar ritmo — por isso ele sai de `edital.cobertura()`, a
    função, e não de um SQL parecido escrito aqui. É a aproximação 2
    declarada em core/edital.py: não existe vínculo questão→tópico, então a
    cobertura de uma disciplina é a das QUESTÕES dela, aplicada aos tópicos
    daquela disciplina (média por disciplina, ponderada por quantos tópicos
    o edital dá a cada uma). Não é "90 tópicos revisados"; é "o equivalente
    a 90 tópicos, se a dificuldade for uniforme dentro da disciplina".

    N+1 consultas de propósito: cada mesa tem uma lista de disciplinas
    diferente, então não há um GROUP BY único que sirva. Uma conta tem
    unidades de mesas, não milhares — e a alternativa (materializar
    cobertura numa coluna) criaria estado a invalidar toda vez que alguém
    responde uma questão.
    """
    mesas = db.query(
        """SELECT m.id, m.nome, m.orgao, m.banca, m.criado_em,
                  m.biblioteca_compartilhada,
                  -- Quantos materiais esta mesa subiu (021). O número é o que
                  -- torna a decisão de isolar informada: "isolar" numa mesa sem
                  -- material nenhum significa deixar o tutor só com a lei seca,
                  -- e a pessoa tem que ver isso ANTES de desligar.
                  (SELECT count(*) FROM documento d
                    WHERE d.mesa_id = m.id) AS materiais,
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
        m["origem_alvo"] = origem_do_alvo(m["id"])
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
        m["topicos_cobertos"] = _topicos_cobertos(m["edital_id"], usuario_id)
        m["cobertura_topicos_pct"] = (round(100.0 * m["topicos_cobertos"] / m["topicos"], 1)
                                      if m["topicos"] else 0.0)
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
              orgao: str | None = None, banca: str | None = None,
              disciplinas_manuais: list[str] | None = None,
              biblioteca_compartilhada: bool | None = None) -> dict | None:
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
    # Só disciplinas que EXISTEM no acervo entram. Nome livre viraria filtro
    # que nunca casa nada, e o sintoma seria fila vazia sem explicação — o
    # aluno acharia que o app quebrou, não que escolheu matéria inexistente.
    # `None` preserva o que está lá; `[]` limpa (é como se tira o alvo).
    #
    # RECUSA em vez de descartar em silêncio. A versão anterior filtrava o que
    # não casava e gravava o resto, então a tela dizia "salvo" e a matéria
    # digitada simplesmente não estava lá — o aluno via a lista voltar menor e
    # não tinha como saber por quê. Mesmo princípio de `diagnostico.py` e de
    # `candidatos_data_prova`: reportar pro operador conferir, nunca decidir
    # calado. Falha alta também protege qualquer chamador futuro (import,
    # script) de gravar um alvo pela metade achando que gravou inteiro.
    if disciplinas_manuais is not None:
        validas = set(disciplinas_do_acervo(usuario_id))
        pedidas = [d.strip() for d in disciplinas_manuais if (d or "").strip()]
        fora = sorted({d for d in pedidas if d not in validas})
        if fora:
            raise ErroMesa(
                "o acervo ainda não tem material de: " + ", ".join(fora)
                + ". Suba material dessa matéria em Meus materiais e ela aparece aqui.")
        disciplinas_manuais = sorted(set(pedidas))

    return db.exec1(
        f"""UPDATE mesa SET nome = %(n)s,
                            orgao = COALESCE(%(o)s, orgao),
                            banca = COALESCE(%(b)s, banca),
                            disciplinas_manuais = COALESCE(%(dm)s, disciplinas_manuais),
                            -- `None` preserva: um PATCH que só troca o nome não
                            -- pode religar a biblioteca compartilhada de volta.
                            biblioteca_compartilhada =
                                COALESCE(%(bc)s, biblioteca_compartilhada)
             WHERE id = %(id)s AND usuario_id = %(u)s RETURNING {CAMPOS}""",
        {"id": mesa_id, "u": usuario_id, "n": novo_nome, "o": orgao, "b": banca,
         "dm": disciplinas_manuais, "bc": biblioteca_compartilhada},
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
    return {**m, "disciplinas": disciplinas(m["id"]),
            "origem_alvo": origem_do_alvo(m["id"])}
