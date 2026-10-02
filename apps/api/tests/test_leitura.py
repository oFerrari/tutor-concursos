"""Leitura em sequência: pedir para avançar lê o material na ordem dele.

As falas dos testes puros são as da conversa real de 24/09/2026 em que o aluno
pediu cinco vezes para estudar "na ordem", "como apostila", "sem perguntas" —
e recebeu uma frase e uma pergunta por turno, com a conversa derivando para o
inquérito policial. O material do teste de ponta a ponta é inventado.
"""
import json

from core import conversa, db, leitura, material

VERSAO = "test-leitura-v2"


def test_frases_reais_de_quem_quer_ler_comecam_a_leitura():
    for fala in ("eu queria estudar na ordem entender o conceito inteiro da materia",
                 "não porisso eu quero que você ja traga todo o conteudo sobre esse topico 2.1",
                 "eu quero ver na ordem de aprendizado que os materiais que eu subi trazem",
                 "não e neste primeiro momento eu não quero responder perguntas eu só queroa a historia a explicação",
                 "ja falei que eu quero aprender o conteudo como se estivesse lendo a apostila, sem pausas"):
        assert leitura.intencao(fala, False, False) == "inicio", fala


def test_certo_so_avanca_depois_de_um_turno_de_leitura():
    """Depois de uma pergunta do tutor, "certo" é resposta a ela."""
    assert leitura.intencao("certo..", ultima_foi_leitura=True, ha_leitura=True) == "continua"
    assert leitura.intencao("certo..", ultima_foi_leitura=False, ha_leitura=True) is None
    assert leitura.intencao("certo..", ultima_foi_leitura=False, ha_leitura=False) is None


def test_continua_retoma_a_leitura_mesmo_depois_de_uma_duvida():
    assert leitura.intencao("continua", ultima_foi_leitura=False, ha_leitura=True) == "continua"
    assert leitura.intencao("pode seguir", ultima_foi_leitura=False, ha_leitura=True) == "continua"
    assert leitura.intencao("continua", ultima_foi_leitura=False, ha_leitura=False) is None


def test_pergunta_no_meio_da_leitura_vai_a_busca():
    assert leitura.intencao("o que é perito ad hoc?", True, True) is None
    assert leitura.intencao("aprofunda essa parte", True, True) == "aprofunda"


def test_insistir_no_pedido_de_leitura_nao_troca_de_material():
    assert not leitura.nomeia_outro_assunto(
        "ja falei que eu quero aprender o conteudo como se estivesse lendo a apostila, sem pausas")
    assert leitura.nomeia_outro_assunto("quero ler na ordem a parte de balística forense")


def test_sumario_vira_roteiro_e_nao_come_a_janela():
    sumario = "Sumário\nPerícias ........ 4\nPeritos ........ 11\nNomeação ........ 19\n"
    assert leitura.e_sumario(sumario)
    assert not leitura.e_sumario("Texto corrido sobre perícia. " * 20)
    # Trechos de 40% da janela: cabem dois, o terceiro passaria do limite.
    tamanho = int(leitura.JANELA_CHARS * 0.4)
    linhas = [{"texto": sumario}] + [{"texto": "x" * tamanho} for _ in range(5)]

    janela, seguinte = leitura._selecionar(linhas)

    assert len(janela) == 1 + 2 and seguinte is linhas[3]


def _aula(client, usuario):
    paragrafos = [f"Seção {i}: o instituto sintético número {i} tem regra própria, "
                  f"requisito próprio e efeito próprio no caso concreto. " * 5 for i in range(40)]
    corpo = "\n\n".join(paragrafos).encode()
    doc = client.post("/materiais", files={"arquivo": ("aula-00.txt", corpo, "text/plain")},
                      data={"disciplina": "Ciências Sintéticas", "tipo": "aula"},
                      headers=usuario["headers"]).json()
    assert material.esperar_fila(30)
    return doc["id"]


# A aula do dublê ENSINA o trecho: desde 29/09/2026 (`leitura.ensinados`) só conta
# como lido o que a resposta cobriu, e "Aula sobre o trecho." não cobre nada.
AULA = ("### Instituto\nCada seção mostra que o instituto sintético tem regra própria, "
        "requisito próprio e efeito próprio no caso concreto.")


def _turno(client, usuario, llm_falso, fala, cid=None, retorno=AULA):
    llm_falso.retorno = retorno
    corpo = {"pergunta": fala, **({"conversa_id": cid} if cid else {})}
    r = client.post("/perguntar", json=corpo, headers=usuario["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_leitura_avanca_pela_ordem_e_volta_depois_da_duvida(client, usuario, llm_falso):
    doc = _aula(client, usuario)

    r = _turno(client, usuario, llm_falso,
               "quero estudar o instituto sintético na ordem do material, sem perguntas")
    cid = r["conversa_id"]
    primeira = conversa.ultima_leitura(cid)
    assert primeira and primeira["documento_id"] == doc and primeira["foi_a_ultima"]
    ordens = [c["ordem"] for c in db.query(
        "SELECT ordem FROM chunk WHERE id = ANY(%(i)s) ORDER BY ordem", {"i": primeira["ids"]})]
    assert ordens[0] == 0, "começar a ler é começar do começo do material"
    assert "Leitura do material do aluno" in llm_falso.chamadas[-1]["prompt"]

    _turno(client, usuario, llm_falso, "certo..", cid)
    segunda = conversa.ultima_leitura(cid)
    assert segunda["documento_id"] == doc and min(
        c["ordem"] for c in db.query("SELECT ordem FROM chunk WHERE id = ANY(%(i)s)",
                                     {"i": segunda["ids"]})) == primeira["ordem"] + 1

    # Dúvida no meio: vai à busca, e a leitura fica onde estava.
    _turno(client, usuario, llm_falso, "o que é o requisito próprio do instituto número 3?", cid,
           retorno=json.dumps({"resposta": "É isto.", "fontes_usadas": []}))
    depois_da_duvida = conversa.ultima_leitura(cid)
    assert not depois_da_duvida["foi_a_ultima"] and depois_da_duvida["ordem"] == segunda["ordem"]

    _turno(client, usuario, llm_falso, "continua", cid)
    terceira = conversa.ultima_leitura(cid)
    assert min(c["ordem"] for c in db.query("SELECT ordem FROM chunk WHERE id = ANY(%(i)s)",
                                            {"i": terceira["ids"]})) == segunda["ordem"] + 1


def test_pedir_para_ler_na_ordem_le_o_material_da_conversa_e_nao_o_da_busca(monkeypatch):
    """Medido em 24/09/2026 com o modelo real: a fala sobre ESTUDAR ("na ordem,
    o conceito inteiro, depois questões") foi à busca e voltou a lista de
    gabaritos de outra apostila; o tutor escreveu sobre perícia em cima dela."""
    monkeypatch.setattr(leitura, "documento_para",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia buscar")))
    fala = ("eu queria estudar na ordem entender o conceito inteiro da materia os mais "
            "importante, depois fazer questões se me sentir preparado")

    assert leitura.escolher_material(fala, fala, [], material_recente=2200, disciplinas=None,
                                     mapa=None, usuario_id=1, mesa_id=None) == 2200


def test_turno_termina_a_frase_e_o_seguinte_nao_a_repete():
    """Medido em 24/09/2026: um turno terminou em "que serve para esclarecer e"
    e o seguinte abriu em "prestar informações à Justiça" — a sobreposição do
    chunker e a quebra de página do PDF, lidas em sequência."""
    a = "Texto anterior completo. A perícia é um exame que serve para esclarecer e"
    b = ("serve para esclarecer e\n\nprestar informações à Justiça. Na esfera criminal, "
         "busca-se a materialidade.")
    c = "busca-se a materialidade.\n\nNovo parágrafo sobre peritos."

    [turno1] = leitura.emendar([{"texto": a}], None, {"texto": b})
    turno2 = leitura.emendar([{"texto": b}, {"texto": c}], a, None)

    assert turno1["texto"].endswith("esclarecer e prestar informações à Justiça.")
    assert [t["texto"] for t in turno2] == ["Na esfera criminal, busca-se a materialidade.",
                                          "Novo parágrafo sobre peritos."]


def test_sem_fim_de_frase_por_perto_o_corte_fica():
    """Emendar meia página para fechar uma frase seria pior que o corte."""
    longo = "palavra " * 200
    [t] = leitura.emendar([{"texto": "Frase sem fim e"}], None, {"texto": longo})
    assert t["texto"] == "Frase sem fim e"


def test_ordem_como_materia_nao_comeca_leitura():
    for pergunta in ("o que diz a CF sobre a ordem econômica?",
                     "na ordem social, o que diz o art. 193?",
                     "qual a ordem de vocação hereditária?",
                     "a ordem pública justifica a prisão preventiva?"):
        assert leitura.intencao(pergunta, True, True) is None, pergunta


def _eventos(client, usuario, corpo):
    r = client.post("/perguntar/fluxo", json=corpo, headers=usuario["headers"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    return [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith("data:")]


def test_fluxo_transmite_a_leitura_e_termina_com_a_resposta_de_sempre(client, usuario, llm_falso):
    _aula(client, usuario)
    llm_falso.retorno = AULA

    ev = _eventos(client, usuario, {"pergunta": "quero ler o instituto sintético na ordem do material"})

    assert [e for e in ev if "pedaco" in e] == [{"pedaco": AULA}]
    fim = ev[-1]["fim"]
    assert fim["resposta"].startswith("### Instituto") and fim["conversa_id"]
    assert any(f.get("sequencial") for f in fim["fontes"])


def test_fluxo_de_pergunta_comum_chega_inteiro_no_fim(client, usuario, llm_falso):
    llm_falso.retorno = "Resposta do tutor."
    ev = _eventos(client, usuario, {"pergunta": "boa noite"})
    assert [list(e) for e in ev] == [["fim"]] and ev[0]["fim"]["resposta"] == "Resposta do tutor."


def test_fluxo_sem_modelo_vira_evento_de_erro(client, usuario, llm_falso):
    from core import llm
    llm_falso.excecao = llm.ErroLLM("provedor fora")
    [ev] = _eventos(client, usuario, {"pergunta": "o que é peculato?"})
    assert ev["erro"]["status"] == 503 and "Não consegui responder" in ev["erro"]["detail"]


def test_regras_da_leitura_so_vao_no_turno_de_leitura(client, usuario, llm_falso):
    """~590 tokens que todo turno pagava sem usar (24/09/2026)."""
    from core import socratic
    _aula(client, usuario)
    r = _turno(client, usuario, llm_falso, "quero ler o instituto sintético na ordem do material")
    assert socratic.SISTEMA_LEITURA in llm_falso.chamadas[-1]["sistema"]
    _turno(client, usuario, llm_falso, "o que é o requisito do instituto número 2?", r["conversa_id"],
           retorno=json.dumps({"resposta": "É isto.", "fontes_usadas": []}))
    assert socratic.SISTEMA_LEITURA not in llm_falso.chamadas[-1]["sistema"]
    assert llm_falso.chamadas[-1]["sistema"].startswith(socratic.SISTEMA_TUTOR)


def test_questoes_sobre_isto_saem_do_trecho_lido(client, usuario, llm_falso):
    """Medido em 24/09/2026: lida a parte de federação, as questões saíram de
    outras páginas do mesmo material — o gerador refazia a busca pelo tema."""
    _aula(client, usuario)
    r = _turno(client, usuario, llm_falso, "quero ler o instituto sintético na ordem do material")
    lidos = conversa.ultima_leitura(r["conversa_id"])["ids"]
    llm_falso.retorno = json.dumps([{"tema": "t", "enunciado": "Qual o efeito do instituto?",
                                     "gabarito": "O efeito próprio.", "dicas": ["a", "b", "c"],
                                     "trecho": 1}])

    g = client.post("/questoes/gerar", json={"quantidade": 1, "conversa_id": r["conversa_id"]},
                    headers=usuario["headers"]).json()

    assert g["questoes"], g
    fonte = db.exec1("SELECT fonte_chunks FROM questao WHERE id = %(q)s",
                     {"q": g["questoes"][0]["id"]})["fonte_chunks"]
    assert set(fonte) <= set(lidos)


def test_planejamento_nao_e_leitura_e_muleta_antes_do_continua_vale():
    assert leitura.intencao("eu queria um mapa mental e uma trilha de aprendizagem completa "
                            "seguindo a ordem do edital", False, False) is None
    assert leitura.intencao("em continua o conteudo de direito administrativo", False, True) == "continua"
    assert leitura.intencao("não continua", False, True) is None


def test_fala_informal_da_bateria_de_24_09():
    """Falas da bateria com o modelo real que não disparavam a leitura."""
    assert leitura.intencao("vamo le o conteudo de direito constitucional pela apostila",
                            False, False) == "inicio"
    assert leitura.intencao("prossiga", False, True) == "continua"
    assert leitura.intencao("volta pro direito administrativo, continua de onde parou",
                            False, True) == "inicio"
    assert leitura.intencao("tá muito resumido, quero mais completo", True, True) == "aprofunda"


def test_lido_e_o_que_a_resposta_ensinou_e_nao_a_janela():
    """Bateria de 29/09/2026: a janela levou a apostila inteira, a resposta
    ensinou só a primeira seção, e o marcador foi para o fim — os turnos
    seguintes "continuaram" de memória, sem fonte."""
    trechos = [
        {"id": 1, "texto": "Proposição é oração declarativa que admite valor lógico verdadeiro ou falso."},
        {"id": 2, "texto": "Proposição composta junta proposições simples por conectivos lógicos."},
        {"id": 3, "texto": "Tautologia sempre verdadeira; contradição sempre falsa; contingência varia."},
        {"id": 4, "texto": "Conjunto reúne elementos; união, interseção e diferença entre conjuntos."},
    ]
    resposta = ("Proposição é toda oração declarativa que admite um valor lógico, verdadeiro ou "
                "falso. A composta junta proposições simples por meio de conectivos. A seguir: tautologia.")
    assert [c["id"] for c in leitura.ensinados(trechos, resposta)] == [1, 2]
    # Trecho do meio fraco não interrompe; resposta que não ensina nada não avança.
    assert [c["id"] for c in leitura.ensinados(trechos, resposta + " União e interseção de "
                                                "conjuntos reúnem elementos.")] == [1, 2, 3, 4]
    assert leitura.ensinados(trechos, "Boa noite! Quer seguir?") == []


def test_pedido_de_explicacao_abre_a_leitura_e_pergunta_pontual_nao():
    """Conversa real (01/10/2026): explicar, trazer o conteúdo, entender, do zero e
    na ordem são pedido de aula; "o que é", "qual a diferença" respondem pontual."""
    for fala in ["me explica proposições compostas", "traga a explicação do assunto",
                 "certo traga todo conceito", "cade o conteudo de Proposições Simples.?",
                 "quero entender conectivos lógicos",
                 "vamos começar a materio do zero mesmo e seguir na ordem o que acha?"]:
        assert leitura.intencao(fala, False, False) == "inicio", fala
    for fala in ["o que é uma proposição?", "qual a diferença entre conjunção e disjunção?",
                 "você pode me explicar como funciona o sistema?", "na ordem social, o que diz a CF?"]:
        assert leitura.intencao(fala, False, False) is None, fala
    for fala in ["é só isso que tem no material?", "de tudo", "certo.."]:
        assert leitura.intencao(fala, True, True) == "continua", fala
    assert leitura.intencao("explica melhor aquela parada que eu não entendi", True, True) == "aprofunda"
