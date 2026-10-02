"""Resumo, jurisprudência e simulado se organizam por DESCRIÇÃO (30/09/2026)."""
import json

from core import db, material

VERSAO = "test-descricao-v1"


def _subir(client, usuario, nome, tipo, texto=None, assunto=None):
    dados = {"tipo": tipo, **({"assunto": assunto} if assunto else {})}
    corpo = (texto or f"Conteúdo sintético de {nome}. " * 40).encode()
    r = client.post("/materiais", files={"arquivo": (nome, corpo, "text/plain")}, data=dados,
                    headers=usuario["headers"])
    assert r.status_code == 201, r.text
    assert material.esperar_fila(30)
    return db.exec1("SELECT id, assunto, disciplina FROM documento WHERE id=%(d)s", {"d": r.json()["id"]})


def test_nome_que_diz_algo_vira_descricao_sem_modelo(client, usuario, llm_falso):
    llm_falso.retorno = "isto não é json"
    d = _subir(client, usuario, "Resumo de Direito Sintético.txt", "resumo")
    assert d["assunto"] == "Resumo de Direito Sintético"
    codigo = _subir(client, usuario, "curso-392635-aula-04-374d.txt", "resumo")
    assert codigo["assunto"] is None, "nome-código não vira descrição"


def test_o_modelo_da_a_descricao_e_ela_nao_vai_a_busca(client, usuario, llm_falso):
    llm_falso.retorno = json.dumps({"disciplina": "Direito Sintético", "assunto": "Informativos Sintéticos"})
    d = _subir(client, usuario, "inf1100x.txt", "jurisprudencia")
    assert d["assunto"] == "Informativos Sintéticos"
    rotulos = {r["rotulo"] for r in db.query("SELECT rotulo FROM chunk WHERE documento_id=%(d)s", {"d": d["id"]})}
    assert rotulos == {None}, "material de consulta não leva rótulo à busca"


def test_sugestoes_separam_descricao_de_assunto_de_aula(client, usuario, llm_falso):
    llm_falso.retorno = "isto não é json"
    _subir(client, usuario, "x.txt", "simulado", assunto="Simulados Sintéticos")
    _subir(client, usuario, "y.txt", "aula", assunto="Peculato Sintético")
    s = client.get("/materiais/sugestoes", headers=usuario["headers"]).json()
    assert s["descricoes_por_tipo"]["simulado"] == ["Simulados Sintéticos"]
    assert "Simulados Sintéticos" not in s["assuntos"] and "Peculato Sintético" in s["assuntos"]


def test_nome_util():
    assert material.nome_util("(Comentado) 3º Simulado PCPR - Projeto Caveira.pdf")
    assert material.nome_util("Informativo STF 1100.pdf") == "Informativo STF 1100"
    for codigo in ("del3689compilado.txt", "scan_001.pdf", "aula_04.pdf", "curso-392635-aula-04-374d.pdf"):
        assert material.nome_util(codigo) is None, codigo


def test_nome_corrompido_por_codificacao_e_consertado():
    assert material.sem_mojibake("(Comentado) 3Âº Simulado PCPR") == "(Comentado) 3º Simulado PCPR"
    assert material.sem_mojibake("Ação já é normal") == "Ação já é normal"


def test_nome_decomposto_tambem_e_consertado():
    import unicodedata
    assert material.sem_mojibake(unicodedata.normalize("NFD", "3Âº Simulado")) == "3º Simulado"
