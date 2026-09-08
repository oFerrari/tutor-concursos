"""
Fixtures compartilhadas dos testes de integração (API + banco real).

Por que contra o Postgres de verdade, não mock: `diagnostico.py`,
`simular.py` e `avaliar_retrieval.py` já seguem esse princípio pro resto do
projeto — o que quebra em produção aqui é SQL e regra de negócio, não
lógica isolável em memória. Mockar `core.db` testaria a mock, não o projeto.

Usuário SEMPRE descartável (`usuario_da_cli`/CLI_USUARIO_EMAIL nunca
entram aqui) — mesma lição de "Armadilhas de método" no CLAUDE.md: testar
contra a conta real corrompeu progresso de verdade uma vez. Cada teste cria
sua própria conta via `/auth/registrar` e apaga no teardown; ON DELETE
CASCADE (migração 009) limpa tentativa/progresso/erro_caderno/simulado de
uma vez, sem lógica de limpeza escrita na mão.

O LLM nunca é chamado de verdade nestes testes (ver fixture `llm_falso`):
gastar cota do Gemini a cada rodada de pytest é o mesmo tipo de custo que
já mordeu o projeto (ver "gerar.py girava pra sempre" no CLAUDE.md) — só que
aqui rodaria em CADA execução da suíte, não uma vez só.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from api import app
from core import db, llm

VERSAO = "conftest-v1"


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _registrar_usuario_descartavel(client: TestClient) -> dict:
    email = f"teste-{uuid.uuid4().hex[:12]}@integracao.local"
    senha = "senha-de-teste-123"
    r = client.post("/auth/registrar", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    corpo = r.json()
    return {
        "id": corpo["usuario"]["id"],
        "email": email,
        "senha": senha,
        "token": corpo["token"],
        "headers": {"Authorization": f"Bearer {corpo['token']}"},
    }


@pytest.fixture
def usuario(client):
    u = _registrar_usuario_descartavel(client)
    yield u
    db.query("DELETE FROM usuario WHERE id = %(id)s", {"id": u["id"]})


@pytest.fixture
def outro_usuario(client):
    """Segunda conta descartável — só existe pros testes de isolamento
    multiusuário (duas pessoas, mesma questão do acervo compartilhado)."""
    u = _registrar_usuario_descartavel(client)
    yield u
    db.query("DELETE FROM usuario WHERE id = %(id)s", {"id": u["id"]})


@pytest.fixture
def questao_id():
    """Reaproveita uma questão real do acervo compartilhado — gerar questão
    nova custa cota de LLM (core/socratic.py `gerar_questoes`), e os testes
    de scheduler/multiusuário não precisam de uma questão NOVA, só de uma
    que já exista pra registrar tentativa contra ela.

    PÚBLICA, explicitamente: desde a 026 a tabela também guarda questão com
    dono (gerada da apostila de um aluno), e "uma questão qualquer" passou a
    poder ser a de outra pessoa."""
    r = db.exec1("SELECT id FROM questao WHERE usuario_id IS NULL ORDER BY id LIMIT 1")
    if not r:
        pytest.skip("acervo vazio — ingira e gere ao menos uma questão antes de rodar isto")
    return r["id"]


@pytest.fixture
def duas_questoes():
    linhas = db.query("SELECT id FROM questao WHERE usuario_id IS NULL ORDER BY id LIMIT 2")
    if len(linhas) < 2:
        pytest.skip("acervo precisa de pelo menos 2 questões")
    return [r["id"] for r in linhas]


class _LLMFalso(llm.LLM):
    """Dublê do LLM real — devolve exatamente o texto configurado em
    `.retorno`, sem rede, sem custo. `LLM.gerar_json()` (herdado da classe
    real) chama `self.gerar()` e faz o parse; setar `.retorno` com um JSON
    válido cobre esse caminho também, sem precisar reimplementar nada."""

    def __init__(self):
        self.retorno = ""
        self.excecao: Exception | None = None
        self.chamadas: list[dict] = []

    def gerar(self, prompt, sistema="", json_mode=False, max_tokens=1200, schema=None,
              temperatura=None):
        self.chamadas.append({"prompt": prompt, "sistema": sistema, "json_mode": json_mode})
        if self.excecao:
            raise self.excecao
        return self.retorno


@pytest.fixture
def llm_falso(monkeypatch):
    fake = _LLMFalso()
    monkeypatch.setattr(llm, "obter", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _indexar_sincrono(monkeypatch):
    """Nos TESTES, indexar material é síncrono.

    Em produção a indexação passa por uma fila com UM trabalhador — foi isso
    que impediu o upload de 20 apostilas de derrubar o servidor. Mas essa fila
    é GLOBAL ao processo, e num `pytest` isso significa que os uploads de todos
    os arquivos de teste se empilham no mesmo trabalhador: o teste que esperava
    a fila drenar passou a estourar 240s por causa da fila de OUTROS testes, e
    passava sozinho e falhava na suíte inteira.

    Acoplar testes por um recurso global é pior que perder a cobertura da fila
    aqui — e a fila não fica sem prova: a concorrência dela foi medida à mão
    (20 uploads em 3,3s, uma thread, `GET /fila` em 111ms durante a indexação),
    e o que os testes precisam afirmar é o RESULTADO da indexação, que é o
    mesmo nos dois caminhos.

    `enfileirar` continua sendo a porta única: quem trocar de mecanismo mexe num
    lugar só, e este duplê acompanha.
    """
    from core import material

    def agora(documento_id: int) -> None:
        linha = db.exec1(
            "SELECT origem, arquivo FROM documento WHERE id = %(i)s AND arquivo IS NOT NULL",
            {"i": documento_id})
        if linha:
            material.indexar(documento_id, linha["origem"] or "material",
                             bytes(linha["arquivo"]))

    monkeypatch.setattr(material, "enfileirar", agora)
