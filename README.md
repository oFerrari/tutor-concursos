# Tutor de concursos — MVP

Tutor socrático com acervo próprio, revisão espaçada e caderno de erros.
Postgres único (pgvector + full-text português), embeddings locais, LLM trocável.

## Subir em 5 passos

```bash
# 1. banco
docker compose up -d          # Postgres 17 + pgvector na porta 5433
docker compose logs -f db     # espere "database system is ready"

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
| `python chat.py perguntar "..."` | pergunta livre ancorada no acervo |
| `python chat.py erros` | caderno de erros por reincidência |
| `python chat.py stats` | % de acerto por disciplina |
| `python chat.py meta 2026-11-15` | dias restantes, cobertura, ritmo necessário |

## Mapa do código

```
db/001_schema.sql     schema; leia os comentários, as decisões estão lá
core/config.py        env + INTERVALOS da revisão espaçada
core/db.py            conexão única, pgvector registrado
core/embeddings.py    e5 local; prefixos query:/passage: encapsulados
core/chunking.py      lei por dispositivo · aula por janela deslizante
core/retrieval.py     citação exata → híbrida (RRF de vetor + tsvector)
core/llm.py           interface LLM + adaptadores Gemini e Ollama
core/socratic.py      avaliação e geração; retenção do gabarito em código
core/scheduler.py     promoção de caixa, caderno de erros, meta
ingest.py             worker de ingestão (batch)
chat.py               sessão de estudo (CLI)
```

## Trocar o LLM

`LLM_PROVIDER=ollama` no `.env`. Nenhuma outra linha muda — é para isso que
existe `core/llm.py`. Para Claude ou OpenAI, escreva uma classe nova com o
método `gerar` e registre no dict de `llm.obter()`.

## Limites conhecidos

- Mono-usuário. Onde entra `usuario_id` está marcado `-- MULTIUSUARIO` no schema.
- PDF escaneado não funciona sem OCR (`ocrmypdf entrada.pdf saida.pdf`).
- Camada gratuita do Gemini: cota diária limitada e prompts podem ser usados
  para treinamento. Não sirva conteúdo sensível por esse caminho.
- Trocar o modelo de embeddings exige `ALTER TABLE chunk` (dimensão do vetor)
  e reindexar tudo.

## Roteiro

- **Semana 1 (feito)** — schema, ingestão, busca híbrida, tutor socrático no CLI.
- **Semana 2** — gerador de simulado por banca; `GET /api` expondo `scheduler` e
  `socratic` como funções HTTP.
- **Semana 3** — Next.js: fila do dia, sessão de estudo, caderno de erros.
- **Semana 4** — dashboard de estatísticas e desafio diário.
