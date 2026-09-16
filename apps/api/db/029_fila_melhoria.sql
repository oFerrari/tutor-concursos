-- 029 — feedback do aluno sobre a RESPOSTA, amarrado à resposta
--
-- O PEDIDO
-- --------
-- "Quero dar feedback in-loco no chat e o sistema deve salvar isso amarrado ao
-- histórico exato da conversa para debug futuro." Hoje o caminho é sair do
-- estudo, abrir uma conversa com um agente e descrever de memória o que o tutor
-- respondeu. O que se perde nessa travessia é justamente o que resolve o
-- defeito: QUAL resposta, com QUAIS trechos, em QUAL ponto da conversa.
--
-- POR QUE `mensagem_tutor_id` E NÃO SÓ O TEXTO DO FEEDBACK
-- --------------------------------------------------------
-- O texto sozinho envelhece em horas ("ele respondeu errado sobre princípios").
-- A chave estrangeira não: dela saem a resposta literal, as `fontes` daquele
-- turno (JSONB na própria `mensagem`), a conversa inteira antes e depois, e a
-- mesa em que aquilo aconteceu. É o mesmo raciocínio de `questao.fonte_chunks`
-- — proveniência é o que separa um relato de um caso reproduzível.
--
-- NULL É ESTADO LEGÍTIMO ali: o aluno pode reclamar antes de o tutor ter dito
-- qualquer coisa na conversa nova. Perder o feedback por causa disso seria
-- trocar o dado que existe pelo que falta.
--
-- POR QUE NÃO TEM `usuario_id`
-- ----------------------------
-- Quem autoriza é a conversa, e a rota só chega aqui depois de `conversa.obter`
-- confirmar que ela é de quem perguntou — mesma porta única de `questoes
-- .do_aluno()`. Coluna repetida seria uma segunda fonte de verdade sobre posse,
-- e o CASCADE de `conversa` (que já cascateia de `usuario`, pela 009) leva esta
-- linha junto quando a conta é apagada.
CREATE TABLE fila_melhoria (
  id                BIGSERIAL PRIMARY KEY,
  conversa_id       BIGINT NOT NULL REFERENCES conversa(id) ON DELETE CASCADE,
  -- A resposta do tutor que o feedback comenta: a ÚLTIMA antes do comando.
  -- SET NULL e não CASCADE: apagar uma mensagem não pode apagar a reclamação
  -- sobre ela — o texto do aluno continua valendo sem o alvo.
  mensagem_tutor_id BIGINT REFERENCES mensagem(id) ON DELETE SET NULL,
  feedback_texto    TEXT NOT NULL CHECK (btrim(feedback_texto) <> ''),
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Ciclo de vida do item: 'pendente' -> o que o dono decidir depois. TEXT com
  -- default e sem CHECK de propósito: os estados ainda não existem, e inventar
  -- a lista agora seria congelar um vocabulário que ninguém usou.
  status            TEXT NOT NULL DEFAULT 'pendente'
);

-- A leitura que existe é "o que está pendente, mais novo primeiro" — é ela que
-- o índice serve.
CREATE INDEX fila_melhoria_pendentes_idx ON fila_melhoria (status, criado_em DESC);

COMMENT ON TABLE fila_melhoria IS
  'Feedback que o aluno dá DENTRO do chat (/erro, /feedback), preso à resposta que ele comenta';
COMMENT ON COLUMN fila_melhoria.mensagem_tutor_id IS
  'última resposta do tutor antes do comando; NULL quando ele reclamou antes de haver resposta na conversa';
COMMENT ON COLUMN fila_melhoria.status IS
  'pendente por padrão; sem CHECK porque os outros estados ainda não foram decididos';
