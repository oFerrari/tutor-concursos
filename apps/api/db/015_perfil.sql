-- 015: perfil de estudo do aluno — o que o tutor precisa saber além dos números
--
-- O QUE FALTAVA
-- ------------------------------------------------------------------------
-- O tutor já sabe o DESEMPENHO (73% em Constitucional, 3 reincidências em
-- peculato) e agora sabe a CONVERSA (014). O que ele nunca soube é como
-- esta pessoa estuda: quantas horas por dia, em que nível está, que turno
-- rende. Sem isso ele trata um iniciante com 1h por dia igual a um veterano
-- com 6h — e a sugestão que fecha toda resposta ("vale focar aqui hoje")
-- é escrita sem saber quanto "hoje" cabe.
--
-- Essas três respostas JÁ ERAM PEDIDAS na tela de onboarding desde o
-- protótipo, e não tinham onde ser gravadas: sumiam ao trocar de rota. A
-- tela dizia isso honestamente ("as três respostas ainda não são
-- gravadas"). Esta migração é o "ainda" acabando.
--
-- JSONB E NÃO TRÊS COLUNAS
-- ------------------------------------------------------------------------
-- Aqui o argumento é o INVERSO do da 014 (onde mensagem virou tabela).
-- Preferência não se pagina, não se conta, não se busca: é lida inteira,
-- toda vez, por um único consumidor (o prompt). E o conjunto vai crescer
-- por tentativa e erro — "prefere exemplos de trânsito", "perde foco depois
-- de 40 minutos" são coisas que só se descobre usando. Uma migração por
-- preferência nova seria atrito onde o formato ainda não assentou.
--
-- Quando um campo desses provar que precisa ser CONSULTADO (relatório,
-- filtro, agregação), ele vira coluna. Até lá, JSONB.
--
-- NÃO É "VETOR DE PERFIL"
-- ------------------------------------------------------------------------
-- Foi cogitado guardar isto como embedding. Não: "prefere exemplos de
-- trânsito" é um fato curto e literal, não um ponto num espaço semântico.
-- Vetor convidaria a buscar por similaridade onde ler o texto resolve, e
-- pior — abriria caminho pro modelo INFERIR o próprio contexto. O princípio
-- do projeto é o oposto: o modelo LÊ um resumo calculado em código
-- (`_resumo_desempenho`), nunca deduz o que sabe sobre o aluno.

ALTER TABLE usuario
  ADD COLUMN perfil JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN usuario.perfil IS
  'Preferências de estudo (horas/dia, nível, turno, observações). Lido '
  'inteiro pelo prompt do tutor; JSONB porque não se consulta por campo. '
  'Vira coluna no dia em que algum campo precisar ser filtrado/agregado.';
