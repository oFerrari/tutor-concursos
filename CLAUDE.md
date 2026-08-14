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
lógica de `core/*.py`, e um frontend Next.js (`apps/web`) consumindo a API.
Corpus atual: Código Penal (434 artigos), Constituição Federal (276 artigos) +
ADCT (151 artigos), Código de Processo Penal (848 chunks) e Lei 8.112/1990 —
regime jurídico dos servidores civis (245 chunks) — como normas separadas,
todos do Planalto — mais um livro de histórico de emendas constitucionais
como material `historico` (busca híbrida, sem citação exata por artigo).

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
db/010_mesa.sql            mesa de estudo: edital passa a ser da mesa, simulado ganha etiqueta
db/011_edital_rascunho.sql rascunho de edital: curadoria (escolher cargo) antes de virar oficial
db/schema.dbml             schema documentado (DBML) — visualização, não fonte de verdade
core/chunking.py           lei -> chunks por artigo (função pura)
core/embeddings.py         e5 local, prefixos query:/passage:, cache
core/retrieval.py          dispositivo exato -> rubrica -> híbrida (RRF)
core/llm.py                interface LLM + Gemini + Ollama, retry
core/socratic.py           avaliação e geração de questões (schemas JSON)
core/questoes.py           lookup simples do banco de questões (compartilhado, sem usuario_id)
core/auth.py               hash de senha (bcrypt), token de sessão (JWT), usuário fixo da CLI
core/mesa.py               mesa de estudo (o concurso-alvo) e o predicado de recorte por disciplina
core/rascunho.py           curadoria do edital: extrai pra rascunho, pessoa escolhe o cargo, confirma
core/scheduler_regras.py   regras de promoção — FUNÇÕES PURAS
core/scheduler.py          fila, registro, caderno de erros, meta — tudo por usuario_id
core/simulado.py           prova sob condição de exame: sem dica, corrige no final
core/desafio.py            meta do dia: reincidentes + novas + mini-simulado, tempo estimado
core/ritmo_regras.py       gatilho de intervenção proativa — FUNÇÕES PURAS
core/ritmo.py              busca desempenho/reincidência/sequência, prioriza 1 sugestão
core/edital.py             extrai data da prova e conteúdo programático de PDF de edital
edital.py                  CLI de ingestão de edital, reporta candidatos (não decide calado)
corpus/html_para_texto.py  converte HTML compilado do Planalto pra .txt (cp1252, descarta tachado/revogado)
ingest.py                  ingestão (batch)
reingest.py                reprocessa chunks preservando questões (linha E fonte_chunks)
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

**Mesa de estudo é FILTRO, não silo (migração 010).** Uma mesa é um
concurso-alvo: guarda o edital, a banca e o órgão. O que ela NÃO guarda é
progresso — `progresso`, `tentativa` e `erro_caderno` continuam escopados
por `usuario_id` e não ganharam `mesa_id`. A memória SM-2 é do ALUNO, não
do concurso: quem dominou o art. 312 estudando pra PC-PR sabe o art. 312 na
mesa da PF, e duplicar a caixa por mesa faria a mesma pessoa reestudar do
zero o que já sabe — o oposto do que repetição espaçada existe pra fazer.
O concurseiro real reaproveita Português/Constitucional entre editais o
tempo todo. O argumento decisivo contra o isolamento total foi outro,
porém: `questao` é acervo compartilhado e GLOBAL (migração 008), então sem
filtro por disciplina toda mesa mostraria o acervo inteiro de qualquer
jeito. Isolar por mesa seria esse mesmo filtro MAIS a duplicação do estado
de aprendizado; o filtro sozinho entrega o mesmo produto sem a duplicação.

As disciplinas da mesa não são coluna: saem de `topico.disciplina` do
edital MAIS RECENTE dela (mesmo "último" que `edital.mais_recente()` usa
pra meta — senão a data viria de um edital e o filtro de outro). Mesa sem
edital devolve `None` e NÃO filtra nada, que é exatamente o comportamento
anterior à 010. O predicado vive num lugar só (`core/mesa.filtro`) porque
"o que esta mesa cobre" precisa dar a mesma resposta na fila, no stats e no
simulado. Ele casa nos DOIS sentidos (`ILIKE` de cada lado) porque o nome
vem do edital por heurística de PDF ("Noções De Direito Administrativo") e
precisa bater com o do acervo, digitado na ingestão ("Direito
Administrativo").

Três números NÃO respeitam a mesa, de propósito, e é a mesma pergunta em
cada caso ("isso é do aluno ou do concurso?"): `ofensiva_dias` (hábito —
recortar quebraria a sequência de quem estudou nos dois dias em mesas
diferentes, punindo quem estudou mais), `tempo_medio_segundos` (velocidade
de resposta da pessoa) e a busca RAG de `socratic.explicar` (o aluno pode
perguntar de qualquer coisa; cortar o acervo pela mesa daria "não
encontrei" pra pergunta que o material responde). Só o resumo de
DESEMPENHO dentro do `explicar` é recortado.

Políticas de FK diferentes de propósito: `edital -> mesa` é CASCADE (o
edital É o conteúdo da mesa), `simulado -> mesa` é SET NULL (a prova já
feita é histórico de desempenho da pessoa, só etiquetado com a mesa —
apagar a mesa não deve sumir com ela). `edital.usuario_id` SAIU: o edital
pertence à mesa e a mesa ao usuário; manter as duas colunas seria
denormalização com risco de divergir.

**A mesa vem no header `X-Mesa-Id`, por requisição — não há "mesa ativa"
no servidor.** Estado de sessão no servidor faz duas abas abertas em mesas
diferentes brigarem pela mesma variável, e o aluno com dois editais abertos
ao mesmo tempo é o caso de uso normal, não a exceção. O header IDENTIFICA,
o `usuario_id` do token AUTORIZA: `mesa.obter()` filtra por usuario_id,
então pedir a mesa de outra pessoa dá 404 (não 403 — não confirma pra quem
chuta um id que ele existe e só não é dele), mesmo espírito de
`simulado.pertence_a()`. Sem header, cai na mesa padrão da conta
(`mesa.padrao`, a mais antiga, criada sob demanda como
`auth.usuario_da_cli`) — é o que mantém a CLI e qualquer cliente que ainda
não conhece mesas funcionando igual. Essa regra de fallback tem UM dono: o
servidor. `GET /mesa` devolve a mesa já resolvida pra requisição, e é o que
a sidebar e o raio-x leem — o cliente nunca recalcula "sem header, usa a
mais antiga", porque duas cópias da mesma regra divergem e o sintoma seria
a nav afirmar um nome enquanto a fila responde por outra mesa. No frontend,
o header sai de UM lugar (`chamar`/`chamarFormData` em `lib/api.ts`): se
cada tela precisasse lembrar de mandá-lo, a primeira que esquecesse leria a
mesa errada sem ninguém perceber. Na CLI o equivalente é `--mesa NOME`,
e nome desconhecido é ERRO, não fallback calado pra padrão: receber a fila
de outro concurso por causa de um typo é o tipo de falha silenciosa que
`--norma` explícito em `reingest.py` já evita noutro lugar.

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
- **`gerar.py` girava pra sempre numa seção, gastando cota real do LLM a
  cada volta, sem NUNCA acionar `MAX_FALHAS`.** Achado gerando questões pra
  CF pela primeira vez (CP não tem artigo baixo o bastante pra expor isso —
  mesma classe de bug já documentada em `retrieval.por_dispositivo()`, LC
  95/1998: Art. 1º-9º levam ordinal, Art. 10+ não). Dois defeitos
  compostos: (1) `salvar()` comparava o artigo cru contra o que o modelo
  devolve — pra "5º", "6º", "8º" o modelo às vezes respondia sem o ordinal,
  então TODA questão da seção era descartada por "proveniência não
  confere"; (2) `falhas` (o contador que decide quando desistir) resetava
  pra 0 sempre que a CHAMADA ao LLM funcionava, mesmo com zero questão
  salva — como a chamada nunca falhava (só o resultado vinha inútil),
  `falhas` nunca chegava em `MAX_FALHAS`, e o loop tentava a MESMA seção
  pra sempre. Rodou ~45 minutos sem salvar nada antes de eu notar que não
  era rede lenta. Corrigido: `_norm_artigo()` tira `[ºo]$` dos dois lados
  antes de comparar (mesma normalização de `retrieval.py`), e `falhas` só
  zera quando `salvar()` de fato salva algo — "a chamada funcionou" e "a
  chamada rendeu progresso" são coisas diferentes, e só a segunda deveria
  resetar o contador de desistência.

**Extração de edital: a quebra de linha É o dado, e `_normalizar()` a
destruía antes de qualquer regex rodar.** Achado com um edital REAL
(Dataprev 001/2026, banca FGV) subido pela tela: o painel mostrou 362
tópicos em 4 disciplinas — `Plataforma Básica` (257), `Iof` (100), `Ecf`
(3), `Gestão De Servidores` (2). Nenhuma das quatro é disciplina daquele
concurso. Três defeitos compostos, cada um invisível sozinho:

1. **Cabeçalho sem numeração não era procurado.** `RE_DISCIPLINA` exigia
   "N. DISCIPLINA:" (padrão PC-PR, o único edital que existia quando o
   módulo nasceu). A FGV escreve "LÍNGUA PORTUGUESA:" sem número — ou
   seja, NENHUMA disciplina real era encontrada.
2. **O que entrou no lugar veio de acidente.** Sem âncora de início de
   linha (o `_normalizar()` já tinha colapsado toda quebra em espaço),
   "…Framework version **1.1.** PLATAFORMA BÁSICA:" fez o `1.` de um
   número de VERSÃO virar número de disciplina, e "3. ECF:" / "12. IOF:"
   — itens no meio de um parágrafo de Contabilidade Tributária — viraram
   disciplinas. Começar a linha é o único sinal que separa cabeçalho de
   item no meio de frase, e era exatamente o sinal jogado fora.
3. **Sem recorte, as REGRAS do edital viraram matéria.** Inscrição, prazos
   e recursos são centenas de itens numerados ("4.5.1", "10.13.6"); é daí
   que saíram os 257 tópicos de "Plataforma Básica".

Corrigido: `limpar_paginacao()` -> `recortar_conteudo_programatico()` ->
cabeçalhos NO TEXTO CRU -> normalizar só o corpo de cada bloco -> contar
folhas. Medido contra `tests/fixtures/edital_fgv_dataprev.txt` (trecho real
do PDF, com as quebras de linha como o pypdf entrega): 14 disciplinas
reais, 98 tópicos, zero fantasma.

**O passo que quase passou batido foi a mobília de página.** O PDF abre
cada página com "DATAPREV | CONCURSO PÚBLICO 2026" e o número da página
numa linha só dela. Disciplina que calha de começar no topo de uma página
fica precedida por um número solto — e a regra nova de "linha que começa
depois de número pendurado é continuação de frase" a descartava. Efeito
medido: **3 disciplinas somem e os tópicos delas migram pra disciplina
anterior**, com o total continuando plausível. É o pior formato de erro,
porque nenhuma contagem denuncia. Só apareceu porque o fixture foi
ATUALIZADO pra incluir a mobília depois que a primeira versão do conserto
já estava "passando" — fixture limpo demais mente tanto quanto métrica
errada (mesma lição de `diagnostico.py` auditar estrutura e não conteúdo).

**Curadoria antes de virar oficial: subir o PDF cria um RASCUNHO, não um
edital (migração 011).** Um edital tem vários cargos, e cada cargo tem
conteúdo específico próprio. O da Dataprev tem TREZE perfis — ingerir tudo
junto deu "1015 tópicos em 52 disciplinas", com Advocacia, Contabilidade e
Engenharia dentro do plano de quem vai prestar TI. **Somar cargo é pior
que não ler**: vira revisão espaçada de matéria que nunca vai cair na
prova daquela pessoa. Agora `POST /editais/rascunho` extrai pra uma tabela
temporária, a tela mostra os cargos encontrados, a pessoa escolhe um e
ajusta a lista, e só o `confirmar` cria `edital` + `topico`. O erro do
extrator morre na tela, antes de virar agendamento.

O agrupamento por cargo é POSICIONAL, e os dois editais reais concordam:
o conteúdo programático abre com o que vale pra todo mundo ("CONHECIMENTOS
COMUNS PARA TODOS OS CARGOS", "MODULO I ... PARA TODOS OS CARGOS/PERFIS") e
só depois vêm os blocos de cargo. Disciplina antes do primeiro marcador é
comum; depois dele, é do cargo aberto. O marcador é o mesmo `RE_CARGO` pras
duas bancas: "PERFIL 3: X" (FGV) e "CARGO: X" (AOCP).

**O extrator continua sendo o parser; o LLM é FALLBACK.** O parser acerta
os dois layouts que existem em fixture, custa zero cota, roda em
milissegundos e é determinístico — dá pra travar em teste, coisa que
resposta de modelo não dá. `estrutura_com_fallback()` só chama o Gemini
(com `responseSchema`, saída estruturada) quando o parser não achou
disciplina NENHUMA — o sinal honesto de "layout que eu não conheço". O
gatilho é "zero disciplina", não "zero cargo": concurso de cargo único é
legítimo e chamar o modelo nele seria queimar cota pra confirmar o que o
parser já acertou. Falha do LLM não derruba a ingestão: devolve o vazio do
parser e a curadoria vira preenchimento manual.

**Rascunho em Postgres, não em Redis.** É um registro escrito uma vez e
lido duas; não paga uma dependência de infra nova, um processo a mais pra
subir e um modo de falha a mais ("o Redis caiu no meio da curadoria").
`expira_em` faz o trabalho do TTL e sobrevive a restart — que é justamente
quando o TTL em memória perderia o PDF que o usuário já subiu. A estrutura
vai em JSONB porque é dado em TRÂNSITO: normalizar em tabelas seria modelar
o que ainda vai ser editado e descartado.

**Segundo edital real, segunda rodada de zeros: o AOCP (PC-BA) devolveu 0
tópicos em 0 disciplinas.** Duas causas independentes, nenhuma delas
visível no edital anterior:

1. **O ponto depois do número.** A FGV escreve "1 Compreensão"; o AOCP
   escreve "1. Compreensão". `RE_SUBITEM` exigia `\s+` logo após o número,
   batia no ponto e falhava em TODO item do documento. Um caractere.
2. **O edital cita o próprio anexo antes de chegar nele.** "Integram o
   presente Edital: Anexo I - Conteúdos Programáticos", "conforme conteúdo
   programático constante do Anexo I", "salvo se listadas nos conteúdos
   programáticos..." — o recorte pegava a PRIMEIRA menção e cortava um
   pedaço das regras de inscrição; o anexo de verdade nunca era lido.
   Regra nova: a ÚLTIMA menção. Referência cruzada vem antes, o anexo é o
   último. (E o marcador precisou aceitar plural: a FGV escreve "CONTEÚDO
   PROGRAMÁTICO", o AOCP escreve "CONTEÚDOS PROGRAMÁTICOS".)

Aceitar "N." como item abriu um falso positivo novo, resolvido junto:
"...Brasil de 1988. A Constituição do Estado" tem a FORMA exata de um item
(número, ponto, espaço, maiúscula). O que separa os dois é **abrir
oração** — item vem no começo do bloco ou depois de pontuação; "1988" vem
depois de "de ". Sem essa âncora, o ano viraria tópico.

Resultado medido: PC-BA passou de 0 para 86 tópicos em 13 disciplinas
reais, e o edital da FGV continuou correto (14 disciplinas). Conferido
ponta a ponta contra o acervo: a mesa da PC-BA casa 18 questões de Direito
Penal. Lição de método: **cada edital novo é um caso de teste novo** —
dois bastaram pra achar cinco defeitos distintos, e nenhum deles aparecia
no outro. Fixture antes de regex.

**O produto NÃO é só para Direito.** O filtro da mesa é por NOME de
disciplina e funciona igual pra TI, bancária, fiscal ou policial — o que
limita é só o que já foi ingerido no acervo. Uma mesa de TI num acervo de
Direito bate zero questão, e isso é verdade, não defeito; mas a tela agora
DIZ ("o acervo ainda não tem questões dessas disciplinas") em vez de
mostrar "0/0" calado, que parece bug.

**Nome do edital: o arquivo TEMPORÁRIO do servidor vazou pro banco.**
`POST /edital` grava o upload num `NamedTemporaryFile` e passava esse
caminho pra `edital.ingerir()`, cujo fallback de título é o nome do
arquivo — então o edital virou "tmpcmrpqinr" no banco e na tela. O
fallback certo na borda HTTP é `UploadFile.filename` (o nome que o usuário
enviou); o `stem` do caminho só faz sentido na CLI, onde o caminho é um
arquivo de verdade. Classe de erro a procurar em qualquer rota que grave
upload: caminho interno do servidor não é dado do usuário.

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
- `sincronizar.py` também NÃO exporta `mesa`/`edital`/`topico` (migração
  010): a outra máquina precisa rodar `python edital.py ... --mesa "..."` de
  novo pra recriar o recorte. O progresso continua viajando inteiro, porque
  é do usuário e não da mesa — que é justamente o que a decisão da 010
  torna verdade. Exportar mesa exigiria resolver identidade de mesa entre
  bancos (o id é sequencial e muda), o mesmo problema que `(norma, artigo)`
  resolve pros chunks; o nome da mesa serviria de chave natural, mas não
  vale construir isso antes de existir uma segunda máquina com mesas.
- Uma mesa não tem disciplinas próprias: elas saem do edital. Mesa criada e
  ainda sem PDF mostra o acervo inteiro (declarado, não silencioso — a CLI
  imprime "sem edital — acervo inteiro" no cabeçalho da sessão).
- A troca de mesa é por aba do navegador, não por dispositivo: a mesa ativa
  vive em `localStorage` (`tutor_mesa`), do mesmo jeito que o token. Abrir
  duas abas em mesas diferentes funciona (é o motivo de o header ser por
  requisição), mas fechar o navegador e abrir noutra máquina começa da mesa
  padrão.

## Aberto

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
- Disciplina da mesa definida à mão, sem edital (hoje só o PDF cria o
  recorte). Faria sentido pra quem estuda pra um concurso ainda sem edital
  publicado — que é metade do tempo de preparação de verdade.
- Provas anteriores da banca: gabarito oficial + peso de incidência real.
- Simulado por banca (peso de incidência real, não amostra uniforme).
  Simulado genérico (`chat.py simulado`) e desafio diário (`chat.py desafio`)
  já existem.
- Next.js consumindo `api.py` — ligado: auth, fila, diálogo turno a turno,
  simulado, desafio, stats, edital e mesas leem a API de verdade.
  `scheduler`/`socratic` continuam funções puras por baixo. O que ainda é
  vitrine em `apps/web` está listado no cabeçalho de `src/mock/prototipo.ts`,
  com a rota que falta anotada em cada bloco (materiais e onboarding).
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
- Testar qualquer coisa que grave em `tentativa`/`progresso`/`simulado`/`edital`/`mesa`
  contra um usuário DESCARTÁVEL (`auth.usuario_da_cli("teste-x@local")`),
  nunca contra a conta real (`CLI_USUARIO_EMAIL`). Apagar com
  `DELETE FROM usuario WHERE email = '...'` — o `ON DELETE CASCADE` da
  migração 009 limpa tentativa/progresso/erro_caderno/simulado e a cadeia
  mesa→edital→topico (010) de uma vez, sem lógica de limpeza escrita na mão
  (ver Armadilhas de método).
- `pytest` cobre isso: `tests/test_mesa_api.py` tem um teste
  (`test_caderno_de_erros_atravessa_mesas`) que existe pra QUEBRAR se
  alguém escopar `progresso`/`erro_caderno` por mesa um dia. A decisão da
  010 não está só escrita — está executável.

## Comandos

```bash
docker compose up -d          # da raiz do monorepo
cd apps/api && source .venv/bin/activate
python ingest.py corpus/cp.txt --disciplina "Direito Penal" --tipo lei --norma CP
python ingest.py corpus/cf.txt --disciplina "Direito Constitucional" --tipo lei --norma CF
python ingest.py corpus/adct.txt --disciplina "Direito Constitucional" --tipo lei --norma ADCT --titulo ADCT
python ingest.py corpus/cpp.txt --disciplina "Direito Processual Penal" --tipo lei --norma CPP --titulo "Código de Processo Penal"
python ingest.py corpus/lei8112.txt --disciplina "Direito Administrativo" --tipo lei --norma L8112 --titulo "Lei 8.112/1990"
python ingest.py corpus/livro-emendas.pdf --disciplina "Direito Constitucional" --tipo historico
python corpus/html_para_texto.py corpus/Arquivo.html corpus/norma.txt --cortar-em "MARCADOR"  # converte HTML do Planalto pra .txt antes de ingerir
python avaliar_retrieval.py         # depois de qualquer ingestão nova ou mudança em retrieval.py
python edital.py corpus/edital.pdf --orgao "PC-PR" --banca FGV   # data da prova + conteúdo programático
python edital.py corpus/edital.pdf --mesa "PC-PR Investigador"   # cria a mesa se não existir
python gerar.py --cobertura 3
python gerar.py 3 --secao "FUNCIONARIO PUBLICO" --por-lote 3 --max 12
python chat.py estudar
python chat.py estudar --mesa "PF Agente"   # recorta pelas disciplinas do edital daquela mesa
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

# mesas (migração 010): o header escolhe o recorte; sem header, mesa padrão
curl -s -X POST localhost:8000/mesas -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"nome":"PF Agente","banca":"Cebraspe"}'
curl -s localhost:8000/mesas -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/fila  -H "Authorization: Bearer $TOKEN" -H "X-Mesa-Id: 3"
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