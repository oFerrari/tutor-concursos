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
from . import assunto, llm, retrieval

VERSAO = "socratic-v32"

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
    consulta = pergunta if assunto.cita_dispositivo(pergunta) else assunto.em_foco(historico, pergunta)

    # `None` = ninguém nomeou assunto nenhum ainda ("olá", "vamos" como primeira
    # fala). NÃO buscar é melhor que buscar por isso: seis artigos sorteados no
    # contexto são um convite pro modelo discorrer sobre eles.
    chunks = (retrieval.buscar(consulta, n=6, usuario_id=usuario_id, mesa_id=mesa_id)
              if consulta else [])
    contexto_material = retrieval.formatar_contexto(chunks) if chunks else None
    contexto_desempenho = _resumo_desempenho(usuario_id, disciplinas) if usuario_id else None
    contexto_mesa = _resumo_mesa(mesa_)
    contexto_perfil = _resumo_perfil(perfil)

    # A guarda considera as QUATRO fontes, não duas. Ela olhava só material e
    # desempenho, e isso bastava enquanto TODA pergunta buscava — havia sempre
    # material, ainda que sorteado. Passando a não buscar quando a fala não
    # nomeia assunto, "por onde começo?" (nenhuma palavra de conteúdo) caía aqui
    # e recebia resposta enlatada, quando é exatamente a pergunta que o
    # concurso-alvo e o perfil declarado respondem sem precisar de artigo nenhum.
    # Regressão pega por `test_perfil.py`, não em uso.
    if not (contexto_material or contexto_desempenho or contexto_mesa or contexto_perfil):
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
        "ESCADA PEDAGÓGICA, e respeite a ordem dos degraus. Em assunto que você ainda não "
        "tratou nesta conversa: primeiro descubra o que o aluno JÁ SABE dele, com UMA pergunta "
        "curta e específica — não \"o que você sabe sobre X?\", que joga o trabalho de volta pra "
        "ele, mas algo como \"você já viu a diferença entre A e B?\". Depois explique o que "
        "faltou, apoiado nos trechos recuperados. Só DEPOIS de ter explicado é que testar faz "
        "sentido. NÃO ofereça o botão de gerar questões sobre assunto que você ainda não "
        "explicou aqui: oferecer prova antes da aula é empurrar produto, e é reclamação real de "
        "aluno deste app. A exceção é única e vale sempre: se ele PEDIR questão, exercício ou "
        "simulado, atenda na hora, sem escada nenhuma. "
        "Se o aluno pedir questão, exercício ou simulado: NÃO escreva a questão na resposta. "
        "Diga que dá pra gerar e mande ele usar o botão \"Quero questões sobre isto\", logo "
        "abaixo. O app monta a questão a partir dos trechos de lei do acervo, confere de qual "
        "artigo ela saiu e a grava na fila de revisão — questão escrita solta no chat não passa "
        "por nenhuma dessas três coisas e some quando a conversa rola. Nunca diga que não tem "
        "como gerar. "
        "Linhas marcadas como [fato da sessão] são o que o aluno FEZ (respondeu uma questão, "
        "acertou, errou) — não são fala sua nem dele. Use-as: errar a questão que você acabou de "
        "propor vale mais que qualquer coisa que ele diga sobre entender ou não, e a próxima "
        "resposta deve partir DAÍ, não repetir a explicação que já não funcionou. "
        "Quando houver conversa anterior, CONTINUE dela: se o aluno responder de forma curta "
        "('qualquer um', 'esse mesmo', 'sim'), entenda que ele está respondendo à SUA última "
        "pergunta e siga daí, em vez de pedir que ele reformule. Não repita explicação já dada. "
        "Português brasileiro, tom direto. Termine com uma pergunta ou sugestão que seja o "
        "PRÓXIMO DEGRAU da escada pra este aluno — não a mesma oferta de questões em toda "
        "resposta. Fechar três mensagens seguidas com o mesmo convite é ruído que ele aprende a "
        "ignorar, e aí o convite não funciona nem quando é a hora certa."
    )
    resposta = llm.obter().gerar("\n\n".join(partes), sistema, max_tokens=1500)
    return {"resposta": resposta, "fontes": chunks}


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
