"""
Recuperação híbrida.

Três caminhos, em ordem de precisão:

1. `por_dispositivo` — o aluno citou "art. 312" ou "§1º". Busca exata por
   metadado. Nenhum vetor compete com isso em precisão, e quando ela acerta
   NÃO se acrescenta complemento semântico: encher a resposta de artigos
   parecidos só dá ao modelo material para citar fonte errada.
2. `por_rubrica` — o aluno usou o nome do crime ("concussão"). Casa contra a
   rubrica, que é mais preciso que casar contra o corpo do artigo.
3. `hibrida` — funde ranking vetorial e ranking full-text português com
   Reciprocal Rank Fusion. RRF dispensa normalizar scores de escalas
   diferentes (distância de cosseno vs ts_rank), que é o erro clássico de
   quem tenta somar os dois direto.

O braço lexical ignora palavras que existem em todo dispositivo — "art",
"parágrafo", "inciso", "caput". Sem isso, a consulta "art. 312" casa com os
437 chunks do código e o ranking vira ruído.
"""
import re

from . import db
from .embeddings import embed_consulta

VERSAO = "retrieval-v4"
RRF_K = 60  # constante de amortecimento padrão do RRF

# Material `historico` (livro de emendas: "Redação Anterior", múltiplas
# versões do mesmo artigo) vale MENOS que lei vigente na fusão. Não é
# exclusão — ele foi ingerido justamente pra estar disponível, e continua
# ganhando quando é de fato a melhor resposta (pergunta sobre evolução de
# um dispositivo). É desempate: ele entra por janela de parágrafo, não por
# artigo, então gera muito mais candidatos parecidos que uma lei — e sem
# peso ele tomava 4 das 6 vagas de "princípios da administração pública",
# uma delas uma página de LEGENDA DE SÍMBOLOS. Vaga gasta com índice é
# contexto que o modelo não tem pra responder.
#
# 0.5 medido contra o gabarito de avaliar_retrieval.py: em 0.7 ainda
# sobravam 2 chunks de histórico no top-6; em 0.5 zeram, e nenhum caso que
# passava deixou de passar. HONESTIDADE: isto NÃO conserta o art. 37 da CF
# (ver o docstring de avaliar_retrieval.py) — aquilo é diluição de chunk
# gigante, problema diferente. Aqui só se ganha qualidade do contexto.
PESO_HISTORICO = 0.5

# O braço LEXICAL pesa mais que o semântico na fusão. Não é preferência de
# gosto: é correção de um viés medido contra chunks GRANDES.
#
# O art. 37 da CF tem 13.059 caracteres (média do acervo: 1.245) e cobre
# concurso público, licitação, teto remuneratório e improbidade no mesmo
# artigo. O embedding é a média disso tudo, então "administração direta e
# indireta" — que é literalmente o começo do caput — o encontrava em 83º
# lugar no semântico, contra 3º no lexical. Entrando em uma lista só, o RRF
# o punha atrás de chunks medianos presentes nas duas, e ele NÃO chegava ao
# contexto que o tutor lê. Ampliar o pool de candidatos de 30 pra 200 não
# resolvia (testado): o problema é a posição, não o corte.
#
# Casar frase exata é justamente o que o braço lexical faz bem e o vetor
# médio faz mal em texto longo. 1.5 é o MENOR valor que corrige, medido
# contra o gabarito de avaliar_retrieval.py: top-6 de 28/32 pra 30/32, sem
# nenhum caso deixando de passar. Valores maiores (2, 3, 5) não melhoram
# mais nada — sinal de que 1.5 já basta e o resto seria ajuste fino a um
# gabarito de 32 casos, que é pouco pra isso.
#
# O conserto de RAIZ continua sendo sub-chunk do artigo gigante pro
# embedding (mantendo o artigo como unidade de citação); isto aqui compra
# o resultado sem reingestão, e o gabarito agora tem os casos que
# denunciariam uma regressão.
PESO_LEXICAL = 1.5

RE_CITACAO = re.compile(r"(?i)\bart(?:igo)?s?\.?\s*(\d+[\-\wºo]*)")
GENERICOS = {"art", "arts", "artigo", "artigos", "paragrafo", "parágrafo",
             "paragrafos", "parágrafos", "inciso", "incisos", "caput",
             "lei", "codigo", "código", "cf", "cp", "cpp"}

CAMPOS = """c.id, c.texto, c.norma, c.artigo, c.paragrafo, c.rubrica, c.secao,
            c.pagina, d.titulo, d.disciplina, d.tipo"""

# DONO DO MATERIAL (migração 019). "O público MAIS o meu", e nada além.
#
# Vai DENTRO das CTEs `sem`/`lex`, não só no WHERE final, e a diferença não é
# estética: as CTEs cortam em LIMIT k ANTES do join com `documento`. Filtrar
# depois deixaria o material de outros alunos OCUPAR vagas do top-k e ser
# descartado em seguida — a busca perderia recall silenciosamente, e quanto
# mais gente subisse apostila, pior ficaria pra todos.
#
# `usuario_id = NULL` é NULL (nunca true) em SQL, então quem chama sem
# identificar o usuário — a CLI, `avaliar_retrieval.py`, o gabarito — vê
# exatamente o acervo público. O padrão inseguro seria o contrário.
DONO = "(d.usuario_id IS NULL OR d.usuario_id = %(uid)s)"

# MESA DO MATERIAL (migração 021). Some junto do DONO, dentro das mesmas CTEs, e
# pelo mesmo motivo: filtrar DEPOIS de rankear faria o material da outra mesa
# gastar vaga no top-6 e sair da lista — a pergunta perderia contexto sem
# ninguém ver por quê.
#
# Lê-se: "sem mesa pedida, passa tudo; senão público passa sempre e material
# privado passa se não tiver mesa (pool comum) ou se for desta mesa".
#
# A PRIMEIRA guarda (`%(mid)s IS NULL`) é o conserto de um bug que só apareceu
# medindo: sem ela, chamar com `mesa_id=None` — que significa "não recorte" —
# EXCLUÍA todo material que tem mesa, porque `d.mesa_id = NULL` é NULL e nunca
# true em SQL. O caso comum (biblioteca compartilhada, o default) ficava sem ver
# a própria biblioteca. O `::bigint` é obrigatório: parâmetro sozinho num
# `IS NULL` estoura IndeterminateDatatype, a mesma armadilha do `::bigint[]` que
# o reingest.py já precisou e do `%s::text` da 020.
MESA = ("(%(mid)s::bigint IS NULL OR d.usuario_id IS NULL"
        " OR d.mesa_id IS NULL OR d.mesa_id = %(mid)s)")

SQL_HIBRIDA = f"""
WITH sem AS (
    SELECT c.id, ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(emb)s::vector) AS pos
    FROM chunk c JOIN documento d ON d.id = c.documento_id
    WHERE c.embedding IS NOT NULL AND {DONO} AND {MESA}
    ORDER BY c.embedding <=> %(emb)s::vector
    LIMIT %(k)s
),
lex AS (
    SELECT c.id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.busca, q) DESC) AS pos
    FROM chunk c
    JOIN documento d ON d.id = c.documento_id,
         websearch_to_tsquery('portuguese', %(termos)s) q
    WHERE c.busca @@ q AND {DONO} AND {MESA}
    ORDER BY ts_rank_cd(c.busca, q) DESC
    LIMIT %(k)s
)
SELECT {CAMPOS},
       (COALESCE(1.0 / (%(rrf)s + sem.pos), 0) +
        COALESCE(%(peso_lexical)s / (%(rrf)s + lex.pos), 0))
       * CASE WHEN d.tipo = 'historico' THEN %(peso_historico)s ELSE 1 END AS score
FROM chunk c
JOIN documento d ON d.id = c.documento_id
LEFT JOIN sem ON sem.id = c.id
LEFT JOIN lex ON lex.id = c.id
WHERE sem.id IS NOT NULL OR lex.id IS NOT NULL
ORDER BY score DESC
LIMIT %(n)s
"""


def _termos_lexicais(pergunta: str) -> str:
    """Remove palavras presentes em todo dispositivo, que só geram ruído."""
    palavras = [p for p in re.findall(r"[\wÀ-ÿ\-]+", pergunta)
                if p.lower() not in GENERICOS]
    return " ".join(palavras) or pergunta


def _normas_existentes() -> list[str]:
    """Consulta o banco em vez de fixar uma lista — corpus cresce (CP, CF,
    ADCT hoje; CPP, Lei 8.112 depois) e a lista hardcoded ficaria pra trás."""
    return [r["norma"] for r in db.query(
        "SELECT DISTINCT norma FROM chunk WHERE norma IS NOT NULL")]


#  Gente fala "da constituição", não "da CF" — a sigla sozinha não cobre
#  como a pergunta é feita de verdade. Alias só para os apelidos comuns;
#  a sigla em si já é coberta dinamicamente por _normas_existentes().
APELIDOS_NORMA = {
    "CF": ("constituição", "constituicao"),
    "CP": ("código penal", "codigo penal"),
}


def _norma_mencionada(pergunta: str) -> str | None:
    """
    "art. 121 do CP" e "art. 121 da CF" são perguntas DIFERENTES — mas
    RE_CITACAO só pega o número. Com uma norma só no banco isso nunca doeu;
    com CP+CF+ADCT convivendo (todas têm artigos de número baixo), sem isso
    "art. 5" podia devolver a CF antes do CP mesmo quando a pergunta cita
    "CP" explicitamente — ordem alfabética de norma não é intenção do
    usuário. Casa como palavra inteira, case-insensitive; sigla ou apelido.
    """
    p = pergunta.upper()
    for norma in _normas_existentes():
        if re.search(rf"\b{re.escape(norma.upper())}\b", p):
            return norma
        for apelido in APELIDOS_NORMA.get(norma, ()):
            if re.search(rf"\b{re.escape(apelido.upper())}\b", p):
                return norma
    return None


def por_dispositivo(pergunta: str, n: int = 4, usuario_id: int | None = None,
                    mesa_id: int | None = None) -> list[dict]:
    """
    Artigos 1º a 9º levam o ordinal "º" por convenção de redação legislativa
    (LC 95/1998); do 10 em diante não. Quase ninguém digita "º" ao perguntar
    — "art. 1" é o normal. Comparar cru contra `c.artigo` ("1º" no banco)
    nunca batia para NENHUMA norma nos artigos 1-9, justamente os mais
    citados (art. 1º e 5º da CF, por exemplo). Tira o "º"/"o" final dos dois
    lados antes de comparar; não afeta sufixo de letra ("103-A"), só ordinal.
    """
    m = RE_CITACAO.search(pergunta)
    if not m:
        return []
    norma = _norma_mencionada(pergunta)
    return db.query(
        f"""SELECT {CAMPOS}, 1.0 AS score
            FROM chunk c JOIN documento d ON d.id = c.documento_id
            WHERE regexp_replace(c.artigo, '[ºo]$', '', 'i')
                  = regexp_replace(%(art)s, '[ºo]$', '', 'i')
              AND (%(norma)s::text IS NULL OR c.norma = %(norma)s)
              AND {DONO} AND {MESA}
            ORDER BY d.tipo = 'lei' DESC, c.norma, c.ordem
            LIMIT %(n)s""",
        {"art": m.group(1), "n": n, "norma": norma, "uid": usuario_id, "mid": mesa_id},
    )


def por_rubrica(pergunta: str, n: int = 4, usuario_id: int | None = None,
                mesa_id: int | None = None) -> list[dict]:
    """Nome de crime é o jeito humano de referenciar um tipo penal."""
    return db.query(
        f"""SELECT {CAMPOS}, 1.0 AS score
            FROM chunk c JOIN documento d ON d.id = c.documento_id,
                 websearch_to_tsquery('portuguese', %(t)s) q
            WHERE c.rubrica IS NOT NULL
              AND to_tsvector('portuguese', c.rubrica) @@ q
              AND {DONO} AND {MESA}
            ORDER BY ts_rank_cd(to_tsvector('portuguese', c.rubrica), q) DESC
            LIMIT %(n)s""",
        {"t": _termos_lexicais(pergunta), "n": n, "uid": usuario_id, "mid": mesa_id},
    )


def hibrida(pergunta: str, n: int = 6, k: int = 40,
            usuario_id: int | None = None, mesa_id: int | None = None) -> list[dict]:
    return db.query(SQL_HIBRIDA, {
        "emb": embed_consulta(pergunta),
        "termos": _termos_lexicais(pergunta),
        "uid": usuario_id,
        "mid": mesa_id,
        "k": k,
        "n": n,
        "rrf": RRF_K,
        "peso_historico": PESO_HISTORICO,
        "peso_lexical": PESO_LEXICAL,
    })


def buscar(pergunta: str, n: int = 6, usuario_id: int | None = None,
           mesa_id: int | None = None) -> list[dict]:
    """
    Ponto de entrada. Precisão vence recall: quando há acerto exato de
    dispositivo, devolve só ele. Contexto extra não ajuda o modelo a
    responder "o que diz o art. 312" — só o convida a citar outra coisa.

    `usuario_id` abre a biblioteca PRIVADA daquele aluno (migração 019) além
    do acervo público. Omitir é o padrão SEGURO — só público —, e é por isso
    que o parâmetro é opcional em vez de obrigatório: a CLI, o `gerar.py` e o
    `avaliar_retrieval.py` medem contra o acervo compartilhado, e passar a
    biblioteca de alguém ali mudaria o gabarito de um teste conforme o que um
    aluno subiu ontem.
    """
    exatos = por_dispositivo(pergunta, n=n, usuario_id=usuario_id, mesa_id=mesa_id)
    if exatos:
        return exatos

    rubricas = por_rubrica(pergunta, n=3, usuario_id=usuario_id, mesa_id=mesa_id)
    if rubricas:
        # Acerto de rubrica é forte: só 2 vagas de complemento, para permitir
        # comparação entre tipos sem afogar a resposta em artigo parecido.
        vistos = {c["id"] for c in rubricas}
        extra = [c for c in hibrida(pergunta, n=4, usuario_id=usuario_id, mesa_id=mesa_id)
                 if c["id"] not in vistos][:2]
        return rubricas + extra
    return hibrida(pergunta, n=n, usuario_id=usuario_id, mesa_id=mesa_id)


def formatar_contexto(chunks: list[dict]) -> str:
    """
    Monta o bloco de contexto com referência, para o tutor citar a fonte.

    A referência NÃO menciona parágrafo: o chunk é o artigo inteiro, e
    rotulá-lo como "§1º" porque contém um parágrafo faz o modelo atribuir
    ao §1º o que está no caput. Errar dispositivo é grave para concurseiro.
    """
    return "\n\n---\n\n".join(f"[{referencia(c)}]\n{c['texto']}" for c in chunks)


def referencia(c: dict) -> str:
    """O rótulo que acompanha o trecho no prompt — e a ÚNICA fonte que o tutor
    está autorizado a citar.

    Saiu de dentro de `formatar_contexto` pra ter um dono só: quem confere se
    uma citação da resposta tem trecho por trás (`socratic.limpar_citacoes`)
    precisa da MESMA regra de formação, e duas cópias divergem — mesma decisão
    de `RE_CITACAO` ser importada em vez de copiada em `core/assunto.py`."""
    ref = c["titulo"]
    if c.get("artigo"):
        ref += f", art. {c['artigo']}"
        if c.get("rubrica"):
            ref += f" — {c['rubrica']}"
    elif c.get("pagina"):
        ref += f", p. {c['pagina']}"
    return ref
