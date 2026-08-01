-- =====================================================================
-- Tutor de concursos — schema inicial
--
-- Decisões que valem explicação:
--
-- 1. Um único banco. Vetor (pgvector) e texto (tsvector português) na
--    MESMA tabela, o que permite busca híbrida em uma query só.
-- 2. Chunks de lei carregam metadados estruturados (norma/artigo/§/inciso).
--    Isso permite recuperar por identificador — "art. 312, §1º" — que é
--    como o estudante realmente pergunta, e onde busca semântica falha.
-- 3. Sem tabela de usuário: v1 é mono-usuário. Onde entra usuario_id
--    depois está marcado com -- MULTIUSUARIO.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- acervo
CREATE TABLE documento (
  id          BIGSERIAL PRIMARY KEY,
  titulo      TEXT NOT NULL,
  disciplina  TEXT NOT NULL,
  tipo        TEXT NOT NULL CHECK (tipo IN ('lei', 'aula', 'resumo', 'jurisprudencia')),
  origem      TEXT,                      -- caminho do arquivo ou URL
  hash        TEXT UNIQUE,               -- evita reingestão do mesmo arquivo
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
  -- MULTIUSUARIO: usuario_id BIGINT NOT NULL REFERENCES usuario(id)
);

CREATE TABLE chunk (
  id            BIGSERIAL PRIMARY KEY,
  documento_id  BIGINT NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
  ordem         INT NOT NULL,
  texto         TEXT NOT NULL,
  -- metadados estruturados, preenchidos quando documento.tipo = 'lei'
  norma         TEXT,
  artigo        TEXT,
  paragrafo     TEXT,
  inciso        TEXT,
  pagina        INT,
  embedding     vector(768),
  busca         tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', texto)) STORED,
  UNIQUE (documento_id, ordem)
);

CREATE INDEX chunk_busca_idx  ON chunk USING GIN (busca);
CREATE INDEX chunk_emb_idx    ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunk_artigo_idx ON chunk (norma, artigo) WHERE artigo IS NOT NULL;

-- ------------------------------------------------------- banco de questões
-- A fila de revisão vive aqui: nada de RAG, é relacional puro.
CREATE TABLE questao (
  id            BIGSERIAL PRIMARY KEY,
  documento_id  BIGINT REFERENCES documento(id) ON DELETE SET NULL,
  disciplina    TEXT NOT NULL,
  tema          TEXT NOT NULL,
  enunciado     TEXT NOT NULL,
  gabarito      TEXT NOT NULL,
  dicas         JSONB NOT NULL DEFAULT '[]'::jsonb,   -- 3 dicas, ordem crescente
  fonte_chunks  BIGINT[] NOT NULL DEFAULT '{}',       -- rastreabilidade da geração
  caixa         SMALLINT NOT NULL DEFAULT 0,          -- 0..5, índice em INTERVALOS
  prox_revisao  DATE NOT NULL DEFAULT CURRENT_DATE,
  criada_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX questao_fila_idx ON questao (prox_revisao, caixa);

CREATE TABLE tentativa (
  id           BIGSERIAL PRIMARY KEY,
  questao_id   BIGINT NOT NULL REFERENCES questao(id) ON DELETE CASCADE,
  resposta     TEXT,
  veredito     TEXT NOT NULL CHECK (veredito IN ('correta', 'parcial', 'incorreta')),
  dicas_usadas SMALLINT NOT NULL DEFAULT 0,
  segundos     INT,
  criada_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX tentativa_questao_idx ON tentativa (questao_id, criada_em DESC);

-- Caderno de erros: visão materializada leve, atualizada pelo scheduler.
CREATE TABLE erro_caderno (
  questao_id  BIGINT PRIMARY KEY REFERENCES questao(id) ON DELETE CASCADE,
  disciplina  TEXT NOT NULL,
  tema        TEXT NOT NULL,
  vezes       INT NOT NULL DEFAULT 1,
  ultima      DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX erro_reincidencia_idx ON erro_caderno (vezes DESC, ultima DESC);

-- ------------------------------------------------------------- estatísticas
CREATE VIEW v_desempenho_disciplina AS
SELECT q.disciplina,
       COUNT(DISTINCT q.id)                                          AS questoes,
       COUNT(DISTINCT q.id) FILTER (WHERE q.caixa >= 3)              AS dominadas,
       COUNT(t.id)                                                   AS tentativas,
       COUNT(t.id) FILTER (WHERE t.veredito = 'correta')             AS acertos,
       ROUND(100.0 * COUNT(t.id) FILTER (WHERE t.veredito = 'correta')
             / NULLIF(COUNT(t.id), 0), 1)                            AS pct_acerto
FROM questao q
LEFT JOIN tentativa t ON t.questao_id = q.id
GROUP BY q.disciplina;
