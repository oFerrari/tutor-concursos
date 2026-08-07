"""
Regras de agendamento — FUNÇÕES PURAS, sem banco e sem relógio.

Por que separadas: a decisão "para qual caixa esta questão vai" não precisa
de Postgres nem da data de hoje. Só depende de (caixa atual, veredito, dicas
usadas). Isolada assim, ela pode ser simulada por 60 dias em milissegundos —
e o simulador exercita O MESMO código que roda em produção, não uma cópia.

É o mesmo princípio do diagnostico.py: empurrar a lógica para função pura e
deixar o efeito colateral na borda.
"""
INTERVALOS = [1, 3, 7, 15, 30, 90]
MAX_CAIXA = len(INTERVALOS) - 1


def proxima_caixa(caixa: int, veredito: str, dicas_usadas: int) -> int:
    """
    correta sem dica  -> promove
    correta com dica  -> mantém (lembrou com andaime, não é domínio)
    parcial           -> desce uma (perto, mas não sabe)
    incorreta         -> zera

    A distinção parcial/incorreta existe para preservar sinal: quem acertou
    metade precisa de revisão curta, não de reestudo do zero. Tratar os dois
    como iguais apaga essa diferença do caderno de erros.
    """
    if veredito == "correta":
        return min(caixa + 1, MAX_CAIXA) if dicas_usadas == 0 else caixa
    if veredito == "parcial":
        return max(caixa - 1, 0)
    return 0


def dias_ate_revisao(caixa: int) -> int:
    return INTERVALOS[max(0, min(caixa, MAX_CAIXA))]


def conta_como_erro(veredito: str) -> bool:
    """Parcial vai para o caderno de erros: não foi domínio."""
    return veredito != "correta"


def orcamento_novas(n_revisoes: int, teto: int, novas: int | None) -> int:
    """
    Quantas questões inéditas cabem na fila de hoje, depois de reservar o
    espaço para revisões.

    novas=None -> usa todo o resto do teto (estratégia que venceu na
    simulação: cota fixa freia a exposição sem necessidade nos dias leves).
    novas=N    -> reserva N no máximo, mesmo com resto de teto sobrando.

    n_revisoes já vem limitado a `teto` por quem chama (a query tem
    LIMIT teto), então `resto` nunca é negativo — o max(..., 0) é
    só para não confiar nessa invariante calada.
    """
    resto = max(teto - n_revisoes, 0)
    return resto if novas is None else min(resto, novas)
