# Auditoria do tutor — placar do MVP

## ▶ ONDE PARAMOS — 22/09/2026, fim do dia (retomar daqui)

**Leia isto primeiro.** O resto do arquivo é o placar item a item.

### Estado do ambiente ao encerrar

- **Serviços:** API (8000), front (3000) e banco (5433) de pé, subidos pelo
  `./setup.sh --subir` — então `./setup.sh --parar` derruba API e front.
- **Banco:** zerado a pedido do dono e repovoado só com o uso real dele.
  1 usuário (`andrei.ferrari11@gmail.com`, senha `12345678`), 1 "Mesa principal"
  criada por ele, **nenhum edital**, perfil do onboarding (2 h, Intermediário,
  Noite), lei seca pública intacta.
- **Material:** 18 PDFs subidos pelo app — **11 prontos, 7 ainda indexando** ao
  encerrar (aulas 00–07 de Constitucional). A fila de indexação tem um
  trabalhador só; confira com a consulta de status antes de simular.
- **Simulação feita:** 1 conversa de aluno novo (11 falas), 2 questões geradas,
  1 tentativa. Resultado registrado na seção 8.

### Git e o estado no GitHub — atenção

- `develop` local está **4 commits à frente** do GitHub (6246645, ed2b7e3,
  bb45341, 8df7bd3) — o dono ainda não empurrou.
- O ref `estado` no GitHub **ainda guarda o banco de 10/09** (publicado às 22:17,
  quando o banco local estava restaurado). O próximo `git push` comum publica o
  banco ATUAL por cima — é o que se quer.
- **Não rodar `git pull` antes desse push**: o hook `post-merge` importaria o
  estado de 10/09 por cima do uso real. `./setup.sh` já não importa (1.7).

### Perguntas em aberto para o dono

1. **Edital:** subir o da PC-PR na mesa, ou seguir simulando sem edital (aluno
   cujo edital não saiu)? Sem edital, o mapa de disciplinas (2.2) não tem o que
   mapear e a classificação escolhe nome errado (8.7).
2. **Hooks de estado (1.8):** manter push/pull levando o banco, ou desligar.
3. **Maestria (2.8):** manter a regra atual ou dar gradiente.

### Próximos passos, em ordem

1. **8.1 — CPF e cabeçalho repetido nos trechos.** Privacidade: o dado vai ao
   Gemini. Regra universal por frequência na ingestão + aproveitar a página.
2. **8.2 — diário que inventa estudo.** Registrar só o que o turno explicou.
3. **4.4 e 6.6 — conversa:** o tutor adia a pergunta do aluno; tique "Sigo
   para…?". É prompt: validar com `./testar.sh` e conversa real.
4. **8.7 — classificação sem edital** escolhe a disciplina errada.
5. **3.3 — rodízio de disciplinas na fila.**
6. **5.1/5.2 — curadoria:** capa/apresentação que vira questão; tema inventado.
7. **6.1/6.2 — selo e CITADO legíveis** (nome do edital; título do material).
8. **Telas (seção 7) e 8.3–8.5.**

### O que falta simular (continuação da bateria de aluno novo)

- Subir o edital pela tela (se o dono aprovar) e conferir: Meu edital, mapa das
  disciplinas (Criminalística/Processual Penal → disciplina do edital), meta e
  data da prova.
- Material de edital subido como aula (`edital_n_4_completo`): ficou **pronto
  sem disciplina e sem assunto** — ver se aparece em algum lugar e como.
- Fila e Sessão de estudo com várias disciplinas (rodízio, 3.3).
- Simulado completo (montar, responder, relatório) e Caderno de erros.
- Meus materiais no celular (7.5) e Mesas (7.1, 7.4).

### Como rodar a simulação de novo

Os roteiros de navegador ficaram em `.logs/auditoria-drivers/` (fora do git):

```bash
cd .logs/auditoria-drivers
npm i && npx playwright install chromium   # uma vez
node primeiro_acesso.mjs   # login → /mesas; sem mesa, tudo volta ao lobby
node aluno_novo.mjs        # a bateria de 11 falas + fila, desempenho, panorama
```

`aluno_novo` e `primeiro_acesso` entram pela tela de login. `abandono`,
`simulado` e `tour` esperam `TOKEN` (`auth.emitir_token(id)`) e `MESA` no ambiente.
A transcrição completa de cada rodada sai do banco (`mensagem` da última
`conversa`), não da tela.

### Onde estão os backups (fora do git, em `.logs/`)

- `backup-completo-antes-do-reset-20260922.sql.gz` — banco inteiro antes do reset
- `backup-estado-restaurado-2210-20260922.sql.gz` — o que o `./setup.sh` trouxe de volta
- `backup-arquivos-20260922/` — os PDFs antigos que estavam em `dados/arquivos`
- `progresso-estado-antigo-20260922.json` — o pacote de estado antigo
- `backup-lixo-teste-20260922.json` e `backup-duplicatas-20260922.json`

### Risco operacional

Um agente do Antigravity (Codex) rodou nesta máquina, no mesmo repositório e no
mesmo banco, e os dois `./setup.sh` que desfizeram o reset saíram do terminal do
Antigravity. Antes de medir qualquer coisa, confira quem mais está usando o banco.

---

Consolida as três rodadas de auditoria de 22/09/2026 (bateria 1 do chat, varredura
de telas, rodada 2 de fluxos e dados) e o que foi corrigido depois. Cada item diz
o estado, a evidência que o sustenta e onde está o conserto.

**Como manter:** ao resolver um item, mude o estado, cite o commit e a verificação.
Item só vira ✅ com verificação que rodou — teste, consulta ou tela —, não com
"deve funcionar". Validação de comportamento do chat exige conversa real
(`./testar.sh` ou o app), porque regressão de prompt não aparece em teste
automatizado.

Legenda: ✅ resolvido · 🟡 resolvido em parte · ⏳ pendente · 🔶 decisão do dono ·
📝 limitação registrada (medida, sem conserto seguro hoje)

---

## Prontidão de MVP (parte do tutor)

| Dimensão | Antes | Agora | O que mudou / o que falta |
|---|---:|---:|---|
| Segurança e alucinação | 85 | 85 | Já recusava premissa falsa, lei inexistente e dado de terceiro |
| Busca (retrieval) | 85 | 85 | Baseline 23/34 top-1, 32/34 top-6, intacto em todas as mudanças |
| Integridade do acervo | 30 | 80 | Testes não vazam mais; dedup na geração; view sem questão alheia. Falta conferir conteúdo × trecho |
| Estatísticas refletem o uso | 35 | 70 | Chat conta tentativa (validado ao vivo); vocabulário único. Falta: diário inventa estudo (8.2); gradiente da maestria |
| Mesa e edital | 35 | 70 | Manual soma ao edital; material entra na disciplina certa; primeiro acesso pela mesa. Falta rodízio da fila |
| Obedecer ao pedido | 40 | 60 | Negação e encerramento validados ao vivo. Falta: adia a pergunta do aluno (4.4 piorou) |
| Qualidade da questão gerada | 30 | 45 | Duplicatas bloqueadas. Falta: capa/apresentação da apostila vira questão; tema inventado |
| Fluxo de conversa | 50 | 55 | Saudação e encerramento certos ao vivo. Falta o tique "Sigo para…?" |
| Privacidade do material | — | 50 | CPF e nome da marca d'água vão ao LLM externo em ~75% dos trechos (8.1) |
| Telas e navegação | — | 55 | Primeiro acesso e Raio-X honestos. Falta Mesas no layout, rótulos, celular |
| **Total** | **~45%** | **~65%** | Média simples das dimensões; conversa validada em simulação de aluno novo (22/09) |

O que separa 65% de um MVP de mercado está concentrado em dois lugares: **o
comportamento da conversa** (obedecer, encerrar, não repetir fórmula) e **a curadoria
do que vira questão** (fonte que não é matéria). O motor — busca, dados, estatística
— está bem à frente.

---

## 1. Integridade de dados

| | Falha | Evidência | Estado |
|---|---|---|---|
| 1.1 | Testes gravavam questão pública no acervo real | 101 de 377 públicas eram lixo ("Enunciado?", "assertiva N", 16× "instrumento contundente") e uma caiu em simulado | ✅ `fe41b04` — `conftest._sem_lixo_no_acervo` apaga o que o processo de teste inseriu. Suíte inteira: 380 → 380 públicas |
| 1.2 | "Instrumento contundente" com fonte CP art. 1º | Era andaime do teste de posse, não o gerador de produção | ✅ reclassificado; o lixo saiu no reset |
| 1.3 | Gerador não confere se o conteúdo bate com o trecho | Confia no ponteiro `artigo`/`trecho` que o modelo devolve | 🟡 2 de 2 questões da simulação com fonte correta; falta medir em volume |
| 1.4 | Mesma pergunta gravada várias vezes no mesmo trecho | 12× "reparação do dano no peculato culposo"; 30× "emissão irregular…" | ✅ `36dbbf2` — Jaccard ≥ 0,9 no mesmo trecho/dono/tipo reaproveita a existente |
| 1.5 | Paráfrase da mesma pergunta | "…originários" × "…oriundos" no caderno | 📝 LIMITACOES — nenhum sinal medido (enunciado, gabarito, e5) separa paráfrase de pergunta distinta |
| 1.6 | Desempenho contava questão privada de outro aluno no denominador | Forenses 30 no Desempenho × 22 no Meu edital | ✅ `90f6374` — migração 032 |
| 1.7 | `./setup.sh` importava o estado remoto por cima do banco local | Dois `./setup.sh` desfizeram o reset em 5 min | ✅ `6246645` — importar virou `TUTOR_TRAZER_ESTADO=1` |
| 1.8 | `git push`/`git pull` levam o banco junto (hooks) | O push de 22:17 publicou o estado restaurado | 🔶 manter ou desligar os hooks |

## 2. Estatísticas e telas que não acompanhavam o uso

| | Falha | Evidência | Estado |
|---|---|---|---|
| 2.1 | Resposta no chat só era gravada no acerto ou no 3º erro | Errar 1× e seguir → 0 tentativas; 29 questões do chat sem registro | ✅ `999ec7e` — sair da questão conta; verificado no navegador: chat, fila e aba recarregada |
| 2.2 | Edital e acervo com nomes diferentes | Criminalística ≠ Ciências Forenses; 62 questões (15%) invisíveis; 2/26 na tela × 3/28 no banco | ✅ `8c06006` — `mesa.mapa_do_acervo` pelo cabeçalho do tópico; testes com concurso inventado |
| 2.3 | Dois módulos, duas regras de casamento | Desempenho 292 de Penal × Meu edital 0 | ✅ `8c06006` — `edital.cobertura` usa `mesa.filtro` |
| 2.4 | Mesas dizia "último estudo há 7 dias" com estudo no dia | Contava só pelo nome do edital | ✅ `8c06006` |
| 2.5 | Raio-X e Panorama não mudavam depois do chat | Consequência de 2.1 e 2.2; pela Fila já atualizava | ✅ por 2.1 + 2.2 |
| 2.6 | Tutor sub-relatava progresso ("Penal e Constitucional") | Resumo de desempenho e diário filtravam pelo edital | 🟡 filtro corrigido (`8c06006`), mas **ao vivo inventou** "você estudou Direito Constitucional" — causa em 8.2 |
| 2.7 | Três números para "quanto já fiz" (22 / 26 / 28) | Meta conta questões distintas; Desempenho, tentativas | 🟡 26 × 28 resolvido por 2.2; falta a tela dizer o que cada número conta |
| 2.8 | Maestria sem gradiente | "Dominada" = caixa 3; acerto com dica não promove; 0% coberto após um mês | 🔶 regra pedagógica deliberada (LIMITACOES) |
| 2.9 | Raio-X com número fictício | "Liga Ouro, 7º de 42" e "28 flashcards" eram constantes do protótipo | ✅ `ed2b7e3` — saíram |

## 3. Mesa, edital e fila

| | Falha | Evidência | Estado |
|---|---|---|---|
| 3.1 | Disciplinas escolhidas à mão ignoradas quando havia edital | Duas mesas com fila idêntica | ✅ `8c06006` — o manual SOMA ao edital (decisão do dono) |
| 3.2 | Primeiro acesso ia ao painel com mesa criada sozinha | `mesa.padrao()` cria na 1ª chamada sem mesa | ✅ `ed2b7e3` — login leva a /mesas; portão na casca; verificado: 0 mesas criadas |
| 3.3 | Fila não alterna disciplinas | Inéditas por `ORDER BY q.id`: Administrativo nunca entrava | ⏳ LIMITACOES — rodízio |
| 3.4 | Sessão de estudo sem a matéria com mais material | Recorte (2.2) + ordem da fila (3.3) | 🟡 recorte resolvido; ordem pendente |
| 3.5 | Material que é edital subido como aula | `edital_n_4_completo` indexado como apostila (22/09) | ⏳ ficou pronto SEM disciplina e SEM assunto — o classificador não o tomou por aula, mas nada avisa o aluno, e sem disciplina ele fica fora de todo recorte |

## 4. Chat — pedido e intenção

| | Falha | Evidência | Estado |
|---|---|---|---|
| 4.1 | Negação ignorada | `pedido.treino("sem questões")` → {'quantidade': 2}; gerou 5 questões num pedido de planejamento | ✅ `9d0b0ef` — 16 casos nos dois sentidos; validado ao vivo (0 questões) |
| 4.2 | Pedido de mapa gerava questão | "quero questões; quais são os assuntos?" | ✅ `cbb82fa` (pedido-v9) |
| 4.3 | Troca curta de disciplina | "e no processo penal?" seguia o assunto anterior | ✅ `cbb82fa` — validado ao vivo ("e no direito administrativo?" mudou de matéria) |
| 4.4 | Não responde a pergunta feita | "o que é constituição?" → poder constituinte; ao vivo, **pior**: "o que é proposição composta?" → "isso já avança… por ora, as simples" | ⏳ o tutor impõe o ritmo dele sobre a pergunta do aluno |
| 4.5 | Não reconhecia encerramento | "obrigado, era só isso" → mais aula | ✅ ao vivo: "Por nada. Sigo à disposição quando quiser retomar os estudos." |
| 4.6 | "Sigo para as questões?" com a questão já na tela | 1º turno do teste ao vivo | 🟡 não repetiu na simulação (1 amostra) |
| 4.7 | Planejamento sem plano | 20 min no chat × 3,5 h no perfil | 🟡 sem edital, pergunta a matéria (razoável), mas não monta plano algum |

## 5. Chat — qualidade da questão gerada

| | Falha | Evidência | Estado |
|---|---|---|---|
| 5.1 | Questão sobre o autor da apostila | "Qual é o cargo do professor Murilo Marques?" | ⏳ filtrar capa/apresentação de forma universal |
| 5.2 | `tema` inventado não bate com a fonte | "Apresentação do Professor" num trecho de "Escolas Criminológicas" | ⏳ |
| 5.3 | Duplicatas na mesma leva | 5 questões = 3 distintas | ✅ `36dbbf2` para texto quase idêntico; paráfrase em 1.5 |

## 6. Chat — conversa e fonte

| | Falha | Evidência | Estado |
|---|---|---|---|
| 6.1 | Três nomes para a mesma matéria na tela | Pedido "Ciências Forenses", tutor "Medicina Legal", selo "CRIMINALÍSTICA" | 🟡 telas agregadas usam o nome do edital; o selo do cartão no chat ainda não |
| 6.2 | CITADO/CONSULTADO com nome de arquivo cru | `CURSO-392722-AULA-05-CDD4-COMPLETO` | ⏳ |
| 6.3 | Não dava a página e não admitia | `chunk.pagina` vazio em 100% dos trechos | 🟡 ao vivo admite ("não consta no material recuperado"); a página existe no texto do cabeçalho mas não é extraída (8.1) |
| 6.4 | Emenda irrelevante depois de recusar | Lei falsa recusada + trecho aleatório do CPP | ✅ ao vivo: recusou e trouxe o art. 34 da Lei 8.112 (exoneração), pertinente e correto |
| 6.5 | "Boa noite." fora de hora | Resposta a pedido direto começando por saudação | ✅ ao vivo: saudou só quando saudado |
| 6.6 | Tique "Isso já é o item X / Sigo para…?" | Quase todo turno | ⏳ confirmado ao vivo: "Sigo para as sentenças abertas?", "Sigo para a união delas…?" |
| 6.7 | Proveniência tipada | "citada" era deduzido de texto entre colchetes | ✅ `cbb82fa` (socratic-v72) |

## 7. Telas e navegação

| | Falha | Estado |
|---|---|---|
| 7.1 | Mesas fora do layout (sem barra lateral, cabeçalho próprio) | ⏳ |
| 7.2 | Cabeçalho colado "TópicosCobertura" no Meu edital | ⏳ |
| 7.3 | Menu × título: "Meu edital" abre "Meta até a prova", "Sessão de estudo" abre "Desafio de hoje", "Meus materiais" abre "Minha biblioteca" | ⏳ |
| 7.4 | Toggle "usa material de todas as mesas" fora do cartão | ⏳ |
| 7.5 | Materiais no celular: aviso estoura até 983 px numa tela de 390 | ⏳ |
| 7.6 | Perfil: chip "3.5h" fora de ordem | ⏳ |
| 7.7 | Aviso do lobby prometia mesa padrão | ✅ `ed2b7e3` |

---

## 8. Achados da simulação de aluno novo (22/09/2026)

Base zerada, conta do dono, material real subido pelo app, sem edital. Login →
mesa → painel → 11 falas no tutor → fila → desempenho → panorama. Latência de
3 a 8,5 s por turno. Transcrição e telas em `.logs`/scratchpad da sessão.

| | Falha | Evidência | Estado |
|---|---|---|---|
| 8.1 | **Cabeçalho e marca d'água repetidos em quase todo trecho** | 160–167 de 219 trechos da apostila começam com "Aula 00 / PC-PR… / site / **CPF e nome do aluno** / página / total". Vai ao Gemini em todo prompt que usa o trecho, dilui o sentido e casa no lexical em tudo | ⏳ **privacidade**: remover na ingestão as linhas que se repetem na maior parte das páginas do MESMO documento (regra por frequência, universal); extrair a página em vez de descartá-la |
| 8.2 | **O diário registra como "estudado" o assunto de qualquer trecho recuperado** | Saudação e pedido de plano deixaram "Direitos sociais / Direito Constitucional" no `estudo_teoria`; a troca para Administrativo registrou "Da Licença para Atividade Política", rubrica de um artigo que nem entrou na resposta. O tutor respondeu "você estudou Constitucional" e omitiu Administrativo | ⏳ registrar só o que o turno de fato explicou (fonte citada, não recuperada) |
| 8.3 | Plural sem concordância | "0 de 1 tentativas", "em 1 tentativas", "(1 reincidências)" | ⏳ |
| 8.4 | Título da conversa é a primeira fala | Recentes: "boa noite" numa conversa sobre proposições | ⏳ |
| 8.5 | `GET /edital` responde 404 quando não há edital | 33 vezes numa sessão; a tela trata, o console acusa erro | ⏳ responder 200 com vazio |
| 8.6 | Edital subido como material de aula | `edital_n_4_completo` ficou pronto sem disciplina nem assunto | ⏳ ver 3.5: detectar e avisar que é edital |
| 8.7 | Classificação sem edital escolhe a disciplina errada | A Aula 00 de Ciências Forenses (perícias) foi classificada como "Direito Processual Penal": sem edital, o classificador prefere nome que já existe no acervo, e "Ciências Forenses" ainda não existia. Com edital, o mapa (2.2) a poria em Penal pelo cabeçalho "7.1 Direito Processual Penal" — errado para conteúdo pericial | ⏳ reclassificar quando o edital chega; não travar a escolha no que já existe |

Validado ao vivo e funcionando: negação (4.1), encerramento (4.5), troca curta
(4.3), tentativa do chat nas estatísticas (2.1 — Panorama "0 de 1", 1 revisão,
1 no caderno), saudação (6.5), recusa de lei falsa com complemento pertinente
(6.4), admitir que não sabe a página (6.3), primeiro acesso pela mesa (3.2) e
painel sem número fictício (2.9).

## Ordem sugerida para o que falta

1. **Privacidade e diário** (8.1, 8.2): o CPF não pode ir ao LLM externo, e o tutor
   não pode afirmar estudo que não houve. Os dois são regra de dado, com teste direto.
2. **Conversa** (4.4, 4.7, 6.6): adiar a pergunta do aluno e o tique são prompt —
   validar com `./testar.sh` e conversa real, nunca só teste.
3. **Curadoria da questão** (5.1, 5.2, 1.3): regra universal para trecho que não é
   matéria (capa, índice, apresentação) antes de gerar.
4. **Rodízio da fila** (3.3): as outras disciplinas aparecerem sem depender do id.
5. **Selo e fonte legíveis** (6.1, 6.2): nome do edital no cartão, título do material
   no lugar do nome de arquivo.
6. **Telas** (7.x, 8.3–8.5): polimento, uma tela por vez.
7. **Decisões do dono** (1.8, 2.8): hooks de estado e gradiente da maestria.
