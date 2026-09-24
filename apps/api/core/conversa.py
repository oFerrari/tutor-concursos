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

VERSAO = "conversa-v4"

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
