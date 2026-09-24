-- 034 — a telemetria passa a contar o PENSAMENTO do modelo e o que veio do CACHE
--
-- Por que agora (24/09/2026): o chat mostrou "resposta truncada em 1500 tokens"
-- num turno cuja resposta visível nunca passou de 735 tokens em três dias de
-- telemetria. A suspeita é o raciocínio interno do modelo (`thoughtsTokenCount`
-- no `usageMetadata`), que conta no `maxOutputTokens` e NÃO entra em
-- `candidatesTokenCount` — a única saída que a 030 gravava. Sem a coluna, a
-- suspeita não se confirma nem se derruba.
--
-- `tokens_cache` é o `cachedContentTokenCount`: a parte do prompt que o provedor
-- reaproveitou de uma chamada anterior (as instruções fixas do tutor são ~5 mil
-- tokens iguais em todo turno). Diz se o cache implícito está valendo.
--
-- NULL = o provedor não informou (Ollama, chamada que falhou, linha antiga).

ALTER TABLE telemetria_llm
    ADD COLUMN tokens_pensamento integer CHECK (tokens_pensamento IS NULL OR tokens_pensamento >= 0),
    ADD COLUMN tokens_cache      integer CHECK (tokens_cache IS NULL OR tokens_cache >= 0);
