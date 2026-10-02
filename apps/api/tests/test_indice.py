"""Assuntos do material e de cada trecho (036, `core/indice.py`). Material e assuntos inventados."""
import json
import re

import pytest

from core import db, geracao, indice, leitura, llm, material, socratic

VERSAO = "test-indice-v1"

# Assunto A ensinado em cima, B no meio, e A RETOMADO embaixo (numa questão).
PARTES = ([f"A perícia sintética é o exame técnico número {i}, com laudo, perito e prazo próprios. " * 5
           for i in range(4)] +
          [f"A cadeia sintética de custódia registra o vestígio número {i} do início ao descarte. " * 5
           for i in range(4)] +
          ["Questão comentada: sobre a perícia sintética, julgue o item. O laudo é obrigatório. "
           "Comentário: certo, a perícia sintética exige laudo. " * 3])


def test_versalete_e_sumario_sao_lidos():
    assert indice.juntar_versalete("F\nORMAS\n N\nOMINAIS DO\n V\nERBO As formas nominais são três.") == \
        "FORMAS NOMINAIS DO VERBO\nAs formas nominais são três."
    chunks = [{"texto": "Capa\n\nÍndice\n.......1) Noções iniciais de Sintética 3\n........"
                        "2) Perícia sintética 5\n.......3) Lista de Questões - FGV 9\n", "pagina": 2},
              {"texto": "texto", "pagina": 3}]
    assert indice.sumario(chunks) == [("Noções iniciais de Sintética", 3), ("Perícia sintética", 5),
                                      ("Lista de Questões - FGV", 9)]


def test_reserva_marca_pela_secao_e_pela_expressao():
    lista = [{"nome": "Perícia sintética", "pagina_inicio": 1, "pagina_fim": 4, "papel": "ensino", "origem": "sumario"},
             {"nome": "Cadeia sintética de custódia", "pagina_inicio": 5, "pagina_fim": 8, "papel": "ensino", "origem": "sumario"},
             {"nome": "Lista de questões", "pagina_inicio": 9, "pagina_fim": 9, "papel": "questoes", "origem": "sumario"}]
    chunks = [{"id": 1, "pagina": 2, "texto": "o perito faz o exame"},
              {"id": 2, "pagina": 6, "texto": "registro do vestígio"},
              {"id": 3, "pagina": 9, "texto": "Questão: a perícia sintética exige laudo?"}]
    m = indice.marcar_reserva(lista, chunks)
    assert m[1] == [("Perícia sintética", "ensino", "secao")]
    assert m[2] == [("Cadeia sintética de custódia", "ensino", "secao")]
    assert m[3] == [("Perícia sintética", "questao", "expressao")], "o assunto retomado na questão"


def _material(client, usuario):
    r = client.post("/materiais", files={"arquivo": ("aula.txt", "\n\n".join(PARTES).encode(), "text/plain")},
                    data={"disciplina": "Ciências Sintéticas", "tipo": "aula", "assunto": "Perícias"},
                    headers=usuario["headers"])
    assert r.status_code == 201 and material.esperar_fila(30)
    return r.json()["id"]


def _modelo_que_le(llm_falso):
    def gerar(prompt, *a, **k):
        if "COMEÇO DA APOSTILA" in prompt:
            return json.dumps({"assuntos": [
                {"nome": "Perícia sintética", "pagina_inicio": 1, "pagina_fim": 1, "papel": "ensino"},
                {"nome": "Cadeia sintética de custódia", "pagina_inicio": 1, "pagina_fim": 1, "papel": "ensino"}]})
        trechos = []
        for n, texto in re.findall(r"\[(\d+)\] \([^)]*\)\n(.*?)(?=\n\n\[\d+\] \(|\Z)", prompt, re.S):
            nomes = (["Perícia sintética"] if "perícia" in texto.lower() else []) + \
                    (["Cadeia sintética de custódia"] if "custódia" in texto.lower() else [])
            trechos.append({"n": int(n), "assuntos": nomes,
                            "papel": "questao" if "Questão" in texto else "ensino"})
        return json.dumps({"trechos": trechos})
    llm_falso.gerar = gerar


def test_o_modelo_marca_o_assunto_onde_quer_que_ele_apareca(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 1000)
    _modelo_que_le(llm_falso)
    doc = _material(client, usuario)

    assert indice.indexar_assuntos(doc) == "pronto"
    pericia = db.exec1("SELECT id FROM material_assunto WHERE documento_id=%(d)s AND nome='Perícia sintética'", {"d": doc})["id"]
    ordens = [r["ordem"] for r in db.query("SELECT ordem FROM chunk WHERE id = ANY(%(i)s) ORDER BY ordem",
                                            {"i": indice.trechos_do_assunto(pericia)})]
    ultimo = db.exec1("SELECT max(ordem) AS m FROM chunk WHERE documento_id=%(d)s", {"d": doc})["m"]
    assert ordens[0] == 0 and ordens[-1] == ultimo, "em cima E retomada embaixo, na questão"
    assert indice.trechos_do_assunto(pericia, "questao"), "a questão do fim ficou com o assunto"


def test_sem_modelo_o_indice_sai_pela_reserva(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 1000)
    llm_falso.excecao = llm.ErroLLM("sem cota")
    doc = _material(client, usuario)
    assert indice.indexar_assuntos(doc) == "reserva"
    assert db.exec1("SELECT assuntos_status AS s FROM documento WHERE id=%(d)s", {"d": doc})["s"] == "reserva"
    assert doc in indice.pendentes(), "reserva é refeita com o modelo depois"


def test_questoes_de_x_saem_dos_trechos_marcados_com_x(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 1000)
    _modelo_que_le(llm_falso)
    doc = _material(client, usuario)
    indice.indexar_assuntos(doc)
    cadeia = db.exec1("SELECT id FROM material_assunto WHERE documento_id=%(d)s AND nome LIKE 'Cadeia%%'", {"d": doc})["id"]
    ids, _ = geracao.escolher(None, "me dá 2 questões de cadeia sintética de custódia", 2, usuario["id"],
                              assunto_nomeado=True)
    assert ids and set(ids) <= set(indice.trechos_do_assunto(cadeia))


def test_resumao_de_x_comeca_no_x_e_a_fonte_tem_o_assunto_do_trecho(client, usuario, llm_falso, monkeypatch):
    monkeypatch.setattr(indice, "ORCAMENTO_DIA", 1000)
    _modelo_que_le(llm_falso)
    doc = _material(client, usuario)
    indice.indexar_assuntos(doc)
    primeiro_da_cadeia = db.exec1("""SELECT min(c.ordem) AS o FROM chunk c JOIN chunk_assunto ca ON ca.chunk_id=c.id
                                     JOIN material_assunto a ON a.id=ca.assunto_id
                                     WHERE c.documento_id=%(d)s AND a.nome LIKE 'Cadeia%%' AND ca.papel='ensino'""",
                                  {"d": doc})["o"]
    assert leitura._ordem_do_assunto(doc, "me traga o resumão de cadeia sintética de custódia", usuario["id"]) == primeiro_da_cadeia
    # trecho só da cadeia (o de fronteira trata dos dois, e o rótulo é o 1º na ordem da apostila)
    trecho = db.exec1("""SELECT ca.chunk_id AS id FROM chunk_assunto ca JOIN chunk c ON c.id = ca.chunk_id
                         WHERE c.documento_id = %(d)s GROUP BY ca.chunk_id
                        HAVING count(*) = 1 AND bool_and(ca.assunto_id IN
                               (SELECT id FROM material_assunto WHERE documento_id=%(d)s AND nome LIKE 'Cadeia%%'))
                         LIMIT 1""", {"d": doc})
    rotulado = socratic._com_assunto_do_trecho([{"id": trecho["id"], "assunto": "Perícias"}])
    assert rotulado[0]["assunto"] == "Cadeia sintética de custódia"
