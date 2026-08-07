-- =====================================================================
-- Multiusuário — schema completo.
--
-- DECISÃO CENTRAL: o acervo é COMPARTILHADO, o progresso é PESSOAL.
-- `documento`/`chunk`/`questao` continuam sem usuario_id — é o mesmo
-- Código Penal para todo mundo, e gerar questão custa cota de LLM: negar
-- reaproveitamento entre usuários seria pagar a mesma pergunta N vezes.
-- O que é pessoal (caixa, prox_revisao, tentativa, erro_caderno, simulado,
-- edital) passa a carregar usuario_id.
--
-- CAIXA E PROX_REVISAO SAEM DE `questao` E VÃO PRA `progresso`.
-- Hoje esses dois campos vivem na questão — mas caixa/prox_revisao são
-- ESTADO DE QUEM ESTUDA, não da pergunta. Com dois usuários estudando o
-- mesmo banco compartilhado, cada um precisa da sua própria caixa pra
-- MESMA questão. `progresso` é a tabela (usuario_id, questao_id) que
-- resolve isso: linha só existe depois da primeira tentativa — ausência de
-- linha = "esta pessoa nunca viu esta questão", que é exatamente o sinal
-- que `scheduler.fila()` já usava (antes via tentativa, agora via
-- progresso) pra separar revisão de material inédito.
--
-- TRANSAÇÃO ÚNICA: se o backfill falhar no meio, o DROP COLUMN não
-- executa e nada fica pela metade — mesma lição de reingest.py sobre
-- DELETE antes de validar o INSERT (ver Armadilhas de método).
-- =====================================================================

BEGIN;

CREATE TABLE usuario (
  id         BIGSERIAL PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  senha_hash TEXT NOT NULL,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Usuário placeholder pra dono dos dados que já existem no banco. Email
-- genérico de propósito: este projeto não leva identificador ligado à
-- empresa do autor (decisão do próprio CLAUDE.md) — troque depois com
-- UPDATE usuario SET email = '...' WHERE id = 1, se quiser um e-mail real
-- de login.
INSERT INTO usuario (email, senha_hash) VALUES ('estudante@local', '');

-- ------------------------------------------------------------ progresso
CREATE TABLE progresso (
  usuario_id   BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  questao_id   BIGINT NOT NULL REFERENCES questao(id) ON DELETE CASCADE,
  caixa        SMALLINT NOT NULL DEFAULT 0,
  prox_revisao DATE NOT NULL DEFAULT CURRENT_DATE,
  PRIMARY KEY (usuario_id, questao_id)
);

CREATE INDEX progresso_fila_idx ON progresso (usuario_id, prox_revisao, caixa);

-- Backfill: só as questões com tentativa real ganham linha. As sem
-- tentativa ficam sem linha — que é o estado correto pra "nunca tentada"
-- no modelo novo, não uma omissão.
INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao)
SELECT 1, id, caixa, prox_revisao FROM questao
WHERE EXISTS (SELECT 1 FROM tentativa t WHERE t.questao_id = questao.id);

-- a view depende de questao.caixa; precisa cair ANTES do DROP COLUMN e
-- só é recriada (já na forma nova) no fim do script.
DROP VIEW v_desempenho_disciplina;
DROP INDEX IF EXISTS questao_fila_idx;
ALTER TABLE questao DROP COLUMN caixa;
ALTER TABLE questao DROP COLUMN prox_revisao;

-- ------------------------------------------------------------ tentativa
ALTER TABLE tentativa ADD COLUMN usuario_id BIGINT REFERENCES usuario(id);
UPDATE tentativa SET usuario_id = 1 WHERE usuario_id IS NULL;
ALTER TABLE tentativa ALTER COLUMN usuario_id SET NOT NULL;
CREATE INDEX tentativa_usuario_idx ON tentativa (usuario_id, questao_id);

-- ---------------------------------------------------------- erro_caderno
-- PK vira composta: a mesma questão pode ser erro de reincidência pra um
-- usuário e nunca ter sido tentada por outro.
ALTER TABLE erro_caderno ADD COLUMN usuario_id BIGINT REFERENCES usuario(id);
UPDATE erro_caderno SET usuario_id = 1 WHERE usuario_id IS NULL;
ALTER TABLE erro_caderno ALTER COLUMN usuario_id SET NOT NULL;
ALTER TABLE erro_caderno DROP CONSTRAINT erro_caderno_pkey;
ALTER TABLE erro_caderno ADD PRIMARY KEY (usuario_id, questao_id);
DROP INDEX IF EXISTS erro_reincidencia_idx;
CREATE INDEX erro_reincidencia_idx ON erro_caderno (usuario_id, vezes DESC, ultima DESC);

-- -------------------------------------------------------------- simulado
ALTER TABLE simulado ADD COLUMN usuario_id BIGINT REFERENCES usuario(id);
UPDATE simulado SET usuario_id = 1 WHERE usuario_id IS NULL;
ALTER TABLE simulado ALTER COLUMN usuario_id SET NOT NULL;
CREATE INDEX simulado_usuario_idx ON simulado (usuario_id, criado_em DESC);

-- ---------------------------------------------------------------- edital
-- Cada usuário aponta pro seu próprio concurso-alvo (data de prova, banca).
ALTER TABLE edital ADD COLUMN usuario_id BIGINT REFERENCES usuario(id);
UPDATE edital SET usuario_id = 1 WHERE usuario_id IS NULL;
ALTER TABLE edital ALTER COLUMN usuario_id SET NOT NULL;
CREATE INDEX edital_usuario_idx ON edital (usuario_id, criado_em DESC);

-- ------------------------------------------------------- v_desempenho_disciplina
-- Refeita: dominadas/acertos agora dependem de progresso+tentativa POR
-- usuário, não só de questao. usuario_id entra no SELECT e no GROUP BY —
-- sem isso a view mistura desempenho de todo mundo numa linha só.
--
-- `questoes` (denominador da cobertura) precisa ficar sobre TODO o acervo
-- compartilhado da disciplina, não só sobre o que este usuário já tocou —
-- senão quem respondeu 2 de 18 e dominou as 2 mostraria 100% de cobertura.
-- Por isso o FROM parte de questao (cross join com os usuários que têm
-- QUALQUER progresso) e os LEFT JOIN entram depois, escopados por usuário.
-- (DROP já aconteceu mais acima, antes do DROP COLUMN em questao.)
CREATE VIEW v_desempenho_disciplina AS
SELECT u.usuario_id,
       q.disciplina,
       COUNT(DISTINCT q.id)                                          AS questoes,
       COUNT(DISTINCT q.id) FILTER (WHERE p.caixa >= 3)              AS dominadas,
       COUNT(t.id)                                                   AS tentativas,
       COUNT(t.id) FILTER (WHERE t.veredito = 'correta')             AS acertos,
       ROUND(100.0 * COUNT(t.id) FILTER (WHERE t.veredito = 'correta')
             / NULLIF(COUNT(t.id), 0), 1)::float8                    AS pct_acerto,
       ROUND(100.0 * COUNT(DISTINCT q.id) FILTER (WHERE p.caixa >= 3)
             / NULLIF(COUNT(DISTINCT q.id), 0), 1)::float8           AS cobertura_pct
FROM (SELECT DISTINCT usuario_id FROM progresso) u
CROSS JOIN questao q
LEFT JOIN progresso p ON p.usuario_id = u.usuario_id AND p.questao_id = q.id
LEFT JOIN tentativa t ON t.questao_id = q.id AND t.usuario_id = u.usuario_id
GROUP BY u.usuario_id, q.disciplina;

COMMIT;
