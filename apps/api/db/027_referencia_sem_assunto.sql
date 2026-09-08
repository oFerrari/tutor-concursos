-- 027 — material de REFERÊNCIA não tem "assunto"
--
-- O RELATO
-- --------
-- O aluno indexou a Constituição pelo link do Planalto, marcada como
-- jurisprudência. O classificador lê só o COMEÇO do material (`MAX_CHARS_CLASSE`)
-- e rotulou o documento inteiro — 1074 trechos — com "Princípios fundamentais e
-- direitos e garantias fundamentais", que é o que está nas primeiras páginas.
-- Nas palavras dele: "se fôssemos criar assunto da CF, iríamos ter que criar uma
-- quantidade imensurável de assuntos".
--
-- O DANO, MEDIDO
-- --------------
-- `assunto` não é só rótulo de tela: ele entra no texto que vira embedding e,
-- desde a 025, no tsvector de CADA trecho (`chunk.rotulo`). Um assunto falso em
-- 1074 trechos casa lexicalmente com qualquer consulta constitucional:
--
--   "princípios fundamentais do direito administrativo"
--      -> a cópia do aluno levava 6 de 6, devolvendo art. 88, art. 234, art. 18
--   "direitos e garantias fundamentais: remédios constitucionais"
--      -> art. 196 (saúde), art. 157, art. 55, art. 83
--
-- Relevância decidida por ruído. E é ESTE o mecanismo do defeito antigo "as
-- cópias da CF do aluno passam na frente da CF oficial", que estava em
-- LIMITACOES sem causa identificada: não era ser cópia, era o rótulo mentiroso
-- repetido mil vezes.
--
-- A REGRA
-- -------
-- `assunto` é rótulo de AULA — o título de uma coisa só ("Traumatologia
-- forense", "Lesão corporal"), e é o que faz a busca achar a aula 12 quando se
-- pergunta de asfixiologia. Poço de consulta não tem um: jurisprudência serve
-- de apoio a várias matérias, e uma norma inteira trata de centenas de
-- assuntos. Material fatiado por artigo já tem rótulo PRECISO por trecho
-- (`artigo`, `rubrica`) — melhor que um assunto único, não pior.
--
-- A disciplina FICA: ela é verdade em todos os trechos, e é por nome de
-- disciplina que `mesa.filtro` encontra o material.
--
-- Esta migração conserta as linhas que já existem. O `chunk.rotulo` é
-- recalculado aqui mesmo porque é ele que alimenta o tsvector (efeito
-- imediato, sem reindexar). O EMBEDDING dos trechos afetados continua com o
-- assunto dentro até o material ser reindexado — daí o status, que faz a fila
-- do `material.retomar_pendentes()` refazer os vetores sozinha.

-- 1. quem é referência: jurisprudência, ou material fatiado por artigo
--    (corpus de norma, independentemente do tipo escolhido na tela)
CREATE TEMP TABLE ref_027 AS
SELECT DISTINCT d.id
  FROM documento d
 WHERE d.usuario_id IS NOT NULL
   AND d.assunto IS NOT NULL
   AND (d.tipo = 'jurisprudencia'
        OR EXISTS (SELECT 1 FROM chunk c
                    WHERE c.documento_id = d.id AND c.artigo IS NOT NULL));

-- 2. o rótulo lexical do trecho ZERA — inclusive a disciplina.
--
--    A primeira versão desta migração deixava a disciplina, com o argumento de
--    que ela é VERDADE nos 1074 trechos. É verdade e não bastou: medido depois,
--    a cópia ainda levava 5 de 5 em "direitos e garantias fundamentais:
--    remédios constitucionais" (art. 196 da saúde, art. 6 dos direitos
--    sociais), enquanto a CF oficial, com os mesmos artigos, não aparecia.
--    "Direito Constitucional" casa "direitos"/"constitucionais" em TODOS os
--    trechos, e o trecho oficial tem rotulo NULL.
--
--    Num corpus de norma inteira o rótulo não DISTINGUE trecho nenhum: só
--    multiplica por mil um acerto que não informa nada. O que a 025 comprou é
--    outra coisa — o rótulo do material de AULA, onde ele distingue a aula 12
--    da aula 3, e aquela medição segue de pé.
--
--    `documento.disciplina` fica: dela saem o recorte da mesa
--    (`mesa.filtro('d.disciplina')`) e o agrupamento da tela.
UPDATE chunk
   SET rotulo = NULL
 WHERE documento_id IN (SELECT id FROM ref_027);

-- 3. o assunto sai do documento
UPDATE documento SET assunto = NULL WHERE id IN (SELECT id FROM ref_027);

-- 4. e o material volta pra fila, pra o EMBEDDING também perder o assunto.
--    `retomar_pendentes()` (chamado no startup da API) reindexa sozinho; até
--    lá o material continua buscável pelo lexical já corrigido.
UPDATE documento SET status = 'processando', erro = NULL
 WHERE id IN (SELECT id FROM ref_027) AND arquivo IS NOT NULL;
