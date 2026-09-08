-- 028 — de onde o material veio, quando veio de um LINK
--
-- O RELATO
-- --------
-- "Ainda não mostra qual arquivo tá com o link." O aluno indexou a Constituição
-- colando o endereço do Planalto, depois apagou o material, e quis conferir
-- qual dos arquivos da biblioteca tinha vindo daquele link. Não havia como
-- responder: a informação nunca foi gravada.
--
-- `POST /materiais/link` chama `material.baixar(url)`, que devolve um NOME
-- derivado do endereço (`_nome_da_url`), e é esse nome que vai pra
-- `documento.origem`. A URL morre ali. Do banco em diante, material vindo de
-- link é indistinguível de arquivo arrastado com o mesmo nome — e "constituicao
-- .txt" não diz que veio do Planalto.
--
-- POR QUE COLUNA NOVA, E NÃO REUSAR `origem`
-- ------------------------------------------
-- `origem` é o NOME DE ARQUIVO e tem uma função ativa: `indexar` o passa de
-- volta pro `_extrair`, que escolhe o leitor pela extensão (.pdf, .htm, .txt).
-- Guardar a URL ali quebraria a reextração de todo material vindo de link — e
-- silenciosamente, no reindex, não no upload.
--
-- NÃO HÁ BACKFILL POSSÍVEL, e é honesto dizer: a URL do material já existente
-- não foi guardada em lugar nenhum, então a coluna nasce NULL pra ele. A tela
-- mostra o nome do arquivo como sempre nesse caso, e passa a mostrar o endereço
-- só no que for indexado a partir daqui.
ALTER TABLE documento ADD COLUMN url text;

COMMENT ON COLUMN documento.url IS
  'endereço público de onde o material foi baixado (POST /materiais/link); NULL em arquivo enviado direto e em material anterior à 028';
