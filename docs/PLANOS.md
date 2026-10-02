# Planos — melhorias que dependem de dinheiro, e o que não engessar até lá

Duas coisas neste arquivo, e só elas:

- **Seções 1 e 2:** melhorias futuras que dependem de gastar (cota maior, modelo
  melhor, máquina, contrato). Ficam no radar; nada aqui está ligado.
- **Seção 3:** onde o código ainda está preso ao provedor atual, para que trocar
  de modelo ou escalar seja configuração e não reescrita.

Estado registrado em 24/09/2026.

## 1. Leitura em fluxo contínuo costurada ("Seamless Streaming")

### O que já existe (todos os planos)

| Peça | Estado | Onde |
|---|---|---|
| Paginação no backend: o pedido de leitura manda ao modelo só os próximos trechos do material (~4.500 caracteres, 2–3 páginas), a partir de onde o aluno parou naquele material | ✅ | `core/leitura.py` (`janela`, `planejar`), marcador em `mensagem.fontes` (`conversa.marcadores_de_leitura`) |
| Texto aparecendo na tela enquanto o modelo escreve | ✅ só na leitura | `/perguntar/fluxo` (SSE), `llm.gerar_em_fluxo`, `perguntar(..., aoPedaco)` na tela |
| Meta de tamanho: a aula de cada turno tem ~70% das palavras do trecho | ✅ | `leitura.meta_de_palavras` |

Uma requisição ao modelo por turno. Medido em 24/09/2026 com o modelo real: 250 a
580 palavras por turno de leitura, fiéis ao trecho.

### O que fica para o plano pago: várias chamadas por turno, costuradas

Cada "continua" passa a entregar uma seção maior do material sem o aluno pedir de
novo:

1. O backend pega 2 ou 3 janelas seguidas do material (6 a 9 páginas).
2. Chama o modelo uma vez por janela, em sequência, cada chamada recebendo o fim
   da anterior para emendar sem repetir (a emenda de frase já existe:
   `leitura.emendar`).
3. Transmite tudo para a mesma bolha na tela, na ordem. O aluno vê uma aula longa
   e contínua, sem saber que foram várias chamadas.
4. O marcador avança para o fim da última janela.

**Por que não está ligado hoje:** multiplica por 2 ou 3 as requisições de cada
turno de leitura, e requisição por dia é o recurso que acaba no plano gratuito do
Gemini (em 24/09/2026 a cota esgotou nos quatro modelos no meio do uso).

**Por que não é "mandar o PDF inteiro":** trecho grande numa chamada só faz o
modelo resumir. Medido em 24/09/2026: com o dobro de texto, a resposta continuou
com ~300 palavras e cobriu 15% do trecho. O ganho vem de várias chamadas curtas,
não de uma chamada com mais texto.

**Não vem de graça com o plano: precisa ser codado.** Pagar só remove o motivo
de não ter feito. As peças difíceis já existem (janela em ordem, emenda de frase,
transmissão, marcador); falta o laço, a costura na mesma bolha, o marcador de
várias janelas e o parâmetro por plano (abaixo).

**Antes de codar, medir se ainda é preciso.** A costura só existe porque o modelo
atual resume quando recebe texto demais (com o dobro de janela cobriu 15% do
trecho, 24/09/2026). Um modelo melhor, vindo com o plano, pode seguir a meta de
tamanho numa janela maior, e aí UMA chamada por turno já entrega mais páginas,
pela metade do custo. Quando houver o modelo novo: rodar `bateria_conversa.py`
com (a) janela grande e uma chamada e (b) janelas costuradas, e comparar a
proporção do trecho coberta e a fidelidade. Só codar a costura se (a) continuar
resumindo.

**Para implementar:**

- Um parâmetro de plano, por exemplo `janelas_por_turno` (1 no gratuito, 2–3 no
  pago), lido em `leitura.planejar`.
- Um laço em `socratic.explicar`, no ramo `plano` (hoje uma chamada a
  `gerar_em_fluxo`): N chamadas, cada uma com a janela seguinte e o fim do texto
  anterior; os `ao_gerar` vão para o mesmo fluxo SSE.
- Fontes do turno = união das janelas, com `sequencial` e `ordem` (o marcador já
  sai daí).
- Validar com `bateria_conversa.py`: turnos de leitura com 2–3 vezes mais
  conteúdo, sem repetição entre as partes costuradas.

### Também candidato: fluxo nas perguntas comuns

Hoje só a leitura aparece em pedaços; a pergunta comum chega inteira, porque a
lista de fontes (`fontes_usadas`, JSON) só existe no fim. Transmitir o texto e
mandar as fontes num evento final exige trocar o envelope JSON por texto com as
fontes ao fim. Não gasta requisição a mais; fica aqui porque muda o contrato da
resposta.

## 2. Radar: limitações do nível gratuito que um plano resolveria

Medido na telemetria (`telemetria_llm`, migrações 030 e 034) entre 17 e 25/09/2026,
salvo onde dito.

| # | Limitação hoje | Medida | O que o plano mudaria |
|---|---|---|---|
| 2.1 | **Requisições por dia** | Em 24/09 a cota acabou nos quatro modelos após ~600 requisições do dia (uso do dono + testes) | Nível pago do provedor e um orçamento de requisições por aluno e por plano |
| 2.2 | **Instabilidade das reservas** | 8 dias: `3.5-flash-lite` 80 falhas em 1.093 (7%); `3.5-flash` 31 em 56; `flash-lite-latest` 25 em 31. Turno que cai na reserva leva 10–30 s | Nível pago tem capacidade reservada; a reserva deixa de ser loteria |
| 2.3 | **Modelo fraco em seguir regra** | O `flash-lite` precisou de trava em código para não inventar matéria sem material (11.1/12.8 da auditoria), repete tique de fechamento e oferta de questão, resume quando mandado não resumir | Modelo mais forte (ver 2.9). Regra de produto continua em código; o modelo melhor erra menos entre as travas |
| 2.4 | **Raciocínio comendo o teto de resposta** | Reserva `3.5-flash`: 1.478 tokens pensando para 58 de resposta, no teto de 1.500 → "resposta truncada" (23/09) | Configurar o raciocínio por modelo e por tarefa: baixo no chat, alto onde vale (correção, geração de questão) |
| 2.5 | **Tamanho da resposta e do contexto** | Chat com teto de 1.500 tokens de saída (4.000 na segunda tentativa), leitura com 6.000; histórico de 8 turnos; entrada média do tutor ~7.500 tokens | Tetos por plano; histórico maior; leitura costurada (seção 1) |
| 2.6 | **Privacidade no nível gratuito** | Pelos termos do Google, no nível gratuito da API o conteúdo enviado pode ser usado para melhorar os produtos deles; no pago, não. Vai para lá o material do aluno (já sem a moldura com nome e CPF, 8.1) e a conversa | Nível pago (ou provedor com contrato de não uso) antes de ter aluno de verdade. Para LGPD, olhar também onde o provedor processa os dados |
| 2.7 | **Indexação no CPU local, um trabalhador** | 20–180 s por apostila (reindexação de 23/09); vinte uploads fazem fila | Embeddings por API ou máquina com GPU; mais de um trabalhador (a trava por documento já existe: `TRAVA_INDEXACAO`) |
| 2.8 | **PDF escaneado não entra** | Sem OCR: "precisa de OCR" na subida | OCR, ou modelo que lê imagem de página; gasta requisição por página, é recurso de plano |
| 2.9 | **Modelo por plano** | Um modelo para todos, escolhido pela cota gratuita | Plano básico com modelo melhor (ex.: DeepSeek), plano superior com o mais forte nas tarefas que pesam (tutor, correção). Depende da seção 3 |

### Sobre o DeepSeek (candidato citado pelo dono para o plano básico)

- **Encaixe técnico:** a API é compatível com a da OpenAI e transmite em SSE, então
  entra pelo adaptador da seção 3 sem mexer no resto. Ela tem modo JSON, mas não o
  esquema de resposta que o Gemini aceita (`responseSchema`); o código já valida
  cada resposta (`_resposta_com_fontes`, `socratic` nas questões), que é o que
  segura um modelo sem esquema.
- **Antes de trocar:** rodar `bateria_conversa.py` e `./testar.sh` com ele e
  comparar pela contagem de falhas, não por impressão. Medir também a latência
  vista do Brasil.
- **Dados:** os servidores ficam fora do país; é transferência internacional de
  dado de aluno (material, conversa, desempenho), que a LGPD trata à parte. Pesa
  na escolha tanto quanto o preço.

### A medição para dimensionar o plano

Até 25/09/2026 a telemetria gravava a cota esgotada como status 0 ("sem
resposta"), não como 429 — os 119 "sem resposta" de 24/09 eram, na maior parte,
cota. Corrigido em `llm-v22` (`_post` devolve a resposta 429/5xx em vez de
levantar). A partir daí, `telemetria.resumo()` mostra quanto de cota o uso real
consome por dia e por modelo — é o número que dimensiona o plano.

## 3. Para não engessar: o que ainda está preso ao provedor atual

Levantamento do código em 25/09/2026. Nada disto custa dinheiro; é preparar a
troca de modelo e a escala para que virem configuração.

| # | Hoje | Onde | Desenho sugerido |
|---|---|---|---|
| 3.1 | **A escolha do modelo é uma só para o app inteiro.** `llm.obter()` sem tarefa em 9 chamadas; só a classificação de material (`obter("classificar")`) escolhe diferente | `socratic`, `geracao`, `edital`, `material` | Toda chamada diz a TAREFA (`tutor`, `leitura`, `avaliar`, `gerar_questoes`, `edital`, `classificar`, `julgar`), e uma tabela de configuração diz, por tarefa, provedor, modelo, reservas, teto de resposta e nível de raciocínio. Plano diferente = tabela diferente |
| 3.2 | **Teto de resposta espalhado.** 8 valores fixos no meio das chamadas (200 a 8.000) mais 3 constantes no `socratic` | idem | Sai da chamada e vai para a tabela de 3.1 |
| 3.3 | **Esquemas de resposta no formato do Gemini.** 31 ocorrências de `"OBJECT"`/`"STRING"`/`propertyOrdering` no `socratic` | `core/socratic.py` | Um formato neutro (JSON Schema padrão) no código, e cada adaptador traduz para o seu provedor (o Ollama já recebe JSON Schema; OpenAI e DeepSeek têm modos próprios) |
| 3.4 | **Raciocínio do modelo sem configuração.** O `flash` gasta até 1.478 tokens pensando, e nada controla isso | `core/llm.py` | Nível de raciocínio por tarefa na tabela de 3.1; cada adaptador traduz para o campo do seu provedor |
| 3.5 | **Dois provedores.** Gemini (com transmissão) e Ollama | `core/llm.py` | Adaptador compatível com a API da OpenAI: cobre DeepSeek, OpenRouter e a maioria dos provedores com o mesmo código, inclusive transmissão |
| 3.6 | **Modelo de embeddings fixo na coluna.** `chunk.embedding` tem 768 dimensões (e5-base) | schema | Trocar de modelo de embeddings pede migração e reindexação de tudo; registrar o modelo por trecho permite trocar aos poucos |
| 3.7 | **Sem noção de plano no banco.** Nenhuma tabela diz o plano do aluno nem o orçamento de requisições dele | schema | Tabela de plano e limites, lida pela tabela de 3.1 e pela telemetria (que já conta por chamada) |
| 3.8 | **Fila de indexação dentro do processo da API.** Um trabalhador; a trava por documento já existe (`TRAVA_INDEXACAO`) | `core/material.py` | Fila fora do processo quando houver mais de uma instância da API |
| 3.9 | **Testes gastam a cota dos alunos.** `./testar.sh` e `bateria_conversa.py` usam a mesma chave | `.env` | Chave de desenvolvimento separada, escolhida pela tabela de 3.1 |

Ordem sugerida quando for mexer: 3.1 + 3.2 + 3.4 juntos (é a mesma tabela), depois
3.3 e 3.5 (abre outros provedores), depois 3.7. 3.6 e 3.8 só quando a escala pedir.


## Índice de assuntos com modelo mais forte (036)

Hoje a marcação de assunto por trecho usa o modelo leve gratuito
(`LLM_INDICE=gemini-3.1-flash-lite`) e acerta 72–77%, medido à mão. O erro é entre
assuntos vizinhos da mesma apostila. Com plano pago:

- trocar `LLM_INDICE` por um modelo mais forte é só configuração;
- subir `INDICE_ORCAMENTO_DIA`;
- reindexar todos os materiais com `python -m core.indice`, depois de marcá-los como
  `pendente`.

Nenhum código muda.
