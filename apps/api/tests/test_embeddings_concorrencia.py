"""O modelo de embeddings carrega UMA vez, mesmo com N threads entrando junto.

Este teste existe por causa de uma falha MEDIDA, não de teoria: subir três
materiais em lote pela tela (`api.py` indexa em `BackgroundTasks`, ou seja, no
pool de threads) deu dois `falha` e um `pronto`, com

    Cannot copy out of meta tensor; no data!

gravado em `documento.erro`. A causa era `@lru_cache(maxsize=1)` em `_modelo()`:
o lru_cache memoiza o RESULTADO, não protege o CORPO. Duas threads que chegam
antes da primeira carga terminar erram o cache as duas e constroem o
SentenceTransformer as duas, e as duas cargas disputam a inicialização de pesos
no device `meta` do transformers.

Não é caso só do lote: o caminho interativo tem a mesma exposição — uma pergunta
no tutor durante uma indexação chama `embed_consulta` de outra thread.

O dublê é obrigatório aqui. Com o modelo de verdade, o teste passaria pelo
motivo errado: a carga real leva segundos, e a versão QUEBRADA também "passa"
se as threads não se cruzarem — o teste tem que forçar o cruzamento, e é o
`sleep` do dublê que garante isso.
"""
import threading
import time

import pytest

from core import embeddings

VERSAO = "test-embeddings-concorrencia-v1"


@pytest.fixture
def modelo_zerado():
    """Zera o singleton e o devolve no fim.

    Sem restaurar, todo teste posterior que chamasse `_modelo()` receberia o
    dublê — o tipo de vazamento entre testes que faz uma suíte falhar
    dependendo da ORDEM."""
    original = embeddings._MODELO
    embeddings._MODELO = None
    yield
    embeddings._MODELO = original


def test_carga_concorrente_constroi_uma_vez_so(modelo_zerado, monkeypatch):
    construcoes = []

    class Dublê:
        def __init__(self, nome, device=None):
            construcoes.append(nome)
            # A janela é o teste: sem demora na construção, as threads não se
            # cruzam e a versão quebrada passaria igual.
            time.sleep(0.15)

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", Dublê)

    obtidos, barreira = [], threading.Barrier(6)

    def carregar():
        barreira.wait()          # todas as threads largam no mesmo instante
        obtidos.append(embeddings._modelo())

    ts = [threading.Thread(target=carregar) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert len(construcoes) == 1, f"o modelo foi construído {len(construcoes)}x"
    # Mesma instância pra todas: duas instâncias em memória seriam o dobro do
    # RAM do modelo, além da corrida que estourava a carga.
    assert len(obtidos) == 6 and len({id(m) for m in obtidos}) == 1


def test_caminho_rapido_nao_reconstroi(modelo_zerado, monkeypatch):
    """Depois de carregado, `_modelo()` devolve sem entrar na trava — senão toda
    chamada de embedding pagaria contenção de lock pelo resto do processo."""
    construcoes = []

    class Dublê:
        def __init__(self, nome, device=None):
            construcoes.append(nome)

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", Dublê)

    primeiro = embeddings._modelo()
    for _ in range(50):
        assert embeddings._modelo() is primeiro
    assert len(construcoes) == 1
