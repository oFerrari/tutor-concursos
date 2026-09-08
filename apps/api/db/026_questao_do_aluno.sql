-- 026 — questão gerada do MATERIAL DO ALUNO
--
-- POR QUE
-- -------
-- Até aqui `questao` era acervo estritamente compartilhado (008): sem
-- usuario_id, porque questão saía só do corpus público (Planalto). O aluno
-- pedia questão sobre "traumatologia forense" — assunto que só existe na
-- apostila que ELE subiu — e recebia questão de Direito Penal, porque a
-- geração exigia `chunk.artigo IS NOT NULL` e nenhum chunk de apostila tem
-- artigo. O relato foi direto: "se você está trazendo a fonte de um lugar, o
-- certo é trazer questões dali também".
--
-- Gerar da apostila dentro de uma tabela compartilhada seria vazamento: o
-- enunciado carrega trecho de material pago de UM aluno, e a proveniência
-- aponta pra um chunk que os outros não podem ler. Daí a coluna.
--
-- SEMÂNTICA (a regra inteira)
-- ---------------------------
--   usuario_id IS NULL  -> acervo PÚBLICO, de todos, como toda questão até
--                          hoje. Nada precisa ser migrado: as existentes
--                          nascem NULL e seguem públicas.
--   usuario_id = N      -> questão gerada do material privado de N. Só N a
--                          vê, em qualquer pool (fila, desafio, simulado,
--                          lookup por id, cobertura do edital).
--
-- O predicado que implementa isso mora em UM lugar — `questoes.do_aluno()` —
-- pelo mesmo motivo de `mesa.filtro()`: espalhar cópias faz a fila e o
-- simulado divergirem, e aqui divergir significa mostrar material de outro.
ALTER TABLE questao
  ADD COLUMN usuario_id bigint REFERENCES usuario(id) ON DELETE CASCADE;

-- Parcial: só as privadas entram. As públicas são a maioria e não se
-- consulta por dono nelas — o índice existe pra "as minhas", não pra "as de
-- ninguém".
CREATE INDEX idx_questao_usuario ON questao (usuario_id)
  WHERE usuario_id IS NOT NULL;

COMMENT ON COLUMN questao.usuario_id IS
  'NULL = acervo público compartilhado; preenchido = gerada do material privado deste aluno, visível só pra ele';
