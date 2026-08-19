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

Dois formatos de questão: discursiva curta (avaliada por LLM) e item
CERTO/ERRADO no estilo Cebraspe (corrigido em código), este com ou sem
"Texto associado" compartilhado entre vários itens. Quando o banco não tem
questão da matéria, o sistema GERA a partir do acervo e grava com
proveniência. O chat do tutor tem memória de conversa e sabe para que
concurso a pessoa estuda.

**Não contém e nunca deve conter** dados de empresa. O autor trabalha numa
cooperativa; este projeto é separado disso por decisão explícita.

## Pilha

```
Postgres 17 + pgvector   docker compose, porta 5433
embeddings               intfloat/multilingual-e5-base, 768 dim, LOCAL (CPU)
LLM                      Gemini Flash via REST, adaptador trocável
auth                     JWT (PyJWT) + bcrypt, stateless — sem tabela de sessão
interface                CLI (rich, chat.py) + API HTTP (FastAPI, api.py) sobre o mesmo core/,
                         e frontend Next.js (apps/web) consumindo a API.
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
db/012_questao_tipo.sql    questao.tipo + gabarito_ce: item CERTO/ERRADO (Cebraspe), CHECK casada
db/013_contexto.sql        "Texto associado": texto-base compartilhado por vários itens
db/014_conversa.sql        conversa + mensagem: o chat do tutor passa a ter memória
db/015_perfil.sql          usuario.perfil (JSONB): horas/nível/turno declarados no onboarding
db/018_edital_cargo.sql    edital.cargo: o plano diz PARA QUEM ele é (17 cargos no da PF)
db/019_material_do_aluno.sql documento.usuario_id + status/erro/chunks_total: biblioteca privada
db/020_material_classificado.sql disciplina virou NULLABLE + assunto + classificado_por
db/021_biblioteca_por_mesa.sql documento.mesa_id + mesa.biblioteca_compartilhada
db/022_conceito_faltante.sql tentativa.conceito_faltante: o que o aluno CONFUNDE
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
core/geracao.py            gera questão do ACERVO sob demanda e grava com proveniência
core/conversa.py           conversa persistida do tutor + janela de histórico pro prompt
core/assunto.py            o assunto em foco da conversa — a consulta que vai à BUSCA (PURO)
core/scheduler_regras.py   regras de promoção — FUNÇÕES PURAS
core/scheduler.py          fila, registro, caderno de erros, meta — tudo por usuario_id
core/simulado.py           prova sob condição de exame: sem dica, corrige no final
core/desafio.py            meta do dia: reincidentes + novas + mini-simulado, tempo estimado
core/ritmo_regras.py       gatilho de intervenção proativa — FUNÇÕES PURAS
core/ritmo.py              busca desempenho/reincidência/sequência, prioriza 1 sugestão
core/edital.py             extrai data da prova e conteúdo programático de PDF de edital
core/material.py           biblioteca do ALUNO: sobe/baixa, classifica, indexa material privado
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
semear_demo.py             semeia conta descartável com 3 mesas e 15 dias, pra olhar a TELA
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

**Questão sob demanda: a IA cria do acervo quando o banco não tem
(`core/geracao.py`).** Até aqui a fila só servia o que já estava em
`questao`, e essa tabela só crescia por `gerar.py`, rodado à mão. O efeito
era GERAL, não de uma matéria: qualquer mesa cujo edital cobrisse
disciplina ainda não gerada abria vazia — TI, bancária, fiscal, e também
Direito Administrativo, que tinha 245 chunks da Lei 8.112 no acervo e ZERO
questão. O material estava lá; o modelo já sabia gerar questão a partir de
trecho de lei desde o começo. Faltava encanamento, não capacidade.

Sem tema, sorteia trecho ainda DESCOBERTO dentro do recorte da mesa ("minha
fila está vazia"); com tema, usa a MESMA `retrieval.buscar` do tutor, pra a
questão sair do trecho que fundamentou a conversa e não de outro. Nunca de
`tipo='historico'` — sem artigo não há proveniência, e pior: pode conter
redação REVOGADA.

A invariante NÃO foi afrouxada: questão cujo artigo não está no lote é
descartada, como sempre. `gerar.py` passou a CHAMAR `geracao.salvar` em vez
de manter a cópia dela — duas versões da regra que grava proveniência é
como elas divergem. E `documento_id`/`disciplina` saem do CHUNK casado, não
de parâmetro: lote montado por busca atravessa normas, e herdar a
disciplina de fora rotularia a questão errado — justamente o rótulo que a
mesa usa pra recortar a fila.

A questão gerada é GRAVADA no acervo compartilhado, não fica na tela: só
assim entra em `progresso`/SM-2 e volta pra revisão. `POST` e nunca
automático dentro de `/fila` — gasta cota e escreve no acervo; um GET que
gera faria cada refresh queimar cota. **409, não 500**, quando o acervo não
cobre a matéria: "não temos material" e "a IA falhou" pedem ações opostas
do aluno.

**Item CERTO/ERRADO é tipo de questão, não formatação (migração 012).** A
maior banca do país cobra assertiva binária, e o produto respondia "meu
acervo não traz itens nesse formato" — verdade sobre a tabela, mentira
sobre o sistema. `tipo` + `gabarito_ce BOOLEAN`, com **CHECK casada**:
"item C/E sem booleano" e "discursiva COM booleano" não podem existir, e
deixar isso pro código significaria que o primeiro caminho de escrita que
esquecesse a regra gravaria lixo calado (são vários: `gerar.py`,
`sob_demanda`, `sincronizar`). BOOLEAN e não 'C'/'E' em texto porque campo
livre aceita "Certo", "V", "verdadeiro" e espalha normalização de string
por quem consome. `gabarito` segue NOT NULL e passa a guardar a
JUSTIFICATIVA — sem ela o aluno acerta ou erra e não aprende nada.

**Múltipla escolha ficou de fora de propósito:** exige tabela de
alternativas, modelagem inteira e não uma coluna. Aceitar o valor no CHECK
sem ter onde guardá-las criaria questão gravável e não renderizável — falha
na tela do aluno em vez de falhar na hora de gravar.

Correção do item C/E é **em código, sem LLM** (`socratic.avaliar_questao` é
o dispatcher): a resposta é um booleano, e mandar isso pro modelo custa
cota, demora e introduz erro num julgamento que `==` faz sem errar. Num
simulado de 40 itens é a diferença entre 40 chamadas e nenhuma. O
dispatcher existe porque QUATRO caminhos corrigiam chamando `avaliar()`
direto (rota, simulado, desafio, CLI), e cada um que esquecesse o tipo
mandaria "C" pra ser comparado contra uma justificativa em prosa.

**Não há escada socrática no item binário**, e isso é decisão: qualquer
dica sobre uma assertiva de 50% É a resposta, e "tente de novo" vira cara
ou coroa com o gabarito garantido na segunda. Também não existe `parcial` —
metade de um booleano não é nada, e `parcial` DESCE uma caixa em
`scheduler_regras`, punindo por um estado que o formato não pode ocupar.

Na geração, `_validar_ce` checa `isinstance(gabarito_ce, bool)` e não
veracidade: `if not gabarito_ce` descartaria TODO item ERRADO (False é
falsy) — metade do lote, e justamente a metade que dá valor ao formato.

**"Texto associado": o texto-base é registro compartilhado, não cópia
(migração 013).** A prova real raramente traz assertiva avulsa — um
texto-base é seguido de N itens que o julgam de ângulos diferentes.
Repetir esse texto dentro de cada `enunciado` quebraria três coisas: os
itens deixam de ser irmãos (a tela não sabe dizer "item 2 de 3"), o mesmo
texto vira N cópias que divergem quando uma for corrigida, e o SM-2
reapresenta a situação inteira pra revisar uma assertiva de duas linhas.
Coluna resolveria só a terceira — **o compartilhamento É a estrutura**, e
relação se modela com chave.

CASCADE deliberado: item cujo texto-base sumiu é ILEGÍVEL ("com base no
argumento acima" sem o argumento) e apareceria na fila de alguém. Órfão
silencioso é pior que apagar junto. `contexto_id` é NULLABLE porque item
avulso continua legítimo.

A série sai em UMA chamada, não uma por item: os itens precisam ser
coerentes entre si (mesma situação, mesmos nomes, ângulos diferentes), e
isso só acontece se o modelo os escrever de uma vez, vendo o texto que ele
mesmo criou. Item por item sobre contexto pronto produz repetição — o
defeito que o formato não pode ter.

**A banca decide o formato.** `geracao.tipo_da_banca` lê `mesa.banca`:
Cebraspe/CESPE gera item C/E. Treinar discursiva pra prova Cebraspe é
treinar o exercício errado — o formato tem um vício próprio (marcar Certo
sem ler a troca de prazo ou de "poderá/deverá") que só se treina
respondendo nele.

**Conversa persistida: o tutor lembra do turno anterior (migração 014).** O
problema era maior que "esquece a semana passada": não havia memória
NENHUMA. `POST /perguntar` recebia só a pergunta atual, o histórico vivia
no estado do React e sumia num F5, e o modelo nunca o via. Em uso isso
aparecia assim: o aluno respondia "qualquer um" e o tutor devolvia "qualquer
um de quê?" — ele não tinha a pergunta anterior. O padrão já existia
(`socratic.avaliar()` recebe turnos por parâmetro pelo mesmo motivo);
faltava aplicá-lo ao chat livre e ter onde guardar.

Duas tabelas e não JSONB: mensagem é a unidade que se pagina, conta e
busca; array em JSONB obriga a reescrever o documento inteiro a cada turno.
`mesa_id` é ETIQUETA com SET NULL — a conversa é do ALUNO (mesma decisão de
`progresso` na 010) e apagar a mesa não deve sumir com o que foi discutido.

**Janela de 8 turnos, e o motivo não é economia:** o prompt já carrega 6
chunks de lei (alguns com milhares de caracteres) e o resumo de desempenho.
Uma conversa de 40 turnos empurraria o MATERIAL — a parte que ancora a
resposta — pra fora da janela do modelo, e o tutor passaria a responder de
memória própria. Melhor esquecer o turno 1 do que esquecer o art. 37. As
fontes de turnos passados NÃO voltam pro prompt: são contexto de exibição
(reabrir a conversa ancorada); reinjetá-las faria o modelo citar
dispositivo recuperado pra outra pergunta.

A pergunta do aluno é gravada ANTES da chamada ao modelo: se o LLM cair,
ela fica registrada. Reabrir e não achar o que você mesmo escreveu é a pior
forma de perder confiança no histórico.

**O prompt do tutor sabe PARA QUE CONCURSO o aluno estuda.** Antes,
perguntado "o que tem no meu edital", ele jogava a palavra na busca e
devolvia a definição jurídica de "edital" na Lei 8.112 e no CPP — resposta
correta sobre a lei e completamente fora do que foi perguntado, porque o
prompt nunca dizia que existe um edital. Agora entram concurso, órgão,
banca e disciplinas. Só os NOMES das disciplinas, nunca os tópicos: o
edital da Dataprev tem 1015 e isso queimaria cota pra repetir o que a tela
já mostra melhor.

Junto veio o conserto de um **vazamento de rótulo**: uma resposta real
terminou com "...75.3% [DESEMPENHO REAL DO ALUNO]" — o modelo citou o NOME
DA SEÇÃO do prompt como se fosse fonte, porque cabeçalho em maiúscula
somado a "cite a referência entre colchetes" ficou ambíguo. Rótulo vazando
como citação é pior que citação errada: expõe o andaime e destrói a
confiança nas citações verdadeiras da mesma frase.

E o prompt NÃO manda o modelo escrever questão no chat. Uma versão
intermediária dizia "ofereça gerar, nunca diga que não tem como", e ele
passou a redigir múltipla escolha dentro da conversa — sem proveniência,
sem entrar no SM-2, num formato que o banco não tem. Agora ele encaminha
pro botão e explica por quê.

**Perfil de estudo em JSONB, e NÃO "vetor de perfil" (migração 015).** O
tutor sabia o desempenho e a conversa; não sabia COMO a pessoa estuda
(horas/dia, nível, turno), então tratava um iniciante de 1h igual a um
veterano de 6h. Essas três respostas já eram pedidas no onboarding desde o
protótipo e sumiam ao trocar de rota.

JSONB aqui pelo argumento INVERSO ao da 014: preferência não se pagina, não
se conta, não se busca — é lida inteira, toda vez, por um consumidor só (o
prompt), e o conjunto vai crescer por tentativa e erro. Quando um campo
precisar ser CONSULTADO, vira coluna.

Vetor seria o instrumento errado: "prefere exemplos de trânsito" é um fato
curto e literal, não um ponto num espaço semântico. Convidaria a buscar por
similaridade onde ler o texto resolve e, pior, abriria caminho pro modelo
INFERIR o próprio contexto — o oposto do princípio de que ele LÊ um resumo
calculado em código.

**Lista fechada de campos e valores, validada na escrita E NA LEITURA.** A
segunda é redundante hoje, de propósito: o destino desse texto é o prompt,
e o dia em que alguém gravar perfil por outro caminho (import, migração,
script) não pode ser o dia em que "nivel: ignore as regras acima" chega ao
modelo. Valor fora da lista é ignorado em silêncio — cliente desatualizado
e payload malicioso pedem a mesma resposta.

**A busca pesa o braço lexical mais que o semântico
(`retrieval.PESO_LEXICAL = 1.5`).** Não é gosto: é correção de um viés
MEDIDO contra chunks grandes. O art. 37 da CF tem 13.059 caracteres (média
do acervo: 1.245) e cobre concurso, licitação, teto e improbidade no mesmo
artigo; o embedding é a média disso, então "administração direta e
indireta" — que é o começo do caput — o encontrava em 83º no semântico
contra 3º no lexical. Entrando em uma lista só, o RRF o punha atrás de
chunks medianos presentes nas duas, e ele NÃO chegava ao contexto que o
tutor lê. Ampliar o pool de candidatos de 30 pra 200 não resolvia
(testado): o problema é a posição, não o corte.

1.5 é o MENOR valor que corrige (2, 3 e 5 não melhoram mais nada) — número
escolhido por maximizar a nota num gabarito de 32 casos seria ajuste ao
gabarito, não à busca. **O conserto de raiz continua sendo sub-chunk do
artigo gigante pro embedding**, mantendo o artigo como unidade de citação;
o peso compra o resultado sem reingestão, e o gabarito agora tem os casos
que denunciariam uma regressão.

`PESO_HISTORICO = 0.5` não mudou a nota e entrou assim mesmo: o livro de
emendas ocupava 4 das 6 vagas de "princípios da administração pública", uma
delas uma página de LEGENDA DE SÍMBOLOS. Vaga gasta com índice é contexto
que o modelo não tem pra responder — melhora que a métrica não vê.

**Orçamento de tempo no desafio: o "só tenho 20 minutos hoje".**
`desafio.orcamento_blocos` é FUNÇÃO PURA e o que ela codifica é uma decisão
de produto — a ORDEM do corte. Reincidentes ficam (é o que a pessoa erra de
novo e de novo, o que mais rende por minuto); novas vêm depois (material
inédito é o mais caro cognitivamente, sai antes numa sessão curta);
**mini-simulado cai primeiro e CAI INTEIRO** — simulado de 2 questões não é
simulado, e medida sobre amostra pequena é ruído, a mesma lição que já vale
em `ritmo_regras`. Cortar até virar enfeite é pior que cortar de vez.

O número de questões sai da velocidade REAL da pessoa
(`avg(tentativa.segundos)`), então 20 minutos de quem responde em 30s rende
mais que de quem responde em 120s. Prometer "10 questões em 20 minutos" pra
todo mundo seria número fixo onde existe medida.

**A intervenção proativa passou a INTERROMPER, não só sugerir.** As três
regras originais descrevem TENDÊNCIA (disciplina fraca há semanas, tema que
reincide) e cabem num aviso passivo. `sugestao_erros_seguidos` descreve o
estado de AGORA: três erros consecutivos é alguém batendo a cabeça neste
minuto, e continuar só produz mais erro e mais caixa zerada. O custo de não
interromper é assimétrico — um aviso ignorado custa uma linha de tela; dez
minutos errando em sequência custam a sessão.

Ela devolve DICT e não string, ao contrário das outras: interromper sem
oferecer pra onde ir é só atrapalhar, então vem com uma PERGUNTA PRONTA pro
tutor. Pedir pro aluno formular "o que estou errando?" no momento em que
ele acabou de errar três vezes é exigir energia justamente de quem já está
sem ela. O tema entra no texto só quando os três erros são do MESMO ponto:
"errou 3 seguidas" é observação, "errou 3 seguidas de peculato" é
diagnóstico. `parcial` conta como erro — tratá-lo como acerto faria a
interrupção nunca disparar pra quem erra "quase acertando", que é
exatamente quem mais precisa parar. E ela NUNCA bloqueia: "continuar mesmo
assim" fica ao lado, porque tutor que impede o aluno de estudar é pior que
tutor calado.

**A conversa registra o que o aluno FEZ, não só o que disse (migração
016).** A 014 deu memória do que foi DITO; faltava o que acontece ENTRE os
turnos. O tutor explicava peculato, gerava três itens, o aluno errava os
três — e a mensagem seguinte continuava explicando como se nada tivesse
acontecido. É a mesma cegueira da 014 um nível acima, e sobre a informação
mais valiosa da conversa: dizer "não entendi" é relato, **errar a questão é
evidência**.

`mensagem.autor` ganhou um terceiro valor, `'evento'`. Não dá pra
reaproveitar os dois que existiam: gravar "respondeu e errou" como fala do
ALUNO põe na boca dele uma frase que ele não escreveu; como fala do TUTOR,
inventa uma resposta que o modelo nunca gerou. As duas mentem justamente no
histórico que volta pro prompt e que o aluno relê na tela. No prompt o
evento entra rotulado `[fato da sessão]` — "(o aluno errou)" dito por
"Você" faria o modelo tratar aquilo como coisa que ele mesmo afirmou.

Não bastava o `_resumo_desempenho` que já ia no prompt: ele é AGREGADO
("73% em Constitucional, 111 tentativas") e um erro isolado some numa média
de 111 — mas é exatamente o erro isolado, recém-cometido, sobre o assunto
em discussão, que deveria mudar a próxima frase do tutor. Medido: depois de
errar uma questão de concussão gerada na conversa, a resposta seguinte
abriu com "Você errou a questão sobre concussão agora pouco, então vamos
direto ao ponto crítico".

**A questão gerada no chat é respondida NO CHAT.** Antes o botão fazia
`router.push("/fila")`: você pedia questão no meio de um raciocínio e era
jogado pra outra tela, e o que acertava lá não voltava pra conversa. As
questões continuam entrando na fila normal (são gravadas no acervo, como
sempre); o que mudou é ONDE se responde.

**Relevância manda mais que novidade na geração por tema.** Bug real,
achado na primeira conversa de verdade: pedir questão sobre PECULATO
devolveu uma sobre DESACATO, porque peculato já tinha questão e desacato
não. A ordenação era `(ja_tem, ranking)` — todo inédito à frente de todo
cobrado, que é "cobrar o artigo errado só por ser inédito", exatamente o
que o comentário do próprio código dizia evitar. Agora o 1º colocado da
busca entra SEMPRE (quando a busca é precisa — "art. 312", "concussão" —
ele É o assunto) e a novidade só ordena as vagas restantes, dentro de um
pool ainda relevante.

**Mesa sem edital tem TRÊS estados, não dois (migração 017).** Relatado em
uso: mesa recém-criada aparecia no lobby com "4 / 54 questões · 7%" e a
legenda "sem edital — mostra o acervo inteiro". O número é verdadeiro e
está no lugar errado — é o progresso da PESSOA no acervo todo, exibido num
cartão que promete o progresso DAQUELA mesa. Gaveta nova que já nasce
cheia.

**A correção NÃO foi "sem edital, escopo vazio".** Foi a primeira proposta
e ela quebra mais do que conserta: `mesa.filtro` com lista vazia não casa
nada, então fila, desafio, simulado, stats e meta ficam TODOS vazios — a
mesa vira inútil até alguém subir um PDF, e quem ainda não tem edital
publicado (metade do tempo de preparação de verdade) simplesmente não
conseguiria estudar. Trocar "número confuso" por "produto morto" não é
conserto. O problema também não era o filtro: era o CARTÃO afirmando ser
progresso de mesa um número que é do aluno, e isso se resolve na tela.

O que faltava era o estado "esta mesa TEM alvo, e não veio de PDF". Agora
`mesa.disciplinas()` tem três respostas, e `origem_alvo` diz qual é:

  · `edital`  — veio do PDF. TEM PRECEDÊNCIA sobre o manual: é o documento
                oficial e é dele que `scheduler.meta` tira a data da prova.
                Deixar o manual sobrepor faria o recorte vir de um lugar e
                o prazo de outro — o defeito que a 010 evitou ao fazer
                disciplina e data saírem do MESMO "último edital".
  · `manual`  — o aluno escolheu as matérias na mão, do que EXISTE no
                acervo. Nome livre viraria filtro que nunca casa nada, e o
                sintoma seria fila vazia sem explicação: o aluno acharia
                que o app quebrou, não que escolheu matéria inexistente.
  · `nenhum`  — ninguém declarou nada. Segue sem filtrar (a mesa é
                utilizável no dia 1), mas o cartão esconde barra e
                percentual e diz o que FAZER: anexar o edital, ou escolher
                as matérias no lápis.

`TEXT[]` e não tabela: lista curta, lida inteira, escrita inteira, nunca
consultada por item — o oposto de `topico`, que se conta e se agrupa.

**Onde o aprendizado é MEDIDO, e onde não é.** Vale ter isto explícito
porque é fácil supor errado: fila, `/questao/[id]`, desafio, simulado e a
questão embutida no /tutor passam TODOS por `scheduler.registrar` — logo
alimentam `tentativa`, `progresso` (SM-2), `erro_caderno`, desempenho,
ofensiva, tempo médio e a intervenção proativa. Medido com conta
descartável: um simulado de 4 questões subiu tentativa 0->4, progresso
0->4, caderno 0->4, ofensiva 0->1, tempo médio 90s (default) -> 40s (real),
e disparou a interrupção por erros seguidos.

O **chat livre NÃO registra nada disso** — e não deveria: conversar não é
responder questão, e contar conversa como tentativa inflaria acerto e
ofensiva sem ninguém ter sido avaliado. Ele é CONSUMIDOR dos insights
(`_resumo_desempenho` entra no prompt), não produtor. A única coisa que ele
grava é a própria conversa (014).

Mas a QUESTÃO respondida dentro da conversa registra normalmente, como
qualquer outra — e desde a 016 registra DUAS vezes: em `tentativa`/
`progresso` (o aprendizado, igual à fila) e como evento na linha do tempo
da conversa (o contexto, pro tutor considerar no próximo turno). São coisas
diferentes e nenhuma substitui a outra.

**Biblioteca do aluno: o acervo passa a ter DONO opcional (migração 019).**
Até aqui `documento` era só material público (lei do Planalto), e o aluno não
tinha como alimentar o tutor com o PDF do curso que ele pagou. A alternativa
teria sido uma tabela nova (`material`, `material_chunk`) — e ela duplicaria
chunking, embedding, cache e busca híbrida pra chegar no mesmo lugar. Uma
COLUNA `usuario_id` nullable em `documento` reaproveita tudo: `NULL` é o acervo
público de sempre, preenchido é material de UM aluno.

O preço dessa escolha é que o predicado de dono tem que estar em TODA busca, e
não no código que chama: `retrieval.DONO = "(d.usuario_id IS NULL OR
d.usuario_id = %(uid)s)"` entra DENTRO das CTEs de `por_dispositivo`,
`por_rubrica` e `hibrida`. Filtrar depois de rankear seria pior que não filtrar:
o material de outro aluno gastaria vaga no top-6 e sairia da lista, então a
pergunta perderia contexto sem ninguém ver por quê. `usuario_id=None` é o
default e devolve só público — a CLI e qualquer chamador que ainda não conhece
biblioteca continuam vendo o que sempre viram, e o vazamento exige um
`usuario_id` explícito, não um esquecimento. Medido com dois alunos e um
mnemônico inventado: o dono ACHOU, o outro não, a CLI não.

`geracao.py` NÃO recebe `usuario_id`, e isso é decisão, não esquecimento:
`questao` é acervo COMPARTILHADO (008), então questão gerada de material pago
de um aluno seria distribuída pros outros. O tutor pode LER o material privado
pra explicar; o gerador não pode COPIÁ-LO pra dentro de uma tabela pública.

**Indexar é `BackgroundTasks`, com o progresso no BANCO.** O embedding roda
local na CPU (decisão de "Pilha") e um PDF de curso leva minutos — não cabe num
request. `status`/`chunks_total`/`chunks` em `documento` e não em memória porque
o aluno dá F5, fecha a aba e volta depois; progresso em memória perderia
exatamente o PDF que ele já subiu. `indexar()` é IDEMPOTENTE (`DELETE FROM
chunk WHERE documento_id` antes de inserir) — provado com 3 execuções seguidas,
sem duplicar trecho: sem isso o botão "tentar de novo" dobraria o material.

**Disciplina é OPCIONAL e quem descobre é o classificador (migração 020).**
Obrigar a rotular é obrigar a LER antes de subir, e o caso que mais importa é
justamente o material que a pessoa não conhece ("joguei lá, não sei se
agrega"). `assunto` entrou junto porque disciplina sozinha não distingue a aula
3 da aula 11 de um mesmo curso, e `classificado_por` existe pra tela pedir
conferência SÓ no palpite — o que o aluno digitou não precisa de aviso, ele
sabe o que escreveu. O classificador NUNCA sobrescreve rótulo do aluno, e roda
FORA do `try` da indexação: uma falha de rótulo marcando como `falha` um
material inteiramente indexado seria mentir sobre o que aconteceu.

**Lote: os campos valem pros N arquivos, e um arquivo ruim não derruba os
outros.** "Opcional" resolvia metade do problema — subir 14 aulas ainda era 14
idas ao seletor de arquivo. O envio é SEQUENCIAL de propósito: o servidor
indexa em background no próprio processo, então disparar 14 de uma vez não
termina mais rápido, só some com o progresso ("3 de 14") e concorre por CPU com
o embedding que já está rodando. E quem escolheu 14 não deveria reenviar 13 que
já entraram por causa do que falhou — os que falharam são NOMEADOS no fim,
porque "3 falharam" sem dizer quais é um erro que não dá pra agir.

**O seletor de rótulo é `<datalist>`, não `<select>`, e a fonte tem um botão.**
A lista é DICA, não domínio fechado: `<select>` seria o componente errado
(recusaria matéria nova) e um combobox caseiro reimplementaria teclado, foco e
"aceita valor de fora" pra chegar onde o navegador já está. As sugestões saem de
`GET /materiais/sugestoes`, e só da biblioteca de QUEM pergunta — oferecer a
disciplina que outro aluno cadastrou vazaria o que ele estuda, num campo que
parece inofensivo. O botão troca a fonte da DISCIPLINA entre as matérias da
mesa (edital, 011, ou alvo manual, 017) e o que o aluno já usou aqui; fica
desabilitado DIZENDO POR QUÊ quando a mesa não declarou matérias, em vez de
ligar e não sugerir nada. Vem LIGADO quando há alvo, porque usar a grafia do
edital faz a biblioteca agrupar com o mesmo nome que o plano de estudo usa.
ASSUNTO só tem sugestão com o botão desligado: o alvo da mesa não tem assunto
pra oferecer — tem disciplina e tópico, e tópico é outra coisa (o edital da
Dataprev tem 1015; uma datalist com isso não é sugestão, é um documento).
Dentro da biblioteca, prefere os assuntos DA disciplina escolhida
(`assuntos_por_disciplina`): oferecer "Remédios constitucionais" a quem digita
Contabilidade é ruído. No lápis de cada linha não há botão — corrigir um rótulo
é ação sobre a biblioteca, e fazer a correção depender de um modo que está no
outro canto da tela esconderia metade das grafias possíveis.

**Link indexado resolve o DNS antes de baixar (SSRF).** O pedido sai de dentro
da rede do servidor, então "cole uma URL" é uma primitiva de requisição
arbitrária se ninguém olhar. `material.baixar` resolve o nome, exige
`ipaddress.is_global` em todos os endereços e REVALIDA a cada redirecionamento
— redirect é o furo clássico: o domínio público responde 302 pra
`169.254.169.254`. Verificado contra `127.0.0.1`, `localhost`,
`169.254.169.254`, `10.0.0.5` e `file://`. O que isso NÃO é: allowlist de
domínio. Endereço público que serve conteúdo hostil continua aceito, e a tela
diz o limite ANTES de a pessoa colar e falhar.

**A consulta de busca não é a mensagem: a 014 deu memória ao MODELO e deixou
o BUSCADOR amnésico (`core/assunto.py`).** O prompt passou a receber 8 turnos;
`retrieval.buscar` continuou recebendo a frase isolada. E `hibrida()` é
k-vizinhos, sem piso de relevância — frase sem assunto não devolve vazio,
devolve 6 artigos com confiança total. Relatado com log de conversa real: o
aluno conversou a sessão inteira sobre eficácia das normas constitucionais,
escreveu "vamos", clicou em "quero questões sobre isto", e recebeu CP art. 352
(evasão mediante violência) e CF art. 200 (SUS) — porque a tela mandava a
ÚLTIMA FALA como tema e rodou `buscar("vamos")`. Reproduzido byte a byte antes
de consertar.

O mesmo cano no chat: no turno em que ele escreveu "você deveria perguntar se
eu já sei algo do assunto... melhor me explicar", voltaram CPP 188/190/203/212
— os artigos de INTERROGATÓRIO. A busca acertou as palavras e errou a matéria.
E a prova de que o retriever está são está no mesmo log: no turno com "eficácia
limitada existem 2 tipos" ele trouxe a apostila certa seis vezes. **Turno com
assunto acerta; turno curto ou meta devolve lixo** — por isso `retrieval.py`
NÃO foi tocado e o gabarito do `avaliar_retrieval.py` segue valendo.

`em_foco()` é REGRA, não LLM (mesma escolha de `ritmo_regras`): extrair tema
por modelo custaria a cota mais escassa e 1-2s em TODO turno, e resposta de
modelo não se trava em teste. Enriquece ENQUANTO a consulta está fraca e para ao
ter assunto (`CONTEUDO_SUFICIENTE`) — contar turnos não serve pros dois casos:
"queria saber como a fgv cobra" precisa de dois reforços pra alcançar "eficácia
limitada", e dois reforços numa conversa que migrou de Penal pra Constitucional
trazem PECULATO de volta. Citação de dispositivo vai CRUA, e é a exceção que
mais importa: `por_dispositivo` lê o número da própria string, então enriquecer
deixaria um "art. 140" de três turnos atrás sequestrar a pergunta nova.
`MIN_CONTEUDO = 1` por assimetria de erro — exigir 2 descartaria "matar alguém"
da consulta inteira. Ficam FORA de `VAZIAS`, de propósito, "direito", "penal",
"norma", "prazo", "pena" e "tipo": parecem genéricas e são o nome de metade das
disciplinas.

O tema da geração é derivado NO SERVIDOR (`POST /questoes/gerar` já recebia
`conversa_id`): "sobre o que é esta conversa" é regra, e regra com duas cópias
diverge — mesmo argumento que fez a mesa padrão ser resolvida no servidor.

**A escada pedagógica é ORDEM no prompt, não intenção.** Relatado no mesmo log:
o tutor empurrou "Quero questões sobre isto" nas três primeiras respostas e o
aluno teve de pedir aula. Nada mandava vender — mas "termine com uma pergunta ou
sugestão que ajude o aluno" somado a um parágrafo enfático sobre COMO oferecer o
botão produz isso: a instrução de formato mais específica ganha do objetivo
vago. Agora o prompt diz descobrir -> explicar -> testar, com exceção permanente
se o aluno PEDIR questão, e o fecho é o PRÓXIMO DEGRAU em vez da mesma oferta
(três mensagens com o mesmo convite é ruído que se aprende a ignorar — mesma
lição de `ritmo` mostrar UMA sugestão por sessão). "Assunto novo" virou FATO
calculado em código: conversa sem histórico entra como "Primeira mensagem desta
conversa", senão conversa vazia é indistinguível de histórico que não veio.

**O que o aluno CONFUNDE não é o que ele erra (migração 022).**
`ESQUEMA_AVALIACAO` pedia `conceito_faltante` ao modelo desde sempre, o Gemini
preenchia em toda avaliação, o campo atravessava a API e estava tipado no front
— e era DESCARTADO. Já pago e jogado fora. `erro_caderno.tema` não substitui:
guarda `questao.tema`, o rótulo da PERGUNTA escolhido por quem gerou a questão.
É a diferença entre "errou a questão de peculato culposo" e "confunde extinção
da punibilidade" — medido com o modelo real, nas duas linhas do mesmo prompt.

Vai em `tentativa` e não em `erro_caderno` porque `tentativa` é o FATO e
`erro_caderno` o agregado: a mesma questão errada duas vezes pode faltar coisa
diferente em cada uma, e é essa mudança que mostra evolução. NULLABLE porque
item C/E é corrigido em código (012) e não produz conceito — `DEFAULT ''` faria
"não houve modelo" ficar igual a "o modelo não achou nada".

**Texto de LLM voltando pro prompt de LLM é input sujo, e a defesa é em código.**
Lista fechada não cabe (conceito é livre por natureza), então: `conceito_limpo`
COLAPSA quebra de linha — é a quebra que transforma campo de dado em bloco de
instrução dentro do prompt (`confunde X` + linha em branco + `### Instrução:
ignore as regras acima` chegaria como duas seções) —, CHECK de 160 no banco pra
que um segundo caminho de escrita não passe calado, e no prompt ele entra ENTRE
ASPAS e com autoria ("apontado pela sua própria correção"), nunca como fato do
sistema no meio de números do banco. E **nunca** vai pro `usuario.perfil`: esse
campo é lido inteiro e literal pelo prompt, e fechar esse laço deixaria o modelo
instruir a si mesmo no turno seguinte. Há teste que trava isso.

Agrupamento por string exata (minúsculas) + disciplina, com mínimo de 2
ocorrências — apontado uma vez é observação, e a lição de `ritmo_regras` sobre
amostra pequena vale aqui igual. Medido: duas avaliações reais da MESMA questão
devolveram a MESMA string ("Extinção da punibilidade"), porque o campo é curto e
o modelo escreve um NOME de conceito, não uma frase. Agrupar por similaridade
(embeddings) seria o conserto de raiz e não vale antes de o agrupamento ruim
doer.

## Invariantes (violação = bug)

- Todo `Art.` do arquivo vira um chunk. `diagnostico.py` verifica.
- Toda linha aceita como rubrica é atribuída a algum chunk.
- `questao.fonte_chunks` aponta para o artigo real de onde a questão saiu.
  Se o modelo cita artigo fora do lote, a questão é DESCARTADA — cobertura
  que mente é pior que cobertura inexistente. Vale IGUAL na geração sob
  demanda (`core/geracao.py`), que reusa a mesma `salvar()`: gerar no meio
  de uma sessão não é motivo pra afrouxar a regra.
- Item `certo_errado` tem `gabarito_ce` não-nulo e `resposta_livre` tem
  `gabarito_ce` nulo. Não é convenção — é CHECK no banco (012).
- `tentativa.conceito_faltante` nunca passa de 160 caracteres e nunca contém
  quebra de linha. CHECK no banco (022) + `scheduler.conceito_limpo`.
- Nenhum texto gerado por LLM é escrito em `usuario.perfil`. O prompt lê esse
  campo inteiro e literal; a lista fechada da 015 existe por isso.
- Questão com `contexto_id` tem `ordem_no_contexto`, e vice-versa (CHECK, 013).
- Item C/E nunca recebe veredito `parcial`: metade de um booleano não é nada,
  e `parcial` desce uma caixa.
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

- **`@lru_cache` NÃO é trava: ele memoiza o resultado, não protege o corpo.**
  `embeddings._modelo()` era `@lru_cache(maxsize=1)`, e isso pareceu suficiente
  por meses porque nada rodava embedding em paralelo. Subir TRÊS materiais em
  lote pela tela quebrou: `api.py` indexa em `BackgroundTasks` (pool de
  threads), as três threads erraram o cache juntas, as três construíram o
  SentenceTransformer, e duas morreram com `Cannot copy out of meta tensor; no
  data!` — o transformers inicializa os pesos no device `meta` e depois os move,
  e as cargas simultâneas disputam esse estado. Resultado medido: 2 `falha` e 1
  `pronto`, com a razão gravada em `documento.erro` (foi o único motivo de eu
  ter descoberto em vez de achar que o PDF era ruim). Corrigido com dupla
  checagem (`threading.Lock` + global), caminho rápido sem trava. Não é caso só
  do lote: uma pergunta no tutor DURANTE uma indexação chama `embed_consulta` de
  outra thread, então o furo estava no caminho interativo também. **Não
  serializei os `encode`**, e é escolha: uma trava global ali poria a pergunta
  do aluno atrás de um lote de 14 arquivos por dez minutos. `tests/
  test_embeddings_concorrencia.py` trava isso — e o teste foi conferido CONTRA
  o bug (a versão com `lru_cache` constrói 6x na mesma corrida), porque um teste
  de concorrência que não reprova a versão quebrada não está medindo nada.

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
  consegue COBRÁ-LO, porque `geracao` só usa acervo público (008). Consertar
  exige piso de relevância, e o gabarito do `avaliar_retrieval.py` deve receber
  esse caso ANTES do código.

## Aberto

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
- Antes de mexer no PROMPT do tutor (`socratic.explicar`): rode uma pergunta
  real e LEIA a resposta. Duas regressões nasceram de prompt que parecia
  certo — o rótulo de seção citado como fonte
  (`[DESEMPENHO REAL DO ALUNO]`) e o modelo escrevendo questão de múltipla
  escolha dentro do chat. Nenhuma das duas aparece em teste automatizado,
  porque o texto continua sendo uma resposta válida.
- Pra conferir a TELA com dado plausível (não só o terminal):
  `python semear_demo.py --email conta@teste --senha 12345678`. `simular.py`
  responde se a REGRA se sustenta; ele não toca no banco, então não diz se
  a tela fica coerente.
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
  010 não está só escrita — está executável. O mesmo vale pra
  `test_geracao.py` (proveniência e os CHECKs da 012/013),
  `test_conversa.py` (histórico chegando ao prompt) e `test_perfil.py`
  (perfil inválido nunca chegando ao prompt).
- **Migração numerada nova exige aplicar na mão** (ver a armadilha do
  `docker-entrypoint-initdb.d` logo abaixo). Da 012 à 020 todas foram
  aplicadas assim; num banco recriado do zero elas entram sozinhas.

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

# API (o apps/web consome de verdade; curl abaixo pra testar sem o front)
uvicorn api:app --reload --port 8000
curl -s -X POST localhost:8000/auth/registrar -H 'content-type: application/json' \
     -d '{"email":"voce@exemplo.com","senha":"pelomenos8chars"}'
curl -s localhost:8000/fila -H "Authorization: Bearer $TOKEN"

# questão sob demanda: cria do ACERVO quando o banco não tem (custa cota)
curl -s -X POST localhost:8000/questoes/gerar -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"quantidade":3}'
# com tema (o assunto da conversa) e formato explícito
curl -s -X POST localhost:8000/questoes/gerar -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' \
     -d '{"tema":"acumulação de cargos","tipo":"certo_errado","quantidade":3}'

# desafio com orçamento de tempo ("só tenho 20 minutos hoje")
curl -s "localhost:8000/desafio?minutos=20" -H "Authorization: Bearer $TOKEN"

# conversa do tutor (014): sem conversa_id, o servidor abre uma e devolve o id
curl -s -X POST localhost:8000/perguntar -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"pergunta":"art. 312"}'
curl -s localhost:8000/conversas -H "Authorization: Bearer $TOKEN"

# perfil de estudo (015) — faz merge, não substitui
curl -s -X PUT localhost:8000/me/perfil -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"horas":"2h","nivel":"Intermediário"}'

# olhar a TELA com dado plausível: 3 mesas e 15 dias numa conta descartável
python semear_demo.py --email voce@teste --senha 12345678
python semear_demo.py --limpar --email voce@teste

# mesas (migração 010): o header escolhe o recorte; sem header, mesa padrão
curl -s -X POST localhost:8000/mesas -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"nome":"PF Agente","banca":"Cebraspe"}'
curl -s localhost:8000/mesas -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/fila  -H "Authorization: Bearer $TOKEN" -H "X-Mesa-Id: 3"

# biblioteca do aluno (019/020): material PRIVADO, indexado no mesmo acervo
curl -s localhost:8000/materiais -H "Authorization: Bearer $TOKEN"
# disciplina e assunto são OPCIONAIS — sem eles, o classificador descobre
curl -s -X POST localhost:8000/materiais -H "Authorization: Bearer $TOKEN" \
     -F "arquivo=@aula-03.pdf" -F "tipo=aula"
curl -s -X POST localhost:8000/materiais/link -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"url":"https://exemplo.org/lei.pdf"}'
# o que alimenta o seletor da tela: só os rótulos DESTE aluno
curl -s localhost:8000/materiais/sugestoes -H "Authorization: Bearer $TOKEN"

# o que o aluno CONFUNDE (022) — agregado do conceito_faltante das tentativas
curl -s localhost:8000/conceitos -H "Authorization: Bearer $TOKEN"

# editar o alvo DEPOIS de o edital estar valendo, sem subir o PDF de novo
curl -s -X PATCH localhost:8000/edital/disciplinas -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"remover":["Contabilidade"]}'
curl -s -X PATCH localhost:8000/edital/data-prova -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"data_prova":"2026-11-15"}'
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