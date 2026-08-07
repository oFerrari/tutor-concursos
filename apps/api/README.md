# apps/api — backend do Tutor de concursos

Tutor socrático com acervo próprio, revisão espaçada e caderno de erros.
Postgres único (pgvector + full-text português), embeddings locais, LLM trocável.
Multiusuário: acervo compartilhado, progresso pessoal. CLI (`chat.py`) e API
HTTP (`api.py`) sobre a mesma lógica — Next.js consumindo a API é o próximo passo.

Parte do monorepo — ver `../../README.md` pra visão geral da estrutura.
Todos os comandos abaixo assumem `cd apps/api` primeiro (exceto o `docker
compose`, que lê `docker-compose.yml` da raiz do monorepo).

## Subir em 5 passos

```bash
# 1. banco (da RAIZ do monorepo, não daqui)
cd ../.. && docker compose up -d     # Postgres 17 + pgvector na porta 5433
docker compose logs -f db            # espere "database system is ready"
cd apps/api

# 2. dependências
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. configuração
cp .env.example .env
# edite .env e cole a GEMINI_API_KEY (aistudio.google.com/apikey)

# 4. ingerir material
mkdir -p acervo
python ingest.py acervo/cp.pdf --disciplina "Direito Penal" --tipo lei --norma CP --gerar 10

# 5. estudar
python chat.py estudar
```

A primeira execução baixa o modelo de embeddings (~1 GB). Depois roda offline.

## Comandos

| comando | o que faz |
|---|---|
| `python ingest.py ARQ --disciplina D --tipo lei --norma CP` | indexa lei por artigo |
| `python ingest.py ARQ --disciplina D --tipo aula --gerar 8` | indexa aula e gera 8 questões |
| `python chat.py estudar` | fila de revisão do dia, modo socrático |
| `python chat.py desafio` | meta do dia: pontos fracos + novas + mini-simulado, tempo estimado |
| `python chat.py simulado 20 60` | prova de 20 questões, sem dica, corrige no final |
| `python chat.py simulados` | histórico de simulados feitos |
| `python chat.py perguntar "..."` | pergunta livre ancorada no acervo |
| `python chat.py erros` | caderno de erros por reincidência |
| `python chat.py stats` | % de acerto e cobertura por disciplina, com barra no terminal |
| `python chat.py stats --json` | mesmo dado, formato pronto pra um futuro endpoint consumir |
| `python edital.py ARQ.pdf --orgao O --banca B` | extrai data da prova + conteúdo programático de um edital |
| `python chat.py meta` | dias restantes, cobertura, probabilidade de fechamento — usa o edital ingerido |
| `python chat.py meta 2026-11-15` | mesma coisa, com data manual (sempre vence a do edital) |
| `uvicorn api:app --reload --port 8000` | API HTTP — mesma lógica, autenticada por JWT |

## Mapa do código

```
db/001_schema.sql     schema; leia os comentários, as decisões estão lá
db/008_usuario.sql    usuario, progresso — acervo compartilhado, progresso pessoal
core/config.py        env + INTERVALOS da revisão espaçada
core/db.py            conexão única, pgvector registrado
core/embeddings.py    e5 local; prefixos query:/passage: encapsulados
core/chunking.py      lei por dispositivo · aula por janela deslizante
core/retrieval.py     citação exata → híbrida (RRF de vetor + tsvector)
core/llm.py           interface LLM + adaptadores Gemini e Ollama
core/socratic.py      avaliação e geração; retenção do gabarito em código
core/auth.py          hash de senha (bcrypt), token de sessão (JWT)
core/scheduler.py     promoção de caixa, caderno de erros, meta — por usuario_id
core/simulado.py      prova sob condição de exame: sem dica, corrige no final
core/desafio.py       meta do dia: reincidentes + novas + mini-simulado
core/edital.py        extrai data da prova e conteúdo programático de PDF de edital
ingest.py             worker de ingestão (batch)
chat.py               sessão de estudo (CLI, um usuário fixo por email)
api.py                API HTTP (FastAPI) — pronta pra um frontend consumir
```

## Trocar o LLM

`LLM_PROVIDER=ollama` no `.env`. Nenhuma outra linha muda — é para isso que
existe `core/llm.py`. Para Claude ou OpenAI, escreva uma classe nova com o
método `gerar` e registre no dict de `llm.obter()`.

## Limites conhecidos

- Multiusuário desde a migração 008; `sincronizar.py` continua pensado pra
  alternância de UM usuário entre duas máquinas, não pra distribuir contas.
- JWT sem revogação: token vazado vale até expirar (uma semana).
- PDF escaneado não funciona sem OCR (`ocrmypdf entrada.pdf saida.pdf`).
- Camada gratuita do Gemini: cota diária limitada e prompts podem ser usados
  para treinamento. Não sirva conteúdo sensível por esse caminho.
- Trocar o modelo de embeddings exige `ALTER TABLE chunk` (dimensão do vetor)
  e reindexar tudo.

## Roteiro

- **Feito** — schema, ingestão, busca híbrida, tutor socrático, revisão
  espaçada, simulados, desafio diário, edital real, multiusuário, API HTTP.
- **Próximo** — Next.js consumindo `api.py`: fila do dia, sessão de estudo,
  simulado, caderno de erros, dashboard de estatísticas.
