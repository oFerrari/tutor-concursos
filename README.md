# tutor-ai — monorepo

Tutor socrático para concursos públicos brasileiros. RAG sobre lei seca,
banco de questões, repetição espaçada, simulados, multiusuário.

```
apps/
  api/          backend (Python) — core/, chat.py (CLI), api.py (FastAPI).
                Ver apps/api/README.md pra subir e usar.
  web/          Next.js — 11 rotas (login, fila, responder, simulado,
                desafio, stats, erros, perguntar, meta). Consome apps/api.
  mobile/       React Native/Expo ou Flutter — futuro, mesma lógica.

packages/       código compartilhado entre apps (SDK da API, prompts,
                tipos). Vazio hoje — entra quando houver algo real pra
                compartilhar, não como esqueleto.

docker-compose.yml   Postgres 17 + pgvector — infra compartilhada, roda
                     da raiz (o volume de dados de apps/api/db aponta
                     pra lá).
turbo.json           orquestra tasks entre apps/packages (Turborepo, yarn).
```

## Onde está cada coisa

- **Regras de negócio, decisões de arquitetura, corpus, banco de dados**:
  tudo isso é do backend — `apps/api/README.md` e, mais detalhado,
  `CLAUDE.md` (nesta raiz; os caminhos ali são relativos a `apps/api/`).
- **Subir o banco**: `docker compose up -d` (desta raiz).
- **Rodar o backend**: `cd apps/api && ...` — ver `apps/api/README.md`.
- **Rodar o frontend**: `cd apps/web && yarn dev`.

## Continuar em outra máquina (git pull + retomar de onde parou)

O que viaja pelo git e o que não viaja é uma decisão deliberada (documentada
em `CLAUDE.md`, seção "Sincronização entre máquinas"): código e o **texto**
da lei vão; **chunks/embeddings** não vão (derivam do texto, CPU local, sem
custo); **questões geradas por LLM e o progresso pessoal** vão, mas por um
canal separado (`sincronizar.py`), não automaticamente com o `git pull`.

```bash
git pull

# 1. banco
docker compose up -d

# 2. backend — .venv nunca vai pro git, recria toda vez que troca de máquina
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # cole GEMINI_API_KEY; gere JWT_SECRET:
#   python -c "import secrets; print(secrets.token_hex(32))"

# 3. reingerir o texto (corpus/ já veio pelo git — isso é rápido, só CPU,
#    sem custo de LLM; repita pra cada norma que já tiver corpus/*.txt)
python ingest.py corpus/cp.txt  --disciplina "Direito Penal"          --tipo lei --norma CP
python ingest.py corpus/cf.txt  --disciplina "Direito Constitucional" --tipo lei --norma CF
python ingest.py corpus/adct.txt --disciplina "Direito Constitucional" --tipo lei --norma ADCT --titulo ADCT
python ingest.py corpus/CF88_Livro_EC91_2016.pdf --disciplina "Direito Constitucional" --tipo historico

# 4. trazer as questões geradas e o progresso — isso SIM veio pelo git
python sincronizar.py importar

# 5. frontend (yarn na raiz do workspace, não dentro de apps/web)
cd ../.. && yarn install
cp apps/web/.env.local.example apps/web/.env.local
```

**Antes de sair de uma máquina**, sempre: `cd apps/api && python sincronizar.py exportar`,
depois `git add -A && git commit && git push` — sem isso, a próxima
exportação (de qualquer lado) sobrescreve o que ficou de fora.

## Por que monorepo desde o início, mesmo sem frontend no primeiro commit

`apps/web` e `apps/mobile` iam precisar consumir a mesma API — decidir a
estrutura antes (Turborepo, `apps/`/`packages/`) evitou reorganizar tudo
quando o frontend chegou. O que não fazia sentido era criar código dentro
de pastas vazias antes de ter algo real pra colocar lá — `apps/web` só
entrou no repositório no commit em que teve conteúdo de verdade.
