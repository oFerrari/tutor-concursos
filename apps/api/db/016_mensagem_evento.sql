-- 016: mensagem de EVENTO na conversa — o que o aluno fez, não o que disse
--
-- O QUE FALTAVA
-- ------------------------------------------------------------------------
-- A 014 deu memória do que foi DITO. Mas no meio de uma conversa o aluno
-- também FAZ coisas: pede questão, responde, acerta, erra. Hoje isso
-- acontece fora do histórico — o tutor explica peculato, gera três itens, o
-- aluno erra os três, e na mensagem seguinte o tutor continua explicando
-- como se nada tivesse acontecido.
--
-- É a mesma classe de cegueira que a 014 corrigiu, um nível acima: lá o
-- modelo não via o turno anterior; aqui ele não vê o que o aluno demonstrou
-- entre um turno e outro. E é justamente essa a informação mais valiosa da
-- conversa inteira — dizer "não entendi" é relato, errar a questão é
-- evidência.
--
-- POR QUE UM AUTOR NOVO E NÃO REAPROVEITAR 'aluno'/'tutor'
-- ------------------------------------------------------------------------
-- Gravar "respondeu X e errou" como mensagem do ALUNO seria pôr na boca
-- dele uma frase que ele não escreveu; como mensagem do TUTOR, seria
-- inventar uma fala que o modelo nunca gerou. As duas mentem no lugar onde
-- a honestidade importa mais — o histórico que volta pro prompt e que o
-- aluno relê na tela.
--
-- 'evento' é o terceiro: fato registrado pelo sistema, exibido diferente
-- (não é balão de conversa) e lido pelo modelo como contexto, não como
-- fala. O CHECK cresce de dois pra três valores; nada do que existe muda.
--
-- POR QUE NÃO BASTA O RESUMO DE DESEMPENHO QUE JÁ VAI NO PROMPT
-- ------------------------------------------------------------------------
-- `_resumo_desempenho` é AGREGADO ("73% em Constitucional, 111
-- tentativas"): ele diz como a pessoa vai no geral, não o que ela acabou de
-- fazer nos últimos dois minutos. Um erro isolado some numa média de 111
-- tentativas — e é exatamente o erro isolado, recém-cometido, sobre o
-- assunto em discussão, que deveria mudar a próxima frase do tutor.

ALTER TABLE mensagem DROP CONSTRAINT mensagem_autor_check;

ALTER TABLE mensagem
  ADD CONSTRAINT mensagem_autor_check
  CHECK (autor IN ('aluno', 'tutor', 'evento'));

COMMENT ON COLUMN mensagem.autor IS
  'aluno = escreveu; tutor = o modelo gerou; evento = fato registrado pelo '
  'sistema (respondeu questão, acertou, errou). Evento não é fala de '
  'ninguém: entra no prompt como contexto e na tela como marca discreta.';
