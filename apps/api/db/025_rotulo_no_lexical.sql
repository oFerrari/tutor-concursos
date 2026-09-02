-- O RÓTULO DO MATERIAL ENTRA NO ÍNDICE LEXICAL.
--
-- A 024 guardou o arquivo; o passo seguinte foi fazer a disciplina e o assunto
-- corrigidos pelo aluno valerem na BUSCA, e não só na lista e na geração de
-- questão. Metade disso o `material.texto_para_vetor` resolveu, prefixando o
-- texto que vai ao embedding. Medido numa apostila cujo corpo não menciona a
-- matéria: com o rótulo "Ciências Forenses / Papiloscopia", a consulta
-- "papiloscopia" saiu de FORA DO TOP6 para a posição 2.
--
-- A outra metade não veio, e a razão é aritmética: embedding é média, e 35
-- caracteres de rótulo contra 700 de corpo quase não movem o vetor. "ciências
-- forenses" continuou fora do top6 — justamente a consulta mais provável, que é
-- o nome da matéria.
--
-- Quem resolve isso é o lado LEXICAL da híbrida (`PESO_LEXICAL = 1.5`), que
-- casa palavra e não sentido. Só que `busca` é GENERATED sobre `texto`
-- sozinho, e o rótulo mora em `documento` — coluna gerada não atravessa tabela.
-- Daí a coluna `chunk.rotulo`: preenchida na indexação, entra no tsvector junto
-- do texto.
--
-- POR QUE NÃO BASTAVA PÔR O RÓTULO DENTRO DE `texto`: é `texto` que
-- `formatar_contexto` manda ao prompt, e o tutor leria "Ciências Forenses.
-- Papiloscopia." como se fosse conteúdo da apostila. A separação entre o que é
-- INDEXADO e o que é EXIBIDO é o ponto da mudança inteira.
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS rotulo text;

COMMENT ON COLUMN chunk.rotulo IS
  'disciplina/assunto do material do aluno, pra busca lexical; NULL em chunk de lei';

-- `busca` tem de ser recriada: não existe ALTER para a expressão de uma coluna
-- gerada. O rewrite recalcula o tsvector das 2.673 linhas — segundos nesta
-- escala, e a alternativa (coluna nova em paralelo) deixaria duas fontes de
-- verdade para "onde a busca lexical olha".
--
-- Chunk de LEI não muda de comportamento: `rotulo` é NULL, o `coalesce` devolve
-- string vazia e o tsvector sai idêntico ao de antes. Isso é verificável, e foi
-- verificado — `avaliar_retrieval.py` mede o mesmo antes e depois.
DROP INDEX IF EXISTS chunk_busca_idx;
ALTER TABLE chunk DROP COLUMN IF EXISTS busca;
ALTER TABLE chunk ADD COLUMN busca tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', texto || ' ' || coalesce(rotulo, ''))
  ) STORED;
CREATE INDEX chunk_busca_idx ON chunk USING GIN (busca);
