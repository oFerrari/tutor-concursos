-- 032 — o denominador do desempenho deixa de contar questão PRIVADA de outro aluno
--
-- O QUE ESTAVA ERRADO
-- -------------------
-- A view nasceu na 008, antes de existir questão privada (026). Ela faz
-- `CROSS JOIN questao` para contar "quantas questões a disciplina tem", e desde
-- a 026 isso inclui as questões geradas da APOSTILA de outro aluno. Não vaza
-- conteúdo — só o número —, mas o número mente e contradiz a tela vizinha.
--
-- Medido em 22/09/2026, depois de o material entrar na disciplina do edital a
-- que pertence (mesa-v5): Ciências Forenses tinha 30 questões no Desempenho e
-- 22 no Meu edital, para o mesmo aluno. As 8 de diferença eram privadas de
-- outras contas. `edital.cobertura` já usava `questoes.do_aluno`; a view não.
--
-- A REGRA É A MESMA DE `questoes.do_aluno`, com o dono vindo da própria linha
-- (u.usuario_id) em vez de parâmetro — numa view não há %(dono)s. Colunas,
-- tipos e ordem idênticos à 008, para CREATE OR REPLACE valer sem derrubar nada
-- que dependa da view.

CREATE OR REPLACE VIEW v_desempenho_disciplina AS
SELECT u.usuario_id,
       q.disciplina,
       COUNT(DISTINCT q.id)                                          AS questoes,
       COUNT(DISTINCT q.id) FILTER (WHERE p.caixa >= 3)              AS dominadas,
       COUNT(t.id)                                                   AS tentativas,
       COUNT(t.id) FILTER (WHERE t.veredito = 'correta')             AS acertos,
       ROUND(100.0 * COUNT(t.id) FILTER (WHERE t.veredito = 'correta')
             / NULLIF(COUNT(t.id), 0), 1)::float8                    AS pct_acerto,
       ROUND(100.0 * COUNT(DISTINCT q.id) FILTER (WHERE p.caixa >= 3)
             / NULLIF(COUNT(DISTINCT q.id), 0), 1)::float8           AS cobertura_pct
FROM (SELECT DISTINCT usuario_id FROM progresso) u
JOIN questao q ON q.usuario_id IS NULL OR q.usuario_id = u.usuario_id
LEFT JOIN progresso p ON p.usuario_id = u.usuario_id AND p.questao_id = q.id
LEFT JOIN tentativa t ON t.questao_id = q.id AND t.usuario_id = u.usuario_id
GROUP BY u.usuario_id, q.disciplina;
