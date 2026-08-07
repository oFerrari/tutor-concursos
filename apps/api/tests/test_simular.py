"""
Testes de simular.py — invariantes estruturais + a comparação de estratégias
que está documentada em comentário em core/scheduler.py (TETO_DIARIO).

Por que isto importa: simular.py hoje só é validado visualmente ("olhe a
tabela impressa"). Sem um teste, uma futura mudança na regra pode inverter
silenciosamente a conclusão "revisão primeiro vence" sem que ninguém note —
exatamente a armadilha que o próprio projeto documentou (CLAUDE.md:
"diferença de 8 pontos virou 36 ao repetir 15 vezes" — por isso aqui usamos
várias sementes, nunca uma só).
"""
import pytest

from simular import simular


SEMENTES = range(1, 16)  # 15 sementes, mesma metodologia do comentário em scheduler.py


def _final(questoes, dias, limite, p_correta, p_parcial, semente, novas_por_dia=None):
    return simular(questoes, dias, limite, p_correta, p_parcial,
                    semente=semente, novas_por_dia=novas_por_dia)[-1]


# --------------------------------------------------------------------------
# invariantes estruturais — devem valer para QUALQUER regra/estratégia

@pytest.mark.parametrize("novas_por_dia", [None, 8])
@pytest.mark.parametrize("semente", [1, 2, 3])
def test_respondidas_nunca_passa_do_limite_nem_do_que_venceu(novas_por_dia, semente):
    limite = 25
    hist = simular(428, 90, limite, 0.45, 0.20, semente=semente, novas_por_dia=novas_por_dia)
    for dia in hist:
        assert dia["respondidas"] <= limite
        assert dia["respondidas"] <= dia["venceram"]


@pytest.mark.parametrize("novas_por_dia", [None, 8])
def test_vistas_e_monotonico_no_tempo(novas_por_dia):
    """Uma questão, uma vez vista, não pode "des-ver". `vistas` só sobe."""
    hist = simular(428, 90, 25, 0.45, 0.20, semente=1, novas_por_dia=novas_por_dia)
    vistas = [d["vistas"] for d in hist]
    assert vistas == sorted(vistas)


@pytest.mark.parametrize("novas_por_dia", [None, 8])
def test_dominadas_nunca_excede_o_total_de_questoes(novas_por_dia):
    questoes = 428
    hist = simular(questoes, 90, 25, 0.45, 0.20, semente=1, novas_por_dia=novas_por_dia)
    assert all(0 <= d["dominadas"] <= questoes for d in hist)


def test_atraso_e_nao_negativo():
    hist = simular(428, 90, 15, 0.45, 0.20, semente=1, novas_por_dia=5)
    assert all(d["atraso"] >= 0 for d in hist)


# --------------------------------------------------------------------------
# determinismo — mesma semente, mesmo resultado (pré-requisito para poder
# comparar estratégias por média de sementes com confiança)

def test_mesma_semente_e_deterministico():
    a = simular(428, 90, 25, 0.45, 0.20, semente=7, novas_por_dia=8)
    b = simular(428, 90, 25, 0.45, 0.20, semente=7, novas_por_dia=8)
    assert a == b


def test_sementes_diferentes_podem_divergir():
    """Sanidade inversa do teste acima: se nem isso variasse, `semente` não
    estaria de fato alimentando o gerador aleatório."""
    a = _final(428, 90, 25, 0.45, 0.20, semente=1, novas_por_dia=8)
    b = _final(428, 90, 25, 0.45, 0.20, semente=2, novas_por_dia=8)
    assert a != b


# --------------------------------------------------------------------------
# a conclusão documentada: revisão-primeiro (ANKI) vence a estratégia antiga
# (caixa mais baixa primeiro) quando a capacidade não cobre a demanda.
# Números de referência no comentário de core/scheduler.py, teto=25:
#   antiga ~39 dominadas · revisão-primeiro ~220 dominadas (médias de 15 sementes)
# Não travamos no número exato (é uma média de aleatório); travamos na ORDEM,
# com margem folgada, porque é a ordem que orienta a decisão de produto.

def test_revisao_primeiro_vence_estrategia_antiga_sob_teto_apertado():
    questoes, dias, limite = 428, 90, 25
    antigas = [_final(questoes, dias, limite, 0.45, 0.20, s)["dominadas"] for s in SEMENTES]
    anki = [_final(questoes, dias, limite, 0.45, 0.20, s, novas_por_dia=8)["dominadas"]
            for s in SEMENTES]

    media_antiga = sum(antigas) / len(antigas)
    media_anki = sum(anki) / len(anki)

    assert media_anki > media_antiga * 1.5, (
        f"gap documentado (antiga~39 vs anki~220) não se sustentou: "
        f"antiga={media_antiga:.0f} anki={media_anki:.0f}"
    )
