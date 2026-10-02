"""
Acesso direto ao banco de questões — compartilhado entre usuários por
padrão (a questão em si não pertence a ninguém; progresso é que é pessoal,
e mora em `progresso`/`tentativa`).

A EXCEÇÃO É A QUESTÃO GERADA DO MATERIAL PRIVADO (026), que tem dono. O
predicado que separa as duas coisas mora aqui, em `do_aluno()`, e é este
módulo que todo pool importa.

Extraído como módulo próprio porque `api.py` precisa buscar uma questão
por id fora do contexto de fila/simulado/desafio (rota de diálogo turno a
turno), e nenhum módulo existente já tinha essa consulta simples pronta.
"""
from . import db

VERSAO = "questoes-v5"

CAMPOS = ("id, disciplina, tema, enunciado, gabarito, dicas, tipo, gabarito_ce, "
          "contexto_id, ordem_no_contexto")

# MÚLTIPLA ESCOLHA E QUESTÃO DE PROVA (037): a letra do gabarito, de onde ela
# veio, e as alternativas — juntas da questão, como o texto-base, pelo mesmo
# motivo: questão de múltipla escolha sem as alternativas é ilegível.
# `alias` é o da tabela `questao` na consulta.
def campos_de_prova(alias: str = "q") -> str:
    return (f"{alias}.gabarito_letra, {alias}.gabarito_fonte, {alias}.origem, {alias}.numero_na_prova, "
            f"(SELECT coalesce(json_agg(json_build_object('letra', a.letra, 'texto', a.texto) "
            f"ORDER BY a.letra), '[]'::json) FROM questao_alternativa a "
            f"WHERE a.questao_id = {alias}.id) AS alternativas")

# O texto-base vem JUNTO da questão, por LEFT JOIN, e não numa segunda
# chamada: item C/E de série é ilegível sem ele ("com base no argumento
# acima"), então buscar os dois separado só criaria um instante em que a
# tela tem a assertiva e não tem o enunciado — e uma rota a mais pra
# esquecer de chamar.
CAMPOS_COM_CONTEXTO = ("q.id, q.disciplina, q.tema, q.enunciado, q.gabarito, q.dicas, "
                       "q.tipo, q.gabarito_ce, q.contexto_id, q.ordem_no_contexto, "
                       "x.texto AS contexto, " + campos_de_prova("q"))
JOIN_CONTEXTO = "LEFT JOIN contexto x ON x.id = q.contexto_id"


def do_aluno(alias: str = "q") -> str:
    """
    Predicado SQL "esta questão pode ser servida a este aluno" (026).

    UM lugar só, como `mesa.filtro()`, e aqui o motivo é mais grave que
    coerência: cópia divergente não devolve número errado, devolve o
    material PAGO de outra pessoa. Toda consulta que escolhe questão de um
    POOL — fila, desafio, simulado, lookup por id, cobertura, geração —
    passa por aqui.

    Quem usa precisa passar `dono` nos parâmetros, SEMPRE: o id do aluno,
    ou `None` pra restringir ao acervo público (é o que a CLI de geração em
    lote e o `sincronizar` querem — nenhum dos dois fala por um aluno).

    Consulta que sai de `progresso`/`tentativa`/`erro_caderno` NÃO precisa
    do predicado: aquelas tabelas já são por `usuario_id`, e questão privada
    só chega lá pela mão do próprio dono. Pôr o predicado ali também não
    estaria errado, só seria redundante — e redundância que parece
    necessária faz a próxima pessoa achar que a ausência dela é um bug.
    """
    return f"({alias}.usuario_id IS NULL OR {alias}.usuario_id = %(dono)s)"


def obter(questao_id: int, dono: int | None = None) -> dict | None:
    """`dono` é quem está pedindo. Sem ele, só questão pública — o default
    é o mais restritivo de propósito: rota nova que esqueça de passar o
    aluno devolve 404 em questão privada, não a questão de outro."""
    return db.exec1(
        f"""SELECT {CAMPOS_COM_CONTEXTO} FROM questao q {JOIN_CONTEXTO}
             WHERE q.id = %(id)s AND {do_aluno()}""",
        {"id": questao_id, "dono": dono})


def obter_varias(ids: list[int], dono: int | None = None) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.query(
        f"""SELECT {CAMPOS_COM_CONTEXTO} FROM questao q {JOIN_CONTEXTO}
             WHERE q.id = ANY(%(ids)s) AND {do_aluno()}""",
        {"ids": ids, "dono": dono})
    return {r["id"]: r for r in rows}


def obter_com_progresso(usuario_id: int, questao_id: int) -> dict | None:
    """Como `obter()`, mas com caixa/prox_revisao DESTE usuário anexados —
    mesmo default de `scheduler.fila()` pra questão nunca tentada (caixa 0,
    hoje). Usado pela tela de responder, que precisa mostrar a caixa atual
    mesmo quando chega direto (refresh), sem vir da lista da fila."""
    return db.exec1(
        f"""SELECT {CAMPOS_COM_CONTEXTO}, COALESCE(p.caixa, 0) AS caixa,
                  COALESCE(p.prox_revisao, CURRENT_DATE) AS prox_revisao
           FROM questao q
           {JOIN_CONTEXTO}
           LEFT JOIN progresso p ON p.usuario_id = %(u)s AND p.questao_id = q.id
           WHERE q.id = %(id)s AND {do_aluno()}""",
        {"u": usuario_id, "id": questao_id, "dono": usuario_id},
    )
