-- 031 — o DIÁRIO DE CLASSE: o que o aluno estudou conversando, sem responder nada
--
-- O BURACO QUE ESTA TABELA FECHA
-- ------------------------------
-- Levantamento de 16/09/2026: o tutor sabia tudo sobre o que o aluno RESPONDEU
-- (v_desempenho_disciplina, caderno de erros, conceitos da 022) e nada sobre o
-- que ele CONVERSOU. Duas horas de teoria sobre peculato, sem uma questão,
-- deixavam rastro zero: no dia seguinte, conversa nova, `### Conversa até aqui`
-- dizia "Primeira mensagem desta conversa" e o tutor começava do zero — depois
-- de o prompt mandar, na Seção 10, que ele NÃO é uma sessão em branco. A regra
-- existia sem a matéria-prima, e o modelo preenchia o vão inventando ou se
-- esquivando.
--
-- POR QUE UMA LINHA POR (ALUNO, DIA, ASSUNTO) E NÃO POR TURNO
-- -----------------------------------------------------------
-- A pergunta que isto responde é "o que estudamos ontem?", e ela é do tamanho
-- do DIA. Uma linha por turno faria a leitura do prompt somar no Python a cada
-- pergunta, e a janela de 8 turnos já ensinou que prompt não perdoa volume.
-- `turnos` acumulando no UPSERT dá a intensidade ("três turnos" vs "vinte") sem
-- guardar o texto de novo: o texto já está em `mensagem`, e duplicá-lo aqui
-- seria uma segunda fonte de verdade sobre a mesma conversa.
--
-- POR QUE NÃO TEM `conversa_id`
-- -----------------------------
-- De propósito, e é o ponto do produto: o diário precisa ATRAVESSAR a conversa.
-- Amarrá-lo ao `conversa_id` reproduziria exatamente a amnésia que ele existe
-- pra curar — o aluno abre o chat amanhã, nasce outra conversa, e o rastro
-- ficaria preso na de ontem. Quem pergunta é o ALUNO, não a janela.
--
-- POR QUE NÃO TEM TEXTO DE LLM
-- ----------------------------
-- `assunto` é rótulo COLHIDO, não resumo gerado: sai da rubrica do artigo
-- recuperado ("Peculato") ou do assunto classificado do material do aluno
-- ("Traumatologia forense"), que já são texto do acervo. Resumir a sessão com
-- uma chamada de LLM custaria cota por turno e colocaria prosa de modelo dentro
-- de um prompt de modelo — o mesmo cuidado que a 022 teve com
-- `conceito_faltante`, que entra no prompt citado e com autoria.
--
-- A DISCIPLINA É O QUE PERMITE DIZER "E NÃO TESTOU"
-- -------------------------------------------------
-- Guardada junto porque é a chave que cruza com `tentativa`/`questao` para
-- responder a pergunta que o dono formulou: "você já viu bastante o conceito de
-- tal coisa, porém não resolveu nenhuma questão ainda". Sem ela, o diário diria
-- o que foi conversado e não saberia dizer o que FALTOU.
CREATE TABLE estudo_teoria (
  id          BIGSERIAL PRIMARY KEY,
  usuario_id  BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  -- DATA e não timestamp: a unidade da pergunta é o dia de calendário.
  dia         DATE NOT NULL DEFAULT CURRENT_DATE,
  -- Teto de 120 caracteres pelo mesmo motivo da 022: isto vai INTEIRO pro
  -- prompt, e rótulo longo empurra o trecho de lei pra fora da janela.
  assunto     TEXT NOT NULL CHECK (btrim(assunto) <> '' AND length(assunto) <= 120),
  disciplina  TEXT,
  turnos      INTEGER NOT NULL DEFAULT 1 CHECK (turnos >= 1),
  primeiro_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ultimo_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- O UPSERT do dia inteiro depende desta chave.
  UNIQUE (usuario_id, dia, assunto)
);

-- A leitura é sempre "os últimos dias deste aluno".
CREATE INDEX idx_estudo_teoria_recente ON estudo_teoria (usuario_id, dia DESC, turnos DESC);
