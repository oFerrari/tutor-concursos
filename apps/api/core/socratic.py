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
import re
import unicodedata

from . import assunto, llm, mesa as mesa_mod, retrieval

VERSAO = "socratic-v42"

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

ESQUEMA_QUESTOES_CE = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "artigo": {"type": "STRING"},
            "tema": {"type": "STRING"},
            "enunciado": {"type": "STRING"},
            "gabarito_ce": {"type": "BOOLEAN"},
            "justificativa": {"type": "STRING"},
        },
        "required": ["artigo", "tema", "enunciado", "gabarito_ce", "justificativa"],
        "propertyOrdering": ["artigo", "tema", "enunciado", "gabarito_ce", "justificativa"],
    },
}

SISTEMA_GERADOR_CE = """Você elabora itens de prova no formato CERTO/ERRADO do Cebraspe \
(CESPE), a partir de um material de lei fornecido.

O formato:
- O item é uma ASSERTIVA afirmativa, nunca uma pergunta. Não escreva "?" nem "assinale".
- O aluno julga se a assertiva está certa ou errada. Não existe meio-termo.
- Uma assertiva cobra UM ponto verificável no material. Não junte dois com "e".

Regras:
- Use exclusivamente o conteúdo do material. Não invente dispositivo, número ou prazo.
- APROXIMADAMENTE METADE dos itens deve ser ERRADO. Um lote todo CERTO ensina o aluno a \
marcar Certo sem ler, que é o vício que o formato Cebraspe pune.
- Item ERRADO se faz por UMA alteração específica e verificável no texto da lei — nunca por \
absurdo óbvio nem por assertiva vaga. Alterações que o Cebraspe usa de verdade:
  · trocar o prazo ou o número ("trinta dias" -> "sessenta dias");
  · trocar faculdade por dever ("poderá" -> "deverá") e vice-versa;
  · inverter a competência ou o sujeito (quem pratica, quem julga, quem autoriza);
  · ampliar ou restringir a hipótese ("em qualquer caso" onde a lei traz exceção);
  · afirmar como regra o que a lei traz como exceção.
- A `justificativa` diz POR QUE, apontando o dispositivo, e no item ERRADO diz o que a lei \
realmente estabelece. É o que o aluno lê depois de responder: sem ela, ele acerta ou erra e \
não aprende nada.
- Enunciado com no máximo 3 frases. Justificativa com no máximo 3 frases.
- O campo `artigo` recebe SÓ o número do dispositivo de onde o item saiu, como aparece no \
material: "312", "121-A", "8º". Nunca invente número, nunca escreva "Art.".
- Um item por artigo. Se pedirem 3 itens, use 3 artigos diferentes do material."""

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


CERTO = {"c", "certo", "certa", "v", "verdadeiro", "true", "1"}
ERRADO = {"e", "errado", "errada", "f", "falso", "false", "0"}


def avaliar_certo_errado(gabarito_ce: bool, resposta: str) -> dict:
    """
    Corrige item Cebraspe SEM chamar o modelo. Mesma forma de retorno de
    `avaliar()`, pra quem consome não precisar de dois caminhos.

    POR QUE NÃO PASSA PELO LLM: a resposta é um booleano. Mandar "o aluno
    respondeu Certo, o gabarito é Certo, ele acertou?" pra um modelo custa
    cota, demora, e introduz chance de erro num julgamento que `==` faz sem
    erro nenhum. É a mesma família de decisão de "retenção do gabarito é
    imposta em código": o que dá pra decidir com regra, decide-se com regra.

    POR QUE NÃO HÁ DIÁLOGO SOCRÁTICO NEM DICA AQUI: a escada socrática
    (pista → pergunta-guia → gabarito) existe pra conduzir alguém que está
    construindo uma resposta. Num item binário não há o que conduzir —
    qualquer dica sobre uma assertiva de 50% de chance É a resposta, e
    "tente de novo" vira cara ou coroa com o gabarito garantido na segunda.
    Por isso o veredito sai fechado e a justificativa aparece na hora: o
    aprendizado do item C/E está em LER POR QUE, não em tentar de novo.

    Não existe `parcial`: metade de um booleano não é nada. Isso importa
    além da estética — `scheduler_regras.proxima_caixa` desce uma caixa no
    parcial, e um item C/E que caísse ali estaria sendo punido por um
    estado que ele não pode ocupar.
    """
    escolha = (resposta or "").strip().lower()
    if escolha in CERTO:
        marcou = True
    elif escolha in ERRADO:
        marcou = False
    else:
        # Em branco/ilegível é erro por definição, igual a `simulado.corrigir`
        # — e nunca acerto por acidente de parsing.
        return {"veredito": "incorreta", "comentario": "(sem resposta)",
                "pergunta": "", "conceito_faltante": "", "revelar_gabarito": True}

    acertou = marcou == gabarito_ce
    esperado = "CERTO" if gabarito_ce else "ERRADO"
    return {
        "veredito": "correta" if acertou else "incorreta",
        "comentario": f"O item está {esperado}." if not acertou else f"Isso: {esperado}.",
        "pergunta": "",
        "conceito_faltante": "",
        "revelar_gabarito": True,
    }


def avaliar_questao(questao: dict, resposta: str, nivel: int = 0,
                    historico: list[dict] | None = None) -> dict:
    """
    O ÚNICO lugar que decide como uma questão é corrigida, pelo seu tipo.

    Existe porque os caminhos de correção são quatro (rota de avaliação,
    simulado, desafio, CLI) e todos chamavam `avaliar()` direto. Cada um que
    esquecesse de olhar o tipo mandaria um item C/E pro julgamento por LLM,
    que compararia "C" contra uma justificativa em prosa e devolveria
    qualquer coisa — errado, caro e silencioso. Um dispatcher, quatro
    chamadores; mesmo princípio de `mesa.filtro` viver num lugar só.
    """
    if questao.get("tipo") == "certo_errado":
        return avaliar_certo_errado(questao["gabarito_ce"], resposta)
    return avaliar(questao["enunciado"], questao["gabarito"], resposta, nivel, historico)


def _resumo_perfil(perfil: dict | None) -> str | None:
    """
    Como esta pessoa estuda — o que os números não dizem.

    Vira FRASE, não JSON despejado: o modelo lê melhor "estuda cerca de 2h
    por dia, se considera Intermediário" do que `{"horas":"2h"}`, e a frase
    deixa explícito o que é declaração do aluno (e portanto pode estar
    desatualizada) em vez de parecer medida do sistema.

    Só os campos conhecidos entram (a lista fechada mora em
    `auth.CAMPOS_PERFIL`): perfil vai direto pro prompt, e texto livre
    vindo do cliente aqui seria injeção de instrução disfarçada de
    preferência.
    """
    if not perfil:
        return None
    # Revalida na LEITURA com a MESMA FUNÇÃO usada na escrita
    # (`auth._valor_valido`), não uma reimplementação paralela — foi
    # reimplementação que causou bug real: a versão anterior checava só
    # `v in CAMPOS_PERFIL[k]`, que cobre os presets mas não o regex de
    # horas personalizada (`_RE_HORAS_PERSONALIZADA`, aceito na escrita
    # desde sempre). Resultado: "horas": "3h" gravava certo, `desafio.py`
    # calculava os minutos certo (tem a própria regex), e só aqui — o
    # resumo que vai pro prompt do tutor — o campo desaparecia, como se a
    # pessoa nunca tivesse respondido "quantas horas por dia" no
    # onboarding. Duas cópias da MESMA regra de validação é exatamente
    # como elas divergem; a chamada é o jeito de nunca mais divergir.
    # Import local: `socratic` não deve carregar `auth` pra quem só usa
    # `avaliar()` — mesmo motivo do import de `scheduler` abaixo.
    from .auth import _valor_valido

    valido = {k: v for k, v in perfil.items() if _valor_valido(k, v)}
    partes = []
    if valido.get("horas"):
        partes.append(f"estuda cerca de {valido['horas']} por dia")
    if valido.get("nivel"):
        partes.append(f"se considera {valido['nivel']}")
    if valido.get("turno"):
        partes.append(f"rende melhor de {valido['turno']}")
    if not partes:
        return None
    return ("Declarado por ele no onboarding (pode estar desatualizado): "
            + ", ".join(partes) + ".")


def _programa_em_foco(mesa_: dict | None, pergunta: str,
                      historico: list[dict] | None) -> str | None:
    """O programa do edital DA DISCIPLINA que a conversa nomeou, na ordem dele.

    POR QUE ISTO NÃO CONTRADIZ `_resumo_mesa`. Aquele docstring decidiu, com
    razão, que a lista de tópicos NUNCA entra: o edital da Dataprev tem 1015, e
    despejá-los em todo prompt queima cota pra repetir o que a tela mostra
    melhor. A decisão continua de pé — o que muda é o RECORTE. Aqui entra UMA
    disciplina, e só quando a conversa a nomeou: Ciências Forenses da PC-PR são
    ~30 linhas, com teto de 40 em `mesa.MAX_TOPICOS_NO_PROMPT`.

    O QUE FALHAVA SEM ISTO, medido no cenário `forense_do_zero`: o aluno pediu
    "quero aprender ciências forenses do zero" e depois "na ordem do edital da
    PC-PR". O tutor respondeu que "o ponto de partida é a preservação do local e
    o início do rastreamento do vestígio" — inventado a partir do que a BUSCA
    devolveu (cadeia de custódia), enquanto o edital abre em "8.1.1 Conceito e
    divisão da Medicina Legal". O dado estava no banco, em ordem, e não chegava
    a quem responde.

    Olha a pergunta atual E o histórico porque "na ordem do edital" costuma vir
    no turno SEGUINTE ao que nomeou a matéria — foi exatamente assim no log."""
    if not mesa_ or not mesa_.get("id"):
        return None
    disc = mesa_.get("disciplinas")
    if not disc:
        return None
    falas = [pergunta] + [m.get("texto", "") for m in reversed(historico or [])
                          if m.get("autor") == "aluno"]
    alvo = next((d for f in falas if (d := assunto.disciplina_citada(f, disc))), None)
    if not alvo:
        return None
    topicos = mesa_mod.topicos_da_disciplina(mesa_["id"], alvo)
    if not topicos:
        return None
    linhas = "\n".join(f"{i}. {t}" for i, t in enumerate(topicos, 1))
    return (f"### Programa de {alvo} no edital deste aluno, NA ORDEM\n{linhas}\n"
            "Esta é a ordem oficial. Se ele pedir para começar do zero ou seguir o edital, "
            "siga ESTA lista e diga em que ponto dela vocês estão — não invente outro ponto "
            "de partida a partir dos trechos de lei recuperados. Tópico para o qual não houver "
            "trecho recuperado: diga que ainda não tem esse material aqui e siga para o "
            "próximo, sem explicá-lo de memória.")


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

    # O CONCEITO, e não só o tema (022). "Temas que reincidem" nomeia a
    # PERGUNTA errada; isto nomeia a confusão. Sem essa linha o resumo já dizia
    # "peculato (3x)" e o modelo tinha de adivinhar o que exatamente falha ali —
    # e adivinhar é o que ele faz de melhor e de pior.
    #
    # ENTRA ROTULADO COMO CITAÇÃO DO PRÓPRIO MODELO, entre aspas e com autoria
    # ("apontado pela sua própria correção"), e isso não é estilo. Este texto foi
    # ESCRITO POR UM LLM e está voltando pro prompt de um LLM: apresentá-lo como
    # fato do sistema, no meio de números que vêm do banco, é o que permitiria
    # uma frase inventada num turno virar premissa no turno seguinte. Mesmo
    # cuidado da 016 com `[fato da sessão]` — a fonte de cada linha do prompt
    # precisa ser legível pra quem lê o prompt.
    conceitos = scheduler.conceitos_fracos(usuario_id, disciplinas, limite=5)
    if conceitos:
        linhas.append(
            "Conceitos que ele erra de novo, apontado pela sua própria correção nas "
            "tentativas dele: " +
            ", ".join(f"\"{c['conceito']}\" ({c['vezes']}x, {c['disciplina']})"
                      for c in conceitos))
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


# ------------------------------------------------------- citação com fonte

# Toda citação que o tutor escreve. O formato é o de `retrieval.referencia`,
# porque é dele que o modelo copia: colchete, norma, vírgula, "art. N".
RE_CITADA = re.compile(r"\[([^\[\]\n]{1,160})\]")

# Conectores que ficariam pendurados se a citação saísse sozinha do meio da
# frase ("conforme [Lei X, art. 5º], o vínculo..." viraria "conforme , o
# vínculo"). Saem junto com ela. Lista curta e fechada: nas seis citações medidas
# em resposta real, todas vinham no fim da oração, onde apagar só a citação
# basta — estes existem pro caso que a medição não viu, não pro comum.
RE_CONECTOR = re.compile(
    r"(?:,\s*)?\b(?:conforme|segundo|previsto[s]?\s+(?:em|n[oa])|nos\s+termos\s+d[oae]|"
    r"de\s+acordo\s+com|com\s+base\s+n[oa]|na\s+forma\s+d[oae]|"
    r"consta\s+(?:em|n[oa])|est[aá]\s+(?:em|n[oa]))\s*$",
    re.IGNORECASE)

RE_NUMERO_ART = re.compile(r"\bart\w*\.?\s*(\d+)", re.IGNORECASE)
RE_TOKEN = re.compile(r"[0-9]+|[^\W\d_]+", re.UNICODE)


def _tokens(texto: str) -> tuple[str, ...]:
    nfkd = unicodedata.normalize("NFKD", (texto or "").lower())
    limpo = "".join(c for c in nfkd if not unicodedata.combining(c))
    return tuple(RE_TOKEN.findall(limpo))


def _identidade(citada: str) -> tuple[tuple[str, ...], str | None]:
    """(tokens da norma, número do artigo) de uma citação ou de uma referência.

    A norma é o que vem ANTES da primeira vírgula, e o artigo é o primeiro
    número depois de "art" — as duas escolhas saem de medição, não de gosto. O
    modelo acrescenta detalhe que o trecho não tem: escreveu "[CF, art. 37,
    XVI]" para a referência "[cf, art. 37]" e "[cp, art. 316, § 1º]" para "[cp,
    art. 316 — Concussão]". Exigir a citação inteira igual reprovaria as duas;
    exigir que TODO número bata reprovaria a segunda (o "1" do parágrafo). Quem
    identifica a fonte é norma + artigo; o resto é refinamento que o modelo fez
    por cima do que leu, e refinamento não é invenção."""
    if "," in citada:
        norma = citada.split(",")[0]
    else:
        norma = re.split(r"\bart\w*\.?", citada, maxsplit=1, flags=re.IGNORECASE)[0]
    achado = RE_NUMERO_ART.search(citada)
    return _tokens(norma), (achado.group(1) if achado else None)


def com_fonte(citada: str, chunks: list[dict]) -> bool:
    """A citação tem trecho recuperado por trás?

    Aceita o `titulo` E a `norma` do chunk como identidade da fonte: o mesmo
    acervo se apresenta das duas formas ("Código de Processo Penal" e "CPP",
    "Lei 8.112/1990" e "L8112"), e as duas são dado que já está na linha — não
    tabela de apelidos escrita por mim, que é o tipo de coisa que envelhece
    calada. Chunk sem artigo (material do aluno, `historico`) casa por nome só:
    é o que a referência dele tem."""
    tokens, artigo = _identidade(citada)
    if not tokens:
        return False
    for c in chunks or []:
        if tokens not in {_tokens(c.get("titulo") or ""), _tokens(c.get("norma") or "")}:
            continue
        digitos = "".join(ch for ch in str(c.get("artigo") or "") if ch.isdigit())
        if artigo is None or not digitos or artigo == digitos:
            return True
    return False


# QUESTÃO ESCRITA PELO TUTOR, que o app tem de apagar da resposta.
#
# `[Questão 1: ...]` é a forma que o modelo escolheu sozinho, e alternativas
# inline são a marca dela. Duas alternativas em sequência é o gatilho: uma letra
# com parêntese solta aparece em prosa legítima ("o item a) do edital").
RE_BLOCO_QUESTAO = re.compile(
    r"\[\s*(?:quest[ãa]o|item|assertiva)\b[^\]]{0,900}\]", re.IGNORECASE | re.DOTALL)
# TRÊS alternativas, não duas. Com duas, a regra apagava prosa legítima:
# "O item a) do edital trata de princípios e o b) de atos." Item de prova
# brasileira tem quatro ou cinco; texto corrido cita uma ou duas.
RE_ALTERNATIVAS = re.compile(
    r"(?:^|[;\s(])a\s*\)\s*\S.{0,200}?[;\s]b\s*\)\s*\S.{0,200}?[;\s]c\s*\)",
    re.IGNORECASE | re.DOTALL)
RE_ASSINALE = re.compile(r"(?i)assinale\s+a\s+(?:alternativa|op[çc][ãa]o|correta)")


def limpar_questoes(resposta: str) -> tuple[str, int]:
    """Tira da resposta as questões que o TUTOR escreveu. Devolve (texto, quantas).

    POR QUE EM CÓDIGO, e não mais uma linha de prompt: já foram TRÊS tentativas
    de proibir por instrução (v40 pedindo o botão, v41 dizendo que o app monta,
    v42 enumerando "nada de Questão 1:, nada de alternativas a), b), c)"), e o
    log seguinte mostrou o modelo escrevendo exatamente isso de novo. Este
    projeto já sabe o que fazer nesse ponto: `limpar_citacoes` existe pelo mesmo
    motivo — o que dá pra garantir em código não se confia ao prompt.

    E o dano é concreto, não estético: questão escrita na prosa não tem campo de
    resposta, não tem `fonte_chunks`, não entra na fila SM-2 e não conta no
    progresso. O aluno lê duas questões que parecem iguais às de verdade, tenta
    responder, e não tem onde. Foi relatado assim: "não trouxe o campo pra eu
    anexar a resposta individualmente".

    Não tenta consertar a frase de abertura: se sobrar pouco texto, quem chama
    põe uma linha padrão. Reescrever prosa de modelo é o que `_costurar`
    aprendeu a não fazer."""
    limpo, n = RE_BLOCO_QUESTAO.subn("", resposta)
    # Fora de colchete também: o modelo alterna entre os dois formatos.
    linhas, mortas = [], 0
    for par in limpo.split("\n"):
        if RE_ALTERNATIVAS.search(par) or RE_ASSINALE.search(par):
            mortas += 1
            continue
        linhas.append(par)
    limpo = "\n".join(linhas)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo).strip()
    return limpo, n + mortas


def limpar_citacoes(resposta: str, chunks: list[dict]) -> str:
    """Apaga da resposta as citações que nenhum trecho recuperado sustenta.

    É REGRA EM CÓDIGO, e pelo motivo de sempre neste projeto: o prompt já manda
    "cite SOMENTE as referências que acompanham cada trecho", e instrução vaza —
    mesma lição da retenção do gabarito. Medido em conversa real: o tutor
    escreveu "[Lei Maria da Penha, art. 5º]" sem nenhum trecho dessa lei, que
    NEM ESTÁ no acervo. O conteúdo estava certo; a fonte era inverificável — e é
    a verificabilidade que dá valor ao colchete. Um colchete que o aluno não pode
    conferir contamina os verdadeiros da mesma resposta.

    Apagar em vez de avisar: "(fora do acervo)" na cara do aluno é vocabulário do
    sistema aparecendo na aula, proibido no mesmo prompt. A afirmação continua —
    sem o carimbo de fonte que ela não tem.

    E apagar na SAÍDA fecha o cano na origem: a resposta filtrada é a que vai pro
    banco (014), então o histórico deixa de ensinar o modelo a citar lei fora do
    acervo — era daí que esta vinha, dos turnos anteriores DELE mesmo. Mensagem
    já gravada não é reescrita: filtro de borda vale do ponto em que existe pra
    frente.

    Não toca em nada quando não há o que apagar. Uma resposta sem citação
    inverificável sai byte por byte como o modelo escreveu, porque `_costurar`
    mexe em espaço e pontuação, e mexer nisso sem motivo é risco sem prêmio."""
    texto = resposta or ""
    saida, fim, apagou = [], 0, False
    for m in RE_CITADA.finditer(texto):
        antes = texto[fim:m.start()]
        if com_fonte(m.group(1), chunks):
            saida.append(antes + m.group(0))
        else:
            saida.append(RE_CONECTOR.sub("", antes))
            apagou = True
        fim = m.end()
    saida.append(texto[fim:])
    return _costurar("".join(saida)) if apagou else resposta


def _costurar(texto: str) -> str:
    """A cicatriz de onde a citação saiu: espaço duplo, espaço antes de
    pontuação, vírgula abrindo frase. Sem isto a resposta fica com "protetiva ?",
    "cargo  público" ou ", o vínculo de afeto basta" — e defeito de pontuação lê
    como app quebrado, não como filtro funcionando.

    A vírgula órfã e a maiúscula só aparecem no caminho do conector, que é
    DEFENSIVO: nas seis citações medidas em resposta real, todas vinham no fim da
    oração, e ali apagar o colchete não deixa cicatriz nenhuma."""
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"[ \t]+([,.;:!?])", r"\1", texto)
    texto = re.sub(r",\s*,", ",", texto)
    texto = re.sub(r"\A[\s,]+", "", texto)
    texto = re.sub(r"\n[ \t]*,[ \t]*", "\n", texto)
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    # Frase que perdeu o conector inicial começa em minúscula. Só início de
    # texto e de parágrafo: depois de ponto no meio da frase, "etc. isso" e
    # "art. peculato" existem, e trocar letra ali é mexer no que não quebrou.
    return re.sub(r"(\A|\n)([a-zà-ÿ])",
                  lambda m: m.group(1) + m.group(2).upper(), texto.strip())


def explicar(pergunta: str, usuario_id: int | None = None,
             disciplinas: list[str] | None = None,
             mesa_: dict | None = None,
             historico: list[dict] | None = None,
             perfil: dict | None = None) -> dict:
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
    # `usuario_id` também abre a BIBLIOTECA dele (019): a apostila e o resumo
    # que ele subiu entram no contexto junto da lei. É o ponto do produto —
    # "alimente sua IA com seus PDFs" só significa algo se o material chegar
    # ao prompt. Sem usuario_id (CLI), fica só o acervo público.
    # RECORTE POR MESA (021): só quando a mesa pediu isolamento. Com
    # `biblioteca_compartilhada` — o default, e o comportamento anterior à 021 —
    # passa `None` e a busca vê tudo do aluno, como antes. Ler o flag AQUI e não
    # em quem chama evita que uma segunda rota esqueça de aplicá-lo: o recorte
    # anda junto do `mesa_` que já chega nesta função.
    mesa_id = mesa_.get("id") if mesa_ and mesa_.get("biblioteca_compartilhada") is False else None

    # A CONSULTA DE BUSCA NÃO É A MENSAGEM. A 014 deu memória ao MODELO e deixou
    # o BUSCADOR amnésico: o prompt recebia 8 turnos e `retrieval.buscar` recebia
    # a frase isolada. Como `hibrida()` é k-vizinhos e não tem piso de
    # relevância, frase sem assunto não devolve vazio — devolve 6 artigos com
    # confiança total. Medido: "você deveria perguntar se eu já sei algo do
    # assunto... melhor me explicar" trouxe CPP 188/190/203/212, os artigos de
    # INTERROGATÓRIO, no meio de uma conversa sobre eficácia das normas
    # constitucionais. Ver `core/assunto.py`.
    #
    # Citação de dispositivo vai CRUA, e é a exceção que importa: `por_dispositivo`
    # lê o número da própria string, então enriquecer com histórico deixaria um
    # "art. 140" de três turnos atrás sequestrar a pergunta nova — e a resposta
    # viria confiante sobre o artigo errado, que é a pior falha possível aqui.
    consulta = (pergunta if assunto.cita_dispositivo(pergunta)
                else assunto.em_foco(historico, pergunta, disciplinas))

    # `None` = ninguém nomeou assunto nenhum ainda ("olá", "vamos" como primeira
    # fala). NÃO buscar é melhor que buscar por isso: seis artigos sorteados no
    # contexto são um convite pro modelo discorrer sobre eles.
    chunks = (retrieval.buscar(consulta, n=6, usuario_id=usuario_id, mesa_id=mesa_id)
              if consulta else [])
    contexto_material = retrieval.formatar_contexto(chunks) if chunks else None
    contexto_desempenho = _resumo_desempenho(usuario_id, disciplinas) if usuario_id else None
    contexto_mesa = _resumo_mesa(mesa_)
    contexto_programa = _programa_em_foco(mesa_, pergunta, historico)
    contexto_perfil = _resumo_perfil(perfil)

    # A guarda considera as QUATRO fontes, não duas. Ela olhava só material e
    # desempenho, e isso bastava enquanto TODA pergunta buscava — havia sempre
    # material, ainda que sorteado. Passando a não buscar quando a fala não
    # nomeia assunto, "por onde começo?" (nenhuma palavra de conteúdo) caía aqui
    # e recebia resposta enlatada, quando é exatamente a pergunta que o
    # concurso-alvo e o perfil declarado respondem sem precisar de artigo nenhum.
    # Regressão pega por `test_perfil.py`, não em uso.
    if not (contexto_material or contexto_desempenho or contexto_mesa or contexto_perfil
            or contexto_programa):
        return {"resposta": ("Não encontrei isso no material, e ainda não tenho nenhum "
                             "desempenho seu registrado.") if consulta else
                            ("Me diga de que matéria ou assunto você quer tratar — ainda não "
                             "tenho nada seu registrado pra sugerir por onde começar."),
                "fontes": []}

    # Os rótulos de seção usam "###" e nome comum, não MAIÚSCULA seca. O
    # formato anterior ("DESEMPENHO REAL DO ALUNO (dados do banco):") somado
    # à instrução "cite a referência entre colchetes" fez o modelo tratar o
    # NOME DA SEÇÃO como se fosse uma fonte citável: uma resposta real
    # terminou com "...está em 75.3% [DESEMPENHO REAL DO ALUNO]". Rótulo de
    # prompt vazando como citação é pior que citação errada — expõe o
    # andaime e destrói a confiança nas citações verdadeiras da mesma frase.
    partes = []
    if contexto_mesa or contexto_perfil:
        bloco = "\n".join(x for x in (contexto_mesa, contexto_perfil) if x)
        partes.append(f"### Contexto do aluno\n{bloco}")
    if contexto_programa:
        partes.append(contexto_programa)
    if contexto_material:
        partes.append(f"### Trechos de lei recuperados\n{contexto_material}")
    else:
        # A AUSÊNCIA DE MATERIAL É DECLARADA, não omitida. Sem esta seção o
        # modelo recebe um prompt onde a lei simplesmente não é mencionada, e a
        # instrução "se os trechos não cobrirem a pergunta, diga isso" fica sem
        # referente — o convite a responder de memória própria, que é a única
        # coisa que este tutor não pode fazer.
        motivo = ("a busca não encontrou nada para esta pergunta." if consulta else
                  "a mensagem do aluno não nomeia matéria nem assunto, então não houve o "
                  "que buscar.")
        partes.append(
            f"### Trechos de lei recuperados\nNenhum — {motivo} NÃO afirme conteúdo de lei "
            "sem trecho recuperado: use o contexto do aluno e os números dele, e pergunte de "
            "que assunto ele quer tratar.")
    if contexto_desempenho:
        partes.append(f"### Números deste aluno no banco\n{contexto_desempenho}")
    if historico:
        # A CONVERSA ATÉ AQUI, e não só a pergunta solta. Sem isso o aluno
        # que responde "qualquer um" a uma pergunta do tutor recebe de volta
        # "qualquer um de quê?" — aconteceu em uso real. Vem ANTES da
        # pergunta atual porque é o que a contextualiza.
        # O EVENTO entra rotulado como fato, não como fala: "(o aluno
        # respondeu e errou)" dito por "Você" faria o modelo tratar aquilo
        # como coisa que ele mesmo afirmou antes.
        rotulos = {"aluno": "Aluno", "tutor": "Você", "evento": "[fato da sessão]"}
        turnos = "\n".join(
            f"{rotulos.get(m['autor'], 'Aluno')}: {m['texto']}" for m in historico)
        partes.append(f"### Conversa até aqui\n{turnos}")
    else:
        # FATO calculado em código, não deixado pra inferência. A escada
        # pedagógica depende de saber se o assunto é novo, e "é a primeira
        # mensagem" é a única forma de o modelo ter certeza disso — sem essa
        # linha, uma conversa vazia é indistinguível de uma cujo histórico não
        # veio, e ele erra pro lado de já estar no meio da aula.
        partes.append("### Conversa até aqui\nPrimeira mensagem desta conversa.")
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
        "O tempo disponível e o nível declarados calibram o TAMANHO da sugestão final: não "
        "proponha três horas de estudo a quem declarou 1h por dia, nem trate como iniciante quem "
        "se declarou avançado. Não comente o perfil em si — use-o. "
        # ORDEM DE ENSINO — e ela é INVISÍVEL. Este bloco antes começava com o
        # rótulo "ESCADA PEDAGÓGICA" em maiúsculas, e o modelo passou a NARRAR o
        # andaime: uma resposta real abriu com "Perfeito, vamos voltar um degrau
        # na escada pedagógica". Rótulo de prompt vazando na resposta é o mesmo
        # defeito do `[DESEMPENHO REAL DO ALUNO]` citado como fonte, e pela
        # mesma causa: nome próprio dentro do prompt vira vocabulário do modelo.
        # Por isso a instrução não tem mais nome, e a proibição de nomear é
        # explícita.
        "Descubra, explique, e só então teste — nessa ordem, e SEM NUNCA DIZER QUE ESTÁ "
        "FAZENDO ISSO. Em assunto que você ainda não tratou nesta conversa: primeiro descubra o "
        "que o aluno JÁ SABE dele, com UMA pergunta curta e específica — não \"o que você sabe "
        "sobre X?\", que joga o trabalho de volta pra ele, mas algo como \"você já viu a "
        "diferença entre A e B?\". Depois explique o que faltou, apoiado nos trechos "
        "recuperados. Só depois de ter explicado é que testar faz sentido. NÃO proponha teste "
        "sobre assunto que você ainda não tratou aqui: oferecer prova antes da aula é empurrar "
        "produto, e é reclamação real de aluno deste app. A exceção é única e vale sempre: se "
        "ele PEDIR questão, exercício ou treino, atenda NA HORA — o app monta as questões e "
        "você só apresenta, em uma linha. "
        "NUNCA use, na resposta, o vocabulário do seu próprio funcionamento: nada de \"escada "
        "pedagógica\", \"degrau\", \"método socrático\", \"diagnóstico\", \"contexto\", "
        "\"acervo\", \"trechos recuperados\", \"prompt\" ou \"ferramenta\". O aluno veio "
        "estudar Direito, não ler o manual do app. Você é um professor conversando, não um "
        "sistema se descrevendo. "
        "RESPONDA NO TAMANHO DA PERGUNTA. Se o aluno só cumprimentou (\"oi\", \"boa noite\"), "
        "cumprimente de volta em UMA linha e pergunte, curto e aberto, por onde ele quer ir — "
        "citando no máximo as disciplinas do edital dele pra escolher. NÃO abra matéria densa "
        "antes de ele escolher o rumo: despejar um parágrafo sobre eficácia das normas em cima "
        "de um \"boa noite\" cansa e é reclamação real. "
        # PEDIDO DE EXPOSIÇÃO, E POR QUE ELE PRECISA ESTAR AQUI.
        #
        # Reclamação direta do dono: "nem sempre eu quero ficar respondendo
        # perguntas, às vezes eu quero ler sobre o assunto e entender". O prompt
        # não tinha essa saída — mandava descobrir-explicar-testar e TERMINAR COM
        # PERGUNTA, sempre. Medido no cenário `forense_do_zero`: os quatro turnos
        # terminaram com pergunta, inclusive o que respondia a "começa pelo
        # primeiro tópico então", que é pedido de aula e não de sabatina.
        #
        # A ordem descobrir-explicar-testar NÃO cai: ela vale quando é o TUTOR que
        # conduz. O que muda é que o aluno pode pedir a condução de volta.
        "O ALUNO PODE PEDIR PRA LER, EM VEZ DE RESPONDER. Quando ele disser que quer "
        "entender, ler, ver o assunto, ou que não quer pergunta agora: EXPLIQUE corrido, sem "
        "devolver pergunta de diagnóstico, e feche oferecendo continuar (\"quer que eu siga "
        "para X?\") em vez de interrogar. Volte a perguntar quando ele pedir, ou quando a "
        "explicação daquele ponto tiver acabado. "
        # A RESSALVA QUE FALTAVA NA PRIMEIRA VERSÃO DESTA REGRA, e ela é a mais
        # importante do bloco. Sem dizê-la, "explique corrido" foi lido como
        # licença pra ensinar de memória: medido no cenário `quero_ler` já com
        # esta regra ativa, o tutor afirmou "o art. 37, § 1º, da Constituição
        # proíbe..." tendo recebido L8112 153, CP 321 e CP 337-O — nenhuma linha
        # de CF. Explicar corrido muda o FORMATO da resposta, nunca a fonte dela.
        # A REGRA DIZIA "CONTEÚDO DE LEI", E O MODELO LEU LITERALMENTE. Medido na
        # bateria com esta regra já ativa: perguntado "o que o STJ diz sobre
        # peculato de uso?", ele respondeu "o entendimento consolidado do STJ é
        # de que não há tipificação" — jurisprudência inventada, sem uma linha
        # de STJ no acervo. E perguntado pelos pontos que mais caem em Direito
        # Administrativo, escreveu a própria lista TENDO recebido o programa do
        # edital no prompt. Proibir "afirmar lei" deixou de fora doutrina,
        # jurisprudência, súmula e classificação — que é quase tudo o que uma
        # aula tem. Por isso agora a proibição enumera, e diz o que o acervo É.
        # DOUTRINA SEM FONTE PASSA A SER PERMITIDA — MARCADA. Decisão do dono,
        # e a razão dele é boa: "se eu for no Gemini e pedir os princípios ele
        # vai saber me responder". A regra anterior proibia TODO conteúdo sem
        # trecho, e o efeito era pior que o risco que ela evitava: Supremacia,
        # Indisponibilidade e Autotutela não estão em artigo NENHUM da CF, então
        # "não tenho o texto" virava "não te ensino" — que não era a intenção.
        #
        # O que se conserva é o que a proibição existia pra dar: saber o que dá
        # pra CONFERIR. Por isso a licença é só pra CONCEITO, e vem com aviso
        # obrigatório. Número, artigo, súmula e posição de tribunal continuam
        # proibidos sem trecho, porque é ali que a invenção é irrecuperável —
        # medido, o modelo já afirmou entendimento do STJ sobre peculato de uso
        # que não existe, e artigo 37 em conversa sem CF recuperada.
        "SE OS TRECHOS NÃO COBREM, VOCÊ PODE ENSINAR O CONCEITO — MARCANDO. Doutrina, "
        "classificação e definição você pode dar do seu próprio conhecimento quando não houver "
        "trecho: é o caso dos princípios implícitos (supremacia do interesse público, "
        "indisponibilidade, autotutela), que não estão em artigo nenhum. Mas diga, numa linha "
        "curta e explícita, que aquilo NÃO veio do material dele — algo como \"isto é doutrina "
        "e não está no seu material; confira na sua apostila\". Nunca use colchete nesse "
        "trecho: colchete é reservado a fonte recuperada. "
        "O QUE CONTINUA PROIBIDO SEM TRECHO, sem exceção: número de artigo, número de súmula, "
        "pena, prazo, valor, e a posição de qualquer tribunal. Nada de \"o STJ entende que\", "
        "nem para dizer que é pacífico. Se o aluno pedir jurisprudência, diga que não está no "
        "material e ofereça o que a LEI diz. Errar um número é o que estraga a prova dele; "
        "errar uma explicação ele descobre na primeira apostila. "
        "E quando HOUVER trecho, ele manda: cite-o e trate do que ele diz, em vez de recitar o "
        "que você já sabia. "
        "\"QUAIS OS PONTOS QUE MAIS CAEM\" é pedido de MAPA, não de aula: liste os pontos "
        "principais daquele assunto em ordem de importância para a banca dele, curto, um por "
        "linha, e ofereça aprofundar um deles. Não transforme isso numa explicação longa. "
        "HAVENDO programa do edital acima, o mapa É ELE: use aqueles itens, com as palavras "
        "deles, e diga que é o que o edital dele cobra. Sem programa e sem trecho, NÃO invente "
        "a lista — diga que não tem como afirmar o que mais cai sem o material. "
        "ESGOTE UM ASSUNTO ANTES DE IR PARA OUTRO. Enquanto ele demonstrar dúvida no ponto "
        "atual, fique nele e ataque a dúvida por outro ângulo — não avance de tópico nem "
        "ofereça assunto novo. Só troque quando ele pedir, ou quando o ponto estiver claramente "
        "resolvido; e ao trocar, diga em uma linha que está trocando. "
        "UM MICRO-TÓPICO POR RESPOSTA. Não misture dois assuntos diferentes na mesma mensagem — "
        "explicar direitos sociais e emendar competência concorrente no parágrafo seguinte "
        "confunde em vez de ensinar, e também é reclamação real. Se os trechos recuperados "
        "falarem de coisas distintas, ESCOLHA a que responde o aluno e IGNORE o resto; trecho "
        "que veio na busca não é assunto que precisa ser mencionado. Termine com uma pergunta "
        "que trate exclusivamente do conceito que você acabou de explicar. "
        # QUEM DEFINE O ASSUNTO É A CONVERSA, NÃO O QUE VOLTOU DA BUSCA.
        #
        # As duas frases acima não cobriam o caso que quebrou o produto, e ele é
        # o mais traiçoeiro: o trecho casa com as PALAVRAS da pergunta e não com
        # o ASSUNTO da conversa. Medido, com log real — conversa inteira sobre
        # Lei Maria da Penha, aluno responde "dependencia?", e a única coincidência
        # literal de "dependência econômica" no acervo é a L8112 art. 198
        # (salário-família). O tutor respondeu sobre salário-família, com oito
        # turnos de violência doméstica no prompt: do ponto de vista dele, o
        # trecho RESPONDEU a pergunta. Não há como consertar isso na busca — piso
        # de relevância vetorial foi medido e não separa neste acervo (ver
        # Decisões, "CEMITÉRIO DE IDEIAS") —, então a defesa é aqui.
        "O ASSUNTO É O DA CONVERSA, não o do trecho que voltou da busca. Antes de citar, "
        "confira se o trecho é do MESMO instituto que vocês estão tratando: coincidência de "
        "palavra não basta. Se ele só repete um termo da pergunta e pertence a outro assunto "
        "(um artigo sobre benefício de servidor num diálogo sobre violência doméstica, por "
        # A PALAVRA PROIBIDA NÃO PODE ESTAR NA INSTRUÇÃO. Estas duas frases diziam
        # "diga que o ACERVO não tem a lei desse ponto" e "o app monta a questão a
        # partir dos trechos de lei do ACERVO" — trinta linhas depois de a lista de
        # proibições incluir "acervo". Instrução vence proibição, e o resultado
        # medido foi o tutor abrindo resposta com "O acervo disponível no momento
        # não aborda...", em 3 de 3 rodadas de `avaliar_chat.py`.
        #
        # É a QUARTA vez que este projeto vê o mesmo mecanismo: `[DESEMPENHO REAL
        # DO ALUNO]` citado como fonte, "escada pedagógica" narrada, e agora esta.
        # A lição é sempre a mesma e vale escrever de novo: nome próprio dentro do
        # prompt vira vocabulário do modelo, e proibir sem TIRAR da instrução não
        # funciona. A lista de proibições fica (ela precisa nomear pra proibir),
        # mas nada mais no prompt manda usar a palavra.
        "exemplo), NÃO o use nem o cite — diga que não localizou a lei desse ponto, "
        "responda o que der pelo que já foi tratado na conversa e siga dela. Trocar de assunto "
        "no meio da explicação por causa de uma palavra igual é o pior erro que você pode "
        "cometer aqui. "
        # QUEM PEDE TREINO É TREINADO NA HORA — E O APP É QUE MONTA A QUESTÃO.
        #
        # Três desenhos foram tentados aqui, nesta ordem, e vale registrar por
        # que os dois primeiros caíram:
        #
        # 1. "mande usar o botão". Medido em log real: "queria 2 questões
        #    rápidas de direito constitucional" recebeu "clique no botão Quero
        #    questões sobre isto". O aluno pediu treino e levou instrução de
        #    interface — parada de conversa, e o avaliador achou 16 casos disso
        #    nas conversas gravadas.
        #
        # 2. "escreva a questão você mesmo, no chat". Resolvia o atrito jogando
        #    fora o que dá valor à questão: sem `fonte_chunks` não há
        #    proveniência, sem gravar não há fila SM-2, sem fila não há
        #    repetição espaçada — e a resposta do aluno não conta no progresso
        #    dele. Chat mais limpo, estudo pior.
        #
        # 3. (este) o SERVIDOR aciona `geracao.sob_demanda`, o mesmo que o botão
        #    acionava, e as questões chegam junto da resposta. Proveniência,
        #    fila e progresso intactos; o clique é que desaparece.
        #
        # Daí a instrução ser NEGATIVA nos dois sentidos: o tutor não escreve a
        # questão (o app escreve, com o artigo conferido) e não manda clicar (o
        # app já está gerando enquanto ele fala). O papel dele é uma linha de
        # abertura — e é só isso.
        "SE O ALUNO PEDIR QUESTÃO, EXERCÍCIO OU TREINO: o app JÁ ESTÁ montando as questões "
        "a partir dos trechos de lei, e elas vão aparecer logo abaixo da sua resposta, dentro "
        "desta conversa. Então você NÃO escreve a questão e NÃO manda clicar em nada. "
        "Responda em UMA OU DUAS LINHAS, dizendo sobre o que elas são e sugerindo por onde ele "
        "comece a pensar — algo como \"vamos treinar isso; as questões estão logo abaixo, "
        "repare no que a lei exige do funcionário público\". Não repita o enunciado, não "
        "adiante o gabarito, não pergunte de novo se ele quer. "
        # A PROIBIÇÃO FOI DESOBEDECIDA em log real, então ela ficou explícita
        # sobre o que exatamente não fazer: o tutor escreveu
        # "[Questão 1: ... a) Legalidade; b) Eficiência; c) Autotutela...]"
        # NO MESMO TURNO em que o app gerou três questões de verdade — ou seja,
        # duplicou o trabalho e entregou a versão sem proveniência junto da boa.
        "Nunca diga que não tem como gerar e nunca fale de botão. E NÃO ESCREVA A QUESTÃO: "
        "nada de \"Questão 1:\", nada de enunciado numerado, nada de alternativas a), b), c) — "
        "nem entre colchetes, nem em lista, nem no meio da frase. Colchete na sua resposta é "
        "reservado a CITAÇÃO de fonte, e escrever questão ali a disfarça de lei. O app já "
        "montou os itens com o artigo conferido; a sua parte é a linha de abertura. "

        "Linhas marcadas como [fato da sessão] são o que o aluno FEZ (respondeu uma questão, "
        "acertou, errou) — não são fala sua nem dele. Use-as: errar a questão que você acabou de "
        "propor vale mais que qualquer coisa que ele diga sobre entender ou não, e a próxima "
        "resposta deve partir DAÍ, não repetir a explicação que já não funcionou. "
        "Quando houver conversa anterior, CONTINUE dela: se o aluno responder de forma curta "
        "('qualquer um', 'esse mesmo', 'sim'), entenda que ele está respondendo à SUA última "
        "pergunta e siga daí, em vez de pedir que ele reformule. Não repita explicação já dada. "
        "Português brasileiro, tom direto. Termine com uma pergunta ou sugestão que seja o "
        "próximo passo para este aluno — não a mesma oferta de questões em toda "
        "resposta. Fechar três mensagens seguidas com o mesmo convite é ruído que ele aprende a "
        "ignorar, e aí o convite não funciona nem quando é a hora certa."
    )
    resposta = llm.obter().gerar("\n\n".join(partes), sistema, max_tokens=1500)

    # A ORDEM IMPORTA: tira as questões ANTES de limpar citações. Questão escrita
    # pelo modelo vem cheia de "art. 37" inventado, e limpar citação primeiro
    # gastaria trabalho num texto que vai ser apagado inteiro.
    #
    # `limpar_questoes` existia, tinha teste e NÃO ERA CHAMADA: perdi esta linha
    # ao refazer a edição da função, e o efeito foi silencioso — a suíte
    # continuou verde (o teste chama a função direto) e a bateria trouxe as
    # questões inline de volta. Teste de unidade sobre função morta passa.
    resposta, questoes_tiradas = limpar_questoes(resposta)
    if questoes_tiradas and len(resposta) < 40:
        # Sobrou só cacoete. Uma linha honesta é melhor que um resto de frase —
        # e reescrever prosa de modelo é o que `_costurar` aprendeu a não fazer.
        resposta = ("Vamos treinar isso — as questões estão logo abaixo, "
                    "com o artigo conferido.")
    return {"resposta": limpar_citacoes(resposta, chunks), "fontes": chunks,
            "questoes_do_modelo_tiradas": questoes_tiradas}


def gerar_questoes(chunks: list[dict], quantidade: int = 5,
                   tipo: str = "resposta_livre") -> list[dict]:
    """
    Gera em lotes pequenos: uma chamada pedindo 10 questões estoura tokens.

    `tipo` troca prompt, schema e validação — o resto do laço (deduplicar
    tema, parar quando o modelo trava, cortar no pedido) é idêntico nos dois
    formatos, e duplicar a função pra trocar duas constantes faria as
    correções futuras do laço valerem só pra metade.
    """
    ce = tipo == "certo_errado"
    contexto = retrieval.formatar_contexto(chunks)
    modelo = llm.obter()
    coletadas: list[dict] = []
    restante = quantidade

    while restante > 0:
        pedido = min(LOTE_GERACAO, restante)
        rotulo = "itens CERTO/ERRADO" if ce else "questões"
        prompt = (f"Gere {pedido} {rotulo} a partir do material.\n\n"
                  f"MATERIAL:\n{contexto}")
        if coletadas:
            temas = ", ".join(q["tema"] for q in coletadas)
            prompt += f"\n\nNÃO repita estes temas já cobrados: {temas}"
        itens = modelo.gerar_json(prompt,
                                  SISTEMA_GERADOR_CE if ce else SISTEMA_GERADOR,
                                  max_tokens=4096,
                                  schema=ESQUEMA_QUESTOES_CE if ce else ESQUEMA_QUESTOES)
        if isinstance(itens, dict):
            itens = itens.get("questoes", [])
        novas = _validar_ce(itens) if ce else _validar(itens)
        if not novas:
            break               # modelo travou; devolve o que já veio
        coletadas.extend(novas)
        restante = quantidade - len(coletadas)

    return coletadas[:quantidade]


def _artigo_limpo(q) -> str | None:
    return (q.get("artigo") or "").strip().replace("Art.", "").strip() or None


def _validar(itens) -> list[dict]:
    validas = []
    for q in itens or []:
        if not isinstance(q, dict) or not q.get("enunciado") or not q.get("gabarito"):
            continue
        dicas = [str(d).strip() for d in (q.get("dicas") or []) if str(d).strip()]
        validas.append({
            "tipo": "resposta_livre",
            "artigo": _artigo_limpo(q),
            "tema": (q.get("tema") or "Sem tema").strip(),
            "enunciado": q["enunciado"].strip(),
            "gabarito": q["gabarito"].strip(),
            "gabarito_ce": None,
            "dicas": dicas[:3],
        })
    return validas


def _validar_ce(itens) -> list[dict]:
    """
    `gabarito_ce` é checado com `isinstance(..., bool)`, não por veracidade:
    `if not q.get("gabarito_ce")` descartaria TODO item cujo gabarito é
    ERRADO (False é falsy) — metade do lote, e justamente a metade que dá
    valor ao formato. Item sem o campo, ou com string no lugar do booleano,
    é que não serve.

    A justificativa vira `gabarito` (a coluna segue NOT NULL nos dois
    tipos) e `dicas` fica vazia de propósito: não há escada socrática num
    item binário — ver `avaliar_certo_errado`.
    """
    validas = []
    for q in itens or []:
        if not isinstance(q, dict) or not q.get("enunciado"):
            continue
        if not isinstance(q.get("gabarito_ce"), bool) or not q.get("justificativa"):
            continue
        validas.append({
            "tipo": "certo_errado",
            "artigo": _artigo_limpo(q),
            "tema": (q.get("tema") or "Sem tema").strip(),
            "enunciado": q["enunciado"].strip(),
            "gabarito": q["justificativa"].strip(),
            "gabarito_ce": q["gabarito_ce"],
            "dicas": [],
        })
    return validas

# Série Cebraspe: um texto-base e N itens que o julgam. É a forma real da
# prova, não um enfeite — ver db/013_contexto.sql.
ESQUEMA_SERIE_CE = {
    "type": "OBJECT",
    "properties": {
        "artigo": {"type": "STRING"},
        "contexto": {"type": "STRING"},
        "itens": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "tema": {"type": "STRING"},
                    "enunciado": {"type": "STRING"},
                    "gabarito_ce": {"type": "BOOLEAN"},
                    "justificativa": {"type": "STRING"},
                },
                "required": ["tema", "enunciado", "gabarito_ce", "justificativa"],
                "propertyOrdering": ["tema", "enunciado", "gabarito_ce", "justificativa"],
            },
        },
    },
    "required": ["artigo", "contexto", "itens"],
    "propertyOrdering": ["artigo", "contexto", "itens"],
}

SISTEMA_SERIE_CE = SISTEMA_GERADOR_CE + """

FORMATO DESTA TAREFA — TEXTO-BASE + ITENS (o "Texto associado" da prova):
- Escreva UM texto-base curto a partir do material e VÁRIOS itens que o julgam.
- O texto-base é uma SITUAÇÃO HIPOTÉTICA concreta (pessoas, cargos, prazos, fatos) construída \
sobre o dispositivo, não a repetição da lei. É o que o Cebraspe faz: a lei fica implícita e o \
candidato precisa aplicá-la ao caso.
  RUIM:  "O art. 15 estabelece que o prazo para entrar em exercício é de quinze dias."
  BOM:   "Pedro foi empossado no cargo de analista em 3 de março e entrou em exercício em 25 \
de março, sem apresentar justificativa."
- O texto-base NÃO afirma nem nega nada que os itens vão julgar: ele descreve. Quem afirma são \
os itens.
- Cada item se sustenta lendo o texto-base — nunca escreva "conforme o item anterior".
- Os itens cobram ÂNGULOS DIFERENTES do mesmo caso, não a mesma coisa reescrita."""


def gerar_serie_ce(chunks: list[dict], n_itens: int = 3) -> dict | None:
    """
    Gera UM texto-base e `n_itens` itens C/E que o julgam.

    Chamada única, não uma por item, de propósito: os itens precisam ser
    coerentes ENTRE SI (mesma situação, mesmos nomes, ângulos diferentes) e
    isso só é possível se o modelo os escrever de uma vez, vendo o texto que
    ele mesmo acabou de criar. Gerar item por item sobre um contexto pronto
    produziria repetição, que é exatamente o que o formato não deve ter.

    Devolve `None` quando o modelo não entregou contexto + pelo menos um
    item válido — quem chama trata como "não rendeu", igual ao lote vazio de
    `gerar_questoes`, em vez de gravar série capenga.
    """
    contexto = retrieval.formatar_contexto(chunks)
    d = llm.obter().gerar_json(
        f"Gere um texto-base e {n_itens} itens CERTO/ERRADO sobre ele, a partir do "
        f"material.\n\nMATERIAL:\n{contexto}",
        SISTEMA_SERIE_CE, max_tokens=4096, schema=ESQUEMA_SERIE_CE)
    if not isinstance(d, dict) or not (d.get("contexto") or "").strip():
        return None
    itens = _validar_ce(d.get("itens"))
    if not itens:
        return None
    artigo = _artigo_limpo(d)
    for i, item in enumerate(itens, 1):
        item["artigo"] = artigo
        item["ordem_no_contexto"] = i
    return {"artigo": artigo, "contexto": d["contexto"].strip(), "itens": itens}
