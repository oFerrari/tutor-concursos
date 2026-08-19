-- 014: conversa persistida — o tutor passa a lembrar do turno anterior
--
-- O PROBLEMA ERA MAIOR DO QUE "ESQUECE A SEMANA PASSADA"
-- ------------------------------------------------------------------------
-- Não existia memória NENHUMA. `POST /perguntar` recebia só o texto da
-- pergunta atual; o histórico da conversa vivia no estado do componente
-- React e sumia num F5. Cada mensagem chegava ao modelo como se fosse a
-- primeira da vida.
--
-- Isso aparecia em uso, não em teoria. Numa conversa real o aluno respondeu
-- "qualquer um" a uma pergunta do tutor, e o tutor devolveu "você se refere
-- a quais cargos podem ser acumulados ou à regra de acessibilidade?" — ele
-- não estava sendo obtuso, ele literalmente não tinha a pergunta anterior.
--
-- Note que `socratic.avaliar()` JÁ recebia histórico (o diálogo socrático
-- de uma questão é stateless por design, com os turnos vindo por
-- parâmetro). O padrão existia; o chat livre é que não o usava, e não tinha
-- onde guardar entre sessões.
--
-- DUAS TABELAS, NÃO UMA COLUNA JSONB
-- ------------------------------------------------------------------------
-- Tentador guardar o histórico como JSONB dentro de uma linha por conversa.
-- Não: mensagem é a unidade que se pagina, se conta e se busca ("de que a
-- gente falou sobre peculato?"). Array em JSONB obriga a reescrever o
-- documento inteiro a cada turno e não indexa por conteúdo.
--
-- ESCOPO: DO USUÁRIO, E ETIQUETADA PELA MESA
-- ------------------------------------------------------------------------
-- `usuario_id` é quem AUTORIZA (mesma regra de `mesa.obter`: pedir conversa
-- de outra pessoa dá 404, não 403). `mesa_id` é ETIQUETA — a conversa
-- aconteceu no contexto daquele concurso e é útil listá-la lá, mas ela não
-- pertence à mesa: apagar a mesa não deve sumir com a conversa (SET NULL),
-- mesma política de `simulado.mesa_id` na 010. O que você discutiu sobre o
-- art. 312 continua valendo quando você troca de concurso.
--
-- `fontes` guarda o que a busca devolveu naquele turno. Sem isso, reabrir
-- uma conversa mostraria o texto do tutor sem as referências que o
-- sustentavam — e citação que some é pior que citação ausente: o aluno leu
-- a resposta ancorada e volta a ela desancorada.

CREATE TABLE conversa (
  id          BIGSERIAL PRIMARY KEY,
  usuario_id  BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  mesa_id     BIGINT REFERENCES mesa(id) ON DELETE SET NULL,
  -- Resumo curto pra listar na sidebar ("Revisão SM-2 · Direito Penal").
  -- Nasce da primeira pergunta e pode ser reescrito depois.
  titulo      TEXT NOT NULL,
  criada_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Ordena a lista de recentes por ATIVIDADE, não por criação: conversa
  -- retomada ontem importa mais que uma aberta há um mês e abandonada.
  atualizada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX conversa_recentes_idx ON conversa (usuario_id, atualizada_em DESC);

CREATE TABLE mensagem (
  id          BIGSERIAL PRIMARY KEY,
  conversa_id BIGINT NOT NULL REFERENCES conversa(id) ON DELETE CASCADE,
  autor       TEXT NOT NULL CHECK (autor IN ('aluno', 'tutor')),
  texto       TEXT NOT NULL,
  -- [{"titulo","norma","artigo"}] do turno. JSONB porque é payload de
  -- exibição, não entidade consultável — o oposto do caso de `mensagem`.
  fontes      JSONB NOT NULL DEFAULT '[]'::jsonb,
  criada_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX mensagem_conversa_idx ON mensagem (conversa_id, id);

COMMENT ON COLUMN conversa.mesa_id IS
  'ETIQUETA, não posse: quem autoriza é usuario_id. SET NULL porque apagar '
  'a mesa não deve apagar o que foi conversado (mesma política de simulado).';
