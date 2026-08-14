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
"""
from . import db

VERSAO = "conversa-v1"

JANELA = 8          # turnos (aluno+tutor) devolvidos como histórico
MAX_TITULO = 60


def _titulo_de(pergunta: str) -> str:
    limpa = " ".join((pergunta or "").split())
    if len(limpa) <= MAX_TITULO:
        return limpa or "conversa"
    return limpa[:MAX_TITULO].rsplit(" ", 1)[0] + "…"


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
                  (SELECT count(*) FROM mensagem g WHERE g.conversa_id = c.id) AS mensagens
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


def apagar(usuario_id: int, conversa_id: int) -> bool:
    apagadas = db.query(
        "DELETE FROM conversa WHERE id = %(c)s AND usuario_id = %(u)s RETURNING id",
        {"c": conversa_id, "u": usuario_id},
    )
    return bool(apagadas)
