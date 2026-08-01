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
from pathlib import Path

import httpx

from .config import (GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER,
                     OLLAMA_MODEL, OLLAMA_URL)

TIMEOUT = httpx.Timeout(120.0)
DEBUG_FILE = Path(".llm_debug.txt")


class ErroLLM(RuntimeError):
    pass


class LLM:
    def gerar(self, prompt: str, sistema: str = "", json_mode: bool = False,
              max_tokens: int = 1200, schema: dict | None = None) -> str:
        raise NotImplementedError

    def gerar_json(self, prompt: str, sistema: str = "",
                   max_tokens: int = 1200, schema: dict | None = None,
                   tentativas: int = 2):
        """Gera e parseia JSON. Repete uma vez se o modelo escorregar."""
        ultimo = None
        for i in range(tentativas):
            bruto = self.gerar(prompt, sistema, json_mode=True,
                               max_tokens=max_tokens, schema=schema)
            try:
                return _parse_json(bruto)
            except ErroLLM as e:
                ultimo = e
                _registrar_debug(bruto)
        raise ultimo


class Gemini(LLM):
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def gerar(self, prompt, sistema="", json_mode=False, max_tokens=1200, schema=None):
        if not GEMINI_API_KEY:
            raise ErroLLM("GEMINI_API_KEY ausente no .env")
        cfg = {"temperature": 0.3, "maxOutputTokens": max_tokens}
        if json_mode or schema:
            cfg["responseMimeType"] = "application/json"
        if schema:
            cfg["responseSchema"] = schema
        corpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                 "generationConfig": cfg}
        if sistema:
            corpo["systemInstruction"] = {"parts": [{"text": sistema}]}

        r = httpx.post(f"{self.BASE}/{GEMINI_MODEL}:generateContent",
                       params={"key": GEMINI_API_KEY}, json=corpo, timeout=TIMEOUT)
        if r.status_code == 429:
            raise ErroLLM("cota do plano gratuito estourada (429). Aguarde ou troque de modelo.")
        if r.status_code == 404:
            raise ErroLLM(f"modelo '{GEMINI_MODEL}' não existe para esta conta. "
                          f"Confira a lista no AI Studio e ajuste GEMINI_MODEL no .env.")
        if r.status_code >= 400:
            raise ErroLLM(f"Gemini HTTP {r.status_code}: {r.text[:400]}")

        d = r.json()
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
            raise ErroLLM(f"resposta truncada em {max_tokens} tokens. "
                          f"Aumente max_tokens ou reduza a quantidade pedida.")
        if motivo == "SAFETY":
            raise ErroLLM("resposta bloqueada pelos filtros do Gemini.")
        if not texto:
            raise ErroLLM(f"resposta vazia (finishReason={motivo}).")
        return texto


class Ollama(LLM):
    """Caminho 100% local. Mesma interface, zero mudança no resto do código."""

    def gerar(self, prompt, sistema="", json_mode=False, max_tokens=1200, schema=None):
        corpo = {"model": OLLAMA_MODEL, "prompt": prompt, "system": sistema,
                 "stream": False,
                 "options": {"temperature": 0.3, "num_predict": max_tokens}}
        if schema:
            corpo["format"] = schema      # Ollama aceita JSON Schema aqui
        elif json_mode:
            corpo["format"] = "json"
        r = httpx.post(f"{OLLAMA_URL}/api/generate", json=corpo, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise ErroLLM(f"Ollama HTTP {r.status_code}: {r.text[:400]}")
        return r.json().get("response", "").strip()


def obter() -> LLM:
    provedor = LLM_PROVIDER.strip()
    if provedor not in ("gemini", "ollama"):
        raise ErroLLM(f"LLM_PROVIDER inválido: {provedor!r}. Use 'gemini' ou 'ollama'.")
    return {"gemini": Gemini, "ollama": Ollama}[provedor]()


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
