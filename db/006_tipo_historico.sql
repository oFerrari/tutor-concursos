-- =====================================================================
-- Novo documento.tipo: 'historico'.
--
-- Para material que traz múltiplas versões do MESMO artigo (histórico de
-- emendas constitucionais, "Redação Anterior", texto revogado citado por
-- inteiro) — chunk_lei() extrai (norma, artigo) assumindo uma versão
-- vigente por artigo; um livro de histórico de emendas tem "Art. 1º"
-- repetido dezenas de vezes (uma por emenda + suas redações anteriores),
-- o que faz várias linhas de chunk colidirem no mesmo (norma, artigo) e
-- corrompe a citação exata — buscar "art. 50 CF" passaria a poder
-- devolver a versão REVOGADA em vez da vigente.
--
-- 'historico' cai em chunk_generico() (mesmo caminho de aula/resumo/
-- jurisprudencia): janela deslizante por parágrafo, sem tentar extrair
-- artigo. Sem exact-match por dispositivo, mas com busca híbrida --
-- normal, e sem risco de contaminar a citação exata do texto vigente.
-- =====================================================================

ALTER TABLE documento DROP CONSTRAINT documento_tipo_check;
ALTER TABLE documento ADD CONSTRAINT documento_tipo_check
  CHECK (tipo IN ('lei', 'aula', 'resumo', 'jurisprudencia', 'historico'));
