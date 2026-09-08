"""
Conversa persistida (migração 014) — o tutor lembrando do turno anterior.

O que estes testes travam:
  · o histórico CHEGA ao modelo (é o defeito que existia: `/perguntar`
    mandava só a pergunta atual, e "qualquer um" virava "qualquer um de
    quê?");
  · a pergunta do aluno fica gravada mesmo se o LLM cair depois — reabrir a
    conversa e não achar o que você escreveu é a pior forma de perder
    confiança no histórico;
  · conversa de outro usuário devolve 404, nunca conteúdo;
  · apagar a MESA não apaga a conversa (SET NULL, mesma política do
    simulado na 010): o que foi discutido continua valendo noutro concurso.
"""
from core import conversa, db

VERSAO = "test-conversa-v1"


def _resposta_falsa(fake, texto="resposta do tutor"):
    fake.retorno = texto
    return fake


def test_historico_chega_ao_modelo(client, usuario, llm_falso):
    """O coração da 014. Sem isso o modelo recebe cada mensagem como se
    fosse a primeira da vida."""
    _resposta_falsa(llm_falso)
    r1 = client.post("/perguntar", json={"pergunta": "o que é peculato?"},
                     headers=usuario["headers"]).json()
    cid = r1["conversa_id"]

    llm_falso.chamadas.clear()
    client.post("/perguntar", json={"pergunta": "qualquer um", "conversa_id": cid},
                headers=usuario["headers"])

    prompt = llm_falso.chamadas[-1]["prompt"]
    assert "Conversa até aqui" in prompt
    assert "o que é peculato?" in prompt      # a pergunta do turno 1
    assert "resposta do tutor" in prompt      # e a resposta dele


def test_primeira_pergunta_abre_conversa_sem_chamada_extra(client, usuario, llm_falso):
    """Sem `conversa_id` o servidor cria e devolve o id — o fluxo normal
    (abrir o tutor e digitar) não deve custar dois round-trips."""
    _resposta_falsa(llm_falso)
    r = client.post("/perguntar", json={"pergunta": "art. 312"},
                    headers=usuario["headers"]).json()
    assert isinstance(r["conversa_id"], int)
    assert r["titulo"] == "art. 312"

    lista = client.get("/conversas", headers=usuario["headers"]).json()
    assert [c["id"] for c in lista] == [r["conversa_id"]]
    assert lista[0]["mensagens"] == 2         # a do aluno e a do tutor


def test_pergunta_fica_gravada_mesmo_se_o_llm_cair(client, usuario, llm_falso):
    """A gravação acontece antes da chamada. Perder a própria pergunta
    porque o modelo caiu ensina o aluno a não confiar no histórico."""
    from core import llm as llm_mod
    _resposta_falsa(llm_falso)
    r = client.post("/perguntar", json={"pergunta": "primeira"},
                    headers=usuario["headers"]).json()
    cid = r["conversa_id"]

    llm_falso.excecao = llm_mod.ErroLLM("caiu")
    assert client.post("/perguntar", json={"pergunta": "segunda", "conversa_id": cid},
                       headers=usuario["headers"]).status_code == 503
    llm_falso.excecao = None

    msgs = client.get(f"/conversas/{cid}", headers=usuario["headers"]).json()["mensagens"]
    assert [m["texto"] for m in msgs] == ["primeira", "resposta do tutor", "segunda"]


def test_conversa_de_outro_usuario_da_404(client, usuario, outro_usuario, llm_falso):
    """404 e não 403: não confirma pra quem chuta um id que ele existe e só
    não é dele — mesmo espírito de `mesa.obter` e `simulado.pertence_a`."""
    _resposta_falsa(llm_falso)
    cid = client.post("/perguntar", json={"pergunta": "minha"},
                      headers=usuario["headers"]).json()["conversa_id"]

    assert client.get(f"/conversas/{cid}", headers=outro_usuario["headers"]).status_code == 404
    assert client.post("/perguntar", json={"pergunta": "x", "conversa_id": cid},
                       headers=outro_usuario["headers"]).status_code == 404
    assert client.get("/conversas", headers=outro_usuario["headers"]).json() == []


def test_apagar_a_mesa_nao_apaga_a_conversa(client, usuario, llm_falso):
    """SET NULL, não CASCADE: a conversa é do ALUNO e etiquetada pela mesa.
    O que você discutiu sobre o art. 312 continua valendo no outro
    concurso."""
    _resposta_falsa(llm_falso)
    m = client.post("/mesas", json={"nome": "Mesa da conversa"},
                    headers=usuario["headers"]).json()
    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}
    cid = client.post("/perguntar", json={"pergunta": "art. 312"}, headers=cab).json()["conversa_id"]

    client.delete(f"/mesas/{m['id']}", headers=usuario["headers"])

    conv = client.get(f"/conversas/{cid}", headers=usuario["headers"])
    assert conv.status_code == 200
    assert conv.json()["mesa_id"] is None


def test_janela_limita_o_historico_enviado(usuario):
    """Teto existe pra o material de lei não ser empurrado pra fora da
    janela do modelo por uma conversa longa: melhor esquecer o turno 1 do
    que esquecer o art. 37."""
    c = conversa.criar(usuario["id"], None, "início")
    for i in range(20):
        conversa.gravar(c["id"], "aluno" if i % 2 == 0 else "tutor", f"msg {i}")

    hist = conversa.historico_para_prompt(c["id"])
    assert len(hist) == conversa.JANELA
    assert hist[-1]["texto"] == "msg 19"          # os ÚLTIMOS
    assert hist == sorted(hist, key=lambda m: int(m["texto"].split()[1]))  # em ordem


def test_titulo_sai_da_primeira_pergunta_sem_llm(usuario, llm_falso):
    """Gastar uma chamada pra resumir "o que diz o art. 312?" em três
    palavras é pagar por enfeite."""
    longa = "quero entender " + "muito " * 40 + "sobre peculato"
    c = conversa.criar(usuario["id"], None, longa)
    assert len(c["titulo"]) <= conversa.MAX_TITULO + 1
    assert c["titulo"].endswith("…")
    assert llm_falso.chamadas == []


# ------------------------------------ evolução dentro da conversa (016)
def test_resposta_a_questao_entra_na_linha_do_tempo(client, usuario, llm_falso):
    """
    O ponto da 016: o que o aluno FAZ vale mais que o que ele diz. Dizer
    "não entendi" é relato; errar a questão é evidência — e antes disso o
    tutor propunha três itens, o aluno errava os três, e a mensagem seguinte
    continuava explicando como se nada tivesse acontecido.
    """
    _resposta_falsa(llm_falso)
    cid = client.post("/perguntar", json={"pergunta": "peculato"},
                      headers=usuario["headers"]).json()["conversa_id"]
    q = db.exec1("SELECT id, tema FROM questao LIMIT 1")
    if not q:
        return

    client.post(f"/questoes/{q['id']}/registrar",
                json={"veredito": "incorreta", "resposta": "chutei", "dicas_usadas": 2,
                      "segundos": 40, "conversa_id": cid},
                headers=usuario["headers"])

    msgs = client.get(f"/conversas/{cid}", headers=usuario["headers"]).json()["mensagens"]
    evento = [m for m in msgs if m["autor"] == "evento"]
    assert len(evento) == 1
    assert "ERROU" in evento[0]["texto"]
    assert q["tema"] in evento[0]["texto"]
    # dicas entram: acertar com 3 dicas não é a mesma demonstração que
    # acertar de primeira.
    assert "2 dica" in evento[0]["texto"]


def test_evento_chega_ao_prompt_rotulado_como_fato(client, usuario, llm_falso):
    """Evento NÃO pode entrar como fala: "(o aluno errou)" dito por "Você"
    faria o modelo tratar aquilo como coisa que ele mesmo afirmou antes."""
    _resposta_falsa(llm_falso)
    cid = client.post("/perguntar", json={"pergunta": "peculato"},
                      headers=usuario["headers"]).json()["conversa_id"]
    q = db.exec1("SELECT id FROM questao LIMIT 1")
    if not q:
        return
    client.post(f"/questoes/{q['id']}/registrar",
                json={"veredito": "incorreta", "resposta": "x", "dicas_usadas": 0,
                      "segundos": 10, "conversa_id": cid},
                headers=usuario["headers"])

    llm_falso.chamadas.clear()
    client.post("/perguntar", json={"pergunta": "explica de novo", "conversa_id": cid},
                headers=usuario["headers"])
    prompt = llm_falso.chamadas[-1]["prompt"]
    assert "[fato da sessão]" in prompt
    assert "ERROU" in prompt


def test_registrar_sem_conversa_nao_cria_evento(client, usuario, llm_falso):
    """Fila, /questao e desafio não têm conversa — e não devem inventar uma.
    O evento existe pra conversa em curso, não pra toda tentativa."""
    _resposta_falsa(llm_falso)
    cid = client.post("/perguntar", json={"pergunta": "oi"},
                      headers=usuario["headers"]).json()["conversa_id"]
    q = db.exec1("SELECT id FROM questao LIMIT 1")
    if not q:
        return
    client.post(f"/questoes/{q['id']}/registrar",
                json={"veredito": "correta", "resposta": "x", "dicas_usadas": 0,
                      "segundos": 10},
                headers=usuario["headers"])
    msgs = client.get(f"/conversas/{cid}", headers=usuario["headers"]).json()["mensagens"]
    assert not [m for m in msgs if m["autor"] == "evento"]


def test_conversa_de_outro_usuario_nao_recebe_evento(client, usuario, outro_usuario, llm_falso):
    """`conversa_id` vem do cliente: sem checar posse, daria pra escrever na
    linha do tempo de qualquer um. `conversa.obter` já é escopado."""
    _resposta_falsa(llm_falso)
    cid = client.post("/perguntar", json={"pergunta": "minha"},
                      headers=usuario["headers"]).json()["conversa_id"]
    q = db.exec1("SELECT id FROM questao LIMIT 1")
    if not q:
        return
    client.post(f"/questoes/{q['id']}/registrar",
                json={"veredito": "correta", "resposta": "x", "dicas_usadas": 0,
                      "segundos": 10, "conversa_id": cid},
                headers=outro_usuario["headers"])
    msgs = client.get(f"/conversas/{cid}", headers=usuario["headers"]).json()["mensagens"]
    assert not [m for m in msgs if m["autor"] == "evento"]


def test_desfazer_ultimo_turno_devolve_a_pergunta_e_limpa_o_historico(client, usuario,
                                                                      llm_falso):
    """PARAR e EDITAR são o mesmo problema visto de dois lados.

    A pergunta é gravada ANTES de o modelo ser chamado (014), de propósito: quem
    reabre a conversa tem de achar o que escreveu, mesmo se o LLM caiu no meio.
    O preço disso é que interromper deixa pergunta sem resposta, e editar
    deixaria a versão errada no histórico junto da certa — e o prompt do turno
    seguinte leria as duas como parte da conversa.

    Devolver a PERGUNTA é o que faz "editar" ser editar em vez de digitar tudo
    de novo. E o par inteiro sai: pergunta + resposta (+ evento, quando o turno
    propôs questões, senão o prompt afirmaria uma proposta que não existe mais).
    """
    r = client.post("/perguntar", headers=usuario["headers"],
                    json={"pergunta": "me explica peculato"})
    assert r.status_code == 200, r.text
    cid = r.json()["conversa_id"]
    assert len(conversa.mensagens(cid)) == 2

    d = client.post(f"/conversas/{cid}/desfazer", headers=usuario["headers"])
    assert d.status_code == 200, d.text
    assert d.json()["pergunta"] == "me explica peculato"
    assert conversa.mensagens(cid) == []

    # Nada a desfazer é 404, não sucesso vazio: a tela precisa distinguir
    # "desfiz" de "não havia nada", pra não limpar o campo por engano.
    assert client.post(f"/conversas/{cid}/desfazer",
                       headers=usuario["headers"]).status_code == 404


def test_desfazer_turno_de_outro_dono_da_404(client, usuario, outro_usuario, llm_falso):
    """404 e não 403: mesma escolha do resto da biblioteca — não confirmar a
    quem chuta um id que ele existe."""
    r = client.post("/perguntar", headers=usuario["headers"], json={"pergunta": "bom dia"})
    cid = r.json()["conversa_id"]
    assert client.post(f"/conversas/{cid}/desfazer",
                       headers=outro_usuario["headers"]).status_code == 404
    # E o turno do dono continua lá.
    assert len(conversa.mensagens(cid)) == 2


def test_questao_escrita_pelo_modelo_e_apagada_da_resposta():
    """O tutor NÃO escreve questão — e isso é garantido em CÓDIGO, não no prompt.

    Foram TRÊS tentativas de proibir por instrução (v40 mandando usar o botão,
    v41 dizendo que o app monta, v42 enumerando "nada de Questão 1:, nada de
    alternativas a), b), c)"), e o log seguinte mostrou o modelo escrevendo
    exatamente isso. `limpar_citacoes` já existia pelo mesmo motivo: o que dá
    pra garantir em código não se confia ao prompt.

    O dano é concreto, não estético: questão na prosa não tem campo de resposta,
    não tem `fonte_chunks`, não entra na fila SM-2 e não conta no progresso. O
    aluno lê duas questões que parecem iguais às de verdade e não tem onde
    responder — foi relatado assim: "não trouxe o campo pra eu anexar a
    resposta individualmente".

    O falso positivo que a primeira versão tinha está no teste: com DUAS
    alternativas como gatilho, ela apagava "O item a) do edital trata de
    princípios e o b) de atos". Item de prova brasileira tem quatro ou cinco;
    prosa cita uma ou duas.
    """
    from core import socratic

    com_questoes = (
        "Vamos treinar isso; as questões estão logo abaixo.\n\n"
        "[Questão 1: Assinale a alternativa que indica um princípio expresso no art. 37: "
        "a) Autotutela; b) Impessoalidade; c) Supremacia; d) Indisponibilidade.]\n\n"
        "[Questão 2: Sobre os implícitos, assinale a correta: a) A Supremacia é expressa "
        "no LIMPE; b) A Indisponibilidade permite abrir mão; c) A Supremacia justifica a "
        "desapropriação; d) A Autotutela é o único.]")
    limpo, quantas = socratic.limpar_questoes(com_questoes)
    assert quantas == 2
    assert "Questão 1" not in limpo and "Autotutela;" not in limpo
    assert limpo.startswith("Vamos treinar isso")

    # Resposta normal não é tocada.
    normal = "Peculato é crime de funcionário público [cp, art. 312]. Já viu a diferença?"
    assert socratic.limpar_questoes(normal) == (normal, 0)

    # Prosa que menciona letras não é questão.
    prosa = "O item a) do edital trata de princípios e o b) de atos."
    assert socratic.limpar_questoes(prosa) == (prosa, 0)
