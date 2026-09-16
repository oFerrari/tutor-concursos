"""
FEEDBACK DO ALUNO SOBRE A RESPOSTA, dito dentro do próprio chat (029).

POR QUE ESTE MÓDULO EXISTE
--------------------------
O relato de defeito do tutor sempre atravessou um vale: o aluno vê a resposta
ruim, sai do estudo, abre outra ferramenta e descreve de memória o que
aconteceu. O que se perde na travessia é o que resolveria o caso — qual
resposta, com quais trechos recuperados, em que ponto da conversa. Print ajuda e
não basta: ele não traz o `fontes` daquele turno nem os oito turnos anteriores.

`/erro isso está errado, peculato culposo não é isso` resolve sem sair da tela, e
grava a FK da resposta comentada. Dali sai a conversa inteira, literal.

É REGRA, NÃO LLM, pelo mesmo motivo de `pedido.py` e `assunto.py`: reconhecer um
comando que começa com barra é trabalho de `startswith`, e mandar isso pro
modelo custaria cota e um segundo pra decidir o que não tem dúvida. E o comando
NÃO VAI pro modelo — é a única fala do aluno que não vira turno de conversa.

O QUE ELE NÃO FAZ
-----------------
Não grava o comando em `mensagem`. A conversa é o contexto de estudo, e
"/erro você errou" no meio dela viraria histórico que o próximo turno lê como
matéria. O feedback fica na fila; a conversa segue como se ele não tivesse
falado — que é exatamente a experiência de anotar um bilhete à margem.
"""
import re

from . import db

VERSAO = "melhoria-v1"

# Os dois comandos, e a barra é obrigatória: "erro" e "feedback" são palavras
# comuns numa conversa sobre estudo ("meu erro foi na alternativa b"), e
# interceptar pela palavra solta calaria o tutor no meio de uma dúvida legítima.
# O texto DEPOIS do comando é o feedback; sem ele não há o que gravar.
RE_COMANDO = re.compile(r"(?i)^\s*/(erro|feedback|bug)\b[:\s]*(?P<texto>.*)\s*$", re.DOTALL)


def comando(fala: str | None) -> str | None:
    """A fala é um comando de feedback? Devolve o TEXTO dele, ou `None`.

    Devolve string VAZIA quando o comando veio sem texto (`/erro` sozinho) — e
    isso é diferente de `None`: a rota precisa distinguir "não é comando" de "é
    comando e falta o quê", pra pedir o que falta em vez de mandar pro modelo.
    """
    m = RE_COMANDO.match(fala or "")
    return None if not m else " ".join(m.group("texto").split())


def ultima_do_tutor(conversa_id: int) -> int | None:
    """O id da última resposta do tutor nesta conversa.

    É o alvo do feedback. `None` quando ele reclamou antes de o tutor ter dito
    qualquer coisa — estado legítimo, não erro (ver a 029).
    """
    linha = db.exec1(
        """SELECT id FROM mensagem
            WHERE conversa_id = %(c)s AND autor = 'tutor'
            ORDER BY id DESC LIMIT 1""",
        {"c": conversa_id})
    return linha["id"] if linha else None


def registrar(conversa_id: int, texto: str) -> dict:
    """Grava o feedback preso à resposta que ele comenta.

    Quem garante que a conversa é de quem está falando é a ROTA, que já passou
    por `conversa.obter(uid, ...)` antes de chegar aqui — mesma doutrina de
    porta única do `questoes.do_aluno()`. Repetir a checagem aqui criaria uma
    segunda regra de posse pra divergir da primeira.
    """
    return db.exec1(
        """INSERT INTO fila_melhoria (conversa_id, mensagem_tutor_id, feedback_texto)
           VALUES (%(c)s, %(m)s, %(t)s)
           RETURNING id, conversa_id, mensagem_tutor_id, criado_em, status""",
        {"c": conversa_id, "m": ultima_do_tutor(conversa_id), "t": texto.strip()})


def pendentes(limite: int = 50) -> list[dict]:
    """A fila, com o turno comentado junto — é assim que ela serve pra depurar.

    Devolve a resposta do tutor e as fontes DAQUELE turno na mesma linha: sem
    isso, ler a fila seria abrir o banco de novo a cada item, e quem lê está
    justamente atrás do contexto."""
    return db.query(
        """SELECT f.id, f.conversa_id, f.mensagem_tutor_id,
                  f.feedback_texto, f.criado_em, f.status,
                  c.titulo AS conversa_titulo,
                  m.texto  AS resposta_do_tutor,
                  m.fontes AS fontes_do_turno
             FROM fila_melhoria f
             JOIN conversa c ON c.id = f.conversa_id
             LEFT JOIN mensagem m ON m.id = f.mensagem_tutor_id
            WHERE f.status = 'pendente'
            ORDER BY f.criado_em DESC
            LIMIT %(l)s""",
        {"l": limite})
