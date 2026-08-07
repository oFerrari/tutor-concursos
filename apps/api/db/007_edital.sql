-- =====================================================================
-- Edital — meta até a prova com dado real, não digitado na mão.
--
-- topico é achatado (sem árvore N.N.N -> N.N -> N): cada subitem numerado
-- do conteúdo programático vira uma linha, com o número dentro do próprio
-- `texto`. Suficiente para contar "quantos tópicos existem" e estimar
-- cobertura por disciplina; não modela hierarquia porque nada hoje precisa
-- navegar a árvore, só contar folhas.
-- =====================================================================

CREATE TABLE edital (
  id          BIGSERIAL PRIMARY KEY,
  titulo      TEXT NOT NULL,
  orgao       TEXT,
  banca       TEXT,
  data_prova  DATE,
  arquivo     TEXT,
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE topico (
  id          BIGSERIAL PRIMARY KEY,
  edital_id   BIGINT NOT NULL REFERENCES edital(id) ON DELETE CASCADE,
  disciplina  TEXT NOT NULL,
  ordem       INT NOT NULL,
  texto       TEXT NOT NULL
);

CREATE INDEX topico_edital_idx ON topico (edital_id);
CREATE INDEX topico_disciplina_idx ON topico (disciplina);
