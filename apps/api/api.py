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

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from pydantic import BaseModel

from core import (assunto, auth, conversa, desafio, edital, geracao, material, mesa, pedido,
                  questoes, rascunho, ritmo, scheduler, simulado, socratic)
from core.config import CORS_ORIGINS
from core.llm import ErroLLM

VERSAO = "api-v5"

app = FastAPI(title="Tutor de concursos — API", version=VERSAO)


@app.on_event("startup")
def retomar_indexacao_pendente() -> None:
    """Ao subir, reindexa o material que um restart deixou em `processando`.

    A indexação roda em background NO PROCESSO — não há worker. Antes da 024 um
    restart no meio deixava a linha presa pra sempre e o único jeito de sair era
    o aluno reenviar o PDF, porque os bytes não existiam. Agora estão no banco,
    e a fila passou a ser retomável: é isso que torna viável subir vinte
    apostilas sem apostar que nada reinicia por horas.

    Só ENFILEIRA — não indexa. O trabalhador da fila (`material.enfileirar`) é
    quem trabalha, numa thread daemon própria, então o boot não espera nada: são
    N `put()` numa fila. Antes isto abria thread própria e indexava em série
    aqui, o que funcionava e duplicava o mecanismo.

    Falha aqui NUNCA impede a API de subir: `indexar` já converte erro em
    `status='falha'`, e um banco fora do ar no boot não pode virar app que não
    sobe.
    """
    try:
        n = material.retomar_pendentes()
        if n:
            print(f"[tutor] {n} material(is) pendente(s) de volta na fila de indexação")
    except Exception as e:  # noqa: BLE001 — ver o docstring
        print(f"[tutor] não consegui retomar a indexação: {e}")

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


@app.get("/disciplinas")
def rota_disciplinas_do_acervo(uid: int = Depends(usuario_atual)):
    """O que existe pra escolher como alvo de uma mesa sem edital. Sai do
    ACERVO e não de lista fixa: uma mesa de TI num banco só de Direito
    precisa VER que não há o que escolher, em vez de escolher e receber fila
    vazia sem explicação."""
    # Com `uid`: público MAIS o material do próprio aluno. Sem ele, a rota
    # mostraria a matéria que OUTRO aluno cadastrou (019) — ver o predicado de
    # dono em `mesa.disciplinas_do_acervo`.
    return {"disciplinas": mesa.disciplinas_do_acervo(uid)}


class EditalManualBody(BaseModel):
    """Tudo opcional — cada combinação é um caso real de quem estuda antes do
    edital sair (só matérias, só data prevista, só o nome do concurso). O que o
    core recusa é o vazio completo."""
    titulo: str | None = None
    data_prova: date | None = None
    disciplinas: list[str] = []


@app.post("/edital/manual", status_code=201)
def rota_edital_manual(body: EditalManualBody, uid: int = Depends(usuario_atual),
                       m: dict = Depends(mesa_atual)):
    """Edital declarado à MÃO, sem PDF.

    Um edital declarado à mão É um edital: em vez de uma segunda fonte de data
    (coluna nova na mesa + `scheduler.meta` olhando em dois lugares), cria-se um
    `edital` de verdade e todo o encanamento existente serve — a data, a
    cobertura, o recorte e o /meta. Guardar o prazo fora do edital faria o
    recorte vir de uma fonte e o prazo de outra, que é o defeito que a 010
    evitou.

    SUBSTITUI o edital anterior da mesa, e não soma: duas fontes de recorte é
    exatamente o que 010/017 recusam. `criar_manual` cria antes de apagar, então
    falha no meio nunca deixa a mesa sem edital.

    Limpa `disciplinas_manuais` no fim porque a mesma escolha passa a viver no
    edital: deixar a lista antiga pra trás criaria um alvo fantasma, que
    ressuscitaria se o edital fosse removido depois. Falha aqui é inofensiva —
    o edital vence de qualquer forma — então não derruba a resposta.

    400 e não 422 pro vazio completo: não é o formato do corpo que está errado,
    é o pedido que não diz nada."""
    try:
        novo = edital.criar_manual(m["id"], body.titulo, body.data_prova,
                                   body.disciplinas, nome_da_mesa=m.get("nome"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        mesa.atualizar(uid, m["id"], disciplinas_manuais=[])
    except Exception:
        pass
    return {**novo, "cobertura": edital.cobertura(novo["id"], uid)}


@app.delete("/edital")
def rota_remover_edital(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    """Tira o edital da mesa — ela volta a ser estudo avulso (017).

    DELETE e não PATCH: não é ajuste de campo, é o alvo da mesa mudando de
    origem. E é o único jeito de a escolha manual valer, porque o edital vence
    inteiro quando existe — a alternativa era a tela de alvo manual aceitar um
    trabalho que o servidor ignora.

    404 e não 400 quando não há edital: "esta mesa não tem edital" é o mesmo
    estado que o cliente teria acabado de ler em `GET /edital`, e um 4xx que
    confirma inexistência é mais útil que um sucesso vazio dizendo que apagou
    algo que nunca existiu.

    Autorizado pela MESA: `mesa_atual` já resolveu a mesa filtrando por
    `usuario_id`, então pedir o edital de outra pessoa nem chega aqui."""
    r = edital.remover(m["id"])
    if not r:
        raise HTTPException(404, "esta mesa não tem edital pra remover")
    return {"removido": r}


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
    # `None` preserva; `[]` limpa o alvo. Só entram disciplinas que existem
    # no acervo (validação em core/mesa.atualizar).
    disciplinas: list[str] | None = None
    orgao: str | None = None
    banca: str | None = None
    # `None` PRESERVA (021): um PATCH que só troca o nome não pode religar a
    # biblioteca compartilhada de volta sem ninguém pedir.
    biblioteca_compartilhada: bool | None = None


@app.patch("/mesas/{mid}")
def rota_atualizar_mesa(mid: int, body: AtualizarMesaBody, uid: int = Depends(usuario_atual)):
    try:
        m = mesa.atualizar(uid, mid, body.nome, body.orgao, body.banca,
                           body.disciplinas, body.biblioteca_compartilhada)
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


class PerfilBody(BaseModel):
    horas: str | None = None
    nivel: str | None = None
    turno: str | None = None


@app.put("/me/perfil")
def rota_perfil(body: PerfilBody, uid: int = Depends(usuario_atual)):
    """
    As três respostas do onboarding, que desde o protótipo eram pedidas e
    não tinham onde ser gravadas (migração 015).

    PUT e não PATCH em `/me`: trocar preferência de estudo não é a mesma
    operação que trocar e-mail ou senha, e aquela rota exige a senha atual
    de propósito (token roubado não deve sequestrar a conta). Exigir senha
    pra dizer que você estuda de manhã seria atrito sem ameaça
    correspondente.
    """
    return {"perfil": auth.atualizar_perfil(uid, body.model_dump(exclude_none=True))}


@app.get("/me/perfil")
def rota_obter_perfil(uid: int = Depends(usuario_atual)):
    """Faltava o caminho de VOLTA: só existia gravar, não ler. É o que
    /desafio usa pra calibrar o orçamento padrão pelas horas declaradas
    (core.desafio.minutos_do_perfil) e o que a tela usaria pra mostrar as
    respostas do onboarding já marcadas se a pessoa reabrir a entrevista."""
    return auth.perfil(uid)


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
    """
    Dois produtos diferentes na mesma chamada, de propósito — quem responde
    uma questão precisa dos dois e não deve pagar dois round-trips:

      `sugestao`   — aviso PASSIVO, o banner da fila. Tendência (disciplina
                     fraca, tema que reincide), lida quando o aluno quiser.
      `intervencao` — o pedido de PARAR. Estado de agora (3 erros seguidos),
                     e vem com uma pergunta pronta pro tutor: interromper
                     sem oferecer pra onde ir é só atrapalhar.
    """
    return {
        "sugestao": ritmo.sugestao(uid, m["disciplinas"]),
        "intervencao": ritmo.intervencao(uid, m["disciplinas"]),
    }


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
    # Respondida DENTRO de uma conversa: o resultado entra na linha do tempo
    # dela. É o que faz o tutor considerar a evolução em vez de continuar
    # explicando como se nada tivesse acontecido.
    conversa_id: int | None = None
    # O que a correção apontou como faltando (022) — o cliente devolve o que
    # `POST /questoes/{qid}/responder` acabou de lhe entregar.
    #
    # Vem do cliente porque avaliar e registrar são DUAS chamadas e não há
    # sessão no servidor pra guardar nada entre elas (mesma razão de o JWT ser
    # stateless e de a mesa vir no header). O `veredito` já chega por esse mesmo
    # caminho e com a mesma confiança — quem responde reporta o próprio
    # resultado. O que protege este campo não é a origem: é `conceito_limpo`
    # colapsando quebra de linha, o CHECK de 160 no banco e o rótulo de citação
    # no prompt.
    conceito_faltante: str | None = None


@app.post("/questoes/{qid}/registrar")
def rota_registrar_tentativa(qid: int, body: RegistrarBody, uid: int = Depends(usuario_atual)):
    """Fecha a questão — equivalente ao `fechar()` de `chat._estudar_lista`."""
    if body.veredito not in ("correta", "parcial", "incorreta"):
        raise HTTPException(422, "veredito precisa ser correta/parcial/incorreta")
    try:
        r = scheduler.registrar(uid, qid, body.veredito, body.resposta, body.dicas_usadas,
                                body.segundos, body.simulado_id,
                                conceito_faltante=body.conceito_faltante)
    except ValueError as e:
        raise HTTPException(404, str(e))

    if body.conversa_id is not None and conversa.obter(uid, body.conversa_id):
        q = questoes.obter(qid) or {}
        # O TEXTO do evento é curto e factual de propósito: o modelo não
        # precisa do enunciado inteiro de volta (ele acabou de propô-lo), e
        # sim do veredito e do assunto — é isso que muda a próxima frase.
        # `dicas_usadas` entra porque acertar com três dicas não é a mesma
        # demonstração que acertar de primeira.
        veredito = {"correta": "ACERTOU", "parcial": "acertou em parte",
                    "incorreta": "ERROU"}.get(body.veredito, body.veredito)
        ajuda = f", usando {body.dicas_usadas} dica(s)" if body.dicas_usadas else ""
        conversa.registrar_evento(
            body.conversa_id,
            f"O aluno respondeu a questão sobre \"{q.get('tema', 'o tema')}\" "
            f"e {veredito}{ajuda}. A caixa dele nessa questão agora é {r['caixa']}.")
    return r


# -------------------------------------------------------------------- desafio
@app.get("/desafio")
def rota_desafio(n_reincidentes: int = 3, n_novas: int = 5, n_simulado: int = 5,
                 minutos: int | None = None,
                 uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    """`minutos` é o "só tenho 20 minutos hoje": o desafio encolhe pra caber,
    cortando na ordem que rende mais por minuto (ver desafio.orcamento_blocos).

    A proporção dos blocos (`n_reincidentes/n_novas/n_simulado`) é ajustada
    pelo "nível" do perfil ANTES de montar — só quando os três ainda estão
    no default (`proporcao_por_nivel` não mexe em override explícito, e
    hoje nenhum chamador manda um). `minutos` propositalmente NÃO ganha um
    padrão calibrado por perfil aqui: essa calibração acontece no
    FRONTEND, na primeira carga da tela — fazer aqui não daria pra
    distinguir "ninguém escolheu ainda" de "escolheu 'sessão cheia' de
    propósito", já que os dois chegam como `minutos=None`."""
    perfil = auth.perfil(uid)
    n_reincidentes, n_novas, n_simulado = desafio.proporcao_por_nivel(
        perfil, n_reincidentes, n_novas, n_simulado)
    return desafio.montar(uid, n_reincidentes, n_novas, n_simulado, m["disciplinas"], minutos)


# ------------------------------------------------------------------- simulado
class IniciarSimuladoBody(BaseModel):
    n: int = simulado.N_PADRAO
    minutos: int | None = None
    disciplina: str | None = None
    # Lista pronta (vinda de /desafio, bloco "mini_simulado") pula o sorteio
    # aleatório — mesmo espírito de chat.simulado(questoes=...) aceitar uma
    # lista já escolhida em vez de reamostrar o acervo todo de novo.
    questao_ids: list[int] | None = None
    # Opcional (migração 019) — sem nome, a tela do histórico cai pro
    # rótulo por data, que é ambíguo quando há mais de uma prova no dia.
    nome: str | None = None


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
    sid = simulado.iniciar(uid, len(qs), body.minutos, m["id"], questao_ids=[q["id"] for q in qs],
                           nome=body.nome)
    return {"simulado_id": sid, "questoes": qs}


@app.delete("/simulados/{sid}")
def rota_apagar_simulado(sid: int, uid: int = Depends(usuario_atual)):
    """Tira a prova do histórico (não apaga tentativa/progresso — ver
    core/simulado.apagar). 404 se não existe ou não é sua, mesmo padrão de
    sempre; sem corpo de resposta porque não há nada a devolver depois de
    apagar."""
    if not simulado.apagar(sid, uid):
        raise HTTPException(404, "simulado não encontrado")
    return {"ok": True}


@app.get("/simulados/{sid}/estado")
def rota_estado_simulado(sid: int, uid: int = Depends(usuario_atual)):
    """Reconstrói a prova pra retomar: questões na ordem original, quais já
    têm tentativa (a tela pula pra primeira sem resposta) e o relógio
    acumulado. 404 tanto pra id inexistente quanto pra id de outra conta —
    mesmo motivo de sempre (não confirmar posse de id alheio)."""
    e = simulado.estado(sid, uid)
    if e is None:
        raise HTTPException(404, "simulado não encontrado")
    return e


class ResponderUmaBody(BaseModel):
    questao_id: int
    resposta: str
    segundos_pergunta: int = 0
    segundos_acumulados: int = 0


@app.post("/simulados/{sid}/responder")
def rota_responder_uma(sid: int, body: ResponderUmaBody, uid: int = Depends(usuario_atual)):
    """
    Salva UMA resposta na hora — migração 018. Antes desta rota, o
    simulado inteiro só chegava ao banco numa tacada só no final
    (`finalizar`); conexão cair ou aba fechar no meio perdia 100% do que
    já tinha sido respondido. Sem diálogo nem correção mostrada aqui (isso
    continua só em `finalizar` — ver core/simulado.py), só a GRAVAÇÃO deixou
    de ficar empilhada pro fim.
    """
    try:
        return simulado.responder_uma(sid, uid, body.questao_id, body.resposta,
                                      body.segundos_pergunta, body.segundos_acumulados)
    except ValueError:
        raise HTTPException(404, "simulado não encontrado")
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível ao corrigir: {e}")


class TempoSimuladoBody(BaseModel):
    segundos_acumulados: int


@app.post("/simulados/{sid}/tempo")
def rota_tempo_simulado(sid: int, body: TempoSimuladoBody, uid: int = Depends(usuario_atual)):
    """Só salva o relógio — sem responder questão nenhuma. É o que
    "pausar" e "sair" chamam pra não perder o tempo decorrido quando a
    pessoa não respondeu mais nada nesta visita (ver core.simulado.
    atualizar_tempo)."""
    if not simulado.pertence_a(sid, uid):
        raise HTTPException(404, "simulado não encontrado")
    simulado.atualizar_tempo(sid, uid, body.segundos_acumulados)
    return {"ok": True}


class FinalizarSimuladoBody(BaseModel):
    segundos_total: int = 0


@app.post("/simulados/{sid}/finalizar")
def rota_finalizar_simulado(sid: int, body: FinalizarSimuladoBody, uid: int = Depends(usuario_atual)):
    """Fecha a prova e devolve o relatório. Não recebe respostas — todas já
    foram salvas via `POST /simulados/{sid}/responder`, uma a uma, conforme
    o aluno respondia. Substituiu o antigo `POST /simulados/{sid}/respostas`
    (lote único no final), que ficou incompatível com prova retomável: não
    dá pra "mandar tudo de uma vez" de uma sessão que pode ter sido
    respondida em três pedaços, em três dias diferentes."""
    if not simulado.pertence_a(sid, uid):
        raise HTTPException(404, "simulado não encontrado")
    return {
        "resultado": simulado.finalizar(sid, uid, body.segundos_total),
        "relatorio": simulado.relatorio(sid, uid),
        "erros": simulado.erros_do(sid, uid),
    }


@app.get("/simulados/{sid}/relatorio")
def rota_relatorio_simulado(sid: int, uid: int = Depends(usuario_atual)):
    """Reabre a revisão de uma prova — em andamento ou já fechada, tanto
    faz: os dois só leem `tentativa`, nunca re-finalizam (diferente de
    `POST .../finalizar`, que grava `segundos_total`). É o que o histórico
    usa pro "ver revisão" continuar disponível bem depois da prova ter
    acabado — a resposta e o gabarito de cada questão não deveriam
    desaparecer só porque a tela de resultado foi fechada."""
    if not simulado.pertence_a(sid, uid):
        raise HTTPException(404, "simulado não encontrado")
    return {
        "resultado": simulado.resultado(sid, uid),
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


@app.get("/conceitos")
def rota_conceitos(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    """O que o aluno CONFUNDE, não quais questões ele erra (022).

    Rota separada de `/erros` porque é outra pergunta, não outro formato da
    mesma: `/erros` agrupa por questão e rotula com `questao.tema` (o índice do
    material); esta agrupa pelo que faltou na resposta DELE. Vinte questões
    diferentes podem estar apontando a mesma confusão — e é a confusão que diz o
    que estudar hoje.

    Somar as duas numa rota mudaria o tipo do `/erros`, que já é consumido como
    lista simples; e um cliente que só quer o caderno passaria a pagar esta
    agregação sem pedir.
    """
    return scheduler.conceitos_fracos(uid, m["disciplinas"], limite=12)


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
        r = socratic.explicar(body.pergunta, uid, m["disciplinas"], m, historico,
                              auth.perfil(uid))
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível: {e}")

    fontes = [{"id": f["id"], "titulo": f["titulo"], "norma": f.get("norma"),
               "artigo": f.get("artigo")} for f in r["fontes"]]
    conversa.gravar(conv["id"], "tutor", r["resposta"], fontes)

    # ---- TREINO PEDIDO NA CONVERSA: o app monta as questões, sem botão.
    #
    # É o mesmo `geracao.sob_demanda` que `/questoes/gerar` chama, com o mesmo
    # tema derivado no SERVIDOR — então proveniência (`fonte_chunks`), gravação
    # e entrada na fila SM-2 continuam idênticas. O que sai é o clique.
    #
    # Custa cota, e isso é deliberado: `/questoes/gerar` avisa no docstring que
    # gerar "gasta cota de LLM e ESCREVE no acervo", e por isso nunca acontece
    # dentro de um GET. Aqui continua sendo ação EXPLÍCITA do aluno — pedir
    # questão numa frase é o mesmo ato que clicar no botão era, e nada gera se
    # `pedido.treino` não reconhecer o pedido.
    #
    # Falha aqui NÃO derruba o turno: a resposta do tutor já existe e já está
    # gravada, e trocar uma conversa boa por um 503 porque o gerador tossiu é
    # perder o que funcionou junto com o que não. Vai `questoes: []` e o front
    # mostra o texto — que é o comportamento de hoje.
    questoes: list[dict] = []
    trocou = False
    # `apos_treino` deixa a forma ELÍPTICA valer: depois de "me da 4 questoes",
    # "agora só uma" e "manda cinco" são pedido, e sem o contexto não seriam
    # reconhecidos como nada. Quem sabe se o turno anterior era treino é
    # `pedido.veio_de_treino`, sobre o histórico de ANTES desta fala.
    p = pedido.treino(body.pergunta, apos_treino=pedido.veio_de_treino(historico))
    if p and not p["formal"]:
        # O TEMA VEM DO HISTÓRICO DE ANTES DO PEDIDO, e essa escolha é o conserto
        # de um bug que eu mesmo introduzi aqui. Usar o histórico ATUALIZADO
        # (que já inclui esta fala) faz a própria frase do pedido virar a
        # consulta: `em_foco` viu "me da 3 questoes disso", achou "disso" como
        # palavra de conteúdo, e as três questões saíram sobre apropriação
        # indébita, inquérito policial e usurpação — numa conversa sobre
        # peculato. É a mesma classe do "vamos" que fez nascer o `core/assunto.py`.
        #
        # Pedido de treino NUNCA nomeia o assunto: ele diz "disso", "isso",
        # "nisso". Quem nomeia é a conversa até aqui, e `historico` é justamente
        # ela — capturado antes de `gravar`, algumas linhas acima.
        tema = assunto.em_foco(historico, disciplinas=m["disciplinas"])
        try:
            tipo = p["tipo"] or geracao.tipo_da_banca(m.get("banca"))
            g = geracao.sob_demanda(m["disciplinas"], tema, p["quantidade"], tipo)
            questoes = g["questoes"]
            # A TROCA DE ASSUNTO VIAJA ATÉ A TELA. O acervo não tinha trecho do
            # que a conversa tratava, o gerador caiu pro recorte da mesa (certo)
            # e ninguém avisava (errado): o tutor abria com "vamos treinar isso"
            # e vinham questões de outra matéria. O texto do tutor é escrito
            # ANTES de gerar, então ele não pode saber — quem diz é a tela.
            trocou = bool(g.get("trocou_de_assunto"))
        except (geracao.SemMaterial, ErroLLM):
            questoes = []
        if questoes:
            temas = ", ".join(q["tema"] for q in questoes)
            conversa.registrar_evento(
                conv["id"],
                f"Você propôs {len(questoes)} questão(ões) sobre {temas}. "
                f"O aluno vai respondê-las agora, dentro desta conversa.")

    return {**r, "conversa_id": conv["id"], "titulo": conv["titulo"],
            "questoes": questoes,
            "questoes_fora_do_assunto": trocou,
            # `simulado_pedido` deixa a TELA decidir o que fazer com um pedido de
            # prova cronometrada: ela tem a página do simulado, o servidor não
            # deve abri-la por conta própria no meio de um chat.
            "simulado_pedido": bool(p and p["formal"])}


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
    # Quando a questão nasce DENTRO de uma conversa, o fato entra na linha
    # do tempo dela — senão o tutor propõe o exercício e não fica sabendo
    # que propôs.
    conversa_id: int | None = None


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
    com `conversa_id` = "quero questão disto que a gente acabou de conversar" — e
    QUAL é esse "disto" é o servidor que decide, não o cliente (ver abaixo).
    """
    conv = (conversa.obter(uid, body.conversa_id)
            if body.conversa_id is not None else None)

    # O TEMA VEM DA CONVERSA, E O DONO DESSA REGRA É O SERVIDOR.
    #
    # A tela mandava a última fala do aluno como tema. Numa conversa real, a
    # última fala foi "vamos" — então rodou `buscar("vamos")` e voltaram CP art.
    # 352 (evasão mediante violência) e CF art. 200 (competências do SUS), no
    # meio de uma conversa inteira sobre eficácia das normas constitucionais.
    # Duas questões impecáveis sobre assunto que ninguém pediu.
    #
    # "Sobre o que é esta conversa" é regra, e regra com duas cópias divergem —
    # exatamente o argumento que fez a mesa padrão ser resolvida no servidor e
    # nunca recalculada no front. O cliente pode MANDAR um tema (é o caso de um
    # botão que cobra um tópico específico), mas se o que ele mandar não nomear
    # assunto nenhum, não vale mais que não ter mandado nada.
    tema = body.tema if (body.tema and assunto.diz_assunto(body.tema)) else None
    if tema is None and conv:
        # As disciplinas da mesa vão como palavras vazias: quando o assunto vem
        # herdado do TUTOR, a fala dele pode ser a lista de matérias ("Temos
        # Direito Administrativo, Direito Constitucional..."), e buscar por nome
        # de matéria devolve artigo sorteado DENTRO dela — errado com cara de
        # acerto. `socratic.explicar` já passava isto; este caminho não.
        tema = assunto.em_foco(conversa.historico_para_prompt(conv["id"]),
                               disciplinas=m["disciplinas"])

    try:
        tipo = body.tipo or geracao.tipo_da_banca(m.get("banca"))
        r = geracao.sob_demanda(m["disciplinas"], tema, body.quantidade, tipo)
    except geracao.SemMaterial as e:
        # 409, não 500: o pedido é válido e o sistema está são — o acervo é
        # que não tem material dessa matéria. A tela precisa distinguir isso
        # de "a IA falhou" pra dizer a coisa certa ao aluno.
        raise HTTPException(409, str(e))
    except ErroLLM as e:
        raise HTTPException(503, f"LLM indisponível: {e}")

    if conv and r["questoes"]:
        temas = ", ".join(q["tema"] for q in r["questoes"])
        conversa.registrar_evento(
            conv["id"],
            f"Você propôs {len(r['questoes'])} questão(ões) sobre {temas}. "
            f"O aluno vai respondê-las agora, dentro desta conversa.")
    return r


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
    # Cargo escolhido na curadoria (migração 018). Sem isto a meta mostrava
    # nome de ARQUIVO e nunca de quem era o plano — num edital com 17 cargos
    # isso omite a informação mais importante da tela.
    cargo: str | None = None


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
                                  orgao=body.orgao, banca=body.banca, cargo=body.cargo)
    except rascunho.ErroRascunho as e:
        raise HTTPException(400, str(e))


@app.get("/edital")
def rota_edital_atual(uid: int = Depends(usuario_atual), m: dict = Depends(mesa_atual)):
    ed = edital.mais_recente(m["id"])
    if not ed:
        raise HTTPException(404, "nenhum edital ingerido ainda")
    return {**ed, "cobertura": edital.cobertura(ed["id"], uid)}


class AjusteDisciplinasBody(BaseModel):
    remover: list[str] = []
    adicionar: list[str] = []


@app.patch("/edital/disciplinas")
def rota_ajustar_disciplinas(body: AjusteDisciplinasBody,
                             uid: int = Depends(usuario_atual),
                             m: dict = Depends(mesa_atual)):
    """Tirar ou acrescentar matéria num edital JÁ confirmado.

    A curadoria só acontecia uma vez: depois de confirmar, mudar de ideia
    exigia subir o PDF inteiro de novo. O aluno muda de ideia NO MEIO do
    estudo, que é quando ele finalmente sabe o que está sobrando.

    Escopo pela MESA (não por id de edital vindo do cliente): `mais_recente`
    já filtra por mesa, e a mesa vem do token — mandar um `edital_id` no corpo
    deixaria editar o edital de outra pessoa por tentativa."""
    ed = edital.mais_recente(m["id"])
    if not ed:
        raise HTTPException(404, "nenhum edital ingerido ainda")
    r = edital.ajustar_disciplinas(ed["id"], body.remover, body.adicionar)
    return {**r, "cobertura": edital.cobertura(ed["id"], uid)}


class DataProvaBody(BaseModel):
    data_prova: date


@app.patch("/edital/data-prova")
def rota_corrigir_data_prova(body: DataProvaBody, uid: int = Depends(usuario_atual),
                             m: dict = Depends(mesa_atual)):
    """Aponta uma data futura quando a do edital já passou.

    O edital da PF em corpus/ é de 2025: a prova passou, e `scheduler.meta`
    devolvia "0 dias restantes / 0%" — verdadeiro e inútil. Quem estuda por
    edital antigo (concurso que vai reabrir) é o caso NORMAL de preparação, e
    não tinha saída: reingerir o PDF traria a mesma data velha."""
    ed = edital.mais_recente(m["id"])
    if not ed:
        raise HTTPException(404, "nenhum edital ingerido ainda")
    novo = edital.corrigir_data_prova(ed["id"], body.data_prova)
    return {**novo, "cobertura": edital.cobertura(ed["id"], uid)}


# ------------------------------------------------------------- biblioteca
@app.get("/materiais")
def rota_listar_materiais(uid: int = Depends(usuario_atual)):
    """A biblioteca DESTE aluno. O acervo público não entra: não é dele, ele
    não subiu e não pode apagar."""
    return {"materiais": material.listar(uid)}


@app.get("/materiais/sugestoes")
def rota_sugestoes_material(uid: int = Depends(usuario_atual)):
    """Rótulos que ESTE aluno já usou, pra alimentar o seletor da tela.

    Declarada ANTES de `/materiais/{documento_id}` não por acaso: o FastAPI
    casa rotas na ordem de registro, e uma rota de path param declarada antes
    engoliria "sugestoes" tentando convertê-la em int."""
    return material.sugestoes(uid)


@app.post("/materiais", status_code=201)
async def rota_subir_material(fundo: BackgroundTasks,
                              arquivo: UploadFile = File(...),
                              disciplina: str | None = Form(None),
                              assunto: str | None = Form(None),
                              tipo: str = Form("aula"),
                              titulo: str | None = Form(None),
                              uid: int = Depends(usuario_atual),
                              m: dict = Depends(mesa_atual)):
    """
    Sobe material privado e responde NA HORA, com status `processando`.

    O embedding roda local na CPU (ver "Pilha"): um PDF de 800 trechos leva
    minutos. Fazer isso dentro do request daria timeout no navegador e perderia
    o trabalho já pago em CPU. Então `registrar` grava a linha e valida o que dá
    pra validar de graça (duplicata, PDF protegido, PDF escaneado), e `indexar`
    roda em background gravando o progresso no banco — é de lá que sai o
    "187 de 340" da tela, e é por isso que ele sobrevive a um F5.

    `arquivo.filename` e não o caminho do temporário: essa é a mesma classe de
    erro que já fez um edital ser gravado como "tmpcmrpqinr" no banco.
    """
    dados = await arquivo.read()
    try:
        # `run_in_threadpool` NÃO é enfeite, é o conserto de um travamento MEDIDO.
        # Esta rota é `async def`, e dentro de uma corrotina qualquer chamada
        # bloqueante para o EVENT LOOP INTEIRO — ou seja, todas as outras
        # requisições, de todos os usuários. `registrar` extrai o PDF com pypdf,
        # divide em trechos, calcula hash e escreve no banco: num edital de
        # 1,5 MB isso levou 9,8s.
        #
        # Efeito medido antes do conserto, sondando `/fila` a cada 200ms durante
        # o upload: latência de 289ms (baseline) para 9.295ms, e só 2 sondas
        # completaram em ~10s em vez de ~50. Era o relato de "a API sobrecarrega
        # a aplicação inteira" — e não aparecia no meu teste anterior porque eu
        # tinha usado .txt pequeno, onde a extração é instantânea.
        #
        # As rotas de edital não têm o problema: são `def` (síncronas), e o
        # FastAPI já as roda no pool de threads por conta própria. O perigo é
        # exclusivo de quem escreve `async def` e chama código bloqueante.
        doc = await run_in_threadpool(
            material.registrar, uid, arquivo.filename or "material", dados,
            disciplina=disciplina, tipo=tipo, titulo=titulo,
            assunto=assunto, mesa_id=m["id"])
    except material.ErroMaterial as e:
        raise HTTPException(400, str(e))
    # ENFILEIRA em vez de `add_task(indexar, ..., dados)`. Com um arquivo dava no
    # mesmo; com VINTE, o BackgroundTasks despachava as vinte quase juntas — cada
    # uma com o arquivo inteiro preso na closure, extraindo PDF, abrindo conexão
    # própria e rodando o e5 na CPU ao mesmo tempo. Isso DERRUBOU o servidor no
    # upload de 20 apostilas: caiu depois da primeira, e o F5 voltou numa tela
    # vazia porque não havia mais API respondendo `/materiais`.
    #
    # A fila tem UM trabalhador (o embedding é CPU local: paralelizar nunca ia
    # ser mais rápido, só mais frágil) e carrega o ID, não os bytes — quem
    # trabalha lê o arquivo do banco, o que só é possível por causa da 024.
    material.enfileirar(doc["id"])
    return doc


@app.post("/materiais/{documento_id}/reindexar")
async def rota_reindexar_material(documento_id: int, fundo: BackgroundTasks,
                                  arquivo: UploadFile = File(...),
                                  uid: int = Depends(usuario_atual)):
    """Tentar de novo, reenviando o arquivo.

    Existe porque a indexação roda em background NO PROCESSO do servidor: um
    restart no meio deixa a linha em `processando` pra sempre, e sem retry a
    única saída seria apagar e subir de novo.

    O arquivo VOLTA no request porque o servidor não guarda os bytes — só o
    nome, em `origem`. Guardar o PDF exigiria armazenamento de arquivo, que o
    projeto não tem, e é honesto pedir de novo em vez de fingir que dá.

    `indexar` é idempotente (apaga os trechos do documento antes), então
    reindexar não duplica nada — é o que torna este botão seguro."""
    # Mesmo motivo da rota de subir: consulta de banco numa corrotina bloqueia o
    # event loop. É rápida, mas "rápida" sob um lote de 14 arquivos indexando não
    # é rápida — e o custo de errar aqui é a aplicação inteira parada.
    if not await run_in_threadpool(material.para_reindexar, uid, documento_id):
        raise HTTPException(404, "material não encontrado")
    dados = await arquivo.read()
    # Pela FILA também: vários retries seguidos repetiriam, em escala menor, o
    # que derrubou o servidor no upload de 20. Os bytes já foram gravados pelo
    # `registrar` original, então o trabalhador os lê do banco.
    material.enfileirar(documento_id)
    return {"ok": True, "status": "processando"}


class LinkBody(BaseModel):
    url: str
    disciplina: str | None = None
    assunto: str | None = None
    tipo: str = "aula"


@app.post("/materiais/link", status_code=201)
def rota_indexar_link(body: LinkBody, fundo: BackgroundTasks,
                      uid: int = Depends(usuario_atual),
                      m: dict = Depends(mesa_atual)):
    """Indexa o conteúdo de uma URL pública.

    O download acontece DENTRO do request, ao contrário do embedding: ele é
    rápido, e é onde as falhas que o aluno precisa ver acontecem (404, endereço
    interno, conteúdo que não sei ler). Falhar em background aqui daria uma
    linha vermelha minutos depois em vez de um erro na hora.

    Sobre o risco: `material.baixar` resolve o DNS e recusa IP não-público,
    revalidando a cada redirecionamento. Não é allowlist de domínio — está
    escrito no docstring dele por quê, e o que isso deixa de cobrir."""
    try:
        nome, dados = material.baixar(body.url)
        doc = material.registrar(uid, nome, dados, disciplina=body.disciplina,
                                 tipo=body.tipo, titulo=nome, assunto=body.assunto,
                                 mesa_id=m["id"])
    except material.ErroMaterial as e:
        raise HTTPException(400, str(e))
    material.enfileirar(doc["id"])
    return doc


class ClassificarBody(BaseModel):
    disciplina: str | None = None
    assunto: str | None = None


@app.patch("/materiais/{documento_id}")
def rota_classificar_material(documento_id: int, body: ClassificarBody,
                              tarefas: BackgroundTasks,
                              uid: int = Depends(usuario_atual)):
    """O aluno corrige o palpite do classificador. Passa a valer como 'aluno':
    a lista da tela é que vale, mesmo princípio da curadoria de edital.

    E REINDEXA em background, porque o rótulo agora entra no vetor
    (`material.texto_para_vetor`). Sem isto a correção ficaria pela metade — a
    lista dizendo "Ciências Forenses" e a busca respondendo pelo rótulo velho,
    que é pior que não ter corrigido, porque parece ter funcionado.

    Em background e não aqui: o embedding leva minutos e o PATCH tem que
    responder na hora. O material volta a `processando` e a biblioteca já sabe
    desenhar esse estado. Só acontece se houver arquivo (024) — material
    anterior à migração não tem bytes pra reextrair, e a resposta diz isso em
    `reindexar` pra tela poder avisar."""
    r = material.atualizar(uid, documento_id, body.disciplina, body.assunto)
    if not r:
        raise HTTPException(404, "material não encontrado")
    if r.get("reindexar"):
        arq = material.bytes_do_arquivo(uid, documento_id)
        if arq:
            material.enfileirar(documento_id)
    return r


@app.get("/materiais/{documento_id}/arquivo")
def rota_baixar_material(documento_id: int, uid: int = Depends(usuario_atual)):
    """O arquivo ORIGINAL de volta (024) — pra reler a apostila sem guardá-la no
    computador, que era o pedido.

    404 pra material de outro dono E pra material antigo sem arquivo, no mesmo
    ramo: a autorização mora no WHERE de `material.arquivo`, e distinguir os
    dois casos na resposta contaria a quem chuta um id que ele existe. Mesma
    escolha de `rota_apagar_material` logo abaixo.

    `Content-Disposition: attachment` com o nome de ORIGEM, não o título: o
    título é editável e pode ter virado "Aula 4 — revisar", que não é nome de
    arquivo. `origem` é o que ele subiu, com a extensão que o sistema operacional
    dele entende.

    Devolve `Response` de uma vez, sem streaming: o material do aluno é apostila
    de alguns MB, e `StreamingResponse` sobre `bytea` exigiria manter a conexão
    do banco aberta durante o envio — a conexão é UMA por processo (ver
    `core/db.conexao_isolada`), então segurá-la aqui bloquearia o resto do app
    pelo tempo do download.
    """
    a = material.arquivo(uid, documento_id)
    if not a:
        raise HTTPException(404, "arquivo não encontrado")
    nome = (a["origem"] or a["titulo"] or "material").replace('"', "")
    return Response(
        content=bytes(a["arquivo"]),
        media_type=a["arquivo_tipo"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nome}"',
                 "Content-Length": str(a["arquivo_bytes"] or len(a["arquivo"]))})


@app.delete("/materiais/{documento_id}")
def rota_apagar_material(documento_id: int, uid: int = Depends(usuario_atual)):
    """404 e não 403 pra material de outra pessoa: mesma escolha de
    `mesa.obter` — não confirmar a quem chuta um id que ele existe."""
    if not material.apagar(uid, documento_id):
        raise HTTPException(404, "material não encontrado")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
