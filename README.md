# tutor-ai — monorepo

Tutor socrático para concursos públicos brasileiros. RAG sobre lei seca,
banco de questões, repetição espaçada, simulados, multiusuário.

```
apps/
  api/          backend (Python) — core/, chat.py (CLI), api.py (FastAPI).
                Ver apps/api/README.md pra subir e usar.
  web/          Next.js — ainda não existe. Vem quando houver frontend de
                verdade pra escrever, não antes.
  mobile/       React Native/Expo ou Flutter — futuro, mesma lógica.

packages/       código compartilhado entre apps (SDK da API, prompts,
                tipos). Vazio hoje — entra quando houver algo real pra
                compartilhar, não como esqueleto.

docker-compose.yml   Postgres 17 + pgvector — infra compartilhada, roda
                     da raiz (o volume de dados de apps/api/db aponta
                     pra lá).
turbo.json           orquestra tasks entre apps/packages (Turborepo).
```

## Onde está cada coisa

- **Regras de negócio, decisões de arquitetura, corpus, banco de dados**:
  tudo isso é do backend — `apps/api/README.md` e, mais detalhado,
  `CLAUDE.md` (nesta raiz; os caminhos ali são relativos a `apps/api/`).
- **Subir o banco**: `docker compose up -d` (desta raiz).
- **Rodar o backend**: `cd apps/api && ...` — ver `apps/api/README.md`.
- **Frontend**: ainda não escrito.

## Por que monorepo já, sem frontend ainda

`apps/web` e `apps/mobile` vão precisar consumir a mesma API — decidir a
estrutura agora (Turborepo, `apps/`/`packages/`) evita reorganizar tudo
quando o primeiro frontend chegar. O que NÃO faz sentido ainda é criar
código dentro dessas pastas: pasta vazia com README genérico é dívida
técnica disfarçada de organização. Elas entram no repositório no commit
em que tiverem conteúdo real.
