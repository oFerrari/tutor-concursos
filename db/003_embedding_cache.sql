-- =====================================================================
-- Cache de embeddings endereçado por conteúdo.
--
-- Embedding é a operação caríssima do pipeline (CPU, ~1s por chunk).
-- Mas o vetor é função pura do par (texto, modelo): mesmo texto e mesmo
-- modelo produzem sempre o mesmo vetor. Então nunca deveria ser calculado
-- duas vezes.
--
-- Com isso, corrigir chunking deixa de custar reingestão inteira: só os
-- chunks cujo TEXTO mudou são reprocessados. Metadado (rubrica, seção)
-- muda de graça.
-- =====================================================================

CREATE TABLE IF NOT EXISTS embedding_cache (
  hash       TEXT NOT NULL,          -- sha256 do texto, hex
  modelo     TEXT NOT NULL,          -- vetor só é válido para o modelo que o gerou
  embedding  vector(768) NOT NULL,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hash, modelo)
);

-- Semeia o cache com o trabalho já feito: os embeddings que estão hoje na
-- tabela chunk. Depois disso, a próxima reingestão só calcula o que mudou.
-- O nome do modelo tem de casar com EMBEDDING_MODEL do .env.
INSERT INTO embedding_cache (hash, modelo, embedding)
SELECT DISTINCT ON (h) h, 'intfloat/multilingual-e5-base', embedding
FROM (
  SELECT encode(sha256(convert_to(texto, 'UTF8')), 'hex') AS h, embedding
  FROM chunk
  WHERE embedding IS NOT NULL
) s
ORDER BY h
ON CONFLICT (hash, modelo) DO NOTHING;
