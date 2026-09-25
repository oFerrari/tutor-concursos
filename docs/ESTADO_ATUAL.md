# Estado atual — base zerada para simulação completa

O placar da auditoria — o que foi resolvido, o que falta e a prontidão de MVP —
mora em `docs/AUDITORIA_MVP.md`.

## 22/09/2026 — LEIA ANTES DE TUDO: o banco foi zerado de propósito

A pedido do dono, a base foi limpa para ele subir um edital e materiais novos e
simular o uso completo da ferramenta. **Não restaure nada**: o estado antigo
não é perda, é decisão.

- Ficou: a conta do dono (perfil zerado, para o
  onboarding rodar de novo), uma única "Mesa principal", a lei seca pública (CP,
  CF, ADCT, CPP, Lei 8.112, histórico da CF — 2.314 trechos), `migracao`,
  `embedding_cache` e `telemetria_llm`.
- Saiu: os outros 10 usuários, mesas, editais, tópicos, todos os materiais do
  aluno, todas as questões (públicas também), tentativas, progresso, caderno,
  simulados, conversas, diário de teoria e fila de melhoria.
- Backup completo anterior: `.logs/backup-completo-antes-do-reset-20260922.sql.gz`
  (pg_dump, fora do git).
- `avaliar_retrieval.py` depois do reset: 23/34 top-1, 32/34 top-6 (baseline).

**`./setup.sh` não importa mais o estado remoto** (desde 22/09/2026): ele só sobe
o serviço. Importar o de outra máquina é opção explícita:
`TUTOR_TRAZER_ESTADO=1 ./setup.sh --subir`. Antes disso, dois `./setup.sh`
seguidos restauraram o banco antigo por cima do reset.

**Risco para quem trabalha em paralelo neste banco:** `git pull` dispara o hook
`post-merge`, que IMPORTA o estado do ref remoto `estado` — ou seja, traria de
volta o banco de antes do reset. `sincronizar.sh` sem argumento faz o mesmo.
Antes do reset, 169 questões antigas já tinham sido reimportadas por fora desta
sessão, com as datas originais. Não rodar import de estado sem pedido do dono.

### O que mudou no código nesta rodada (commits fe41b04..90f6374)

- Testes não deixam mais questão pública no acervo (`conftest._sem_lixo_no_acervo`).
- `pedido.treino` trata negação ("não quero questões" não gera questão).
- Questão abandonada depois de uma resposta vira tentativa (DialogoQuestao).
- Material entra na disciplina do edital a que pertence, pelo cabeçalho dos
  tópicos (`mesa.mapa_do_acervo`); `mesa.contexto` separa `disciplinas` (nomeia)
  de `recorte` (filtra). Disciplinas manuais SOMAM às do edital (decisão do dono).
- 032: o desempenho deixa de contar questão privada de outro aluno.
- Geração não grava a mesma pergunta duas vezes no mesmo trecho (Jaccard ≥ 0,9).

## Histórico anterior (fase 0) — dados abaixo são de ANTES do reset

Checkpoint verificado em 21/09/2026. Este arquivo registra o que falta; não
substitui `git status`, o banco ou os testes. Atualize-o ao terminar cada item.

## Regra de fase

O usuário determinou que a fase 0 terminasse sem nenhuma pendência conhecida
dessa fase. Os itens que o handoff havia adiado foram tratados e as verificações
abaixo fecharam limpas. Não iniciar bateria 2/fase 1 sem novo pedido do usuário.

## Já concluído e verificado

- Retrieval v7–v9: norma ausente, número por extenso e termos vazios no braço
  lexical; baseline registrado em 23/34 top-1 e 32/34 top-6.
- Documento 707 removido após confirmar zero referências; documento 1040 é a
  cópia válida de Criminalística.
- Mesa 1007 voltou a compartilhar a biblioteca.
- Questão 1062 deixou de apontar para o chunk inexistente 7274 e agora aponta
  para o chunk real 441; consulta atual: zero referências órfãs.
- Troca curta de disciplina corrigida em `assunto-v11`; os antigos xfails foram
  removidos e 29 testes direcionados passaram.
- Reindexação sem arquivo original implementada em `material-v25`, preservando
  ids de chunk, com teste direcionado aprovado.
- Documentos 344, 739 e 952 reindexados a partir do original; documento 342
  reindexado a partir dos chunks preservados (268/268 rótulos).

## Última pendência operacional — concluída

Os cinco documentos antigos do usuário 1914 foram reindexados pelos chunks
preservados, sem recriar ids:

| Documento | Assunto | Chunks | Rótulos depois |
|---:|---|---:|---:|
| 343 | Princípios fundamentais e direitos fundamentais | 202 | 202 |
| 345 | Poder Executivo | 145 | 145 |
| 346 | Organização do Estado | 515 | 515 |
| 347 | Direitos Políticos | 134 | 134 |
| 348 | Nacionalidade | 181 | 181 |
| **Total** |  | **1.177** | **1.177** |

Consulta final do usuário 1914: zero chunks sem rótulo entre aula/resumo. Consulta
global de proveniência: zero referências de questão para chunk inexistente.

Os documentos 1019 (237 chunks, usuário 5147) e 1022 (1 chunk, usuário 5150)
também aparecem sem rótulo numa consulta global, mas pertencem a outras contas
descartáveis e não fazem parte do corpus/fase 0 do usuário 1914. Não alterá-los
como efeito colateral.

## Verificações finais

- Testes direcionados: **30 passed**.
- Suíte completa: **453 passed, 1 skipped** em 191,31 s; nenhum xfail restante.
- `avaliar_retrieval.py`: **23/34 top-1, 32/34 top-6**, idêntico ao baseline.
- Documentos 343, 345, 346, 347 e 348: `status=pronto`, 1.177/1.177 rótulos.
- Corpus de aula/resumo do usuário 1914: zero chunk sem rótulo.
- `questao.fonte_chunks`: zero referência órfã.

As limitações gerais que continuam em `docs/LIMITACOES.md` são backlog de fases
futuras/produto, não pendência escondida da fase 0.

## Alterações locais da fase 0

O worktree já continha mudanças em `api.py`, `core/assunto.py`,
`core/material.py`, fixtures/testes e `docs/DECISOES.md`/`LIMITACOES.md`. Elas
são o trabalho concluído desta fase, não sujeira para descartar. Não usar
reset/checkout. Ainda não houve commit nem início da fase 1.

## Melhorias posteriores ao fechamento da fase 0

Em 21/09/2026, os relatos 20, 58, 65 e 108 da fila de melhorias foram corrigidos
sem iniciar a fase 1: posição no edital ao mudar de assunto dentro do mesmo item,
humor contextual, planejamento sem empurrar conteúdo e separação explícita entre
matéria e assunto. Validação: 72 testes direcionados e uma resposta real para
cada caso. Os detalhes e as medições estão em `docs/DECISOES.md`.

## Auditoria sênior no navegador — 22/09/2026

O serviço local foi exercitado no Chrome visível, com a sessão real autorizada
pelo usuário. Esta rodada não inicia a fase 1 e não reabre a fase 0; é uma
auditoria do produto em uso.

Corrigido e verificado:

- “quero questões de Ciências Forenses, quais são os assuntos?” agora é pedido
  de mapa: lista o programa e espera a escolha, sem gerar questões antes dela;
- quando a fala atual nomeia Ciências Forenses, ela vence o foco constitucional
  antigo inclusive no fallback do gerador;
- pedidos vagos como “manda cinco” continuam herdando o assunto anterior;
- trocar de conversa ou abrir uma nova limpa questões geradas no estado React;
- a tela não recalcula citação apenas por `art. N`, evitando confundir, por
  exemplo, CP 312 com CPP 312;
- a abertura fictícia do protótipo, a pergunta pronta de peculato, a questão de
  fila e o flashcard decorativo foram removidos do `/tutor`. Uma conversa vazia
  agora mostra somente uma orientação neutra; conteúdo só aparece vindo da API.

Casos reais aprovados no Chrome: Ciências Forenses → papiloscopia; meta-pergunta
sem consulta de material → pedido de Penal com consulta retomada; Direito
Administrativo → troca curta para Processo Penal; reabertura de conversa sem
cartões gerados de outra conversa. Validação automatizada: **132 testes
direcionados passaram**, ESLint dos arquivos alterados passou e
`git diff --check` ficou limpo. A suíte completa não foi repetida nesta rodada.

Os dados privados criados pelo replay defeituoso foram removidos: questões 1936
e 1937 e mensagens 5296–5298. As conversas de QA permanecem visíveis para
auditoria. O relato original e seus dados foram preservados.

Proveniência tipada corrigida em `socratic-v72`: a mesma chamada retorna prosa
e IDs das fontes usadas, validados contra os chunks desta chamada. O contrato
`citada` da API/tela permanece. Testes direcionados de citação/conversa: 34
aprovados. Uma pergunta real enviada no Chrome sobre reparação no peculato
culposo exibiu somente CP 312 como CITADO, com prosa sem colchetes. Isso registra
atribuição declarada pelo modelo, não prova automática de suporte semântico.
