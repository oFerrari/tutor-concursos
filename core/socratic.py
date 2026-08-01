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
            "tema": {"type": "STRING"},
            "enunciado": {"type": "STRING"},
            "gabarito": {"type": "STRING"},
            "dicas": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["tema", "enunciado", "gabarito", "dicas"],
        "propertyOrdering": ["tema", "enunciado", "gabarito", "dicas"],
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
- Português brasileiro, tom direto, no máximo 2 frases no comentário."""

SISTEMA_GERADOR = """Você elabora questões discursivas curtas para concursos públicos \
brasileiros, no estilo Cebraspe/FGV, a partir de um material fornecido.

Regras:
- Use exclusivamente o conteúdo do material. Não invente dispositivo, número ou prazo.
- Cada questão cobra UM ponto verificável, não um resumo do assunto.
- Exatamente 3 dicas, em ordem crescente de ajuda, e NENHUMA delas contém o gabarito \
completo: a primeira reorienta o olhar, a segunda restringe o campo, a terceira quase entrega.
- Enunciado com no máximo 2 frases. Gabarito com no máximo 3 frases."""

LOTE_GERACAO = 3   # questões por chamada; lotes grandes estouram o limite de tokens


def avaliar(enunciado: str, gabarito: str, resposta: str, nivel: int) -> dict:
    """
    nivel = quantas dicas já foram consumidas (0..3).
    Devolve dict com veredito, comentario, pergunta e revelar_gabarito.
    """
    prompt = (
        f"QUESTÃO: {enunciado}\n\n"
        f"GABARITO (uso interno, jamais revele): {gabarito}\n\n"
        f"RESPOSTA DO ALUNO: {resposta}\n\n"
        f"Esta é a tentativa nº {nivel + 1}. "
        f"{'Seja mais específico na pista, o aluno já errou antes.' if nivel else ''}"
    )
    d = llm.obter().gerar_json(prompt, SISTEMA_AVALIADOR,
                              max_tokens=800, schema=ESQUEMA_AVALIACAO)
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


def explicar(pergunta: str) -> dict:
    """Modo livre: aluno pergunta, tutor responde ancorado no acervo."""
    chunks = retrieval.buscar(pergunta, n=6)
    if not chunks:
        return {"resposta": "Não encontrei isso no material que você ingeriu ainda.", "fontes": []}
    contexto = retrieval.formatar_contexto(chunks)
    sistema = (
        "Você é professor de concursos. Responda usando SOMENTE o material entre marcadores. "
        "Cite a referência entre colchetes que acompanha cada trecho. Se o material não "
        "cobrir a pergunta, diga isso em vez de completar com conhecimento próprio. "
        "Explique com suas palavras em vez de transcrever o trecho inteiro. "
        "Termine com uma pergunta que teste se o aluno entendeu."
    )
    resposta = llm.obter().gerar(f"MATERIAL:\n{contexto}\n\nPERGUNTA DO ALUNO: {pergunta}",
                                 sistema, max_tokens=1500)
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
            "tema": (q.get("tema") or "Sem tema").strip(),
            "enunciado": q["enunciado"].strip(),
            "gabarito": q["gabarito"].strip(),
            "dicas": dicas[:3],
        })
    return validas
