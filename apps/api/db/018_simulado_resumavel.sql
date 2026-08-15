-- =====================================================================
-- Simulado sobrevive a desconexão: hoje TODA resposta só chega ao banco
-- numa tacada só, no final (POST /simulados/{id}/respostas manda a lista
-- inteira de uma vez). Conexão cair, aba fechar ou bateria acabar no meio
-- da prova perde 100% do que foi respondido — nada foi salvo ainda.
--
-- `questao_ids` grava QUAL prova foi sorteada pra este simulado_id, coisa
-- que hoje não existe em lugar nenhum do banco (só existe na memória do
-- navegador, no array devolvido por POST /simulados). Sem isso, retomar
-- não tem como saber quais eram as N questões nem em que ordem.
--
-- `segundos_acumulados` é o relógio que sobrevive à pausa: tempo ativo de
-- prova, atualizado a cada resposta salva — não o tempo de parede entre
-- abrir e fechar a aba (isso incluiria a pausa pro banheiro, o que é
-- exatamente o que "pausar" existe pra não contar).
-- =====================================================================

ALTER TABLE simulado ADD COLUMN questao_ids BIGINT[];
ALTER TABLE simulado ADD COLUMN segundos_acumulados INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN simulado.questao_ids IS
  'Ordem exata sorteada pra este simulado — sem isso não dá pra retomar sabendo quais eram as N questões.';
COMMENT ON COLUMN simulado.segundos_acumulados IS
  'Tempo ATIVO de prova (exclui pausa) — atualizado a cada resposta salva, não só no finalizar.';

-- Defesa em profundidade: dentro de UM simulado, a mesma questão não pode
-- ganhar duas tentativas (reenvio por rede instável não deve contar duas
-- vezes). Fora de simulado (simulado_id NULL) isso não vale — a mesma
-- questão pode voltar pela fila SM-2 quantas vezes o algoritmo mandar.
CREATE UNIQUE INDEX tentativa_simulado_questao_unica
  ON tentativa (simulado_id, questao_id) WHERE simulado_id IS NOT NULL;
