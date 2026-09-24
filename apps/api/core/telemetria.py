"""Consumo do LLM: uma linha por CHAMADA, inclusive a que falhou (030).

Existe porque o 429 do free tier derrubou uma bateria inteira de `testar.sh` e
não havia como saber, de dentro do projeto, quanto tinha sido gasto nem por
quem. O painel é `gasto.py` (CLI) e `GET /gasto` (API).

DUAS REGRAS QUE ESTE MÓDULO NÃO PODE QUEBRAR:

1. TELEMETRIA NUNCA DERRUBA GERAÇÃO. Banco fora do ar, tabela ausente (máquina
   que ainda não rodou `migrar.py`), disco cheio: engole e segue. O aluno
   perder a resposta porque a contabilidade falhou seria trocar o produto pela
   métrica dele.
2. A LINHA DA FALHA É A MAIS IMPORTANTE. Cada tentativa que recebe 429 gastou
   uma requisição da cota — é exatamente isso que o dono quer ver. Por isso
   `registrar` é chamado por TENTATIVA, não por chamada bem-sucedida.
"""
import inspect
import os

from . import db

VERSAO = "telemetria-v1"

# Módulos que são o CAMINHO da chamada, não a origem dela: a pilha passa por
# eles em toda chamada e apontá-los não diria nada.
_TRANSPARENTES = {"telemetria", "llm"}


def origem() -> str | None:
    """"modulo.funcao" de quem pediu a geração, lido da pilha.

    Calculado aqui em vez de virar parâmetro em `LLM.gerar` porque são dez
    chamadores, e um parâmetro novo em todos eles é dez chances de esquecer —
    além de ruído numa interface que existe pra ser trocável (Ollama também a
    implementa). A pilha já sabe.
    """
    try:
        for frame in inspect.stack()[1:]:
            modulo = os.path.splitext(os.path.basename(frame.filename))[0]
            if modulo in _TRANSPARENTES:
                continue
            return f"{modulo}.{frame.function}"
    except Exception:
        pass
    return None


def registrar(provedor: str, modelo: str, status_code: int,
              tokens_input: int | None = None,
              tokens_output: int | None = None,
              origem_chamada: str | None = None,
              tokens_pensamento: int | None = None,
              tokens_cache: int | None = None) -> None:
    """Grava a tentativa. Silencioso por contrato — ver regra 1 no topo."""
    try:
        db.query(
            "INSERT INTO telemetria_llm (provedor, modelo, tokens_input, tokens_output, "
            "                            status_code, origem_chamada, tokens_pensamento, "
            "                            tokens_cache) "
            "VALUES (%(p)s, %(m)s, %(ti)s, %(to)s, %(s)s, %(o)s, %(tp)s, %(tc)s)",
            {"p": provedor, "m": modelo, "ti": tokens_input, "to": tokens_output,
             "s": status_code, "o": origem_chamada or origem(),
             "tp": tokens_pensamento, "tc": tokens_cache})
    except Exception:
        pass


def resumo(dias: int = 1) -> dict:
    """O painel: total, quebra por modelo, tokens e 429 na janela pedida.

    `dias=1` é HOJE no fuso do servidor, e não "últimas 24h": a cota do free
    tier zera por DIA de calendário (no Pacífico), então somar uma janela
    deslizante responderia uma pergunta que ninguém fez.
    """
    corte = "criado_em >= date_trunc('day', now()) - make_interval(days => %(d)s - 1)"
    por_modelo = db.query(
        f"SELECT modelo, count(*) AS chamadas, "
        f"       count(*) FILTER (WHERE status_code = 429) AS quota, "
        f"       count(*) FILTER (WHERE status_code >= 400 AND status_code <> 429) AS falhas, "
        f"       coalesce(sum(tokens_input), 0)  AS tokens_input, "
        f"       coalesce(sum(tokens_output), 0) AS tokens_output "
        f"FROM telemetria_llm WHERE {corte} "
        f"GROUP BY modelo ORDER BY chamadas DESC", {"d": dias})
    por_origem = db.query(
        f"SELECT coalesce(origem_chamada, '(desconhecida)') AS origem, count(*) AS chamadas, "
        f"       coalesce(sum(tokens_input + tokens_output), 0) AS tokens "
        f"FROM telemetria_llm WHERE {corte} "
        f"GROUP BY 1 ORDER BY chamadas DESC LIMIT 10", {"d": dias})
    ultima = db.exec1(
        "SELECT modelo, status_code, criado_em FROM telemetria_llm "
        "ORDER BY criado_em DESC LIMIT 1")
    return {
        "dias": dias,
        "chamadas": sum(m["chamadas"] for m in por_modelo),
        "quota_429": sum(m["quota"] for m in por_modelo),
        "falhas": sum(m["falhas"] for m in por_modelo),
        "tokens_input": sum(m["tokens_input"] for m in por_modelo),
        "tokens_output": sum(m["tokens_output"] for m in por_modelo),
        "por_modelo": por_modelo,
        "por_origem": por_origem,
        # O modelo ATIVO é o que respondeu por último, não o configurado: o
        # adaptador cai nas reservas sem avisar quem chama.
        "modelo_ativo": (ultima or {}).get("modelo"),
        "ultima_chamada": (ultima or {}).get("criado_em"),
    }
