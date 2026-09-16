"""
Biblioteca do aluno — material PRIVADO (apostila, resumo, jurisprudência)
indexado no mesmo acervo da lei, mas visível só para quem subiu.

Por que existe separado de `ingest.py`: a CLI é um script de operador, com
`print` e `sys.exit`, e ingere lei no acervo COMPARTILHADO. O que a tela
/materiais recebe é outra coisa — arquivo de UM aluno, subido por HTTP, que
precisa de dono, de estado de processamento e de nunca derrubar o request.
A parte comum de verdade (extrair -> chunk -> embed -> gravar) é curta; o
que difere é tudo em volta.

DECISÃO CENTRAL: material do aluno NUNCA entra como `tipo='lei'`. Isso
continua valendo — o tipo é sempre o que ele escolheu (aula, resumo,
jurisprudência), e a norma fica NULA, porque nome de norma é do acervo
público (`ingest.py --norma CF`).

O QUE MUDOU, e por um caso relatado: o CHUNKER passou a depender do texto.
A regra anterior mandava tudo pra `chunk_generico`, e o medo era legítimo —
apostila comentada cita "art. 312" no meio de um parágrafo do professor, e
virar chunk com `artigo='312'` faria `por_dispositivo` devolver o comentário
em vez da lei.

Só que o dono colou o link da Constituição e depois subiu o .htm dela, e as
duas viraram ~2100 janelas genéricas com `artigo` NULO. O efeito, medido:
não dava pra achar por dispositivo, não dava pra gerar questão (o gerador
exige `artigo IS NOT NULL`), a citação saía "constituicao, p. 14" em vez de
"CF, art. 37", e — o pior — esses 2100 trechos COMPETIAM na busca com a CF
do acervo, que já estava lá dividida por artigo.

`_e_lei_seca` separa os dois casos pelo que os distingue de fato: lei
publicada abre linha com "Art. N" (584 vezes na CF); apostila cita no meio da
frase. Com teto folgado de 40 ocorrências EM INÍCIO DE LINHA, apostila que
cita dezenas de artigos continua indo por janela. E o medo original segue
coberto duas vezes: a norma nula e o `ORDER BY d.tipo = 'lei' DESC` de
`por_dispositivo` mantêm a lei oficial na frente da cópia do aluno.
"""
import hashlib
import queue
import threading
import time
import re

from . import chunking, db, embeddings

VERSAO = "material-v24"

LOTE = 32
MIN_CHARS = 200

# Sem 'lei' e sem 'historico', e a ausência é a decisão acima: os dois
# prometem coisa que material privado não pode cumprir (citação exata de
# dispositivo). Sobra o que a tela realmente oferece.
TIPOS = ("aula", "resumo", "jurisprudencia")

# MATERIAL DE REFERÊNCIA × MATERIAL DE ESTUDO, e a diferença tem consequência.
#
# `aula` e `resumo` são uma coisa só: uma aula fala de traumatologia forense,
# um resumo fala de lesão corporal. `assunto` é o título dessa coisa, e é o que
# faz a busca achar a aula 12 quando o aluno pergunta de asfixiologia (020/025).
#
# `jurisprudencia` não é uma coisa só — é um poço de decisões que serve de
# apoio a várias matérias. Um corpus de lei também não: a CF trata de centenas
# de assuntos.
#
# RELATO QUE DEU ORIGEM A ISTO: o aluno indexou a CF pelo link do Planalto como
# jurisprudência, e o classificador — que lê só o COMEÇO do material — rotulou
# os 1074 trechos com "Princípios fundamentais e direitos e garantias
# fundamentais", que é o que está nas primeiras páginas. As palavras dele: "se
# fôssemos criar assunto da CF, iríamos ter que criar uma quantidade
# imensurável de assuntos".
#
# NÃO É COSMÉTICO — MEDIDO. O rótulo entra no tsvector (025), então esse
# assunto falso casava lexicalmente com QUALQUER consulta constitucional, em
# todos os 1074 trechos. Resultado antes do conserto:
#
#   "princípios fundamentais do direito administrativo"
#      -> a cópia levava 6 de 6, devolvendo art. 88, art. 234, art. 18
#   "direitos e garantias fundamentais: remédios constitucionais"
#      -> art. 196 (saúde), art. 157, art. 55, art. 83
#
# Relevância decidida por ruído. E este é o mecanismo do defeito antigo "as
# duas cópias da CF do aluno passam na frente da CF oficial": não era ser
# cópia, era o rótulo mentiroso repetido mil vezes.
#
# Material de lei seca não perde nada sem o assunto: cada trecho já tem
# `artigo` e `rubrica`, que são rótulos PRECISOS por trecho — melhores que um
# assunto único, não piores.
TIPOS_DE_REFERENCIA = ("jurisprudencia",)


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


def e_referencia(tipo: str | None, chunks: list[dict] | None = None) -> bool:
    """Este material é poço de consulta, não aula? Ver `TIPOS_DE_REFERENCIA`.

    Duas evidências, qualquer uma basta: o TIPO que o aluno escolheu, e o
    material ter sido fatiado por artigo (`_dividir` -> `chunk_lei`), que é
    corpus de norma inteira independentemente do que ele marcou no seletor."""
    if (tipo or "") in TIPOS_DE_REFERENCIA:
        return True
    return bool(chunks) and any(c.get("artigo") for c in chunks)


def classificar(texto: str, disciplinas_conhecidas: list[str] | None = None,
                com_assunto: bool = True, nome_arquivo: str | None = None) -> dict:
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

    `nome_arquivo` é a ORIGEM (o nome com que o material subiu) e entra como
    evidência, não como verdade. Quem escreve "Direito Administrativo -
    Princípios do Direito Administrativo.pdf" leu o material e já disse do que
    ele trata; o classificador lia só `texto[:MAX_CHARS_CLASSE]` e, num PDF que
    abre pela capa do primeiro vídeo, chamava de "Regime jurídico
    administrativo" uma aula que é de princípios — o mesmo erro de escopo da CF
    virando "Princípios fundamentais" (027), o começo mentindo sobre o todo.
    Nome inútil existe e é comum (`curso-392722-aula-10-9415-completo`), e nome
    ERRADO também — o dono renomeou uma aula de direitos sociais para "Direitos
    Humanos - princípios internacionais" e subiu. Por isso a ordem no prompt é
    de PRECEDÊNCIA e não de peso: o nome vale quando concorda com o texto ou
    quando o texto não decide; contradizendo o texto, ele é descartado. Pista
    que sobrepuja a prova é pior que pista nenhuma, porque o rótulo errado vira
    `chunk.rotulo` e entra no tsvector (025).

    Falha do modelo devolve `{}`, não estoura: material sem rótulo continua
    indexado e buscável, só aparece como "não identificado" na tela. Perder o
    material inteiro porque a cota acabou seria trocar um defeito pequeno por
    um grande.
    """
    from . import llm
    conhecidas = ", ".join(disciplinas_conhecidas or []) or "(nenhuma ainda)"
    # Uma linha, sem extensão e curto: o nome é texto do aluno indo pro prompt,
    # e nome de 200 caracteres com quebra de linha viraria instrução parecendo
    # dado. O que sobra é rótulo, que é tudo que se quer dele.
    nome = re.sub(r"\s+", " ",
                  re.sub(r"\.[A-Za-z0-9]{1,5}$", "", str(nome_arquivo or ""))).strip()[:160]
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
        + ("ASSUNTO é o recorte DENTRO da disciplina, curto, como um título de "
           "aula: \"Remédios constitucionais\", \"Controle de constitucionalidade\", "
           "\"Crimes contra a administração pública\". Um curso inteiro cai na mesma "
           "disciplina — é o assunto que distingue a aula 3 da aula 11.\n\n"
           if com_assunto else
           # SEM pedir assunto: material de referência não tem um, e pedir a um
           # modelo que leu só o começo produz uma resposta plausível e falsa —
           # foi assim que a CF inteira virou "Princípios fundamentais". Campo
           # que não deve existir não se pede e se descarta: não se pede.
           "NÃO devolva assunto: este material é um poço de consulta (norma "
           "inteira, jurisprudência) e não trata de um assunto só.\n\n")
        + (("Você recebe TAMBÉM o NOME ORIGINAL DO ARQUIVO. Ele é PISTA; o "
            "TEXTO é a PROVA, e o texto SEMPRE ganha.\n"
            "· Nome descritivo que CONCORDA com o texto (\"Direito "
            "Administrativo - Princípios.pdf\" sobre uma aula de princípios): "
            "use como indicador d" + ("a disciplina e do assunto"
                                      if com_assunto else "a disciplina") +
            ", porque quem nomeou assim leu o material inteiro.\n"
            # O EXEMPLO É INVENTADO DE PROPÓSITO, e não o caso que motivou a
            # regra ("Direitos Humanos" num PDF de direitos sociais): exemplo
            # formatado vale mais que regra em prosa — está medido na 3b — e
            # colocar o caso real aqui seria entregar a resposta dele ao modelo
            # e perder a única prova de que a regra funciona sozinha.
            "· Nome que CONTRADIZ o texto: está ERRADO e se IGNORA. Arquivo "
            "chamado \"Direito Penal - crimes contra a fé pública\" cujo "
            "conteúdo trata de licitações e contratos é aula de LICITAÇÕES, e é "
            "LICITAÇÕES que você devolve — nunca repita um nome que o texto "
            "desmente.\n"
            "· Nome genérico ou inútil (\"scan_001.pdf\", \"aula_04.pdf\", "
            "\"curso-392722-aula-10-9415-completo\"): IGNORADO por completo.\n"
            "Em qualquer caso, devolva o rótulo no seu formato canônico — não "
            "copie o nome do arquivo literalmente.\n\n") if nome else "")
        + "Se não der pra saber, devolva string vazia no campo. Não invente."
    )
    # O nome vai ROTULADO e antes do trecho: sem o rótulo o modelo lê o nome
    # como primeira linha do conteúdo, que é exatamente o que ele não é.
    corpo = texto[:MAX_CHARS_CLASSE]
    if nome:
        corpo = f"NOME DO ARQUIVO: {nome}\n\nTRECHO DO CONTEÚDO:\n{corpo}"
    try:
        r = llm.obter().gerar_json(corpo, sistema,
                                   max_tokens=200, schema=ESQUEMA_CLASSE)
    except Exception:
        return {}
    limpa = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()[:120]
    # O descarte do assunto fica AQUI e não só no prompt: o modelo devolve o
    # campo mesmo mandado não devolver, e é este projeto decidindo no código o
    # que o prompt não garante.
    pares = (("disciplina", limpa(r.get("disciplina"))),
             ("assunto", limpa(r.get("assunto")) if com_assunto else ""))
    return {k: v for k, v in pares if v}


class ErroMaterial(Exception):
    """Falha que o ALUNO pode resolver — vira 400 na borda HTTP, com o texto
    aparecendo na tela. Falha de infra não passa por aqui."""


# Postgres recusa `\x00` em coluna TEXT ("text fields cannot contain NUL"), e
# extração de PDF real produz isso: aconteceu com uma aula de curso (a que traz
# marca d'água por página). Os outros controles C0 não quebram o INSERT, mas
# entram no `texto` que vira embedding e prompt — lixo invisível que ninguém
# consegue depurar olhando a tela. Tab, \n e \r ficam: são estrutura do texto.
_LIXO = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)}
_LIXO[0x7F] = None


def _limpar(texto: str) -> str:
    """Tira o que o banco recusa e o que não é texto.

    Na EXTRAÇÃO, e não na hora de gravar, porque o texto tem três destinos
    (documento, chunk, classificador) e limpar em cada um deles é a receita
    para o dia em que um caminho novo esquecer."""
    return texto.translate(_LIXO)


def _extrair(nome: str, dados: bytes) -> str:
    """Bytes -> texto. PDF via pypdf; qualquer outra coisa como texto puro."""
    baixo = nome.lower()
    if baixo.endswith((".htm", ".html", ".xhtml")):
        # HTML por LINK já era tratado em `baixar` (pelo content-type); por
        # ARQUIVO caía no `decode` genérico, ou seja, indexava as tags. Quem
        # salva a página do Planalto e arrasta o .htm é o caso mais provável de
        # todos neste projeto.
        #
        # cp1252 antes de utf-8 como reserva: o HTML compilado do Planalto é
        # cp1252 (é o que `corpus/html_para_texto.py` já documenta), e decodificar
        # como utf-8 com `errors="ignore"` come os acentos em silêncio — texto
        # sem acento casa pior na busca e fica ilegível na citação.
        return _limpar(_html_para_texto(_decodificar(dados)))
    if baixo.endswith(".pdf"):
        import io
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(dados))
            # PDF com senha: o pypdf não estoura na abertura, estoura ao ler
            # a página — e a mensagem crua ("file has not been decrypted") não
            # diz ao aluno o que fazer.
            if getattr(reader, "is_encrypted", False):
                raise ErroMaterial("PDF protegido por senha — remova a proteção e suba de novo")
            return _limpar("\n\n".join((p.extract_text() or "") for p in reader.pages))
        except ErroMaterial:
            raise
        except Exception as e:
            raise ErroMaterial(f"não consegui abrir este PDF ({type(e).__name__})")
    return _limpar(dados.decode("utf-8", errors="ignore"))


# ----------------------------------------------------------------- por link
MAX_BYTES_URL = 25 * 1024 * 1024

# Teto do upload direto. Mais generoso que o de link porque aqui o arquivo já
# está na máquina de quem sobe (não há download pra travar), e apostila de
# cursinho digitalizada passa fácil de 25 MB. Existe pra impedir o caso
# patológico, não pra policiar tamanho normal.
MAX_BYTES_ARQUIVO = 60 * 1024 * 1024
TIMEOUT_URL = 20

# USER-AGENT DE NAVEGADOR, e não é firula: o Planalto — a fonte mais óbvia de
# lei seca deste projeto — DERRUBA a conexão de cliente sem `User-Agent`.
# Medido no mesmo minuto: sem cabeçalho, `ReadTimeout`; com este, HTTP 200 e
# 1,8 MB de HTML. O erro que o aluno via era "Não deu pra indexar este link"
# pra uma URL perfeitamente válida.
#
# httpx não manda UA por padrão (manda `python-httpx/x.y`), e vários servidores
# de governo tratam isso como robô. Identificar-se como navegador aqui é o que
# faz a função cumprir o que ela promete: buscar uma página pública.
CABECALHOS_URL = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


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
    # O UA honesto ("FerrarIA/1.0") era o certo por educação e o errado na
    # prática: o Planalto DERRUBA a conexão de quem não parece navegador, e é a
    # fonte mais óbvia de lei seca deste projeto. Medido no mesmo minuto — sem
    # UA de navegador, ReadTimeout; com, HTTP 200 e 1,8 MB. O aluno via "Não deu
    # pra indexar este link" numa URL perfeitamente válida.
    with httpx.Client(follow_redirects=False, timeout=TIMEOUT_URL,
                      headers=CABECALHOS_URL) as c:
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
                # DECODIFICA À MÃO em vez de confiar em `r.text`. O HTML
                # compilado do Planalto é cp1252 e o cabeçalho não diz — o
                # httpx chutava utf-8 e o resultado vinha "Constitui��o", com
                # 1170 artigos ilegíveis. Acento quebrado não é cosmético aqui:
                # some da busca lexical e aparece na citação que o aluno lê.
                #
                # Mesma ordem de `_extrair`, e por isso mesmo: utf-8 primeiro
                # (é o que a web moderna usa), cp1252 como reserva.
                return _nome_da_url(atual, ".txt"), _html_para_texto(
                    _decodificar(r.content)).encode()
            raise ErroMaterial(f"não sei ler este conteúdo ({tipo_http or 'sem tipo'})")
    raise ErroMaterial("redirecionamentos demais")


def _nome_da_url(url: str, ext: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    base = (p.path.rstrip("/").rsplit("/", 1)[-1] or p.netloc or "link")
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base)
    return (re.sub(r"[^\w\-.]+", "-", base)[:80] or "link") + ext


def _decodificar(dados: bytes) -> str:
    """Bytes -> str, com a ordem que este projeto precisa.

    utf-8 primeiro porque é o que a web moderna usa; cp1252 como reserva
    porque é o que o Planalto serve, e é de lá que vem quase toda lei seca
    daqui. `errors="ignore"` só no último recurso — comer acento em silêncio é
    pior que falhar, e por isso não é a primeira tentativa."""
    for codec in ("utf-8", "cp1252", "latin-1"):
        try:
            return dados.decode(codec)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", errors="ignore")


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


# Quantos "Art. N" seguidos fazem um texto ser LEI SECA e não apostila.
#
# 40 é folgado de propósito: apostila cita artigo o tempo todo (a de
# Criminalística cita dezenas), e tratar apostila como lei seca seria pior que o
# contrário — o chunker de lei parte o texto por artigo e jogaria fora a
# explicação do professor entre um e outro.
MIN_ARTIGOS_LEI = 40
RE_ARTIGO_LEI = re.compile(r"(?im)^\s*Art(?:igo)?\.?\s*\d")

# MARCAS DE APOSTILA: o que existe em material de curso e NÃO existe em lei
# publicada. Contar artigo não bastou — uma aula de Direitos Sociais que
# transcreve os arts. 6º a 11 da CF passa dos 40 com folga (medido: 57), e a
# aula de Processo Legislativo também (55). As duas foram fatiadas por artigo,
# perderam a explicação do professor entre um dispositivo e outro e viraram
# "material de consulta" — sem assunto, pela 027.
#
# Duas famílias independentes, qualquer uma bastando, porque erro de OCR ou
# apostila sem nome de banca não pode desarmar as duas ao mesmo tempo:
RE_BANCA_APOSTILA = re.compile(
    r"(?i)\b(cebraspe|cespe|fgv|fcc|vunesp|quadrix|ibfc|instituto aocp)\b")
RE_MARCA_APOSTILA = re.compile(
    r"(?im)^\s*(?:aula\s*\d|questões\s+comentadas|lista\s+de\s+questões|"
    r"gabarito|prof(?:\.|essor)|índice|sumário)")

# Os cortes saem da MEDIÇÃO abaixo, com a margem que ela mostrou — não de
# palpite. Lei de verdade (cf, cp, cpp, 8.112, ADCT, e os três .html compilados
# do Planalto) vs. o que o aluno subiu de fato:
#
#   arquivo                       artigos  banca  marcas
#   cf.txt                            292      0       4
#   cp.txt                            437      0       0
#   cpp.txt                           899      0       1
#   lei8112.txt                       253      0       1
#   adct.txt                          174      0       0
#   Constituicao-Compilado.html       466      0       0
#   Del3689Compilado.html             898      0       0
#   L8112consol.html                  362      0       1
#   ---------------------------------------------------
#   aula 10 (doc 738)                  55     82     155
#   Direitos Sociais (doc 789)         57     38      87
#   Edital PC-PR 2026                  72     99       9
#   aula 00 (doc 344)                  26     56     100
#
# Nenhuma lei cita banca (0 em oito arquivos) e nenhuma passa de 7 marcas;
# nenhuma apostila fica abaixo de 37 bancas. O EDITAL entrou junto e é caso
# novo: 72 "Art." em começo de linha faziam dele lei seca também.
MIN_BANCA_APOSTILA = 3
MIN_MARCA_APOSTILA = 20


def _e_apostila(texto: str) -> bool:
    """Tem cara de material de CURSO — aula, resumo, edital, caderno de questões?

    Serve de VETO ao `_e_lei_seca`, não de classificador: quem responde "não"
    aqui não está dizendo que o texto é lei, só que não há prova de que seja
    apostila. Por isso os dois cortes são altos — o custo de vetar por engano
    (a lei do aluno fica em janela genérica, como era antes da 019) é menor que
    o de fatiar uma apostila por artigo, que joga fora a aula inteira.
    """
    return (len(RE_BANCA_APOSTILA.findall(texto)) >= MIN_BANCA_APOSTILA
            or len(RE_MARCA_APOSTILA.findall(texto)) >= MIN_MARCA_APOSTILA)


def _e_lei_seca(texto: str) -> bool:
    """O material é o TEXTO DE UMA LEI, e não uma aula sobre ela?

    Existe por um caso relatado: o dono colou o link da Constituição e depois
    subiu o .htm dela, e as duas viraram ~2100 trechos de janela genérica com
    `artigo` NULO. Consequências, todas medidas:
    · não dá pra achar por dispositivo ("art. 37" não casa nada),
    · não dá pra gerar questão (o gerador exige `artigo IS NOT NULL`),
    · a citação sai como "constituicao, p. 14" em vez de "CF, art. 37",
    · e — o pior — esses 2100 trechos COMPETEM na busca com a CF do acervo
      público, que já estava lá corretamente dividida por artigo.

    Conta artigo em INÍCIO DE LINHA, que é como lei publicada se apresenta.
    Citação no meio do texto ("previsto no art. 37") não conta, e é justamente
    o que apostila faz.

    SÓ CONTAR NÃO BASTOU. Apostila boa transcreve o dispositivo antes de
    explicá-lo, em início de linha e em bloco — a aula de Direitos Sociais traz
    os arts. 6º a 11 da CF inteiros e bateu 57. O que separa não é quantidade de
    artigo, é a companhia: `_e_apostila` veta pelo que só existe em material de
    curso. A ordem importa e é barata — a contagem roda primeiro e derruba a
    maioria dos textos sem olhar as marcas."""
    if len(RE_ARTIGO_LEI.findall(texto)) < MIN_ARTIGOS_LEI:
        return False
    return not _e_apostila(texto)


# Quantos artigos amostrados precisam bater pra dizer "isto já está no acervo".
# 0.6 e 25 amostras: sobra folga pra versão mais nova (emendas mudam artigos) e
# não confunde apostila que TRANSCREVE alguns artigos com a lei inteira.
LIMIAR_DUPLICATA = 0.6
AMOSTRA_DUPLICATA = 25


def descricao_da_norma_publica(norma: str) -> str:
    """"CF (276 artigos, já vem com o app)" — o que a recusa de duplicata
    precisa dizer pra não ser lida como acusação a um arquivo do aluno.

    POR QUE ISTO EXISTE. A recusa dizia "esta lei já está no acervo do app
    (CF)", e "acervo do app" foi lido como "a minha biblioteca". O aluno tinha
    apagado a cópia dele e ficou procurando o arquivo culpado: "o problema
    continua e ainda não mostra qual arquivo tá com o link". Não havia arquivo
    dele — o que existe é a CF OFICIAL, que o app já traz ingerida por artigo,
    e da qual não há nada pra apagar.

    Mensagem que aponta um conflito sem dizer com QUEM manda a pessoa procurar
    o culpado na lista errada."""
    r = db.exec1(
        """SELECT d.titulo, count(*) AS arts
             FROM documento d JOIN chunk c ON c.documento_id = d.id
            WHERE d.usuario_id IS NULL AND c.norma = %(n)s AND c.artigo IS NOT NULL
            GROUP BY d.titulo ORDER BY count(*) DESC LIMIT 1""",
        {"n": norma})
    if not r:
        return norma
    return f"{norma} — {r['arts']} artigos, já ingerida pelo próprio app"


def norma_ja_no_acervo(chunks: list[dict]) -> str | None:
    """A lei que o aluno subiu já existe no acervo PÚBLICO? Devolve a norma.

    POR QUE ISTO É NECESSÁRIO, e a medição que obrigou: o dono colou o link da
    Constituição e depois subiu o .htm dela. Cada cópia virou 543 chunks por
    artigo, e as duas passaram a COMPETIR com a CF oficial — a busca por
    "princípios da administração pública", que antes trazia `cf, art. 37` na
    posição 3, passou a trazer `constituicao.txt, art. 88`, `art. 39`,
    `art. 234`. Mil e oitenta e seis cópias afogando o original.
    
    O `avaliar_retrieval.py` NÃO pega isso, e é importante saber: ele mede
    contra o acervo compartilhado, sem `usuario_id`, então a biblioteca do aluno
    é invisível pra ele. Ficou 21/32 antes e depois. A degradação era só do
    aluno — o pior tipo, porque nenhuma medida do projeto a mostra.
    
    Compara por (artigo, começo do texto) numa amostra: emenda muda a redação de
    alguns artigos, então exigir igualdade total recusaria a versão nova de uma
    lei que valeria a pena ter. `LIMIAR_DUPLICATA` de 60% em 25 amostras dá essa
    folga sem confundir apostila que transcreve uns poucos artigos."""
    amostra = [c for c in chunks if c.get("artigo")][:AMOSTRA_DUPLICATA]
    if len(amostra) < 10:
        return None
    achados: dict[str, int] = {}
    for c in amostra:
        prefixo = " ".join((c.get("texto") or "").split())[:60]
        if len(prefixo) < 30:
            continue
        for r in db.query(
            """SELECT c.norma FROM chunk c JOIN documento d ON d.id = c.documento_id
                WHERE d.usuario_id IS NULL AND c.norma IS NOT NULL
                  AND c.artigo = %(a)s
                  AND regexp_replace(c.texto, '\s+', ' ', 'g') LIKE %(p)s""",
            {"a": c["artigo"], "p": f"%{prefixo}%"},
        ):
            achados[r["norma"]] = achados.get(r["norma"], 0) + 1
    if not achados:
        return None
    norma, batidas = max(achados.items(), key=lambda x: x[1])
    return norma if batidas / len(amostra) >= LIMIAR_DUPLICATA else None


def _dividir(texto: str, nome: str) -> list[dict]:
    """Divide pelo chunker CERTO pro tipo de texto.

    Lei seca pelo `chunk_lei` (um chunk por artigo, com `artigo` preenchido —
    é o que dá proveniência, citação exata e geração de questão); o resto por
    janela. A norma fica `None`: o nome dela é do acervo público
    (`ingest.py --norma CF`), e inventar uma aqui faria a busca por dispositivo
    misturar a cópia do aluno com a oficial."""
    if _e_lei_seca(texto):
        chunks = chunking.chunk_lei(chunking.normalizar_lei(texto), norma=None)
        if chunks:
            return chunks
    return chunking.chunk_generico(texto)


def registrar(usuario_id: int, nome: str, dados: bytes,
              disciplina: str | None = None, tipo: str = "aula",
              titulo: str | None = None, assunto: str | None = None,
              mesa_id: int | None = None, url: str | None = None) -> dict:
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
    # TETO NO UPLOAD DIRETO. Só o caminho por LINK tinha (`MAX_BYTES_URL`), e o
    # arrastar-e-soltar não tinha nenhum: um PDF de 200 MB era extraído inteiro
    # em memória e agora, com a 024, gravado inteiro no banco. Falhar aqui é
    # falhar barato — antes de extrair, antes de gravar, com a razão na tela.
    if len(dados) > MAX_BYTES_ARQUIVO:
        mb = MAX_BYTES_ARQUIVO // 1024 // 1024
        raise ErroMaterial(
            f"arquivo de {len(dados) // 1024 // 1024} MB — o teto é {mb} MB. "
            f"Divida a apostila em partes, ou suba só os capítulos que você vai estudar.")
    # Disciplina NÃO é mais obrigatória (020). Vazio significa "descubra você",
    # e o classificador preenche em background. Exigir aqui obrigava a LER o
    # material antes de subir — e o caso que mais importa é justamente o
    # material que a pessoa não conhece.

    digest = hashlib.sha256(dados).hexdigest()
    # Só entre os documentos DESTE aluno (índice parcial da 019): o mesmo
    # arquivo na biblioteca de outra pessoa não é duplicata, é coincidência.
    ja = db.exec1(
        """SELECT id, titulo, disciplina, assunto, tipo, status, chunks_total,
                  classificado_por, mesa_id, criado_em,
                  (arquivo IS NOT NULL) AS tem_arquivo,
                  (SELECT count(*) FROM chunk WHERE documento_id = documento.id) AS chunks
             FROM documento WHERE hash = %(h)s AND usuario_id = %(u)s""",
        {"h": digest, "u": usuario_id})
    if ja:
        # DUPLICATA PARADA NÃO É DUPLICATA — é serviço inacabado, e recusá-la
        # foi relatado do jeito mais claro possível: depois de o servidor cair
        # no meio do lote, o dono subiu os 18 de novo e recebeu "você já subiu
        # este arquivo" DEZOITO vezes, enquanto as linhas estavam no banco sem
        # um único trecho indexado. A reação certa dele era terminar o serviço;
        # a resposta do sistema tratava isso como erro dele.
        #
        # `pronto` COM trecho continua sendo recusado, e tem de continuar: aí a
        # duplicata é real e reindexar seria pagar CPU de novo pelo mesmo
        # material. Com UMA exceção, logo abaixo: se faltarem os bytes do
        # arquivo, o reenvio serve pra guardá-los — e aí não se reindexa nada. O que muda é `processando` e `falha` (ou zero chunks):
        # volta pra fila e devolve a linha que já existe, como se fosse um
        # upload novo — do ponto de vista de quem arrastou o arquivo, foi.
        parado = ja["status"] != "pronto" or (ja["chunks"] or 0) == 0
        if not parado:
            # PRONTO, MAS SEM OS BYTES: subir de novo ANEXA o arquivo original.
            #
            # Quem cai aqui é material de antes da 024, quando o upload extraía
            # o texto e DESCARTAVA o PDF. A indexação dele está inteira e certa
            # — o que falta é só o original, e sem ele a biblioteca esconde o
            # "abrir" e o "baixar" (`tem_arquivo` falso). Até aqui não havia
            # porta nenhuma: reenviar dava "você já subiu este arquivo", e a
            # única saída era APAGAR o material e reindexar do zero. Trocar os
            # trechos pelo PDF é um preço que ninguém aceitaria pagar sabendo.
            #
            # E NÃO REINDEXA — é essa a diferença pro retomado logo abaixo. Lá
            # falta o trabalho; aqui falta o arquivo. Grava os bytes, deixa o
            # `status` como está e devolve a linha; nada vai pra fila (ver
            # `deve_indexar`, que é onde as rotas de upload perguntam isso).
            #
            # `AND arquivo IS NULL` no UPDATE: se dois uploads do mesmo arquivo
            # chegarem juntos, o segundo vira no-op em vez de reescrever bytes
            # idênticos — o hash é o mesmo, então o conteúdo também é.
            if not ja["tem_arquivo"]:
                db.query("""UPDATE documento SET arquivo = %(b)s, arquivo_tipo = %(t)s,
                                   arquivo_bytes = %(n)s
                             WHERE id = %(i)s AND arquivo IS NULL""",
                         {"i": ja["id"], "b": dados, "t": _tipo_mime(nome), "n": len(dados)})
                volta = {k: v for k, v in ja.items() if k != "tem_arquivo"}
                return {**volta, "tem_arquivo": True, "arquivo_bytes": len(dados),
                        "arquivo_anexado": True}
            raise ErroMaterial(f"você já subiu este arquivo (\"{ja['titulo']}\")")
        db.query("""UPDATE documento SET status = 'processando', erro = NULL,
                           arquivo = COALESCE(arquivo, %(b)s),
                           arquivo_tipo = COALESCE(arquivo_tipo, %(t)s),
                           arquivo_bytes = COALESCE(arquivo_bytes, %(n)s)
                     WHERE id = %(i)s""",
                 {"i": ja["id"], "b": dados, "t": _tipo_mime(nome), "n": len(dados)})
        enfileirar(ja["id"])
        volta = {k: v for k, v in ja.items() if k not in ("chunks", "tem_arquivo")}
        return {**volta, "status": "processando", "chunks": 0, "retomado": True}

    texto = _extrair(nome, dados)
    if len(texto.strip()) < MIN_CHARS:
        raise ErroMaterial(
            "quase nenhum texto foi extraído — este PDF provavelmente é imagem "
            "escaneada. Rode OCR (ocrmypdf) e suba de novo.")

    chunks = _dividir(texto, nome)
    if not chunks:
        raise ErroMaterial("não consegui dividir este material em trechos")

    # RECUSA CÓPIA DO QUE JÁ ESTÁ NO ACERVO, e recusar é o certo aqui: aceitar
    # não acrescenta nada e ATIVAMENTE piora a busca do aluno, porque as cópias
    # competem com o original. Medido — ver `norma_ja_no_acervo`.
    ja_tem = norma_ja_no_acervo(chunks)
    if ja_tem:
        # TEMPO VERBAL: "passariam a competir", não "competem". A redação
        # anterior estava no presente, e foi lida como estado atual — o aluno
        # tinha ACABADO de apagar a cópia dele, colou o link de novo pra
        # conferir, leu "as duas versões competem" e entendeu que havia sobrado
        # rastro. Não havia. Recusa fala do que ACONTECERIA; dizê-la no
        # presente afirma um fato sobre o acervo que ela não verificou.
        raise ErroMaterial(
            f"não subi, e não é nada que você tenha na biblioteca: esta lei JÁ VEM COM O APP "
            f"({descricao_da_norma_publica(ja_tem)}), e o tutor a usa direto — não há arquivo "
            f"seu envolvido nem nada pra apagar. Uma segunda cópia não acrescentaria nada e "
            f"pioraria a sua busca, porque as duas versões passariam a competir; então nada "
            f"foi gravado e a sua biblioteca continua como estava. Pergunte \"art. 37\" ao "
            f"tutor pra ver. O que vale subir é o que o app NÃO tem: aula, resumo e apostila.")

    # O ARQUIVO VAI PARA O BANCO (024). Antes daqui o `dados` era usado pra
    # extrair texto e descartado, e o PDF ficava só no computador de quem subiu
    # — reler a apostila exigia achar o arquivo de novo, e trocar de máquina
    # perdia tudo. Guardar é o que permite o download da biblioteca.
    #
    # Gravado no MESMO INSERT, não num UPDATE depois: um segundo passo poderia
    # falhar entre os dois e deixar a linha existindo sem arquivo, que é
    # exatamente o estado indistinguível de "material antigo, de antes da 024".
    doc = db.exec1(
        """INSERT INTO documento (titulo, disciplina, assunto, tipo, origem, hash,
                                  usuario_id, mesa_id, status, chunks_total,
                                  classificado_por, arquivo, arquivo_tipo,
                                  arquivo_bytes, url)
           VALUES (%(t)s, %(d)s, %(as)s, %(tp)s, %(o)s, %(h)s, %(u)s, %(mid)s,
                   'processando', %(n)s, %(cp)s, %(arq)s, %(arqt)s, %(arqn)s,
                   %(url)s)
           RETURNING id, titulo, disciplina, assunto, tipo, status, chunks_total,
                     classificado_por, mesa_id, criado_em, url""",
        {"t": (titulo or re.sub(r"\.[A-Za-z0-9]{1,5}$", "", nome)).strip()[:200],
         "d": (disciplina or "").strip() or None,
         "as": (assunto or "").strip() or None,
         "tp": tipo, "o": nome, "h": digest, "u": usuario_id, "n": len(chunks),
         # DE ONDE VEIO (028). Só o caminho por link preenche; arquivo
         # arrastado fica NULL, e é a diferença que a tela precisa mostrar —
         # "constituicao.txt" não diz que veio do Planalto.
         "url": (url or "").strip()[:2000] or None,
         # Mesa de ORIGEM (021). `None` grava no pool comum, que é o que a CLI e
         # qualquer chamador sem contexto de mesa devem fazer — inventar uma mesa
         # aqui prenderia o material num concurso que ninguém escolheu.
         "mid": mesa_id,
         # Só marca 'aluno' se ele realmente disse algo. Sem isso, material
         # não classificado apareceria como "você informou" — e a tela usa
         # essa procedência pra decidir se pede conferência.
         "cp": "aluno" if (disciplina or "").strip() else None,
         "arq": dados, "arqt": _tipo_mime(nome), "arqn": len(dados)})
    return {**doc, "chunks": 0}


# O `Content-Type` que a rota de download devolve. Deduzido da EXTENSÃO e não
# adivinhado do conteúdo: é a extensão que o navegador usa pra decidir se abre
# ou baixa, e é ela que o aluno reconhece. `octet-stream` é o default honesto —
# força download em vez de o navegador tentar renderizar algo que não sabe.
MIME = {"pdf": "application/pdf", "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _tipo_mime(nome: str) -> str:
    ext = (nome.rsplit(".", 1)[-1] if "." in nome else "").lower()
    return MIME.get(ext, "application/octet-stream")


def arquivo(usuario_id: int, documento_id: int) -> dict | None:
    """Os bytes do original, se forem DELE e se existirem.

    O `usuario_id` no WHERE é a autorização inteira, e é assim que toda a
    biblioteca já funciona (019): sem ele, um id sequencial na URL daria a
    apostila paga de um aluno para outro. Não há checagem em camada acima —
    ela mora aqui, junto do SELECT, onde não dá pra esquecer.

    Devolve `None` tanto pra material de outro dono quanto pra material antigo
    sem arquivo: quem chama responde 404 nos dois casos, e é o certo — dizer
    "existe mas não é seu" já é contar algo sobre a biblioteca alheia."""
    return db.exec1(
        """SELECT titulo, origem, arquivo, arquivo_tipo, arquivo_bytes
             FROM documento
            WHERE id = %(d)s AND usuario_id = %(u)s AND arquivo IS NOT NULL""",
        {"d": documento_id, "u": usuario_id})


def texto_para_vetor(texto: str, disciplina: str | None, assunto: str | None) -> str:
    """O texto que vai ao EMBEDDING — com o rótulo na frente.

    POR QUE O RÓTULO ENTRA NO VETOR. Até aqui a correção que o aluno fazia na
    disciplina e no assunto era usada pra gerar questão, pra recortar a fila e
    pro seletor da tela — e NÃO pra busca, porque só o corpo do trecho era
    vetorizado. O efeito é o que ele relatou: rotular uma apostila como
    "Ciências Forenses" não fazia a busca achá-la quando ele perguntava de
    ciências forenses. A informação mais confiável que existe sobre aquele
    material — a que uma pessoa digitou olhando o conteúdo — ficava fora do
    único lugar onde decide o que é encontrado.

    O `chunk.texto` GRAVADO continua limpo, e essa separação é o ponto: é ele
    que `formatar_contexto` manda ao prompt, e prefixar ali faria o tutor ler
    "Disciplina: X. Assunto: Y." como se fosse conteúdo da apostila. O rótulo
    enriquece o VETOR, não o texto.

    Vale só pro material do ALUNO. Chunk de lei tem norma, artigo e rubrica, que
    `por_dispositivo` e `por_rubrica` já usam com precisão maior que qualquer
    prefixo — e mexer no vetor da lei exigiria reingerir 2.673 chunks pra
    resolver um problema que a medição não aponta (`avaliar_retrieval.py`:
    dispositivo 6/6, rubrica 4/4).

    O ASSUNTO VEM PRIMEIRO, E NUNCA SE DEPENDE DA DISCIPLINA SOZINHA. O nome da
    matéria muda de edital pra edital — "Direito Administrativo", "Noções de
    Direito Administrativo", "Direito Administrativo e Gestão Pública" são a
    mesma gaveta com três nomes, e a PC-PR tem duas dessas ao mesmo tempo.
    Apostila rotulada com o nome de um edital deixaria de ser encontrada ao
    trocar de concurso, o que é o pior tipo de perda: silenciosa.
    O assunto ("papiloscopia", "improbidade") não tem esse problema — é o que a
    pessoa realmente quer estudar, e é a mesma razão pela qual
    `assunto._com_assunto` já descarta nome de disciplina como assunto de busca:
    disciplina é a gaveta, não o conteúdo.

    Por isso o assunto abre o prefixo e é REPETIDO no fim: embedding é média, e
    posição pesa pouco — repetir é o que de fato move o vetor na direção dele.
    A disciplina fica no meio, como contexto, e sozinha nunca é o bastante.

    Sem rótulo devolve o texto intacto: `sha256` igual, cache aproveitado, nada
    reindexado sem motivo."""
    a = (assunto or "").strip()
    d = (disciplina or "").strip()
    if a and d:
        return f"{a}. {d}. {a}. {texto}"
    if a:
        return f"{a}. {a}. {texto}"
    if d:
        return f"{d}. {texto}"
    return texto


# Classe do advisory lock do Postgres. Número arbitrário e fixo: ele só existe
# pra que `pg_try_advisory_lock(classe, documento_id)` não colida com outro uso
# de advisory lock que apareça no projeto.
TRAVA_INDEXACAO = 40271


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

    UM INDEXADOR POR DOCUMENTO, garantido por lock no banco — ver
    `TRAVA_INDEXACAO`. A fila deste processo tem um trabalhador só, e por muito
    tempo isso pareceu bastar; não basta, porque a fila é do PROCESSO e não do
    banco.
    """
    try:
        texto = _extrair(nome, dados)
        # `_dividir` e não `chunk_generico` direto: `indexar` reextrai dos bytes
        # por decisão (ver docstring), então ele tem a MESMA escolha de chunker a
        # fazer que o `registrar`. Trocar só num dos dois foi o que fiz primeiro,
        # e o efeito foi silencioso: a CF reindexada voltou com 1074 janelas
        # genéricas e zero artigo, exatamente como antes, porque o caminho que
        # roda de verdade é este.
        chunks = _dividir(texto, nome)
    except Exception as e:  # noqa: BLE001 — ver o comentário do except final
        with db.conexao_isolada() as c, c.cursor() as cur:
            cur.execute("UPDATE documento SET status='falha', erro=%s WHERE id=%s",
                        (str(e)[:500], documento_id))
        return

    # O rótulo ATUAL, lido aqui e não recebido por parâmetro: `indexar` roda em
    # background e pode começar depois de o aluno já ter corrigido a disciplina
    # na tela. Ler no começo do trabalho pega a versão mais nova que existe.
    rot = db.exec1("SELECT disciplina, assunto, tipo FROM documento WHERE id = %(i)s",
                   {"i": documento_id}) or {}
    # MATERIAL DE REFERÊNCIA NÃO LEVA ASSUNTO EM TRECHO NENHUM — nem no vetor,
    # nem no tsvector. Ver o bloco de `TIPOS_DE_REFERENCIA`: um assunto único
    # repetido em 1074 trechos da CF fazia a cópia do aluno ganhar 6 de 6 em
    # consulta constitucional qualquer, devolvendo artigo sem relação.
    #
    # A DISCIPLINA fica. Ela é VERDADE nos 1074 trechos (é tudo Direito
    # Constitucional), e é por nome de disciplina que `mesa.filtro` acha o
    # material. A 025 mediu esse ganho; o que estava errado era o assunto.
    # A DISCIPLINA TAMBÉM SAI, e isto foi a segunda medição. Tirado o assunto,
    # a cópia da CF ainda levava 5 de 5 em "direitos e garantias fundamentais:
    # remédios constitucionais", devolvendo art. 196 (saúde) e art. 6 (direitos
    # sociais) — enquanto a CF oficial, com os MESMOS artigos, não aparecia.
    #
    # A causa: "Direito Constitucional" no `rotulo` casa lexicalmente com
    # "direitos"/"constitucionais" em TODOS os 1074 trechos, e o trecho oficial
    # tem `rotulo` NULL. O rótulo era verdadeiro e ainda assim decidia a
    # ordenação — porque num corpus de norma inteira ele não distingue trecho
    # nenhum: só multiplica por mil um acerto que não informa nada.
    #
    # O que a 025 comprou foi outra coisa: o rótulo que o ALUNO corrige valendo
    # na busca de material de AULA ("papiloscopia", "ciências forenses"). Ali o
    # rótulo distingue a aula 12 da aula 3, e a medição dela segue de pé — o
    # teste de "traumatologia forense" continua devolvendo a aula em 1º.
    #
    # `documento.disciplina` FICA: é dela que sai o recorte da mesa
    # (`mesa.filtro('d.disciplina')`) e o agrupamento da tela. O que sai é a
    # injeção por trecho. Cópia da CF passa a se comportar como a CF.
    if e_referencia(rot.get("tipo"), chunks):
        rot = {**rot, "assunto": None, "disciplina": None}
    # O MESMO rótulo vai por dois caminhos, e é de propósito: `texto_para_vetor`
    # o põe no vetor (semântico) e `chunk.rotulo` o põe no tsvector (lexical,
    # 025). Medido, o vetor sozinho não bastava — "papiloscopia" subiu pra
    # posição 2, mas "ciências forenses" ficou fora do top6, porque embedding é
    # média e o rótulo é curto perto do corpo. O lexical casa a palavra
    # independentemente do tamanho do trecho.
    # Ordem espelha `texto_para_vetor`: assunto na frente. No tsvector a ordem
    # não muda nada (é conjunto de lexemas), mas duas formações diferentes da
    # mesma string é o começo de duas strings diferentes — e o `rotulo` é o que
    # o teste compara.
    rotulo_lex = ". ".join(x for x in (rot.get("assunto"), rot.get("disciplina")) if x) or None

    try:
        with db.conexao_isolada() as c:
            # UM INDEXADOR POR DOCUMENTO — e este lock existe porque a falta
            # dele já apagou material.
            #
            # O QUE ACONTECEU. `uvicorn --reload` chama `retomar_pendentes()` a
            # cada boot, e um comando de manutenção rodando `retomar_pendentes()`
            # noutro processo pegou o MESMO documento no mesmo instante. Os dois
            # trabalhadores rodaram este bloco em paralelo: os dois apagaram os
            # trechos, os dois começaram a inserir, e o segundo bateu em
            # `duplicate key value violates unique constraint
            # "chunk_documento_id_ordem_key"`. O documento terminou com status
            # 'falha' e ZERO trechos — a Constituição inteira do aluno,
            # invisível pra busca.
            #
            # A idempotência do DELETE abaixo é real e não protege disto: ela
            # cobre duas passadas em SEQUÊNCIA, e o problema é o paralelo. A fila
            # com um trabalhador também não, porque ela é do PROCESSO: dois
            # processos têm duas filas e nenhum coordena com o outro.
            #
            # `pg_try_advisory_lock` é a coordenação no único lugar que os dois
            # compartilham — o banco. Não espera (`try_`): quem perde a corrida
            # DESISTE, porque quem ganhou vai fazer exatamente o mesmo trabalho.
            # Lock de sessão, então sai sozinho quando esta conexão fecha,
            # inclusive se o processo morrer no meio.
            with c.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s, %s) AS meu",
                            (TRAVA_INDEXACAO, documento_id))
                if not cur.fetchone()["meu"]:
                    print(f"[tutor] {documento_id} já está sendo indexado "
                          f"por outro processo; deixo pra ele.")
                    return

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
                vetores = embeddings.embed_passagens(
                    [texto_para_vetor(x["texto"], rot.get("disciplina"),
                                      rot.get("assunto")) for x in lote])
                with c.cursor() as cur:
                    for j, (x, v) in enumerate(zip(lote, vetores)):
                        cur.execute(
                            """INSERT INTO chunk (documento_id, ordem, texto, norma,
                                                  artigo, paragrafo, inciso, rubrica,
                                                  secao, embedding, rotulo)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (documento_id, i + j, x["texto"], x["norma"], x["artigo"],
                             x["paragrafo"], x["inciso"], x.get("rubrica"),
                             x.get("secao"), v, rotulo_lex))
            with c.cursor() as cur:
                # `chunks_total` é reescrito, não só o status: ele foi gravado
                # em `registrar` com a contagem daquele momento, e a contagem
                # MUDA quando o chunker muda de opinião sobre o texto. A CF do
                # aluno tinha 1074 (janelas genéricas de uma versão anterior de
                # `_dividir`) e reindexou pra 543 artigos — a tela mostrava
                # "543 de 1074" pra material completo, que parece indexação
                # travada. O denominador tem de vir de quem acabou de contar.
                # SEM `status='pronto'` AQUI: ele é a última coisa que
                # acontece, depois do rótulo. Ver o bloco no fim da função.
                cur.execute("""UPDATE documento
                                  SET erro=NULL, chunks_total=%s
                                WHERE id=%s""",
                            (len(chunks), documento_id))

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
        _classificar_se_faltar(documento_id, texto, chunks)
    except Exception:
        pass

    # E O 'pronto' É A ÚLTIMA LINHA, depois do rótulo — não antes.
    #
    # A tela só faz polling ENQUANTO existe material `processando` (senão seria
    # consulta a cada 3s numa biblioteca parada). Anunciar `pronto` antes de
    # classificar abre uma janela de segundos em que a lista é buscada com o
    # material já pronto e ainda SEM disciplina: a tela desenha "Outros", para
    # de perguntar, e fica mentindo até alguém dar F5. Relatado exatamente
    # assim — "ele não identificou a matéria" — com a matéria gravada no banco.
    #
    # Só o ANÚNCIO mudou de lugar: o rótulo continua fora do try da indexação e
    # continua sem poder marcar `falha` (o `except ... pass` acima), então
    # material sem cota de modelo termina `pronto` do mesmo jeito. Índice
    # continua sendo o produto; o que ele não pode é dizer que acabou enquanto
    # a linha ainda vai mudar na tela.
    with db.conexao_isolada() as c, c.cursor() as cur:
        cur.execute("UPDATE documento SET status='pronto' WHERE id=%s", (documento_id,))


def _classificar_se_faltar(documento_id: int, texto: str,
                           chunks: list[dict] | None = None) -> None:
    """Preenche disciplina/assunto quando o aluno não disse.

    NÃO sobrescreve o que ele digitou: quem informou a matéria decidiu, e um
    palpite de modelo passando por cima disso é o sistema discordando de quem
    tem mais contexto. Só completa o que está vazio — e é por campo, porque
    "informei a disciplina, descubra o assunto" é um caso normal.

    MATERIAL DE REFERÊNCIA só recebe disciplina (ver `TIPOS_DE_REFERENCIA`).
    `chunks` entra pra que a decisão use a forma REAL do material e não só o
    seletor da tela: corpus de norma fatiado por artigo é referência mesmo
    marcado como "aula".
    """
    with db.conexao_isolada() as c:
        with c.cursor() as cur:
            cur.execute("SELECT disciplina, assunto, tipo, origem, classificado_por "
                        "FROM documento WHERE id=%s", (documento_id,))
            atual = cur.fetchone()
        if not atual:
            return
        referencia = e_referencia(atual["tipo"], chunks)
        # Referência precisa só da disciplina; pedir o assunto de novo a cada
        # reindexação gastaria cota pra descartar a resposta.
        if atual["disciplina"] and (atual["assunto"] or referencia):
            return
        conhecidas = [r["disciplina"] for r in
                      db.query("SELECT DISTINCT disciplina FROM documento "
                               "WHERE disciplina IS NOT NULL ORDER BY 1")]
        palpite = classificar(texto, conhecidas, com_assunto=not referencia,
                              nome_arquivo=atual.get("origem"))
        if not palpite:
            return
        disc = atual["disciplina"] or palpite.get("disciplina")
        # Em referência o assunto é ZERADO, não preservado: se o palpite antigo
        # gravou um (era o comportamento até aqui, e é ele que poluiu a busca),
        # reindexar tem de limpar. Preservar seria carregar o defeito pra
        # frente justamente na hora que existe pra consertá-lo.
        assu = None if referencia else (atual["assunto"] or palpite.get("assunto"))
        # 'aluno' se ELE informou a disciplina e o modelo só completou o assunto:
        # a parte que decide o recorte da mesa continua sendo a dele.
        #
        # Sai do `classificado_por` GRAVADO, não de "a disciplina já está
        # preenchida" — que era a regra e estava errada na REINDEXAÇÃO: na
        # segunda passada a disciplina já está lá, posta pelo próprio modelo na
        # primeira, e o material se promovia sozinho a "você informou". Visto
        # acontecer: o doc 789 perdeu o aviso "eu deduzi, confira" reindexando,
        # sem ninguém confirmar nada. `registrar` já grava 'aluno' só quando o
        # aluno digita, então o campo antigo é a resposta, e a pergunta velha
        # ("tem disciplina?") só coincidia com ela na primeira vez.
        de_quem = "aluno" if atual["classificado_por"] == "aluno" else "modelo"
        with c.cursor() as cur:
            cur.execute(
                """UPDATE documento
                      SET disciplina = %s, assunto = %s, classificado_por = %s
                    WHERE id = %s""",
                (disc, assu, de_quem, documento_id))


def atualizar(usuario_id: int, documento_id: int, disciplina: str | None = None,
              assunto: str | None = None) -> dict | None:
    """O aluno corrige o palpite. Passa a valer como 'aluno' — a lista da tela
    é que vale, mesmo princípio da curadoria de edital.

    DEVOLVE `reindexar: True` quando a correção precisa entrar nos vetores. O
    rótulo agora faz parte do texto embutido (`texto_para_vetor`), então mudá-lo
    sem reindexar deixa a biblioteca num estado que ninguém consegue explicar: a
    lista mostra "Ciências Forenses" e a busca continua respondendo pelo rótulo
    velho. Quem reindexa é a rota, em background — aqui não, porque `atualizar`
    responde dentro do request e o embedding leva minutos.

    Só pede reindexação se houver ARQUIVO (024): sem os bytes não há como
    reextrair o texto, e material anterior à migração fica com o vetor antigo.
    A lista continua certa; a busca é que não melhora — e é melhor isso que
    apagar os trechos que existem."""
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
    r = db.exec1(
        f"""UPDATE documento SET {', '.join(campos)}
             WHERE id = %(d)s AND usuario_id = %(u)s
         RETURNING id, titulo, disciplina, assunto, tipo, status, classificado_por,
                   origem, (arquivo IS NOT NULL) AS tem_arquivo""",
        params)
    if not r:
        return None
    return {**r, "reindexar": bool(r.pop("tem_arquivo"))}


def bytes_do_arquivo(usuario_id: int, documento_id: int) -> tuple[str, bytes] | None:
    """(nome, bytes) do original, pra reindexar sem o aluno reenviar nada.

    É esta função que torna possível o laço "corrigi o rótulo -> a busca
    melhora": antes da 024 os bytes não existiam, e reindexar exigia o upload de
    novo — que é exatamente o atrito que fazia a correção não valer nada."""
    r = db.exec1(
        """SELECT origem, arquivo FROM documento
            WHERE id = %(d)s AND usuario_id = %(u)s AND arquivo IS NOT NULL""",
        {"d": documento_id, "u": usuario_id})
    return (r["origem"] or "material", bytes(r["arquivo"])) if r else None


# ══════════════════════════════════════════════════ a FILA de indexação
#
# POR QUE UMA FILA COM UM TRABALHADOR SÓ.
#
# A rota fazia `fundo.add_task(indexar, doc_id, nome, dados)` por upload. Com um
# arquivo isso é ótimo. Com VINTE, o `BackgroundTasks` do FastAPI despacha as
# vinte pro pool de threads quase juntas, e cada uma:
#
#   · carrega o arquivo inteiro em memória (o `dados` fica preso na closure),
#   · extrai o PDF com pypdf (CPU + RAM),
#   · abre uma conexão isolada própria,
#   · e roda o e5 na CPU.
#
# Vinte disso ao mesmo tempo derrubou o servidor — relatado e reproduzível: o
# upload das vinte apostilas matou a API depois da primeira, e o F5 voltou numa
# tela vazia porque não havia mais API pra responder `/materiais`.
#
# A fila conserta os dois lados de uma vez. Um trabalhador só significa
# concorrência 1 — o embedding é CPU local, então paralelizar nunca ia ser mais
# rápido, só mais frágil. E a fila carrega o ID, não os BYTES: quem precisa do
# arquivo o lê do banco na hora de trabalhar (só é possível por causa da 024), e
# a memória do processo deixa de crescer com o tamanho do lote.
_fila: "queue.Queue[int]" = queue.Queue()
_trabalhador: threading.Thread | None = None
_trava_trabalhador = threading.Lock()


def _trabalhar() -> None:
    """Consome a fila pra sempre, um documento por vez.

    Erro NUNCA mata o trabalhador: `indexar` já converte exceção em
    `status='falha'` com a razão, e o que escapar disso é engolido aqui de
    propósito — um PDF corrompido não pode parar os dezenove atrás dele na fila.
    """
    while True:
        doc_id = _fila.get()
        try:
            # CONEXÃO ISOLADA, e não `db.exec1`. `core.db.conn()` devolve UMA
            # conexão de módulo, e psycopg não é thread-safe: usá-la aqui
            # enquanto uma requisição usa a mesma é corrupção de protocolo,
            # não lentidão. Apareceu como material caindo em `status='falha'`
            # sem razão nenhuma no teste — e apareceria em produção como
            # exceção aleatória em rota que nada tem a ver com material.
            # `indexar` já fazia certo (é ele que documenta o motivo).
            with db.conexao_isolada() as c, c.cursor() as cur:
                cur.execute(
                    "SELECT origem, arquivo FROM documento "
                    " WHERE id = %s AND arquivo IS NOT NULL", (doc_id,))
                linha = cur.fetchone()
            if linha:
                indexar(doc_id, linha["origem"] or "material", bytes(linha["arquivo"]))
        except Exception as e:  # noqa: BLE001 — ver o docstring
            print(f"[tutor] indexação de {doc_id} falhou na fila: {e}")
        finally:
            _fila.task_done()


def deve_indexar(doc: dict) -> bool:
    """A linha que `registrar` devolveu gerou trabalho de indexação?

    Falso num caso só: o upload apenas ANEXOU o arquivo original a um material
    que já estava pronto e indexado (material de antes da 024). Ali os trechos
    já existem, e enfileirar pagaria o embedding outra vez pelo mesmo texto —
    numa apostila de 500 trechos são minutos de CPU por nada, e a biblioteca
    piscaria `processando` num material que está pronto.

    Vive aqui e não na rota porque são DUAS que sobem material (arquivo e
    link), e a regra tem que ser a mesma nas duas: a terceira que aparecer
    chama isto sem precisar saber por quê."""
    return not doc.get("arquivo_anexado")


def enfileirar(documento_id: int) -> None:
    """Põe o documento na fila e garante que o trabalhador está de pé.

    Chamado pela rota de upload em vez do `add_task` direto. Responde na hora: a
    tela já mostra `processando` e o `0 de N` sai do banco, então a pessoa pode
    sair da página, ir responder questões e voltar — nada depende de a aba ficar
    aberta.

    Trabalhador criado sob demanda e `daemon=True`: não há o que esperar no
    shutdown, porque o que ficar na fila é retomado no próximo boot por
    `retomar_pendentes` (a linha continua `processando` no banco)."""
    global _trabalhador
    with _trava_trabalhador:
        if _trabalhador is None or not _trabalhador.is_alive():
            _trabalhador = threading.Thread(target=_trabalhar, daemon=True,
                                            name="indexador")
            _trabalhador.start()
    _fila.put(documento_id)


def esperar_fila(segundos: float = 180.0) -> bool:
    """Bloqueia até a fila drenar. `False` se estourou o tempo.

    Existe pro TESTE, e a razão é uma mudança de comportamento real: com
    `TestClient`, o `BackgroundTasks` do FastAPI rodava ANTES de a resposta
    voltar, então quatro testes podiam subir material e afirmar
    `status == 'pronto'` na linha seguinte. Com a fila a indexação é
    assíncrona de verdade — o que é o ponto —, e quem afirma sobre o RESULTADO
    tem de esperar por ele.

    `queue.join()` não serve sozinho: ele volta quando o último `task_done`
    acontece, e o `UPDATE ... status='pronto'` do `indexar` já terminou nessa
    altura, mas o teste pode ler por outra conexão. Então espera a fila E dá
    uma folga curta."""
    fim = time.monotonic() + segundos
    while _fila.unfinished_tasks and time.monotonic() < fim:
        time.sleep(0.2)
    return not _fila.unfinished_tasks


def tamanho_da_fila() -> int:
    """Quantos esperando. A tela usa pra dizer "3º da fila" em vez de um
    `processando` mudo que parece travado."""
    return _fila.qsize()


def pendentes_retomaveis() -> list[dict]:
    """Material preso em `processando` que dá pra retomar sozinho.

    A indexação roda em background NO PROCESSO do servidor — não há worker. Um
    restart no meio (o `--reload` do uvicorn, um deploy, um Ctrl+C) deixava a
    linha em `processando` PRA SEMPRE, e o único jeito de sair era o aluno
    reenviar o arquivo, porque os bytes não existiam em lugar nenhum.

    A 024 mudou isso: o arquivo está no banco. Então a fila passou a ser
    retomável, e é o que destrava carga grande — subir vinte apostilas deixava
    de ser uma aposta de que nada reinicia por horas.

    `arquivo IS NOT NULL` é o filtro inteiro: material anterior à 024 continua
    dependendo do reenvio, e é honesto que continue — sem bytes não há o que
    reprocessar. `ORDER BY id` retoma na ordem em que foram subidos."""
    return db.query(
        """SELECT id, origem FROM documento
            WHERE status = 'processando' AND arquivo IS NOT NULL
            ORDER BY id""")


def retomar_pendentes() -> int:
    """Reindexa, UM POR VEZ, tudo o que ficou pendurado. Devolve quantos.

    Sequencial de propósito: o embedding é CPU local e paralelizar só faria os
    lotes disputarem os mesmos núcleos, com o efeito colateral de várias
    conexões isoladas abertas ao mesmo tempo. Vinte apostilas em série levam o
    tempo que levam; em paralelo levariam o mesmo e com mais coisa pra dar
    errado.

    Erro de um documento não para os outros: `indexar` já converte exceção em
    `status='falha'` com a razão, que é exatamente o comportamento desejado
    aqui — um PDF corrompido no meio da fila não pode segurar os dezenove."""
    pend = pendentes_retomaveis()
    for d in pend:
        enfileirar(d["id"])
    return len(pend)


def renomear_disciplina(usuario_id: int, de: str, para: str | None = None) -> list[int]:
    """Renomeia a disciplina em TODO o material do aluno que a usa. Devolve quantos.

    Pedido, e a razão é do domínio: "às vezes o mesmo assunto cai em nomes de
    matérias diferentes". Criminalística num edital é Ciências Forenses no
    outro, Direito Administrativo é "Noções de Direito Administrativo" num
    terceiro. Corrigir material por material é o que existia — treze cliques
    pra treze aulas do mesmo curso.

    A reindexação é NECESSÁRIA e é o custo real disto: `chunk.rotulo` entra no
    tsvector (025), então trocar a disciplina sem reindexar deixaria a lista
    dizendo um nome e a BUSCA respondendo pelo outro — o mesmo estado
    inexplicável que `atualizar` já evita pra um documento só. Quem chama
    enfileira; aqui só se troca o rótulo e se devolve a lista de ids.

    `para` vazio TIRA a disciplina (volta pro grupo "sem matéria"), que é o que
    a tela já faz ao soltar um material fora dos grupos."""
    de = (de or "").strip()
    if not de:
        return []
    novo = (para or "").strip()[:120] or None
    linhas = db.query(
        """UPDATE documento SET disciplina = %(p)s, classificado_por = 'aluno'
            WHERE usuario_id = %(u)s AND disciplina = %(d)s
        RETURNING id""",
        {"u": usuario_id, "d": de, "p": novo})
    return [r["id"] for r in linhas]


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
                  d.erro, d.classificado_por, d.chunks_total, d.origem, d.url,
                  d.criado_em,
                  d.arquivo_bytes, (d.arquivo IS NOT NULL) AS tem_arquivo,
                  d.mesa_id, m.nome AS mesa_nome,
                  count(c.id) AS chunks,
                  -- É MATERIAL DE REFERÊNCIA? A regra é a de `e_referencia()`,
                  -- em SQL porque a tela precisa dela por linha e não vale
                  -- reimplementá-la no front: jurisprudência, ou material
                  -- fatiado por artigo (corpus de norma inteira). É o que faz a
                  -- tela separar "poço de consulta" de "aula", que era o pedido:
                  -- "jurisprudência não deve ser fragmentada, é um poço de
                  -- informações que serve de auxiliar complementar aos PDFs".
                  (d.tipo = ANY(%(ref)s) OR count(c.artigo) > 0) AS referencia,
                  -- FATIADO POR ARTIGO: este material é texto de norma, não
                  -- aula — `_e_lei_seca` o reconheceu e `chunk_lei` o dividiu
                  -- por dispositivo. Separado de `referencia` porque responde
                  -- outra pergunta: `referencia` é "como a tela deve tratar
                  -- isto", e este é "isto é uma cópia de lei".
                  --
                  -- A tela precisa dizer isso em algum lugar. Relato: o aluno
                  -- apagou a cópia da Constituição e não teve como CONFERIR
                  -- que sobrou nada — "ficou ainda algum rastro do link da CF
                  -- que ele mapeou como aula, porém eu não consigo saber, ele
                  -- não me dá essa informação". Estava limpo, e a tela não
                  -- tinha como dizer nem que estava nem que não.
                  (count(c.artigo) > 0) AS fatiado_por_artigo
             FROM documento d
             LEFT JOIN chunk c ON c.documento_id = d.id
             -- LEFT: material do pool comum (mesa_id NULL) não pode desaparecer
             -- da lista por não ter mesa. É o caso de tudo que foi subido antes
             -- da 021.
             LEFT JOIN mesa m ON m.id = d.mesa_id
            WHERE d.usuario_id = %(u)s
            GROUP BY d.id, m.nome
            ORDER BY d.criado_em DESC, d.id DESC""",
        {"u": usuario_id, "ref": list(TIPOS_DE_REFERENCIA)})


def sugestoes(usuario_id: int, mesa_id: int | None = None) -> dict:
    """O que ESTE aluno já usou de rótulo, pra tela oferecer em vez de exigir
    que ele lembre.

    Só da biblioteca dele: sugerir disciplina que outro aluno cadastrou
    vazaria o que os outros estudam, e o acervo público já tem rota própria
    (`GET /disciplinas`).

    `assuntos_por_disciplina` além da lista chapada porque assunto só faz
    sentido DENTRO de uma matéria — oferecer "Remédios constitucionais" a
    quem está subindo Contabilidade é ruído que atrapalha mais que ajuda.
    A lista chapada fica pro caso de ainda não haver disciplina escolhida.

    `topicos_por_disciplina` é a OUTRA fonte de assunto: o conteúdo programático
    do edital da mesa. Existe porque o interruptor da tela ("usar sugestões
    daqui" × "usar do edital") mandava só na disciplina — do lado do assunto ele
    não tinha o que oferecer, e um interruptor que não muda nada é pior que
    interruptor nenhum. Vem SEMPRE por disciplina, nunca chapado: a objeção
    medida contra usar tópico como sugestão continua de pé (o edital da Dataprev
    tem 1015, e uma lista com isso não é sugestão, é um documento) — o que a
    derruba é o recorte, porque a lista que a tela pede é a de UM material, que
    tem UMA disciplina.
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
    # SQL direto e não `edital.mais_recente`: `core.edital` importa `core.material`
    # (ingestão de PDF de edital), e o caminho de volta fecharia o ciclo. A regra
    # do "mais recente da mesa" está duplicada em uma linha, e é a mesma dele —
    # se ela mudar, muda nos dois (o docstring de lá diz por que ela existe).
    topicos: dict[str, list[str]] = {}
    if mesa_id is not None:
        ed = db.exec1("""SELECT id FROM edital WHERE mesa_id = %(m)s
                          ORDER BY criado_em DESC, id DESC LIMIT 1""", {"m": mesa_id})
        if ed:
            for l in db.query("""SELECT disciplina, texto FROM topico
                                  WHERE edital_id = %(e)s AND texto IS NOT NULL
                                  ORDER BY disciplina, ordem""", {"e": ed["id"]}):
                if l["disciplina"]:
                    topicos.setdefault(l["disciplina"], []).append(l["texto"])
    return {
        "disciplinas": sorted(disciplinas),
        "assuntos": sorted(assuntos),
        "assuntos_por_disciplina": {k: sorted(v) for k, v in sorted(por_disc.items())},
        "topicos_por_disciplina": topicos,
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
