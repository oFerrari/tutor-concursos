# AGENTS.md — Tutor de concursos

Contexto persistente do projeto. Leia antes de propor mudanças.
Portável: serve para Antigravity, Claude Code, Cursor, Codex.
(Para Claude Code: `ln -s AGENTS.md CLAUDE.md`.)

**Monorepo.** Este arquivo fica na raiz (é onde as ferramentas de IA
procuram por padrão), mas TODO caminho e comando abaixo — `core/`, `db/`,
`chat.py`, `corpus/`, `.env` — é relativo a `apps/api/`, que é onde mora o
backend inteiro. `cd apps/api` antes de rodar qualquer coisa deste
documento, exceto `docker compose` (lê `docker-compose.yml` da raiz).
Atalho: `source ativar.sh` na raiz faz esse `cd` e ativa o venv; `./tutor
<comando>` roda um comando só no venv certo, de onde você estiver.
Ver `README.md` (raiz) para a estrutura do monorepo (`apps/`, `packages/`).

---

## O que é

Tutor socrático para concursos públicos brasileiros. RAG sobre lei seca +
banco de questões + repetição espaçada. Multiusuário desde a migração 008
(ver `docs/DECISOES.md`); CLI própria (`chat.py`) e API HTTP (`api.py`) sobre a MESMA
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
db/023_migracao.sql        livro-razão: quais migrações já rodaram NESTE banco
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
migrar.py                  aplica as migrações de db/ que faltam (único mecanismo)
atualizar.sh               instala arquivos baixados do chat
```
## Onde está o resto

Este arquivo é o MAPA (o que existe, como rodar, o que não pode quebrar). O
histórico do projeto mora em `docs/`, e vale mais que qualquer resumo dele:

- **`docs/DECISOES.md`** — por que cada coisa é como é, e as armadilhas que já
  custaram tempo (corpus do Planalto, método, extração de edital). **Leia a
  seção correspondente antes de mexer na área**, principalmente em:
  chunking/retrieval, scheduler, prompt do tutor, geração de questão, mesa,
  migração, auth, extração de edital, biblioteca do aluno.
- **`docs/LIMITACOES.md`** — o que o sistema não faz (e por quê) e o que está
  em aberto. Várias "melhorias óbvias" já foram tentadas, medidas e revertidas;
  está lá.

Regra que vale pros dois: decisão registrada com MEDIÇÃO só se derruba com
outra medição, não com opinião.

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
- **Comando do backend de qualquer pasta: `source ativar.sh` (ativa o venv e te
  põe em `apps/api`) ou `./tutor migrar.py --listar` (roda um só, sem mudar o
  shell).** O venv mora em `apps/api/.venv` porque o backend inteiro mora lá, e
  errar isso não dá erro claro — dá `No module named 'psycopg'` ou `python:
  command not found`, que parece defeito do projeto e é caminho errado.
- **`python migrar.py` aplica migração; commitar não aplica** (migração 023).
  Era este o buraco: `git pull` traz os ARQUIVOS e não aplica nenhum, o
  `docker-entrypoint-initdb.d` só roda em volume NOVO, e nada no banco
  registrava o que já tinha rodado. O modo de falha é o pior que existe — a
  aplicação SOBE e quebra depois, num lugar sem relação óbvia com o schema.
  Custou o módulo de Simulados/Estatísticas inteiro rodando contra a
  view/tabela antiga sem avisar (`chat.py simulado` batendo em tabela
  inexistente, `stats --json` devolvendo `Decimal` que quebra `json.dumps`)
  até alguém tentar de verdade. `./setup.sh` chama o `migrar.py` antes do
  corpus, então "cheguei na outra máquina" voltou a ser um comando.
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
- **Migração numerada nova entra com `python migrar.py`** (023). Da 012 à 022
  todas foram aplicadas na mão, na era anterior a isso — o livro-razão deste
  banco foi preenchido de uma vez com `migrar.py --adotar`. Banco de máquina
  nova recebe as 25 em ordem, sozinho.

## Comandos

```bash
# CAMINHO NORMAL — de qualquer pasta do repo, sobe banco, schema, API e front:
./setup.sh                    # máquina nova ou depois de pull que mexeu em dependência
./setup.sh --subir            # dia a dia: confere o schema e sobe os dois
./setup.sh --parar            # derruba API e front (o banco fica)

# ambiente, de qualquer pasta do repo
source ativar.sh              # ativa o venv e te deixa em apps/api
./tutor migrar.py --listar    # roda UM comando no venv certo, sem mudar o shell

# schema, se quiser rodar isolado
cd apps/api && python migrar.py            # aplica o que falta (mede o banco da
                                           # era pré-023 e aplica só o que falta)
python migrar.py --listar                  # estado, sem tocar em nada
python migrar.py --adotar                  # banco JÁ em dia: registra sem executar

# à mão, se preferir
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
