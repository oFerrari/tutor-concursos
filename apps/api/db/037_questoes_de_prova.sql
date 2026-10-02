-- 037 — QUESTÕES DE PROVA: o simulado que o aluno sobe vira banco de questões
--
-- POR QUE (30/09/2026)
-- --------------------
-- Até aqui toda questão do banco era GERADA pelo modelo a partir de um trecho.
-- O aluno sobe simulados comentados (100 questões de banca, com gabarito e o
-- comentário do professor), e eles entravam como "aula": o tutor lia o texto,
-- mas as questões não existiam como questão — nem cartão, nem fila, nem
-- caderno de erros. E a banca cobra MÚLTIPLA ESCOLHA, que o banco não tinha
-- (a 012 deixou de fora de propósito: sem tabela de alternativas, seria um tipo
-- gravável e não renderizável).
--
-- O QUE ENTRA
-- -----------
-- · `documento.tipo = 'simulado'`: o material de questões. Indexado como os
--   outros (a busca e o índice de assuntos o leem), e além disso cada questão
--   é extraída para `questao` (`core/prova.py`).
-- · `questao.tipo = 'multipla_escolha'` com `gabarito_letra` e as alternativas
--   em `questao_alternativa`. A letra é a do PDF (A–E; algumas bancas usam até
--   F) e o texto é literal.
-- · `questao.origem`: 'gerada' (o modelo escreveu a partir de um trecho — tudo
--   o que existia) ou 'prova' (veio do material do aluno, literal).
-- · `questao.numero_na_prova`: o número dela no simulado — é por ele que um
--   arquivo SÓ DE GABARITO, subido à parte, se casa com as questões.
-- · `questao.gabarito_fonte`: 'arquivo' (o próprio PDF ou o gabarito subido
--   junto) ou 'tutor' (o arquivo não trazia, o modelo resolveu — a tela diz
--   isso, e um gabarito oficial que chegue depois substitui).
-- · `documento.gabarito_de`: o arquivo só de respostas aponta para o simulado
--   que ele responde.
--
-- O QUE FICA PARA DEPOIS (e o desenho já comporta)
-- ------------------------------------------------
-- Converter entre formatos — a mesma questão de prova servida como C/E (cada
-- alternativa vira um item), por extenso (resposta livre) ou híbrida — é um
-- MODO DE APRESENTAR, não outra questão: sairá desta linha + das alternativas,
-- sem duplicar o banco. Por isso a alternativa guarda o texto literal e o
-- gabarito guarda a letra, não um booleano por alternativa.
--
-- INVARIANTES MANTIDAS
-- --------------------
-- · `fonte_chunks` aponta para o trecho REAL do simulado onde a questão está.
-- · O dono sai do documento (privado, 026): questão de prova tem `usuario_id`.
-- · C/E continua com `gabarito_ce` e só ele; múltipla escolha tem
--   `gabarito_letra` e só ela.

ALTER TABLE documento DROP CONSTRAINT IF EXISTS documento_tipo_check;
ALTER TABLE documento ADD CONSTRAINT documento_tipo_check
    CHECK (tipo IN ('lei', 'aula', 'resumo', 'jurisprudencia', 'historico', 'edital', 'simulado'));
ALTER TABLE documento ADD COLUMN gabarito_de bigint REFERENCES documento(id) ON DELETE SET NULL;
-- Contagem da última extração, para a tela e para refazer o que faltou.
ALTER TABLE documento ADD COLUMN questoes_extraidas integer;
ALTER TABLE documento ADD COLUMN questoes_sem_gabarito integer;

ALTER TABLE questao ADD COLUMN origem text NOT NULL DEFAULT 'gerada'
    CHECK (origem IN ('gerada', 'prova'));
ALTER TABLE questao ADD COLUMN numero_na_prova integer;
ALTER TABLE questao ADD COLUMN gabarito_letra text CHECK (gabarito_letra ~ '^[A-F]$');
ALTER TABLE questao ADD COLUMN gabarito_fonte text CHECK (gabarito_fonte IN ('arquivo', 'tutor'));

ALTER TABLE questao DROP CONSTRAINT IF EXISTS questao_tipo_conhecido;
ALTER TABLE questao ADD CONSTRAINT questao_tipo_conhecido
    CHECK (tipo IN ('resposta_livre', 'certo_errado', 'multipla_escolha'));
ALTER TABLE questao ADD CONSTRAINT questao_letra_casa_com_tipo
    CHECK ((tipo = 'multipla_escolha') = (gabarito_letra IS NOT NULL));
-- Questão de prova sabe de onde veio o gabarito e qual é o número dela.
ALTER TABLE questao ADD CONSTRAINT questao_de_prova_completa
    CHECK (origem <> 'prova' OR (gabarito_fonte IS NOT NULL AND numero_na_prova IS NOT NULL));
-- Uma questão por número em cada simulado: reextrair atualiza, não duplica.
CREATE UNIQUE INDEX questao_numero_na_prova_unico ON questao (documento_id, numero_na_prova)
    WHERE origem = 'prova';

CREATE TABLE questao_alternativa (
    questao_id bigint NOT NULL REFERENCES questao(id) ON DELETE CASCADE,
    letra      text NOT NULL CHECK (letra ~ '^[A-F]$'),
    texto      text NOT NULL CHECK (btrim(texto) <> ''),
    PRIMARY KEY (questao_id, letra)
);
