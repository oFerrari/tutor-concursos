"""
Conversa do tutor — persistida, e com o histórico voltando pro modelo.

POR QUE ISTO EXISTE (migração 014)
----------------------------------
`POST /perguntar` recebia só a pergunta atual. O histórico vivia no estado
do componente React e sumia num F5, e o modelo NUNCA o via — cada mensagem
chegava como se fosse a primeira. Em uso isso aparece assim: o aluno
responde "qualquer um" e o tutor pergunta de volta "qualquer um de quê?".

O padrão já existia no projeto: `socratic.avaliar()` recebe os turnos
anteriores por parâmetro, justamente porque sem eles o modelo reformulava a
pergunta-guia do zero a cada rodada. Aqui é a mesma lição aplicada ao chat
livre, com um lugar pra guardar entre sessões.

QUANTOS TURNOS VOLTAM, E POR QUE UM TETO
----------------------------------------
`JANELA` limita o histórico enviado. Não é economia mesquinha: o contexto
do prompt já carrega os trechos de lei recuperados (6 chunks, alguns com
milhares de caracteres) e o resumo de desempenho. Uma conversa de 40 turnos
empurraria o material — a parte que ANCORA a resposta — pra fora da janela
do modelo, e o tutor passaria a responder de memória própria em vez de da
lei. Preferimos esquecer o turno 1 a esquecer o art. 37.

TÍTULO VEM DA PRIMEIRA PERGUNTA, sem LLM: gastar uma chamada pra resumir
"o que diz o art. 312?" em três palavras é pagar por enfeite. Truncar a
pergunta é honesto e reconhecível na lista.

E É REFEITO NA PRIMEIRA AULA (`retitular`): conversa que abre com "boa noite"
ficava "boa noite" na lista de Recentes, sobre proposições (medido em
22/09/2026). O primeiro turno com fonte CITADA é onde a matéria aparece; dali
em diante o título não muda mais.
"""
import re

from . import db, diario

VERSAO = "conversa-v7"

JANELA = 8          # turnos (aluno+tutor) devolvidos como histórico
MAX_TITULO = 60


def _titulo_de(pergunta: str) -> str:
    limpa = " ".join((pergunta or "").split())
    if len(limpa) <= MAX_TITULO:
        return limpa or "conversa"
    return limpa[:MAX_TITULO].rsplit(" ", 1)[0] + "…"


PALAVRAS_PARA_TITULO = 3   # abaixo disso a fala é "sim", "pode", "explica peculato"


def titulo_da_aula(pergunta: str, citadas: list[dict]) -> str | None:
    """O título do turno em que a aula começou, ou None se ela não começou.

    PURO. A fala do aluno quando ela diz do que se trata; o assunto dos
    trechos citados quando ela é curta demais pra dizer ("sim, pode")."""
    if not citadas:
        return None
    if len(re.findall(r"\w{4,}", pergunta or "")) >= PALAVRAS_PARA_TITULO:
        return _titulo_de(pergunta)
    r = diario.rotulo(citadas)
    return _titulo_de(r[0] if r else pergunta)


def retitular(conversa_id: int, pergunta: str, citadas: list[dict]) -> str | None:
    """Troca o título pelo da primeira aula; depois dela, não mexe mais.

    Chamar ANTES de gravar a resposta do tutor deste turno: "primeira aula" é
    nenhuma mensagem anterior do tutor com fonte citada."""
    titulo = titulo_da_aula(pergunta, citadas)
    if not titulo:
        return None
    r = db.exec1(
        """UPDATE conversa SET titulo = %(t)s
            WHERE id = %(c)s
              AND NOT EXISTS (SELECT 1 FROM mensagem
                               WHERE conversa_id = %(c)s AND autor = 'tutor'
                                 AND fontes @> '[{"citada": true}]')
           RETURNING titulo""",
        {"t": titulo, "c": conversa_id})
    return r["titulo"] if r else None


def ultima_leitura(conversa_id: int) -> dict | None:
    """Onde a leitura em sequência parou nesta conversa (`core/leitura.py`).

    Lê `mensagem.fontes` das últimas respostas do tutor: a mais recente com
    fonte `sequencial` é o marcador, e o maior `ordem` dela é o ponto. Nenhum
    estado novo — é o registro do que o tutor usou, que já existia.
    `foi_a_ultima` diz se a resposta mais recente do tutor foi de leitura: é o
    que decide se um "certo" do aluno avança a leitura ou responde a uma pergunta."""
    respostas = db.query(
        """SELECT fontes FROM mensagem
            WHERE conversa_id = %(c)s AND autor = 'tutor'
            ORDER BY id DESC LIMIT 20""", {"c": conversa_id})
    for i, r in enumerate(respostas):
        lidas = [f for f in (r["fontes"] or []) if f.get("sequencial") and f.get("ordem") is not None]
        if lidas:
            return {"documento_id": lidas[-1]["documento_id"],
                    "ordem": max(f["ordem"] for f in lidas),
                    "ids": [f["id"] for f in lidas],
                    "foi_a_ultima": i == 0}
    return None


def trechos_lidos(usuario_id: int, dias: int = 90) -> set[int]:
    """Todos os trechos que o aluno já leu em sequência, em qualquer conversa —
    é o que diz à leitura "na ordem do edital" qual ponto já foi visto."""
    return {r["id"] for r in db.query(
        """SELECT DISTINCT (f->>'id')::bigint AS id
             FROM mensagem m JOIN conversa c ON c.id = m.conversa_id,
                  jsonb_array_elements(m.fontes) f
            WHERE c.usuario_id = %(u)s AND m.autor = 'tutor'
              AND m.criada_em > now() - make_interval(days => %(d)s)
              AND (f->>'sequencial')::boolean""", {"u": usuario_id, "d": dias})}


def marcadores_de_leitura(usuario_id: int, dias: int = 90) -> dict[int, dict]:
    """Onde o aluno parou em CADA material, em todas as conversas dele.

    {documento_id: {"ordem", "quando"}} — a posição da resposta de leitura MAIS
    RECENTE de cada material (não o maior `ordem` já lido: quem recomeçou do
    zero está no começo). Sem estado novo: é `mensagem.fontes`, como
    `ultima_leitura`. Medido em 24/09/2026: trocar de Constitucional para
    Administrativo e voltar recomeçava a apostila, porque o marcador só
    enxergava a última leitura da conversa."""
    marcadores: dict[int, dict] = {}
    for r in db.query(
            """SELECT m.fontes, m.criada_em FROM mensagem m JOIN conversa c ON c.id = m.conversa_id
                WHERE c.usuario_id = %(u)s AND m.autor = 'tutor'
                  AND m.criada_em > now() - make_interval(days => %(d)s)
                  AND m.fontes @> '[{"sequencial": true}]'
                ORDER BY m.id""", {"u": usuario_id, "d": dias}):
        lidas = [f for f in r["fontes"] if f.get("sequencial") and f.get("ordem") is not None
                 and f.get("documento_id")]
        if lidas:
            marcadores[lidas[-1]["documento_id"]] = {"ordem": max(f["ordem"] for f in lidas),
                                                     "quando": r["criada_em"]}
    return marcadores


def trechos_citados_recentes(conversa_id: int, respostas: int = 3) -> list[int]:
    """Os trechos que a última resposta do tutor COM fonte citada usou — é o
    "isto" de "quero questões sobre isto". Até 3 respostas para trás: o pedido de
    treino no chat grava antes a própria resposta curta ("vamos treinar"), que
    não cita nada."""
    for r in db.query(
            """SELECT fontes FROM mensagem
                WHERE conversa_id = %(c)s AND autor = 'tutor'
                ORDER BY id DESC LIMIT %(l)s""", {"c": conversa_id, "l": respostas}):
        citados = [f["id"] for f in (r["fontes"] or []) if f.get("citada") and f.get("id")]
        if citados:
            return citados
    return []


def origem_da_ultima_resposta(conversa_id: int, respostas: int = 3) -> str | None:
    """De onde veio a última resposta do tutor que citou fonte: material e páginas,
    ou norma e artigo. É o que responde "qual aula e página sustentam isso?" —
    a busca, nessa pergunta, só traria trecho sorteado."""
    from .cobertura import paginas
    for r in db.query(
            """SELECT fontes FROM mensagem
                WHERE conversa_id = %(c)s AND autor = 'tutor'
                ORDER BY id DESC LIMIT %(l)s""", {"c": conversa_id, "l": respostas}):
        usadas = [f for f in (r["fontes"] or []) if f.get("citada") or f.get("sequencial")]
        if not usadas:
            continue
        grupos: dict[str, list | None] = {}
        for f in usadas:
            if f.get("artigo") and not f.get("material"):
                grupos[f"{f.get('norma') or f.get('titulo')}, art. {f['artigo']}"] = None
            else:
                grupos.setdefault(f.get("assunto") or f.get("titulo") or "material", []).append(f.get("pagina"))
        return "\n".join(f"- {nome}" + ("" if ps is None else
                                         f", p. {paginas(ps)}" if any(ps) else " (sem número de página)")
                         for nome, ps in grupos.items())
    return None


def material_recente(conversa_id: int, respostas: int = 6) -> int | None:
    """O material DO ALUNO de que a conversa está tratando: o citado mais
    recentemente nas últimas respostas do tutor (o consultado, se nenhum foi
    citado). É o que `leitura.escolher_material` usa quando o aluno pede "na
    ordem" sem nomear matéria — a fala dele é sobre estudar, e o assunto é o
    da conversa."""
    for r in db.query(
            """SELECT fontes FROM mensagem
                WHERE conversa_id = %(c)s AND autor = 'tutor'
                ORDER BY id DESC LIMIT %(l)s""", {"c": conversa_id, "l": respostas}):
        materiais = [f for f in (r["fontes"] or []) if f.get("material") and f.get("documento_id")]
        citados = [f for f in materiais if f.get("citada")]
        if citados or materiais:
            return (citados or materiais)[0]["documento_id"]
    return None


def criar(usuario_id: int, mesa_id: int | None, primeira_pergunta: str) -> dict:
    return db.exec1(
        """INSERT INTO conversa (usuario_id, mesa_id, titulo)
           VALUES (%(u)s, %(m)s, %(t)s)
           RETURNING id, titulo, mesa_id, criada_em, atualizada_em""",
        {"u": usuario_id, "m": mesa_id, "t": _titulo_de(primeira_pergunta)},
    )


def obter(usuario_id: int, conversa_id: int) -> dict | None:
    """SEMPRE escopado por usuario_id — pedir conversa de outra pessoa
    devolve None (que a API vira 404, não 403: não confirma pra quem chuta
    um id que ele existe e só não é dele). Mesmo espírito de `mesa.obter`."""
    return db.exec1(
        """SELECT id, titulo, mesa_id, criada_em, atualizada_em
             FROM conversa WHERE id = %(c)s AND usuario_id = %(u)s""",
        {"c": conversa_id, "u": usuario_id},
    )


def listar(usuario_id: int, limite: int = 12) -> list[dict]:
    """Recentes por ATIVIDADE, não por criação — conversa retomada ontem
    importa mais que uma aberta há um mês e abandonada. Sem recorte por
    mesa: a conversa é do aluno (mesma decisão de `progresso` na 010), e
    esconder o que ele discutiu porque trocou de concurso seria perder
    material que continua valendo."""
    return db.query(
        """SELECT c.id, c.titulo, c.mesa_id, c.atualizada_em, m.nome AS mesa_nome,
                  (SELECT count(*) FROM mensagem g
                    WHERE g.conversa_id = c.id
                      -- EVENTO NÃO É MENSAGEM PRA QUEM CONTA (016). Ele é fato
                      -- da sessão, escrito PRO MODELO e em segunda pessoa
                      -- dirigida ao tutor — não aparece como balão na tela.
                      -- Contá-lo faria a sidebar prometer 4 e a conversa
                      -- reaberta mostrar 3, e número que não confere com o que
                      -- se vê é o tipo de detalhe que faz duvidar do resto.
                      AND g.autor <> 'evento') AS mensagens
             FROM conversa c
             LEFT JOIN mesa m ON m.id = c.mesa_id
            WHERE c.usuario_id = %(u)s
            ORDER BY c.atualizada_em DESC
            LIMIT %(l)s""",
        {"u": usuario_id, "l": limite},
    )


def mensagens(conversa_id: int, limite: int | None = None) -> list[dict]:
    """Em ordem cronológica. `limite` pega as ÚLTIMAS N e devolve na ordem
    certa — o `ORDER BY id DESC` do subselect é só pra cortar pelo fim; ler
    a conversa de trás pra frente não é o que ninguém quer."""
    if limite is None:
        return db.query(
            "SELECT id, autor, texto, fontes, criada_em FROM mensagem "
            "WHERE conversa_id = %(c)s ORDER BY id",
            {"c": conversa_id},
        )
    return db.query(
        """SELECT * FROM (
             SELECT id, autor, texto, fontes, criada_em FROM mensagem
              WHERE conversa_id = %(c)s ORDER BY id DESC LIMIT %(l)s
           ) t ORDER BY id""",
        {"c": conversa_id, "l": limite},
    )


def com_rotulo_das_fontes(msgs: list[dict]) -> list[dict]:
    """Completa `assunto` e `pagina` das fontes gravadas antes de 24/09/2026.

    A tela passou a rotular material do aluno pelo assunto e pela página, e as
    mensagens antigas só guardavam o `titulo` — o nome do arquivo. Lido pelo id
    do trecho; trecho que já não existe (material reindexado) fica como estava."""
    faltam = {f["id"] for m in msgs for f in (m.get("fontes") or [])
              if f.get("id") and "assunto" not in f}
    if not faltam:
        return msgs
    rotulos = {r["id"]: r for r in db.query(
        """SELECT c.id, c.pagina, d.assunto FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE c.id = ANY(%(i)s) AND d.usuario_id IS NOT NULL""", {"i": list(faltam)})}
    for m in msgs:
        m["fontes"] = [{**f, "assunto": rotulos[f["id"]]["assunto"], "pagina": rotulos[f["id"]]["pagina"]}
                       if f.get("id") in rotulos and "assunto" not in f else f
                       for f in (m.get("fontes") or [])]
    return msgs


def reescrever(mensagem_id: int, texto: str) -> None:
    """Troca o texto de uma mensagem já gravada. Só para o caso em que ela ficou
    FALSA depois de gravada: o tutor anunciou as questões e o gerador falhou."""
    db.query("UPDATE mensagem SET texto = %(t)s WHERE id = %(i)s", {"t": texto, "i": mensagem_id})


def gravar(conversa_id: int, autor: str, texto: str, fontes: list | None = None) -> dict:
    """Grava a mensagem e marca a conversa como ativa AGORA. As duas coisas
    juntas porque `atualizada_em` só existe pra ordenar a lista de recentes;
    deixar a atualização a cargo de quem chama é convidar a lista a mentir
    na primeira rota que esquecer."""
    import json

    msg = db.exec1(
        """INSERT INTO mensagem (conversa_id, autor, texto, fontes)
           VALUES (%(c)s, %(a)s, %(t)s, %(f)s)
           RETURNING id, autor, texto, fontes, criada_em""",
        {"c": conversa_id, "a": autor, "t": texto, "f": json.dumps(fontes or [])},
    )
    db.query("UPDATE conversa SET atualizada_em = now() WHERE id = %(c)s", {"c": conversa_id})
    return msg


def registrar_evento(conversa_id: int, texto: str) -> dict:
    """
    Grava um FATO da sessão na linha do tempo da conversa: "respondeu a
    questão sobre peculato e errou".

    Não é fala de ninguém (ver db/016). Existe porque a informação mais
    valiosa de uma conversa de estudo não é o que o aluno DIZ, é o que ele
    DEMONSTRA — dizer "não entendi" é relato, errar a questão é evidência.
    Sem isto o tutor gera três itens, o aluno erra os três, e a mensagem
    seguinte continua explicando como se nada tivesse acontecido.
    """
    return gravar(conversa_id, "evento", texto)


def historico_para_prompt(conversa_id: int, janela: int = JANELA) -> list[dict]:
    """
    Últimos turnos no formato que `socratic.explicar` consome.

    Só `autor` e `texto`: as fontes de turnos passados NÃO voltam pro
    prompt. Elas são contexto de EXIBIÇÃO (o aluno reabre e vê o que
    sustentou aquela resposta); reinjetá-las faria o modelo citar
    dispositivo recuperado para outra pergunta, que é exatamente o defeito
    que `retrieval.buscar` evita ao NÃO acrescentar complemento semântico
    quando acerta o dispositivo exato.
    """
    return [{"autor": m["autor"], "texto": m["texto"]}
            for m in mensagens(conversa_id, limite=janela)]


def desfazer_ultimo_turno(usuario_id: int, conversa_id: int) -> dict | None:
    """Apaga o último turno e devolve a fala do aluno que estava nele.

    Existe pra dois gestos que o chat não tinha e o aluno espera de qualquer
    chat: PARAR a resposta e EDITAR a pergunta. Os dois deixam o histórico numa
    situação que a gravação em dois lados (014) não previa — a pergunta é
    gravada ANTES de chamar o modelo, de propósito, pra ninguém reabrir a
    conversa e não achar o que escreveu. Parando no meio, sobra uma pergunta
    sem resposta; editando, sobraria a versão errada junto da certa.

    Devolve a fala pra tela poder pré-preencher o campo — é o que faz "editar"
    ser editar, e não digitar tudo de novo.

    Apaga do FIM pra trás, e só o último par: apagar por texto igual pegaria a
    pergunta repetida três turnos antes, que é justamente o que acontece quando
    alguém insiste no mesmo assunto.

    `evento` entra na conta ("[fato da sessão]", 016): se o turno propôs
    questões, o fato de tê-las proposto vai junto — senão o prompt seguinte
    afirmaria uma proposta que não existe mais."""
    conv = obter(usuario_id, conversa_id)
    if not conv:
        return None
    linhas = db.query(
        """SELECT id, autor, texto FROM mensagem
            WHERE conversa_id = %(c)s ORDER BY id DESC LIMIT 6""",
        {"c": conversa_id})
    if not linhas:
        return None
    # Anda de trás pra frente até (e incluindo) a última fala do ALUNO.
    apagar_ids, fala = [], None
    for m in linhas:
        apagar_ids.append(m["id"])
        if m["autor"] == "aluno":
            fala = m["texto"]
            break
    if fala is None:
        return None
    db.query("DELETE FROM mensagem WHERE id = ANY(%(ids)s)", {"ids": apagar_ids})
    return {"pergunta": fala, "apagadas": len(apagar_ids)}


def apagar(usuario_id: int, conversa_id: int) -> bool:
    apagadas = db.query(
        "DELETE FROM conversa WHERE id = %(c)s AND usuario_id = %(u)s RETURNING id",
        {"c": conversa_id, "u": usuario_id},
    )
    return bool(apagadas)
