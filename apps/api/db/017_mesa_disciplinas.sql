-- 017: a mesa pode declarar as disciplinas SEM edital
--
-- O PROBLEMA REAL (relatado em uso)
-- ------------------------------------------------------------------------
-- Mesa recém-criada aparecia no lobby com "4 / 54 questões · 7%" e a
-- legenda "sem edital — mostra o acervo inteiro". O número é verdadeiro e
-- está no lugar errado: ele é o progresso da PESSOA no acervo todo, exibido
-- num cartão que promete o progresso DAQUELA mesa. Gaveta nova que já
-- nasce cheia.
--
-- POR QUE A CORREÇÃO **NÃO** É "SEM EDITAL, ESCOPO VAZIO"
-- ------------------------------------------------------------------------
-- Foi a primeira proposta e ela quebra mais do que conserta: `mesa.filtro`
-- com lista vazia não casa nada, então fila, desafio, simulado, stats e
-- meta ficam TODOS vazios. A mesa vira inútil até alguém subir um PDF — e
-- quem ainda não tem edital publicado (metade do tempo de preparação de
-- verdade) simplesmente não conseguiria estudar. Trocar "número confuso"
-- por "produto morto" não é conserto.
--
-- O problema também não era o filtro: era o CARTÃO afirmando ser progresso
-- de mesa um número que é do aluno. Isso se resolve na tela, e foi resolvido
-- lá (o cartão sem escopo não mostra mais barra nem percentual).
--
-- O QUE ESTA MIGRAÇÃO RESOLVE
-- ------------------------------------------------------------------------
-- O estado que faltava: "esta mesa TEM alvo, e não veio de PDF". Estudar
-- pra um concurso ainda sem edital publicado é o caso normal, não a
-- exceção, e até aqui a única forma de recortar uma mesa era subir um
-- arquivo que ainda não existe.
--
-- Com isso `mesa.disciplinas()` passa a ter três respostas, e as três
-- significam coisas diferentes:
--   · lista do EDITAL   — o alvo veio do PDF (continua tendo precedência:
--                         é o documento oficial, e é dele que a meta tira a
--                         data da prova; deixar o manual sobrepor faria o
--                         recorte vir de um lugar e o prazo de outro);
--   · lista MANUAL      — o aluno declarou o alvo na mão;
--   · None              — ninguém declarou nada ainda. Segue sem filtrar,
--                         que é o que mantém a mesa utilizável no dia 1.
--
-- TEXT[] E NÃO TABELA: é uma lista curta (uma dúzia de nomes), lida
-- inteira, escrita inteira, nunca consultada por item — o oposto do caso de
-- `topico`, que se conta, se agrupa por disciplina e vira cobertura. Tabela
-- aqui seria normalizar o que ninguém vai perguntar.

ALTER TABLE mesa
  ADD COLUMN disciplinas_manuais TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN mesa.disciplinas_manuais IS
  'Alvo declarado à mão, para mesa sem edital publicado. O edital tem '
  'precedência quando existe (ver core/mesa.disciplinas). Vazio = sem alvo '
  'declarado, e aí a mesa não filtra nada.';
