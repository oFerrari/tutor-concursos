# Auditoria do tutor — placar do MVP

## ▶ ONDE PARAMOS — 24/09/2026 (retomar daqui)

**Leia isto primeiro.** O resto do arquivo é o placar item a item. A seção 10 é a
análise da conversa real de 24/09 (Ciências Forenses) e o que saiu dela.

### Estado do ambiente

- **Serviços:** API (8000), front (3000) e banco (5433) de pé (`./setup.sh --subir`).
- **Banco:** só a conta do dono, 1 mesa com o
  **edital da PC-PR** (110 tópicos, subido pelo dono em 24/09). Migração **033**
  aplicada. Diário limpo das 4 linhas antigas (backup em
  `.logs/backup-diario-antigo-20260924.json`).
- **Material:** 18 PDFs; a apostila de Ciências Forenses agora está em Ciências
  Forenses (era "Direito Processual Penal"); o edital da Transpetro virou
  `tipo='edital'` (fora da busca, com aviso na tela de materiais).
- **Suíte:** 528 testes, 0 pulados. Busca intacta (23/34, 32/34).

### Git

- `develop` local à frente do GitHub desde `6246645`; o push é do dono.
  **Não rodar `git pull` antes desse push** (o hook importaria o estado de 10/09).

### Perguntas em aberto para o dono

1. **Hooks de estado (1.8):** manter push/pull levando o banco, ou desligar.
2. **Maestria (2.8):** manter a regra atual ou dar gradiente.

### Pendente com o modelo real (deixado para depois pelo dono, 24/09)

Depende de cota do Gemini; nada disto está feito:

1. **Limitar o raciocínio do modelo nas chamadas do chat.** Causa medida do
   "resposta truncada em 1500 tokens": a reserva `gemini-3.5-flash` gastou ~1.450
   dos 1.500 tokens pensando e 45 escrevendo (telemetria 807/809, 20:50 de 23/09).
   Descobrir qual campo o modelo aceita (`thinkingBudget` ou `thinkingLevel`) e
   conferir na coluna `tokens_pensamento` (034).
2. Ver se o cache implícito vale para as instruções fixas (`tokens_cache`).
3. Conferir o streaming (`/perguntar/fluxo`) no navegador com o modelo real.
4. Conversa de validação (`./testar.sh`) depois das mudanças de prompt.

### Próximos passos, em ordem

1. **Usar a leitura na tela** (10.1): conferir o botão "Continuar a leitura", o
   olho das fontes e as etiquetas por assunto/página no navegador.
2. **5.1/5.2 — curadoria:** capa/apresentação que vira questão; tema inventado.
   A mesma regra serviria à leitura (LIMITACOES).
3. **Leitura a partir de uma seção** ("lê a parte de balística") — LIMITACOES.
4. **6.6 — resto do tique** e **telas (seção 7)**.

### O que falta simular (continuação da bateria de aluno novo)

- Subir o edital pela tela (se o dono aprovar) e conferir: Meu edital, mapa das
  disciplinas, meta e data da prova.
- Fila e Sessão de estudo com várias disciplinas — o rodízio (3.3) está em teste,
  falta ver na tela com o material real.
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

| Dimensão | 21/09 | 22/09 | 23/09 | 24/09 | O que mudou / o que falta |
|---|---:|---:|---:|---:|---|
| Segurança e alucinação | 85 | 85 | 85 | 85 | Leitura fiel ao trecho medida com o modelo real; material errado ⇒ texto inventado foi achado e fechado (10.3) |
| Busca (retrieval) | 85 | 85 | 88 | 90 | Edital fora da busca (10.4); leitura em sequência para quem pede avanço (10.1) |
| Integridade do acervo | 30 | 80 | 85 | 85 | Reindexar não deixa mais questão citando trecho apagado (9.1). Falta conferir conteúdo × trecho |
| Estatísticas refletem o uso | 35 | 70 | 80 | 85 | Diário antigo limpo; convite a testar só na abertura (10.9) |
| Mesa e edital | 35 | 70 | 80 | 85 | Edital novo reclassifica o palpite do modelo (10.5); edital subido como aula detectado (10.4) |
| Obedecer ao pedido | 40 | 60 | 70 | 80 | "Na ordem", "como apostila", "sem perguntas" viram leitura em sequência (10.1) |
| Qualidade da questão gerada | 30 | 45 | 45 | 45 | Falta: capa/apresentação vira questão; tema inventado |
| Fluxo de conversa | 50 | 55 | 65 | 75 | Aula expositiva longa e contínua; "continua" é botão; inventário responde "o que você tem" (10.6) |
| Privacidade do material | — | 50 | 90 | 90 | Nome/CPF em 0 trechos (8.1); classificador não vê mais matéria de outro aluno (9.2) |
| Telas e navegação | — | 55 | 60 | 70 | Olho das fontes, etiqueta por assunto e página, títulos no texto, erro legível (10.7, 10.8) |
| **Total** | **~45%** | **~65%** | **~75%** | **~79%** | Média simples das dimensões |

O que separa 79% de um MVP de mercado está agora concentrado em **a curadoria do
que vira questão** (fonte que não é matéria, tema inventado) e no **polimento da
conversa e das telas**. O motor — busca, dados, estatística, privacidade — está à
frente.

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
| 2.6 | Tutor sub-relatava progresso ("Penal e Constitucional") | Resumo de desempenho e diário filtravam pelo edital | ✅ filtro `8c06006` + diário só com fonte citada `ee77f01` (8.2) |
| 2.7 | Três números para "quanto já fiz" (22 / 26 / 28) | Meta conta questões distintas; Desempenho, tentativas | 🟡 26 × 28 resolvido por 2.2; falta a tela dizer o que cada número conta |
| 2.8 | Maestria sem gradiente | "Dominada" = caixa 3; acerto com dica não promove; 0% coberto após um mês | 🔶 regra pedagógica deliberada (LIMITACOES) |
| 2.9 | Raio-X com número fictício | "Liga Ouro, 7º de 42" e "28 flashcards" eram constantes do protótipo | ✅ `ed2b7e3` — saíram |

## 3. Mesa, edital e fila

| | Falha | Evidência | Estado |
|---|---|---|---|
| 3.1 | Disciplinas escolhidas à mão ignoradas quando havia edital | Duas mesas com fila idêntica | ✅ `8c06006` — o manual SOMA ao edital (decisão do dono) |
| 3.2 | Primeiro acesso ia ao painel com mesa criada sozinha | `mesa.padrao()` cria na 1ª chamada sem mesa | ✅ `ed2b7e3` — login leva a /mesas; portão na casca; verificado: 0 mesas criadas |
| 3.3 | Fila não alterna disciplinas | Inéditas por `ORDER BY q.id`: Administrativo nunca entrava | ✅ `fe96b3d` — rodízio por disciplina na fila e no desafio; série C/E sai inteira. Teste com duas disciplinas sintéticas |
| 3.4 | Sessão de estudo sem a matéria com mais material | Recorte (2.2) + ordem da fila (3.3) | 🟡 os dois resolvidos em teste; falta ver na tela com material real |
| 3.5 | Material que é edital subido como aula | `edital_n_4_completo` indexado como apostila (22/09) | ⏳ ficou pronto SEM disciplina e SEM assunto — o classificador não o tomou por aula, mas nada avisa o aluno, e sem disciplina ele fica fora de todo recorte |

## 4. Chat — pedido e intenção

| | Falha | Evidência | Estado |
|---|---|---|---|
| 4.1 | Negação ignorada | `pedido.treino("sem questões")` → {'quantidade': 2}; gerou 5 questões num pedido de planejamento | ✅ `9d0b0ef` — 16 casos nos dois sentidos; validado ao vivo (0 questões) |
| 4.2 | Pedido de mapa gerava questão | "quero questões; quais são os assuntos?" | ✅ `cbb82fa` (pedido-v9) |
| 4.3 | Troca curta de disciplina | "e no processo penal?" seguia o assunto anterior | ✅ `cbb82fa` — validado ao vivo ("e no direito administrativo?" mudou de matéria) |
| 4.4 | Não responde a pergunta feita | "o que é constituição?" → poder constituinte; ao vivo, **pior**: "o que é proposição composta?" → "isso já avança… por ora, as simples" | 🟡 `05e233e` — prompt: a pergunta do aluno vem antes da ordem de ensino; e a consulta passa a ser a pergunta dele (9.3). Validado em 1 conversa real (peculato culposo respondido na hora); falta volume |
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
| 6.3 | Não dava a página e não admitia | `chunk.pagina` vazio em 100% dos trechos | 🟡 `89296ca` — página em 100% dos trechos do PDF (é a do PDF, não a impressa no cabeçalho: a apostila de lógica diz 35 onde o PDF diz 36). Falta o tutor recebê-la no contexto e conferir ao vivo |
| 6.4 | Emenda irrelevante depois de recusar | Lei falsa recusada + trecho aleatório do CPP | ✅ ao vivo: recusou e trouxe o art. 34 da Lei 8.112 (exoneração), pertinente e correto |
| 6.5 | "Boa noite." fora de hora | Resposta a pedido direto começando por saudação | ✅ ao vivo: saudou só quando saudado |
| 6.6 | Tique "Isso já é o item X / Sigo para…?" | Quase todo turno | 🟡 `05e233e` — sem o exemplo literal no prompt; oferta no máximo 1 turno em 3. 6 turnos reais: "Sigo para" 0×; mas "Consegue…?" 2/6 e uma pergunta repetida |
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
| 8.1 | **Cabeçalho e marca d'água repetidos em quase todo trecho** | 160–167 de 219 trechos da apostila começam com "Aula 00 / PC-PR… / site / **CPF e nome do aluno** / página / total". Vai ao Gemini em todo prompt que usa o trecho, dilui o sentido e casa no lexical em tudo | ✅ `89296ca` — moldura = linha na BORDA (até 8 linhas) de ≥ metade das páginas, dígitos normalizados. A faixa da borda é medida: 4 das 17 apostilas extraem uma palavra por linha, e sem ela "de"/"que" sairiam do texto. 18 materiais reindexados: 0 trechos com nome/CPF, ~7% das palavras removidas (só as 6 linhas de moldura de cada apostila) |
| 8.2 | **O diário registra como "estudado" o assunto de qualquer trecho recuperado** | Saudação e pedido de plano deixaram "Direitos sociais / Direito Constitucional" no `estudo_teoria`; a troca para Administrativo registrou "Da Licença para Atividade Política", rubrica de um artigo que nem entrou na resposta. O tutor respondeu "você estudou Constitucional" e omitiu Administrativo | ✅ `ee77f01` — só os trechos de `fontes_usadas`; sem fonte citada, nada entra. As linhas antigas continuam no banco (pergunta 4 ao dono) |
| 8.3 | Plural sem concordância | "0 de 1 tentativas", "em 1 tentativas", "(1 reincidências)" | ✅ `ee77f01` — painel, desempenho, KPIs, prompt e intervenção |
| 8.4 | Título da conversa é a primeira fala | Recentes: "boa noite" numa conversa sobre proposições | ✅ `ee77f01` — refeito no primeiro turno com fonte citada (a fala, ou o assunto citado se ela for curta); depois não muda |
| 8.5 | `GET /edital` responde 404 quando não há edital | 33 vezes numa sessão; a tela trata, o console acusa erro | ✅ `ee77f01` — 200 com `null` |
| 8.6 | Edital subido como material de aula | `edital_n_4_completo` ficou pronto sem disciplina nem assunto | ⏳ ver 3.5: detectar e avisar que é edital |
| 8.7 | Classificação sem edital escolhe a disciplina errada | A Aula 00 de Ciências Forenses (perícias) foi classificada como "Direito Processual Penal": sem edital, o classificador prefere nome que já existe no acervo, e "Ciências Forenses" ainda não existia | 🟡 `fe96b3d` — o vocabulário do classificador inclui as disciplinas dos editais e alvos manuais do aluno. Medido com o modelo real: sem edital 3/3 "Processual Penal" (a aula é de perícia no CPP, 141 menções — defensável); com a disciplina do edital, 3/3 "Ciências Forenses / Perícias e Peritos". Uma regra de prompt ("matéria vizinha não é a mesma") foi testada, não mudou nada e saiu. Falta reclassificar o que já foi classificado quando o edital chega |

## 9. Achados de 23/09/2026 (ao consertar e testar)

| | Falha | Evidência | Estado |
|---|---|---|---|
| 9.1 | Reindexar material do aluno deixava a questão citando trecho apagado | `indexar` apaga e recria os trechos; `fonte_chunks` guarda id cru e só o `reingest.py` (lei pública) remapeava | ✅ `89296ca` — remapeia pelo conteúdo (trecho novo com ≥ 50% das palavras do antigo); sem correspondente, id antigo fica e é logado. As 2 questões reais apontam para trechos que existem e tratam do assunto delas |
| 9.2 | **Classificador via nome de matéria de outro aluno** | `_classificar_se_faltar` montava a lista com `SELECT DISTINCT disciplina FROM documento`, sem dono — a classe de vazamento que `mesa.disciplinas_do_acervo` documenta | ✅ `fe96b3d` — `material.vocabulario_do_aluno`, com teste de isolamento |
| 9.3 | **Pergunta nova do aluno buscava pela resposta anterior do tutor** | "e o peculato mediante erro de outrem?" depois de pergunta do tutor caía no eco; o art. 313 não veio e o tutor afirmou "está no art. 312" | ✅ `05e233e` — abrir como quem pergunta ("o que é", "qual", "como funciona", "e o <assunto>?") com assunto próprio é iniciativa. 101 falas gravadas: 5 mudam de classe, todas perguntas novas. Rodada real: art. 313 recuperado e citado certo |
| 9.4 | 52 testes pulavam calados com o acervo vazio | Fila, simulado, isolamento entre alunos — todos com `pytest.skip("acervo vazio")` desde o reset | ✅ `ee77f01` — fixture `acervo` semeia questões públicas sintéticas e as apaga; 516 rodam, banco termina igual |
| 9.5 | `--reprocessar` acusava 16 "questões sem proveniência" que nunca existiram | Relia `fonte_chunks` no banco atual, e as questões antigas saíram no reset | ✅ `05e233e` — questão que não existe mais vira aviso |

Validado ao vivo e funcionando: negação (4.1), encerramento (4.5), troca curta
(4.3), tentativa do chat nas estatísticas (2.1 — Panorama "0 de 1", 1 revisão,
1 no caderno), saudação (6.5), recusa de lei falsa com complemento pertinente
(6.4), admitir que não sabe a página (6.3), primeiro acesso pela mesa (3.2) e
painel sem número fictício (2.9).

## Ordem sugerida para o que falta

1. **Curadoria da questão** (5.1, 5.2, 1.3): regra universal para trecho que não é
   matéria (capa, índice, apresentação) antes de gerar.
2. **Conversa** (4.4, 4.7, 6.6): validar em volume com `./testar.sh --livre` e
   `--cenario todos`; o tique de fechamento ainda aparece.
3. **Edital** (8.7, 3.5): reclassificar quando o edital chega; avisar edital subido
   como aula.
4. **Selo e fonte legíveis** (6.1, 6.2): nome do edital no cartão, título do material
   no lugar do nome de arquivo.
5. **Telas** (7.x): polimento, uma tela por vez.
6. **Decisões do dono** (1.8, 2.8, diário antigo): hooks de estado, gradiente da
   maestria, linhas do diário gravadas antes do conserto.

## 10. A conversa real de 24/09/2026 — Ciências Forenses "como apostila"

O dono pediu cinco vezes, com palavras diferentes, para estudar pelo material na
ordem e sem perguntas ("na ordem", "todo o conteúdo do tópico 2.1", "na ordem que
os materiais trazem", "não quero responder perguntas", "como se estivesse lendo a
apostila, sem pausas"). Recebeu uma frase e uma pergunta por turno, a conversa
derivou para o inquérito policial do CPP, e o último turno foi a mensagem
"LLM indisponível: resposta truncada em 1500 tokens". Repetida com o modelo real
depois dos consertos (sem gravar nada na conta), a mesma sequência lê a Aula 00
de Ciências Forenses do começo, em ordem, com 275–458 palavras por turno.

| | Falha | Causa medida | Estado |
|---|---|---|---|
| 10.1 | **Não havia como ler o material na ordem** | A busca por sentido não conhece ordem: cada turno trazia os 6 trechos mais parecidos com a fala, de qualquer lugar | ✅ `core/leitura.py` — pedido de avanço ("continua", "segue", "certo" depois de leitura, "como apostila", "na ordem do material") lê os próximos trechos por `chunk.ordem`; pergunta no meio vai à busca e a leitura fica onde estava; "aprofunda" reexplica a mesma janela. Marcador em `mensagem.fontes` (`sequencial`, `ordem`) — sem migração. Prompt: turno tipo 0, aula expositiva sem limite de parágrafos e sem pergunta de diagnóstico |
| 10.2 | Resposta curta demais para substituir o PDF | Prompt limitava exposição a 2 parágrafos e fechava com pergunta; `max_tokens=1500` | ✅ leitura com 6000 tokens de teto e regra "não encurte"; primeira janela dobrada (capa/sumário/apresentação); emenda de frase entre turnos (a sobreposição do chunker e a quebra de página faziam turno terminar em "esclarecer e") |
| 10.3 | **Leitura do material errado virava texto inventado** | Achado nos testes: "estudar na ordem… o conceito inteiro" foi à busca e voltou gabarito de Administrativo; o modelo escreveu sobre perícia em cima dele | ✅ o material sai da conversa (disciplina nomeada → material citado há pouco → disciplina das falas recentes → busca por último); prompt "fiel ao trecho, e só a ele" |
| 10.4 | Edital de outro concurso (Transpetro) como fonte | Subido como aula; a busca do chat não recorta por disciplina | ✅ migração 033 (`tipo='edital'`), `material.parece_edital` (≥ 12 de 23 marcas e ≥ 1 "inscri"/mil palavras: edital 17 e 2,8; nenhuma apostila acima de 7 e 0,2); aviso em Meus materiais com link para Meu edital |
| 10.5 | "Essa matéria não veio no seu material" — havia a apostila | Classificada como Processual Penal antes do edital; o edital põe Processual Penal dentro de Penal | ✅ confirmar edital reclassifica o palpite do MODELO com o vocabulário do edital (3/3 Ciências Forenses; controles estáveis); o que o aluno digitou não muda |
| 10.6 | "O que você tem de material?" respondido pelos trechos do turno | Não havia inventário no prompt | ✅ `### Material que o aluno subiu`, por disciplina do edital, com assunto e número da aula |
| 10.7 | Fontes sempre à mostra, com nome de arquivo repetido | — | ✅ olho para ocultar/mostrar (lembrado no navegador); etiqueta por assunto com faixa de páginas; "lido do material" na leitura |
| 10.8 | "LLM indisponível: resposta truncada em 1500 tokens…" na tela | Detalhe técnico do 503 virava balão do tutor | ✅ uma segunda tentativa com folga quando o modelo bate no teto (`llm.ErroTruncado`); aviso legível ao aluno, motivo no log |
| 10.9 | Abertura "vamos continuar Direito Administrativo, licença para atividade política" | Linhas do diário gravadas antes do conserto 8.2 | ✅ linhas apagadas com backup. E o convite a testar ("NENHUMA questão") só vai ao prompt na abertura: chegava em todo turno e o tutor oferecia questão em 3 de 6 turnos |
| 10.10 | "Vamos por partes para não acumular" — recusou "todo o conteúdo do 2.1" | Regra UMA DIVISÃO POR VEZ | ✅ o pedido vira leitura (10.1), onde a regra não vale |

## 11. Conversa real de 24/09/2026 (2ª) — matéria sem material

O aluno pediu Legislação Estadual e Institucional, que não tinha em material
nenhum, e pediu "seguir a ordem do edital", "um aulão", "como se tivesse lendo um
pdf". Nenhum turno foi de leitura, e o tutor descreveu por cinco turnos uma
"estrutura da Polícia Civil" que não estava em trecho algum (0 fontes citadas em
todos). O botão "Quero questões sobre isto" aparecia embaixo de tudo.

| | Falha | Causa medida | Estado |
|---|---|---|---|
| 11.1 | **Inventou conteúdo de matéria sem material** | A busca trouxe trechos de Constitucional e o prompt não sabia que a matéria pedida não tinha fonte | ✅ `assunto.disciplina_em_foco` + bloco "### Cobertura do material": trechos de outra matéria saem, o tutor diz na 1ª frase que não há material, mostra o que o edital cobra e pede o material. Validado com o modelo real (4 turnos honestos) |
| 11.2 | "Legislação institucional" não era reconhecida como a disciplina | `disciplina_citada` exige todas as palavras distintivas | ✅ nome de 3+ palavras casa com 2 e 60%; continuação ("todo o conceito disso") herda a matéria, pergunta com assunto próprio não |
| 11.3 | Pedido de leitura não disparava | Faltavam "seguir a ordem do edital", "aulão", "lendo um pdf", "todo o conceito" | ✅ gatilhos novos; e a leitura lê o material da matéria EM FOCO, nunca o de outra |
| 11.4 | Botão de questões sem assunto | Aparecia sob qualquer resposta | ✅ só com fonte citada ou leitura na última resposta |

## 12. Conversa real de 24/09/2026 (3ª) e a primeira bateria sobre material real

A conversa: "você não consegue me ensinar nada de legislação?" voltou a inventar;
"mapa mental e trilha seguindo a ordem do edital" abriu uma apostila de
Constitucional; "sim" a uma oferta do próprio tutor o fez ensinar a Constituição
do PR sem material; a reclamação "você tá me trazendo resumos…" leu Constitucional
em vez do Administrativo combinado; "em continua o conteúdo de Administrativo" não
foi reconhecido; as questões "sobre isto" saíram de outras páginas e ficaram
grudadas no fim da conversa. Cada turno foi conferido contra `mensagem.fontes`.

| | Falha | Estado |
|---|---|---|
| 12.1 | Matéria em foco perdida em fala de reclamação ou aceite | ✅ nome da disciplina e vocabulário de estudo não contam como assunto novo; proposta do tutor com UMA matéria conta; oferta com duas deixa a escolha em aberto; em fala do tutor só o nome inteiro vale |
| 12.2 | Planejamento virava leitura; "em continua", "prossiga", "volta pro X, de onde parou", "pela apostila" não disparavam | ✅ `leitura-v4` |
| 12.3 | Voltar a uma matéria recomeçava a apostila | ✅ `conversa.marcadores_de_leitura`: onde parou em CADA material, em todas as conversas |
| 12.4 | Leitura resumia (~300 palavras por turno qualquer que fosse o trecho) | ✅ meta de tamanho no prompt (70% das palavras do trecho); janela de 4.500 caracteres. Janela dobrada foi medida e revertida: com o dobro de texto a resposta caiu para 15% dele |
| 12.5 | Tutor não sabia o que já foi lido | ✅ inventário diz "lido até a p. X de Y" por material |
| 12.6 | Questões "sobre isto" de outras páginas | ✅ saem dos trechos que a última resposta citou (`geracao._dos_trechos`) |
| 12.7 | Questões grudadas no fim da conversa | ✅ ancoradas no turno em que nasceram; recolhem em "Questão · tema — abrir" quando a conversa segue. Conferido no navegador com a API simulada |
| 12.8 | Aceitar ("sim") oferta do tutor destravava ensinar sem material | ✅ regra explícita no bloco de cobertura |

**A bateria** (`bateria_conversa.py`, 6 cenários, 34 turnos com o modelo real):
0 falhas na última rodada. Pegou e ajudou a consertar 12.1 (texto de perícia com
"esfera administrativa" lido como o tutor nomeando Direito Administrativo), 12.2,
12.3 e 12.4. Fica pendente e observado:
- "não entendi essa parte" / "aprofunda" reexplicam o trecho, mas mais curto que a
  primeira leitura (89–163 palavras);
- "sim" depois de uma oferta com duas matérias: o tutor escolhe e começa, mas sem
  citar a apostila;
- "resumão de tudo que vimos" sai curto (40–80 palavras).

## 13. "Domina o seu edital": o edital ligado ao material por subitem (28/09/2026)

A promessa da tela de entrada ("domina o seu edital") só existia no nível da
disciplina: nenhuma tabela ligava um ponto do programa aos trechos do material.

| | Entrega | Estado |
|---|---|---|
| 13.1 | Mapa por subitem (migração 035, `core/cobertura.py`): cada ponto do edital com estado (no material, só citado, sem material, conferindo) e onde está (apostila e páginas) | ✅ |
| 13.2 | Como decide, medido num edital real com 17 apostilas: busca por sentido sozinha não separa (notas do e5 de 0,82 a 0,87 para tudo); por expressão acerta ~85% com cobertura falsa; candidatos da região mais densa da apostila certa, sem sumário, trecho-índice nem questão comentada, e o modelo julga cada par subitem–trecho | ✅ Constitucional: nacionalidade, direitos políticos, Poderes, remédios, controle e Polícia Civil na aula certa, com páginas |
| 13.3 | Custo: uma chamada por item do edital (36 no edital da PC-PR), ao confirmar o edital; material novo só marca a disciplina e a verificação roda depois, uma vez; sem cota fica o resultado por texto, reverificado no máximo a cada 6 h | ✅ |
| 13.4 | Tela Meu edital: por disciplina, quanto do programa está no material, abrindo para cada ponto com o selo e a apostila/páginas; confere sozinha enquanto houver disciplina pendente | ✅ conferido no navegador |
| 13.5 | Tutor: "onde está X?" responde com apostila e páginas; "o que me falta?" responde pelo mapa; ponto sem material é dito, não ensinado de memória | ✅ validado com o modelo real |
| 13.6 | "Na ordem do edital" lê ponto por ponto: abre a apostila onde o próximo ponto não lido começa e anuncia o ponto; "próximo item" avança; no fim, lista o que não tem material | ✅ em teste; com o modelo real depende da leitura gravada |
| 13.7 | "Próximo item do edital" gerava questões ("item" lido como item Certo/Errado) | ✅ `pedido`: item do programa não é pedido de treino |

**Limites conhecidos** (em `docs/LIMITACOES.md`): o modelo atual oscila em parte
dos subitens entre rodadas ("Poder Legislativo" 1 ou 4 trechos; "ação popular"
citado ou sem material); ainda não há como o aluno corrigir um ponto na tela (o
banco já prevê `metodo = 'aluno'`); o mapa usa só o material do aluno, não a lei
seca do acervo.

