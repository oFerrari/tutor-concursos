#!/usr/bin/env python3
"""
API HTTP — a mesma lógica de core/*.py, exposta por rota em vez de terminal.

    uvicorn api:app --reload --port 8000

Não é reescrita do fluxo: cada rota abaixo chama exatamente as funções que
`chat.py` já chama. A diferença é onde mora o ESTADO do diálogo socrático —
em `chat.py` são variáveis locais de um `while True`; aqui o cliente (o
futuro Next.js) manda `historico`/`nivel` de volta em cada chamada, porque
`socratic.avaliar()` já foi desenhado stateless (recebe histórico como
parâmetro, não guarda nada) — dá pra expor sem mudar uma linha dele.

AUTENTICAÇÃO: Bearer token (JWT, `core/auth.py`). Toda rota que não é
`/auth/*` exige `Authorization: Bearer <token>` e resolve `usuario_id` a
partir dele — nunca aceita usuario_id vindo do corpo da requisição, porque
isso deixaria qualquer cliente alegar ser outra pessoa só mudando um campo.

MESA (migração 010): o cliente diz em qual mesa está pelo header
`X-Mesa-Id`, por requisição — não há "mesa ativa" guardada no servidor. A
escolha é deliberada: estado de sessão no servidor faz duas abas abertas em
mesas diferentes brigarem pela mesma variável, e o aluno com dois editais
abertos ao mesmo tempo é o caso de uso normal, não a exceção. O header
identifica, o `usuario_id` do token AUTORIZA: `mesa.obter()` filtra por
usuario_id, então pedir a mesa de outra pessoa dá 404, não os dados dela.
Sem header, cai na mesa padrão da conta (`mesa.padrao`) — é o que mantém a
CLI e qualquer cliente que ainda não conhece mesas funcionando igual.
"""
import tempfile
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from core import (auth, conversa, desafio, edital, geracao, mesa, questoes, rascunho,
                  ritmo, scheduler, simulado, socratic)
from core.config import CORS_ORIGINS
from core.llm import ErroLLM

VERSAO = "api-v5"

app = FastAPI(title="Tutor de concursos — API", version=VERSAO)

# CORS: só o Next.js local por padrão. Sem isso o navegador bloqueia a
# resposta antes mesmo do JS ver — dá erro de rede genérico no fetch, não
# um 403 explicável, então isso costuma ser o primeiro obstáculo silencioso
# ao ligar um frontend de verdade contra a API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------- auth
class Credenciais(BaseModel):
    email: str
    senha: str


@app.post("/auth/registrar")
def rota_registrar(c: Credenciais):
    try:
        u = auth.registrar(c.email, c.senha)
    except auth.ErroAuth as e:
        raise HTTPException(400, str(e))
    return {"token": auth.emitir_token(u["id"]), "usuario": u}


@app.post("/auth/login")
def rota_login(c: Credenciais):
    try:
        u = auth.autenticar(c.email, c.senha)
    except auth.ErroAuth as e:
        raise HTTPException(401, str(e))
    return {"token": auth.emitir_token(u["id"]), "usuario": u}


# HTTPBearer (não Header solto) por causa do Swagger: com isso o /docs ganha
# um botão "Authorize" que aceita só o token puro — sem ele, cada rota exigia
# digitar "Bearer <token>" na mão em cada teste, e esquecer o prefixo dá 401
# silencioso (aconteceu na prática: log mostrava login 200 e a rota seguinte
# 401, porque o token colado sem "Bearer " não bate no Header solto).
_security = HTTPBearer(auto_error=False)


def usuario_atual(cred: HTTPAuthorizationCredentials | None = Depends(_security)) -> int:
    if not cred:
        raise HTTPException(401, "token ausente — clique em 'Authorize' no /docs "
                                 "e cole SÓ o token (sem 'Bearer ', o Swagger adiciona)")
    try:
        return auth.usuario_id_do_token(cred.credentials)
    except auth.ErroAuth as e:
        raise HTTPException(401, str(e))


def mesa_atual(x_mesa_id: str | None = Header(default=None),
               uid: int = Depends(usuario_atual)) -> dict:
    """
    A mesa desta requisição, com as disciplinas dela já resolvidas — as
    funções de `core/` recebem a lista pronta, não o mesa_id, pra não
    repetir a mesma consulta em cada uma dentro de um request só.

    Header ausente = mesa padrão da conta. Header com id de outra pessoa
    (ou inexistente) = 404, nunca os dados dela: `mesa.obter()` filtra por
    usuario_id, mesmo espírito de `simulado.pertence_a()`.
    """
    if x_mesa_id is None or not x_mesa_id.strip():
        return mesa.contexto(uid)
    try:
        mesa_id = int(x_mesa_id)
    except ValueError:
        raise HTTPException(422, "X-Mesa-Id precisa ser um número inteiro")
    ctx = mesa.contexto(uid, mesa_id)
    if not ctx:
        raise HTTPException(404, "mesa não encontrada")
    return ctx


# ---------------------------------------------------------------------- mesas
class MesaBody(BaseModel):
    nome: str
    orgao: str | None = None
    banca: str | None = None


@app.get("/mesa")
def rota_mesa_atual(m: dict = Depends(mesa_atual)):
    """
    Qual mesa ESTA requisição está usando, já resolvida. Existe pra o
    cliente não precisar reimplementar a regra de fallback ("sem header =
    mesa mais antiga da conta"): duas cópias da mesma regra divergem, e
    divergir aqui significaria a sidebar dizer um nome enquanto a fila
    responde por outra mesa.

    `questoes` vem junto pras telas de estudo poderem EXPLICAR o vazio
    ("o acervo ainda não cobre estas disciplinas") em vez de mostrar uma
    lista vazia sem motivo. É a única rota que paga esse COUNT.
    """
    return {**m, "questoes": mesa.contar_questoes(m["disciplinas"])}


@app.get("/mesas")
def rota_listar_mesas(uid: int = Depends(usuario_atual)):
    return mesa.listar(uid)


@app.post("/mesas")
def rota_criar_mesa(body: MesaBody, uid: int = Depends(usuario_atual)):
    try:
        return mesa.criar(uid, body.nome, body.orgao, body.banca)
    except mesa.ErroMesa as e:
        raise HTTPException(400, str(e))


@app.get("/mesas/{mid}")
def rota_obter_mesa(mid: int, uid: int = Depends(usuario_atual)):
    """Inclui `disciplinas` — é o recorte que esta mesa aplica, e ver isso
    explícito é o que impede a tela de prometer um filtro que não existe
    (mesa sem edital devolve null e mostra o acervo inteiro)."""
    ctx = mesa.contexto(uid, mid)
    if not ctx:
        raise HTTPException(404, "mesa não encontrada")
    return ctx


class AtualizarMesaBody(BaseModel):
    nome: str | None = None
    orgao: str | None = None
    banca: str | None = None


@app.patch("/mesas/{mid}")
def rota_atualizar_mesa(mid: int, body: AtualizarMesaBody, uid: int = Depends(usuario_atual)):
    try:
        m = mesa.atualizar(uid, mid, body.nome, body.orgao, body.banca)
    except mesa.ErroMesa as e:
        raise HTTPException(400, str(e))
    if not m:
        raise HTTPException(404, "mesa não encontrada")
    return m


@app.delete("/mesas/{mid}")
def rota_apagar_mesa(mid: int, uid: int = Depends(usuario_atual)):
    """Apaga a mesa e o edital dela. NÃO apaga progresso, tentativas nem
    caderno de erros — esses são do aluno (ver core/mesa.py:apagar)."""
    if not mesa.apagar(uid, mid):
        raise HTTPException(404, "mesa não encontrada")
    return {"ok": True}


@app.get("/me")
def rota_me(uid: int = Depends(usuario_atual)):
    u = auth.obter(uid)
    if not u:
        raise HTTPException(404, "usuário não encontrado")
    return u


class AtualizarMeBody(BaseModel):
    email: str | None = None
    senha_atual: str | None = None
    senha_nova: str | None = None


@app.patch("/me")
def rota_atualizar_me(body: AtualizarMeBody, uid: int = Depends(usuario_atual)):
    # senha primeiro: se as duas coisas vierem juntas e a senha falhar
    # (senha_atual errada), o email não deve mudar mesmo assim.
    if body.senha_nova:
        if not body.senha_atual:
            raise HTTPException(422, "senha_atual é obrigatória pra trocar a senha")
        try:
            auth.atualizar_senha(uid, body.senha_atual, body.senha_nova)
        except auth.ErroAuth as e:
            raise HTTPException(400, str(e))
    if body.email:
        try:
            auth.atualizar_email(uid, body.email)
        except auth.ErroAuth as e:
            raise HTTPException(400, str(e))
    return auth.obter(uid)


class ApagarContaBody(BaseModel):
    senha: str


@app.delete("/me")
def rota_apagar_me(body: ApagarContaBody, uid: int = Depends(usuario_atual)):
    """Irreversível — ON DELETE CASCADE (migração 009) limpa tentativa/
    progresso/erro_caderno/simulado/edital(+topico) de uma vez."""
    try:
        auth.apagar_conta(uid, body.senha)
    except auth.ErroAuth as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ----------------------------------------------------------------- fila/estudo
@app.get("/fila")
def rota_fila(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return scheduler.fila(uid, disciplinas=m["disciplinas"])


@app.get("/carga")
def rota_carga(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return scheduler.carga_hoje(uid, m["disciplinas"])


@app.get("/sugestao")
def rota_sugestao(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return {"sugestao": ritmo.sugestao(uid, m["disciplinas"])}


@app.get("/questoes/{qid}")
def rota_questao(qid: int, uid: int = Depends(usuario_atual)):
    """
    Busca uma questão específica — usado pela tela de responder quando ela
    é aberta direto (refresh, link compartilhado), sem depender de já ter
    a lista da fila em memória no cliente. Não filtra por usuario_id porque
    o banco de questões é compartilhado (ver Decisões no CLAUDE.md);
    `uid` só garante que quem pergunta está autenticado.
    """
    q = questoes.obter_com_progresso(uid, qid)
    if not q:
        raise HTTPException(404, "questão não encontrada")
    return q


class AvaliarBody(BaseModel):
    resposta: str
    nivel: int = 0
    historico: list[dict] = []


@app.post("/questoes/{qid}/avaliar")
def rota_avaliar(qid: int, body: AvaliarBody, uid: int = Depends(usuario_atual)):
    """
    Um turno do diálogo socrático. NÃO registra nada — só julga e devolve
    pergunta-guia/comentário, igual ao meio do loop de `chat._estudar_lista`.
    O cliente decide, com essa resposta, se chama de novo (turno seguinte) ou
    fecha a questão em /registrar.
    """
    q = questoes.obter(qid)
    if not q:
        raise HTTPException(404, "questão não encontrada")
    try:
        # Dispatcher, não `avaliar()` direto: item C/E é corrigido em código.
        # Mandá-lo pro LLM compararia "C" contra uma justificativa em prosa.
        return socratic.avaliar_questao(q, body.resposta, body.nivel, body.historico)
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível: {e}")


class RegistrarBody(BaseModel):
    veredito: str
    resposta: str
    dicas_usadas: int = 0
    segundos: int | None = None
    simulado_id: int | None = None


@app.post("/questoes/{qid}/registrar")
def rota_registrar_tentativa(qid: int, body: RegistrarBody, uid: int = Depends(usuario_atual)):
    """Fecha a questão — equivalente ao `fechar()` de `chat._estudar_lista`."""
    if body.veredito not in ("correta", "parcial", "incorreta"):
        raise HTTPException(422, "veredito precisa ser correta/parcial/incorreta")
    try:
        return scheduler.registrar(uid, qid, body.veredito, body.resposta, body.dicas_usadas,
                                   body.segundos, body.simulado_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# -------------------------------------------------------------------- desafio
@app.get("/desafio")
def rota_desafio(n_reincidentes: int = 3, n_novas: int = 5, n_simulado: int = 5,
                 uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return desafio.montar(uid, n_reincidentes, n_novas, n_simulado, m["disciplinas"])


# ------------------------------------------------------------------- simulado
class IniciarSimuladoBody(BaseModel):
    n: int = simulado.N_PADRAO
    minutos: int | None = None
    disciplina: str | None = None
    # Lista pronta (vinda de /desafio, bloco "mini_simulado") pula o sorteio
    # aleatório — mesmo espírito de chat.simulado(questoes=...) aceitar uma
    # lista já escolhida em vez de reamostrar o acervo todo de novo.
    questao_ids: list[int] | None = None


@app.post("/simulados")
def rota_iniciar_simulado(body: IniciarSimuladoBody, uid: int = Depends(usuario_atual),
                          m: dict = Depends(mesa_atual)):
    if body.questao_ids:
        # Lista pronta vem do /desafio, que JÁ montou dentro do recorte da
        # mesa — refiltrar aqui só arriscaria descartar em silêncio o que
        # aquele bloco escolheu de propósito.
        mapa = questoes.obter_varias(body.questao_ids)
        qs = [mapa[i] for i in body.questao_ids if i in mapa]
    else:
        qs = simulado.selecionar(body.n, body.disciplina, m["disciplinas"])
    if not qs:
        raise HTTPException(404, "nenhuma questão no acervo (ou disciplina inexistente)")
    sid = simulado.iniciar(uid, len(qs), body.minutos, m["id"])
    return {"simulado_id": sid, "questoes": qs}


class RespostaSimuladoItem(BaseModel):
    questao_id: int
    resposta: str
    segundos: int | None = None


class RespostasSimuladoBody(BaseModel):
    respostas: list[RespostaSimuladoItem]
    segundos_total: int = 0


@app.post("/simulados/{sid}/respostas")
def rota_responder_simulado(sid: int, body: RespostasSimuladoBody, uid: int = Depends(usuario_atual)):
    """
    Sem diálogo (por design — ver core/simulado.py): manda TODAS as
    respostas de uma vez, corrige tudo, registra e devolve o relatório. É a
    versão HTTP do laço final de `chat.simulado()`.
    """
    if not simulado.pertence_a(sid, uid):
        # 404, não 403: não confirma pra quem tenta adivinhar que o id existe
        # e só não é seu (mesmo espírito da mensagem de login em auth.py).
        raise HTTPException(404, "simulado não encontrado")
    qmap = questoes.obter_varias([r.questao_id for r in body.respostas])
    for item in body.respostas:
        q = qmap.get(item.questao_id)
        if not q:
            continue
        try:
            av = simulado.corrigir(q, item.resposta)
        except ErroLLM as e:
            raise HTTPException(503, f"LLM indisponível ao corrigir \"{q['tema']}\": {e}")
        scheduler.registrar(uid, q["id"], av["veredito"], item.resposta, 0, item.segundos,
                            simulado_id=sid)
    return {
        "resultado": simulado.finalizar(sid, uid, body.segundos_total),
        "relatorio": simulado.relatorio(sid, uid),
        "erros": simulado.erros_do(sid, uid),
    }


@app.get("/simulados")
def rota_historico_simulados(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return simulado.historico(uid, mesa_id=m["id"])


# --------------------------------------------------------------------- stats
@app.get("/stats")
def rota_stats(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return scheduler.desempenho(uid, m["disciplinas"])


@app.get("/erros")
def rota_erros(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    return scheduler.caderno_erros(uid, disciplinas=m["disciplinas"])


@app.get("/meta")
def rota_meta(data: date | None = None, uid: int = Depends(usuario_atual),
              m: dict = Depends(mesa_atual)):
    return scheduler.meta(uid, data, m["id"], m["disciplinas"])


# ------------------------------------------------------------------ perguntar
class PerguntaBody(BaseModel):
    pergunta: str
    # None = comece uma conversa nova. O cliente não precisa de uma chamada
    # extra só pra existir antes de perguntar.
    conversa_id: int | None = None


@app.post("/perguntar")
def rota_perguntar(body: PerguntaBody, uid: int = Depends(usuario_atual),
                   m: dict = Depends(mesa_atual)):
    """
    Um turno do chat livre, agora COM MEMÓRIA (migração 014).

    Sem `conversa_id` o servidor abre uma conversa e devolve o id — o
    cliente não precisa de uma chamada a mais só pra existir, e o fluxo
    normal (abrir o tutor e digitar) não deve custar dois round-trips.

    A gravação acontece nos DOIS lados do turno: a pergunta antes de chamar
    o modelo, a resposta depois. Se o LLM cair no meio, a pergunta do aluno
    fica registrada — reabrir a conversa e não encontrar o que você mesmo
    escreveu é a pior forma de perder confiança no histórico.
    """
    if body.conversa_id is None:
        conv = conversa.criar(uid, m["id"], body.pergunta)
    else:
        conv = conversa.obter(uid, body.conversa_id)
        if not conv:
            raise HTTPException(404, "conversa não encontrada")

    historico = conversa.historico_para_prompt(conv["id"])
    conversa.gravar(conv["id"], "aluno", body.pergunta)
    try:
        r = socratic.explicar(body.pergunta, uid, m["disciplinas"], m, historico)
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível: {e}")

    fontes = [{"id": f["id"], "titulo": f["titulo"], "norma": f.get("norma"),
               "artigo": f.get("artigo")} for f in r["fontes"]]
    conversa.gravar(conv["id"], "tutor", r["resposta"], fontes)
    return {**r, "conversa_id": conv["id"], "titulo": conv["titulo"]}


# ------------------------------------------------------------------ conversas
@app.get("/conversas")
def rota_listar_conversas(uid: int = Depends(usuario_atual)):
    """Sem recorte por mesa, de propósito: a conversa é do ALUNO (mesma
    decisão de `progresso` na 010). Esconder o que ele discutiu porque
    trocou de concurso seria perder material que continua valendo."""
    return conversa.listar(uid)


@app.get("/conversas/{cid}")
def rota_obter_conversa(cid: int, uid: int = Depends(usuario_atual)):
    conv = conversa.obter(uid, cid)
    if not conv:
        raise HTTPException(404, "conversa não encontrada")
    return {**conv, "mensagens": conversa.mensagens(cid)}


@app.delete("/conversas/{cid}")
def rota_apagar_conversa(cid: int, uid: int = Depends(usuario_atual)):
    if not conversa.apagar(uid, cid):
        raise HTTPException(404, "conversa não encontrada")
    return {"ok": True}



class GerarQuestaoBody(BaseModel):
    tema: str | None = None
    quantidade: int = 3
    # None = decidir pela banca da mesa (Cebraspe -> item C/E). Explícito
    # vence, pra quem quer treinar o outro formato de propósito.
    tipo: str | None = None


@app.post("/questoes/gerar")
def rota_gerar_questoes(body: GerarQuestaoBody, uid: int = Depends(usuario_atual),
                        m: dict = Depends(mesa_atual)):
    """
    Cria questão A PARTIR DO ACERVO quando o banco não tem o que servir.

    POST, não GET, e nunca automático dentro de `/fila`: gasta cota de LLM e
    ESCREVE no acervo compartilhado. Efeito desses dois só acontece quando
    alguém pede — um GET que gera questão faria cada refresh da fila queimar
    cota, e é o tipo de custo que aparece na fatura antes de aparecer na tela.

    `tema` ausente = "minha fila está vazia, me dá o que estudar desta mesa";
    com `tema` = "quero questão disto que a gente acabou de conversar".
    """
    try:
        tipo = body.tipo or geracao.tipo_da_banca(m.get("banca"))
        return geracao.sob_demanda(m["disciplinas"], body.tema, body.quantidade, tipo)
    except geracao.SemMaterial as e:
        # 409, não 500: o pedido é válido e o sistema está são — o acervo é
        # que não tem material dessa matéria. A tela precisa distinguir isso
        # de "a IA falhou" pra dizer a coisa certa ao aluno.
        raise HTTPException(409, str(e))
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível: {e}")


# --------------------------------------------------------------------- edital
def _titulo_do_upload(arquivo: UploadFile) -> str | None:
    """"Edital DATAPREV.pdf" -> "Edital DATAPREV". `None` (nome ausente ou
    só espaço) deixa `edital.ingerir()` seguir com o fallback dele."""
    nome = Path(arquivo.filename or "").stem.strip()
    return nome or None


@app.post("/edital")
def rota_ingerir_edital(arquivo: UploadFile = File(...), titulo: str | None = Form(None),
                        orgao: str | None = Form(None), banca: str | None = Form(None),
                        m: dict = Depends(mesa_atual)):
    """O edital entra NA MESA do header (migração 010) — é ele que define
    quais disciplinas ela passa a mostrar, então subir o PDF é o que
    transforma uma mesa recém-criada num recorte de verdade."""
    # edital.ingerir() lê de um caminho em disco (PdfReader) — salva o
    # upload num temporário e apaga depois, sem deixar PDF de aluno no disco.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(arquivo.file.read())
        caminho = Path(tmp.name)
    try:
        # SEM `titulo`, `edital.ingerir()` cai no nome do arquivo — e por
        # este caminho o arquivo é o TEMPORÁRIO, então o edital ia pro banco
        # chamado "tmpcmrpqinr" e era isso que a tela mostrava. O fallback
        # certo aqui é o nome que o usuário enviou; o `stem` de `ingerir()`
        # só faz sentido pra CLI, onde o caminho é um arquivo de verdade.
        return edital.ingerir(m["id"], caminho, titulo=titulo or _titulo_do_upload(arquivo),
                              orgao=orgao, banca=banca)
    finally:
        caminho.unlink(missing_ok=True)


# ----------------------------------------------------- edital: curadoria
# Fluxo em dois tempos, e o intervalo entre eles é o ponto: subir o PDF NÃO
# cria edital nenhum, só um rascunho. Quem transforma extração em dado
# oficial — e portanto em fila SM-2, meta e cobertura — é a pessoa, depois
# de escolher o cargo e ajustar as disciplinas. Ver core/rascunho.py.
def _texto_do_pdf(arquivo: UploadFile) -> str:
    from pypdf import PdfReader
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(arquivo.file.read())
        caminho = Path(tmp.name)
    try:
        reader = PdfReader(str(caminho))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)
    finally:
        caminho.unlink(missing_ok=True)


@app.post("/editais/rascunho")
def rota_criar_rascunho(arquivo: UploadFile = File(...), titulo: str | None = Form(None),
                        uid: int = Depends(usuario_atual)):
    nome = _titulo_do_upload(arquivo)
    try:
        return rascunho.criar(uid, titulo or nome or "edital sem nome",
                              _texto_do_pdf(arquivo), arquivo=arquivo.filename)
    except ErroLLM as e:  # só chega aqui se o fallback foi acionado e caiu
        raise HTTPException(503, f"LLM indisponível ao ler o edital: {e}")


@app.get("/editais/rascunho/{rid}")
def rota_obter_rascunho(rid: int, uid: int = Depends(usuario_atual)):
    r = rascunho.obter(uid, rid)
    if not r:
        raise HTTPException(404, "rascunho não encontrado ou expirado")
    return r


@app.delete("/editais/rascunho/{rid}")
def rota_apagar_rascunho(rid: int, uid: int = Depends(usuario_atual)):
    if not rascunho.apagar(uid, rid):
        raise HTTPException(404, "rascunho não encontrado ou expirado")
    return {"ok": True}


class DisciplinaCurada(BaseModel):
    disciplina: str
    topicos: list[str] = []


class ConfirmarRascunhoBody(BaseModel):
    disciplinas: list[DisciplinaCurada]
    titulo: str | None = None
    data_prova: date | None = None
    orgao: str | None = None
    banca: str | None = None


@app.post("/editais/rascunho/{rid}/confirmar")
def rota_confirmar_rascunho(rid: int, body: ConfirmarRascunhoBody,
                            uid: int = Depends(usuario_atual),
                            m: dict = Depends(mesa_atual)):
    """Grava na MESA do header o que a pessoa curou — não o que o extrator
    achou. A partir daqui isso é edital de verdade e passa a recortar a
    mesa."""
    try:
        return rascunho.confirmar(uid, rid, m["id"],
                                  [d.model_dump() for d in body.disciplinas],
                                  titulo=body.titulo, data_prova=body.data_prova,
                                  orgao=body.orgao, banca=body.banca)
    except rascunho.ErroRascunho as e:
        raise HTTPException(400, str(e))


@app.get("/edital")
def rota_edital_atual(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    ed = edital.mais_recente(m["id"])
    if not ed:
        raise HTTPException(404, "nenhum edital ingerido ainda")
    return {**ed, "cobertura": edital.cobertura(ed["id"], uid)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
