"""O que a resolução e o mapa mental precisam que chegue inteiro à tela (28/09/2026)."""
from core import geracao, llm, socratic

VERSAO = "test-formato-resposta-v1"


def test_json_perde_so_a_cerca_de_fora():
    """O mapa mental é um bloco de código DENTRO da resposta; as crases dele ficam."""
    bruto = '```json\n{"resposta": "```text\\nConjuntos\\n└── União\\n```"}\n```'
    assert llm._parse_json(bruto)["resposta"] == "```text\nConjuntos\n└── União\n```"
    assert llm._parse_json('{"a": 1}') == {"a": 1}


def test_latex_que_o_json_comeu_volta_a_ter_barra():
    comido = "\\boxed{105\text{ Agentes}} e \x0crac{1}{2}, \x08oxed{x}, a \neq b"
    assert socratic.latex_de_volta(comido) == (
        "\\boxed{105\\text{ Agentes}} e \\frac{1}{2}, \\boxed{x}, a \\neq b")
    # quebra de linha de verdade continua quebra de linha
    assert socratic.latex_de_volta("Passo 1\nequação montada") == "Passo 1\nequação montada"


def test_gerador_nao_completa_o_lote_com_artigo_fora_do_assunto(monkeypatch):
    """"questões de conjuntos" gerou "Furto Noturno": a vaga da lei foi para o
    artigo mais bem colocado da busca, que não tinha nada de conjuntos."""
    linhas = {1: {"id": 1, "rubrica": None, "texto": "Aula: apresentação e conjuntos"},
              2: {"id": 2, "rubrica": "Furto", "texto": "Subtrair coisa alheia móvel"},
              3: {"id": 3, "rubrica": None, "texto": "União e interseção de conjuntos"}}
    monkeypatch.setattr(geracao.db, "query", lambda sql, p: [linhas[i] for i in p["i"]])
    uteis = [{"id": 1, "e_lei": False}, {"id": 2, "e_lei": True}, {"id": 3, "e_lei": False}]
    assert [u["id"] for u in geracao._no_assunto(uteis, "questões de conjuntos")] == [1, 3]
    # o líder entra sempre, e tema sem conteúdo não filtra
    assert geracao._no_assunto(uteis, "") == uteis


def test_consultado_mostra_so_o_que_sustentou_a_resposta():
    fontes = [{"id": 1, "citada": True}, {"id": 2, "citada": False},
              {"id": 3, "citada": False, "sequencial": True}]
    assert [f["id"] for f in socratic._fontes_da_tela(fontes)] == [1, 3]


def test_gerador_que_falha_nao_deixa_a_promessa_na_tela(client, usuario, llm_falso, monkeypatch):
    from core import conversa, db
    llm_falso.retorno = "As questões já estão prontas logo abaixo."
    monkeypatch.setattr(geracao, "sob_demanda",
                        lambda *a, **k: (_ for _ in ()).throw(llm.ErroLLM("cota")))
    r = client.post("/perguntar", json={"pergunta": "me dá 2 questões de peculato"},
                    headers=usuario["headers"]).json()
    assert r["questoes"] == [] and "logo abaixo" not in r["resposta"]
    gravada = db.exec1("SELECT texto FROM mensagem WHERE conversa_id = %(c)s AND autor = 'tutor' "
                       "ORDER BY id DESC LIMIT 1", {"c": r["conversa_id"]})["texto"]
    assert gravada == r["resposta"]


def test_de_onde_veio_isso_responde_com_a_resposta_anterior(client, usuario, llm_falso):
    from core import conversa, pedido
    assert pedido.pede_fonte("qual aula e página do meu material sustentam o que você explicou?")
    assert pedido.pede_fonte("de onde vc tirou isso?")
    assert not pedido.pede_fonte("onde está nacionalidade no meu material?")
    llm_falso.retorno = "Aula."
    r = client.post("/perguntar", json={"pergunta": "o que é peculato?"}, headers=usuario["headers"]).json()
    cid = r["conversa_id"]
    conversa.gravar(cid, "tutor", "explicação", [
        {"id": 1, "citada": True, "assunto": "Crimes funcionais", "pagina": 4, "material": True},
        {"id": 2, "citada": True, "assunto": "Crimes funcionais", "pagina": 5, "material": True},
        {"id": 3, "citada": True, "norma": "CP", "artigo": "312", "titulo": "cp"}])
    assert conversa.origem_da_ultima_resposta(cid) == "- Crimes funcionais, p. 4–5\n- CP, art. 312"
    client.post("/perguntar", json={"pergunta": "de onde vc tirou isso?", "conversa_id": cid},
                headers=usuario["headers"])
    assert "Crimes funcionais, p. 4–5" in llm_falso.chamadas[-1]["prompt"]


def test_colchete_dentro_da_formula_nao_e_citacao():
    texto = "Fica $$E = [n(A) - n(A \\cap B)] + [n(B) - n(A \\cap B)]$$ e [Inventada, art. 9]."
    limpo = socratic.fora_da_formula(lambda t: socratic.limpar_citacoes(t, []), texto)
    assert "[n(A) - n(A \\cap B)] + [n(B) - n(A \\cap B)]" in limpo
    assert "Inventada" not in limpo


def test_gerador_fica_na_materia_da_conversa_quando_o_assunto_esta_nela(monkeypatch):
    """"tira isso e bota de tabela verdade" numa conversa de lógica deu cartão de
    Licença para atividade política: o 1º colocado da busca era a 8.112."""
    textos = {1: "Art. 86 licença para atividade política", 2: "tabela verdade com 2 elevado a n linhas"}
    monkeypatch.setattr(geracao.db, "query", lambda sql, p: [{"id": i, "texto": textos[i]} for i in p["i"]])
    uteis = [{"id": 1, "disciplina": "Direito Administrativo"},
             {"id": 2, "disciplina": "Raciocínio Lógico-Matemático"}]
    fala = "mano eu pedi tabela verdade, bota de tabela verdade logo"
    assert [u["id"] for u in geracao._na_materia_da_conversa(uteis, fala, ["Raciocínio Lógico-Matemático"])] == [2]
    # pedir outro assunto que a matéria da conversa não tem é trocar de assunto
    assert geracao._na_materia_da_conversa(uteis, "questão de licença", ["Raciocínio Lógico-Matemático"]) == uteis


def test_trilha_do_edital_inteiro_leva_os_itens_de_todas_as_disciplinas(monkeypatch):
    """"mapa mental e trilha completa seguindo a ordem do edital" deu a lista de
    APOSTILAS: o programa só entrava com uma disciplina nomeada (29/09/2026)."""
    programa = {"Ciências Sintéticas": ["1.1 Perícia sintética: conceito; laudo.", "1.2 Cadeia sintética."],
                "Lógica Inventada": ["2.1 Proposições inventadas: valor lógico."],
                "Alvo Manual": ["Alvo Manual"]}
    monkeypatch.setattr(socratic.mesa_mod, "topicos_da_disciplina",
                        lambda mid, d, limite=40: programa.get(d, []))
    mesa = {"id": 1, "disciplinas": list(programa)}
    bloco = socratic._programa_em_foco(mesa, "quero um mapa mental e uma trilha completa na ordem do edital", [])
    assert "Perícia sintética; Cadeia sintética" in bloco and "Proposições inventadas" in bloco
    assert "- Alvo Manual" in bloco
    assert socratic._programa_em_foco(mesa, "me explica isso melhor", []) is None


def test_assunto_nomeado_sem_material_nao_vira_cartao_de_outra_materia(client, usuario, llm_falso):
    """Bateria de 29/09/2026: questões de Informática (sem material) saíam de Direito
    Administrativo. Assunto NOMEADO sem trecho dele: a resposta diz que não há."""
    llm_falso.retorno = "As questões estão abaixo."
    r = client.post("/perguntar", json={"pergunta": "me dá 2 questões de criptozoologia sintética"},
                    headers=usuario["headers"]).json()
    assert r["questoes"] == []
    # O tutor fica sabendo ANTES de escrever, e diz com as palavras dele.
    assert "NENHUMA vai aparecer" in llm_falso.chamadas[-1]["prompt"]
    assert "criptozoologia" in llm_falso.chamadas[-1]["prompt"].split("NENHUMA vai aparecer")[1][:120]
    assert geracao.termo_raro("me manda questões de criptozoologia sintética", usuario["id"]) is None


def test_termo_raro_ignora_o_vocabulario_do_pedido():
    from core import pedido
    assert pedido.sem_o_pedido("me manda 3 questões de controle de constitucionalidade pfv") == \
        "de controle de constitucionalidade"


def test_dois_termos_raros_barram_o_ruido_do_pedido():
    """"consegue me mandar umas questões de controle de constitucionalidade?" teve
    "consegue" como termo mais raro e deu cartão do CP 177."""
    raros = geracao.termos_raros("consegue me mandar umas questões de controle de constitucionalidade?", None)
    assert len(raros) == 2 and "constitucionalidade" in raros


def test_pedido_sem_termo_forte_fica_na_materia_da_conversa():
    """"bota a questão pra eu resolver direito": "direito" é advérbio aqui; sem termo
    forte o pedido não nomeia assunto (validação de 29/09/2026)."""
    from core import pedido
    assert not geracao.tem_termo_forte("ta errada, ROM nao apaga nada, mas bota a questao com A B C D pra eu tentar resolver direito", None)
    assert geracao.tem_termo_forte("me dá 2 questões de peculato", None)
    assert "disso" not in pedido.sem_o_pedido("é a RAM que é volátil, bota uma questão disso aí")


def test_dois_assuntos_no_pedido_vao_cada_um_por_si():
    assert geracao._partes("manda uma questão de conjuntos e porcentagem") == ["de conjuntos", "porcentagem"]
    assert geracao._partes("questões de peculato") == ["questões de peculato"]


def test_pdf_justificado_uma_palavra_por_linha_e_remontado():
    from core import chunking
    assert chunking.desquebrar("em\n \ntodos\n \nos  tempos\n \ne modos.\nNova linha") == \
        "em todos os tempos e modos.\nNova linha"


def test_id_do_trecho_nao_aparece_na_conversa():
    """Conversa real (29/09/2026): "Ex.: As redes promoveram o aumento (ID 67553)"."""
    texto = ("Ex.: As redes promoveram o aumento (ID 67553). Precisa ser transitivo direto "
             "(IDs 67550 e 67575), e o art. 5º (CF) vale; [ID: 67543] fim. Em 1988 (ano) mudou.")
    assert socratic.sem_ids(texto) == ("Ex.: As redes promoveram o aumento. Precisa ser transitivo direto, "
                                      "e o art. 5º (CF) vale; fim. Em 1988 (ano) mudou.")


def test_reindexar_leva_o_marcador_de_leitura_junto(client, usuario, llm_falso):
    """Reindexar mudava a posição dos trechos e deixava o marcador da leitura (e as
    fontes das conversas) apontando para outra parte do material."""
    from core import conversa, db, material
    corpo = "\n\n".join(f"Parágrafo {i} sobre perícia sintética, laudo e prazo. " * 6 for i in range(30)).encode()
    r = client.post("/materiais", files={"arquivo": ("aula.txt", corpo, "text/plain")},
                    data={"disciplina": "Ciências Sintéticas", "tipo": "aula", "assunto": "Perícias"},
                    headers=usuario["headers"])
    assert r.status_code == 201 and material.esperar_fila(30)
    doc = r.json()["id"]
    alvo = db.exec1("SELECT id, ordem FROM chunk WHERE documento_id=%(d)s ORDER BY ordem OFFSET 10 LIMIT 1", {"d": doc})
    cid = db.exec1("INSERT INTO conversa (usuario_id, titulo) VALUES (%(u)s, 'x') RETURNING id", {"u": usuario["id"]})["id"]
    conversa.gravar(cid, "tutor", "aula", [{"id": alvo["id"], "documento_id": doc, "ordem": alvo["ordem"],
                                            "sequencial": True, "citada": True}])
    material.indexar(doc, "aula.txt", corpo)
    marcador = conversa.ultima_leitura(cid)
    assert marcador["documento_id"] == doc
    assert db.exec1("SELECT count(*) AS n FROM chunk WHERE id = ANY(%(i)s)", {"i": marcador["ids"]})["n"] == 1, \
        "o marcador aponta para um trecho que existe depois de reindexar"
