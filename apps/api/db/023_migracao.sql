-- =====================================================================
-- Migração 023 — o livro-razão das migrações.
--
-- Até aqui NADA no banco sabia quais das 22 migrações já tinham rodado. O
-- controle era humano e o CLAUDE.md registrava a consequência: aplicar na mão,
-- e "commitar a migração não é aplicar a migração". Custou o módulo de
-- Simulados/Estatísticas inteiro rodando contra a view antiga sem avisar.
--
-- O modo de falha é o pior que existe: a aplicação SOBE e quebra depois, num
-- lugar que não tem relação óbvia com o schema. Nada falha na hora em que o
-- erro é cometido.
--
-- `CREATE TABLE IF NOT EXISTS` de propósito: `migrar.py` cria esta tabela ANTES
-- de aplicar qualquer coisa (senão não teria onde registrar o que aplicou), e
-- depois aplica este arquivo como qualquer outro. Sem o IF NOT EXISTS ele
-- morreria no primeiro passo do banco novo. Dois caminhos, um resultado.
--
-- `nome` (e não número) como chave: os 018/019 estão DUPLICADOS neste diretório
-- (018_edital_cargo + 018_simulado_resumavel, 019_material_do_aluno +
-- 019_simulado_nome). Chavear por número perderia metade do histórico
-- silenciosamente — e "silenciosamente" é justamente o que esta tabela existe
-- pra acabar.
--
-- `checksum` guarda o conteúdo aplicado. Não é paranoia: `documento.hash` do CP
-- ficou desatualizado por DIAS porque o corpus mudou depois da ingestão e nada
-- comparava. Migração editada depois de aplicada é a mesma classe de
-- divergência — o arquivo diz uma coisa, o banco tem outra, e ninguém sabe.
-- `migrar.py` avisa; não corrige sozinho, porque corrigir exigiria adivinhar o
-- que a edição pretendia.
-- =====================================================================

CREATE TABLE IF NOT EXISTS migracao (
  nome        TEXT PRIMARY KEY,
  checksum    TEXT NOT NULL,
  aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE migracao IS
  'Quais arquivos de db/*.sql já rodaram neste banco (023). Escrito por '
  'migrar.py, nunca à mão. Ausência de linha = migração pendente.';
