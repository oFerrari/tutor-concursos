-- =====================================================================
-- Migração 020 — o sistema descobre do que é o material; o aluno não precisa.
--
-- A 019 exigia `disciplina` no upload, e a exigência não se sustentou no
-- primeiro uso real: subir 14 aulas de um curso significa digitar a mesma
-- disciplina 14 vezes, e o pior caso é o material que a pessoa NÃO conhece —
-- "joguei lá, não sei se agrega". Obrigar a rotular é obrigar a LER antes de
-- subir, o que inverte quem trabalha: era o sistema que devia dizer do que
-- se trata.
--
-- `disciplina` passa a ser NULLABLE, e o NULL é um estado com nome:
-- "ainda não sei". A tela mostra "identificando…" enquanto isso, e o
-- classificador preenche. Continua editável — o palpite do modelo é palpite,
-- e a lista da tela é que vale (mesmo princípio da curadoria de edital).
--
-- `assunto` é o nível abaixo, e existe porque um curso inteiro cai na MESMA
-- disciplina: 14 aulas de Direito Constitucional só se distinguem por
-- "Aplicabilidade das normas", "Remédios constitucionais", "Controle de
-- constitucionalidade". Sem ele a biblioteca vira uma lista de 14 linhas
-- indistinguíveis, e agrupar por disciplina não ajuda ninguém.
--
-- TEXTO LIVRE nos dois, e isto é deliberado ao contrário de `usuario.perfil`
-- (015, lista fechada validada na escrita E na leitura): perfil vai pro
-- PROMPT do tutor, então campo livre ali é injeção de instrução. Disciplina e
-- assunto vão pra WHERE de recorte e pra rótulo de tela — o pior caso é uma
-- string que não casa nada, não uma instrução obedecida.
--
-- `classificado_por` registra a PROCEDÊNCIA. Não é enfeite: "o aluno disse"
-- e "o modelo achou" têm confiabilidade diferente, e a tela precisa poder
-- dizer qual foi (o palpite merece um "confira", o que a pessoa digitou não).
-- =====================================================================

ALTER TABLE documento ALTER COLUMN disciplina DROP NOT NULL;

ALTER TABLE documento
  ADD COLUMN assunto          TEXT,
  ADD COLUMN classificado_por TEXT
    CHECK (classificado_por IN ('aluno', 'modelo', 'acervo'));

COMMENT ON COLUMN documento.disciplina IS
  'NULL = ainda não classificado (o classificador roda em background). '
  'Editável pelo aluno depois; o palpite do modelo é palpite.';
COMMENT ON COLUMN documento.assunto IS
  'Um nível abaixo da disciplina ("Remédios constitucionais"). É o que '
  'distingue 14 aulas do mesmo curso entre si. NULL = não identificado.';
COMMENT ON COLUMN documento.classificado_por IS
  'aluno = digitou; modelo = LLM leu o começo do texto; acervo = deduzido '
  'por semelhança com material já indexado (sem custo de cota).';
