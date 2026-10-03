-- 038 — a que ASSUNTO DO EDITAL cada assunto do material pertence (mapa de domínio)
--
-- POR QUE (02/10/2026)
-- --------------------
-- O mapa de domínio mostra o edital assunto por assunto: o que o aluno já leu
-- com o tutor, o que respondeu e onde está no ciclo de revisão. Para isso cada
-- trecho lido e cada questão respondida precisa chegar a um `topico`. A questão
-- só sabe `disciplina`, `tema` e `fonte_chunks`; o trecho sabe os assuntos do
-- índice (036). Falta a ponte assunto do material -> assunto do edital.
--
-- O QUE A MEDIÇÃO DECIDIU (conta real, edital de 110 assuntos, 119 nomes do índice)
-- ---------------------------------------------------------------------------------
-- · Ligação conferida do 035 (subitem <-> trecho): 1 de 108 questões chegava.
-- · Palavras em comum: "Verbos" caía em "Modos de organização discursiva" ("modo").
-- · Vetores locais (e5), pelo texto inteiro ou por subitem: "Princípios
--   fundamentais" -> "Direitos e garantias" com folga grande; folga não diz acerto.
-- · O MODELO, uma chamada por material: a lista de nomes do índice contra a lista
--   de assuntos do edital da disciplina. É o mesmo arranjo do 036.
--
-- Uma linha por (assunto do material, edital). `topico_id` NULL = conferido, não
-- pertence a assunto nenhum do edital — sem a linha, o par ficaria pendente para
-- sempre. Reindexar o material refaz `material_assunto` e o CASCADE apaga as
-- linhas: o par volta a pendente, que é o certo. `origem='texto'` é a reserva sem
-- cota, refeita quando houver.
CREATE TABLE assunto_no_edital (
    assunto_id bigint NOT NULL REFERENCES material_assunto(id) ON DELETE CASCADE,
    edital_id  bigint NOT NULL REFERENCES edital(id) ON DELETE CASCADE,
    topico_id  bigint REFERENCES topico(id) ON DELETE CASCADE,
    origem     text NOT NULL CHECK (origem IN ('modelo', 'texto')),
    em         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (assunto_id, edital_id)
);

CREATE INDEX assunto_no_edital_topico_idx ON assunto_no_edital (topico_id);
