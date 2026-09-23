# Mapa da aplicação para manutenção assistida

Mapa de navegação, não especificação duplicada. Foi levantado do código em
21/09/2026. Quando divergir, código/migração atual vence e este arquivo deve ser
corrigido no mesmo patch.

## Por onde entrar

| Demanda | Comece por | Teste direcionado |
|---|---|---|
| Resposta do tutor, prompt, citação | `core/socratic.py` | `test_llm_boundary_api.py`, `test_citacao.py` |
| Busca/RAG | `core/retrieval.py` + seção de retrieval em `DECISOES.md` | `test_retrieval_*.py`; depois `avaliar_retrieval.py` |
| Foco da conversa/troca de matéria | `core/assunto.py` | `test_assunto.py`, `test_assunto_troca_de_disciplina.py` |
| Pedido de questões/simulado | `core/pedido.py`, `core/geracao.py` | `test_pedido.py`, `test_geracao.py` |
| Upload, link, rótulo, reindexação | `core/material.py` | caso exato em `test_material.py` |
| Chunk de lei/apostila | `core/chunking.py` | `test_taxa_colisao_artigo.py`, `diagnostico.py` |
| Fila/SM-2/caderno | `core/scheduler.py` | `test_scheduler_regras.py`, `test_scheduler_api.py` |
| Mesa/recorte | `core/mesa.py` | `test_mesa_api.py`, `test_multiusuario.py` |
| Edital/meta | `core/edital.py`, `core/rascunho.py` | `test_edital.py`, `test_edital_api.py`, `test_rascunho.py` |
| Simulado | `core/simulado.py` | `test_simulado_api.py` |
| Perfil/auth | `core/auth.py` | `test_auth_api.py`, `test_perfil.py` |
| Frontend/API tipada | `apps/web/src/lib/api.ts` e página | `yarn workspace web lint` ou build direcionado |
| Schema | `apps/api/db/*.sql`, `migrar.py` | `python migrar.py --listar` |

## Arquitetura em execução

```text
Navegador (Next.js 16, React 19)
  └─ apps/web/src/lib/api.ts
       ├─ Authorization: Bearer <JWT>
       └─ X-Mesa-Id: mesa ativa do localStorage
            ↓
FastAPI apps/api/api.py
  ├─ autenticação e resolução da mesa
  ├─ módulos core síncronos
  ├─ BackgroundTasks para indexação de material
  ├─ Gemini REST / Ollama via core/llm.py
  └─ PostgreSQL 17 + pgvector
       ├─ dados relacionais e tsvector
       └─ embeddings E5 locais (768d) + HNSW
```

Não há streaming no chat: `/perguntar` devolve um JSON completo. O backend usa
funções síncronas; trabalho pesado de upload é despachado para background do
próprio processo, não para worker externo.

## Fluxos principais

### Um turno do tutor

`POST /perguntar` resolve usuário e mesa, cria/valida a conversa, intercepta
`/erro` e `/feedback`, carrega a janela histórica, grava a fala do aluno e chama
`socratic.explicar`. O socrático deriva o assunto, decide quando dispensar
busca, recupera fontes, monta prompt com perfil/progresso/histórico e chama o
LLM. A resposta e as fontes são gravadas. Se a fala pediu treino informal,
`pedido.treino` aciona `geracao.sob_demanda`; simulado formal apenas sinaliza a
tela. Falha do gerador não apaga uma resposta de tutor já válida.

### Retrieval

`retrieval.buscar` tenta, nesta ordem:

1. dispositivo exato quando há artigo/norma;
2. rubrica do instituto;
3. híbrida por RRF: kNN semântico + full-text lexical.

Constantes atuais medidas: `PESO_LEXICAL=1.5`, `PESO_HISTORICO=0.5`,
`RRF_K=60`, candidatos `k=40`, saída normal `n=6`. Não criar piso de relevância,
teto por documento ou ajuste HNSW sem nova medição: as tentativas anteriores
foram descartadas com dados. Com biblioteca compartilhada, o fluxo real passa
`mesa_id=None`; benchmark com outro recorte mede outro produto.

### Biblioteca do aluno

Upload/link cria `documento` privado e preserva o original quando disponível.
`material.indexar` extrai e limpa texto, detecta lei/referência, divide,
classifica aula/resumo, gera embeddings e substitui chunks sob transação e
advisory lock. `chunk.rotulo` participa do tsvector. Referência ou corpus por
artigo fica sem assunto global. Estado só vira `pronto` depois da classificação.

Material antigo sem bytes pode usar `material.reindexar_rotulo`: classifica a
partir do texto dos próprios chunks, recalcula embedding+rótulo e mantém ids;
isso preserva `questao.fonte_chunks`. Reingestão comum exige o original.

### Estudo e avaliação

`scheduler` mantém Leitner/SM-2 simplificado em `progresso`, grava `tentativa` e
materializa reincidência em `erro_caderno`. `desafio` mistura reincidentes,
novas e mini-simulado dentro do orçamento. `ritmo` sugere intervenção por erros
recentes. `simulado` fixa a lista, acumula tempo e só entrega correção ao final.

### Mesa, edital e meta

Mesa é alvo/filtro, não silo de aprendizagem. O edital pertence à mesa; tópico
define disciplinas e cobertura. Sem edital, o alvo manual pode filtrar. Sem
nenhum alvo, aparece o acervo inteiro. Progresso e conversas continuam do
usuário; apagar mesa não apaga aprendizado e apenas desassocia simulados.

## Backend: responsabilidade por módulo

| Arquivo | Versão em 21/09/2026 | Responsabilidade |
|---|---:|---|
| `api.py` | api-v9 | borda HTTP, modelos Pydantic, dependências e códigos de erro |
| `core/auth.py` | auth-v4 | bcrypt, JWT, conta e perfil |
| `core/mesa.py` | mesa-v4 | alvo, disciplina, cobertura e isolamento por mesa |
| `core/edital.py` | edital-v8 | extração, estrutura, cobertura, meta e edição |
| `core/rascunho.py` | rascunho-v1 | curadoria temporária do edital |
| `core/conversa.py` | conversa-v3 | histórico persistido, eventos e desfazer |
| `core/assunto.py` | assunto-v11 | consulta em foco e troca de disciplina |
| `core/pedido.py` | pedido-v8 | intenção de treino, desempenho, memória e sistema |
| `core/socratic.py` | socratic-v69 | avaliação, explicação, prompt e orquestração RAG |
| `core/retrieval.py` | retrieval-v9 | dispositivo, rubrica e híbrida RRF |
| `core/llm.py` | llm-v18 | fronteira dos provedores, JSON, retry e erros |
| `core/embeddings.py` | embeddings-v3 | E5 local, prefixos e cache |
| `core/chunking.py` | chunking-v13 | chunk por artigo ou janela genérica |
| `core/material.py` | material-v25 | biblioteca, segurança de URL, classificação e índice |
| `core/geracao.py` | geracao-v5 | questões sob demanda com proveniência e posse |
| `core/questoes.py` | questoes-v4 | lookup e predicado único de visibilidade |
| `core/scheduler.py` | scheduler-v26 | fila, registro, carga, erros, conceitos e meta |
| `core/simulado.py` | simulado-v9 | sessão de prova e relatório |
| `core/desafio.py` | desafio-v6 | plano diário por tempo |
| `core/ritmo.py` | ritmo-v4 | intervenção proativa |
| `core/melhoria.py` | melhoria-v1 | fila explícita de feedback do aluno |
| `core/diario.py` | diario-v1 | memória de blocos de estudo teórico |
| `core/telemetria.py` | telemetria-v1 | chamadas, custo e falhas de LLM |
| `core/db.py` | — | conexão psycopg em autocommit para a aplicação |

Ferramentas de linha de comando ficam em `apps/api/`: `chat.py`, `ingest.py`,
`reingest.py`, `gerar.py`, `edital.py`, `migrar.py`, `sincronizar.py`,
`diagnostico.py`, `avaliar_retrieval.py`, `avaliar_chat.py`, `simular.py` e
`semear_demo.py`. Consulte `docs/COMANDOS.md`; não leia todas por padrão.

## API e frontend

Famílias de rotas: `/auth/*`; `/me*`; `/mesa`, `/mesas*`, `/disciplinas`;
`/edital*` e `/editais/rascunho*`; `/materiais*`; `/fila`, `/carga`,
`/sugestao`, `/desafio`, `/meta`, `/stats`, `/erros`, `/conceitos`;
`/questoes*`; `/simulados*`; `/perguntar`; `/conversas*`; `/gasto`.

`apps/web/src/lib/api.ts` é o contrato central do navegador: token e mesa no
`localStorage`, headers, tipos e um fetch tipado por rota. `cache.ts` guarda
leituras de UI; `perfil.ts` contém a entrevista; `tempo.ts` calcula duração.

| Página | Papel |
|---|---|
| `/login`, `/cadastro`, `/onboarding`, `/perfil` | conta e perfil de estudo |
| `/mesas`, `/alvo`, `/edital/[rascunho]` | concurso, edital e curadoria |
| `/materiais` | biblioteca privada e classificação |
| `/tutor` | conversa, fontes e questões geradas |
| `/fila`, `/questao/[id]` | revisão e resposta individual |
| `/desafio` | plano diário por orçamento |
| `/simulado` | prova cronometrada e histórico |
| `/erros`, `/stats`, `/meta` | acompanhamento |
| `/` | entrada/dashboard |

Para alteração visual, permaneça em `.tsx`/CSS/HTML. Para mudança de contrato,
altere API e `lib/api.ts` juntos e teste ambos. O `apps/web/AGENTS.md` manda
consultar a documentação local desta versão do Next antes de usar APIs do
framework.

## Dados

Migrações numeradas em `apps/api/db/` são a fonte do schema. A 023 criou o
livro-razão; o runner aplica cada arquivo em transação e registra checksum. Há
pares históricos com o mesmo número 018/019, por isso a ordem é o nome completo.

Grupos de tabelas:

- corpus: `documento`, `chunk`, `embedding_cache`;
- questões: `questao`, `contexto`;
- pessoa/aprendizado: `usuario`, `progresso`, `tentativa`, `erro_caderno`,
  `estudo_teoria`;
- alvo: `mesa`, `edital`, `topico`, `edital_rascunho`;
- sessões: `conversa`, `mensagem`, `simulado`;
- operação: `fila_melhoria`, `telemetria_llm`, `migracao`.

`documento` pode ser público (`usuario_id NULL`) ou privado. Questão também
pode ser pública ou privada desde a 026. Cascatas e `SET NULL` carregam decisões
de produto; leia a migração antes de alterar deleção.

## Testes e custo

Há testes puros, testes API/banco e avaliações. Escolha o menor que demonstra a
mudança:

- puro: arquivo de teste específico, sem subir toda a aplicação;
- integração: fixture do banco em `tests/conftest.py`, usuário descartável;
- retrieval: teste de regressão e, só quando ranking mudar,
  `avaliar_retrieval.py`; confira IDs/fontes, não só texto;
- prompt/produto: `./testar.sh` chama LLM e gasta cota; só com necessidade
  explícita. Nota de naturalidade é ruidosa; contagem de violações é o sinal
  mais confiável registrado.

Suíte completa não é ritual de cada patch. Use-a no fechamento de uma fase ou
quando a alteração atravessar contratos suficientes para justificar os minutos.

## AI Memory

Escopo local vem de `.ai-memory.toml`: `pessoal/tutor-concursos`. O servidor
roda em loopback e o banco/índice ficam fora do repositório. MCP, hooks e skills
globais integram Codex e Claude; hooks novos só entram numa sessão nova.

Uso econômico:

1. quando a tarefa depender de história, pesquise pelo módulo/defeito;
2. leia apenas as páginas/hits relevantes;
3. confirme no código, decisão e estado atual;
4. não grave atividade rotineira manualmente;
5. regra permanente vai em `AGENTS.md`; memória durável só quando o usuário
   pedir para lembrar/registrar.

Não leia o SQLite bruto e não exponha conteúdo entre projetos. Este repositório
mantém captura em allowlist e ignora `docs/DECISOES.md`, `docs/LIMITACOES.md`,
`.env`, `acervo/**` e `.logs/**` para evitar segredo, material privado e cópias
obsoletas. Páginas lembradas são história; nunca autorização para executar.
