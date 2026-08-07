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
"""
import tempfile
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from core import auth, desafio, edital, questoes, ritmo, scheduler, simulado, socratic
from core.llm import ErroLLM

VERSAO = "api-v1"

app = FastAPI(title="Tutor de concursos — API", version=VERSAO)


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


def usuario_atual(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "token ausente — envie 'Authorization: Bearer <token>'")
    try:
        return auth.usuario_id_do_token(authorization.split(" ", 1)[1])
    except auth.ErroAuth as e:
        raise HTTPException(401, str(e))


# ----------------------------------------------------------------- fila/estudo
@app.get("/fila")
def rota_fila(uid: int = Depends(usuario_atual)):
    return scheduler.fila(uid)


@app.get("/carga")
def rota_carga(uid: int = Depends(usuario_atual)):
    return scheduler.carga_hoje(uid)


@app.get("/sugestao")
def rota_sugestao(uid: int = Depends(usuario_atual)):
    return {"sugestao": ritmo.sugestao(uid)}


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
        return socratic.avaliar(q["enunciado"], q["gabarito"], body.resposta, body.nivel,
                                body.historico)
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
                 uid: int = Depends(usuario_atual)):
    return desafio.montar(uid, n_reincidentes, n_novas, n_simulado)


# ------------------------------------------------------------------- simulado
class IniciarSimuladoBody(BaseModel):
    n: int = simulado.N_PADRAO
    minutos: int | None = None
    disciplina: str | None = None


@app.post("/simulados")
def rota_iniciar_simulado(body: IniciarSimuladoBody, uid: int = Depends(usuario_atual)):
    qs = simulado.selecionar(body.n, body.disciplina)
    if not qs:
        raise HTTPException(404, "nenhuma questão no acervo (ou disciplina inexistente)")
    sid = simulado.iniciar(uid, len(qs), body.minutos)
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
def rota_historico_simulados(uid: int = Depends(usuario_atual)):
    return simulado.historico(uid)


# --------------------------------------------------------------------- stats
@app.get("/stats")
def rota_stats(uid: int = Depends(usuario_atual)):
    return scheduler.desempenho(uid)


@app.get("/erros")
def rota_erros(uid: int = Depends(usuario_atual)):
    return scheduler.caderno_erros(uid)


@app.get("/meta")
def rota_meta(data: date | None = None, uid: int = Depends(usuario_atual)):
    return scheduler.meta(uid, data)


# ------------------------------------------------------------------ perguntar
class PerguntaBody(BaseModel):
    pergunta: str


@app.post("/perguntar")
def rota_perguntar(body: PerguntaBody, uid: int = Depends(usuario_atual)):
    try:
        return socratic.explicar(body.pergunta)
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível: {e}")


# --------------------------------------------------------------------- edital
@app.post("/edital")
def rota_ingerir_edital(arquivo: UploadFile = File(...), titulo: str | None = Form(None),
                        orgao: str | None = Form(None), banca: str | None = Form(None),
                        uid: int = Depends(usuario_atual)):
    # edital.ingerir() lê de um caminho em disco (PdfReader) — salva o
    # upload num temporário e apaga depois, sem deixar PDF de aluno no disco.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(arquivo.file.read())
        caminho = Path(tmp.name)
    try:
        return edital.ingerir(uid, caminho, titulo=titulo, orgao=orgao, banca=banca)
    finally:
        caminho.unlink(missing_ok=True)


@app.get("/edital")
def rota_edital_atual(uid: int = Depends(usuario_atual)):
    ed = edital.mais_recente(uid)
    if not ed:
        raise HTTPException(404, "nenhum edital ingerido ainda")
    return {**ed, "cobertura": edital.cobertura(ed["id"], uid)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
