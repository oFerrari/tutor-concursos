-- =====================================================================
-- Mesa de estudo — o alvo (concurso) que dá contexto à sessão.
--
-- DECISÃO CENTRAL: mesa é FILTRO, não silo. `progresso`, `tentativa` e
-- `erro_caderno` continuam escopados por `usuario_id` e NÃO ganham
-- mesa_id — a memória SM-2 é do ALUNO, não do concurso. Quem dominou o
-- art. 312 estudando pra PC-PR sabe o art. 312 na mesa da PF; duplicar a
-- caixa por mesa faria a mesma pessoa reestudar do zero o que já sabe,
-- que é exatamente o oposto do que repetição espaçada existe pra fazer
-- (e o concurseiro real reaproveita Português/Constitucional entre
-- editais o tempo todo).
--
-- O que a mesa faz é RECORTAR: fila, dashboard, caderno e simulado
-- passam a mostrar só as disciplinas do edital daquela mesa. E o recorte
-- seria necessário DE QUALQUER JEITO — `questao` é acervo compartilhado e
-- global (migração 008), então sem filtro por disciplina toda mesa
-- mostraria o acervo inteiro. Isolamento total seria este filtro MAIS
-- duplicação do estado de aprendizado; o filtro sozinho entrega o mesmo
-- produto sem a duplicação.
--
-- Consequência: as disciplinas da mesa NÃO são uma coluna, são derivadas
-- de `topico.disciplina` do edital mais recente dela (ver
-- core/mesa.py:disciplinas). Mesa sem edital não filtra nada — mostra o
-- acervo todo, que é o comportamento de antes desta migração.
--
-- DUAS FKs COM POLÍTICAS DIFERENTES, de propósito:
--   edital   -> mesa  ON DELETE CASCADE   (o edital É o conteúdo da mesa;
--                                          apagar a mesa apaga o edital)
--   simulado -> mesa  ON DELETE SET NULL  (o simulado é histórico de
--                                          desempenho da PESSOA, só
--                                          etiquetado com a mesa; apagar
--                                          a mesa não deve sumir com a
--                                          prova que ela já fez)
--
-- `edital.usuario_id` SAI: o edital agora pertence à mesa, e a mesa ao
-- usuário. Manter as duas colunas seria denormalização com risco de
-- divergir (edital de uma mesa apontando pra outro dono). O CASCADE
-- continua chegando na conta: usuario -> mesa -> edital -> topico.
--
-- TRANSAÇÃO ÚNICA, mesma lição da 008: se o backfill falhar no meio, o
-- DROP COLUMN não executa e nada fica pela metade.
-- =====================================================================

BEGIN;

CREATE TABLE mesa (
  id         BIGSERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  nome       TEXT NOT NULL,
  orgao      TEXT,
  banca      TEXT,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Nome único POR USUÁRIO: duas pessoas podem ter cada uma a sua mesa
  -- "PF Agente"; a mesma pessoa com duas mesas de nome igual não teria
  -- como distinguir uma da outra na tela nem no `--mesa` da CLI.
  UNIQUE (usuario_id, nome)
);

CREATE INDEX mesa_usuario_idx ON mesa (usuario_id, criado_em);

-- Toda conta existente ganha uma mesa. Sem isso, `edital.mesa_id NOT NULL`
-- não teria pra onde apontar no backfill — e é o mesmo default que
-- core/mesa.py:padrao() cria sozinho pra conta nova (mesmo espírito de
-- auth.usuario_da_cli: o recurso existe quando for preciso, não exige
-- ritual de criação antes do primeiro uso).
INSERT INTO mesa (usuario_id, nome) SELECT id, 'Mesa principal' FROM usuario;

-- ---------------------------------------------------------------- edital
ALTER TABLE edital ADD COLUMN mesa_id BIGINT REFERENCES mesa(id) ON DELETE CASCADE;
UPDATE edital e
   SET mesa_id = (SELECT m.id FROM mesa m
                   WHERE m.usuario_id = e.usuario_id ORDER BY m.id LIMIT 1);
ALTER TABLE edital ALTER COLUMN mesa_id SET NOT NULL;
DROP INDEX IF EXISTS edital_usuario_idx;
ALTER TABLE edital DROP COLUMN usuario_id;
CREATE INDEX edital_mesa_idx ON edital (mesa_id, criado_em DESC);

-- -------------------------------------------------------------- simulado
-- Etiqueta, não posse: `usuario_id` CONTINUA aqui e continua sendo o que
-- `simulado.pertence_a()` checa. mesa_id só responde "de qual mesa foi
-- esta prova" — por isso pode ser NULL (prova anterior às mesas, ou mesa
-- apagada depois).
ALTER TABLE simulado ADD COLUMN mesa_id BIGINT REFERENCES mesa(id) ON DELETE SET NULL;
UPDATE simulado s
   SET mesa_id = (SELECT m.id FROM mesa m
                   WHERE m.usuario_id = s.usuario_id ORDER BY m.id LIMIT 1);
CREATE INDEX simulado_mesa_idx ON simulado (mesa_id, criado_em DESC);

COMMIT;
