# FerrarIA — contexto completo para retomada

> **HISTÓRICO, NÃO CHECKPOINT ATUAL.** Este handoff foi superado pelo trabalho
> posterior da fase 0. Para retomar, leia `AGENTS.md` e
> `docs/ESTADO_ATUAL.md`; confirme no banco. Em especial, “fase 0 concluída” e
> “2.358 chunks” abaixo descrevem o estado conhecido na hora deste handoff, não
> o estado atual.

Documento de passagem. Escrito para outra IA assumir o trabalho sem precisar
reconstruir nada. Data: 21/09/2026.

---

## 1. O que é o projeto

**FerrarIA** — tutor socrático para concursos públicos, desenvolvido por A.
Ferrari. Projeto pessoal, separado por decisão explícita do trabalho dele numa
cooperativa; só usa material público.

**Repositório:** `~/tutor-concursos` (WSL Ubuntu, usuário `administrador`)
Monorepo. Todo caminho e comando é relativo a `apps/api/`, exceto
`docker compose`, que lê o `docker-compose.yml` da raiz.

**Pilha:**

```
Postgres 17 + pgvector 0.8.6   docker compose, porta 5433
embeddings                     intfloat/multilingual-e5-base, 768 dim, LOCAL (CPU)
LLM                            gemini-3.5-flash-lite via REST (free tier)
auth                           JWT (PyJWT) + bcrypt, stateless
frontend                       Next.js, localhost:3000
backend                        FastAPI, localhost:8000
```

**Atenção:** o `CLAUDE.md` diz `gemini-3.1-flash-lite` na seção "Pilha". Está
desatualizado — o `.env` traz `GEMINI_MODEL=gemini-3.5-flash-lite`. Corrigir o
mapa quando houver oportunidade.

---

## 2. Processo de trabalho obrigatório

O projeto tem regras próprias em `.clinerules` e `CLAUDE.md`. Elas valem mais
que o estilo de qualquer assistente. Resumo operativo:

**Fast Track** (padrão para pedido pontual = bug, ajuste localizado, mudança
clara em arquivo conhecido):
proibido plano, pré-análise, lista de alternativas, pergunta de permissão e
resumo longo. Sequência: abrir o arquivo → editar o bloco (nunca reescrever o
arquivo) → rodar **só** o teste que cobre a mudança → responder em **até 3
linhas** (o que mudou, `arquivo:linha`, resultado do teste).

**Sai do Fast Track** — parar e perguntar antes: migração que apaga dado; ação
irreversível ou que sai da máquina (push, deploy); arquitetura nova ou pedido
com duas leituras plausíveis; qualquer coisa fora do que foi pedido.

**Antes de mexer em qualquer coisa:**

- Ler a seção correspondente de `docs/DECISOES.md` (3.031 linhas). Decisão
  registrada com MEDIÇÃO só cai com outra medição, nunca com opinião.
- Todo módulo tem `VERSAO = "nome-vN"` no topo. Conferir antes de depurar: o
  bug mais caro do projeto foi rodar código antigo achando que era novo.
- `docs/LIMITACOES.md` lista o que o sistema NÃO faz e o que já foi tentado e
  revertido.

**Comandos:**

```bash
source ativar.sh              # venv + apps/api
./tutor <cmd>                 # roda um comando no venv certo
python avaliar_retrieval.py   # precisão da busca contra gabarito (sem LLM)
python diagnostico.py         # chunking (sem banco)
./testar.sh                   # qualidade da resposta do tutor (GASTA LLM)
pytest tests/                 # suíte, ~3,5 min
python migrar.py --listar     # estado do schema
```

**Migrações:** só por `python migrar.py`. Nunca `psql -f` — fora do runner não
entra no livro-razão (023). A próxima é a **032**.

---

## 3. Invariantes do projeto (violação = bug)

- Todo `Art.` do arquivo vira um chunk; `diagnostico.py` verifica.
- `questao.fonte_chunks` aponta pro artigo real. Artigo fora do lote = questão
  DESCARTADA.
- `certo_errado` tem `gabarito_ce`; `resposta_livre` não tem (CHECK 012).
- Item C/E nunca recebe veredito `parcial`.
- Nenhum texto de LLM é escrito em `usuario.perfil`.
- Questão com `usuario_id` (026) nunca aparece pra outra pessoa. Predicado
  único: `questoes.do_aluno()`.
- Material de REFERÊNCIA (jurisprudência, corpus fatiado por artigo) não recebe
  assunto nem disciplina em `chunk.rotulo` (027). O rótulo entra no tsvector
  (025) e assunto único num corpus de centenas decide ordenação por ruído.
- Indexar documento é exclusivo: `pg_try_advisory_lock` por documento_id. Dois
  processos já apagaram material de um aluno.

---

## 4. Como a busca funciona (`core/retrieval.py`, hoje `retrieval-v9`)

`buscar()` tem três caminhos, em ordem de precisão:

1. **`por_dispositivo`** — a pergunta cita "art. 312". Busca exata por
   `(norma, artigo)`. Devolve `score = 1.0` fixo. Se acerta, devolve SÓ isso —
   contexto extra não ajuda e convida o modelo a citar outra coisa
   (`DECISOES.md:25`).
2. **`por_rubrica`** — nome de crime ("peculato"). Devolve 3 + 2 de
   complemento.
3. **`hibrida`** — RRF sobre dois braços:
   - semântico: kNN por distância de cosseno, `LIMIT k=40`
   - lexical: `websearch_to_tsquery('portuguese', ...)` com `@@`
   - fusão: `1/(60+pos_sem) + 1.5/(60+pos_lex)`, com `RRF_K = 60`

**Constantes medidas (não mexer sem nova medição):**

- `PESO_LEXICAL = 1.5` — corrige viés contra chunks grandes. O art. 37 da CF
  tem 13.059 caracteres (média do acervo: 1.245) e o embedding médio o punha em
  83º no semântico contra 3º no lexical. Menor valor que corrige.
- `PESO_HISTORICO = 0.5` — material `historico` (livro de emendas) vale menos
  na fusão.
- `RRF_K = 60`, `k = 40`, `n = 6`.

**Filtros, dentro das CTEs (nunca no WHERE final — filtrar depois faria
material alheio ocupar vaga do top-k):**

```sql
DONO = "(d.usuario_id IS NULL OR d.usuario_id = %(uid)s)"
MESA = "(%(mid)s::bigint IS NULL OR d.usuario_id IS NULL
         OR d.mesa_id IS NULL OR d.mesa_id = %(mid)s)"
```

**Quem decide o `mesa_id` — `core/socratic.py:943`:**

```python
mesa_id = mesa_.get("id") if mesa_ and mesa_.get("biblioteca_compartilhada") is False else None
```

Ou seja: com `biblioteca_compartilhada = True` (o default), a produção passa
`mesa_id=None` e não recorta nada. **Toda medição precisa usar `mesa_id=None`,
senão mede um cenário que a aplicação não vive.** Isto custou três rodadas de
medição inválida nesta sessão.

---

## 5. O corpus real (uid 1914)

35 documentos, 6.697 chunks.

| Disciplina | Situação |
|---|---|
| **Criminalística** | 18 aulas (`curso-392569`, docs 1024–1040), ~2.060 chunks, **todas com rótulo e com arquivo original**. É o corpus mais rico e o único bom para testar ancoragem no material. |
| **Direito Constitucional** | 8 aulas (`curso-392722`) + CF + ADCT + livro de emendas. 6 das 8 aulas **sem rótulo e sem arquivo original**. |
| **Direito Administrativo** | 1 apostila (255 chunks) + Lei 8.112. |
| **Direito Penal** | Só o CP (434 chunks, tipo `lei`). **Nenhuma aula.** |
| **Direito Processual Penal** | Só o CPP (848 chunks, tipo `lei`). **Nenhuma aula.** |

**Consequência prática:** perguntar sobre Penal ou Processual Penal testa
citação de dispositivo, não recuperação de material. O modelo sabe lei seca de
cor e acerta sempre, mascarando falha de busca. Criminalística é o único lugar
onde dá pra separar "o RAG funcionou" de "o Gemini sabia".

**Mesas:**

```
1007  "Agente"          biblioteca_compartilhada = True  (era False, corrigido)
3018  "Mesa principal"  biblioteca_compartilhada = True
```

A Criminalística mora na 3018.

---

## 6. Auditoria inicial (bateria 1, seções 1–10 de um spec de QA)

17 consultas instrumentadas contra `localhost:3000/tutor`, com hook de `fetch`
medindo TTFB, duração e corpo de resposta.

**Arquitetura observada:**

- `POST /perguntar` — corpo `{pergunta, conversa_id?}`; headers `Authorization:
  Bearer` e `X-Mesa-Id`.
- Resposta: `{resposta, fontes[], questoes[], conversa_id, titulo,
  questoes_fora_do_assunto, simulado_pedido}`.
- `fontes[]` expõe `disciplina, norma, artigo, paragrafo, rubrica, tipo, score,
  citada`. **Manter esse campo — foi o que tornou a auditoria possível.**
- **Não há streaming.** `content-type: application/json`, 1 chunk, resposta
  inteira de uma vez. 1,0 a 6,2 s de tela parada; média 1,7 s.
- 46 rotas no OpenAPI, e `/openapi.json` responde sem autenticação (irrelevante
  em localhost, fechar antes de deploy).

**Resultado de qualidade:** em 17 consultas, **zero afirmação jurídica
incorreta**. Recusou corretamente premissa falsa sobre pena do art. 312, súmula
inexistente e disciplina fora do edital.

**Padrão sistêmico encontrado, e é o mais importante do projeto:**

> **O acerto do modelo mascara a falha do RAG.**
>
> Exemplo medido: `qual o prazo do art. 312 para reparação no peculato culposo`
> recuperou o **§1º** e respondeu corretamente sobre o **§3º**. Sem olhar
> `fontes`, isso conta como sucesso.

**Toda validação de RAG neste projeto precisa olhar a fonte, não a resposta.**

---

## 7. Fase 0 — CONCLUÍDA

Objetivo: corrigir defeito de recuperação, sem mudar comportamento de produto.
Corrigir antes de medir, porque medir sobre defeito é medir ruído.

### Corrigido

| Commit | O quê |
|---|---|
| `d9c9325` | **Norma citada e ausente do corpus.** `art. 1º da Lei 8.429` devolvia o art. 1º do ADCT, da CF, do CP, do CPP e da L8112 — todas as normas do índice, com `score=1`. Causa: `_norma_mencionada` só resolve contra normas existentes no banco, então norma ausente devolvia `None`, indistinguível de "nenhuma norma citada", e o filtro se desligava. Conserto: `RE_NORMA_NUMERADA` detecta referência a lei numerada; não resolvendo, `por_dispositivo` devolve `[]` e `buscar` cai para rubrica/híbrida. (`retrieval-v7`) |
| `0e553de` | **Norma por extenso.** Regressão criada pelo anterior: `art. 20 da Lei 8.112` passou a devolver `[]` porque o banco guarda `L8112`. Conserto: `_formas_por_extenso` deriva o padrão da própria sigla, em vez de tabela manual de apelidos. (`retrieval-v8`) |
| `436b835` | **`VAZIAS` no braço lexical.** `_termos_lexicais` removia só `GENERICOS` (art/artigo/parágrafo/inciso/caput). `assunto.VAZIAS` — a lista que separa "falar da matéria" de "falar sobre o estudo" — nunca era consultada. Resultado medido: `"obrigado, era só isso"` casava 299 chunks e 6/6 lexical, parecendo mais coberto que `"peculato culposo"` (1 chunk). Conserto: aplicar `VAZIAS` e remover o fallback `or pergunta`. (`retrieval-v9`) |
| — (dado) | **Documento 346** (`curso-392722-aula-07`, 515 chunks, 11,7% do índice) estava com `disciplina = NULL` e vazava em consulta de qualquer matéria. Classificado como Direito Constitucional via `PATCH /materiais/346`. |
| — (dado) | **Documento 707 apagado.** Era cópia da Aula 00 de Ciências Forenses arquivada como Direito Processual Penal, com rótulo zerado, duplicando o doc 1040. Conferido antes: 0 questões apontando pros chunks dele, 102 dos 106 textos idênticos. |
| — (config) | **Mesa 1007 tinha `biblioteca_compartilhada = False`.** Com ela ativa, a produção passava `mesa_id=1007` e **excluía os 2.060 chunks de Criminalística**, que moram na mesa 3018 — no concurso que tem Ciências Forenses no próprio edital. Corrigido por `PATCH /mesas/1007`. **Foi o conserto de maior efeito da fase inteira, e é configuração, não código.** |

### Adiado, com registro no código

**Troca curta de disciplina.** `"e no processo penal?"`, dito depois de uma
pergunta do tutor, é classificado como resposta (`assunto.e_eco` devolve
`True`) porque não tem verbo de `PEDIDO`, não cita dispositivo e não pede
treino. A consulta vira a fala do tutor, que é da disciplina anterior. A busca
fica **um turno atrás da conversa**.

Registrado em `tests/test_assunto_troca_de_disciplina.py` (2 testes `xfail`
estrito — viram XPASS e acusam quando alguém consertar) e em
`docs/LIMITACOES.md`.

Tentado e revertido em 19/09. A correção exigia quatro mudanças acopladas:
`disciplinas` em `pede_assunto` e `e_eco`, trocar o filtro do caminho normal de
`em_foco` para `_com_assunto` — **o que derruba citação pura**, porque
`"art. 312"` não tem palavra de conteúdo — e casamento por radical em
`disciplina_citada` (`"processo"` contra `"processual"`).

**Hipótese não testada, para quem retomar:** a resposta de `/perguntar` já traz
um campo `titulo` gerado pelo modelo. Um campo adicional tipo `assunto_atual`
no mesmo schema JSON custaria ~10 tokens de saída, zero requisição extra e zero
latência — e o turno seguinte usaria esse assunto declarado junto da fala nova.
**Ninguém leu o `socratic.py` para confirmar se cabe.** Fazer isso antes de
propor.

**2.358 chunks de aula sem rótulo.** São exatamente os documentos sem bytes do
arquivo original — o PDF não existe mais em disco, e `reingest.py` precisaria
de `--arquivo`. Sem conserto por código. Só reenviando o material. (Ver §10:
existe uma ferramenta pronta para isso.)

### Investigado e descartado por medição

Três propostas que **não** devem ser refeitas sem dado novo:

**Piso de relevância (corte por distância de cosseno).** Medido duas vezes,
`enable_indexscan=off`, 18 consultas em 5 grupos de cobertura. Com escopo
correto (`mesa_id=None`):

```
0.1491  peculato culposo         ← maior COBERTO
0.1509  substituição ICMS        ← NULO (zero material)
0.1542  teste de conexao harness ← RUÍDO
0.1575  docimasia hidrostática
```

Margem de **0,0018** entre coberto e não coberto, com ruído intercalado. Não é
limiar, é coincidência. **Causa:** distância de cosseno com `e5-base` mede
registro textual, não cobertura — pergunta de tributário "parece" texto
jurídico e cai perto de texto jurídico. Um embedding com faixa de similaridade
mais larga poderia separar, mas significa reprocessar 6.697 chunks.

**Teto de chunks por documento.** Medido: a concentração é 6/6 num documento só
em quase toda consulta real — mas isso é **correto**. 6 chunks do CP para
"peculato culposo" são o art. 312 e vizinhos; 6 chunks de uma apostila para
"princípios da administração" são a apostila daquele assunto. Concentração só
era defeito em consulta de ruído, e o ruído tem outra solução.

**HNSW cortando o braço semântico.** `hnsw.ef_search = 40`, filtro aplicado
depois do índice. Com `mid=1007` o CTE `sem` devolvia de 0 a 40 linhas. Com
`mid=None` (o que a produção usa): **16 de 18 consultas em 40/40**, déficit
restante de 3 e 1 linha. Era sintoma do recorte de mesa, não defeito próprio.
pgvector 0.8.6 tem `iterative_scan` se voltar a doer.

---

## 8. Onde o trabalho está agora

**Fase 0 fechada.** Suíte: 449 passed, 1 skipped, 2 xfailed.
`avaliar_retrieval.py`: top1 23/34, top6 32/34 — idêntico ao baseline em todas
as rodadas (o gabarito ganhou 2 casos de norma por extenso, 32 → 34).

**Próximo passo: Fase 1 — montar a bateria 2 e medir a linha de base.**

A bateria 1 mediu recuperação em material que o modelo sabe de cor. A bateria 2
mede **ancoragem**: perguntas cuja resposta certa só existe no material do
aluno, ou que diverge do conhecimento geral. Ponto de corte de banca,
entendimento que a aula adota e a doutrina majoritária não, número que mudou
depois do treino do modelo.

Ela deve ser **estratificada por cobertura**, porque o comportamento certo é
diferente em cada estado e o sistema precisa saber em qual está:

| Estado | Onde testar | Comportamento esperado |
|---|---|---|
| Farto | Criminalística (18 aulas) | responde ancorado no material |
| Lei sem aula | CP, CPP | entrega o dispositivo exato |
| Escasso | Administrativo (1 apostila) | responde e sinaliza material raso |
| Nulo | fora do edital | diz que não tem |

**Como montar:** ler os chunks indexados de Criminalística e extrair afirmações
verificáveis (número, prazo, classificação, critério) que o modelo não teria
como saber de cor. Cada uma vira uma pergunta com gabarito conferido contra o
chunk. 15 a 20 perguntas bastam.

**Armadilha de medição, importante:** rodar a bateria 1 depois de mudar a fonte
de conhecimento faz os números **melhorarem** — menos recusa, mais fluidez —
enquanto o risco real sobe. A bateria 1 mede recuperação; o risco das mudanças
de Fase 2 em diante é alucinação em conteúdo material-específico, que só a
bateria 2 enxerga.

---

## 9. Fases seguintes, na ordem decidida

**Fase 2 — partir a "Precedência 0" em duas.** Hoje a regra manda número
normativo sair só de trecho recuperado. O dono quer mais fluidez, e tem razão:
recusa não protege ninguém se o aluno abre outra aba.

A divisão que funciona sem brigar com o verificador:

- **Número normativo** (artigo, súmula, pena, prazo, posição de tribunal):
  chunk obrigatório. Continua duro.
- **Explicação conceitual** (definição, analogia, mnemônico, tabela
  comparativa, cálculo passo a passo, mapa mental): liberado.

`avaliar_chat.checar` reprova artigo sem chunk, e **não** reprova explicação —
a linha que o verificador já traça é exatamente essa. A caixa de ferramentas
pedagógica inteira cai no lado liberado: risco zero perante o verificador, sem
tier pago, sem busca externa.

**Fase 3 — streaming no `/perguntar`.** Hoje são 1,7 s de tela parada em média,
6,2 s no pior caso. Boa parte da sensação de "o Gemini Web é mais vivo" é isso,
não conhecimento. Sem risco de correção, e vira pré-requisito da Fase 5.

**Fase 4 — `fontes[]` vira proveniência tipada.** Hoje `citada` vem `false` em
**17 de 17** consultas, enquanto a UI exibe selo "CONSULTADO". No caso do art.
312, a fonte exibida era o §1º e a resposta tratava do §3º. Ou o campo está
morto, ou a UI atribui procedência falsa.

Consertar isso é a **mesma** mudança que qualquer conhecimento externo vai
exigir: `fontes[]` deixar de ser "chunks recuperados" e passar a ser
"proveniência da resposta", com tipo. Fazer uma vez, servir as duas.

**Fase 5 — conhecimento externo.** Duas sub-etapas:

- **5a — ingestão de jurisprudência curada.** STF e STJ publicam informativos,
  súmulas e teses de repetitivo de forma estruturada. Não é problema de web
  aberta: é conjunto delimitado. Entra no corpus, passa pelo chunking, aparece
  em `fontes[]`, o verificador funciona normalmente, tem data e órgão. Resolve
  o buraco declarado em `fora_do_acervo` sem depender de tier nem de busca
  externa. **Provavelmente resolve ~80% do que o dono chama de material
  escasso.**
- **5b — busca web para o resto** (edital, banca, conteúdo recente).

**Sobre grounding do Gemini:** "Grounding with Google Search" é **"Not
available" no free tier** para `gemini-3.5-flash-lite`. Não é questão de preço,
é de disponibilidade. No tier pago: 5.000 buscas/mês grátis compartilhadas
entre os modelos 3.x, US$ 14 por 1.000 depois; o contexto trazido pela busca
não é cobrado como token de entrada.

**Alerta de arquitetura, levantado pelo próprio dono e correto:** empacotar
resultado de web no mesmo formato dos chunks **cega o verificador** em vez de
passar por ele. `avaliar_chat.checar` reprova afirmação normativa sem trecho, e
com razão — a lista de fontes embaixo da resposta é o que o aluno confere. Se
entrar, entra como fonte de primeira classe, marcada como web, com URL. Nunca
como texto solto no prompt.

**Sobre DuckDuckGo scraping** (avaliado e desaconselhado): é raspagem, o limite
é por IP, e quebra exatamente quando o projeto ganha usuários — otimizada para
o cenário que ele está saindo. Tavily / Brave / Exa são o meio sensato:
contrato de API, conteúdo limpo, URL de volta. Escolher por confiabilidade e
proveniência, não por preço: o custo de busca é segunda ordem perto da
inferência.

---

## 10. Ferramenta paralela já entregue

Na mesma sessão foi construído um baixador/organizador dos PDFs do Estratégia
Concursos, entregue em `Documents\Baixar Materiais\_ferramenta\`:

- `coletar.js` — cola no console do Chrome logado, varre pacote → cursos →
  aulas expandindo a listagem (o link do PDF carrega ao expandir, então dá 18
  requisições em vez de ~450), gera `manifesto.json`. Token nunca sai da
  máquina.
- `baixar.py` — lê o manifesto, baixa com throttle, valida magic bytes `%PDF`,
  retoma de onde parou, resolve colisão de nome (o curso tem duas "Aula 06"),
  gera `_indice.csv`. Python puro, sem `pip install`.
- `LEIA-ME.md`.

**Conexão com o item pendente:** é esta ferramenta que resolve os 2.358 chunks
sem arquivo original. Baixar de novo as 6 aulas de Constitucional que estão sem
bytes e reingerir fecha a única limitação da Fase 0 que não tem conserto por
código.

---

## 11. Débito conhecido, fora de escopo até agora

- **Questão 1062 órfã** — aponta para o chunk 7274, criada em 15/09, anterior a
  todo este trabalho. Viola o invariante de `fonte_chunks`.
- **Art. 37 da CF, 13.059 caracteres.** O embedding é a média de concurso
  público, licitação, teto e improbidade juntos. Conserto de raiz registrado no
  `DECISOES.md`: sub-chunk do artigo gigante para o embedding, mantendo o
  artigo como unidade de citação. Exige reingestão.
- **`CLAUDE.md` desatualizado** na linha do modelo (3.1 contra 3.5).
- **`/openapi.json` sem autenticação** — irrelevante em localhost, fechar antes
  de qualquer deploy.
- **UI:** botão escrito `"pedir dica (3 disponíveleis)"`; `"Modo Socrático"`
  não aparece na árvore de acessibilidade como elemento interativo (provável
  `div` com `onClick`, inalcançável por teclado).
- **Contradições numéricas na tela inicial** — texto semeado fixo que não
  conversa com os números calculados: "Faltam 63 dias" contra sidebar "23 dias
  · 11/10"; "39% do edital aberto" contra "EDITAL FECHADO 0%"; "ofensiva de 12
  dias" contra "OFENSIVA 0"; "Direito Constitucional 8%" logo acima de "0 de 44
  dominadas · 0% coberto".

---

## 12. Lições de método que custaram caro nesta sessão

Escritas porque valem para quem assumir.

**Ler o código antes de propor.** Três vezes que a leitura veio primeiro, a
proposta estava certa ou foi corrigida a tempo. Todas as vezes que a proposta
veio de cabeça, estava errada:

- o filtro de norma "que faltava" já existia em `retrieval.py:202`
- o teto por documento ignorava que o CP inteiro é **um** documento
- a Opção A do `assunto.py` quebrou citação pura, e foi revertida

**Declarar o escopo em toda medição.** Três rodadas de medição foram rodadas
com `mesa_id=1007` enquanto a produção passa `mesa_id=None`. A divergência foi
notada e ignorada por duas rodadas. Toda tabela de medição deve trazer
`uid` e `mesa_id` no cabeçalho, e conferir se batem com o que a aplicação faz.

**Não confiar em tabela truncada.** Uma lista cortada em 16 linhas gerou a
conclusão errada de que a Criminalística tinha duas aulas indexadas. Tem 18.

**Medir antes de escolher número.** Três propostas morreram com dado —
piso, teto, HNSW. As três teriam entrado no código se não fossem medidas.
Preferir isso a três correções erradas dentro do projeto.

---

## 13. Infraestrutura de leitura (para o assistente)

O projeto roda no WSL. Existe um espelho em
`C:\Users\Administrador\Documents\tutor-concursos`, mantido por um vigia
`inotifywait` + `rsync` que sincroniza a cada save.

Caminhos UNC (`\\wsl.localhost\...`) são bloqueados para leitura externa — por
isso o espelho existe. Postgres (porta 5433) **não** é alcançável de fora da
máquina; todo teste que toca banco, e o `avaliar_chat.py`, são do dono.

Antes de escrever qualquer bloco de Fast Track: conferir a `VERSAO` no topo do
módulo alvo. Se estiver defasada em relação ao último commit reportado, o
espelho caiu — parar e avisar em vez de escrever sobre código velho.
