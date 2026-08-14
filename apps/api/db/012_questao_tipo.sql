-- 012: tipo de questão — item Certo/Errado (Cebraspe) ao lado da resposta livre
--
-- POR QUE O SCHEMA PRECISOU MUDAR
-- ------------------------------------------------------------------------
-- `questao.gabarito` é TEXT e sempre foi avaliado por `socratic.avaliar()`:
-- o aluno escreve, o modelo julga. Isso cobre bem a discursiva curta, e é o
-- único formato que existia. Só que a maior banca de concurso do país
-- (Cebraspe) cobra ITEM CERTO/ERRADO — assertiva única, resposta binária —
-- e o produto respondia "meu acervo não traz itens nesse formato".
--
-- Era verdade sobre a tabela e mentira sobre o sistema: o material de lei
-- está lá, e transformar artigo em assertiva é o que o modelo faz melhor.
-- Faltava onde GUARDAR a resposta binária.
--
-- POR QUE COLUNA NOVA E NÃO 'C'/'E' DENTRO DE `gabarito`
-- ------------------------------------------------------------------------
-- Guardar "C" num campo de texto livre parece barato e cobra caro depois:
-- nada impede gravar "Certo", "certo", "V", "verdadeiro", e a correção
-- vira normalização de string espalhada por quem consome. Com BOOLEAN, o
-- banco recusa o que não é resposta.
--
-- E `gabarito` continua NOT NULL e útil no item C/E: passa a guardar a
-- JUSTIFICATIVA (por que a assertiva está certa ou errada, com o
-- dispositivo). É o que a tela mostra depois de responder — sem ela, o
-- aluno acerta ou erra e não aprende nada, que é o oposto de tutor.
--
-- A CHECK CASADA É O CORAÇÃO DESTA MIGRAÇÃO
-- ------------------------------------------------------------------------
-- "item C/E sem gabarito booleano" e "questão discursiva com gabarito
-- booleano" são estados que não podem existir. Deixar isso por conta do
-- código significa que o primeiro caminho de escrita que esquecer a regra
-- grava lixo em silêncio — e são vários (gerar.py, geracao.sob_demanda,
-- sincronizar.py importar). A restrição fica no banco, onde todos passam.
--
-- TIPOS QUE NÃO ENTRARAM
-- ------------------------------------------------------------------------
-- Múltipla escolha (FGV, Vunesp) NÃO está aqui de propósito. Ela exige
-- tabela de alternativas com ordem e marcação da correta — modelagem
-- inteira, não uma coluna. Aceitar o valor 'multipla_escolha' no CHECK sem
-- ter onde guardar as alternativas criaria uma questão gravável e não
-- renderizável: pior que não suportar, porque falha depois, na tela do
-- aluno, e não na hora de gravar.

ALTER TABLE questao
  ADD COLUMN tipo TEXT NOT NULL DEFAULT 'resposta_livre',
  ADD COLUMN gabarito_ce BOOLEAN;

ALTER TABLE questao
  ADD CONSTRAINT questao_tipo_conhecido
  CHECK (tipo IN ('resposta_livre', 'certo_errado'));

ALTER TABLE questao
  ADD CONSTRAINT questao_gabarito_ce_casa_com_tipo
  CHECK (
    (tipo = 'certo_errado' AND gabarito_ce IS NOT NULL) OR
    (tipo <> 'certo_errado' AND gabarito_ce IS NULL)
  );

-- A fila e o simulado passam a poder pedir "só item C/E" (mesa de banca
-- Cebraspe). Índice parcial: os itens C/E são a minoria hoje, e um índice
-- sobre a coluna inteira não ajudaria a consulta que importa.
CREATE INDEX questao_tipo_ce_idx ON questao (disciplina) WHERE tipo = 'certo_errado';

COMMENT ON COLUMN questao.tipo IS
  'resposta_livre = discursiva curta avaliada por LLM; certo_errado = item '
  'Cebraspe, corrigido em código (booleano, sem modelo no meio)';
COMMENT ON COLUMN questao.gabarito_ce IS
  'Resposta do item C/E. NULL para resposta_livre (ver CHECK). A '
  'justificativa fica em `gabarito`, que segue NOT NULL nos dois tipos.';
