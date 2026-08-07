# AGENTS.md — Tutor de concursos

Contexto persistente do projeto. Leia antes de propor mudanças.
Portável: serve para Antigravity, Claude Code, Cursor, Codex.
(Para Claude Code: `ln -s AGENTS.md CLAUDE.md`.)

**Monorepo.** Este arquivo fica na raiz (é onde as ferramentas de IA
procuram por padrão), mas TODO caminho e comando abaixo — `core/`, `db/`,
`chat.py`, `corpus/`, `.env` — é relativo a `apps/api/`, que é onde mora o
backend inteiro. `cd apps/api` antes de rodar qualquer coisa deste
documento, exceto `docker compose` (lê `docker-compose.yml` da raiz).
Ver `README.md` (raiz) para a estrutura do monorepo (`apps/`, `packages/`).

---

## O que é

Tutor socrático para concursos públicos brasileiros. RAG sobre lei seca +
banco de questões + repetição espaçada. Multiusuário desde a migração 008
(ver Decisões); CLI própria (`chat.py`) e API HTTP (`api.py`) sobre a MESMA
lógica de `core/*.py` — Next.js consumindo `api.py` é o próximo passo, ainda
não escrito.
Corpus atual: Código Penal (434 artigos), Constituição Federal (276 artigos) +
ADCT (151 artigos) como normas separadas, todos do Planalto — mais um livro
de histórico de emendas constitucionais como material `historico` (busca
híbrida, sem citação exata por artigo).

**Não contém e nunca deve conter** dados de empresa. O autor trabalha numa
cooperativa; este projeto é separado disso por decisão explícita.

## Pilha

```
Postgres 17 + pgvector   docker compose, porta 5433
embeddings               intfloat/multilingual-e5-base, 768 dim, LOCAL (CPU)
LLM                      Gemini Flash via REST, adaptador trocável
auth                     JWT (PyJWT) + bcrypt, stateless — sem tabela de sessão
interface                CLI (rich, chat.py) + API HTTP (FastAPI, api.py) sobre o mesmo core/.
                         Frontend (Next.js) ainda não escrito — é o próximo passo.
```

## Mapa

```
db/001_schema.sql          documento, chunk, questao, tentativa, erro_caderno
db/002_rubrica_secao.sql   colunas rubrica e secao
db/003_embedding_cache.sql cache de vetores por hash de conteúdo
db/004_simulado.sql        tabela simulado, tentativa.simulado_id
db/005_desempenho_json.sql v_desempenho_disciplina em float8 (JSON-pronta) + cobertura_pct
db/006_tipo_historico.sql  documento.tipo aceita 'historico' (material com múltiplas versões do artigo)
db/007_edital.sql          tabelas edital e topico
db/008_usuario.sql         usuario, progresso (caixa/prox_revisao saem de questao), usuario_id em tudo pessoal
db/009_cascade_usuario.sql ON DELETE CASCADE consistente em toda FK pra usuario
db/schema.dbml             schema documentado (DBML) — visualização, não fonte de verdade
core/chunking.py           lei -> chunks por artigo (função pura)
core/embeddings.py         e5 local, prefixos query:/passage:, cache
core/retrieval.py          dispositivo exato -> rubrica -> híbrida (RRF)
core/llm.py                interface LLM + Gemini + Ollama, retry
core/socratic.py           avaliação e geração de questões (schemas JSON)
core/questoes.py           lookup simples do banco de questões (compartilhado, sem usuario_id)
core/auth.py               hash de senha (bcrypt), token de sessão (JWT), usuário fixo da CLI
core/scheduler_regras.py   regras de promoção — FUNÇÕES PURAS
core/scheduler.py          fila, registro, caderno de erros, meta — tudo por usuario_id
core/simulado.py           prova sob condição de exame: sem dica, corrige no final
core/desafio.py            meta do dia: reincidentes + novas + mini-simulado, tempo estimado
core/ritmo_regras.py       gatilho de intervenção proativa — FUNÇÕES PURAS
core/ritmo.py              busca desempenho/reincidência/sequência, prioriza 1 sugestão
core/edital.py             extrai data da prova e conteúdo programático de PDF de edital
edital.py                  CLI de ingestão de edital, reporta candidatos (não decide calado)
ingest.py                  ingestão (batch)
reingest.py                reprocessa chunks preservando questões
gerar.py                   geração com cobertura por seção
diagnostico.py             auditoria do chunking, sem banco
avaliar_retrieval.py       precision@k da busca híbrida contra gabarito de artigos
simular.py                 simulação de meses de estudo, sem banco
chat.py                    sessão de estudo (CLI, usuário fixo por email)
api.py                     API HTTP (FastAPI) — mesma lógica de core/, autenticada por JWT
sincronizar.py             exporta/importa questões e progresso de UM usuário entre máquinas
atualizar.sh               instala arquivos baixados do chat
```

## Decisões e o porquê

**Chunk = artigo, não N caracteres.** Artigo é unidade semântica completa.
Cortar por tamanho destrói o que o estudante procura.

**Rubrica ("Concussão") vai DENTRO do campo `texto`.** Embedding e tsvector
são calculados sobre `texto`; o que não está lá não é recuperável. Também
existe em coluna própria para busca direta.

**Busca híbrida com RRF, não soma de scores.** Distância de cosseno e
`ts_rank_cd` vivem em escalas diferentes; somar é o erro clássico. RRF funde
por posição no ranking.

**Citação exata de dispositivo não traz complemento semântico.** Precisão
vence recall: contexto extra só dá ao modelo material para citar fonte errada.

**Retenção do gabarito é imposta em código, não no prompt.** O modelo recebe
o gabarito para julgar e é instruído a não revelar — mas instrução vaza. Quem
decide revelar é `chat.py`, após 3 respostas erradas.

**`socratic.explicar()` tem DUAS fontes de contexto — material E desempenho
real do aluno — porque um professor que não sabe conversar sobre o próprio
progresso do aluno não é professor.** Antes disso, "como estou indo em
português?" não tinha onde bater: a busca (RAG) só sabe sobre o acervo de
lei, nunca sobre quem pergunta. `_resumo_desempenho()` busca
`scheduler.desempenho()` + `scheduler.caderno_erros()` e monta um resumo
pronto — o modelo só LÊ esse resumo, nunca soma nada sozinho, mesmo
princípio de "retenção imposta em código" acima. O modelo escolhe qual
fonte usar (ou as duas) por instrução de prompt, não por classificação
separada — mais simples que rotear a pergunta antes de perguntar, e testado
que funciona: sem tentativa nenhuma, admite que não tem dado; com
tentativa real, responde com o número exato do banco, nunca inventado.

**Fila = revisões primeiro, novas com o orçamento restante.** Ordenar só por
caixa causa INANIÇÃO: com centenas de questões inéditas, a promovida volta em
3 dias e fica atrás de todas. Simulado em 90 dias: 8% de domínio contra 51%.

**Penalidade de promoção = errar, não receber dica.** Dica vem automática ao
errar, então as duas coisas andam juntas; penalizar ambas conta a mesma falha
duas vezes. Dica pedida por iniciativa própria conta.

**Simulado não dialoga nem dá dica — corrige tudo no final.** É a diferença
entre treino e prova; andaime durante a prova mede a ajuda, não o aluno.
Reaproveita `scheduler.registrar`: como nunca há dica, `dicas_usadas` é
sempre 0, então acerto sempre promove — mesma regra de sempre, mesmo sinal
limpo. Seleciona por `ORDER BY random()` sobre TODO o acervo, não pela fila
do dia: fila prioriza o que venceu, simulado testa o conjunto inteiro.

**`v_desempenho_disciplina` devolve `float8`, não `numeric`.** `ROUND(numeric,
N)` vira `Decimal` no psycopg, e `json.dumps(Decimal)` estoura `TypeError`.
Castear na view agora é o que deixa `scheduler.desempenho()` pronto pra virar
endpoint depois sem reescrever nada — `chat.py stats --json` já imprime
exatamente o que a API vai servir.

**Cache de embeddings por hash de conteúdo.** Vetor é função pura de (texto,
modelo). Corrigir chunking passou a custar segundos em vez de minutos.

**Lógica em funções puras, efeito colateral na borda.** `chunking`,
`scheduler_regras` não tocam banco nem relógio — por isso `diagnostico.py` e
`simular.py` existem e rodam em milissegundos sobre o MESMO código de produção.

**Sincronização entre máquinas por arquivo no git, não por Postgres compartilhado.**
`sincronizar.py` exporta questões e tentativas para `dados/progresso.json`
traduzindo `chunk.id` para `(norma, artigo)` — o id é sequencial e MUDA entre
bancos; copiar a coluna crua faria a questão citar o artigo errado, calado.
A importação resolve `(norma, artigo)` de volta contra os chunks locais.
Resolve alternância entre duas máquinas de um usuário só; não resolve edição
simultânea (para isso, Postgres hospedado com `DATABASE_URL` compartilhado).

**Desafio diário é composição, não módulo novo.** `core/desafio.py` só decide
QUAIS questões entram em cada um dos três blocos (reincidentes do caderno de
erros, novas, mini-simulado); quem resolve de verdade é `chat._estudar_lista`
(extraído de `estudar()`) e `chat.simulado` (agora aceita lista pronta em vez
de sempre sortear). Estimativa de tempo vem de `avg(tentativa.segundos)` real,
não de um número chutado — sem histórico, cai num default documentado.
`_estudar_lista` devolve se o usuário pediu "sair", porque sem esse sinal o
desafio emendava o próximo bloco mesmo depois da pessoa dizer que ia parar.

**Edital vira dado real, não data digitada na mão — mas é MELHOR ESFORÇO
reportado, não contrato.** `core/edital.py` extrai data da prova e conteúdo
programático de um PDF de edital com heurística de texto (regex + pontuação
por proximidade de palavra-chave), porque layout de edital varia por banca e
não existe parser universal. `candidatos_data_prova()` devolve TODOS os
candidatos com pontuação, não só "a resposta" — mesmo espírito de
`diagnostico.py`: reportar pro operador conferir, nunca decidir calado.
`chat.py meta` sem argumento usa a data do edital mais recente; passar data
manual sempre vence (saída de emergência se a extração errou), e essa
correção também alimenta `probabilidade_fechamento()` — sem isso, corrigir
a data na mão deixaria a probabilidade calculando com a data errada do banco.

Duas aproximações DECLARADAS em `core/edital.py`, não escondidas: (1) sem
separação por cargo — concurso com mais de um cargo repete disciplina com
conteúdo próprio, os tópicos se somam num grupo só; (2) cobertura por
tópico é estimada por DISCIPLINA inteira (não há vínculo questão→tópico
individual no schema), assume dificuldade uniforme dentro da disciplina.

**"Probabilidade de fechamento" é extrapolação linear de ritmo, não modelo
estatístico.** `ritmo_atual = tópicos cobertos / dias estudando; ritmo
necessário = tópicos pendentes / dias restantes; probabilidade = min(100,
100 * atual/necessário)`. Não modela variância nem esquecimento — mesma
limitação já documentada em `simular.py`. Nomear isso de "probabilidade"
sem dizer a fórmula seria o mesmo erro de "48% dominadas" virar "a
ferramenta só acerta 48%" — por isso a fórmula fica no docstring da função,
não só na cabeça de quem escreveu.

**Intervenção proativa é regra, não o LLM decidindo quando falar.** O LLM já
resolve a conversa livre (`socratic.explicar`); decidir QUANDO interromper é
limiar sobre número (5 acertos seguidos, <50% de acerto, 3+ reincidências) —
pedir pro modelo julgar isso a cada questão custaria cota e mudaria de
sessão pra sessão sem ninguém pedir. `ritmo_regras.py` é puro, no mesmo
molde de `scheduler_regras.py`; `ritmo.py` busca os dados e prioriza.
Mostra no máximo UMA sugestão por sessão (reincidência > disciplina fraca >
sequência de acertos) — três avisos empilhados deixam de ser proativos e
viram ruído que o aluno aprende a ignorar. Disciplina fraca exige um mínimo
de tentativas antes de disparar, mesma lição do simulador: percentual sobre
amostra pequena é ruído, não tendência.

**Multiusuário: o acervo é COMPARTILHADO, o progresso é PESSOAL (migração
008).** `documento`/`chunk`/`questao` continuam sem `usuario_id` — é o
mesmo Código Penal pra todo mundo, e gerar questão custa cota de LLM; negar
reaproveitamento entre usuários pagaria a mesma pergunta N vezes. O que é
estado de quem estuda (`caixa`, `prox_revisao`) SAI de `questao` e vai pra
`progresso` (usuario_id, questao_id) — porque caixa é estado de QUEM
responde, não da pergunta, e dois usuários estudando o mesmo banco
compartilhado precisam de caixas independentes pra MESMA questão. Ausência
de linha em `progresso` é o sinal de "esta pessoa nunca tentou esta
questão" (antes esse sinal vinha de `tentativa` não ter linha; migrou pra
`progresso`, que é o dado que efetivamente muda). `tentativa`, `erro_caderno`
(PK virou composta), `simulado` e `edital` ganharam `usuario_id`.

**`v_desempenho_disciplina`: o denominador da cobertura é o acervo INTEIRO
da disciplina, não só o que o usuário já tocou.** Primeira versão da view
pós-migração partia de `progresso` (só linhas existentes) — um usuário que
respondeu 2 de 18 questões e dominou as 2 aparecia com 100% de cobertura.
Corrigido partindo de `questao` (CROSS JOIN com os usuários que têm
qualquer progresso) e trazendo `progresso`/`tentativa` como LEFT JOIN
escopado — `questoes` conta o universo compartilhado, `dominadas` conta só
o que ESTE usuário dominou. Achado revisando a própria migração antes de
aplicar, não em produção — mas do tipo de erro que só aparece com mais de
um usuário, que o dataset mono-usuário anterior nunca teria exposto.

**Autenticação é JWT stateless, não sessão em tabela.** `api.py` e
`chat.py` não compartilham processo nem memória; um token assinado
(`core/auth.py`, bcrypt pro hash de senha, PyJWT pra sessão) evita precisar
de mais uma tabela só pra sessão. Trade-off aceito: sem lista de revogação,
um token vazado vale até expirar (uma semana) — aceitável pra uso
pessoal/pequeno grupo, revisar se isso crescer.

**A CLI não loga — resolve um usuário fixo pelo email do `.env`.**
`chat.py`/`sincronizar.py`/`edital.py` (CLI) chamam
`auth.usuario_da_cli(CLI_USUARIO_EMAIL)`, que cria a conta (sem senha
usável) se não existir. Login de verdade com senha só existe pelo caminho
da API — é o único lugar que precisa disso, porque é o único lugar onde
"alguém que não é você" poderia estar do outro lado.

**`PATCH /me`/`DELETE /me` exigem a senha atual, mesmo já autenticado por
token.** Token roubado (mas não a senha) não deveria bastar pra sequestrar
a conta trocando e-mail/senha, nem pra apagá-la. Efeito colateral aceito: a
conta criada por `usuario_da_cli` (sem senha usável) não consegue trocar
senha por essa rota — ela nunca teria como chegar autenticada ali sem
senha alguma; ganhar login via API pra essa conta seria um fluxo
diferente (tipo reset), fora de escopo por ora.

**`ON DELETE CASCADE` consistente em toda FK pra `usuario` (migração 009).**
A 008 só deu CASCADE em `progresso`; as outras (`tentativa`, `erro_caderno`,
`simulado`, `edital`) ficaram RESTRICT por padrão do Postgres — inconsistência
descoberta ao testar com usuário descartável: apagar a conta de teste
travava num FK esquecido. Testar multiusuário sem isso exigiria apagar cada
tabela na mão, na ordem certa — a mesma classe de erro já documentada em
"Armadilhas de método" (lógica de limpeza ad-hoc é onde bug mora); um
`DELETE FROM usuario` limpo é o que permite testar com conta descartável
com confiança.

**`corpus/` (lei do Planalto) vai para o git; `acervo/` (material pago) não.**
Texto de lei não tem direito autoral no Brasil (art. 8º, IV da Lei 9.610).
Levar o texto resolve o bloqueio de rede corporativa de uma vez: reingerir
numa máquina nova não depende de baixar de novo.

**CF e ADCT são normas SEPARADAS, não uma "CF" só.** O Ato das Disposições
Constitucionais Transitórias reinicia sua própria numeração ("Art. 1º do
ADCT" ≠ "Art. 1º da CF" — são dispositivos diferentes, citados diferente na
prática). Ingerir os dois com `norma=CF` faria `chunk_artigo_idx` colidir
exatamente como o livro de histórico de emendas colidia — o mesmo defeito,
só que dentro de um documento por sinal legítimo. `corpus/cf.txt` (corpo
principal) e `corpus/adct.txt` são arquivos e `documento` distintos.

**`documento.tipo = 'historico'` existe pra material com múltiplas versões
do mesmo artigo (emendas, "Redação Anterior") sem forçar `chunk_lei()`
nele.** Cai em `chunk_generico()` — janela por parágrafo, sem tentar
extrair (norma, artigo). Perde citação exata por dispositivo, mas fica
disponível pra busca híbrida, e principalmente: não arrisca `art. X`
devolver a versão REVOGADA em vez da vigente. `ingest.py`/`reingest.py`
recusam automaticamente gravar como `--tipo lei` se a taxa de colisão de
artigo (`chunking.taxa_colisao_artigo`) passar de 5% — antes disso só um
`diagnostico.py` manual pegava esse tipo de problema, e só se alguém
lembrasse de rodar.

## Invariantes (violação = bug)

- Todo `Art.` do arquivo vira um chunk. `diagnostico.py` verifica.
- Toda linha aceita como rubrica é atribuída a algum chunk.
- `questao.fonte_chunks` aponta para o artigo real de onde a questão saiu.
  Se o modelo cita artigo fora do lote, a questão é DESCARTADA — cobertura
  que mente é pior que cobertura inexistente.
- Erro de transporte não escapa de `core/llm.py` como exceção httpx.

## Armadilhas do corpus (Planalto)

- Quebra de linha no meio da frase; `normalizar_lei()` remonta.
- Rubrica com nota colada: `Concussão (Redação dada pela Lei nº ...)`.
- Nota isolada ENTRE rubrica e artigo (feminicídio, art. 121-A).
- Artigo revogado tem como corpo só a nota — preservar, é matéria de prova.
- Rubrica pode começar com "Pena" ("Penas restritivas de direitos").
- Assinatura e aviso de rodapé ("Este texto não substitui o publicado no
  DOU...", "GETÚLIO VARGAS") vêm colados depois do último artigo no HTML
  compilado. Sem cortar pelo marcador do aviso ANTES de gerar o `.txt`, esse
  texto vira corpo do último artigo — não é rubrica nem termina sem
  pontuação, então `_cortar_cauda` não descarta.
- Acento faltando em palavra comum ("alguem" em vez de "alguém", Art. 121)
  não aparece em nenhuma métrica estrutural — só quebra busca lexical em
  runtime, silenciosamente. `grep -c` da palavra certa vs. errada no corpus
  é o jeito rápido de checar se é isolado ou sistêmico antes de decidir como
  corrigir (ver "Postgres 'portuguese' não faz accent-folding" em Aberto).
- **CF compilada:** o aviso "Este texto não substitui..." e a lista de
  assinatura dos constituintes vêm no MEIO do arquivo (fim do corpo
  principal, ANTES do ADCT), não só no fim como no CP — cortar só pelo fim
  do arquivo perderia o ADCT inteiro. E a palavra quebra entre "não" e
  "substitui" com `\n`, não espaço — busca ingênua por essa frase falha se
  não tolerar quebra de linha no meio.
- **ADCT:** referência a "art. X da Lei nº ..." ou "art. X da Constituição
  de 1967" no MEIO de um parágrafo, quebrada em nova linha pela extração,
  casa com `RE_ARTIGO` como se fosse um artigo novo — gera chunk fantasma
  (fragmento de outro artigo, com número de artigo errado). Baixo volume
  (3 de 151, 2%) e a `taxa_colisao_artigo` já sinaliza; não vale regex mais
  esperto pra 2% enquanto não aparecer caso real de citação errada.

## Armadilhas de método (custaram tempo)

- **Métrica que a própria regra define não arbitra entre regras.** "Questões
  dominadas" sobe se a regra afrouxa, sem ninguém saber mais.
- **Simulação com aleatoriedade precisa de várias sementes.** Diferença de 8
  pontos virou 36 ao repetir 15 vezes.
- **O simulador não modela esquecimento.** Logo, não pode julgar "revisão
  antes de novidade" quando a capacidade cobre a demanda.
- **Medir ausência não é medir defeito.** "112 artigos sem rubrica" media o
  Código Penal, não o código-fonte. A métrica certa é perda de informação.
- **`diagnostico.py` audita estrutura (contagem, rubrica), não conteúdo do
  corpo.** O corpus com assinatura/rodapé colada no Art. 361 passava 434/434
  limpo — o defeito estava DENTRO do texto do último chunk, onde a métrica
  não olha. Só apareceu inspecionando `chunk_lei(...)[-1]` na mão.
- **`DELETE` antes de validar que o `INSERT` vai funcionar é perigoso sem
  transação.** `reingest.py` fazia `DELETE FROM chunk` e só DEPOIS calculava
  embedding lote a lote — um erro no meio (aconteceu de verdade: API do
  `pgvector.Vector` mudou entre versões, `.tolist()` deixou de existir)
  deixava o documento com ZERO chunks, sem nada pra reverter, porque
  `autocommit=True` não dá rollback. Pior: a norma que o comando precisa pra
  rodar de novo é inferida DOS CHUNKS que acabaram de sumir — travava
  exatamente no momento em que mais se precisava dele. Corrigido calculando
  tudo antes de tocar no banco, e adicionando `--norma` explícito como saída
  de emergência. `core/embeddings.py` também não fixava `device="cpu"`
  (decisão já documentada em "Pilha"), então uma GPU incompatível com o
  build do torch instalado quebra em runtime em vez de nunca ser tocada.
- **`VAR=valor cmd1 | cmd2` só passa a env var pro PRIMEIRO comando do
  pipe, não pro segundo.** Testando isolamento multiusuário, um
  `CLI_USUARIO_EMAIL=teste printf ... | python chat.py simulado` rodou o
  `chat.py` com o email DEFAULT do `.env` — ou seja, contra o usuário real —
  porque o prefixo só se aplicava ao `printf`. As duas tentativas foram
  registradas na conta real antes de eu notar (progresso divergindo do
  esperado). Corrigido colocando a env var no lado do pipe que efetivamente
  a usa: `printf ... | CLI_USUARIO_EMAIL=teste python chat.py ...`. A
  correção nos dados usou o mesmo método já validado (recomputar `caixa`
  a partir do histórico real de tentativas, não da data de "hoje") —
  restaurado e reverificado byte a byte contra backup antes de continuar.
  Lição: ao testar isolamento entre usuários, um usuário "de teste" com
  `usuario_da_cli()` + `ON DELETE CASCADE` (migração 009) que se apaga com
  um `DELETE` só é mais seguro que confiar em escopo de env var em pipe.

## Limitações conhecidas

- Multiusuário desde a migração 008 — acervo compartilhado, progresso pessoal
  (ver Decisões). `sincronizar.py` continua pensado pra alternância de UM
  usuário entre duas máquinas, não pra distribuir contas.
- JWT sem revogação: token vazado vale até expirar (uma semana, `core/auth.py`).
  Aceitável pra uso pessoal/pequeno grupo; revisar se isso crescer.
- PDF escaneado exige OCR antes (`ocrmypdf`).
- Camada gratuita do Gemini: cota diária baixa e prompts podem ser usados
  para treinamento. Não sirva conteúdo sensível por esse caminho.
- Artigo revogado pode herdar a nota do artigo seguinte (cosmético).
- Trocar modelo de embeddings exige `ALTER TABLE` e reindexação.
- `sincronizar.py` resolve alternância entre duas máquinas de um usuário só,
  não edição simultânea. Estudar nas duas sem exportar perde a mais recente.
- `sincronizar.py` não exporta `simulado`/`tentativa.simulado_id`: histórico
  de provas não viaja entre máquinas (o progresso em si — caixa,
  prox_revisao — viaja, porque isso vem da tentativa comum).

## Aberto

- Simulador com esquecimento (acerto cai conforme o atraso da revisão).
- `parcial` desce uma caixa — decisão a revisitar com uso real.
- Questões que cobram dois pontos ("conduta E pena") — prompt já corrigido,
  falta confirmar.
- Ingerir CPP, Lei 8.112 (mesmo pipeline, trocar `--norma`; CF+ADCT já feitos).
- Vínculo questão→tópico individual (hoje `edital.cobertura()` estima por
  disciplina inteira, não por tópico — ver aproximação (2) documentada
  acima). Exigiria marcar cada questão gerada com o tópico de origem.
- Separação por cargo no parsing de edital (hoje disciplinas de nomes
  iguais entre cargos se somam — ver aproximação (1) documentada acima).
- Provas anteriores da banca: gabarito oficial + peso de incidência real.
- Simulado por banca (peso de incidência real, não amostra uniforme).
  Simulado genérico (`chat.py simulado`) e desafio diário (`chat.py desafio`)
  já existem.
- Next.js consumindo `api.py` — API já existe e testada (auth, fila,
  diálogo turno a turno, simulado, desafio, stats, edital), frontend ainda
  não escrito. `scheduler`/`socratic` continuam funções puras por baixo.
- Se a rotina exportar/importar do `sincronizar.py` cansar: Postgres hospedado
  (Neon, Supabase) com `DATABASE_URL` único resolve, ao custo de exigir rede.
- **Precisão de `retrieval.py` MEDIDA** (`avaliar_retrieval.py`, agora 22
  casos, 3 normas — CP/CF/ADCT): top-6 100%, top-1 77%. Híbrida fica em
  top-6 100% mas só 8/12 top-1 — semântica encontra o artigo certo, nem
  sempre em 1º lugar; aceitável, `buscar()` devolve n=6 pro LLM escolher o
  que citar, top-6 é a métrica que importa pro produto. Rodar de novo
  sempre que mexer em `retrieval.py`, `embeddings.py` ou reingerir.
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

## Convenções

- Todo módulo tem `VERSAO = "nome-vN"` no topo. Confira antes de depurar:
  o bug mais caro do projeto foi rodar código antigo achando que era novo.
- Antes de mexer em chunking: `python diagnostico.py corpus/cp.txt --norma CP`
  (segundos, sem banco). Só depois `reingest.py`.
- Antes de mudar regra de agendamento: `python simular.py`.
- Antes de mexer em `retrieval.py`/`embeddings.py` ou reingerir: `python avaliar_retrieval.py`
  (precisa de banco com o CP ingerido; roda em segundos, sem custo de LLM).
- Nunca `DELETE FROM documento` para reprocessar: use `reingest.py`.
- `reingest.py --doc N` infere a norma dos chunks atuais; se algo já apagou
  os chunks (ou você não tem certeza), passe `--norma CP` explícito.
- `.env` e `acervo/` fora do git; `corpus/` e `dados/progresso.json` vão para o git.
  SQL só migrações numeradas.
- **`docker-entrypoint-initdb.d` só roda em volume novo.** Migração numerada
  nova (`db/00N_*.sql`) não se aplica sozinha a um container já existente —
  ela só entra de fato num `docker compose down -v` (perde todos os dados)
  ou aplicando na mão: `docker exec -i tutor-db psql -U tutor -d tutor -f
  /docker-entrypoint-initdb.d/00N_nome.sql`. Commitar a migração não é
  aplicar a migração; um `git pull` na outra máquina tem o mesmo problema se
  o volume lá já existir. Custou o módulo de Simulados/Estatísticas inteiro
  rodando contra a view/tabela antiga sem avisar (`chat.py simulado` batendo
  em tabela inexistente, `stats --json` devolvendo `Decimal` que quebra
  `json.dumps`) até alguém tentar de verdade.
- Ao sair de uma máquina: `python sincronizar.py exportar` antes do commit/push,
  sempre — senão a próxima exportação (de qualquer lado) sobrescreve progresso.
- Testar qualquer coisa que grave em `tentativa`/`progresso`/`simulado`/`edital`
  contra um usuário DESCARTÁVEL (`auth.usuario_da_cli("teste-x@local")`),
  nunca contra a conta real (`CLI_USUARIO_EMAIL`). Apagar com
  `DELETE FROM usuario WHERE email = '...'` — o `ON DELETE CASCADE` da
  migração 009 limpa tentativa/progresso/erro_caderno/simulado/edital(+topico)
  de uma vez, sem lógica de limpeza escrita na mão (ver Armadilhas de método).

## Comandos

```bash
docker compose up -d          # da raiz do monorepo
cd apps/api && source .venv/bin/activate
python ingest.py corpus/cp.txt --disciplina "Direito Penal" --tipo lei --norma CP
python ingest.py corpus/cf.txt --disciplina "Direito Constitucional" --tipo lei --norma CF
python ingest.py corpus/adct.txt --disciplina "Direito Constitucional" --tipo lei --norma ADCT --titulo ADCT
python ingest.py corpus/livro-emendas.pdf --disciplina "Direito Constitucional" --tipo historico
python avaliar_retrieval.py         # depois de qualquer ingestão nova ou mudança em retrieval.py
python edital.py corpus/edital.pdf --orgao "PC-PR" --banca FGV   # data da prova + conteúdo programático
python gerar.py --cobertura 3
python gerar.py 3 --secao "FUNCIONARIO PUBLICO" --por-lote 3 --max 12
python chat.py estudar
python chat.py desafio             # meta do dia: pontos fracos + novas + mini-simulado
python chat.py simulado 20 60      # 20 questões, meta de 60 min
python chat.py simulados
python chat.py erros | stats | stats --json
python chat.py meta                 # usa a data do edital ingerido
python chat.py meta 2026-11-15      # data manual, sempre vence a do edital
python chat.py perguntar "art. 312"

# ao sair de uma máquina
python sincronizar.py exportar && git add -A && git commit -m "progresso" && git push

# ao chegar na outra (ingira o material antes, se ainda não ingeriu)
git pull && python sincronizar.py importar

# API (pra Next.js consumir depois; hoje só testada via TestClient/curl)
uvicorn api:app --reload --port 8000
curl -s -X POST localhost:8000/auth/registrar -H 'content-type: application/json' \
     -d '{"email":"voce@exemplo.com","senha":"pelomenos8chars"}'
curl -s localhost:8000/fila -H "Authorization: Bearer $TOKEN"
```


## Escopo do projeto

Este repositório contém um projeto de estudo e desenvolvimento de arquitetura
para sistemas baseados em RAG, recuperação híbrida, repetição espaçada e
tutoria socrática.

O corpus atual é composto exclusivamente por material público (Código Penal),
utilizado como domínio de demonstração e validação da arquitetura.

O projeto não contém dados, documentos, regras de negócio ou informações
confidenciais de qualquer organização.

No futuro, a arquitetura poderá ser reutilizada como base para outros projetos,
inclusive profissionais, desde que esses sejam desenvolvidos em repositórios
próprios, com escopo, autorização e políticas adequadas. Este repositório
permanece independente e utiliza apenas dados públicos.