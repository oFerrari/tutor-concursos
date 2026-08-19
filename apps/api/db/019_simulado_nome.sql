-- =====================================================================
-- Nome do simulado — "2026-08-15 · 10/15 · 60%" não diferencia nada
-- quando existem três provas no mesmo dia (teste, revisão de Penal,
-- simulado de verdade). Opcional: sem nome, a tela cai pro rótulo por
-- data que já usava antes.
--
-- Apagar simulado do histórico NÃO apaga tentativa/progresso — a FK já
-- existente (`tentativa.simulado_id ... ON DELETE SET NULL`, migração
-- 004) cuida disso: a prova (o AGRUPAMENTO) some, o que foi aprendido
-- fica, porque simulado é snapshot de desempenho, não fonte de verdade
-- (mesmo argumento que já vale pra mesa apagada, migração 010).
-- =====================================================================

ALTER TABLE simulado ADD COLUMN nome TEXT;
COMMENT ON COLUMN simulado.nome IS
  'Rótulo opcional pra diferenciar provas no histórico — sem ele, a tela usa a data.';
