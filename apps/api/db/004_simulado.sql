-- =====================================================================
-- Simulado — sessão sob condições de prova: sem dica, sem diálogo,
-- correção só no final.
--
-- Não duplica o que `tentativa` já guarda. Uma coluna nova basta para
-- marcar quais tentativas pertencem a qual simulado; nota e agregados
-- saem de GROUP BY sobre tentativa, não de contadores mantidos à mão.
-- =====================================================================

CREATE TABLE simulado (
  id             BIGSERIAL PRIMARY KEY,
  n_questoes     INT NOT NULL,
  minutos_alvo   INT,                     -- meta informativa; não há corte forçado
  segundos_total INT,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
  -- MULTIUSUARIO: usuario_id BIGINT NOT NULL REFERENCES usuario(id)
);

ALTER TABLE tentativa ADD COLUMN simulado_id BIGINT REFERENCES simulado(id) ON DELETE SET NULL;
CREATE INDEX tentativa_simulado_idx ON tentativa (simulado_id) WHERE simulado_id IS NOT NULL;
