"""Cobertura do edital por subitem (035). Disciplinas, tópicos e material inventados."""
import json
import re

from core import cobertura, db, material

VERSAO = "test-cobertura-v1"

TOPICO = ("3.1. Instituto Sintético: conceito, divisões e importância; perícia sintética; "
          "cadeia sintética de custódia; criminologia sintética.")


def test_topico_vira_subitens_e_generico_herda_o_cabecalho():
    assert cobertura.cabecalho(TOPICO) == "Instituto Sintético"
    subs = cobertura.subitens(TOPICO)
    assert subs == ["conceito, divisões e importância", "perícia sintética",
                    "cadeia sintética de custódia", "criminologia sintética"]
    assert cobertura.atomos(subs[0], "Instituto Sintético") == ["Instituto Sintético"]
    assert cobertura.atomos("direitos individuais e coletivos", "x") == ["direitos individuais e coletivos"]
    assert cobertura.subitens("4.1 Estatística descritiva.") == ["Estatística descritiva"]


def test_paginas_em_faixa():
    assert cobertura.paginas([9, 3, 4, 5, None, 4]) == "3–5, 9"


def _mesa_com_material(client, usuario):
    m = client.post("/mesas", json={"nome": "Concurso sintético"}, headers=usuario["headers"]).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s, 'Edital sintético') "
                   "RETURNING id", {"m": m["id"]})["id"]
    db.query("INSERT INTO topico (edital_id, disciplina, ordem, texto) VALUES "
             "(%(e)s, 'Ciências Sintéticas', 1, %(t)s)", {"e": eid, "t": TOPICO})
    paragrafos = ([f"A perícia sintética é o exame técnico número {i}, feito por perito, com laudo "
                   f"e prazo próprios no caso concreto. " * 4 for i in range(20)] +
                  [f"A cadeia sintética de custódia registra o vestígio número {i} do início ao "
                   f"descarte, sem lacuna. " * 4 for i in range(3)])
    corpo = "\n\n".join(paragrafos).encode()
    r = client.post("/materiais", files={"arquivo": ("aula-00.txt", corpo, "text/plain")},
                    data={"disciplina": "Ciências Sintéticas", "tipo": "aula",
                          "assunto": "Perícias sintéticas"},
                    headers={**usuario["headers"], "X-Mesa-Id": str(m["id"])})
    assert r.status_code == 201, r.text
    assert material.esperar_fila(30)
    return m["id"]


def test_modelo_confirma_e_o_mapa_diz_onde_esta_e_o_que_falta(client, usuario, llm_falso):
    mid = _mesa_com_material(client, usuario)

    def confirma_o_que_tem_o_termo(prompt, *a, **k):
        # o dublê "confirma" os candidatos cujo texto tem o termo do subitem
        subs = {}
        for bloco in prompt.split("SUBITEM ")[1:]:
            n = int(bloco.split(":")[0])
            termo = bloco.split(":", 1)[1].split("\n")[0].strip().split()[0].lower()
            ids = [int(i) for i, texto in re.findall(r"\[T(\d+)\]([^\n]*)", bloco)
                   if termo[:6] in texto.lower()]
            subs[n] = ids
        todos = {n: [int(i) for i in re.findall(r"\[T(\d+)\]", b)]
                 for n, b in ((int(b.split(":")[0]), b) for b in prompt.split("SUBITEM ")[1:])}
        return json.dumps({"vereditos": [{"subitem": n, "trecho": t, "ensina": t in subs[n]}
                                         for n, ts in todos.items() for t in ts]})
    llm_falso.gerar = lambda prompt, *a, **k: confirma_o_que_tem_o_termo(prompt)

    r = cobertura.mapear(mid, usuario["id"])

    assert r["chamadas"] == 1, "uma chamada por item do edital"
    [item] = cobertura.mapa_do_edital(mid, usuario["id"])
    estados = {s["texto"]: s["estado"] for s in item["subitens"]}
    assert estados["perícia sintética"] == "coberto"
    assert estados["criminologia sintética"] == "sem_material"
    pericia = next(s for s in item["subitens"] if s["texto"] == "perícia sintética")
    assert pericia["materiais"][0]["assunto"] == "Perícias sintéticas"
    assert "SEM MATERIAL" in cobertura.resumo_para_prompt(mid, usuario["id"], "Ciências Sintéticas")


def test_sem_modelo_fica_o_texto_e_volta_a_ser_pendente(client, usuario, llm_falso):
    from core import llm
    mid = _mesa_com_material(client, usuario)
    llm_falso.excecao = llm.ErroLLM("sem cota")

    cobertura.mapear(mid, usuario["id"])

    [item] = cobertura.mapa_do_edital(mid, usuario["id"])
    assert {s["metodo"] for s in item["subitens"]} == {"texto"}
    assert next(s for s in item["subitens"] if s["texto"] == "criminologia sintética")["estado"] == "sem_material"
    # Só texto é refeito com o modelo, mas não na hora: a cada 6 h no máximo.
    assert "Ciências Sintéticas" not in cobertura.pendentes(mid)
    db.query("UPDATE edital_subitem SET atualizado_em = now() - interval '7 hours' "
             "WHERE topico_id IN (SELECT id FROM topico WHERE edital_id IN "
             "(SELECT id FROM edital WHERE mesa_id = %(m)s))", {"m": mid})
    assert "Ciências Sintéticas" in cobertura.pendentes(mid)
    assert cobertura.marcar_pendente(usuario["id"], "Ciências Sintéticas") == 4


def test_mapa_nao_mostra_material_de_outro_aluno(client, usuario, outro_usuario, llm_falso):
    mid = _mesa_com_material(client, usuario)
    llm_falso.excecao = None
    cobertura.mapear(mid, usuario["id"], com_modelo=False)
    assert all(not s["materiais"] for i in cobertura.mapa_do_edital(mid, outro_usuario["id"])
               for s in i["subitens"])


def test_questao_comentada_nao_e_candidata():
    questao = ("57. (FGV/ALE-MA/2023) Julgue o item.\na) certo\nb) errado\n"
               "Comentários: o item está correto. Gabarito: Letra B.")
    assert cobertura.e_questao(questao)
    assert not cobertura.e_questao("O habeas corpus protege a liberdade de locomoção contra "
                                   "ilegalidade ou abuso de poder.")


def test_rota_do_mapa_e_verificacao_em_segundo_plano(client, usuario, llm_falso):
    mid = _mesa_com_material(client, usuario)
    llm_falso.excecao = __import__("core.llm", fromlist=["ErroLLM"]).ErroLLM("sem cota")
    cab = {**usuario["headers"], "X-Mesa-Id": str(mid)}

    r = client.get("/edital/mapa", headers=cab).json()

    # A primeira visita dispara a verificação (no TestClient, a tarefa roda ao fim
    # da resposta); a segunda já vê o resultado — aqui, só por texto.
    assert r["verificando"] == ["Ciências Sintéticas"]
    r = client.get("/edital/mapa", headers=cab).json()
    [item] = r["itens"]
    assert {s["metodo"] for s in item["subitens"]} == {"texto"}
    assert r["verificando"] == [], "texto recém-verificado espera 6 h para nova tentativa"
    assert r["resumo"][0]["subitens"] == 4


def test_apagar_material_volta_o_mapa_a_pendente(client, usuario, llm_falso):
    mid = _mesa_com_material(client, usuario)
    cobertura.mapear(mid, usuario["id"], com_modelo=False)
    doc = db.exec1("SELECT id FROM documento WHERE usuario_id = %(u)s", {"u": usuario["id"]})["id"]

    material.apagar(usuario["id"], doc)

    assert {s["estado"] for i in cobertura.mapa_do_edital(mid, usuario["id"]) for s in i["subitens"]} == {"pendente"}


def test_ler_na_ordem_do_edital_abre_o_ponto_seguinte_nao_lido(client, usuario, llm_falso):
    """A leitura vai ao PRÓXIMO ponto do edital com material, na ordem oficial, e
    abre a apostila onde ele começa; lido um ponto, o seguinte é o próximo."""
    from core import conversa, leitura
    mid = _mesa_com_material(client, usuario)
    cobertura.mapear(mid, usuario["id"], com_modelo=False)
    cab = {**usuario["headers"], "X-Mesa-Id": str(mid)}
    # A aula do dublê ENSINA o ponto: só conta como lido o que a resposta cobriu
    # (`leitura.ensinados`, 29/09/2026), e "Aula do ponto." não cobre nada.
    llm_falso.retorno = ("A perícia sintética é o exame técnico feito por perito, com laudo e "
                         "prazo próprios no caso concreto.")
    assert leitura.intencao("quero seguir a ordem do edital", False, False) == "edital"

    r = client.post("/perguntar", json={"pergunta": "quero ciências sintéticas seguindo a ordem do edital"},
                    headers=cab).json()

    prompt = llm_falso.chamadas[-1]["prompt"]
    assert "PONTO DO EDITAL deste turno" in prompt and "perícia sintética" in prompt
    primeiro = conversa.ultima_leitura(r["conversa_id"])
    assert primeiro and primeiro["ids"]

    client.post("/perguntar", json={"pergunta": "próximo item do edital", "conversa_id": r["conversa_id"]},
                headers=cab)
    segundo = llm_falso.chamadas[-1]["prompt"]
    assert len(llm_falso.chamadas) == 2, "\"próximo item do edital\" não é pedido de questões"
    assert "cadeia sintética de custódia" in segundo.split("PONTO DO EDITAL")[1][:200]


def test_fala_que_cita_um_ponto_do_edital_recebe_onde_ele_esta(client, usuario, llm_falso):
    mid = _mesa_com_material(client, usuario)
    cobertura.mapear(mid, usuario["id"], com_modelo=False)
    onde = cobertura.localizar(mid, usuario["id"], "onde está a perícia sintética no meu material?")
    # material .txt não tem página; em PDF vem "Perícias sintéticas, p. 3–17"
    assert "perícia sintética" in onde and "Perícias sintéticas" in onde
    assert cobertura.localizar(mid, usuario["id"], "quero ver o conceito") is None
    assert "SEM MATERIAL" in cobertura.localizar(mid, usuario["id"], "e a criminologia sintética?")
