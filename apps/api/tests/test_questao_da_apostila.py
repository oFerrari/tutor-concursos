"""
Questão gerada do MATERIAL DO ALUNO (026) — e o isolamento que isso exige.

O QUE MOTIVOU
-------------
O tutor sempre leu a biblioteca privada pra EXPLICAR (`socratic.explicar`), mas
a geração de questão exigia `chunk.artigo IS NOT NULL`, e chunk de apostila é
janela de texto, sem artigo. Resultado no uso real: a explicação vinha da aula
de traumatologia forense e a questão vinha do Código Penal. O relato foi
direto — "se você está trazendo a fonte de um lugar, o certo é trazer questões
dali também".

O QUE ESTES TESTES TRAVAM
-------------------------
Dois riscos opostos, e o segundo é o grave:

  1. a questão da apostila SAI (senão nada disso serviu de nada);
  2. ela nunca aparece pra outra pessoa. `questao` é acervo compartilhado
     desde a 008; a questão privada é a primeira exceção, e cada pool que
     escolhe questão (fila, desafio, simulado, lookup por id, cobertura da
     mesa) é uma rota por onde ela poderia escapar. Um `AND` esquecido em
     qualquer uma delas não devolve número errado: devolve o material pago de
     outra pessoa.

Por isso o teste de isolamento ENUMERA as rotas em vez de checar uma. Rota
nova que sirva questão de pool tem de entrar nesta lista — e se não entrar,
o teste não a cobre, o que é a única forma honesta de dizer que a lista é o
inventário.
"""
import json

import pytest

from core import db, geracao, material, mesa, questoes, scheduler, simulado

VERSAO = "test-questao-da-apostila-v3"

# Texto sem UM "Art." — é o que faz `material._e_lei_seca` recusar e cair no
# fatiamento por janela, que é o chunk sem artigo que interessa aqui.
APOSTILA = (
    "TRAUMATOLOGIA FORENSE — AULA 3\n\n"
    "Energias de ordem mecânica produzem lesões cuja morfologia permite "
    "inferir o instrumento utilizado. Instrumento contundente age por "
    "pressão, tração ou torção e produz equimose, hematoma e escoriação. "
    "Instrumento perfurante age por pressão em pequena área e produz "
    "ferida punctória, cuja profundidade excede as demais dimensões. "
    "Instrumento cortante age por deslizamento do fio e produz ferida "
    "incisa, de bordas regulares e cauda de escoriação. "
) * 6


def _apostila(client, headers, nome="aula-03.txt"):
    """Sobe a apostila e devolve o documento indexado. Indexação é síncrona
    nos testes (`_indexar_sincrono` no conftest)."""
    r = client.post("/materiais",
                    files={"arquivo": (nome, APOSTILA.encode(), "text/plain")},
                    data={"disciplina": "Ciências Forenses", "assunto": "Traumatologia forense",
                          "tipo": "aula"},
                    headers=headers)
    assert r.status_code in (200, 201), r.text
    doc_id = r.json()["id"]
    doc = db.exec1("SELECT id, status, usuario_id FROM documento WHERE id = %(i)s", {"i": doc_id})
    if doc["status"] != "pronto":
        pytest.skip(f"indexação do material não concluiu: {doc['status']}")
    return doc


def _chunk_sem_artigo(documento_id: int) -> dict:
    c = db.exec1(
        f"""SELECT {geracao.CAMPOS_LOTE} FROM chunk c
              JOIN documento d ON d.id = c.documento_id
             WHERE c.documento_id = %(i)s AND c.artigo IS NULL
             ORDER BY c.ordem LIMIT 1""",
        {"i": documento_id})
    if not c:
        pytest.skip("a apostila de teste não gerou chunk sem artigo")
    return c


def _questao(trecho, artigo=None):
    q = {"trecho": trecho, "tema": "Instrumento contundente",
         "enunciado": "O que caracteriza a ação do instrumento contundente?",
         "gabarito": "Age por pressão, tração ou torção.", "dicas": ["a", "b", "c"]}
    if artigo is not None:
        q["artigo"] = artigo
    return q


# ------------------------------------------------------- 1. a questão sai
def test_questao_de_chunk_sem_artigo_e_gravada_pelo_numero_do_trecho(client, usuario):
    """A chave nova de proveniência. Sem ela, apostila era ingerável por
    definição: não há artigo pra casar, então TODA questão dela caía no
    descarte "artigo None não está no lote"."""
    doc = _apostila(client, usuario["headers"])
    c = _chunk_sem_artigo(doc["id"])

    salvas, descartes = geracao.salvar([_questao(trecho=1)], [c])

    assert descartes == []
    assert len(salvas) == 1
    gravada = db.exec1(
        "SELECT usuario_id, fonte_chunks, documento_id FROM questao WHERE id = %(i)s",
        {"i": salvas[0]["id"]})
    # PROVENIÊNCIA REAL, não relaxada: aponta o chunk exato da apostila.
    assert gravada["fonte_chunks"] == [c["id"]]
    assert gravada["documento_id"] == doc["id"]
    # E NASCE PRIVADA — sem isso, o resto deste arquivo não teria como valer.
    assert gravada["usuario_id"] == usuario["id"]


def test_o_dono_sai_do_chunk_nao_de_parametro(client, usuario):
    """`salvar` não tem parâmetro de dono, de propósito: se tivesse, existiria
    a chamada que grava apostila como pública por esquecimento. Aqui a prova é
    negativa — o mesmo `salvar()`, sem nenhum argumento novo, produz questão
    pública a partir de chunk de lei e privada a partir de chunk de apostila."""
    doc = _apostila(client, usuario["headers"])
    privado = _chunk_sem_artigo(doc["id"])
    publico = db.exec1(
        f"""SELECT {geracao.CAMPOS_LOTE} FROM chunk c
              JOIN documento d ON d.id = c.documento_id
             WHERE d.usuario_id IS NULL AND c.artigo IS NOT NULL
               AND d.tipo <> 'historico' AND length(c.texto) >= 140
             ORDER BY c.id LIMIT 1""")
    if not publico:
        pytest.skip("acervo público sem chunk de lei")

    salvas, _ = geracao.salvar(
        [_questao(trecho=1), _questao(trecho=2, artigo=publico["artigo"])],
        [privado, publico])
    assert len(salvas) == 2
    donos = {s["id"]: s["usuario_id"] for s in salvas}
    ids = list(donos)
    fontes = {r["id"]: r["fonte_chunks"][0] for r in db.query(
        "SELECT id, fonte_chunks FROM questao WHERE id = ANY(%(i)s)", {"i": ids})}
    for qid, dono in donos.items():
        esperado = usuario["id"] if fontes[qid] == privado["id"] else None
        assert dono == esperado


# ---------------------------------- 2. a invariante NÃO foi afrouxada
def test_lei_sem_artigo_citado_continua_sendo_descarte(client, usuario):
    """A porta lateral que o `trecho` poderia abrir, e não abre.

    Se o número do trecho valesse pra qualquer chunk, ele seria o jeito de
    gravar questão de LEI sem dizer de que artigo ela saiu — exatamente o
    afrouxamento que `core/geracao.py` existe pra não fazer. O trecho vale
    apenas onde não há artigo pra citar."""
    c = db.exec1(
        f"""SELECT {geracao.CAMPOS_LOTE} FROM chunk c
              JOIN documento d ON d.id = c.documento_id
             WHERE c.artigo IS NOT NULL AND length(c.texto) >= 140
             ORDER BY c.id LIMIT 1""")
    if not c:
        pytest.skip("acervo sem chunk de lei")
    antes = db.exec1("SELECT count(*) n FROM questao")["n"]

    salvas, descartes = geracao.salvar([_questao(trecho=1)], [c])

    assert salvas == []
    assert len(descartes) == 1 and "não citou o artigo" in descartes[0]
    assert db.exec1("SELECT count(*) n FROM questao")["n"] == antes


@pytest.mark.parametrize("trecho", [0, 3, -1, None, "nenhum"])
def test_trecho_fora_do_lote_e_descarte(client, usuario, trecho):
    """Número fora da faixa é descarte, igual a artigo fora do lote. A chave
    nova tem o mesmo rigor da antiga, senão não é proveniência."""
    doc = _apostila(client, usuario["headers"])
    c = _chunk_sem_artigo(doc["id"])
    salvas, descartes = geracao.salvar([_questao(trecho=trecho)], [c])
    assert salvas == []
    assert len(descartes) == 1 and "fora do lote" in descartes[0]


def test_artigo_citado_dentro_da_apostila_nao_descarta_a_questao(client, usuario):
    """MEDIDO na primeira rodada real, com o Gemini: pedidas 3 questões sobre
    lesão corporal, o lote veio todo da apostila (a busca achou a aula, não o
    CP) e o modelo devolveu `artigo: "129"` em duas delas — porque a aula
    TRANSCREVE o art. 129. As duas foram descartadas por "artigo não está no
    lote", e eram boas.

    O campo `artigo` ali não é proveniência, é conteúdo do material. Quando o
    `trecho` aponta chunk sem artigo, é o trecho que vale. O prompt já pede o
    campo vazio nesse caso; o modelo preenche mesmo assim."""
    doc = _apostila(client, usuario["headers"])
    c = _chunk_sem_artigo(doc["id"])

    salvas, descartes = geracao.salvar([_questao(trecho=1, artigo="129")], [c])

    assert descartes == []
    assert len(salvas) == 1
    gravada = db.exec1("SELECT fonte_chunks FROM questao WHERE id = %(i)s",
                       {"i": salvas[0]["id"]})
    assert gravada["fonte_chunks"] == [c["id"]]


def test_artigo_fora_do_lote_segue_descarte_quando_o_trecho_e_lei(client, usuario):
    """A trava do caso 2, que a mudança acima NÃO podia afrouxar: com lote de
    lei, artigo inventado continua sendo descarte, aponte o trecho pra onde
    apontar."""
    c = db.exec1(
        f"""SELECT {geracao.CAMPOS_LOTE} FROM chunk c
              JOIN documento d ON d.id = c.documento_id
             WHERE c.artigo IS NOT NULL AND length(c.texto) >= 140
             ORDER BY c.id LIMIT 1""")
    if not c:
        pytest.skip("acervo sem chunk de lei")
    salvas, descartes = geracao.salvar([_questao(trecho=1, artigo="999999")], [c])
    assert salvas == []
    assert len(descartes) == 1 and "999999" in descartes[0]


# ------------------------------ 2b. a mistura (regra PURA, sem banco)
def _lei(i):
    return {"id": i, "e_lei": True}


def _apo(i):
    return {"id": i, "e_lei": False}


@pytest.mark.parametrize("ids,cand,limite,esperado,caso", [
    ([1, 2, 3, 9, 4], [_apo(1), _apo(2), _apo(3), _lei(9), _apo(4)], 3, [1, 2, 9],
     "apostila lidera e a lei existe no pool: a última vaga é dela"),
    ([7, 8, 9, 1], [_lei(7), _lei(8), _lei(9), _apo(1)], 3, [7, 8, 1],
     "o contrário — o defeito original: explicar pela apostila e cobrar do Código"),
    ([1, 2, 3, 9, 4], [_apo(1), _apo(2), _apo(3), _lei(9), _apo(4)], 1, [1],
     "pedido de 1 questão não tem como misturar"),
    ([1, 2, 3], [_apo(1), _apo(2), _apo(3)], 3, [1, 2, 3],
     "assunto que só existe na apostila sai inteiro dela — reservar vaga vazia "
     "devolveria menos questão do que o aluno pediu"),
    ([7, 1, 8], [_lei(7), _apo(1), _lei(8)], 2, [7, 1],
     "já veio misturado: nada a fazer"),
])
def test_a_mistura_reserva_uma_vaga_pra_cada_lado(ids, cand, limite, esperado, caso):
    """Função PURA, testada sem banco e sem LLM — é a regra que decide de onde
    a questão vem, e ela cabe numa tabela. O primeiro colocado da busca nunca
    perde a vaga: é a trava que fez "concussão" voltar pra quem pediu
    concussão."""
    assert geracao._misturar(ids, cand, limite) == esperado, caso


@pytest.mark.parametrize("rubrica,tema,esperado,caso", [
    ("Lesão corporal", "lesão corporal grave: conceito e classificação", 2,
     "duas palavras em comum"),
    ("Perigo de contágio de moléstia grave", "lesão corporal grave: conceito", 1,
     "uma só, e por acidente: 'grave' é adjetivo compartilhado"),
    ("Uso de gás tóxico ou asfixiante", "asfixiologia forense: asfixia mecânica", 0,
     "asfixiante e asfixiologia são palavras DIFERENTES — é por não radicalizar "
     "que a comparação acerta aqui"),
    ("Peculato", "peculato", 1, "o caso simples"),
])
def test_palavras_em_comum_com_a_rubrica(rubrica, tema, esperado, caso):
    """A trava que decide se existe artigo DO ASSUNTO. A contagem (e não um
    booleano) é o que põe o art. 129 à frente do 131 pro mesmo tema — ver
    `_lei_do_assunto`."""
    from core import assunto as assunto_mod
    do_tema = {assunto_mod._sem_acento(p)
               for p in assunto_mod.palavras_de_conteudo(tema)}
    assert geracao._palavras_em_comum(rubrica, do_tema) == esperado, caso


@pytest.mark.parametrize("tema,espera_artigo,caso", [
    ("lesão corporal grave: conceito e classificação", "129",
     "o sufixo 'conceito e classificação' fazia a busca pôr o art. 131 em 1º; "
     "a contagem de palavras devolve o 129"),
    ("peculato", "312", "assunto que a lei trata, consulta curta"),
    ("asfixiologia forense: mecanismos de asfixia mecânica", None,
     "a lei NÃO trata de asfixiologia forense; devolver o art. 252 (uso de gás "
     "asfixiante) seria a questão fora do assunto que abriu este trabalho"),
    ("papiloscopia e impressões digitais", None, "idem — não há artigo do assunto"),
])
def test_o_reforco_da_lei_so_traz_artigo_do_assunto(tema, espera_artigo, caso):
    """`_lei_do_assunto` é o reforço que garante o lado da LEI quando a
    apostila afoga a busca (025: o rótulo entra no tsvector, e um rótulo
    repetido em 78 chunks produz 78 acertos lexicais).

    Sem LLM: mede a BUSCA, que é onde o defeito estava. Precisa do corpus
    público ingerido."""
    achados = geracao._lei_do_assunto(tema)
    artigos = [c["artigo"] for c in geracao._lote_por_ids([r["id"] for r in achados])]
    if espera_artigo is None:
        assert artigos == [], f"{caso} — mas veio {artigos}"
    else:
        if not artigos:
            pytest.skip(f"acervo público sem o artigo de {tema!r}")
        assert artigos[0] == espera_artigo, f"{caso} — veio {artigos}"


# ------------------------------------ 3. o isolamento, rota por rota
def _privada_de(client, dono: dict) -> dict:
    doc = _apostila(client, dono["headers"])
    c = _chunk_sem_artigo(doc["id"])
    salvas, descartes = geracao.salvar([_questao(trecho=1)], [c])
    assert descartes == [] and salvas, descartes
    return salvas[0]


def test_questao_privada_nao_escapa_por_nenhuma_rota_de_pool(client, usuario, outro_usuario):
    """
    O INVENTÁRIO DAS ROTAS que servem questão vinda de um pool.

    Cada uma delas era, antes da 026, uma consulta a `questao` sem noção de
    dono — e todas continuariam funcionando sem o predicado, devolvendo
    material privado alheio em silêncio. Estão enumeradas aqui, e não
    resumidas numa só, porque o valor deste teste é ser a LISTA: rota nova de
    pool que não apareça aqui não está coberta.

    A fila e o desafio pedem a mesa do OUTRO com disciplina casando a da
    apostila, senão o recorte por si já esconderia a questão e o teste
    passaria sem provar nada.
    """
    q = _privada_de(client, usuario)
    alheio = outro_usuario["id"]
    disc = ["Ciências Forenses"]

    def ids(lista):
        return {x["id"] for x in lista}

    # a) lookup direto por id — a rota do diálogo turno a turno
    assert questoes.obter(q["id"], alheio) is None
    assert questoes.obter_varias([q["id"]], alheio) == {}
    assert questoes.obter_com_progresso(alheio, q["id"]) is None
    # o DONO continua vendo: isolamento que esconde do dono é bug, não defesa
    assert questoes.obter(q["id"], usuario["id"]) is not None

    # b) fila SM-2 (as inéditas saem de `questao`, não de `progresso`)
    assert q["id"] not in ids(scheduler.fila(alheio, teto=500, disciplinas=disc))
    assert q["id"] in ids(scheduler.fila(usuario["id"], teto=500, disciplinas=disc))

    # c) simulado — sorteio aleatório sobre o acervo
    assert q["id"] not in ids(simulado.selecionar(500, disciplinas=disc, dono=alheio))

    # d) desafio (novas + mini-simulado)
    from core import desafio
    assert q["id"] not in ids(desafio._novas(alheio, 500, set(), disc))
    assert q["id"] not in ids(desafio._mini_simulado(alheio, 500, set(), disc))
    assert q["id"] in ids(desafio._novas(usuario["id"], 500, set(), disc))

    # e) contagens/cobertura — não vazam conteúdo, vazam a EXISTÊNCIA dele,
    #    e um contador que discorda da lista é defeito de tela garantido
    assert (mesa.contar_questoes(disc, usuario["id"])
            == mesa.contar_questoes(disc, alheio) + 1)

    # f) a rota HTTP, ponta a ponta: é onde o aluno de verdade chega
    r = client.get(f"/questoes/{q['id']}", headers=outro_usuario["headers"])
    assert r.status_code == 404
    assert client.get(f"/questoes/{q['id']}", headers=usuario["headers"]).status_code == 200


def test_apagar_a_conta_leva_a_questao_privada(client, usuario):
    """CASCATA da 009/026: a questão privada não pode sobreviver ao dono como
    órfã visível. Sem o `ON DELETE CASCADE` na coluna nova, apagar a conta
    deixaria questão com `usuario_id` apontando pra ninguém — e o predicado
    `usuario_id IS NULL OR = dono` não a esconderia de nada."""
    q = _privada_de(client, usuario)
    db.query("DELETE FROM usuario WHERE id = %(i)s", {"i": usuario["id"]})
    assert db.exec1("SELECT id FROM questao WHERE id = %(i)s", {"i": q["id"]}) is None


def test_desempenho_nao_conta_questao_privada_de_outra_pessoa(usuario, outro_usuario, questao_id):
    """A view do desempenho (008) nasceu antes de existir questão privada e fazia
    `CROSS JOIN questao`: o "0 de N questões" de um aluno contava as questões da
    apostila de OUTRO. Não vazava conteúdo, só o número — e o número contradizia
    o Meu edital (30 contra 22, medido em 22/09/2026). Corrigido na 032."""
    disciplina = "Disciplina Sintética Só Do Outro"
    doc = db.exec1("INSERT INTO documento (titulo, tipo, disciplina, usuario_id) "
                   "VALUES ('apostila do outro', 'aula', %(d)s, %(u)s) RETURNING id",
                   {"d": disciplina, "u": outro_usuario["id"]})["id"]
    qid = db.exec1(
        "INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito, dicas, "
        "fonte_chunks, usuario_id) VALUES (%(d)s, %(disc)s, 't', 'e?', 'g.', '[]'::jsonb, "
        "'{}', %(u)s) RETURNING id",
        {"d": doc, "disc": disciplina, "u": outro_usuario["id"]})["id"]
    # A view só lista quem tem progresso; os dois precisam existir nela.
    publica = questao_id
    for dono, q in ((usuario["id"], publica), (outro_usuario["id"], qid)):
        db.query("INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao) "
                 "VALUES (%(u)s, %(q)s, 0, CURRENT_DATE)", {"u": dono, "q": q})

    def linha(dono):
        return db.exec1("SELECT questoes FROM v_desempenho_disciplina "
                        "WHERE usuario_id = %(u)s AND disciplina = %(d)s",
                        {"u": dono, "d": disciplina})

    assert linha(usuario["id"]) is None, "a questão privada do outro entrou no meu número"
    assert linha(outro_usuario["id"])["questoes"] == 1


def test_mesma_pergunta_no_mesmo_trecho_nao_vira_outra_linha(client, usuario):
    """Medido em 22/09/2026: a mesma pergunta existia 12 vezes num trecho, e cada
    cópia voltava na fila como inédita. Mesma pergunta = mesmo trecho, mesmo dono,
    mesmo tipo e ≥ 90% das palavras de conteúdo do enunciado em comum."""
    doc = _apostila(client, usuario["headers"])
    c = _chunk_sem_artigo(doc["id"])

    [primeira], _ = geracao.salvar([_questao(trecho=1)], [c])

    # Reescrita sem mudar o conteúdo: a existente é devolvida, nada é gravado.
    reescrita = {**_questao(trecho=1),
                 "enunciado": "O que caracteriza a ação de um instrumento contundente?"}
    [devolvida], descartes = geracao.salvar([reescrita], [c])
    assert devolvida["id"] == primeira["id"]
    assert descartes == []

    # Pergunta DIFERENTE sobre o mesmo trecho continua virando linha nova — é o
    # que o limiar alto protege: "pena" e "conduta" do mesmo artigo são duas.
    outra = {**_questao(trecho=1),
             "enunciado": "Qual lesão o instrumento perfurante produz na pele?",
             "gabarito": "Ferida punctória."}
    [nova], _ = geracao.salvar([outra], [c])
    assert nova["id"] != primeira["id"]

    # Duas iguais na MESMA leva: entra uma, a outra vira descarte explicado.
    salvas, descartes = geracao.salvar([_questao(trecho=1), _questao(trecho=1)], [c])
    assert [s["id"] for s in salvas] == [primeira["id"]]
    assert any("mesma leva" in d for d in descartes)

    n = db.exec1("SELECT count(*) n FROM questao WHERE fonte_chunks = %(f)s::bigint[]",
                 {"f": [c["id"]]})["n"]
    assert n == 2, "só a primeira e a diferente existem"


def test_meta_nao_conta_questao_privada_de_outra_pessoa(usuario, outro_usuario):
    """Medido na bateria de estudo (02/10/2026): o /meta dizia 2,3% dominado onde
    eram 4,7% — o denominador somava as questões da apostila de outro aluno."""
    disciplina = "Disciplina Sintética Da Meta"
    for dono in (usuario["id"], outro_usuario["id"]):
        doc = db.exec1("INSERT INTO documento (titulo, tipo, disciplina, usuario_id) "
                       "VALUES ('apostila', 'aula', %(d)s, %(u)s) RETURNING id", {"d": disciplina, "u": dono})["id"]
        db.query("INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito, usuario_id) "
                 "VALUES (%(d)s, %(disc)s, 't', %(e)s, 'g.', %(u)s)",
                 {"d": doc, "disc": disciplina, "e": f"enunciado de {dono}?", "u": dono})
    from core import scheduler
    assert scheduler.meta(usuario["id"], disciplinas=[disciplina])["questoes_pendentes"] == 1
    assert "em_construcao_pct" in scheduler.meta(usuario["id"], disciplinas=[disciplina])
