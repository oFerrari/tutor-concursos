"""
Integração de autenticação — registrar, login, token, PATCH/DELETE /me.

Cobre o que só aparece com a API HTTP de verdade no meio (não em
`core/auth.py` isolado): o Bearer token via `usuario_atual()`, os códigos
HTTP certos por tipo de falha, e o efeito ponta-a-ponta de trocar senha ou
apagar a conta (login deixa de funcionar, CASCADE some com o resto).
"""
from core import auth, db


def test_registrar_e_logar(client, usuario):
    r = client.post("/auth/login", json={"email": usuario["email"], "senha": usuario["senha"]})
    assert r.status_code == 200
    assert r.json()["token"]


def test_registrar_senha_curta_rejeitada(client):
    r = client.post("/auth/registrar", json={"email": "curta@integracao.local", "senha": "1234567"})
    assert r.status_code == 400
    # não deixou lixo no banco — senão o teste seguinte com o mesmo email quebraria
    assert db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": "curta@integracao.local"}) is None


def test_registrar_email_duplicado_rejeitado(client, usuario):
    r = client.post("/auth/registrar", json={"email": usuario["email"], "senha": "outrasenha123"})
    assert r.status_code == 400


def test_login_senha_errada(client, usuario):
    r = client.post("/auth/login", json={"email": usuario["email"], "senha": "senha-errada-123"})
    assert r.status_code == 401


def test_login_email_inexistente_mesma_mensagem_que_senha_errada(client, usuario):
    """auth.autenticar() usa a MESMA mensagem pros dois casos — email
    inexistente não pode confirmar pra quem tenta adivinhar contas."""
    r_email_errado = client.post("/auth/login", json={"email": "nao-existe-mesmo@x.local", "senha": "qualquer123"})
    r_senha_errada = client.post("/auth/login", json={"email": usuario["email"], "senha": "senha-errada-123"})
    assert r_email_errado.status_code == r_senha_errada.status_code == 401
    assert r_email_errado.json()["detail"] == r_senha_errada.json()["detail"]


def test_rota_protegida_sem_token(client):
    r = client.get("/fila")
    assert r.status_code == 401


def test_rota_protegida_com_token_invalido(client):
    r = client.get("/fila", headers={"Authorization": "Bearer isto-nao-e-um-jwt-valido"})
    assert r.status_code == 401


def test_me_devolve_o_proprio_usuario(client, usuario):
    r = client.get("/me", headers=usuario["headers"])
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["id"] == usuario["id"]
    assert corpo["email"] == usuario["email"]


def test_trocar_senha_exige_senha_atual(client, usuario):
    r = client.patch("/me", json={"senha_nova": "novasenha123"}, headers=usuario["headers"])
    assert r.status_code == 422


def test_trocar_senha_com_senha_atual_errada(client, usuario):
    r = client.patch(
        "/me",
        json={"senha_atual": "senha-errada", "senha_nova": "novasenha123"},
        headers=usuario["headers"],
    )
    assert r.status_code == 400


def test_trocar_senha_de_verdade_login_antigo_para_de_funcionar(client, usuario):
    r = client.patch(
        "/me",
        json={"senha_atual": usuario["senha"], "senha_nova": "novasenha123"},
        headers=usuario["headers"],
    )
    assert r.status_code == 200

    velho = client.post("/auth/login", json={"email": usuario["email"], "senha": usuario["senha"]})
    assert velho.status_code == 401

    novo = client.post("/auth/login", json={"email": usuario["email"], "senha": "novasenha123"})
    assert novo.status_code == 200


def test_trocar_email_hoje_nao_exige_senha_atual(client, usuario):
    """
    Achado testando, não comportamento buscado: CLAUDE.md documenta "PATCH
    /me exige a senha atual, mesmo autenticado por token" como decisão
    geral, mas `rota_atualizar_me` (api.py) só chama essa checagem quando
    `senha_nova` vem no corpo — troca de EMAIL sozinha nunca passa por
    `auth.atualizar_senha`, então um token roubado (sem a senha) já basta
    pra mudar o email da conta hoje. Fixando o comportamento ATUAL aqui
    pra não regredir por acidente; é a área a revisar se isso importar.
    """
    novo_email = f"trocado-{usuario['id']}@integracao.local"
    r = client.patch("/me", json={"email": novo_email}, headers=usuario["headers"])
    assert r.status_code == 200
    assert r.json()["email"] == novo_email

    # limpa direto no banco pro teardown do fixture (que apaga pelo email ORIGINAL) ainda achar a conta
    db.query("UPDATE usuario SET email = %(e)s WHERE id = %(id)s", {"e": usuario["email"], "id": usuario["id"]})


def test_apagar_conta_exige_senha_correta(client, usuario):
    # TestClient.delete() (httpx) não aceita corpo por padrão — precisa de
    # .request("DELETE", ...) explícito pra mandar json com um DELETE.
    r = client.request("DELETE", "/me", json={"senha": "senha-errada"}, headers=usuario["headers"])
    assert r.status_code == 400
    assert db.exec1("SELECT id FROM usuario WHERE id = %(id)s", {"id": usuario["id"]}) is not None


def test_apagar_conta_de_verdade_cascade_limpa_tudo(client, usuario, questao_id):
    """Registra uma tentativa antes de apagar — o CASCADE (migração 009)
    precisa levar tentativa/progresso junto, não só a linha de usuario."""
    client.post(
        f"/questoes/{questao_id}/registrar",
        json={"veredito": "correta", "resposta": "x", "dicas_usadas": 0},
        headers=usuario["headers"],
    )
    assert db.exec1(
        "SELECT 1 FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id},
    )

    r = client.request("DELETE", "/me", json={"senha": usuario["senha"]}, headers=usuario["headers"])
    assert r.status_code == 200

    assert db.exec1("SELECT id FROM usuario WHERE id = %(id)s", {"id": usuario["id"]}) is None
    assert db.exec1(
        "SELECT 1 FROM progresso WHERE usuario_id = %(u)s AND questao_id = %(q)s",
        {"u": usuario["id"], "q": questao_id},
    ) is None

    # token antigo (JWT sem revogação — CLAUDE.md, limitação conhecida) continua
    # criptograficamente válido, mas o usuário não existe mais: 404, não 401.
    r_me = client.get("/me", headers=usuario["headers"])
    assert r_me.status_code == 404


def test_usuario_da_cli_nao_ganha_senha_usavel(client):
    """A conta da CLI (`usuario_da_cli`) é criada sem senha usável de
    propósito — login por API pra essa conta não deve funcionar."""
    uid = auth.usuario_da_cli("teste-cli-descartavel@integracao.local")
    try:
        r = client.post(
            "/auth/login",
            json={"email": "teste-cli-descartavel@integracao.local", "senha": "qualquercoisa"},
        )
        assert r.status_code == 401
    finally:
        db.query("DELETE FROM usuario WHERE id = %(id)s", {"id": uid})
