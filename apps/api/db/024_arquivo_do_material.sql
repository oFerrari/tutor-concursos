-- O ARQUIVO ORIGINAL DO MATERIAL DO ALUNO, guardado no banco.
--
-- Até aqui o upload era extraído, chunkado, vetorizado e o arquivo DESCARTADO:
-- `documento.origem` guardava só o nome, e o docstring de `material.para_reindexar`
-- dizia isso na cara ("quem tem que reenviar o arquivo é ele"). A consequência
-- prática é a que o dono relatou: o PDF continuava preso no PC dele, e reler a
-- apostila exigia achar o arquivo de novo.
--
-- POR QUE NO BANCO E NÃO NO DISCO. Disco não atravessa máquina, e atravessar
-- máquina é o requisito ("quando chegar em casa não quero perder"). Dentro do
-- banco o arquivo viaja pelo mesmo caminho que todo o resto do estado, sem
-- serviço novo, sem credencial nova e sem uma segunda noção de "onde as coisas
-- ficam". O custo é tamanho, e ele foi medido antes de decidir: o banco tem
-- 59 MB hoje, o disco desta máquina tem 921 GB livres, e 20 apostilas somam
-- ~100 MB. Não é isso que vai apertar.
--
-- LOB (`bytea`) e não `large object`: `bytea` viaja em `pg_dump`, em réplica e
-- na exportação do `sincronizar.py` como qualquer coluna. `lo_*` exigiria
-- tratamento próprio em cada um desses três caminhos.
--
-- NULLABLE de propósito: todo material já ingerido fica sem arquivo, e isso é
-- correto — os bytes não existem mais. A tela mostra o botão de download apenas
-- onde `arquivo` não é nulo, em vez de prometer o que não pode entregar.
ALTER TABLE documento ADD COLUMN IF NOT EXISTS arquivo      bytea;
ALTER TABLE documento ADD COLUMN IF NOT EXISTS arquivo_tipo text;
ALTER TABLE documento ADD COLUMN IF NOT EXISTS arquivo_bytes integer;

-- `arquivo_bytes` é redundante com `length(arquivo)` e existe pra que a LISTA
-- da biblioteca possa dizer o tamanho sem ler o binário: `SELECT length(arquivo)`
-- puxa o LOB inteiro pra memória em toda listagem, e a lista é a tela mais
-- visitada da biblioteca.
COMMENT ON COLUMN documento.arquivo IS
  'bytes do arquivo original; NULL em material ingerido antes da 024';
COMMENT ON COLUMN documento.arquivo_bytes IS
  'tamanho em bytes, pra listar sem ler o binário';

-- Só material do ALUNO guarda arquivo. Corpus público vem de `corpus/`, que
-- está no git — guardar de novo aqui seria a mesma decisão que o `.gitignore`
-- do `acervo/` já recusou pra PDF de cursinho.
ALTER TABLE documento DROP CONSTRAINT IF EXISTS documento_arquivo_so_do_aluno;
ALTER TABLE documento ADD CONSTRAINT documento_arquivo_so_do_aluno
  CHECK (arquivo IS NULL OR usuario_id IS NOT NULL);
