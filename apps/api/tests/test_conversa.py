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
