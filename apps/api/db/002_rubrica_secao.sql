-- Rubrica (nomen iuris) e hierarquia TÍTULO/CAPÍTULO/SEÇÃO.
-- Idempotente: pode rodar mais de uma vez sem erro.

ALTER TABLE chunk ADD COLUMN IF NOT EXISTS rubrica TEXT;
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS secao   TEXT;

-- Busca direta por nome de crime: "concussão", "peculato-furto".
CREATE INDEX IF NOT EXISTS chunk_rubrica_idx
  ON chunk USING GIN (to_tsvector('portuguese', coalesce(rubrica, '')));

-- Amostragem por seção na geração de questões.
CREATE INDEX IF NOT EXISTS chunk_secao_idx ON chunk (secao) WHERE secao IS NOT NULL;
