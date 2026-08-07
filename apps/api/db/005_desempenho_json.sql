-- =====================================================================
-- Estatísticas prontas para consumo por API/frontend, não só para leitura
-- humana no terminal.
--
-- ROUND(numeric, N) devolve NUMERIC, que o psycopg mapeia para Decimal —
-- json.dumps(Decimal) estoura TypeError. Casteando para float8 aqui, quem
-- expuser scheduler.desempenho() por HTTP no futuro faz json.dumps direto,
-- sem serializer customizado nem conversão na borda.
--
-- cobertura_pct entra junto: "percentual de desempenho por matéria" cobre
-- tanto acerto (respondeu certo) quanto domínio (caixa >= 3, sobreviveu à
-- repetição espaçada) — são dois números diferentes, um gráfico decente
-- vai querer os dois.
-- =====================================================================

-- CREATE OR REPLACE VIEW não permite trocar o tipo de coluna existente
-- (numeric -> float8); precisa recriar.
DROP VIEW v_desempenho_disciplina;

CREATE VIEW v_desempenho_disciplina AS
SELECT q.disciplina,
       COUNT(DISTINCT q.id)                                          AS questoes,
       COUNT(DISTINCT q.id) FILTER (WHERE q.caixa >= 3)              AS dominadas,
       COUNT(t.id)                                                   AS tentativas,
       COUNT(t.id) FILTER (WHERE t.veredito = 'correta')             AS acertos,
       ROUND(100.0 * COUNT(t.id) FILTER (WHERE t.veredito = 'correta')
             / NULLIF(COUNT(t.id), 0), 1)::float8                    AS pct_acerto,
       ROUND(100.0 * COUNT(DISTINCT q.id) FILTER (WHERE q.caixa >= 3)
             / NULLIF(COUNT(DISTINCT q.id), 0), 1)::float8           AS cobertura_pct
FROM questao q
LEFT JOIN tentativa t ON t.questao_id = q.id
GROUP BY q.disciplina;
