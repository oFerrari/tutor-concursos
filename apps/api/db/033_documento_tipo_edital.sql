-- 033 — material que é EDITAL fica na biblioteca, mas fora da busca do tutor
--
-- O QUE ACONTECEU
-- ---------------
-- Em 24/09/2026 o aluno tinha, entre as apostilas, o edital de OUTRO concurso
-- (Transpetro) subido como aula. Sem disciplina nem assunto, ele não entrava
-- em recorte nenhum — e ainda assim a busca do chat, que não recorta por
-- disciplina, o trazia como fonte em três turnos de uma conversa sobre
-- Ciências Forenses. Edital é o mapa da prova, não matéria: ensinar a partir
-- dele é ensinar "das inscrições" e "do cronograma".
--
-- POR QUE UM TIPO E NÃO APAGAR
-- ----------------------------
-- O aluno subiu o arquivo; a decisão de apagar é dele. `tipo = 'edital'` é o
-- sistema dizendo o que o material É, com o mesmo efeito que já existe para
-- `historico`: continua listado, não vira fonte. Quem marca é
-- `material.parece_edital`, pela forma do texto, nunca pelo nome do concurso.
--
-- Mesmo molde da 006: troca a CHECK inteira, acrescentando um valor.

ALTER TABLE documento DROP CONSTRAINT documento_tipo_check;
ALTER TABLE documento ADD CONSTRAINT documento_tipo_check
    CHECK (tipo IN ('lei', 'aula', 'resumo', 'jurisprudencia', 'historico', 'edital'));
