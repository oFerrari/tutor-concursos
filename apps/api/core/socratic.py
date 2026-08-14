"""
O professor socrático.

Decisão central: **a retenção do gabarito é imposta em código, não confiada
ao prompt.** O modelo recebe o gabarito para poder julgar a resposta, e é
instruído a não revelá-lo — mas instrução de prompt vaza. Então o nível de
ajuda é uma máquina de estados aqui no Python: nível 1 e 2 devolvem apenas
pergunta e pista; o gabarito só sai do banco para a tela quando o nível
chega a 3, e nesse caso quem imprime é este módulo, não o modelo.

Segunda decisão: os dois pontos que precisam de JSON declaram `responseSchema`.
Sem isso, modelo pequeno erra a sintaxe e a sessão de estudo morre no meio.
"""
from . import llm, retrieval

VERSAO = "socratic-v25"

# ------------------------------------------------------------------ schemas
# Subconjunto OpenAPI aceito pelo Gemini. propertyOrdering importa: o modelo
# gera na ordem declarada, e gerar o gabarito antes das dicas produz dicas
# mais coerentes com ele.
ESQUEMA_AVALIACAO = {
    "type": "OBJECT",
    "properties": {
        "veredito": {"type": "STRING", "enum": ["correta", "parcial", "incorreta"]},
        "comentario": {"type": "STRING"},
        "pergunta": {"type": "STRING"},
        "conceito_faltante": {"type": "STRING"},
    },
    "required": ["veredito", "comentario", "pergunta"],
    "propertyOrdering": ["veredito", "comentario", "pergunta", "conceito_faltante"],
}

ESQUEMA_QUESTOES = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            # `artigo` primeiro de propósito: o modelo escolhe o dispositivo
            # ANTES de redigir, o que ancora a questão em um artigo só. E é o
            # que permite medir cobertura — sem proveniência não há como saber
            # quais artigos já foram cobrados.
            "artigo": {"type": "STRING"},
            "tema": {"type": "STRING"},
            "enunciado": {"type": "STRING"},
            "gabarito": {"type": "STRING"},
            "dicas": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["artigo", "tema", "enunciado", "gabarito", "dicas"],
        "propertyOrdering": ["artigo", "tema", "enunciado", "gabarito", "dicas"],
    },
}

# ------------------------------------------------------------------ prompts
SISTEMA_AVALIADOR = """Você é um professor de cursinho para concursos públicos brasileiros que \
usa o método socrático. Sua função é avaliar a resposta do aluno e conduzi-lo ao raciocínio \
correto por meio de perguntas, nunca entregando a resposta pronta.

Regras absolutas:
- Nunca reproduza nem parafraseie o gabarito. Nem parcialmente.
- Não use elogio vazio. Se a resposta está incompleta, diga o que falta em termos de conceito, \
não de palavra.
- Sua pergunta deve ser respondível pelo aluno com o que ele já demonstrou saber.
- Uma linha de raciocínio só, do começo ao fim da questão. Cada pergunta sua \
avança UM passo em relação à anterior; nunca recomece de outro ângulo.
- Se o aluno acertou a parte que você perguntou, DIGA isso antes de pedir o resto.
- Português brasileiro, tom direto, no máximo 2 frases no comentário."""

SISTEMA_GERADOR = """Você elabora questões discursivas curtas para concursos públicos \
brasileiros, no estilo Cebraspe/FGV, a partir de um material fornecido.

Regras:
- Use exclusivamente o conteúdo do material. Não invente dispositivo, número ou prazo.
- Cada questão cobra UM ÚNICO ponto verificável. Isto é a regra mais violada: \
não junte dois pedidos com "e".
  RUIM: "Qual a conduta típica E a respectiva pena do crime X?"
  RUIM: "Quais os requisitos E a consequência do aumento de pena?"
  BOM:  "Qual a conduta típica do crime X?"
  BOM:  "Qual a fração de aumento de pena quando resulta dano ao administrado?"
  Se o material der conduta e pena, gere DUAS questões separadas, não uma dupla.
- Exatamente 3 dicas, em ordem crescente de ajuda, e NENHUMA delas contém o gabarito \
completo: a primeira reorienta o olhar, a segunda restringe o campo, a terceira quase entrega.
- Enunciado com no máximo 2 frases. Gabarito com no máximo 3 frases.
- O campo `artigo` recebe SÓ o número do dispositivo de onde a questão saiu, \
como aparece no material: "312", "121-A", "8º". Nunca invente número, nunca escreva "Art.".
- Uma questão por artigo. Se pedirem 3 questões, use 3 artigos diferentes do material."""

LOTE_GERACAO = 3   # questões por chamada; lotes grandes estouram o limite de tokens


def avaliar(enunciado: str, gabarito: str, resposta: str, nivel: int,
            historico: list[dict] | None = None) -> dict:
    """
    nivel    = quantas tentativas erradas já houve nesta questão (0..3).
    historico = turnos anteriores [{resposta, comentario, pergunta}], para que
                o avaliador CONTINUE o diálogo em vez de recomeçá-lo.

    Sem histórico cada chamada era independente: o modelo reformulava a
    pergunta-guia do zero a cada turno e repetia explicação já dada. O aluno
    perseguia um alvo móvel — e pior, respondia à pergunta-guia enquanto era
    avaliado contra o gabarito da questão original.
    """
    partes = [f"QUESTÃO: {enunciado}",
              f"GABARITO (uso interno, jamais revele): {gabarito}"]
    if historico:
        linhas = []
        for i, t in enumerate(historico, 1):
            linhas.append(f"  turno {i} — aluno: {t['resposta']}")
            if t.get("pergunta"):
                linhas.append(f"           você perguntou: {t['pergunta']}")
        partes.append("DIÁLOGO ATÉ AQUI:\n" + "\n".join(linhas))
    partes.append(f"RESPOSTA ATUAL DO ALUNO: {resposta}")
    partes.append(
        f"Esta é a tentativa nº {nivel + 1}. "
        + ("Continue a MESMA linha de raciocínio do turno anterior: se o aluno "
           "respondeu a sua última pergunta, reconheça o avanço e peça só o que "
           "ainda falta. Não repita explicação já dada nem troque de abordagem."
           if historico else "")
    )
    prompt = "\n\n".join(partes)
    # 800 truncava com frequência real (2 de 3 numa amostra manual) em
    # resposta ERRADA: modelos com "thinking" gastam parte do orçamento de
    # maxOutputTokens em raciocínio interno antes do JSON visível, e
    # explicar um erro consome mais desse raciocínio do que confirmar um
    # acerto. Sem thinkingConfig exposto aqui pra zerar isso, o caminho
    # seguro é dar mais orçamento — mesmo padrão de explicar()/gerar_questoes.
    d = llm.obter().gerar_json(prompt, SISTEMA_AVALIADOR,
                              max_tokens=2000, schema=ESQUEMA_AVALIACAO)
    veredito = d.get("veredito", "parcial")
    if veredito not in ("correta", "parcial", "incorreta"):
        veredito = "parcial"
    return {
        "veredito": veredito,
        "comentario": d.get("comentario", ""),
        "pergunta": d.get("pergunta", ""),
        "conceito_faltante": d.get("conceito_faltante", ""),
        # a política de revelação é nossa, não do modelo
        "revelar_gabarito": veredito == "correta" or nivel >= 2,
    }


def _resumo_desempenho(usuario_id: int, disciplinas: list[str] | None = None) -> str | None:
    """
    Texto curto e pronto pra virar contexto de prompt — o modelo só LÊ este
    resumo, nunca soma nada sozinho. Import local (não no topo do módulo):
    `socratic.py` não deve carregar `scheduler.py` pra quem só usa
    `avaliar()`/`gerar_questoes()`, que não tocam nisso.
    """
    from . import scheduler
    dados = scheduler.desempenho(usuario_id, disciplinas)
    if not dados:
        return None
    linhas = [
        f"- {d['disciplina']}: {d['dominadas']}/{d['questoes']} dominadas, "
        f"{d['pct_acerto'] or 0}% de acerto em {d['tentativas']} tentativas, "
        f"{d['cobertura_pct'] or 0}% de cobertura"
        for d in dados
    ]
    erros = scheduler.caderno_erros(usuario_id, limite=5, disciplinas=disciplinas)
    if erros:
        linhas.append("Temas que mais reincidem em erro: " +
                      ", ".join(f"{e['tema']} ({e['vezes']}x)" for e in erros))
    return "\n".join(linhas)


def _resumo_mesa(mesa_: dict | None) -> str | None:
    """
    Quem é o aluno NESTA sessão: o concurso, a banca, e as matérias que o
    edital dele cobra.

    Faltava, e o efeito era grosseiro: perguntado "o que tem no meu edital",
    o tutor não tinha como saber que existe um edital — jogava a palavra na
    busca e devolvia a definição jurídica de "edital" na Lei 8.112 e no CPP
    (o documento que publica um concurso, a citação por edital no processo).
    Resposta correta sobre a lei, e completamente fora do que foi perguntado.

    Só os NOMES das disciplinas entram, nunca a lista de tópicos: o edital da
    Dataprev tem 1015 tópicos, e despejar isso em todo prompt queima cota pra
    repetir o que a tela de edital já mostra melhor.
    """
    if not mesa_ or not mesa_.get("nome"):
        return None
    linhas = [f"Concurso-alvo: {mesa_['nome']}"]
    if mesa_.get("orgao"):
        linhas.append(f"Órgão: {mesa_['orgao']}")
    if mesa_.get("banca"):
        linhas.append(f"Banca: {mesa_['banca']}")
    disc = mesa_.get("disciplinas")
    linhas.append("Disciplinas do edital: " + (", ".join(disc) if disc else
                  "nenhum edital cadastrado nesta mesa ainda"))
    return "\n".join(linhas)


def explicar(pergunta: str, usuario_id: int | None = None,
             disciplinas: list[str] | None = None,
             mesa_: dict | None = None) -> dict:
    """
    Modo livre: aluno pergunta, tutor responde ancorado no acervo E no
    próprio desempenho real (quando usuario_id vem preenchido).

    Sem o desempenho como segunda fonte, "como estou indo em português?"
    não tinha ONDE bater — a busca no acervo (RAG) não sabe nada sobre
    quem pergunta, só sobre o texto de lei. Duas fontes de contexto, uma
    resposta: o modelo escolhe qual usar (ou as duas), mas o resumo de
    desempenho já vem pronto do banco — ele nunca soma nada sozinho, só lê.

    `disciplinas` recorta só a SEGUNDA fonte (o desempenho): "como estou
    indo?" numa mesa deve responder sobre aquele concurso. A busca no
    acervo continua sobre o material inteiro de propósito — o aluno pode
    perguntar de qualquer coisa, e cortar o RAG pela disciplina da mesa
    faria a resposta ser "não encontrei" para uma pergunta que o acervo
    responde perfeitamente.
    """
    chunks = retrieval.buscar(pergunta, n=6)
    contexto_material = retrieval.formatar_contexto(chunks) if chunks else None
    contexto_desempenho = _resumo_desempenho(usuario_id, disciplinas) if usuario_id else None
    contexto_mesa = _resumo_mesa(mesa_)

    if not contexto_material and not contexto_desempenho:
        return {"resposta": "Não encontrei isso no material, e ainda não tenho nenhum "
                            "desempenho seu registrado.", "fontes": []}

    # Os rótulos de seção usam "###" e nome comum, não MAIÚSCULA seca. O
    # formato anterior ("DESEMPENHO REAL DO ALUNO (dados do banco):") somado
    # à instrução "cite a referência entre colchetes" fez o modelo tratar o
    # NOME DA SEÇÃO como se fosse uma fonte citável: uma resposta real
    # terminou com "...está em 75.3% [DESEMPENHO REAL DO ALUNO]". Rótulo de
    # prompt vazando como citação é pior que citação errada — expõe o
    # andaime e destrói a confiança nas citações verdadeiras da mesma frase.
    partes = []
    if contexto_mesa:
        partes.append(f"### Contexto do aluno\n{contexto_mesa}")
    if contexto_material:
        partes.append(f"### Trechos de lei recuperados\n{contexto_material}")
    if contexto_desempenho:
        partes.append(f"### Números deste aluno no banco\n{contexto_desempenho}")
    partes.append(f"### Pergunta do aluno\n{pergunta}")

    sistema = (
        "Você é professor de concursos conversando com um aluno específico, cujo concurso-alvo, "
        "banca e disciplinas do edital estão no contexto. Use isso: fale da matéria como ela cai "
        "NA PROVA DELE, não como tema genérico. "
        "Se o aluno perguntar o que o edital dele cobra, responda com as disciplinas listadas no "
        "contexto — NUNCA explique o que a palavra 'edital' significa juridicamente, não é isso "
        "que ele está perguntando. "
        "Ao falar de conteúdo, use os trechos de lei recuperados e cite entre colchetes SOMENTE "
        "as referências que acompanham cada trecho (ex.: [CF, art. 37]). Nunca cite o nome de uma "
        "seção deste prompt como se fosse fonte. Se os trechos não cobrirem a pergunta, diga isso "
        "em vez de completar com conhecimento próprio. "
        "Uma matéria de prova pode morar em mais de uma norma — organização da administração "
        "pública, por exemplo, está na Constituição e no estatuto dos servidores ao mesmo tempo. "
        "Use o trecho que responde, venha da norma que vier, e diga a que matéria ele pertence "
        "na prova do aluno. "
        "Os números do aluno servem pra responder 'como estou indo' e pra escolher o que sugerir "
        "no fim; NÃO os repita em toda resposta, e NUNCA invente um número que não esteja ali. "
        "Se o aluno pedir questão, exercício ou simulado, ofereça gerar — o app cria questões a "
        "partir dos trechos de lei do acervo, então nunca diga que não tem como. "
        "Português brasileiro, tom direto. Termine com uma pergunta ou sugestão que ajude o aluno "
        "a seguir estudando."
    )
    resposta = llm.obter().gerar("\n\n".join(partes), sistema, max_tokens=1500)
    return {"resposta": resposta, "fontes": chunks}


def gerar_questoes(chunks: list[dict], quantidade: int = 5) -> list[dict]:
    """Gera em lotes pequenos: uma chamada pedindo 10 questões estoura tokens."""
    contexto = retrieval.formatar_contexto(chunks)
    modelo = llm.obter()
    coletadas: list[dict] = []
    restante = quantidade

    while restante > 0:
        pedido = min(LOTE_GERACAO, restante)
        prompt = (f"Gere {pedido} questões a partir do material.\n\n"
                  f"MATERIAL:\n{contexto}")
        if coletadas:
            temas = ", ".join(q["tema"] for q in coletadas)
            prompt += f"\n\nNÃO repita estes temas já cobrados: {temas}"
        itens = modelo.gerar_json(prompt, SISTEMA_GERADOR,
                                  max_tokens=4096, schema=ESQUEMA_QUESTOES)
        if isinstance(itens, dict):
            itens = itens.get("questoes", [])
        novas = _validar(itens)
        if not novas:
            break               # modelo travou; devolve o que já veio
        coletadas.extend(novas)
        restante = quantidade - len(coletadas)

    return coletadas[:quantidade]


def _validar(itens) -> list[dict]:
    validas = []
    for q in itens or []:
        if not isinstance(q, dict) or not q.get("enunciado") or not q.get("gabarito"):
            continue
        dicas = [str(d).strip() for d in (q.get("dicas") or []) if str(d).strip()]
        validas.append({
            "artigo": (q.get("artigo") or "").strip().replace("Art.", "").strip() or None,
            "tema": (q.get("tema") or "Sem tema").strip(),
            "enunciado": q["enunciado"].strip(),
            "gabarito": q["gabarito"].strip(),
            "dicas": dicas[:3],
        })
    return validas
