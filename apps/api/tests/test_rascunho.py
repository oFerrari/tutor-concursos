"""
Curadoria de edital: extrair pra rascunho, escolher o cargo, confirmar.

O TESTE QUE DEFINE A FEATURE é `test_confirmar_persiste_so_o_cargo_escolhido`:
o edital tem 13 perfis, a pessoa presta um, e só o dele pode virar fila
SM-2. Somar cargo é pior que não ler — gera revisão espaçada de matéria
que nunca vai cair na prova dela.
"""
import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from core import db, edital, mesa, rascunho

VERSAO = "test-rascunho-v1"

FGV = (Path(__file__).parent / "fixtures" / "edital_fgv_dataprev.txt").read_text(encoding="utf-8")
AOCP = (Path(__file__).parent / "fixtures" / "edital_aocp_pcba.txt").read_text(encoding="utf-8")


@pytest.fixture
def pdf_em_branco() -> bytes:
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


# ------------------------------------------------------ parser por cargo
def test_estrutura_separa_comum_de_especifico_do_cargo():
    e = edital.extrair_estrutura(AOCP)
    comuns = {d["disciplina"] for d in e["comuns"]}
    assert "Língua Portuguesa" in comuns and "Medicina Legal" in comuns

    nomes = [c["nome"] for c in e["cargos"]]
    assert nomes == ["Delegado De Polícia Civil", "Investigador De Polícia Civil"]

    delegado = {d["disciplina"] for d in e["cargos"][0]["disciplinas"]}
    investigador = {d["disciplina"] for d in e["cargos"][1]["disciplinas"]}
    assert "Direito Processual Penal" in delegado
    assert "Noções De Contabilidade" in investigador
    # o que é de um NÃO vaza pro outro — é o ponto inteiro da feature
    assert "Noções De Contabilidade" not in delegado
    assert "Direito Processual Penal" not in investigador


def test_perfil_sem_subcabecalho_vira_disciplina_com_o_nome_do_cargo():
    """PERFIL 1 da FGV lista tópicos direto. Sem tratar isso, eles cairiam
    no cargo anterior — matéria de um concurso dentro do plano de outro."""
    e = edital.extrair_estrutura(FGV)
    perfil1 = next(c for c in e["cargos"] if c["nome"] == "Análise De Negócios De Ti")
    assert [d["disciplina"] for d in perfil1["disciplinas"]] == ["Análise De Negócios De Ti"]


def test_achatar_por_cargo_junta_comuns_mais_um_cargo_so():
    e = edital.extrair_estrutura(FGV)
    tudo = {t["disciplina"] for t in edital.achatar(e)}
    um = {t["disciplina"] for t in edital.achatar(e, cargo="Contabilidade")}
    assert "Contabilidade Tributária" in um
    assert "Redes De Computadores" in tudo and "Redes De Computadores" not in um
    assert "Língua Portuguesa" in um, "Módulo I é comum a todos os cargos"


# ------------------------------------------------------------- rascunho
def test_criar_nao_toca_em_nada_oficial(usuario):
    antes = db.exec1("SELECT count(*) AS n FROM edital")["n"]
    r = rascunho.criar(usuario["id"], "Edital FGV", FGV, arquivo="fgv.pdf")

    assert r["origem"] == "parser"
    assert len(r["estrutura"]["cargos"]) == 4
    assert db.exec1("SELECT count(*) AS n FROM edital")["n"] == antes, \
        "subir PDF não pode criar edital — só a confirmação cria"


def test_rascunho_de_outro_usuario_nao_existe(usuario, outro_usuario):
    r = rascunho.criar(outro_usuario["id"], "Edital alheio", AOCP)
    assert rascunho.obter(usuario["id"], r["id"]) is None
    assert rascunho.apagar(usuario["id"], r["id"]) is False
    assert rascunho.obter(outro_usuario["id"], r["id"]) is not None


def test_rascunho_expirado_nao_volta(usuario):
    r = rascunho.criar(usuario["id"], "Edital velho", AOCP)
    db.query("UPDATE edital_rascunho SET expira_em = now() - interval '1 hour' "
             "WHERE id = %(id)s", {"id": r["id"]})
    assert rascunho.obter(usuario["id"], r["id"]) is None


def test_confirmar_persiste_so_o_cargo_escolhido(usuario):
    """
    O TESTE DA FEATURE. O edital tem 4 cargos; a pessoa presta um. Depois
    de confirmar, a mesa só pode recortar as disciplinas dela — as dos
    outros três não existem pra esta mesa.
    """
    m = mesa.criar(usuario["id"], "Dataprev — Contabilidade")
    r = rascunho.criar(usuario["id"], "Edital Dataprev", FGV)
    e = r["estrutura"]

    escolhidas = list(e["comuns"]) + next(
        c["disciplinas"] for c in e["cargos"] if c["nome"] == "Contabilidade")
    res = rascunho.confirmar(usuario["id"], r["id"], m["id"], escolhidas)

    assert res["topicos"] > 0
    disc = mesa.disciplinas(m["id"])
    assert "Contabilidade Tributária" in disc
    assert "Redes De Computadores" not in disc, "cargo de outro perfil vazou pra mesa"
    assert "Língua Portuguesa" in disc, "o comum vale pra todo cargo"
    assert rascunho.obter(usuario["id"], r["id"]) is None, "rascunho tem que morrer"


def test_confirmar_respeita_a_edicao_manual(usuario):
    """A lista que vale é a da TELA, não a do extrator: se a pessoa apagou
    uma matéria e acrescentou outra, é a versão dela que vira edital."""
    m = mesa.criar(usuario["id"], "Mesa curada")
    r = rascunho.criar(usuario["id"], "Edital", AOCP)

    rascunho.confirmar(usuario["id"], r["id"], m["id"], [
        {"disciplina": "Direito Penal", "topicos": ["1 Só este tópico."]},
        {"disciplina": "Arquivologia", "topicos": []},   # acrescentada na mão
    ])

    disc = mesa.disciplinas(m["id"])
    assert set(disc) == {"Direito Penal", "Arquivologia"}
    # disciplina sem tópico precisa virar linha em `topico`, senão a matéria
    # escolhida não entraria no recorte da mesa — seria escolher e não valer
    assert db.exec1("SELECT texto FROM topico t JOIN edital e ON e.id = t.edital_id "
                    "WHERE e.mesa_id = %(m)s AND t.disciplina = 'Arquivologia'",
                    {"m": m["id"]})["texto"] == "Arquivologia"


def test_confirmar_sem_disciplina_nenhuma_e_erro(usuario):
    m = mesa.criar(usuario["id"], "Mesa vazia")
    r = rascunho.criar(usuario["id"], "Edital", AOCP)
    with pytest.raises(rascunho.ErroRascunho):
        rascunho.confirmar(usuario["id"], r["id"], m["id"], [])


# ------------------------------------------------------------ rotas HTTP
def test_fluxo_http_completo(client, usuario, pdf_em_branco, llm_falso, monkeypatch):
    """PDF em branco = layout que o parser não entende, então o fallback do
    LLM entra. O dublê devolve estrutura válida: o que se testa aqui é o
    CAMINHO (rascunho -> curadoria -> edital), não a leitura do PDF."""
    llm_falso.retorno = ('{"comuns": [{"disciplina": "Português", "topicos": ["1 Crase."]}],'
                         ' "cargos": [{"nome": "Agente", "disciplinas": ['
                         '{"disciplina": "Informática", "topicos": ["1 Redes."]}]}]}')

    r = client.post("/editais/rascunho",
                    files={"arquivo": ("Edital PF.pdf", pdf_em_branco, "application/pdf")},
                    headers=usuario["headers"])
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["titulo"] == "Edital PF"
    assert draft["origem"] == "llm"
    assert [c["nome"] for c in draft["estrutura"]["cargos"]] == ["Agente"]

    assert client.get(f"/editais/rascunho/{draft['id']}",
                      headers=usuario["headers"]).status_code == 200

    r = client.post(f"/editais/rascunho/{draft['id']}/confirmar",
                    json={"disciplinas": [{"disciplina": "Informática", "topicos": ["1 Redes."]}]},
                    headers=usuario["headers"])
    assert r.status_code == 200, r.text

    assert client.get("/edital", headers=usuario["headers"]).json()["titulo"] == "Edital PF"
    assert client.get("/mesa", headers=usuario["headers"]).json()["disciplinas"] == ["Informática"]
    # confirmado = rascunho morto
    assert client.get(f"/editais/rascunho/{draft['id']}",
                      headers=usuario["headers"]).status_code == 404
