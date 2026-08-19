-- =====================================================================
-- Rascunho de edital — a área de curadoria entre "a IA leu" e "o sistema
-- passou a cobrar isso todo dia".
--
-- O PROBLEMA QUE ISTO RESOLVE: um edital tem vários cargos, e cada cargo
-- tem conteúdo específico próprio. Ingerir direto empilhava tudo na mesma
-- mesa — o edital da Dataprev virou 1015 tópicos em 52 disciplinas, com o
-- conteúdo de Advocacia, Contabilidade e Engenharia dentro do plano de
-- quem vai prestar Desenvolvimento de Software. Somar cargo é pior que não
-- ler: gera revisão espaçada de matéria que a pessoa nunca vai cair.
--
-- POR QUE UMA TABELA E NÃO AS TABELAS OFICIAIS: escrever direto em
-- `edital`/`topico` suja o banco com o que o aluno não escolheu, e o que
-- entra ali vira imediatamente fila SM-2, meta e cobertura. O rascunho é o
-- lugar onde a extração pode estar errada sem consequência — quem decide o
-- que é verdade é a pessoa, na tela de curadoria, e só então isso vira
-- dado oficial.
--
-- POR QUE POSTGRES E NÃO REDIS: é um registro escrito uma vez e lido duas.
-- Não paga uma dependência de infra nova, um processo a mais pra subir e
-- um modo de falha a mais ("o Redis caiu e o rascunho sumiu no meio da
-- curadoria"). `expira_em` faz o mesmo trabalho do TTL, e sobrevive a
-- restart — que é justamente quando o TTL em memória perderia o trabalho
-- que o usuário já teve de subir o PDF.
--
-- A estrutura vai em JSONB de propósito: é dado em TRÂNSITO, com forma
-- ditada pelo parser (comuns/cargos/disciplinas/topicos), e normalizar
-- isso em tabelas seria modelar o que ainda vai ser editado e descartado.
-- =====================================================================

BEGIN;

CREATE TABLE edital_rascunho (
  id              BIGSERIAL PRIMARY KEY,
  usuario_id      BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  titulo          TEXT NOT NULL,
  arquivo         TEXT,
  data_prova      DATE,
  candidatos_data JSONB NOT NULL DEFAULT '[]'::jsonb,
  -- {"comuns": [{disciplina, topicos[]}], "cargos": [{nome, disciplinas[]}]}
  estrutura       JSONB NOT NULL,
  -- 'parser' | 'llm' — qual extrator produziu isto. Fica gravado porque a
  -- tela DIZ pro usuário de onde veio: confiança diferente, revisão
  -- diferente (o parser é determinístico; o modelo pode ter omitido).
  origem          TEXT NOT NULL DEFAULT 'parser',
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  expira_em       TIMESTAMPTZ NOT NULL DEFAULT now() + interval '24 hours'
);

CREATE INDEX edital_rascunho_usuario_idx ON edital_rascunho (usuario_id, criado_em DESC);
CREATE INDEX edital_rascunho_expira_idx  ON edital_rascunho (expira_em);

COMMIT;
