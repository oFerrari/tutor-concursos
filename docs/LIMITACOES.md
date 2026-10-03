# Limitações conhecidas e o que está em aberto

O que o sistema NÃO faz (e por quê), e o que está na fila. Saiu do `CLAUDE.md`
pelo mesmo motivo que `DECISOES.md`: é consulta, não leitura obrigatória.

Limitação declarada aqui não é bug — é escolha registrada. Antes de "consertar"
qualquer uma delas, leia o parágrafo: várias já foram tentadas e revertidas com
medição.

## Limitações conhecidas

- Multiusuário desde a migração 008 — acervo compartilhado, progresso pessoal
  (ver Decisões). `sincronizar.py` continua pensado pra alternância de UM
  usuário entre duas máquinas, não pra distribuir contas.
- JWT sem revogação POR TOKEN: token vazado vale até expirar (uma semana,
  `core/auth.py`). Aceitável pra uso pessoal/pequeno grupo; revisar se isso
  crescer. O que passou a valer (auth-v4) é que **apagar a conta revoga os
  tokens dela na hora** — `usuario_id_do_token` confere se o usuário existe, e
  antes disso "conta apagada" não invalidava nada.
- PDF escaneado exige OCR antes (`ocrmypdf`).
- Múltipla escolha não existe: só `resposta_livre` e `certo_errado` (012).
  Alternativas exigem tabela própria (texto, ordem, qual é a correta), não
  uma coluna — por isso o valor nem é aceito no CHECK, em vez de virar
  questão gravável e não renderizável.
- Questão gerada sob demanda custa cota de LLM a cada clique. Não há
  pré-geração em background nem teto por usuário; a camada gratuita do
  Gemini tem cota diária baixa, então gerar em série esgota o dia.
- `conversa` não é exportada por `sincronizar.py` (como `mesa`/`edital`):
  trocar de máquina começa o histórico do zero.
- O histórico enviado ao modelo é de 8 turnos. Conversa longa "esquece" o
  começo — é escolha (ver Decisões), não defeito, mas é limite real.
- `usuario.perfil` só tem os três campos do onboarding e ninguém os
  atualiza depois. Não há releitura do comportamento real ("perde foco
  depois de 40 min" continua sendo hipótese de produto, não dado).
- A interrupção por erros seguidos lê as tentativas mais recentes do BANCO,
  não da sessão em curso: num simulado (que corrige tudo no fim) ela só
  pode disparar depois da prova inteira, nunca no meio dela. É consequência
  do design do simulado, não bug.
- Camada gratuita do Gemini: cota diária baixa e prompts podem ser usados
  para treinamento. Não sirva conteúdo sensível por esse caminho.
- Artigo revogado pode herdar a nota do artigo seguinte (cosmético).
- Trocar modelo de embeddings exige `ALTER TABLE` e reindexação.
- `sincronizar.py` resolve alternância entre duas máquinas de um usuário só,
  não edição simultânea. Estudar nas duas sem exportar perde a mais recente.
- `sincronizar.py` não exporta `simulado`/`tentativa.simulado_id`: histórico
  de provas não viaja entre máquinas (o progresso em si — caixa,
  prox_revisao — viaja, porque isso vem da tentativa comum).
- `sincronizar.py` também NÃO exporta `mesa`/`edital`/`topico` (migração
  010): a outra máquina precisa rodar `python edital.py ... --mesa "..."` de
  novo pra recriar o recorte. O progresso continua viajando inteiro, porque
  é do usuário e não da mesa — que é justamente o que a decisão da 010
  torna verdade. Exportar mesa exigiria resolver identidade de mesa entre
  bancos (o id é sequencial e muda), o mesmo problema que `(norma, artigo)`
  resolve pros chunks; o nome da mesa serviria de chave natural, mas não
  vale construir isso antes de existir uma segunda máquina com mesas.
- Mesa sem alvo declarado (nem edital nem escolha manual) mostra o acervo
  inteiro — declarado, não silencioso: a CLI imprime "sem edital — acervo
  inteiro" e o cartão do lobby esconde a barra e pede o edital (017).
- O alvo manual não SOMA ao edital: quando o PDF existe, ele vence inteiro.
  Corrigir uma disciplina que o extrator errou se faz na curadoria (011),
  não pelo alvo manual.
- A troca de mesa é por aba do navegador, não por dispositivo: a mesa ativa
  vive em `localStorage` (`tutor_mesa`), do mesmo jeito que o token. Abrir
  duas abas em mesas diferentes funciona (é o motivo de o header ser por
  requisição), mas fechar o navegador e abrir noutra máquina começa da mesa
  padrão.

- A indexação da biblioteca roda no PROCESSO do servidor
  (`BackgroundTasks`), não num worker. Reiniciar o uvicorn no meio deixa
  material em `processando` pra sempre — por isso a tela tem "tentar de novo"
  também nesse status, e não só em `falha`. Cada indexação também segura uma
  thread do pool do FastAPI pelos minutos que durar: com o limite default (40)
  um lote de 14 arquivos cabe folgado, um de 50 começaria a travar rota
  síncrona. Worker de verdade é o conserto, e é o mesmo item já aberto em
  "Pré-geração em background".
- O classificador de material custa UMA chamada de LLM por arquivo, contra a
  cota gratuita baixa do Gemini. Num lote grande isso queima o dia — quem já
  sabe do que é o material preenche disciplina/assunto e o classificador nem
  é chamado.
- Indexar link não é allowlist de domínio: `material.baixar` só garante que o
  endereço é PÚBLICO (anti-SSRF), não que o conteúdo é confiável.
- `sincronizar.py` não exporta a biblioteca do aluno (019): os bytes do PDF
  nem ficam no servidor (só o nome, em `documento.origem`), então a outra
  máquina precisa subir os arquivos de novo.

- `conceitos_fracos` agrupa por STRING EXATA: "confunde impessoalidade com
  moralidade" e "confundiu impessoalidade e moralidade" contam separado. Na
  prática o modelo devolve nome curto de conceito e isso quase não dói (medido),
  mas é limite real — agrupar por similaridade exigiria embeddings num caminho
  que hoje custa zero.
- Conceito só existe onde o LLM avaliou, ou seja NUNCA em item CERTO/ERRADO
  (corrigido em código, 012). Numa mesa Cebraspe a lista fica curta de propósito:
  a alternativa seria pagar avaliação de LLM em item binário pra preencher
  relatório.
- `sincronizar.py` não exporta `tentativa.conceito_faltante`.
- `buscar()` não tem piso de relevância NENHUM: quando o acervo não cobre o
  assunto, devolve os 6 vizinhos mais próximos do ruído com confiança total, e
  `geracao` gera a partir deles. Medido depois da 022: "aplicabilidade e eficácia
  das normas constitucionais" (doutrina, não lei seca) devolve CP art. 9º
  "Eficácia de sentença estrangeira" por colisão lexical. O tutor consegue
  EXPLICAR o assunto (a apostila do aluno cobre) e o gerador estruturalmente não
  consegue COBRÁ-LO, porque `geracao` só usa acervo público (008).

  **E o piso de relevância — o conserto óbvio — foi MEDIDO e não funciona neste
  acervo** (números e gabarito em Decisões, "CEMITÉRIO DE IDEIAS"): as faixas de
  distância de cosseno de coberto e não coberto se sobrepõem (0,110–0,180 contra
  0,138–0,201), e "violência doméstica contra a mulher", que o acervo não tem,
  fica MAIS PERTO que "peculato", que ele cobre em cheio. A razão d1/d20 separa
  medianas, não faixas. Quem resolveria é um cross-encoder reordenando os 20
  primeiros — outro modelo e outro custo de CPU por turno. Enquanto isso a defesa
  é a CONSULTA ser boa (`core/assunto.py`), não o corte: conversa inteira sobre
  Lei Maria da Penha gerando questão de ajuda de custo era consulta ruim, não
  piso ausente.

  **O que SOBRA disso, e é assunto não coberto virando desvio na pergunta
  final.** Com a consulta certa e o filtro de citação valendo, o corpo da
  resposta fica no assunto e declara a ausência — mas o fecho puxa o instituto
  vizinho que TEM trecho: numa conversa sobre Lei Maria da Penha, três de três
  rodadas terminaram perguntando sobre abandono material (CP art. 244). Faz
  sentido do lado dele: precisa terminar com pergunta e só tem material de outro
  assunto na mão.

  Tentei consertar por prompt — uma cláusula mandando a pergunta final ser do
  assunto da conversa e perguntar SEM citar quando não houver trecho. Medido em
  três rodadas: o desvio continuou 3/3, e o único efeito foi o modelo largar a
  citação legítima em 2 das 3. Perda líquida, revertida. Gravidade é outra que a
  do defeito original (o corpo está certo, a citação é real, e a matéria é do
  edital do aluno), e o conserto de raiz é COBERTURA de acervo, não texto de
  prompt: o gerador continua estruturalmente incapaz de cobrar doutrina e lei
  extravagante, porque só usa acervo público (008).

- O extrator lê o Cesgranrio, e não perfeitamente: **cabeçalho de disciplina que
  quebra de linha ainda é perdido ou truncado** (`III- DADOS E BASES DE\nDADOS`
  vira "Dados"), então a ênfase de Administração sai com 5 das ~14 matérias que o
  edital lista, e 1 dos 33 cargos sai sem disciplina nenhuma. O conserto óbvio
  (deixar o nome atravessar a quebra) foi medido e é PIOR — ver Decisões. O que
  NÃO acontece mais é o cargo errado: as 33 ênfases são oferecidas na curadoria
  e só a escolhida entra na mesa.

- **A nota da escala de naturalidade (`avaliar_chat.py`) NÃO separa versões de
  prompt, e isto foi medido.** A régua tem sete dimensões ancoradas, evidência
  obrigatória por nota e total normalizado em 0-100. Parece instrumento; no
  tamanho de amostra que dá pra pagar, não é.

  Três rodadas do cenário `regressoes`, entrada IGUAL, mesmo prompt: **36, 93 e
  57**. Suspeitei da temperatura (0.3 para tudo, em `core/llm.py`) e a tornei
  parametrizável, com o juiz em 0. Não resolveu, e o experimento que atribui a
  culpa é este: o **mesmo transcript**, julgado duas vezes a temperatura 0, deu
  **86 e 100** — a dimensão `ancoragem` virou de 0 para 4 sozinha. Ou seja, o
  Gemini não é determinístico nem em 0, e há duas fontes somadas: o juiz (~14
  pontos na mesma entrada) e o tutor a 0.3, que gera conversa diferente a cada
  rodada.

  Efeito que se queria detectar (uma versão de prompt contra a outra): ~17
  pontos. Ruído: ~64. Não dá.

  **O que É confiável no mesmo script:** a contagem de erros de regra, que é
  código e não opinião. O vazamento da palavra "acervo" saiu de 2, 1, 1 erros
  em três rodadas do `socratic-v35` para 0, 0, 0 no `v36` — sinal limpo, na
  mesma medição em que a nota dizia que havia PIORADO. Use os erros pra decidir
  e o "o que mais atrapalha" do juiz como ponteiro pra ir ler o turno; não use a
  nota pra aprovar ou reprovar um prompt.

  Caminhos não tentados, se um dia a nota precisar valer: rodar o tutor também
  em 0 (mede um tutor que não é o produto), pontuar cada dimensão em chamada
  separada, ou tirar a média sobre os oito cenários em vez de repetir um
  (`--cenario todos`) — este último é o mais barato e o único que amplia a
  cobertura junto.

## Resolvido em 21/09/2026: troca curta de disciplina muda o foco da busca

"e no processo penal?", dito depois de uma pergunta do tutor, agora é troca
explícita: `disciplina_citada` casa "processo" com "processual" por prefixo
longo, `e_eco` devolve `False` e `em_foco` usa apenas a fala nova, sem arrastar
a disciplina abandonada. A resposta simples ao menu ("direito penal") continua
sem virar consulta. Coberto por `tests/test_assunto_troca_de_disciplina.py`.

## Paráfrase da mesma pergunta não é detectada como duplicata (22/09/2026)

A geração deixa de gravar a mesma pergunta no mesmo trecho quando o enunciado tem
≥ 90% das palavras de conteúdo em comum (`geracao.LIMIAR_DUPLICATA`). Paráfrase
com outra redação passa. Medidos três sinais, entre questões do mesmo trecho, e
nenhum separa paráfrase de pergunta distinta do mesmo artigo: sobreposição do
enunciado ("pena cominada" × "conduta típica" = 0,42; paráfrase real = 0,40),
sobreposição do gabarito, e sentido pelo e5 (perguntas diferentes do mesmo
artigo em 0,88–0,94). Um limiar mais baixo apagaria a pergunta sobre a pena
achando que era a sobre a conduta.

## ~~A fila não alterna disciplinas~~ — resolvido em 23/09/2026

Registrado em 22/09 (inéditas por `ORDER BY q.id`, Direito Administrativo fora de
toda fila). Resolvido por `scheduler.ineditas_em_rodizio` (`fe96b3d`): 1ª de cada
disciplina, depois a 2ª, com a série Certo/Errado contando como uma unidade.

## Maestria sem gradiente — decisão pendente do dono (22/09/2026)

"Dominada" é caixa ≥ 3, e acerto com dica não promove
(`scheduler_regras.proxima_caixa`). No chat a dica aparece sozinha depois do
primeiro erro, então quase nenhum acerto do chat promove. Resultado visível:
"0% coberto" e "100% do edital aberto" depois de um mês de estudo. É regra
pedagógica deliberada, não bug; mudar é decisão de produto.

## Leitura em sequência — o que ela ainda não faz (24/09/2026)

`core/leitura.py` lê o material do aluno na ordem dele. Medido com o modelo real
na Aula 00 de Ciências Forenses, e com estes limites conhecidos:

- **Começa sempre do começo do material.** "Lê como apostila a parte de
  balística" abre o material da disciplina desde o início, não na seção pedida.
- **Um material por vez.** No fim, o tutor nomeia o próximo da disciplina (pela
  ordem do título), mas quem pede para seguir é o aluno.
- **"Continuar a leitura" só aparece na última resposta**, e a conversa só
  retoma a leitura pelas últimas 20 respostas do tutor.
- **A janela é por tamanho de texto** (~3500 caracteres; o dobro no começo, que
  é capa, sumário e apresentação em toda apostila). Trecho de parágrafo enorme,
  como o texto justificado que o pypdf extrai palavra por linha, pode vir sozinho.
- **Apresentação do curso** às vezes ainda é explicada no primeiro turno: a
  regra está no prompt, sem filtro em código (ver 5.1 da auditoria).

## Classificador de material no modelo local — medido e desligado (24/09/2026)

`LLM_CLASSIFICADOR=ollama` existe (`llm.obter("classificar")`, Gemini de reserva),
mas fica DESLIGADO nesta máquina. Medido nos 17 materiais do dono, contra os
rótulos atuais: `qwen2.5:3b` acertou a disciplina em **5/17**, mandou seis aulas
de Constitucional para Administrativo, devolveu disciplina vazia em seis, e
levou 23 s por material (Gemini: ~1 s). Modelo de 7B não cabe com folga em 7 GB
de RAM. Ligar só numa máquina com memória para um modelo maior, e depois de
repetir a mesma medição (régua = rótulos atuais que o aluno não corrigiu).

## Mapa do edital por subitem — o que ele ainda erra (28/09/2026)

`core/cobertura.py` liga cada ponto do edital aos trechos do material, com o
modelo julgando cada par subitem–trecho. Medido no edital da PC-PR:

- **O modelo atual oscila** em parte dos subitens entre rodadas, mesmo com
  temperatura zero ("Poder Legislativo": 1 ou 4 trechos; "ação popular": citado ou
  sem material). Modelo melhor está no radar de `docs/PLANOS.md`.
- **O aluno ainda não corrige** um ponto na tela ("isto está na Aula 03"); o banco
  já tem `metodo = 'aluno'` para quando existir.
- **Só o material do aluno conta.** A lei seca do acervo (CF, CP…) não entra no
  mapa, então um ponto coberto pela lei, mas não por apostila, aparece "sem
  material".
- **"Na ordem do edital" abre o ponto onde ele começa na apostila** e segue a
  leitura dali; ponto espalhado em várias partes da apostila é lido a partir da
  primeira.

## Aberto

### Débito de retrieval: a busca afoga a lei, e a consulta faz eco (16/09/2026)

Dois defeitos MEDIDOS no mesmo dia, nos dois casos com transcrição gravada em
`.logs/`. Nenhum dos dois se conserta no prompt — ficam registrados aqui para
ciclo dedicado de backend, e não como "melhoria óbvia" a ser tentada de raspão.

**1. A biblioteca do aluno afoga a lei seca.** No cenário `direto`, `me explica
peculato` devolveu *Traumatologia forense* cinco vezes e *Asfixiologia* — zero
linha do Código Penal, numa mesa (PC-PR Investigador) com apostilas de Ciências
Forenses no acervo do aluno. O tutor respondeu peculato de cabeça porque não
recebeu artigo nenhum. É o "lei afogada" de `62fab87` voltando por outro lado: a
híbrida não tem piso de relevância, e material do aluno com muitos chunks domina
o RRF quando o termo da pergunta não casa forte com nenhuma rubrica.

Onde olhar: `core/retrieval.py`, o peso dos braços léxico e vetorial, e se
documento com `usuario_id` deve concorrer em pé de igualdade com norma quando a
pergunta nomeia um instituto jurídico. Cuidado: piso de relevância vetorial já
foi medido e enterrado (ver "CEMITÉRIO DE IDEIAS" em `docs/DECISOES.md`) — a
saída não é aquela.

**2. A consulta de busca é a resposta anterior do tutor.** Visível em todo turno
2+ dos cenários `direto` e `fora_do_acervo`: `query: Boa noite. Peculato é o
crime praticado por funcionário público que...`. É o caminho `e_eco` de
`core/assunto.py` — quando a fala do aluno é eco ("e a diferença com
concussão?"), a consulta herda a última fala do TUTOR inteira. Funciona quando o
vocabulário casa, e é sorte: a prosa do tutor tem centenas de palavras e decide
a busca no lugar da pergunta.

Onde olhar: `assunto.em_foco`, ramo `e_eco`. A herança deveria ser do ASSUNTO da
fala anterior, não do texto dela — hoje é `_truncar` de prosa.


- **Múltipla escolha** (FGV, Vunesp): exige tabela de alternativas. O
  dispatcher do front (`<QuestaoInterativa>`) já tem onde encaixar o
  terceiro ramo; falta o schema.
- **Pré-geração em background.** Hoje gerar questão custa 3-5s no clique, o
  que quebra o foco. Um worker que olhasse o SM-2 e pré-gerasse o que vence
  amanhã resolveria — mas precisa nascer com TETO e prioridade (mesa ativa
  de quem estudou nos últimos N dias), senão esgota a cota gratuita antes
  do meio-dia.
- **Áudio (sabatina por voz).** É o único item da visão que não aproveita
  nada do que existe: STT+TTS por minuto é a maior conta e o maior risco de
  latência. Último da fila de propósito.
- **Sub-chunk dos artigos gigantes pro embedding**, mantendo o artigo como
  unidade de citação. É o conserto de RAIZ do viés que `PESO_LEXICAL`
  compra sem reingestão (ver Decisões). Só 70 chunks passam de 4.000
  caracteres e 11 passam de 8.000 — trabalho contido.
- **Provas anteriores da banca** (gabarito oficial + incidência real).
  Ligado ao item C/E: hoje geramos itens no ESTILO Cebraspe; ingerir provas
  reais daria o peso de incidência que `simulado` amostra uniformemente
  hoje. Exigiria metadados que `questao` não tem (ano, órgão, cargo).
- **Perfil que se atualiza sozinho.** `usuario.perfil` (015) só guarda o
  que a pessoa declarou. Derivar do comportamento real ("responde melhor de
  manhã", "cai o rendimento depois de 40 min") é possível com
  `tentativa.criada_em`/`segundos` e não foi feito.
- Simulador com esquecimento (acerto cai conforme o atraso da revisão).
- `parcial` desce uma caixa — decisão a revisitar com uso real.
- Questões que cobram dois pontos ("conduta E pena") — prompt já corrigido,
  falta confirmar.
- Vínculo questão→tópico individual (hoje `edital.cobertura()` estima por
  disciplina inteira, não por tópico — ver aproximação (2) documentada
  acima). Exigiria marcar cada questão gerada com o tópico de origem.
- **Separação por cargo no parsing de edital — subiu de "detalhe" pra
  problema real com o edital da Dataprev: 13 perfis** (Desenvolvimento de
  Software, Advocacia, Contabilidade, Engenharia...), cada um com conteúdo
  específico próprio, todos somados na mesma mesa. Quem vai prestar UM
  perfil recebe um plano com o conteúdo dos outros doze junto. O Módulo I
  (Português/Inglês/RLM) é comum e está certo; o Módulo II é que deveria
  ser filtrado. Exigiria coluna `cargo` em `topico` (o parser já reconhece
  o marcador "PERFIL N:") e a pessoa escolhendo o perfil na ingestão.
- Provas anteriores da banca: gabarito oficial + peso de incidência real.
- Simulado por banca (peso de incidência real, não amostra uniforme).
  Simulado genérico (`chat.py simulado`) e desafio diário (`chat.py desafio`)
  já existem.
- Next.js consumindo `api.py` — ligado: auth, fila, diálogo turno a turno,
  simulado, desafio, stats, edital e mesas leem a API de verdade.
  `scheduler`/`socratic` continuam funções puras por baixo. O que ainda é
  vitrine em `apps/web` está listado no cabeçalho de `src/mock/prototipo.ts`,
  com a rota que falta anotada em cada bloco. **`/materiais` saiu da vitrine**
  (019/020): sobe arquivo em lote, indexa link, classifica, agrupa e edita
  rótulo contra a API de verdade, e o `MATERIAIS_EXEMPLO` do mock foi apagado —
  mock que sobrevive à tela real é o que faz alguém depurar dado inventado.
  **Em 22/09/2026, o `/tutor` também saiu da vitrine:** abertura, rota, pergunta
  de peculato e flashcard fictícios foram retirados da conversa real. Eles
  apareciam antes de qualquer fala e podiam ser confundidos com uma resposta do
  sistema sobre matéria que o aluno não escolheu.
- **Atribuição de fontes é declaração do modelo, não prova semântica.** Em
  `socratic-v72`, resposta estruturada substituiu a dependência de colchetes:
  prosa e IDs vêm na mesma chamada, e somente IDs dos chunks enviados podem
  receber `citada=true`. CP/CPP com artigo igual e páginas de apostila são
  distintos. Isso impede IDs alheios, mas não garante que o modelo escolheu
  semanticamente o trecho correto. Mensagens antigas sem atribuição estruturada
  continuam com o dado histórico; não foram reprocessadas com LLM.
- Se a rotina exportar/importar do `sincronizar.py` cansar: Postgres hospedado
  (Neon, Supabase) com `DATABASE_URL` único resolve, ao custo de exigir rede.
- **Precisão de `retrieval.py` MEDIDA** (`avaliar_retrieval.py`, agora 22
  casos, 3 normas — CP/CF/ADCT): top-6 100%, top-1 77%. Híbrida fica em
  top-6 100% mas só 8/12 top-1 — semântica encontra o artigo certo, nem
  sempre em 1º lugar; aceitável, `buscar()` devolve n=6 pro LLM escolher o
  que citar, top-6 é a métrica que importa pro produto. Rodar de novo
  sempre que mexer em `retrieval.py`, `embeddings.py` ou reingerir.
  **Depois de ingerir o livro de histórico de emendas (1340 chunks no
  total), o mesmo gabarito de 22 casos caiu pra top-6 95% (21/22)** — "matar
  alguém por motivo torpe mediante paga ou promessa" (esperado CP 121) saiu
  do top-6 inteiro, devolvendo só outros artigos do CP (209, 158, 212, 141,
  16, 138), nenhum do livro de histórico. Não é o histórico "roubando" a
  vaga por conteúdo concorrente — mais provável é o HNSW (índice
  aproximado, não exato) mudar de caminho de busca com mais vetores no
  mesmo índice, deslocando um caso já limítrofe. Não investiguei a fundo
  (fora do escopo de "ingerir e estudar" que motivou rodar isso agora);
  registrado aqui pra não achar, num dia futuro, que foi regressão de uma
  mudança em código. 95% continua bom pro produto — mas é uma medida, não
  uma suposição, e por isso entra documentada mesmo sendo só 1 caso.
  **Atualização: voltou a 100% (22/22)** depois de um `reingest.py` do CP
  feito por outro motivo (ver Armadilhas de método) — o caso limítrofe
  era mesmo sensível a reindexação do HNSW, não regressão de código.
  **Depois de ingerir CPP (848 chunks) e Lei 8.112 (245 chunks, acervo total
  2433 chunks/6 documentos), caiu pra top-6 91% (20/22)** — dois casos
  novos, e desta vez com explicação mais concreta que "HNSW mudou de
  caminho": "servidor público que se apropria de dinheiro..." (esperado CP
  312, peculato) passou a devolver só artigos da Lei 8.112 (arts. 31, 13,
  30, 120 — todos sobre servidor público); "ofender a dignidade de alguém
  com xingamento" (esperado CP 140, injúria) passou a devolver CPP 30 no
  lugar. **Aqui parece ser concorrência de conteúdo real, não só
  reindexação**: L8112 é inteiro sobre "servidor público", o mesmo
  vocabulário do enunciado de peculato — diferente do caso ADCT, onde o
  livro de histórico não tinha nada a ver semanticamente com o que sumiu.
  Não investiguei a fundo nem tentei corrigir (fora do escopo de "ingerir
  CPP e Lei 8.112" que motivou rodar isso agora); registrado pra não achar,
  num dia futuro, que foi regressão de mudança em código. 91% ainda é
  aceitável pro produto (a busca por dispositivo exato, que é a maioria do
  uso real, continua 100%) — mas é hipótese plausível, não medida
  confirmada, e por isso entra como hipótese, não como fato.
- **`documento.hash` do CP ficou desatualizado por dias sem ninguém notar
  — `corpus/cp.txt` levou 2 correções de conteúdo (normalização de linha,
  remoção da assinatura colada no Art. 361) depois da ingestão original,
  e nunca foi reingerido.** Passou desapercebido porque nada checa isso
  automaticamente. Só apareceu porque rodar `ingest.py` de novo (script de
  setup numa "máquina nova") comparou o hash do arquivo ATUAL contra o
  hash ANTIGO gravado no banco, viu que não batia, e criou um documento
  **duplicado** (434 chunks a mais, `documento_id` novo) em vez de
  detectar "já ingerido". Pior: rodar `sincronizar.py importar` logo depois
  bateu numa colisão em `(norma, artigo)` entre os dois documentos e
  **reescreveu `fonte_chunks` das 18 questões de CP originais apontando
  pro documento duplicado, errado**. Corrigido: apagar o duplicado,
  `reingest.py --doc 3 --arquivo corpus/cp.txt --norma CP` (pega a correção
  do Art. 361 que nunca tinha sido aplicada — o texto no banco AINDA tinha
  a assinatura do Getúlio Vargas colada, só ficou visível inspecionando o
  chunk na mão) e `sincronizar.py importar` de novo pra resolver
  `fonte_chunks` contra os chunks certos. Confirmado zero órfão depois.
- **`reingest.py` agora remapeia `fonte_chunks` ele mesmo (corrigido —
  `reingest-v4`).** Gap antigo: `DELETE FROM chunk` + `INSERT` de novo dá
  IDs novos pra tudo, e `fonte_chunks` guardava ID cru, não `(norma,
  artigo)` — virava referência órfã silenciosa pra quem reingeria sem
  depois rodar `sincronizar.py importar` (que resolvia de graça, mas só se
  o pacote JSON tivesse as questões). Corrigido igual `sincronizar.py`
  resolve: captura `(norma, artigo)` dos chunks ANTIGOS antes do `DELETE`,
  e depois do `INSERT` novo traduz cada id antigo referenciado por alguma
  questão pro novo id com o MESMO `(norma, artigo)`. Referência sem
  correspondência (artigo saiu do material) fica órfã DECLARADA — reportada
  no fim, não escondida. Validado contra o CP real (18 questões, todas
  remapeadas certo, zero órfão, `avaliar_retrieval.py` intacto em 100%
  top-6 depois). Achado rodando de verdade, não só em teoria: a comparação
  `fonte_chunks && ids_antigos` quebrava com `bigint[] && smallint[]` — o
  psycopg manda uma lista de int Python como `smallint[]` por padrão, e
  a coluna é `bigint[]`; precisou de `::bigint[]` explícito no SQL.
- **Bug real achado ao expandir pra multi-norma: artigos 1º-9º nunca
  batiam em NENHUMA norma.** LC 95/1998 manda escrever "Art. 1º" a "Art.
  9º" com ordinal e "Art. 10" em diante sem — mas ninguém pergunta "art.
  1º", pergunta "art. 1". `por_dispositivo()` comparava a string crua;
  corrigido tirando `[ºo]$` dos dois lados antes de comparar. Achado só
  apareceu ao testar CF (art. 1º e 5º são dos mais cobrados que existem) —
  o gabarito de 1 norma só nunca tinha um artigo baixo o bastante pra expor.
- **Segundo bug da mesma expansão: "art. 121 do CP" podia devolver o art.
  121 da CF primeiro.** Com 1 norma no banco, número de artigo já era
  identidade única; com CP+CF+ADCT convivendo, vários números colidem
  entre normas e `por_dispositivo()` ignorava qualquer norma que a pergunta
  citasse. `_norma_mencionada()` casa a sigla (dinâmico, `SELECT DISTINCT
  norma`) ou apelido comum ("constituição" → CF); some sem detecção clara
  cai de volta pro empate alfabético de antes — limitação aceita e
  documentada, não escondida.
- **CÓPIA DE NORMA SUBIDA PELO ALUNO AINDA COMPETE COM A OFICIAL — o que
  tinha conserto foi consertado (027), o que sobrou é duplicata mesmo.** O
  defeito relatado era "as cópias da CF do aluno passam na frente da CF
  oficial", e a causa não era ser cópia: era o `assunto` inventado pelo
  classificador. Ele lê só o começo do material, então a Constituição inteira
  virou "Princípios fundamentais e direitos e garantias fundamentais" — e
  esse rótulo, que entra no tsvector desde a 025, casava com QUALQUER consulta
  constitucional nos 1074 trechos. Medido antes: a cópia levava 6 de 6 em
  "princípios fundamentais do direito administrativo", devolvendo art. 88,
  art. 234 e art. 18. Depois da 027 (assunto e rótulo zerados em material de
  referência): a CF oficial volta pro 1º lugar, e "habeas corpus" devolve 4 de
  5 oficiais.
  **O que NÃO se resolve com rótulo:** o mesmo artigo existe duas vezes no
  acervo, então uma consulta boa devolve o oficial e a cópia lado a lado
  (posições 1 e 2), gastando vaga de contexto com texto repetido. Consulta
  vaga sobre doutrina que a lei não nomeia — "remédios constitucionais", que a
  CF nunca escreve — continua ruim, e é o mesmo teto de doutrina já
  documentado abaixo, não um efeito da cópia. A tela AVISA na hora de subir
  ("esta lei já está no acervo do app, dividida por artigo"); apagar a cópia é
  decisão do aluno, e o sistema não apaga material dele por conta própria.
- **Postgres `'portuguese'` não faz accent-folding — mas `unaccent` NÃO
  entrou, de propósito.** "alguem" sem acento no Art. 121 (typo isolado, 1
  ocorrência em 434 artigos) fazia a busca lexical não encontrar NADA para
  "matar alguém..." Corrigido o typo pontual. Cheguei a desenhar a migração
  (`unaccent` + configuração de busca dedicada + recriar `chunk.busca`), mas
  parei ao investigar melhor: isso resolveria SÓ a fração "acento
  presente/ausente" do problema — testei e "razão"/"razões" estemizam pra
  radicais DIFERENTES (`razã` vs `razõ`, plural irregular em `-ão`), o que
  `unaccent` não toca. Construir infraestrutura (extensão nova, índice
  funcional, reingest de 434 chunks) pra cobrir uma fração de um problema
  que `avaliar_retrieval.py` mede em 100% top-6 hoje é dívida disfarçada de
  melhoria, não melhoria. Decisão: não fazer agora. Se algum dia isso virar
  falha REAL (uma pergunta real não encontra o artigo por causa de plural),
  a resposta é adicionar esse caso ao gabarito do `avaliar_retrieval.py`
  primeiro — medir que dói antes de construir o que cura.
  **Revalidado com o corpus 3x maior (CF + ADCT, 1340 chunks):** mesmas 8
  palavras comuns checadas, zero ocorrências sem acento em ambos os
  arquivos novos. A hipótese "com mais dado o problema apareceria de novo"
  não se sustentou — decisão mantida.
- **Scheduler validado em escala com dado real de 3 normas** (800 questões
  sintéticas sobre os 1340 chunks reais, 60 dias simulados, 2 disciplinas
  simultâneas): 0 anomalias, `stats --json`/`ritmo.sugestao()`/`desafio.montar()`
  todos corretos com múltiplas disciplinas competindo pelo mesmo teto
  diário. Mesmo método do harness original (scheduler-v19), só com acervo
  maior — nada de novo quebrou ao crescer o corpus, que é exatamente o que
  essa validação existia pra confirmar.

## Fórmula, mapa mental e tabela (28/09/2026)

- A tela desenha um SUBCONJUNTO de LaTeX (`apps/web/src/components/Formula.tsx`):
  fração, potência, índice, raiz, `\boxed`, `\text` e símbolos. Ambiente
  (`\begin{...}`), matriz e alinhamento não são desenhados: o comando aparece pelo
  nome, sem barra. Sem biblioteca de propósito (ver `TextoDoTutor.tsx`).
- O modelo às vezes fecha mal a fórmula (`$$...$|`): a tela mostra o texto cru
  daquela linha. Não há correção automática disso.
- A conta é do modelo, conferida só pela leitura. Em cálculo, o tutor pode
  resolver sem trecho do material; errar uma conta é possível, e nada no código
  refaz a aritmética.

## Bateria de descoberta (28/09/2026)

- O juiz é um modelo. Ele oscila e pode errar nos dois sentidos, e o relatório
  pede leitura, não obediência.
- A leitura de contradição pega choque direto e perde choque sutil (medido).
- Gasta cota de verdade, perto de 200 chamadas na rodada padrão. Com a cota
  gratuita, uma rodada completa por dia é o realista.

## Manutenção de 29/09/2026 — visto e não corrigido

- **Recusa de assunto fora do edital** — tratada na segunda passada (ver
  `DECISOES.md`, "Segunda passada"): não era a busca nem o bloco "Nenhum", e sim a
  regra longe da pergunta. Vale conferir na próxima bateria: com o conserto medido
  em quatro chamadas, não em conversa inteira.
- **Material que terminou, e o tutor seguiu de memória.** A regra existe no
  `SISTEMA_LEITURA`; o modelo a ignorou. Com o marcador certo (`leitura.ensinados`)
  o falso "fim" some, mas o fim de verdade ainda depende do modelo obedecer.
- **Um turno de 119,6 s** (resolver de novo a questão de conjuntos). Sem telemetria
  da conta descartável, que a bateria apaga, não deu para saber se foi espera de cota.
- **CONSULTADO vazio com trecho usado.** Às vezes o modelo ensina a partir de um
  trecho e não o lista em `fontes_usadas`, e a tela não mostra fonte. Medido: fora
  da leitura, a cobertura de texto não separa usado de não usado (ver DECISOES,
  "Depois da madrugada"). Fica como omissão do modelo.
- **Símbolo trocado pelo modelo:** "n(A ∠ B)" no lugar de ∪. Não vem de
  `latex_de_volta`. O cifrão desparelhado ("$$30 + 15 = 45$") a tela passou a
  consertar.
- **Outro turno lento:** 139,8 s para resolver a questão colada de conjuntos.

## Índice de assuntos por trecho (036)

- **Precisão de 72–77% com o modelo leve**, julgada à mão numa amostra. O erro é
  entre assuntos vizinhos da mesma apostila. Um modelo mais forte em `LLM_INDICE`
  é a melhoria direta.
- **Material sem cota no dia sai pela reserva** (sumário, títulos, expressão), que
  fica entre 60% e 75% e às vezes acha só 1 assunto. Ele é refeito com o modelo pelo
  `python -m core.indice`, dentro do orçamento do dia.
- **PDF escaneado** (imagem) não tem texto, logo não tem índice.
- **O rótulo de um trecho com dois assuntos** é o primeiro na ordem da apostila.

## Questões de prova (037)

- **PDF escaneado** não tem texto, então não tem questões.
- **Questão com imagem** (gráfico, figura) entra só com o texto: a figura não vem.
- **Questão discursiva da prova** fica de fora por ora. Só entram múltipla escolha
  e certo/errado.
- **Formatos fora do padrão** (número sem ponto, alternativa sem letra) não são
  reconhecidos. Não há extração por modelo como reserva.
- **Gabarito do tutor** pode errar e fica marcado como tal na tela.

- **Conferência do edital por subitem (035) marca "sem material" demais.** Na conta
  real, 313 subitens "sem material" e 1 "coberto", inclusive onde há apostila. A
  tela e o resumo do chat já não usam esse número (usam o mapa de domínio, 038/039),
  mas a leitura "na ordem do edital" (`leitura.proximo_subitem`) e o "onde está"
  (`cobertura.localizar`) ainda dependem dele.
