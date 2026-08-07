-- =====================================================================
-- ON DELETE CASCADE consistente em toda FK pra usuario.
--
-- A migração 008 só deu CASCADE em `progresso`; tentativa/erro_caderno/
-- simulado/edital ficaram RESTRICT (padrão do Postgres). Apagar uma conta
-- deveria apagar o rastro dela inteiro, não travar num FK esquecido — e
-- sem isso, testar com usuário descartável exige apagar cada tabela na
-- mão, na ordem certa, à mão (a mesma classe de erro documentada em
-- "Armadilhas de método": lógica de limpeza reescrita ad-hoc é onde bug
-- mora).
-- =====================================================================

BEGIN;

ALTER TABLE tentativa DROP CONSTRAINT tentativa_usuario_id_fkey;
ALTER TABLE tentativa ADD CONSTRAINT tentativa_usuario_id_fkey
  FOREIGN KEY (usuario_id) REFERENCES usuario(id) ON DELETE CASCADE;

ALTER TABLE erro_caderno DROP CONSTRAINT erro_caderno_usuario_id_fkey;
ALTER TABLE erro_caderno ADD CONSTRAINT erro_caderno_usuario_id_fkey
  FOREIGN KEY (usuario_id) REFERENCES usuario(id) ON DELETE CASCADE;

ALTER TABLE simulado DROP CONSTRAINT simulado_usuario_id_fkey;
ALTER TABLE simulado ADD CONSTRAINT simulado_usuario_id_fkey
  FOREIGN KEY (usuario_id) REFERENCES usuario(id) ON DELETE CASCADE;

ALTER TABLE edital DROP CONSTRAINT edital_usuario_id_fkey;
ALTER TABLE edital ADD CONSTRAINT edital_usuario_id_fkey
  FOREIGN KEY (usuario_id) REFERENCES usuario(id) ON DELETE CASCADE;

COMMIT;
