-- =====================================================================
-- Migração 019 — a biblioteca do aluno: material PRIVADO conviver com o
-- acervo COMPARTILHADO na mesma tabela.
--
-- A tela /materiais promete "só você tem acesso a este material", e isso
-- colidia de frente com a decisão da 008: `documento`/`chunk`/`questao` não
-- têm `usuario_id` porque é o mesmo Código Penal pra todo mundo. Continua
-- verdade pra LEI — e deixa de ser pra apostila, resumo manuscrito e PDF de
-- curso pago, que é exatamente o que esta tela recebe. Sem dono, o material
-- de um aluno entraria no `retrieval.buscar` de todos os outros: além de
-- vazar conteúdo pago, poluiria a resposta do tutor com material que a
-- pessoa nem tem.
--
-- `usuario_id` NULLABLE, e o NULL é o caso ANTIGO, não o novo:
--   · NULL             -> acervo compartilhado (lei pública via `ingest.py`)
--   · preenchido       -> material privado daquele aluno
-- Assim toda linha que já existe segue pública sem precisar de UPDATE, e
-- quem lê tem uma regra só: "vejo o público MAIS o meu".
--
-- CASCADE porque material privado é do aluno: apagar a conta leva a
-- biblioteca dela, igual `progresso`/`tentativa` na 009.
-- =====================================================================

ALTER TABLE documento ADD COLUMN usuario_id BIGINT
  REFERENCES usuario(id) ON DELETE CASCADE;

CREATE INDEX documento_usuario_idx ON documento (usuario_id, criado_em DESC);

-- ---------------------------------------------------------------------
-- HASH: dois índices PARCIAIS no lugar de um UNIQUE global.
--
-- O UNIQUE(hash) existia por um bug real e caro: rodar `ingest.py` de novo
-- com o CP criou um documento DUPLICADO (434 chunks a mais) e o
-- `sincronizar.py` seguinte reescreveu `fonte_chunks` de 18 questões
-- apontando pro duplicado errado. Essa proteção NÃO pode se perder.
--
-- Mas ela não pode valer entre alunos: dois candidatos ao mesmo concurso
-- compram a mesma apostila, e o segundo a subir não pode ouvir "já foi
-- ingerido" sobre um arquivo que ele não tem.
--
-- UNIQUE com NULL não resolve: no Postgres NULLs são distintos entre si, um
-- UNIQUE(hash, usuario_id) deixaria N cópias públicas do CP passarem — o
-- bug de volta. Daí os dois índices parciais: um por hash no público, outro
-- por (hash, dono) no privado.
-- ---------------------------------------------------------------------
ALTER TABLE documento DROP CONSTRAINT documento_hash_key;

CREATE UNIQUE INDEX documento_hash_publico_idx ON documento (hash)
  WHERE usuario_id IS NULL AND hash IS NOT NULL;

CREATE UNIQUE INDEX documento_hash_privado_idx ON documento (hash, usuario_id)
  WHERE usuario_id IS NOT NULL AND hash IS NOT NULL;

-- ---------------------------------------------------------------------
-- ESTADO DO PROCESSAMENTO. A tela já desenha três estados e um progresso
-- ("IA lendo e processando… 187 de 340"), e o motivo de existirem é físico:
-- o embedding roda LOCAL na CPU (decisão em "Pilha"), então um PDF de 800
-- trechos leva minutos. Processar dentro do request daria timeout no
-- navegador; sem estado no banco, um F5 no meio perderia a única pista de
-- que algo está acontecendo.
--
-- `erro` guarda a razão em texto porque "falhou" sozinho não deixa o aluno
-- agir: "PDF protegido" e "provavelmente escaneado, precisa de OCR" pedem
-- providências diferentes — mesmo princípio de 409-não-500 na geração.
-- ---------------------------------------------------------------------
ALTER TABLE documento
  ADD COLUMN status        TEXT NOT NULL DEFAULT 'pronto'
    CHECK (status IN ('processando', 'pronto', 'falha')),
  ADD COLUMN chunks_total  INTEGER,
  ADD COLUMN erro          TEXT;

COMMENT ON COLUMN documento.usuario_id IS
  'NULL = acervo compartilhado (lei pública). Preenchido = material privado '
  'do aluno, visível só pra ele em retrieval.buscar.';
COMMENT ON COLUMN documento.status IS
  'processando = embedding em curso; pronto = indexado; falha = ver erro. '
  'Linha antiga entra como pronto pelo DEFAULT.';
COMMENT ON COLUMN documento.chunks_total IS
  'Total ESPERADO de trechos, gravado antes de indexar. Com o count() real '
  'de chunk, dá o "187 de 340" que a tela mostra.';
