"""
Simulado — sessão sob condição de prova.

Diferença deliberada em relação a `estudar` (chat.py): aqui não há dica, não
há diálogo socrático questão a questão, e o gabarito só aparece na revisão
final. É a mesma diferença entre treino e prova — dar andaime durante a
prova mede a ajuda, não o aluno.

Reaproveita `scheduler.registrar`: acerto num simulado É acerto, e deve
alimentar a caixa e o caderno de erros como qualquer outro. Como aqui nunca
há dica, `dicas_usadas` é sempre 0, então todo acerto promove — não é um
caso especial, é a mesma regra de sempre vendo o mesmo sinal limpo.

Seleção de questões é amostra aleatória sobre TODO o acervo COMPARTILHADO,
não sobre a fila do dia de ninguém: a fila prioriza o que venceu PARA UM
usuário; o simulado testa o conjunto inteiro, porque é isso que a prova
real vai cobrar — por isso `selecionar()` não recebe usuario_id, só
`iniciar`/`historico` (que são posse pessoal da sessão de prova).

MULTIUSUÁRIO: `simulado` agora carrega usuario_id — funções que recebem um
`simulado_id` específico (`finalizar`, `relatorio`, `erros_do`) TAMBÉM
recebem `usuario_id` e filtram por ele, não só por confiar no id numérico.
Sem isso, adivinhar um simulado_id de outra pessoa devolveria o relatório
dela — o dado sensível aqui é resposta e desempenho, não o id em si.

Limitação conhecida: `sincronizar.py` não exporta `simulado`/`simulado_id`.
Aceitável porque simulado é snapshot de desempenho, não fonte de verdade —
o que importa (caixa, prox_revisao) já viaja pela tentativa comum.
"""
from . import db, mesa, scheduler, socratic

VERSAO = "simulado-v8"

N_PADRAO = 20


def selecionar(n: int = N_PADRAO, disciplina: str | None = None,
               disciplinas: list[str] | None = None) -> list[dict]:
    """
    DOIS filtros de disciplina, que respondem a perguntas diferentes:
    `disciplina` é escolha explícita de quem pediu a prova ("simulado só de
    Penal"); `disciplinas` é o recorte da mesa (o que o edital cobra). Os
    dois valem ao mesmo tempo — pedir "só Penal" numa mesa que não cobra
    Penal devolve vazio, e isso é a resposta certa, não um bug.
    """
    return db.query(
        f"""SELECT q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.tipo,
                   q.gabarito_ce, q.contexto_id, q.ordem_no_contexto, x.texto AS contexto
           FROM questao q
           LEFT JOIN contexto x ON x.id = q.contexto_id
           WHERE (%(d)s::text IS NULL OR q.disciplina = %(d)s)
             AND {mesa.filtro('q.disciplina')}
           ORDER BY random()
           LIMIT %(n)s""",
        {"n": n, "d": disciplina, "disc": disciplinas},
    )


def pertence_a(simulado_id: int, usuario_id: int) -> bool:
    """
    Checagem de posse ANTES de aceitar respostas — achado testando
    isolamento multiusuário: sem isso, `POST /simulados/{sid}/respostas`
    processava `sid` de QUALQUER pessoa (o id só identifica a sessão, não
    quem pode responder por ela). `scheduler.registrar` grava a tentativa
    com o usuario_id de quem chamou, então a CAIXA de ninguém vaza — mas
    a tentativa fica com o `simulado_id` alheio, e `historico()` (join só
    por simulado_id, sem usuario_id) contava essa tentativa "estrangeira"
    na nota do simulado de quem nunca pediu aquela resposta.
    """
    return db.exec1(
        "SELECT 1 FROM simulado WHERE id = %(id)s AND usuario_id = %(u)s",
        {"id": simulado_id, "u": usuario_id},
    ) is not None


def iniciar(usuario_id: int, n_questoes: int, minutos_alvo: int | None = None,
            mesa_id: int | None = None, questao_ids: list[int] | None = None,
            nome: str | None = None) -> int:
    """`mesa_id` é ETIQUETA, não posse — quem responde pela prova continua
    sendo `usuario_id` (é o que `pertence_a()` checa). Serve pra
    `historico()` conseguir dizer "as provas DESTA mesa"; apagar a mesa
    depois deixa o simulado com mesa_id nulo, não apaga a prova (ver a
    política de FK na migração 010).

    `questao_ids` (migração 018) é o que torna a prova RETOMÁVEL: sem
    gravar aqui quais N questões foram sorteadas, `estado()` não teria como
    reconstruir a prova depois de a aba fechar — o array só existia até
    agora na resposta HTTP, que some se a conexão cair antes do fim.

    `nome` (migração 019) é opcional e livre — não vai pro prompt de
    nenhum LLM (diferente de `usuario.perfil`), então não precisa da
    validação fechada que `core/auth.CAMPOS_PERFIL` exige; string vazia
    vira `None` pra tela cair no rótulo por data."""
    r = db.exec1(
        """INSERT INTO simulado (usuario_id, mesa_id, n_questoes, minutos_alvo, questao_ids, nome)
           VALUES (%(u)s, %(mesa)s, %(n)s, %(m)s, %(q)s, %(nome)s) RETURNING id""",
        {"u": usuario_id, "mesa": mesa_id, "n": n_questoes, "m": minutos_alvo,
         "q": questao_ids, "nome": (nome or "").strip() or None},
    )
    return r["id"]


def apagar(simulado_id: int, usuario_id: int) -> bool:
    """Remove a prova do histórico. NÃO apaga tentativa/progresso — a FK
    (`ON DELETE SET NULL`, migração 004) só solta o vínculo; o que foi
    aprendido respondendo essas questões continua contando pra caixa e pro
    desempenho, exatamente como uma questão respondida pela fila comum.
    Só a ETIQUETA "isso foi uma prova" some."""
    r = db.query(
        "DELETE FROM simulado WHERE id = %(id)s AND usuario_id = %(u)s RETURNING id",
        {"id": simulado_id, "u": usuario_id},
    )
    return len(r) > 0


def corrigir(questao: dict, resposta: str) -> dict:
    """
    Correção única, sem histórico e sem segunda chance — é assim que sai
    numa prova real. Resposta em branco nem vai ao LLM: é erro por definição.
    """
    if not resposta.strip():
        return {"veredito": "incorreta", "comentario": "(em branco)",
                "pergunta": "", "conceito_faltante": ""}
    # Dispatcher: item C/E vira comparação booleana, sem LLM — numa prova
    # de 40 itens Cebraspe isso é a diferença entre 40 chamadas e nenhuma.
    return socratic.avaliar_questao(questao, resposta, nivel=0)


def responder_uma(simulado_id: int, usuario_id: int, questao_id: int,
                   resposta: str, segundos_pergunta: int,
                   segundos_acumulados: int) -> dict:
    """
    Salva UMA resposta IMEDIATAMENTE, não no final (migração 018) — é o que
    faz o simulado sobreviver a aba fechada, conexão caindo ou bateria
    acabando no meio da prova. A correção acontece aqui mesmo (silenciosa:
    o front não recebe o veredito de volta, só confirmação de que salvou)
    — isso NÃO viola "simulado só corrige no final" (ver core/simulado.py):
    o aluno continua sem ver acerto/erro até `finalizar()`, só o CÁLCULO
    deixou de ficar todo empilhado pro fim.

    REVISÃO (voltar pra uma questão já respondida e mudar): uma prova real
    deixa revisar antes de entregar — proibir isso é pior que o problema
    que a checagem de idempotência tentava evitar. Por isso a 2ª chamada
    pra mesma questão AGORA atualiza (não pula) o texto/veredito da
    tentativa. O que ela NÃO faz é tocar em `progresso`/caixa de novo: a
    promoção SM-2 já aconteceu na 1ª resposta, e reverter/reaplicar caixa a
    cada revisão exigiria saber o estado ANTERIOR pra desfazer — reincidir
    nisso é caro e arriscado pra um caso que hoje não é o objetivo (medir
    domínio), é só deixar a NOTA da prova refletir a escolha final.
    """
    if not pertence_a(simulado_id, usuario_id):
        raise ValueError(f"simulado {simulado_id} não encontrado")

    existente = db.exec1(
        "SELECT id FROM tentativa WHERE simulado_id = %(s)s AND questao_id = %(q)s",
        {"s": simulado_id, "q": questao_id},
    )
    q = db.exec1(
        "SELECT id, tema, enunciado, gabarito, tipo, gabarito_ce FROM questao WHERE id = %(id)s",
        {"id": questao_id},
    )
    if not q:
        raise ValueError(f"questão {questao_id} não existe")
    av = corrigir(q, resposta)

    if existente:
        db.exec1(
            "UPDATE tentativa SET resposta = %(r)s, veredito = %(v)s, segundos = %(s)s WHERE id = %(id)s",
            {"r": resposta, "v": av["veredito"], "s": segundos_pergunta, "id": existente["id"]},
        )
    else:
        scheduler.registrar(usuario_id, questao_id, av["veredito"], resposta, 0,
                            segundos_pergunta, simulado_id=simulado_id,
                            conceito_faltante=av.get("conceito_faltante"))

    atualizar_tempo(simulado_id, usuario_id, segundos_acumulados)
    return {"ok": True, "ja_respondida": existente is not None}


def atualizar_tempo(simulado_id: int, usuario_id: int, segundos_acumulados: int) -> None:
    """
    Só o relógio, sem responder nada — pra "pausar" e "sair" salvarem o
    tempo decorrido mesmo quando a pessoa não respondeu mais nenhuma
    questão nesta visita. Sem isso, o único jeito de `segundos_acumulados`
    chegar ao banco era `responder_uma()`, e quem pausava/saía sem
    responder nada de novo perdia o tempo que passou ali — reabrir a prova
    depois voltava contando de onde a ÚLTIMA RESPOSTA tinha parado, não de
    onde a pessoa realmente parou.
    """
    db.exec1(
        "UPDATE simulado SET segundos_acumulados = %(s)s WHERE id = %(id)s AND usuario_id = %(u)s "
        "RETURNING id",
        {"s": segundos_acumulados, "id": simulado_id, "u": usuario_id},
    )


def estado(simulado_id: int, usuario_id: int) -> dict | None:
    """
    Reconstrói a prova pra RETOMAR de onde parou: as N questões na MESMA
    ordem do sorteio original (`questao_ids`, migração 018), marcando quais
    já têm tentativa (pra pular na tela) e devolvendo o relógio acumulado.
    `None` se o simulado não existe ou não é deste usuário — mesmo 404
    silencioso de `pertence_a()`.
    """
    s = db.exec1(
        "SELECT id, nome, questao_ids, minutos_alvo, segundos_acumulados, segundos_total FROM simulado "
        "WHERE id = %(id)s AND usuario_id = %(u)s",
        {"id": simulado_id, "u": usuario_id},
    )
    if not s or not s["questao_ids"]:
        return None

    # resposta_dada (não só SE respondeu) é o que permite VOLTAR pra uma
    # questão já respondida e ver/editar o que foi escrito — sem isso, a
    # tela só sabia "respondida: true" e reabria o campo em branco, como se
    # a pessoa nunca tivesse escrito nada.
    respostas_dadas = {
        r["questao_id"]: r["resposta"]
        for r in db.query(
            "SELECT questao_id, resposta FROM tentativa WHERE simulado_id = %(id)s",
            {"id": simulado_id},
        )
    }
    qmap = {
        q["id"]: q
        for q in db.query(
            """SELECT q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.tipo,
                      q.gabarito_ce, q.contexto_id, q.ordem_no_contexto, x.texto AS contexto
               FROM questao q LEFT JOIN contexto x ON x.id = q.contexto_id
               WHERE q.id = ANY(%(ids)s)""",
            {"ids": s["questao_ids"]},
        )
    }
    # Preserva a ORDEM original do sorteio (`questao_ids`), não a ordem que
    # voltou do banco — questão sumida do acervo (raríssimo, mas possível)
    # some da lista em vez de quebrar a reconstrução.
    questoes = [
        {
            **qmap[qid],
            "respondida": qid in respostas_dadas,
            "resposta_dada": respostas_dadas.get(qid),
        }
        for qid in s["questao_ids"] if qid in qmap
    ]
    return {
        "id": s["id"],
        "nome": s["nome"],
        "questoes": questoes,
        "minutos_alvo": s["minutos_alvo"],
        "segundos_acumulados": s["segundos_acumulados"],
        "finalizado": s["segundos_total"] is not None,
    }




def _preencher_faltantes(simulado_id: int, usuario_id: int) -> None:
    """
    Registra "em branco" (incorreta, por definição — ver `corrigir()`) pra
    toda questão do sorteio original que ainda não tem tentativa. Existe
    porque "finalizar agora" é permitido a qualquer momento — parar na 1ª
    de 10 é direito de quem está fazendo a prova, o sistema não tem por que
    barrar (nem tem como saber se é cansaço, emergência ou só quis medir
    5 minutos hoje). Sem isso, a nota saía sobre o que foi RESPONDIDO
    (1/1 = 100%) em vez de sobre o que foi PEDIDO (1/10 = 10%) — uma prova
    real não te dá 100% por ter deixado 9 em branco, ela te dá 10%.
    """
    s = db.exec1(
        "SELECT questao_ids FROM simulado WHERE id = %(id)s AND usuario_id = %(u)s",
        {"id": simulado_id, "u": usuario_id},
    )
    if not s or not s["questao_ids"]:
        return  # simulado antigo, de antes da migração 018 — sem lista, sem como saber o que falta
    respondidas = {
        r["questao_id"]
        for r in db.query(
            "SELECT questao_id FROM tentativa WHERE simulado_id = %(id)s",
            {"id": simulado_id},
        )
    }
    for qid in s["questao_ids"]:
        if qid not in respondidas:
            scheduler.registrar(usuario_id, qid, "incorreta", "", 0, None, simulado_id=simulado_id)


def finalizar(simulado_id: int, usuario_id: int, segundos_total: int) -> dict:
    """Nota sai de GROUP BY sobre tentativa, não de contador mantido à mão.
    `WHERE ... AND usuario_id` faz dupla função: escopo E checagem de posse."""
    _preencher_faltantes(simulado_id, usuario_id)
    db.exec1(
        "UPDATE simulado SET segundos_total = %(s)s WHERE id = %(id)s AND usuario_id = %(u)s "
        "RETURNING id",
        {"s": segundos_total, "id": simulado_id, "u": usuario_id},
    )
    return resultado(simulado_id, usuario_id)


def resultado(simulado_id: int, usuario_id: int) -> dict:
    """Como `finalizar()`, mas só LÊ — não mexe em `segundos_total` nem
    preenche faltante. É o que a tela usa pra REABRIR a revisão de uma
    prova já fechada (histórico → "ver revisão"), sem re-finalizar nada."""
    r = db.exec1(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE veredito = 'correta')  AS acertos,
                  count(*) FILTER (WHERE veredito = 'parcial')  AS parciais,
                  count(*) FILTER (WHERE veredito = 'incorreta') AS erros
           FROM tentativa WHERE simulado_id = %(id)s AND usuario_id = %(u)s""",
        {"id": simulado_id, "u": usuario_id},
    ) or {"total": 0, "acertos": 0, "parciais": 0, "erros": 0}
    r["nota_pct"] = round(100.0 * r["acertos"] / r["total"], 1) if r["total"] else 0.0
    return r


def relatorio(simulado_id: int, usuario_id: int) -> list[dict]:
    """Desempenho por disciplina DENTRO deste simulado — não é a v_desempenho global."""
    return db.query(
        """SELECT q.disciplina,
                  count(*)                                          AS questoes,
                  count(*) FILTER (WHERE t.veredito = 'correta')     AS acertos,
                  round(100.0 * count(*) FILTER (WHERE t.veredito = 'correta')
                        / count(*), 1)::float8                       AS pct
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.simulado_id = %(id)s AND t.usuario_id = %(u)s
           GROUP BY q.disciplina ORDER BY pct""",
        {"id": simulado_id, "u": usuario_id},
    )


def erros_do(simulado_id: int, usuario_id: int) -> list[dict]:
    """Questões erradas ou parciais, para a revisão final — com resposta dada e gabarito."""
    return db.query(
        """SELECT q.tema, q.enunciado, q.gabarito, t.resposta, t.veredito
           FROM tentativa t JOIN questao q ON q.id = t.questao_id
           WHERE t.simulado_id = %(id)s AND t.usuario_id = %(u)s AND t.veredito <> 'correta'
           ORDER BY t.id""",
        {"id": simulado_id, "u": usuario_id},
    )


def historico(usuario_id: int, limite: int = 10, mesa_id: int | None = None) -> list[dict]:
    """`mesa_id=None` devolve o histórico inteiro da conta (é o que a CLI e
    as versões anteriores à 010 faziam). Com mesa, só as provas etiquetadas
    com ela — as de mesa apagada (mesa_id nulo) somem da visão filtrada mas
    continuam existindo na visão geral, que é o ponto de terem sobrevivido.

    `em_andamento` (migração 018/019): a lista já incluía prova não
    finalizada antes disso — só não dava pra distinguir na tela, que
    mostrava uma prova com metade das questões como se fosse uma nota
    real. Agora a tela sabe: em vez de nota, mostra "continuar" na
    própria linha."""
    return db.query(
        """SELECT s.id, s.nome, s.n_questoes, s.minutos_alvo, s.segundos_total, s.criado_em,
                  s.segundos_total IS NULL                          AS em_andamento,
                  count(t.id) FILTER (WHERE t.veredito = 'correta') AS acertos,
                  -- só o que a pessoa TOCOU de verdade — não o que
                  -- `_preencher_faltantes()` gravou em branco ao finalizar
                  -- cedo (essas linhas têm segundos IS NULL, único jeito de
                  -- distinguir "respondeu" de "sistema marcou errado por
                  -- omissão" sem coluna nova).
                  count(t.id) FILTER (WHERE t.segundos IS NOT NULL)  AS respondidas,
                  round(100.0 * count(t.id) FILTER (WHERE t.veredito = 'correta')
                        / NULLIF(count(t.id), 0), 1)::float8        AS nota_pct
           -- t.usuario_id = s.usuario_id além de t.simulado_id = s.id: defesa em
           -- profundidade contra a mesma classe de bug que motivou pertence_a()
           -- acima — se algum dia outra rota inserir tentativa com simulado_id
           -- alheio de novo, ela ainda não entra na nota de quem não pediu.
           FROM simulado s LEFT JOIN tentativa t ON t.simulado_id = s.id AND t.usuario_id = s.usuario_id
           WHERE s.usuario_id = %(u)s
             AND (%(mesa)s::bigint IS NULL OR s.mesa_id = %(mesa)s)
           GROUP BY s.id ORDER BY s.criado_em DESC LIMIT %(l)s""",
        {"u": usuario_id, "l": limite, "mesa": mesa_id},
    )
