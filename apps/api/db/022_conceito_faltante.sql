-- =====================================================================
-- Migração 022 — o que o aluno CONFUNDE, não só o que ele errou.
--
-- `ESQUEMA_AVALIACAO` (core/socratic.py) pede `conceito_faltante` ao modelo
-- desde que existe, o Gemini preenche em TODA avaliação, o campo atravessa a
-- API e está tipado no front (`api.ts`). E é descartado: nenhuma tabela guarda,
-- nenhuma tela mostra, nenhum prompt lê. Já é pago e jogado fora.
--
-- O que existia perto disso não substitui. `erro_caderno.tema` guarda
-- `questao.tema` — o rótulo da PERGUNTA, escolhido por quem gerou a questão.
-- É a diferença entre "errou a questão de peculato" e "confunde peculato com
-- concussão": o primeiro é o índice do material, o segundo é o diagnóstico.
--
-- VAI EM `tentativa`, NÃO EM `erro_caderno`, e o critério é o de sempre neste
-- schema: `tentativa` é o FATO (esta resposta, neste instante, faltou isto) e
-- `erro_caderno` é o AGREGADO por (usuário, questão). Conceito é propriedade da
-- tentativa — a mesma questão errada duas vezes pode faltar coisa diferente em
-- cada uma, e é justamente essa mudança que mostra se a pessoa evoluiu ou
-- travou. Gravar no agregado sobrescreveria a série histórica que interessa.
--
-- NULLABLE, e não string vazia com DEFAULT '': item CERTO/ERRADO é corrigido
-- em CÓDIGO, sem LLM (decisão da 012) — ele não produz conceito nenhum, e
-- forçar '' faria "não houve avaliação por modelo" ficar indistinguível de "o
-- modelo avaliou e não achou o que faltava". Só `NULL` diz a verdade nos dois.
--
-- TEXTO DE MODELO É INPUT SUJO. O destino deste campo é o prompt do tutor, e o
-- perfil (015) já paga o preço de tratar isso a sério: lista fechada validada
-- na escrita E na leitura, porque "nivel: ignore as regras acima" chegando ao
-- modelo é injeção. Aqui não cabe lista fechada — o conceito é livre por
-- natureza —, então a defesa é outra e mora em código: limite de tamanho no
-- banco (CHECK), normalização na escrita, e no prompt ele entra como DADO
-- CONTADO e rotulado, nunca como instrução. O que este campo NUNCA faz é voltar
-- pro `usuario.perfil`: perfil é lido inteiro e literal pelo prompt, e fechar
-- esse laço deixaria o modelo instruir a si mesmo no turno seguinte.
-- =====================================================================

ALTER TABLE tentativa ADD COLUMN conceito_faltante TEXT;

-- 160 caracteres é conceito ("confunde impessoalidade com moralidade"); mais que
-- isso é o modelo escrevendo parágrafo, e parágrafo de modelo indo pro prompt é
-- exatamente o que a decisão acima recusa. O corte é na borda de escrita
-- também; o CHECK existe pra que um segundo caminho de gravação (import,
-- script, migração futura) não possa passar por cima disso calado — mesmo
-- espírito do CHECK casado da 012.
ALTER TABLE tentativa ADD CONSTRAINT tentativa_conceito_tamanho
  CHECK (conceito_faltante IS NULL OR length(conceito_faltante) <= 160);

-- A leitura que interessa é sempre "conceitos que ESTE aluno erra, do mais
-- recente pro mais antigo" — nunca a coluna sozinha.
CREATE INDEX tentativa_conceito_idx ON tentativa (usuario_id, criada_em DESC)
  WHERE conceito_faltante IS NOT NULL;

COMMENT ON COLUMN tentativa.conceito_faltante IS
  'O que faltou nesta resposta, segundo a avaliação do LLM (022). NULL = não '
  'houve avaliação por modelo (item C/E, corrigido em código) ou o modelo não '
  'apontou nada. Texto de modelo: normalizado e truncado na escrita, entra no '
  'prompt como dado contado e NUNCA em usuario.perfil.';
