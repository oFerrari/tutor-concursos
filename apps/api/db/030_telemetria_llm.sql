-- 030 — telemetria de consumo do LLM: quanto, de qual modelo, e quantos 429
--
-- O PEDIDO
-- --------
-- "Acho que gastei minha cota, tem como eu ver um painel do gasto e quando vai
-- resetar? Quero ver o nome do modelo ativo e o gasto dele também." O 429 do
-- free tier derrubou uma bateria inteira de `./testar.sh` e não havia como
-- saber, de dentro do projeto, quanto tinha sido gasto nem por quem.
--
-- POR QUE NO BANCO E NÃO NUM ARQUIVO DE LOG
-- -----------------------------------------
-- O dado já é relacional e a pergunta é agregada ("quantos tokens hoje, por
-- modelo"). JSONL exigiria varrer e somar em Python a cada consulta, e some
-- quando a máquina troca — `sincronizar.py` leva o banco, não o `.logs/`.
--
-- POR QUE NÃO TEM `usuario_id`
-- ----------------------------
-- A cota é da CHAVE, não da conta: quem estoura o free tier é o projeto
-- inteiro somado (chat, geração de questão, extração de edital, avaliador
-- sintético). Recortar por aluno responderia outra pergunta, e a coluna
-- `origem_chamada` já diz de onde veio sem amarrar a linha a ninguém.
--
-- POR QUE `tokens_*` É NULLABLE
-- -----------------------------
-- Falha não tem `usageMetadata`: um 429 é justamente a chamada que NÃO gerou
-- nada, e é a linha mais importante da tabela. Zerar seria mentir que houve
-- consumo nulo medido; NULL diz "não houve medição", que é o fato.
--
-- MODELO É O QUE RESPONDEU, não o que foi pedido. `core/llm.py` tenta o
-- `GEMINI_MODEL` e cai nas reservas; gravar o configurado apagaria exatamente
-- a informação que o dono pediu ("o nome do modelo ativo").
CREATE TABLE telemetria_llm (
  id             BIGSERIAL PRIMARY KEY,
  provedor       TEXT NOT NULL,
  modelo         TEXT NOT NULL,
  tokens_input   INTEGER CHECK (tokens_input  IS NULL OR tokens_input  >= 0),
  tokens_output  INTEGER CHECK (tokens_output IS NULL OR tokens_output >= 0),
  -- HTTP da última tentativa: 200 no sucesso, 429 na cota, 0 quando nem houve
  -- resposta (timeout, rede). Inteiro e não enum: código HTTP novo não deve
  -- exigir migração.
  status_code    INTEGER NOT NULL,
  -- De onde a chamada saiu, no formato "modulo.funcao" — socratic.explicar,
  -- geracao.sob_demanda, edital.extrair. Calculado da pilha em `core/llm.py`,
  -- sem parâmetro novo em nenhum chamador.
  origem_chamada TEXT,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- O painel pergunta sempre por JANELA DE TEMPO ("hoje"), e depois agrupa.
CREATE INDEX idx_telemetria_llm_quando ON telemetria_llm (criado_em DESC);
