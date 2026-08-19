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

    # O token antigo continua CRIPTOGRAFICAMENTE válido — assinado por nós, no
    # prazo — e aponta pra ninguém. Este assert dizia 404 e foi trocado por 401
    # (auth-v4), com motivo:
    #
    # o 404 só acontecia AQUI, porque `/me` por acaso busca o usuário. Toda
    # outra rota estourava 500 na primeira escrita que referenciasse
    # `usuario_id` — relatado em uso, com traceback: `ForeignKeyViolation: Key
    # (usuario_id)=(252) is not present in table "usuario"`, vindo de
    # `mesa.padrao` -> `criar`. Ou seja, o contrato antigo era 404 numa rota e
    # 500 em todas as outras, e NENHUM dos dois leva a pessoa ao login: o front
    # reage a 401 fazendo `sair()` + redirect.
    #
    # 401 unifica os dois casos na porta certa — e é a diferença entre "a conta
    # sumiu, entre de novo" e uma aplicação travada que só destrava limpando o
    # localStorage na mão.
    r_me = client.get("/me", headers=usuario["headers"])
    assert r_me.status_code == 401


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


# --------------------------------------------- token de conta que não existe

def test_token_de_conta_apagada_da_401_e_nao_500(client, usuario):
    """Relatado em uso, com traceback: conta descartável apagada, navegador
    seguiu com o token dela, e a primeira rota que tentou gravar morreu em
    `ForeignKeyViolation: Key (usuario_id)=(252) is not present in table
    "usuario"` — 500 e traceback de psycopg no log.

    O token era válido: assinado por nós, no prazo, apontando pra ninguém.

    501 ou 500 aqui não é detalhe de estética. O front reage a 401 fazendo
    `sair()` + redirect pro login; com 500 ele não tem esse sinal, e a pessoa
    fica presa numa aplicação quebrada, só saindo se limpar o localStorage na
    mão. Erro de autenticação sai pela porta de autenticação."""
    # A conta existe: a rota responde.
    assert client.get("/mesa", headers=usuario["headers"]).status_code == 200

    db.query("DELETE FROM usuario WHERE id = %(id)s", {"id": usuario["id"]})

    # Mesmo token, agora órfão. `/mesa` passa por `mesa.padrao`, que CRIA a mesa
    # se não existir — é o caminho exato que estourou a FK.
    r = client.get("/mesa", headers=usuario["headers"])
    assert r.status_code == 401, r.text
    # E a mensagem não confirma que a conta existia: quem roubou um token não
    # deve descobrir por aqui se acertou o id.
    assert "conta" not in r.json()["detail"].lower() or "não encontrada" in r.json()["detail"]


def test_rota_que_escreve_tambem_recusa_token_orfao(client, usuario):
    """Não é só a leitura: qualquer rota que grave referenciando `usuario_id`
    quebraria na FK. A guarda mora em `usuario_id_do_token`, que é o gargalo por
    onde TODA rota autenticada passa — e não em cada `except` de FK espalhado."""
    db.query("DELETE FROM usuario WHERE id = %(id)s", {"id": usuario["id"]})
    for metodo, rota, corpo in [
        ("post", "/mesas", {"nome": "PF Agente"}),
        ("post", "/perguntar", {"pergunta": "art. 312"}),
        ("put", "/me/perfil", {"horas": "2h"}),
    ]:
        r = getattr(client, metodo)(rota, json=corpo, headers=usuario["headers"])
        assert r.status_code == 401, f"{metodo.upper()} {rota} devolveu {r.status_code}"
