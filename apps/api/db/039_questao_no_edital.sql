-- 039 — a que ASSUNTO DO EDITAL pertence a questão que não chega lá pelo trecho
--
-- POR QUE (02/10/2026)
-- --------------------
-- O mapa de domínio (038) liga a questão ao edital pelo trecho de onde ela saiu
-- (índice do material). Questão de PROVA não tem esse caminho: o trecho é do
-- simulado, que fica fora do índice, e um trecho de simulado mistura matérias. A
-- reserva por palavras do enunciado é a técnica que a medição do 038 já
-- reprovou. Na bateria de estudo (dois meses simulados sobre a conta real), só 3
-- de 32 questões respondidas chegavam a um assunto pelo trecho: o mapa quase não
-- via o que o aluno respondia.
--
-- Mesmo arranjo do 038: o modelo do índice, um lote de enunciados por disciplina
-- contra os assuntos do edital dela. `topico_id` NULL = conferida, sem assunto.
CREATE TABLE questao_no_edital (
    questao_id bigint NOT NULL REFERENCES questao(id) ON DELETE CASCADE,
    edital_id  bigint NOT NULL REFERENCES edital(id) ON DELETE CASCADE,
    topico_id  bigint REFERENCES topico(id) ON DELETE CASCADE,
    origem     text NOT NULL CHECK (origem IN ('modelo', 'texto')),
    em         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (questao_id, edital_id)
);

CREATE INDEX questao_no_edital_topico_idx ON questao_no_edital (topico_id);
