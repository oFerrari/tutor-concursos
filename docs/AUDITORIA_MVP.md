# Auditoria do tutor — placar do MVP

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
| Estatísticas refletem o uso | 35 | 75 | Chat conta tentativa; vocabulário único; mesma regra em todas as telas. Falta o gradiente da maestria |
| Mesa e edital | 35 | 70 | Manual soma ao edital; material entra na disciplina certa; primeiro acesso pela mesa. Falta rodízio da fila |
| Obedecer ao pedido | 40 | 55 | Negação resolvida. Falta: responde outra pergunta, não encerra, "Sigo para as questões?" |
| Qualidade da questão gerada | 30 | 45 | Duplicatas bloqueadas. Falta: capa/apresentação da apostila vira questão; tema inventado |
| Fluxo de conversa | 50 | 50 | Nada validado nesta rodada |
| Telas e navegação | — | 55 | Primeiro acesso e Raio-X honestos. Falta Mesas no layout, rótulos, celular |
| **Total** | **~45%** | **~65%** | Média simples das dimensões |

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
| 1.3 | Gerador não confere se o conteúdo bate com o trecho | Confia no ponteiro `artigo`/`trecho` que o modelo devolve | ⏳ medir antes de propor |
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
| 2.6 | Tutor sub-relatava progresso ("Penal e Constitucional") | Resumo de desempenho e diário filtravam pelo edital | 🟡 `8c06006` — código corrigido; **validar no chat** |
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
| 3.5 | Material que é edital subido como aula | `edital_n_4_completo` indexado como apostila (22/09) | ⏳ a validar na simulação |

## 4. Chat — pedido e intenção

| | Falha | Evidência | Estado |
|---|---|---|---|
| 4.1 | Negação ignorada | `pedido.treino("sem questões")` → {'quantidade': 2}; gerou 5 questões num pedido de planejamento | ✅ `9d0b0ef` — 16 casos nos dois sentidos |
| 4.2 | Pedido de mapa gerava questão | "quero questões; quais são os assuntos?" | ✅ `cbb82fa` (pedido-v9) |
| 4.3 | Troca curta de disciplina | "e no processo penal?" seguia o assunto anterior | ✅ `cbb82fa` (assunto-v13); validar no chat |
| 4.4 | Responde outra pergunta | "o que é constituição?" → poder constituinte | ⏳ |
| 4.5 | Não reconhece encerramento | "obrigado, era só isso" → mais aula; não há detector de despedida | ⏳ |
| 4.6 | "Sigo para as questões?" com a questão já na tela | 1º turno do teste ao vivo | ⏳ |
| 4.7 | Planejamento sem plano; ignora a contradição com o perfil | 20 min no chat × 3,5 h no perfil | ⏳ |

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
| 6.3 | Não dá a página e não admite | `chunk.pagina` vazio em 100% dos trechos | ⏳ dado (não se extrai página) + prompt (admitir) |
| 6.4 | Emenda irrelevante depois de recusar | Lei falsa recusada + trecho aleatório do CPP | ⏳ |
| 6.5 | "Boa noite." fora de hora | Resposta a pedido direto começando por saudação | 🟡 regra de saudação no prompt (`cbb82fa`); validar |
| 6.6 | Tique "Isso já é o item X / Sigo para…?" | Quase todo turno | ⏳ |
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

## Ordem sugerida para o que falta

1. **Conversa** (4.4–4.7, 6.4–6.6): é onde o aluno perde a confiança primeiro, e
   quase tudo é prompt — validar com `./testar.sh` e conversa real, nunca só teste.
2. **Curadoria da questão** (5.1, 5.2, 1.3): regra universal para trecho que não é
   matéria (capa, índice, apresentação) antes de gerar.
3. **Rodízio da fila** (3.3): as outras disciplinas aparecerem sem depender do id.
4. **Selo e fonte legíveis** (6.1, 6.2): nome do edital no cartão, título do material
   no lugar do nome de arquivo.
5. **Telas** (7.x): polimento, uma tela por vez.
6. **Decisões do dono** (1.8, 2.8): hooks de estado e gradiente da maestria.
