"""Busca: peso do tipo pela intenção da fala, braço lexical por pares, e a resposta
que escolhe mandando na consulta (30/09/2026). Universal: vale para todo tipo."""
from core import assunto, db, retrieval

VERSAO = "test-busca-intencao-v1"


def test_intencao_da_fala():
    assert retrieval.intencao("o que diz o art. 5º, XI?") == "lei"
    assert retrieval.intencao("como o STF entende a prisão em segunda instância?") == "jurisprudencia"
    assert retrieval.intencao("me explica proposições compostas") == "conceito"
    assert retrieval.intencao("tenho 2 horas, sem questões por enquanto") is None, \
        "falar de questões não é intenção de busca: pedido de questões vai ao banco do simulado"
    assert retrieval.intencao("bom dia") is None


def test_peso_do_tipo_vale_para_todos_os_tipos():
    for intencao, pesos in retrieval.PESO_TIPO.items():
        sql = retrieval._sql_peso_tipo(intencao)
        assert all(f"WHEN '{t}'" in sql for t in pesos)
    assert retrieval._sql_peso_tipo(None) == "1"


def test_lexical_cai_em_pares_quando_o_e_nao_acha(monkeypatch):
    monkeypatch.setattr(db, "exec1", lambda *a, **k: {"n": 0})
    q = retrieval._termos_da_consulta("homonimos sininimos paronimos", None, None)
    assert q.count("&") == 3 and q.count("|") == 2, q
    monkeypatch.setattr(db, "exec1", lambda *a, **k: {"n": 9})
    assert retrieval._termos_da_consulta("homonimos sininimos paronimos", None, None) == \
        "homonimos & sininimos & paronimos"
    assert retrieval._termos_da_consulta("peculato culposo", None, None) == "peculato & culposo", \
        "duas palavras: o E basta"


def test_resposta_que_escolhe_manda_na_consulta():
    disc = ["Ciências Forenses", "Direito Administrativo", "Língua Portuguesa"]
    cardapio = [{"autor": "tutor", "texto": "Vamos continuar em Direito Administrativo, em licença para "
                                           "atividade política, ou prefere outra disciplina?"}]
    assert assunto.em_foco(cardapio, "que tal hmm, ciencias forense?", disc) == "que tal hmm, ciencias forense?"
    itens = [{"autor": "tutor", "texto": "Em Língua Portuguesa o edital cobra 1.1 Interpretação e compreensão "
                                        "de texto e 1.2 Organização estrutural dos textos. Qual prefere?"}]
    foco = assunto.em_foco(itens, "agora sim, 1.1 Interpretação e compreensão de texto", disc)
    assert foco.startswith("Em Língua Portuguesa") and foco.endswith("compreensão de texto"), foco
