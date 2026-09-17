# Produto: o que o tutor é, para quem, e por quais regras

Camada de DOMÍNIO. O que o sistema faz do ponto de vista de quem estuda, o
vocabulário do concurseiro e as regras de negócio em forma de regra.

- O **porquê medido** de cada decisão está em `docs/DECISOES.md`.
- O que o sistema **não faz** está em `docs/LIMITACOES.md`.
- O `CLAUDE.md` é o mapa operacional e aponta para cá.

Montado por resgate no git: a versão de 1.674 linhas do `CLAUDE.md` em
`6219766` (19/08/2026), a última antes da poda `e463f41`. Ver a nota de
arqueologia no fim.

---

## O que é

Tutor socrático para concursos públicos brasileiros. RAG sobre lei seca + banco
de questões + repetição espaçada. Multiusuário desde a migração 008. CLI
própria (`chat.py`) e API HTTP (`api.py`) sobre a MESMA lógica de `core/*.py`,
com frontend Next.js (`apps/web`) consumindo a API.

Corpus público, ingerido do Planalto, com as normas mantidas SEPARADAS:

| Norma | Volume no resgate (19/08/2026) |
|---|---|
| Código Penal | 434 artigos |
| Constituição Federal | 276 artigos |
| ADCT | 151 artigos |
| Código de Processo Penal | 848 chunks |
| Lei 8.112/1990 (regime dos servidores civis) | 245 chunks |
| Livro de histórico de emendas | material `tipo = 'historico'` |

Mais a **biblioteca privada do aluno**: PDF ou link que ele sobe, indexado no
mesmo acervo e invisível para as outras contas.

O chat do tutor tem memória de conversa e sabe para que concurso a pessoa
estuda. Quando o banco não tem questão da matéria, o sistema GERA a partir do
acervo e grava com proveniência.

## Escopo do projeto

*(Trecho resgatado literal — é a única seção que a poda apagou sem mover para
outro arquivo.)*

Este repositório contém um projeto de estudo e desenvolvimento de arquitetura
para sistemas baseados em RAG, recuperação híbrida, repetição espaçada e
tutoria socrática.

O corpus atual é composto exclusivamente por material público, utilizado como
domínio de demonstração e validação da arquitetura.

O projeto não contém dados, documentos, regras de negócio ou informações
confidenciais de qualquer organização.

No futuro, a arquitetura poderá ser reutilizada como base para outros projetos,
inclusive profissionais, desde que esses sejam desenvolvidos em repositórios
próprios, com escopo, autorização e políticas adequadas. Este repositório
permanece independente e utiliza apenas dados públicos.

---

## Vocabulário do domínio

Um agente que não conhece concurso público brasileiro erra por aqui antes de
errar no código.

| Termo | O que é neste sistema |
|---|---|
| **Lei seca** | o texto da norma, sem doutrina. É o que o acervo guarda e a única coisa que o tutor pode afirmar com número |
| **Banca** | a organizadora da prova (Cebraspe, FGV, AOCP, Cesgranrio...). Ela decide o FORMATO da questão |
| **Cebraspe/CESPE** | banca que cobra itens CERTO/ERRADO; erro anula acerto, daí o formato ter tratamento próprio |
| **Edital** | o documento que define cargo, data e conteúdo programático. Vira dado estruturado (tabelas `edital` e `topico`) |
| **Conteúdo programático** | a lista numerada de itens por disciplina. É a ORDEM de ensino do curso, e o tutor a segue |
| **Cargo** | um edital traz vários (17 no da PF); o aluno escolhe o dele na curadoria, senão estuda matéria de outro |
| **Mesa de estudo** | o concurso-alvo do aluno. É um FILTRO sobre o material, nunca um silo de dados |
| **Rubrica** | o nome do artigo ("Concussão"). Vai DENTRO do texto do chunk, porque é como o aluno procura |
| **Texto associado** | enunciado-base compartilhado por vários itens C/E. Registro próprio, não cópia dentro de cada item |
| **Caderno de erros** | o que o aluno errou, atravessando mesas — o erro é dele, não do concurso |
| **Desafio do dia** | composição: reincidentes + questões novas + mini-simulado, dentro do tempo que ele declarou |
| **Simulado** | prova sob condição de exame: sem diálogo, sem dica, correção só no fim |
| **Caixa / SM-2** | o estágio de repetição espaçada de cada questão para cada aluno |

---

## Regras de negócio

Cada regra em uma linha. O experimento que a produziu está em
`docs/DECISOES.md`, sob o título citado.

### Acervo, posse e privacidade

- O **acervo é compartilhado; o progresso é pessoal** (008). Toda tabela de
  estudo tem `usuario_id`; nenhuma tabela de conteúdo tem.
- O **material do aluno tem dono** (019). Documento com `usuario_id` nunca
  aparece para outra conta, e o dono da questão gerada sai do CHUNK — nunca de
  parâmetro.
- A **biblioteca pode ser isolada por mesa** (021), quando o aluno não quer que
  o material de um concurso contamine o outro.
- `corpus/` (lei do Planalto) vai para o git; `acervo/` (material do aluno) não.
- A **sincronização entre máquinas leva questão privada como privada** — ela
  viaja com o dono, não para o pool comum.

### Conteúdo e proveniência

- **Chunk é o artigo**, não N caracteres: artigo é unidade semântica completa.
- **CF e ADCT são normas separadas.** O ADCT tem numeração própria e um "art.
  2º" de cada um é outro artigo.
- **`tipo = 'historico'`** existe para material com várias versões do mesmo
  artigo (o livro de emendas): entra na busca híbrida e não é citável por
  artigo, porque a "versão certa" não existe ali.
- **Material de referência não recebe assunto nem disciplina** (027):
  jurisprudência e corpus fatiado por artigo não são aula, e um assunto único
  num corpus de centenas decide a ordenação por ruído.
- **Questão sem artigo real é DESCARTADA**, inclusive na geração sob demanda.
  Cobertura que mente é pior que cobertura inexistente.

### Questões

- **Dois formatos**: discursiva curta (avaliada por LLM) e item CERTO/ERRADO
  (corrigido em código, sem gastar cota nem tempo de prova).
- **Múltipla escolha ficou de fora de propósito**: exige tabela de alternativas
  e renderização própria, e a banca-alvo não cobra.
- **Não há escada socrática no item binário**: dica em questão de 50% de chance
  é entregar a resposta.
- **A banca decide o formato**: `geracao.tipo_da_banca` lê `mesa.banca`.
- **Quem pede treino é treinado na hora**: o app monta a questão com
  proveniência e fila, e o tutor só apresenta. Nunca manda clicar em botão.

### O tutor

- **Socrático significa descobrir, explicar, testar — nessa ordem, e sem narrar
  a ordem.** O andaime nunca aparece na resposta.
- **Duas fontes de contexto**: o material recuperado E o desempenho real do
  aluno. "Como estou indo?" não tem onde bater no RAG.
- **O prompt sabe para que concurso o aluno estuda** e fala da matéria como ela
  cai na prova DELE.
- **A conversa é persistida** (014) e registra o que o aluno FEZ, não só o que
  disse (016): errar a questão proposta vale mais que dizer que entendeu.
- **O perfil declarado calibra o tamanho da sugestão**, não o conteúdo — e
  nenhum texto de LLM é escrito em `usuario.perfil`.
- **A hierarquia de comportamento do tutor** está em
  `docs/REGRAS_TUTOR_CONSOLIDADAS.md`, que é a base do system prompt.

### Plano de estudo

- **Mesa é filtro, não silo** (010): o caderno de erros atravessa mesas, e há
  teste que quebra se alguém escopar progresso por mesa.
- **A mesa vem no header `X-Mesa-Id`, por requisição** — não existe "mesa
  ativa" guardada no servidor.
- **Edital é melhor esforço com curadoria** (011): extrai para rascunho, o
  aluno escolhe o cargo e ajusta, e só então vira oficial.
- **Mesa sem edital tem três estados**, não dois (017): sem alvo, alvo
  declarado à mão, edital oficial.
- **"Probabilidade de fechamento" é extrapolação linear de ritmo**, não modelo
  preditivo — e é apresentada como o que é.
- **A intervenção proativa é regra, não o LLM decidindo quando falar**: três
  erros seguidos interrompem a fila.
- **O desafio respeita o orçamento de tempo**, e o mini-simulado cai inteiro
  quando não cabe — simulado de duas questões não é simulado.

---

## Nota de arqueologia

O `CLAUDE.md` chegou a 1.674 linhas e foi podado duas vezes. **Nada foi
perdido nessas podas** — o conteúdo mudou de arquivo:

| Poda | De → para | Para onde foi |
|---|---|---|
| `e463f41` (19/08/2026) | 1.674 → 328 linhas | histórico e armadilhas para `docs/DECISOES.md`; o que não se faz para `docs/LIMITACOES.md` |
| `53b57ac` (15/09/2026) | 438 → 171 linhas | catálogo de comandos para `docs/COMANDOS.md`; migrações uma a uma para `docs/SCHEMA.md` |

O motivo é o mesmo nas duas: o `CLAUDE.md` entra em TODO prompt, e consulta não
precisa estar no contexto de toda tarefa — precisa estar achável.

A única seção que a poda apagou sem destino foi **"Escopo do projeto"**,
recuperada acima de `6219766`. Também se perderam, e estão recuperadas aqui: os
números do corpus por norma e a descrição longa do produto.

Recuperar qualquer outra coisa daquela versão:

```bash
git show 6219766:CLAUDE.md          # 1.674 linhas, 19/08/2026
git show cf97a2d:CLAUDE.md          # 438 linhas, 09/09/2026
git log --follow --format='%h %ad %s' --date=short -- CLAUDE.md
```
