"""
Diário de classe: o que o aluno estudou CONVERSANDO, e o que ele não testou.

O tutor sempre soube o que o aluno RESPONDEU — `v_desempenho_disciplina`, o
caderno de erros, os conceitos da 022. O que ele nunca soube é o que vocês
CONVERSARAM: duas horas de teoria sobre peculato sem uma questão não deixavam
rastro nenhum, e no dia seguinte a conversa nova abria em branco. Este módulo é
a outra metade da memória (031).

O RÓTULO É COLHIDO, NÃO RESUMIDO. Sai da rubrica do artigo que a busca trouxe
("Peculato") ou do assunto classificado do material do aluno ("Traumatologia
forense"). Nada aqui chama LLM: resumir a sessão custaria cota por turno e
colocaria prosa de modelo dentro do prompt de um modelo, que é o cuidado que a
022 já tomou com `conceito_faltante`.

O QUE NÃO ENTRA: turno sem material recuperado. Saudação, desabafo e
meta-pergunta não têm chunk (`pedido.dispensa_busca` corta a busca antes), então
não têm rótulo e não viram estudo — "bom dia" não é aula, e contá-lo encheria o
diário de linhas que enganam a leitura do dia seguinte.
"""
from . import db

VERSAO = "diario-v3"

MAX_ASSUNTO = 120       # casa com o CHECK da 031
DIAS_PADRAO = 7         # janela do bloco que vai ao prompt
LIMITE_LINHAS = 6       # o prompt não é relatório


def rotulo(chunks: list[dict] | None) -> tuple[str, str | None] | None:
    """(assunto, disciplina) do turno, ou None quando não houve material.

    PURO: decide olhando só os chunks, e por isso dá pra testar sem banco.

    O VENCEDOR É O MAIS FREQUENTE, não o primeiro. A busca devolve 6 trechos e
    o topo do RRF oscila entre execuções do mesmo turno; a rubrica que se repete
    é o assunto de que a conversa trata. Empate desempata pela ordem da busca,
    que é a única ordenação com sentido aqui.
    """
    contagem: dict[tuple[str, str | None], int] = {}
    for c in chunks or []:
        # Lei: a rubrica ("Peculato") é o nome que o aluno reconhece. Material do
        # aluno: o assunto que o classificador (020) já escreveu.
        nome = (c.get("rubrica") or c.get("assunto") or "").strip()
        if not nome:
            continue
        chave = (nome[:MAX_ASSUNTO], (c.get("disciplina") or "").strip() or None)
        contagem[chave] = contagem.get(chave, 0) + 1
    if not contagem:
        return None
    return max(contagem, key=lambda k: contagem[k])


def anotar(usuario_id: int, chunks: list[dict] | None) -> None:
    """Soma um turno ao assunto do dia. Silencioso por contrato.

    Silencioso pelo mesmo motivo de `core/telemetria.py`: o aluno perder a
    resposta porque a contabilidade da aula falhou seria trocar o produto pela
    métrica dele. Banco fora do ar ou máquina sem a 031 aplicada seguem
    conversando.
    """
    r = rotulo(chunks)
    if not usuario_id or not r:
        return
    assunto, disciplina = r
    try:
        db.query(
            """INSERT INTO estudo_teoria (usuario_id, assunto, disciplina)
               VALUES (%(u)s, %(a)s, %(d)s)
               ON CONFLICT (usuario_id, dia, assunto) DO UPDATE
                 SET turnos = estudo_teoria.turnos + 1,
                     ultimo_em = now(),
                     -- A disciplina só melhora: turno que veio sem ela (material
                     -- ainda não classificado) não apaga a que já estava lá.
                     disciplina = COALESCE(EXCLUDED.disciplina, estudo_teoria.disciplina)""",
            {"u": usuario_id, "a": assunto, "d": disciplina})
    except Exception:
        pass


def recentes(usuario_id: int, dias: int = DIAS_PADRAO,
             disciplinas: list[str] | None = None,
             limite: int = LIMITE_LINHAS) -> list[dict]:
    """O que ele estudou nos últimos dias, e quantas questões respondeu ali.

    `questoes_no_dia` é o que permite a frase que o dono pediu — "você viu
    bastante e não resolveu nenhuma". Conta tentativa DAQUELE dia na MESMA
    disciplina: cruzar por assunto seria mais fino e não existe, porque
    `questao.tema` é texto livre e não casa com a rubrica do chunk.

    Sem disciplina no diário, `questoes_no_dia` vem NULL — e NULL aqui é "não
    sei", que é diferente de zero. Dizer "você não resolveu nenhuma" quando o
    sistema não tem como saber é a classe de erro que este projeto já mediu
    várias vezes: ausência de dado virando prova.
    """
    from . import mesa
    return db.query(
        f"""SELECT e.dia, e.assunto, e.disciplina, e.turnos, e.ultimo_em,
                   (CURRENT_DATE - e.dia) AS dias_atras,
                   CASE WHEN e.disciplina IS NULL THEN NULL ELSE (
                     SELECT count(*) FROM tentativa t
                       JOIN questao q ON q.id = t.questao_id
                      WHERE t.usuario_id = e.usuario_id
                        AND q.disciplina = e.disciplina
                        AND t.criada_em::date = e.dia
                   ) END AS questoes_no_dia
              FROM estudo_teoria e
             WHERE e.usuario_id = %(u)s
               AND e.dia > CURRENT_DATE - %(dias)s::int
               AND ({mesa.filtro('e.disciplina')} OR e.disciplina IS NULL)
             ORDER BY e.dia DESC, e.turnos DESC
             LIMIT %(lim)s""",
        {"u": usuario_id, "dias": max(1, dias), "disc": disciplinas, "lim": limite})


def _quando(dias_atras: int) -> str:
    return {0: "hoje", 1: "ontem"}.get(dias_atras, f"há {dias_atras} dias")


def resumo_para_prompt(usuario_id: int, dias: int = DIAS_PADRAO,
                       disciplinas: list[str] | None = None,
                       convite: bool = True) -> str | None:
    """Texto pronto pro bloco `### Teoria que vocês já conversaram`.

    `convite=False` tira a marca "NENHUMA questão respondida". Ela existe para
    o convite a testar que o prompt manda fazer UMA vez; chegando em todo
    turno, o tutor a obedecia em todo turno — três ofertas de questão em seis
    turnos, medido em 24/09/2026. Quem chama liga a marca só na abertura.

    Uma linha por assunto, com o dia por extenso relativo ("ontem", "há 3
    dias") em vez da data: a pergunta que isto responde é "o que estudamos
    ontem?", e obrigar o modelo a subtrair datas é criar uma chance de errar
    onde não precisa haver nenhuma.
    """
    registros = recentes(usuario_id, dias, disciplinas)
    if not registros:
        return None

    # MATÉRIA E ASSUNTO NÃO SÃO SINÔNIMOS. O formato antigo era
    # "Peculato (Direito Penal)"; perguntado "quais matérias eu já estudei?",
    # o modelo listou Peculato, Detração e Processo Legislativo como matérias.
    # Entregar a hierarquia já nomeada evita pedir ao modelo que deduza uma
    # estrutura que o banco conhece em cada linha.
    materias = list(dict.fromkeys(
        r["disciplina"] for r in registros if r.get("disciplina")))
    linhas = (["Matérias com teoria conversada nesta janela: " +
               (", ".join(materias) if materias else "nenhuma identificada")])
    for r in registros:
        parte = f"- ASSUNTO: {r['assunto']}"
        if r["disciplina"]:
            parte += f"; MATÉRIA: {r['disciplina']}"
        parte += f"; QUANDO: {_quando(r['dias_atras'])}; {r['turnos']} turno(s) de conversa"
        if r["questoes_no_dia"] == 0 and convite:
            parte += " — NENHUMA questão respondida nesse dia"
        elif r["questoes_no_dia"]:
            parte += f" e {r['questoes_no_dia']} questão(ões) respondida(s)"
        linhas.append(parte)
    return "\n".join(linhas)
