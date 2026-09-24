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
import json

import pytest
from fastapi.testclient import TestClient

from api import app
from core import db, llm

VERSAO = "conftest-v3"


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


DISCIPLINAS_SINTETICAS = ("Disciplina Sintética Alfa", "Disciplina Sintética Beta")
QUESTOES_SINTETICAS_POR_DISCIPLINA = 3


@pytest.fixture
def acervo():
    """Garante questão PÚBLICA em pelo menos duas disciplinas.

    O acervo comum pode estar vazio de propósito — o dono zerou o banco em
    22/09/2026 para usar a ferramenta como aluno novo — e 52 testes passaram a
    pular calados, entre eles os de fila, simulado e isolamento entre alunos.
    Quando o acervo real não basta, semeia questões sintéticas; elas são
    `INSERT INTO questao ... RETURNING id` por `db.query`, então
    `_sem_lixo_no_acervo` as apaga no fim do teste como apaga qualquer outra.

    Acervo real suficiente fica como está: teste que rodava contra ele segue
    rodando contra ele.

    Cada disciplina ganha também um `documento` público: é dele, e não da
    questão, que `mesa.disciplinas_do_acervo` tira o que o aluno pode escolher
    como alvo manual. O documento sai aqui mesmo, no fim."""
    linhas = db.query("""SELECT disciplina, count(*) AS n FROM questao
                          WHERE usuario_id IS NULL GROUP BY disciplina""")
    if len(linhas) >= 2 and all(l["n"] >= 2 for l in linhas[:2]):
        yield
        return
    documentos = []
    for disciplina in DISCIPLINAS_SINTETICAS:
        doc = db.exec1("""INSERT INTO documento (titulo, tipo, disciplina)
                          VALUES (%(t)s, 'aula', %(d)s) RETURNING id""",
                       {"t": f"Material sintético de {disciplina}", "d": disciplina})["id"]
        documentos.append(doc)
        for i in range(1, QUESTOES_SINTETICAS_POR_DISCIPLINA + 1):
            db.query("""INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito)
                        VALUES (%(doc)s, %(d)s, %(t)s, %(e)s, %(g)s) RETURNING id""",
                     {"doc": doc, "d": disciplina, "t": f"Tema sintético {i}",
                      "e": f"Enunciado sintético {i} de {disciplina}?",
                      "g": f"Gabarito sintético {i}."})
    yield
    db.query("DELETE FROM documento WHERE id = ANY(%(ids)s)", {"ids": documentos})


@pytest.fixture
def questao_id(acervo):
    """Uma questão PÚBLICA que já exista pra registrar tentativa contra ela —
    gerar questão nova custaria cota de LLM (`socratic.gerar_questoes`).

    PÚBLICA, explicitamente: desde a 026 a tabela também guarda questão com
    dono (gerada da apostila de um aluno), e "uma questão qualquer" passou a
    poder ser a de outra pessoa."""
    return db.exec1("SELECT id FROM questao WHERE usuario_id IS NULL ORDER BY id LIMIT 1")["id"]


@pytest.fixture
def duas_questoes(acervo):
    return [r["id"] for r in db.query(
        "SELECT id FROM questao WHERE usuario_id IS NULL ORDER BY id LIMIT 2")]


class _LLMFalso(llm.LLM):
    """Dublê do LLM real — devolve exatamente o texto configurado em
    `.retorno`, sem rede, sem custo. `LLM.gerar_json()` (herdado da classe
    real) chama `self.gerar()` e faz o parse; setar `.retorno` com um JSON
    válido cobre esse caminho também, sem precisar reimplementar nada."""

    def __init__(self):
        self.retorno = "Resposta do tutor."
        self.excecao: Exception | None = None
        self.chamadas: list[dict] = []

    def gerar(self, prompt, sistema="", json_mode=False, max_tokens=1200, schema=None,
              temperatura=None):
        self.chamadas.append({"prompt": prompt, "sistema": sistema, "json_mode": json_mode})
        if self.excecao:
            raise self.excecao
        # Testes de conversa configuram prosa; adapte apenas o novo envelope
        # do tutor. JSON explícito continua cru para testar falhas de contrato.
        if (schema and "fontes_usadas" in schema.get("properties", {})
                and not self.retorno.lstrip().startswith(("{", "["))):
            return json.dumps({"resposta": self.retorno, "fontes_usadas": []})
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
            "SELECT origem, arquivo FROM documento WHERE id = %(i)s",
            {"i": documento_id})
        if linha and linha["arquivo"] is not None:
            material.indexar(documento_id, linha["origem"] or "material",
                             bytes(linha["arquivo"]))
        elif linha:
            material.reindexar_rotulo(documento_id)

    monkeypatch.setattr(material, "enfileirar", agora)


# Tabelas cujas linhas nascem PÚBLICAS quando a fonte é pública — e que por
# isso o CASCADE do usuário descartável não alcança. `contexto` entra junto
# porque a série de Certo/Errado grava o texto-base antes dos itens.
TABELAS_SEM_DONO_NO_TESTE = ("questao", "contexto")


@pytest.fixture(autouse=True)
def _sem_lixo_no_acervo(monkeypatch):
    """Todo `INSERT INTO questao/contexto` feito por um teste é apagado no fim dele.

    O dono da questão sai do CHUNK (026, `geracao.salvar`), nunca de parâmetro —
    e é certo que seja assim em produção. O efeito colateral nos testes: gerar a
    partir do CP público cria questão PÚBLICA, que sobrevive ao DELETE do usuário
    descartável. Medido em 22/09/2026: 101 das 377 questões públicas eram lixo de
    três testes ("Enunciado?", "assertiva 0", 16 cópias de "instrumento
    contundente" presas ao CP art. 1º), e uma delas caiu no simulado de um aluno.

    Por que rastrear o que ESTE processo inseriu, e não apagar "tudo que é
    público e mais novo que o início do teste": a API de desenvolvimento roda em
    outro processo sobre o mesmo banco, e o aluno pode estar gerando questão
    pública pelo chat enquanto a suíte roda. Apagar por data levaria a dele.

    Intercepta `db.query` e não uma função de `geracao`: qualquer caminho que
    grave questão — o de hoje ou um teste escrito amanhã — passa por aqui sem
    ninguém lembrar de listá-lo. `db.exec1` chama `query` pelo nome do módulo,
    então é coberto também.
    """
    criadas: dict[str, list[int]] = {t: [] for t in TABELAS_SEM_DONO_NO_TESTE}
    original = db.query

    def query_rastreada(sql, params=None):
        linhas = original(sql, params)
        inicio = " ".join(sql.split()[:3]).lower()
        for tabela in criadas:
            if inicio == f"insert into {tabela}":
                criadas[tabela].extend(l["id"] for l in linhas if "id" in l)
        return linhas

    monkeypatch.setattr(db, "query", query_rastreada)
    yield
    # Questão primeiro: ela aponta para o contexto. tentativa/progresso caem
    # pelo CASCADE da 001/008.
    for tabela in ("questao", "contexto"):
        if criadas[tabela]:
            original(f"DELETE FROM {tabela} WHERE id = ANY(%(ids)s)",
                     {"ids": criadas[tabela]})
