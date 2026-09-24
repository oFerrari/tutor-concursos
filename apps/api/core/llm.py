"""
Camada de LLM.

Todo o resto do sistema fala com a interface `LLM`, nunca com um provedor.
Trocar Gemini por Ollama (ou por Claude) é escrever um adaptador de ~20
linhas e mudar LLM_PROVIDER no .env.

Sobre `schema`: quando informado, o Gemini opera em saída estruturada e é
obrigado a emitir JSON conforme o formato. Pedir JSON no prompt é sugestão;
declarar schema é garantia. Modelos menores (flash-lite) erram muito o JSON
livre, então todo lugar que precisa de JSON aqui passa schema.
"""
import json
import os
import time
from pathlib import Path

import httpx

from . import telemetria
from .config import (GEMINI_API_KEY, GEMINI_MODEL, GEMINI_RESERVAS, LLM_CLASSIFICADOR,
                     OLLAMA_MODEL_CLASSIFICADOR, LLM_PROVIDER,
                     OLLAMA_MODEL, OLLAMA_URL)

# 120s nao bastava no plano gratuito. Configuravel via LLM_TIMEOUT no .env.
TIMEOUT = httpx.Timeout(float(os.getenv("LLM_TIMEOUT", "240")))
DEBUG_FILE = Path(".llm_debug.txt")
VERSAO = "llm-v21"

# Temperatura padrão de TODA chamada do produto. Era um literal repetido nos dois
# adaptadores; virou constante quando o `temperatura=` apareceu, porque dois
# lugares com o mesmo número é o começo de dois números diferentes.
#
# 0.3 é do tutor e está certa pra ele: resposta idêntica a cada turno soa robô.
# Quem pede outra é o juiz de `avaliar_chat.py`, que passa 0 — uma fonte de
# variação a menos, de graça. Sem promessa exagerada: MEDIDO que isso não torna
# a nota repetível (o mesmo transcript deu 86 e 100 a temperatura 0), porque
# Gemini não é determinístico nem em 0.
TEMPERATURA_PADRAO = 0.3
ESPERA = (3, 10, 25)   # backoff entre tentativas, em segundos


class ErroLLM(RuntimeError):
    pass


class ErroTruncado(ErroLLM):
    """O modelo parou no teto de tokens. Subclasse, e não mensagem a comparar:
    quem chama pode tentar de novo com mais folga — o que `socratic.explicar`
    faz — em vez de a frase "resposta truncada em 1500 tokens" chegar ao aluno,
    que foi o que aconteceu em 24/09/2026 no meio de uma leitura."""


class LLM:
    def gerar(self, prompt: str, sistema: str = "", json_mode: bool = False,
              max_tokens: int = 1200, schema: dict | None = None,
              temperatura: float | None = None) -> str:
        raise NotImplementedError

    def gerar_em_fluxo(self, prompt: str, sistema: str, max_tokens: int,
                       ao_pedaco, temperatura: float | None = None) -> str:
        """Texto puro, entregue a `ao_pedaco` à medida que sai; devolve o todo.

        Padrão para quem não sabe transmitir (Ollama, dublê de teste): gera
        inteiro e entrega de uma vez. O contrato para quem chama é o mesmo."""
        texto = self.gerar(prompt, sistema, max_tokens=max_tokens, temperatura=temperatura)
        ao_pedaco(texto)
        return texto

    def gerar_json(self, prompt: str, sistema: str = "",
                   max_tokens: int = 1200, schema: dict | None = None,
                   tentativas: int = 2, temperatura: float | None = None):
        """Gera e parseia JSON. Repete uma vez se o modelo escorregar."""
        ultimo = None
        for i in range(tentativas):
            bruto = self.gerar(prompt, sistema, json_mode=True,
                               max_tokens=max_tokens, schema=schema,
                               temperatura=temperatura)
            try:
                return _parse_json(bruto)
            except ErroLLM as e:
                ultimo = e
                _registrar_debug(bruto)
        raise ultimo


def _post(url, params, corpo, tentativas=3):
    """
    Faz o POST convertendo TODA falha de transporte em ErroLLM.

    Existia um vazamento de abstração aqui: o resto do sistema captura
    ErroLLM, mas httpx.ReadTimeout subia cru e derrubava a execução com
    stack trace. Se esta camada promete esconder o cliente HTTP, ela tem
    de esconder também os erros dele.

    Timeout e 5xx são transitórios: vale reprocessar. 4xx é erro nosso e
    não melhora com repetição.
    """
    ultimo = ""
    for i in range(tentativas):
        try:
            r = httpx.post(url, params=params, json=corpo, timeout=TIMEOUT)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            ultimo = f"{type(e).__name__}: {e}"
        else:
            if r.status_code < 500 and r.status_code != 429:
                return r
            ultimo = f"HTTP {r.status_code}"
        if i + 1 < tentativas:
            espera = ESPERA[min(i, len(ESPERA) - 1)]
            print(f"    rede instavel ({ultimo}); nova tentativa em {espera}s")
            time.sleep(espera)
    raise ErroLLM(f"falhou depois de {tentativas} tentativas — {ultimo}")


def _modelos_gemini() -> list[str]:
    """Principal e reservas, SEM REPETIÇÃO. O default de `GEMINI_RESERVAS` repetia
    o principal no fim, e toda falha pagava uma requisição a mais no mesmo
    modelo que acabara de falhar — medido: 4 chamadas onde bastavam 3."""
    return list(dict.fromkeys([GEMINI_MODEL, *GEMINI_RESERVAS]))


class Gemini(LLM):
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def gerar_em_fluxo(self, prompt, sistema, max_tokens, ao_pedaco, temperatura=None):
        if not GEMINI_API_KEY:
            raise ErroLLM("GEMINI_API_KEY ausente no .env")
        cfg = {"temperature": TEMPERATURA_PADRAO if temperatura is None else temperatura,
               "maxOutputTokens": max_tokens}
        corpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                 "generationConfig": cfg}
        if sistema:
            corpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        return _gemini_em_fluxo(corpo, max_tokens, ao_pedaco)

    def gerar(self, prompt, sistema="", json_mode=False, max_tokens=1200, schema=None,
              temperatura=None):
        if not GEMINI_API_KEY:
            raise ErroLLM("GEMINI_API_KEY ausente no .env")
        cfg = {"temperature": TEMPERATURA_PADRAO if temperatura is None else temperatura,
               "maxOutputTokens": max_tokens}
        if json_mode or schema:
            cfg["responseMimeType"] = "application/json"
        if schema:
            cfg["responseSchema"] = schema
        corpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                 "generationConfig": cfg}
        if sistema:
            corpo["systemInstruction"] = {"parts": [{"text": sistema}]}

        # TROCA DE MODELO ANTES DE INSISTIR NO MESMO. O 503 do plano gratuito é
        # por capacidade DO MODELO: medido no mesmo minuto, `3.5-flash-lite` deu
        # 503 duas vezes enquanto `3.1-flash-lite` respondeu em 2,1s. A versão
        # anterior repetia o mesmo endereço três vezes, dormindo 3s e 10s entre
        # as tentativas — ou seja, transformava a instabilidade deles em 13s de
        # espera nossa pra bater na mesma parede, e o aluno via "LLM
        # indisponível" depois de quase um minuto olhando a tela.
        #
        # Uma tentativa por modelo, e o backoff fica só entre as rodadas: se
        # nenhum dos quatro respondeu, aí sim vale esperar antes de repassar.
        # TELEMETRIA POR TENTATIVA (030). Cada rodada deste laço é uma
        # requisição que a cota contou, inclusive a que voltou 429 — e é
        # justamente a linha do 429 que responde "gastei quanto, em quê". O
        # `de_onde` é lido UMA vez aqui: dentro do `except` a pilha já é outra.
        de_onde = telemetria.origem()
        r = None
        ultimo_erro = ""
        modelo_usado = None
        for modelo in _modelos_gemini():
            try:
                r = _post(f"{self.BASE}/{modelo}:generateContent",
                          {"key": GEMINI_API_KEY}, corpo, tentativas=1)
            except ErroLLM as e:
                ultimo_erro = str(e)
                # Status 0: não houve resposta HTTP (timeout, rede). Zerar o
                # código seria confundir com sucesso; 0 não é código nenhum.
                telemetria.registrar("gemini", modelo, 0, origem_chamada=de_onde)
                continue
            if r.status_code < 500 and r.status_code != 429:
                if modelo != GEMINI_MODEL:
                    print(f"    {GEMINI_MODEL} indisponível; respondeu com {modelo}")
                modelo_usado = modelo
                break
            ultimo_erro = f"HTTP {r.status_code}"
            telemetria.registrar("gemini", modelo, r.status_code, origem_chamada=de_onde)
            r = None
        if r is None:
            raise ErroLLM(
                f"o Gemini não respondeu em nenhum dos {len(_modelos_gemini())} modelos "
                f"({ultimo_erro}). Isso é instabilidade do provedor, não do app — "
                f"costuma passar em alguns minutos. Tente de novo.")
        if r.status_code >= 400:
            # O 4xx do modelo que RESPONDEU também gastou requisição, e sai do
            # laço pela porta do `break` — sem esta linha ele não apareceria no
            # painel. As tentativas que falharam já foram gravadas lá dentro.
            telemetria.registrar("gemini", modelo_usado or GEMINI_MODEL, r.status_code,
                                 origem_chamada=de_onde)
        if r.status_code == 429:
            raise ErroLLM("cota do plano gratuito estourada (429). Aguarde ou troque de modelo.")
        if r.status_code == 404:
            raise ErroLLM(f"modelo '{GEMINI_MODEL}' não existe para esta conta. "
                          f"Confira a lista no AI Studio e ajuste GEMINI_MODEL no .env.")
        if r.status_code >= 400:
            raise ErroLLM(f"Gemini HTTP {r.status_code}: {r.text[:400]}")

        d = r.json()
        # O `usageMetadata` sempre veio na resposta e era descartado sem ser
        # lido — é a única contagem de token que não precisa ser estimada.
        uso = d.get("usageMetadata") or {}
        telemetria.registrar("gemini", modelo_usado or GEMINI_MODEL, r.status_code,
                             tokens_input=uso.get("promptTokenCount"),
                             tokens_output=uso.get("candidatesTokenCount"),
                             origem_chamada=de_onde,
                             tokens_pensamento=uso.get("thoughtsTokenCount"),
                             tokens_cache=uso.get("cachedContentTokenCount"))
        cands = d.get("candidates") or []
        if not cands:
            raise ErroLLM(f"nenhum candidato na resposta: {json.dumps(d)[:400]}")
        cand = cands[0]
        motivo = cand.get("finishReason")
        partes = cand.get("content", {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes).strip()

        # Truncar no meio de um JSON é a causa mais comum de "JSON inválido".
        # Melhor falhar com o motivo real do que devolver texto pela metade.
        if motivo == "MAX_TOKENS":
            raise ErroTruncado(f"resposta truncada em {max_tokens} tokens. "
                               f"Aumente max_tokens ou reduza a quantidade pedida.")
        if motivo == "SAFETY":
            raise ErroLLM("resposta bloqueada pelos filtros do Gemini.")
        if not texto:
            raise ErroLLM(f"resposta vazia (finishReason={motivo}).")
        return texto


def _gemini_em_fluxo(corpo: dict, max_tokens: int, ao_pedaco) -> str:
    """`streamGenerateContent` em SSE, com a mesma troca de modelo de `gerar` —
    mas só ANTES do primeiro pedaço: depois dele o texto já está na tela do
    aluno, e recomeçar noutro modelo mostraria duas respostas emendadas."""
    de_onde = telemetria.origem()
    ultimo_erro = ""
    for modelo in _modelos_gemini():
        url = f"{Gemini.BASE}/{modelo}:streamGenerateContent"
        texto, motivo, uso, emitiu = [], None, {}, False
        try:
            with httpx.stream("POST", url, params={"key": GEMINI_API_KEY, "alt": "sse"},
                              json=corpo, timeout=TIMEOUT) as r:
                if r.status_code == 429 or r.status_code >= 500:
                    ultimo_erro = f"HTTP {r.status_code}"
                    telemetria.registrar("gemini", modelo, r.status_code, origem_chamada=de_onde)
                    continue
                if r.status_code >= 400:
                    telemetria.registrar("gemini", modelo, r.status_code, origem_chamada=de_onde)
                    raise ErroLLM(f"Gemini HTTP {r.status_code}: {r.read()[:400]!r}")
                for linha in r.iter_lines():
                    if not linha.startswith("data:"):
                        continue
                    d = json.loads(linha[5:])
                    uso = d.get("usageMetadata") or uso
                    cand = (d.get("candidates") or [{}])[0]
                    motivo = cand.get("finishReason") or motivo
                    pedaco = "".join(p.get("text", "") for p in
                                     (cand.get("content", {}).get("parts") or [])
                                     if not p.get("thought"))
                    if pedaco:
                        texto.append(pedaco)
                        ao_pedaco(pedaco)
                        emitiu = True
        except (httpx.TimeoutException, httpx.TransportError) as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
            telemetria.registrar("gemini", modelo, 0, origem_chamada=de_onde)
            if emitiu:
                raise ErroLLM(f"a transmissão caiu no meio: {ultimo_erro}")
            continue
        telemetria.registrar("gemini", modelo, 200, origem_chamada=de_onde,
                             tokens_input=uso.get("promptTokenCount"),
                             tokens_output=uso.get("candidatesTokenCount"),
                             tokens_pensamento=uso.get("thoughtsTokenCount"),
                             tokens_cache=uso.get("cachedContentTokenCount"))
        if motivo == "SAFETY":
            raise ErroLLM("resposta bloqueada pelos filtros do Gemini.")
        completo = "".join(texto).strip()
        if not completo:
            raise ErroLLM(f"resposta vazia (finishReason={motivo}).")
        # MAX_TOKENS aqui NÃO vira erro, ao contrário de `gerar`: o aluno já está
        # lendo o texto. Perder a aula inteira por causa do fim dela seria pior.
        if motivo == "MAX_TOKENS":
            print(f"    transmissão parou no teto de {max_tokens} tokens")
        return completo
    raise ErroLLM(
        f"o Gemini não respondeu em nenhum dos {len(_modelos_gemini())} modelos "
        f"({ultimo_erro}). Isso é instabilidade do provedor, não do app — "
        f"costuma passar em alguns minutos. Tente de novo.")


class Ollama(LLM):
    """Caminho 100% local. Mesma interface, zero mudança no resto do código."""

    # O contexto padrão do Ollama (2048 tokens) cortava em silêncio o começo de
    # material que o classificador manda (6000 caracteres + instruções).
    NUM_CTX = 8192

    def __init__(self, modelo: str | None = None):
        self.modelo = modelo or OLLAMA_MODEL

    def gerar(self, prompt, sistema="", json_mode=False, max_tokens=1200, schema=None,
              temperatura=None):
        corpo = {"model": self.modelo, "prompt": prompt, "system": sistema,
                 "stream": False,
                 "options": {
                     "temperature": TEMPERATURA_PADRAO if temperatura is None else temperatura,
                     "num_predict": max_tokens, "num_ctx": self.NUM_CTX}}
        if schema:
            corpo["format"] = schema      # Ollama aceita JSON Schema aqui
        elif json_mode:
            corpo["format"] = "json"
        r = _post(f"{OLLAMA_URL}/api/generate", None, corpo, tentativas=1)
        d = r.json() if r.status_code < 400 else {}
        telemetria.registrar("ollama", self.modelo, r.status_code,
                             tokens_input=d.get("prompt_eval_count"),
                             tokens_output=d.get("eval_count"))
        if r.status_code >= 400:
            raise ErroLLM(f"Ollama HTTP {r.status_code}: {r.text[:400]}")
        return d.get("response", "").strip()


class _ComReserva(LLM):
    """O local primeiro; falhando (Ollama parado, modelo não baixado), o outro."""

    def __init__(self, primeiro: LLM, reserva: LLM):
        self.primeiro, self.reserva = primeiro, reserva

    def gerar(self, *args, **kwargs):
        try:
            return self.primeiro.gerar(*args, **kwargs)
        except ErroLLM as e:
            print(f"    modelo local indisponível ({e}); usando o provedor principal")
            return self.reserva.gerar(*args, **kwargs)


def obter(tarefa: str | None = None) -> LLM:
    """O modelo para a tarefa. `tarefa="classificar"` pode ir ao modelo local
    (`LLM_CLASSIFICADOR=ollama`), com o provedor principal de reserva."""
    provedor = LLM_PROVIDER.strip()
    if provedor not in ("gemini", "ollama"):
        raise ErroLLM(f"LLM_PROVIDER inválido: {provedor!r}. Use 'gemini' ou 'ollama'.")
    principal = {"gemini": Gemini, "ollama": Ollama}[provedor]()
    if tarefa == "classificar" and LLM_CLASSIFICADOR == "ollama" and provedor != "ollama":
        return _ComReserva(Ollama(OLLAMA_MODEL_CLASSIFICADOR), principal)
    return principal


def _registrar_debug(bruto: str) -> None:
    """Guarda a resposta crua inteira — 300 caracteres no terminal não bastam."""
    try:
        DEBUG_FILE.write_text(bruto, encoding="utf-8")
    except OSError:
        pass


def _parse_json(bruto: str):
    limpo = bruto.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass
    for abre, fecha in (("[", "]"), ("{", "}")):
        i, j = limpo.find(abre), limpo.rfind(fecha)
        if i != -1 and j > i:
            try:
                return json.loads(limpo[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ErroLLM(f"JSON inválido do modelo (resposta completa em {DEBUG_FILE}): "
                  f"{limpo[:200]}")
