-- 013: texto-base compartilhado ("Texto associado") entre vários itens
--
-- O QUE FALTAVA
-- ------------------------------------------------------------------------
-- A 012 deu o item Certo/Errado, mas com `enunciado` sozinho — assertiva
-- avulsa. A prova real do Cebraspe raramente é assim: um TEXTO-BASE (uma
-- situação hipotética, um conjunto de proposições, um trecho de lei) é
-- seguido de N itens que o julgam de ângulos diferentes.
--
--   Considere as seguintes proposições de determinado deputado:
--   A: "Se eu não voto favorável à matéria, serei punido pela legenda.";
--   B: "Se sou punido pela legenda, posso decepcionar os eleitores.";
--   C: "Vou votar favoravelmente à matéria.".
--     · item 1 — [assertiva sobre A, B, C]
--     · item 2 — "…é correto concluir que os eleitores não poderão ficar
--                 decepcionados."   (CERTO/ERRADO)
--
-- Sem tabela própria só havia uma saída: repetir o texto-base dentro do
-- `enunciado` de cada item. Isso quebra três coisas de uma vez —
--   (1) os itens deixam de ser irmãos, então a tela não sabe dizer "item 2
--       de 4 sobre este texto" nem apresentá-los juntos;
--   (2) o mesmo texto vira N cópias divergentes na hora que uma delas for
--       corrigida;
--   (3) o SM-2 passa a reapresentar o texto-base inteiro pra revisar uma
--       assertiva de duas linhas.
--
-- POR QUE TABELA E NÃO COLUNA `contexto TEXT` EM `questao`
-- ------------------------------------------------------------------------
-- Coluna resolveria (3) e nenhuma das outras duas: o compartilhamento É a
-- estrutura. "Vários itens julgam o mesmo texto" é uma relação, e relação
-- se modela com chave, não com string repetida.
--
-- O contexto guarda `fonte_chunks` PRÓPRIO. Não é redundância com o da
-- questão: o texto-base pode ser construído sobre um artigo e os itens
-- cobrarem parágrafos diferentes dele — a proveniência de quem enunciou e a
-- de quem cobra não são necessariamente o mesmo trecho.
--
-- CASCADE, E É DELIBERADO
-- ------------------------------------------------------------------------
-- Item cujo texto-base sumiu é ILEGÍVEL: "com base no argumento acima" sem
-- o argumento não é questão difícil, é questão quebrada, e ela apareceria
-- na fila de alguém. Órfão silencioso é pior que apagar junto. Apagar
-- contexto não é operação de rotina — quem o fizer está apagando a série
-- inteira de propósito.
--
-- `contexto_id` é NULLABLE porque o item AVULSO continua legítimo: o
-- Cebraspe cobra os dois formatos, e toda questão que existe hoje (54) é
-- avulsa. NULL = "esta questão se basta", que é o estado anterior à 013.

CREATE TABLE contexto (
  id            BIGSERIAL PRIMARY KEY,
  documento_id  BIGINT REFERENCES documento(id) ON DELETE CASCADE,
  disciplina    TEXT NOT NULL,
  -- "Considere as seguintes proposições…", a situação hipotética, o trecho.
  texto         TEXT NOT NULL,
  fonte_chunks  BIGINT[] NOT NULL DEFAULT '{}',
  criada_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE questao
  ADD COLUMN contexto_id BIGINT REFERENCES contexto(id) ON DELETE CASCADE,
  -- Posição do item DENTRO da série ("item 2"). Sem ela a ordem viria do
  -- id, que é global e não diz nada sobre a série — e a ordem importa:
  -- itens do Cebraspe costumam encadear raciocínio.
  ADD COLUMN ordem_no_contexto SMALLINT;

ALTER TABLE questao
  ADD CONSTRAINT questao_ordem_exige_contexto
  CHECK ((contexto_id IS NULL) = (ordem_no_contexto IS NULL));

CREATE INDEX questao_contexto_idx ON questao (contexto_id, ordem_no_contexto)
  WHERE contexto_id IS NOT NULL;

COMMENT ON TABLE contexto IS
  'Texto-base compartilhado por vários itens ("Texto associado" do '
  'Cebraspe). NULL em questao.contexto_id = item avulso, que se basta.';
