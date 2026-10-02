-- 035 — o edital ligado ao material por SUBITEM: o que está coberto, onde, e o que falta
--
-- POR QUE (28/09/2026)
-- --------------------
-- O edital só se ligava ao material pela DISCIPLINA (`mesa.mapa_do_acervo`). O
-- tutor não sabia dizer "o item 2.1 está nas páginas 3 a 17 da sua Aula 00" nem
-- "o item 2.3 não está em material nenhum seu", e "seguir a ordem do edital" lia a
-- apostila na ordem da apostila. É a promessa "domina o seu edital" da tela de
-- entrada, e não existia.
--
-- O QUE A MEDIÇÃO DECIDIU (protótipo sobre um edital real e 17 apostilas)
-- ------------------------------------------------------------------------
-- · Busca por sentido sozinha NÃO decide cobertura: as notas do e5 ficam entre
--   0,82 e 0,87 para tudo, coberto ou não ("juros" empatou com "conectivos" numa
--   apostila só de proposições).
-- · Busca por EXPRESSÃO (phraseto_tsquery), com concentração por apostila, acerta
--   ~85% dos subitens e às vezes diz "coberto" onde não está. Por isso o modelo
--   CONFIRMA os candidatos que o texto acha; sem cota, fica o resultado por texto,
--   marcado `metodo = 'texto'` para ser refeito.
--
-- DUAS TABELAS
-- ------------
-- `edital_subitem`: um por subitem de cada tópico (o texto do tópico quebrado nos
-- ";"), com o estado da verificação. `pendente` = ainda não verificado — distinto
-- de `sem_material`, que é verificado e vazio. Cobertura que mente é pior que
-- cobertura inexistente, e "não sei" não pode aparecer como "não tem".
--
-- `edital_subitem_trecho`: os trechos que ENSINAM o subitem. As páginas saem daqui
-- na leitura (chunk.pagina), e reindexar um material apaga os trechos dele pelo
-- CASCADE — quem reindexa refaz o mapa daquela disciplina.
--
-- Privacidade: o subitem pertence ao tópico → edital → mesa → usuário, e o trecho
-- só é gravado se for do próprio aluno (quem grava é `core/cobertura.py`).

CREATE TABLE edital_subitem (
    id            bigserial PRIMARY KEY,
    topico_id     bigint NOT NULL REFERENCES topico(id) ON DELETE CASCADE,
    ordem         smallint NOT NULL,
    texto         text NOT NULL,
    estado        text NOT NULL DEFAULT 'pendente'
                  CHECK (estado IN ('pendente', 'coberto', 'citado', 'sem_material')),
    metodo        text CHECK (metodo IN ('texto', 'modelo', 'aluno')),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (topico_id, ordem)
);

CREATE TABLE edital_subitem_trecho (
    subitem_id bigint NOT NULL REFERENCES edital_subitem(id) ON DELETE CASCADE,
    chunk_id   bigint NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    PRIMARY KEY (subitem_id, chunk_id)
);

CREATE INDEX edital_subitem_trecho_chunk_idx ON edital_subitem_trecho (chunk_id);
