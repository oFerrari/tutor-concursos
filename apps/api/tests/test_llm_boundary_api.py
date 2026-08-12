"""
`/questoes/{id}/avaliar` e `/perguntar` são as duas rotas que dependem do
LLM — testadas aqui com o dublê (`llm_falso`, ver conftest.py) pra cobrir
o FIO de verdade (rota HTTP -> core/socratic.py -> schema -> resposta) sem
gastar cota real do Gemini nem depender de rede em toda execução da suíte.

O que NÃO está aqui: julgar se o modelo avalia bem uma resposta de
concurso. Isso é qualidade de prompt, não integração — se testar, é
perguntando de verdade e olhando a resposta, não em CI.
"""
import json

from core.llm import ErroLLM


def test_avaliar_correta_revela_gabarito(client, usuario, questao_id, llm_falso):
    llm_falso.retorno = json.dumps({
        "veredito": "correta", "comentario": "boa resposta", "pergunta": "", "conceito_faltante": "",
    })
    r = client.post(
        f"/questoes/{questao_id}/avaliar",
        json={"resposta": "minha resposta", "nivel": 0, "historico": []},
        headers=usuario["headers"],
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["veredito"] == "correta"
    # a política de revelação é do código, não do modelo (core/socratic.py) —
    # correta revela mesmo que o modelo nem tenha esse campo na resposta
    assert corpo["revelar_gabarito"] is True


def test_avaliar_incorreta_no_nivel_baixo_nao_revela(client, usuario, questao_id, llm_falso):
    llm_falso.retorno = json.dumps({
        "veredito": "incorreta", "comentario": "falta X", "pergunta": "o que seria X?", "conceito_faltante": "X",
    })
    r = client.post(
        f"/questoes/{questao_id}/avaliar",
        json={"resposta": "chute", "nivel": 0, "historico": []},
        headers=usuario["headers"],
    )
    corpo = r.json()
    assert corpo["veredito"] == "incorreta"
    assert corpo["revelar_gabarito"] is False


def test_avaliar_incorreta_no_nivel_2_revela_gabarito_por_regra_de_codigo(client, usuario, questao_id, llm_falso):
    """nivel=2 é a 3ª tentativa — revela mesmo se o modelo devolver
    'incorreta' de novo. Contrato documentado em CLAUDE.md: retenção do
    gabarito é imposta em código, não confiada ao prompt."""
    llm_falso.retorno = json.dumps({
        "veredito": "incorreta", "comentario": "ainda não", "pergunta": "", "conceito_faltante": "",
    })
    r = client.post(
        f"/questoes/{questao_id}/avaliar",
        json={"resposta": "chute de novo", "nivel": 2, "historico": []},
        headers=usuario["headers"],
    )
    assert r.json()["revelar_gabarito"] is True


def test_avaliar_veredito_invalido_do_modelo_cai_para_parcial(client, usuario, questao_id, llm_falso):
    """socratic.avaliar() não confia em qualquer string do modelo pro
    campo veredito — um valor fora do enum cai pra 'parcial', não estoura."""
    llm_falso.retorno = json.dumps({
        "veredito": "mais ou menos", "comentario": "?", "pergunta": "", "conceito_faltante": "",
    })
    r = client.post(
        f"/questoes/{questao_id}/avaliar",
        json={"resposta": "x", "nivel": 0, "historico": []},
        headers=usuario["headers"],
    )
    assert r.status_code == 200
    assert r.json()["veredito"] == "parcial"


def test_avaliar_json_invalido_do_modelo_da_erro_legivel_nao_500(client, usuario, questao_id, llm_falso):
    llm_falso.retorno = "isto não é json nenhum"
    r = client.post(
        f"/questoes/{questao_id}/avaliar",
        json={"resposta": "x", "nivel": 0, "historico": []},
        headers=usuario["headers"],
    )
    # ErroLLM (core/llm.py._parse_json) -> HTTPException(503) em api.py — nunca
    # deveria vazar como 500 cru (ver invariante "erro de transporte não
    # escapa de core/llm.py" no CLAUDE.md).
    assert r.status_code == 503


def test_avaliar_transporte_indisponivel_da_503_nao_500(client, usuario, questao_id, llm_falso):
    llm_falso.excecao = ErroLLM("simulando timeout de rede")
    r = client.post(
        f"/questoes/{questao_id}/avaliar",
        json={"resposta": "x", "nivel": 0, "historico": []},
        headers=usuario["headers"],
    )
    assert r.status_code == 503


def test_questao_inexistente_da_404_antes_de_chamar_o_llm(client, usuario, llm_falso):
    r = client.post(
        "/questoes/999999999/avaliar",
        json={"resposta": "x", "nivel": 0, "historico": []},
        headers=usuario["headers"],
    )
    assert r.status_code == 404
    assert not llm_falso.chamadas


def test_perguntar_usa_o_acervo_real_e_o_llm_dublado(client, usuario, llm_falso):
    """retrieval.buscar() é local (embeddings em CPU, sem custo) — só o
    passo final (llm.obter().gerar) é dublado. Prova que a rota busca no
    acervo de verdade E devolve o texto do "modelo" tal como ele veio."""
    llm_falso.retorno = "resposta de teste sobre o material"
    r = client.post(
        "/perguntar",
        json={"pergunta": "o que é peculato?"},
        headers=usuario["headers"],
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resposta"] == "resposta de teste sobre o material"
    assert len(corpo["fontes"]) > 0
    assert len(llm_falso.chamadas) == 1


def test_perguntar_propaga_falha_de_llm_como_503(client, usuario, llm_falso):
    llm_falso.excecao = ErroLLM("simulando indisponibilidade")
    r = client.post("/perguntar", json={"pergunta": "o que é peculato?"}, headers=usuario["headers"])
    assert r.status_code == 503
