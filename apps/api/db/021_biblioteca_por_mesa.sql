-- =====================================================================
-- Migração 021 — a biblioteca do aluno pode ser POR MESA.
--
-- Relatado em uso: "ele está salvando a minha biblioteca entre mesas de
-- estudo... ele estuda informática e não quer contaminar o ambiente dele com
-- direito". Está certo. A 019 pôs dono no material (`documento.usuario_id`) e
-- resolveu o vazamento ENTRE ALUNOS; não resolveu a separação DENTRO do mesmo
-- aluno. Quem prepara dois concursos ao mesmo tempo — o caso normal, e a razão
-- de a 010 existir — via o tutor citando a apostila de Direito Penal numa
-- pergunta de Redes.
--
-- DUAS colunas, e cada uma responde uma pergunta diferente:
--
--   documento.mesa_id            "de qual concurso é este material?"
--   mesa.biblioteca_compartilhada "esta mesa quer ler material dos outros?"
--
-- Uma só não bastaria. Marcar o material sem o interruptor obrigaria a decidir
-- na hora do upload e nunca mais mudar — e o pedido é explícito: "isso deve ser
-- alterado a qualquer instante por ele". O interruptor sem a marca não teria o
-- que filtrar.
--
-- `mesa_id` NULLABLE não é preguiça, é o POOL COMUM. Material subido antes
-- desta migração tem NULL, e NULL conta como "de todas as mesas": esconder o
-- que a pessoa já tinha subido seria apagar sem apagar, e ela não teria como
-- saber por que o tutor parou de citar a apostila dela. Vale também pra frente:
-- lei seca e material que serve a qualquer concurso ficam no pool.
--
-- ON DELETE SET NULL (e não CASCADE): apagar a mesa NÃO apaga o material. O PDF
-- é do ALUNO, não do concurso — a mesma decisão que fez `simulado -> mesa` ser
-- SET NULL na 010, e pelo mesmo motivo: a mesa é etiqueta, não dona. Perder a
-- apostila paga porque a mesa foi renomeada errado e apagada seria o pior
-- estrago possível nesta tela.
--
-- DEFAULT TRUE porque é o comportamento de HOJE. Quem já subiu material está
-- usando tudo em todas as mesas; entrar isolando calado mudaria o resultado do
-- tutor sem ninguém pedir. Isolar é opt-in, por mesa, reversível a qualquer
-- momento.
-- =====================================================================

ALTER TABLE documento ADD COLUMN mesa_id BIGINT REFERENCES mesa(id) ON DELETE SET NULL;

-- Só material privado tem mesa. O acervo público (`usuario_id IS NULL`) é de
-- todo mundo e de nenhuma mesa; um CHECK deixa isso executável em vez de
-- combinado, no mesmo espírito do CHECK casado da 012.
ALTER TABLE documento ADD CONSTRAINT documento_mesa_exige_dono
  CHECK (mesa_id IS NULL OR usuario_id IS NOT NULL);

-- A busca filtra por (dono, mesa) em toda pergunta do tutor: sem índice isso é
-- varredura na tabela que mais cresce.
CREATE INDEX documento_dono_mesa_idx ON documento (usuario_id, mesa_id);

ALTER TABLE mesa ADD COLUMN biblioteca_compartilhada BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN documento.mesa_id IS
  'Mesa que subiu este material (019/021). NULL = pool comum: material anterior '
  'a esta migração, ou que serve a qualquer concurso. Nunca preenchido para o '
  'acervo público.';

COMMENT ON COLUMN mesa.biblioteca_compartilhada IS
  'TRUE (default) = esta mesa lê o material de todas as mesas do aluno. FALSE = '
  'lê só o próprio e o pool comum (mesa_id NULL). Alternável a qualquer momento; '
  'não move nem apaga material, só muda o que a busca vê.';
