-- 036 — os ASSUNTOS de cada material, e de que assuntos cada trecho trata
--
-- POR QUE (30/09/2026)
-- --------------------
-- O material do aluno era uma sequência de trechos soltos com UM rótulo para o
-- arquivo inteiro (`documento.assunto` = "Verbos"). Nenhum trecho sabia de que
-- parte da apostila era, e "resumão de voz passiva", "questões de habeas
-- corpus" e "onde está X" dependiam de a busca por sentido acertar um trecho
-- solto. Assunto que começa em cima e retoma embaixo, ou que volta nas
-- questões comentadas do fim, não era juntado em lugar nenhum.
--
-- O QUE A MEDIÇÃO DECIDIU (bateria nas 18 apostilas da conta real, 29/09/2026)
-- -----------------------------------------------------------------------------
-- · Regras + vetores locais (sumário, títulos, agrupamento): 60–75% de precisão,
--   e o agrupamento juntava habeas corpus e mandado de segurança num grupo de 82
--   trechos. Fica como RESERVA, para quando falta cota.
-- · O MODELO lendo a apostila (1 chamada para a estrutura, lotes de 30 trechos
--   para a marcação): 72–77% com o modelo gratuito leve, julgado à mão; pegou
--   voz passiva em 18 dos 24 trechos que a mencionam (questões incluídas), e só
--   3 trechos misturaram habeas corpus com mandado de segurança.
--
-- DUAS TABELAS
-- ------------
-- `material_assunto`: a lista de assuntos de UM documento, na ordem, com as
-- páginas e o PAPEL (ensino, questões, outro). Refeita a cada indexação.
--
-- `chunk_assunto`: os assuntos de cada trecho — um trecho pode tratar de mais de
-- um, e um assunto vive em trechos de qualquer parte do material. `papel` diz se
-- o trecho ensina o assunto ou é questão sobre ele; `origem` diz quem marcou
-- (modelo, ou a reserva: seção pela página, expressão no texto).
--
-- `documento.assuntos_status`: 'pendente' (ainda não indexado), 'pronto' (pelo
-- modelo), 'reserva' (sem modelo — a refazer quando houver cota), 'falha'.
--
-- Privacidade: o assunto pertence ao documento, que pertence ao aluno; quem
-- lê filtra por `documento.usuario_id` (`core/indice.py`).

CREATE TABLE material_assunto (
    id            bigserial PRIMARY KEY,
    documento_id  bigint NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    ordem         smallint NOT NULL,
    nome          text NOT NULL CHECK (btrim(nome) <> ''),
    pagina_inicio integer,
    pagina_fim    integer,
    papel         text NOT NULL CHECK (papel IN ('ensino', 'questoes', 'outro')),
    origem        text NOT NULL CHECK (origem IN ('modelo', 'sumario', 'titulo')),
    UNIQUE (documento_id, ordem)
);

CREATE TABLE chunk_assunto (
    chunk_id    bigint NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    assunto_id  bigint NOT NULL REFERENCES material_assunto(id) ON DELETE CASCADE,
    papel       text NOT NULL CHECK (papel IN ('ensino', 'questao')),
    origem      text NOT NULL CHECK (origem IN ('modelo', 'secao', 'expressao')),
    PRIMARY KEY (chunk_id, assunto_id)
);

CREATE INDEX chunk_assunto_assunto_idx ON chunk_assunto (assunto_id);

ALTER TABLE documento ADD COLUMN assuntos_status text NOT NULL DEFAULT 'pendente'
    CHECK (assuntos_status IN ('pendente', 'pronto', 'reserva', 'falha'));
ALTER TABLE documento ADD COLUMN assuntos_em timestamptz;
