-- =====================================================================
-- Migração 018 — o edital lembra PARA QUAL CARGO ele foi curado.
--
-- A curadoria (011) já pergunta "este edital tem N cargos, qual é o seu?" e
-- usa a resposta pra montar a lista de disciplinas. Mas a resposta morria ali:
-- `edital` só guardava título/órgão/banca/data, e `topico` guarda disciplina,
-- não cargo. Efeito na tela: a meta dizia "Ed_1_PF_25_Abertura" — nome de
-- ARQUIVO — sem dizer que aquele plano é de Perito Criminal Federal Área 3, e
-- não dos outros dezesseis cargos do mesmo edital. Num edital com 17 cargos,
-- omitir o cargo é omitir de quem é o plano.
--
-- COLUNA em `edital`, não em `topico`: o cargo é escolhido UMA vez para o
-- edital inteiro, não por matéria. Repeti-lo em cada linha de `topico` seria
-- denormalização com risco de divergir — o mesmo argumento que tirou
-- `edital.usuario_id` na migração 010.
--
-- NULLABLE de propósito, e são TRÊS casos legítimos de vazio, não um bug:
--   · concurso de cargo único (a pergunta nem aparece na curadoria);
--   · edital ingerido pela CLI (`edital.py`), que não tem tela de escolha;
--   · "meu cargo não está aqui" sem a pessoa digitar o nome — o campo é
--     opcional ali de propósito, porque exigir o nome pra deixar o aluno
--     seguir seria atrito sem ganho.
-- Quem lê tem que tratar NULL como "não declarado", nunca como erro.
-- =====================================================================

ALTER TABLE edital ADD COLUMN cargo TEXT;

COMMENT ON COLUMN edital.cargo IS
  'Cargo escolhido na curadoria (011). NULL = não declarado: cargo único, '
  'ingestão por CLI, ou o aluno seguiu sem nomear o próprio cargo.';
