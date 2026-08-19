"""
`POST /edital` — a borda HTTP da ingestão, onde mora o defeito que
`tests/test_edital.py` (função pura, sem upload) não tinha como pegar.

O PDF é gerado em memória com o pypdf que já é dependência: o que se testa
aqui é o CAMINHO do upload (nome do arquivo, mesa de destino), não a
extração de texto — essa tem fixture de edital real no outro arquivo.
"""
import io

import pytest
from pypdf import PdfWriter

from core import db

VERSAO = "test-edital-api-v1"


@pytest.fixture
def pdf_em_branco() -> bytes:
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def test_titulo_vem_do_arquivo_enviado_nunca_do_temporario(client, usuario, pdf_em_branco):
    """
    O DEFEITO QUE ESTE TESTE TRAVA: a rota grava o upload num
    NamedTemporaryFile e passava esse caminho pra `edital.ingerir()`, que
    sem `titulo` cai no nome do arquivo. Resultado no banco (e na tela):
    um edital chamado "tmpcmrpqinr". O nome do temporário do servidor não
    pode vazar pra dentro do dado do usuário.
    """
    r = client.post(
        "/edital",
        files={"arquivo": ("Edital DATAPREV.pdf", pdf_em_branco, "application/pdf")},
        headers=usuario["headers"],
    )
    assert r.status_code == 200, r.text

    titulo = db.exec1("SELECT titulo FROM edital WHERE id = %(e)s",
                      {"e": r.json()["edital_id"]})["titulo"]
    assert titulo == "Edital DATAPREV"
    assert not titulo.startswith("tmp")


def test_titulo_explicito_vence_o_nome_do_arquivo(client, usuario, pdf_em_branco):
    r = client.post(
        "/edital",
        files={"arquivo": ("Edital DATAPREV.pdf", pdf_em_branco, "application/pdf")},
        data={"titulo": "PF Agente 2026"},
        headers=usuario["headers"],
    )
    assert r.status_code == 200, r.text
    assert db.exec1("SELECT titulo FROM edital WHERE id = %(e)s",
                    {"e": r.json()["edital_id"]})["titulo"] == "PF Agente 2026"


def test_edital_entra_na_mesa_do_header(client, usuario, pdf_em_branco):
    mid = client.post("/mesas", json={"nome": "Mesa do edital"},
                      headers=usuario["headers"]).json()["id"]
    r = client.post(
        "/edital",
        files={"arquivo": ("qualquer.pdf", pdf_em_branco, "application/pdf")},
        headers={**usuario["headers"], "X-Mesa-Id": str(mid)},
    )
    assert r.status_code == 200, r.text
    assert db.exec1("SELECT mesa_id FROM edital WHERE id = %(e)s",
                    {"e": r.json()["edital_id"]})["mesa_id"] == mid
