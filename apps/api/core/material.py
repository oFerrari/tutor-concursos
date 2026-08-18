"""
Biblioteca do aluno — material PRIVADO (apostila, resumo, jurisprudência)
indexado no mesmo acervo da lei, mas visível só para quem subiu.

Por que existe separado de `ingest.py`: a CLI é um script de operador, com
`print` e `sys.exit`, e ingere lei no acervo COMPARTILHADO. O que a tela
/materiais recebe é outra coisa — arquivo de UM aluno, subido por HTTP, que
precisa de dono, de estado de processamento e de nunca derrubar o request.
A parte comum de verdade (extrair -> chunk -> embed -> gravar) é curta; o
que difere é tudo em volta.

DECISÃO CENTRAL: material do aluno NUNCA entra como `tipo='lei'`.
`chunk_lei` extrai (norma, artigo) para permitir citação exata de
dispositivo, e apostila comentada é justamente onde isso mente: o texto
cita "art. 312" no meio de um parágrafo do professor, e virar um chunk com
`artigo='312'` faria `por_dispositivo("art. 312")` devolver o comentário da
apostila em vez da lei. Vai tudo por `chunk_generico` — perde citação por
artigo, mantém busca híbrida. É o mesmo raciocínio de `tipo='historico'`.
"""
import hashlib
import re

from . import chunking, db, embeddings

VERSAO = "material-v1"

LOTE = 32
MIN_CHARS = 200

# Sem 'lei' e sem 'historico', e a ausência é a decisão acima: os dois
# prometem coisa que material privado não pode cumprir (citação exata de
# dispositivo). Sobra o que a tela realmente oferece.
TIPOS = ("aula", "resumo", "jurisprudencia")


# ------------------------------------------------------ classificar sozinho
# Saída estruturada, e os dois campos são STRING LIVRE de propósito. A lista
# fechada de `usuario.perfil` (015) existe porque aquele texto vai pro PROMPT
# do tutor — campo livre ali é injeção de instrução. Aqui vai pra WHERE de
# recorte e pra rótulo de tela: o pior caso é uma string que não casa nada.
ESQUEMA_CLASSE = {
    "type": "object",
    "properties": {
        "disciplina": {"type": "string"},
        "assunto": {"type": "string"},
    },
    "required": ["disciplina", "assunto"],
}

# Quanto do material vai pro classificador. O começo basta: apostila abre com
# capa, sumário e o título da aula — é exatamente onde "Aula 03: Remédios
# constitucionais" está escrito. Mandar o PDF inteiro multiplicaria a cota por
# nada, e num curso de 14 aulas isso são 14 chamadas.
MAX_CHARS_CLASSE = 6_000


def classificar(texto: str, disciplinas_conhecidas: list[str] | None = None) -> dict:
    """
    Descobre disciplina e assunto lendo o começo do material.

    Existe porque exigir o rótulo no upload obriga o aluno a LER antes de
    subir — e o caso que mais importa é justamente o material que ele não
    conhece ("joguei lá, não sei se agrega"). Quem tem que dizer do que se
    trata é o sistema.

    `disciplinas_conhecidas` vem do acervo e entra no prompt como preferência,
    não como jaula: casar com nome que já existe é o que faz `mesa.filtro`
    (ILIKE dos dois lados) encontrar o material depois. Inventar "Direito
    Const." quando o acervo diz "Direito Constitucional" produziria material
    indexado que nenhuma mesa alcança — o mesmo defeito do alvo manual com
    nome livre, documentado na 017.

    Falha do modelo devolve `{}`, não estoura: material sem rótulo continua
    indexado e buscável, só aparece como "não identificado" na tela. Perder o
    material inteiro porque a cota acabou seria trocar um defeito pequeno por
    um grande.
    """
    from . import llm
    conhecidas = ", ".join(disciplinas_conhecidas or []) or "(nenhuma ainda)"
    sistema = (
        "Você recebe o começo de um material de estudo para concurso público "
        "brasileiro (apostila, aula, resumo ou jurisprudência) e devolve a "
        "DISCIPLINA e o ASSUNTO dele.\n\n"
        f"Disciplinas que já existem no acervo: {conhecidas}.\n"
        "PREFIRA um desses nomes quando o material for da mesma matéria, "
        "escrito igual — é por nome que o recorte da mesa encontra o material "
        "depois, e \"Direito Const.\" não casa com \"Direito Constitucional\". "
        "Se for matéria que não está na lista, escreva o nome canônico dela "
        "(\"Direito Tributário\", \"Informática\").\n\n"
        "ASSUNTO é o recorte DENTRO da disciplina, curto, como um título de "
        "aula: \"Remédios constitucionais\", \"Controle de constitucionalidade\", "
        "\"Crimes contra a administração pública\". Um curso inteiro cai na mesma "
        "disciplina — é o assunto que distingue a aula 3 da aula 11.\n\n"
        "Se não der pra saber, devolva string vazia no campo. Não invente."
    )
    try:
        r = llm.obter().gerar_json(texto[:MAX_CHARS_CLASSE], sistema,
                                   max_tokens=200, schema=ESQUEMA_CLASSE)
    except Exception:
        return {}
    limpa = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()[:120]
    return {k: v for k, v in (("disciplina", limpa(r.get("disciplina"))),
                              ("assunto", limpa(r.get("assunto")))) if v}


class ErroMaterial(Exception):
    """Falha que o ALUNO pode resolver — vira 400 na borda HTTP, com o texto
    aparecendo na tela. Falha de infra não passa por aqui."""


def _extrair(nome: str, dados: bytes) -> str:
    """Bytes -> texto. PDF via pypdf; qualquer outra coisa como texto puro."""
    if nome.lower().endswith(".pdf"):
        import io
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(dados))
            # PDF com senha: o pypdf não estoura na abertura, estoura ao ler
            # a página — e a mensagem crua ("file has not been decrypted") não
            # diz ao aluno o que fazer.
            if getattr(reader, "is_encrypted", False):
                raise ErroMaterial("PDF protegido por senha — remova a proteção e suba de novo")
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except ErroMaterial:
            raise
        except Exception as e:
            raise ErroMaterial(f"não consegui abrir este PDF ({type(e).__name__})")
    return dados.decode("utf-8", errors="ignore")


# ----------------------------------------------------------------- por link
MAX_BYTES_URL = 25 * 1024 * 1024
TIMEOUT_URL = 20


def baixar(url: str) -> tuple[str, bytes]:
    """
    Busca o conteúdo de uma URL pública. Devolve (nome, bytes).

    RISCO REAL, MITIGADO E DECLARADO: um servidor que busca URL escolhida pelo
    usuário é SSRF — o pedido sai de DENTRO da rede, então `http://127.0.0.1`,
    `http://10.0.0.5` ou o endpoint de metadados de nuvem
    (`169.254.169.254`, que entrega credencial de instância) ficariam
    alcançáveis por quem só tem uma conta no app.

    A mitigação aqui é resolver o DNS primeiro e recusar qualquer coisa que não
    seja IP público — é isso que fecha o caso, não a inspeção do texto da URL:
    `http://meu-dominio.com` pode apontar para 127.0.0.1, e olhar só a string
    não veria. Por isso a checagem é sobre o IP RESOLVIDO.

    Redirecionamento é seguido MANUALMENTE, um a um, revalidando o IP de cada
    salto: seguir automático deixaria um host público redirecionar pra
    `169.254.169.254` depois da checagem ter passado — o bypass clássico.

    O que isto NÃO é: allowlist de domínio. Allowlist é mais forte e mais
    restritiva; foi pedido poder colar qualquer link. Ficou o mais forte que
    dá sem virar allowlist, e está escrito aqui pra ninguém achar que é
    equivalente.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse
    import httpx

    def checar(u: str) -> None:
        p = urlparse(u)
        if p.scheme not in ("http", "https"):
            raise ErroMaterial("só http e https")
        if not p.hostname:
            raise ErroMaterial("URL sem host")
        try:
            infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80),
                                       proto=socket.IPPROTO_TCP)
        except OSError:
            raise ErroMaterial(f"não consegui resolver {p.hostname}")
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            # `is_global` é o predicado certo e cobre de uma vez loopback,
            # privado, link-local (que é onde vive o metadados de nuvem),
            # reservado e multicast. Testar cada faixa na mão erraria alguma.
            if not ip.is_global:
                raise ErroMaterial(
                    f"{p.hostname} resolve para um endereço interno ({ip}) — "
                    "só endereço público é aceito")

    atual = url.strip()
    with httpx.Client(follow_redirects=False, timeout=TIMEOUT_URL,
                      headers={"user-agent": "FerrarIA/1.0 (+biblioteca do aluno)"}) as c:
        for _ in range(5):
            checar(atual)
            r = c.get(atual)
            if r.is_redirect and r.headers.get("location"):
                atual = str(r.next_request.url) if r.next_request else r.headers["location"]
                continue
            if r.status_code >= 400:
                raise ErroMaterial(f"o site respondeu {r.status_code}")
            if len(r.content) > MAX_BYTES_URL:
                raise ErroMaterial("conteúdo maior que 25 MB")
            tipo_http = r.headers.get("content-type", "")
            if "pdf" in tipo_http or atual.lower().endswith(".pdf"):
                return _nome_da_url(atual, ".pdf"), r.content
            if "html" in tipo_http or "text" in tipo_http or not tipo_http:
                return _nome_da_url(atual, ".txt"), _html_para_texto(r.text).encode()
            raise ErroMaterial(f"não sei ler este conteúdo ({tipo_http or 'sem tipo'})")
    raise ErroMaterial("redirecionamentos demais")


def _nome_da_url(url: str, ext: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    base = (p.path.rstrip("/").rsplit("/", 1)[-1] or p.netloc or "link")
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base)
    return (re.sub(r"[^\w\-.]+", "-", base)[:80] or "link") + ext


def _html_para_texto(html: str) -> str:
    """HTML -> texto legível, sem dependência nova.

    `corpus/html_para_texto.py` existe e é mais cuidadoso, mas é feito pro
    HTML compilado do Planalto (descarta tachado, corta no aviso de rodapé) e
    roda como script sobre arquivo. Aqui o alvo é qualquer página, e o que
    importa é tirar script/style — que viram lixo indexável — e desfazer as
    entidades. Regex basta e não paga uma dependência de parser.
    """
    import html as _html
    limpo = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    limpo = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", limpo)
    limpo = re.sub(r"(?s)<[^>]+>", " ", limpo)
    limpo = _html.unescape(limpo)
    limpo = re.sub(r"[ \t]+", " ", limpo)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", limpo).strip()


def registrar(usuario_id: int, nome: str, dados: bytes,
              disciplina: str | None = None, tipo: str = "aula",
              titulo: str | None = None, assunto: str | None = None) -> dict:
    """
    Grava a LINHA do documento e devolve na hora, com `status='processando'`.

    Separado de `indexar()` de propósito: o request HTTP precisa responder em
    milissegundos, e o embedding leva minutos. Aqui só valida o que dá pra
    validar de graça (tipo, tamanho, duplicata, texto extraível) — porque
    falha que o aluno pode consertar tem que aparecer ANTES de ele fechar a
    aba, não num status vermelho dez minutos depois.
    """
    if tipo not in TIPOS:
        raise ErroMaterial(f"tipo inválido: escolha entre {', '.join(TIPOS)}")
    # Disciplina NÃO é mais obrigatória (020). Vazio significa "descubra você",
    # e o classificador preenche em background. Exigir aqui obrigava a LER o
    # material antes de subir — e o caso que mais importa é justamente o
    # material que a pessoa não conhece.

    digest = hashlib.sha256(dados).hexdigest()
    # Só entre os documentos DESTE aluno (índice parcial da 019): o mesmo
    # arquivo na biblioteca de outra pessoa não é duplicata, é coincidência.
    ja = db.exec1(
        "SELECT id, titulo FROM documento WHERE hash = %(h)s AND usuario_id = %(u)s",
        {"h": digest, "u": usuario_id})
    if ja:
        raise ErroMaterial(f"você já subiu este arquivo (\"{ja['titulo']}\")")

    texto = _extrair(nome, dados)
    if len(texto.strip()) < MIN_CHARS:
        raise ErroMaterial(
            "quase nenhum texto foi extraído — este PDF provavelmente é imagem "
            "escaneada. Rode OCR (ocrmypdf) e suba de novo.")

    chunks = chunking.chunk_generico(texto)
    if not chunks:
        raise ErroMaterial("não consegui dividir este material em trechos")

    doc = db.exec1(
        """INSERT INTO documento (titulo, disciplina, assunto, tipo, origem, hash,
                                  usuario_id, status, chunks_total, classificado_por)
           VALUES (%(t)s, %(d)s, %(as)s, %(tp)s, %(o)s, %(h)s, %(u)s,
                   'processando', %(n)s, %(cp)s)
           RETURNING id, titulo, disciplina, assunto, tipo, status, chunks_total,
                     classificado_por, criado_em""",
        {"t": (titulo or re.sub(r"\.[A-Za-z0-9]{1,5}$", "", nome)).strip()[:200],
         "d": (disciplina or "").strip() or None,
         "as": (assunto or "").strip() or None,
         "tp": tipo, "o": nome, "h": digest, "u": usuario_id, "n": len(chunks),
         # Só marca 'aluno' se ele realmente disse algo. Sem isso, material
         # não classificado apareceria como "você informou" — e a tela usa
         # essa procedência pra decidir se pede conferência.
         "cp": "aluno" if (disciplina or "").strip() else None})
    return {**doc, "chunks": 0}


def indexar(documento_id: int, nome: str, dados: bytes) -> None:
    """
    Calcula os embeddings e grava os chunks. RODA FORA DO REQUEST.

    Conexão ISOLADA (`db.conexao_isolada`): a global é uma só e ficaria presa
    por minutos, com todo request do app na fila atrás de uma indexação.

    Reextrai do bytes em vez de receber os chunks de `registrar`: passar uma
    lista de milhares de dicionários entre request e thread só pra economizar
    um parse de PDF é guardar estado em memória que o banco já sabe reconstruir
    — e é justamente esse estado que se perde quando o processo reinicia.

    Erro aqui NÃO sobe: vira `status='falha'` com a razão em `erro`. Exceção
    numa background task morre sem ninguém ver, e o aluno ficaria com uma
    linha "processando" pra sempre.
    """
    try:
        texto = _extrair(nome, dados)
        chunks = chunking.chunk_generico(texto)
    except Exception as e:  # noqa: BLE001 — ver o comentário do except final
        with db.conexao_isolada() as c, c.cursor() as cur:
            cur.execute("UPDATE documento SET status='falha', erro=%s WHERE id=%s",
                        (str(e)[:500], documento_id))
        return

    try:
        with db.conexao_isolada() as c:
            # IDEMPOTENTE: limpa o que já existe deste documento antes de
            # começar. Sem isso, indexar duas vezes o mesmo material dobra os
            # trechos — e duas vezes acontece de verdade em dois casos: o
            # processo reinicia no meio (a linha fica "processando" pra sempre
            # e alguém manda reindexar) e o retry manual da tela.
            #
            # Troca ACEITA e explícita: paga de novo o embedding dos lotes que
            # já tinham passado. A alternativa — retomar de onde parou —
            # economiza CPU e deixa o material num estado que ninguém sabe
            # descrever (parcial? completo? de qual versão do arquivo?).
            # Repetir trabalho é mais barato que dado ambíguo no acervo.
            with c.cursor() as cur:
                cur.execute("DELETE FROM chunk WHERE documento_id = %s", (documento_id,))
                cur.execute("UPDATE documento SET status='processando', erro=NULL WHERE id=%s",
                            (documento_id,))
            for i in range(0, len(chunks), LOTE):
                lote = chunks[i:i + LOTE]
                vetores = embeddings.embed_passagens([x["texto"] for x in lote])
                with c.cursor() as cur:
                    for j, (x, v) in enumerate(zip(lote, vetores)):
                        cur.execute(
                            """INSERT INTO chunk (documento_id, ordem, texto, norma,
                                                  artigo, paragrafo, inciso, rubrica,
                                                  secao, embedding)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (documento_id, i + j, x["texto"], x["norma"], x["artigo"],
                             x["paragrafo"], x["inciso"], x.get("rubrica"),
                             x.get("secao"), v))
            with c.cursor() as cur:
                cur.execute("UPDATE documento SET status='pronto', erro=NULL WHERE id=%s",
                            (documento_id,))

    except Exception as e:
        with db.conexao_isolada() as c, c.cursor() as cur:
            # Os trechos já gravados FICAM, e o status diz `falha`: material
            # meio indexado ainda responde busca, o que é melhor que nada
            # enquanto o aluno não manda tentar de novo. E o retry começa
            # limpo por causa do DELETE acima, então parcial nunca vira
            # duplicado.
            cur.execute("UPDATE documento SET status='falha', erro=%s WHERE id=%s",
                        (f"falhou ao indexar: {e}"[:500], documento_id))
        return

    # CLASSIFICA DEPOIS, e FORA do try da indexação. A ordem e o lugar são
    # decisões separadas:
    #   · depois, porque o material fica buscável mesmo sem cota de modelo —
    #     indexar não depende de cota, classificar sim;
    #   · FORA do try, porque dentro dele uma falha aqui marcava como `falha`
    #     material 100% indexado. Foi o que aconteceu de verdade: um
    #     IndeterminateDatatype no UPDATE virou "falha na leitura" num arquivo
    #     com todos os trechos gravados. Rótulo é enfeite; índice é o produto.
    try:
        _classificar_se_faltar(documento_id, texto)
    except Exception:
        pass


def _classificar_se_faltar(documento_id: int, texto: str) -> None:
    """Preenche disciplina/assunto quando o aluno não disse.

    NÃO sobrescreve o que ele digitou: quem informou a matéria decidiu, e um
    palpite de modelo passando por cima disso é o sistema discordando de quem
    tem mais contexto. Só completa o que está vazio — e é por campo, porque
    "informei a disciplina, descubra o assunto" é um caso normal.
    """
    with db.conexao_isolada() as c:
        with c.cursor() as cur:
            cur.execute("SELECT disciplina, assunto FROM documento WHERE id=%s",
                        (documento_id,))
            atual = cur.fetchone()
        if not atual or (atual["disciplina"] and atual["assunto"]):
            return
        conhecidas = [r["disciplina"] for r in
                      db.query("SELECT DISTINCT disciplina FROM documento "
                               "WHERE disciplina IS NOT NULL ORDER BY 1")]
        palpite = classificar(texto, conhecidas)
        if not palpite:
            return
        disc = atual["disciplina"] or palpite.get("disciplina")
        assu = atual["assunto"] or palpite.get("assunto")
        with c.cursor() as cur:
            cur.execute(
                """UPDATE documento
                      SET disciplina = %s, assunto = %s,
                          -- 'aluno' se ele informou a disciplina e o modelo só
                          -- completou o assunto: a parte que decide o recorte
                          -- da mesa continua sendo a dele.
                          -- `::text` explícito: sem ele o Postgres não
                          -- consegue inferir o tipo do parâmetro num
                          -- `IS NOT NULL` isolado e estoura
                          -- IndeterminateDatatype. Mesma classe do
                          -- `::bigint[]` que o reingest.py já precisou.
                          classificado_por = CASE WHEN %s::text IS NOT NULL
                                                  THEN 'aluno' ELSE 'modelo' END
                    WHERE id = %s""",
                (disc, assu, atual["disciplina"], documento_id))


def atualizar(usuario_id: int, documento_id: int, disciplina: str | None = None,
              assunto: str | None = None) -> dict | None:
    """O aluno corrige o palpite. Passa a valer como 'aluno' — a lista da tela
    é que vale, mesmo princípio da curadoria de edital."""
    campos, params = [], {"d": documento_id, "u": usuario_id}
    if disciplina is not None:
        campos.append("disciplina = %(disc)s")
        params["disc"] = disciplina.strip()[:120] or None
    if assunto is not None:
        campos.append("assunto = %(assu)s")
        params["assu"] = assunto.strip()[:120] or None
    if not campos:
        return None
    campos.append("classificado_por = 'aluno'")
    return db.exec1(
        f"""UPDATE documento SET {', '.join(campos)}
             WHERE id = %(d)s AND usuario_id = %(u)s
         RETURNING id, titulo, disciplina, assunto, tipo, status, classificado_por""",
        params)


def para_reindexar(usuario_id: int, documento_id: int) -> dict | None:
    """O material do aluno, se for dele — pra tela poder mandar tentar de novo.

    Existe porque não há worker persistente: a indexação roda em background
    NO PROCESSO do servidor, então um restart no meio deixa a linha em
    `processando` pra sempre. Sem um retry, o aluno teria que apagar e subir o
    mesmo PDF de novo — e o `origem` guarda só o NOME do arquivo, não os bytes,
    então quem tem que reenviar o arquivo é ele. Esta função apenas confirma a
    propriedade; os bytes vêm no request."""
    return db.exec1(
        "SELECT id, titulo, origem FROM documento WHERE id=%(d)s AND usuario_id=%(u)s",
        {"d": documento_id, "u": usuario_id})


def listar(usuario_id: int) -> list[dict]:
    """A biblioteca DESTE aluno. O acervo público não entra: ele não é dele,
    não foi subido por ele e ele não pode apagá-lo."""
    return db.query(
        """SELECT d.id, d.titulo, d.disciplina, d.assunto, d.tipo, d.status,
                  d.erro, d.classificado_por, d.chunks_total, d.origem, d.criado_em,
                  count(c.id) AS chunks
             FROM documento d
             LEFT JOIN chunk c ON c.documento_id = d.id
            WHERE d.usuario_id = %(u)s
            GROUP BY d.id
            ORDER BY d.criado_em DESC, d.id DESC""",
        {"u": usuario_id})


def sugestoes(usuario_id: int) -> dict:
    """O que ESTE aluno já usou de rótulo, pra tela oferecer em vez de exigir
    que ele lembre.

    Só da biblioteca dele: sugerir disciplina que outro aluno cadastrou
    vazaria o que os outros estudam, e o acervo público já tem rota própria
    (`GET /disciplinas`).

    `assuntos_por_disciplina` além da lista chapada porque assunto só faz
    sentido DENTRO de uma matéria — oferecer "Remédios constitucionais" a
    quem está subindo Contabilidade é ruído que atrapalha mais que ajuda.
    A lista chapada fica pro caso de ainda não haver disciplina escolhida.
    """
    linhas = db.query(
        """SELECT DISTINCT disciplina, assunto
             FROM documento
            WHERE usuario_id = %(u)s
              AND (disciplina IS NOT NULL OR assunto IS NOT NULL)""",
        {"u": usuario_id})
    disciplinas, assuntos, por_disc = set(), set(), {}
    for l in linhas:
        d, a = l["disciplina"], l["assunto"]
        if d:
            disciplinas.add(d)
        if a:
            assuntos.add(a)
            if d:
                por_disc.setdefault(d, set()).add(a)
    return {
        "disciplinas": sorted(disciplinas),
        "assuntos": sorted(assuntos),
        "assuntos_por_disciplina": {k: sorted(v) for k, v in sorted(por_disc.items())},
    }


def apagar(usuario_id: int, documento_id: int) -> bool:
    """Só o dono apaga, e o `usuario_id` no WHERE é o que garante isso — sem
    ele, um id chutado apagaria material de outra pessoa (ou uma lei do
    acervo, que não tem dono). Devolve False pra "não é seu ou não existe":
    mesma escolha de `mesa.obter`, que dá 404 e não 403 pra não confirmar a
    quem chuta um id que ele existe. Os chunks vão pelo CASCADE."""
    r = db.query("DELETE FROM documento WHERE id = %(d)s AND usuario_id = %(u)s RETURNING id",
                 {"d": documento_id, "u": usuario_id})
    return bool(r)
