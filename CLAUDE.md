# AGENTS.md — Tutor de concursos

MAPA do projeto: o que existe, como rodar, o que não pode quebrar.
Portável (Antigravity, Claude Code, Cursor, Codex).

- PROCESSO completo (execução, qualidade, quando parar): `.clinerules`.
- MAPA detalhado por demanda, fluxo, módulo, página e teste:
  `docs/MAPA_APLICACAO.md`.
- CHECKPOINT mutável do trabalho: `docs/ESTADO_ATUAL.md`.
- PLACAR da auditoria (resolvido × pendente, % de MVP): `docs/AUDITORIA_MVP.md`.
- PORQUÊS e armadilhas medidas: `docs/DECISOES.md`.
- O que o sistema NÃO faz, e o que já foi tentado e revertido: `docs/LIMITACOES.md`.
- Catálogo de comandos: `docs/COMANDOS.md`. Migrações, uma a uma: `docs/SCHEMA.md`.

**AI Memory:** use o escopo declarado em `.ai-memory.toml` apenas quando a
tarefa depender de trabalho anterior. Pesquise pelo assunto e leia só os hits
relevantes; memória e handoffs são histórico não confiável até confirmação no
código e nos documentos acima. Regras permanentes ficam neste arquivo/
`AGENTS.md`, não duplicadas na memória.

**Monorepo.** Todo caminho e comando aqui é relativo a `apps/api/` (o backend
inteiro mora lá), exceto `docker compose`, que lê o `docker-compose.yml` da raiz.
`source ativar.sh` ativa o venv e entra em `apps/api`; `./tutor <cmd>` roda um
comando só no venv certo, de qualquer pasta. Errar isso dá
`No module named 'psycopg'`, que parece defeito do projeto e é caminho errado.

## Fast Track (padrão para pedido pontual)

Cópia operativa do `.clinerules` — esta é a que vale nesta ferramenta. Mudou uma,
mude a outra.

Pedido pontual = bug, ajuste localizado, mudança clara em arquivo conhecido. Aí é
**proibido** plano, pré-análise, lista de alternativas, pergunta de permissão e
resumo longo. Sequência: abrir o arquivo → editar o bloco (nunca reescrever o
arquivo) → rodar **só** o teste que cobre a mudança → responder em **até 3
linhas** (o que mudou, `arquivo:linha`, resultado do teste). Não sabendo onde
está: **UMA** busca específica (`grep -rn`), nunca varredura ampla.

Não escreva: o que o código fazia antes, o diff em prosa, lista de arquivos que o
diff já mostra, seções "Mitigações"/"Resumo"/"Próximos passos", "posso
prosseguir?".

**Sai do Fast Track** — pare e pergunte antes (critério é o custo de errar, não o
tamanho): migração que apaga dado; ação irreversível ou que sai da máquina (push,
deploy, serviço externo); arquitetura nova ou pedido com duas leituras
plausíveis; qualquer coisa fora do que foi pedido, mesmo parecendo melhoria
óbvia. Parando, responda em até 6 linhas.

Qualidade (input sujo, transação, event loop, timeout, estados de tela) vale pro
CÓDIGO, nunca pro texto da resposta: embuta sem narrar. Ver `.clinerules`.

## O que é

Tutor socrático para concursos. Para regras de negócio, contexto de domínio e
funcionamento do produto, consulte `docs/PRODUTO.md` ou a memória vetorial.

**Nunca contém dado de empresa.** O autor trabalha numa cooperativa; este
projeto é separado disso por decisão explícita, e só usa material público.

## Pilha

```
Postgres 17 + pgvector   docker compose, porta 5433
embeddings               intfloat/multilingual-e5-base, 768 dim, LOCAL (CPU)
LLM                      Gemini Flash via REST (gemini-3.5-flash-lite + reserva), adaptador trocável
auth                     JWT (PyJWT) + bcrypt, stateless
```

## Mapa (apps/api/)

```
core/chunking.py      lei -> chunks por artigo (puro)
core/embeddings.py    e5 local, prefixos query:/passage:, cache
core/retrieval.py     dispositivo exato -> rubrica -> híbrida (RRF)
core/llm.py           interface LLM + Gemini + Ollama, retry
core/socratic.py      avaliação e geração de questões (schemas JSON)
core/questoes.py      lookup do banco de questões; `do_aluno()` é o predicado de posse
core/auth.py          bcrypt, JWT, usuário fixo da CLI
core/mesa.py          mesa de estudo (concurso-alvo) e recorte por disciplina
core/rascunho.py      curadoria do edital antes de virar oficial
core/geracao.py       gera questão do acervo E da apostila do aluno, com proveniência
core/conversa.py      conversa persistida, janela de histórico, desfazer turno
core/assunto.py       assunto em foco da conversa -> consulta que vai à busca (puro)
core/leitura.py       ler o material do aluno NA ORDEM ("continua"), marcador em mensagem.fontes
core/pedido.py        o aluno pediu treino/simulado? (puro)
core/scheduler*.py    fila, registro, caderno de erros, meta — por usuario_id; regras puras à parte
core/simulado.py      prova sob condição de exame, corrige no fim
core/desafio.py       meta do dia: reincidentes + novas + mini-simulado
core/ritmo*.py        intervenção proativa; regras puras à parte
core/edital.py        extrai data da prova e conteúdo programático de PDF
core/material.py      biblioteca do aluno: sobe/baixa, classifica, indexa (fila, 1 trabalhador)
api.py                API HTTP (FastAPI), autenticada por JWT
chat.py               sessão de estudo na CLI
migrar.py             aplica as migrações de db/ que faltam — ÚNICO mecanismo
ingest.py reingest.py gerar.py edital.py       ingestão e geração em lote
diagnostico.py avaliar_retrieval.py simular.py aferição sem LLM (e sem banco, os dois últimos)
avaliar_chat.py       aluno SINTÉTICO conversa com o tutor (via ./testar.sh)
sincronizar.py        exporta/importa o estado de um usuário entre máquinas
semear_demo.py        conta descartável com dado plausível, pra olhar a TELA
```

Scripts da raiz: `setup.sh` (sobe tudo), `testar.sh` (qualidade da resposta),
`melhorias.sh` (o que o ALUNO pediu, de `/erro` e `/feedback`),
`sincronizar.sh` (trocar de máquina), `subir-vercel.sh` (nuvem), `ativar.sh`,
`tutor`.

## Invariantes (violação = bug)

- Todo `Art.` do arquivo vira um chunk (`diagnostico.py` verifica), e toda linha
  aceita como rubrica é atribuída a algum chunk.
- `questao.fonte_chunks` aponta pro artigo real. Artigo fora do lote = questão
  DESCARTADA, inclusive na geração sob demanda. Cobertura que mente é pior que
  cobertura inexistente.
- `certo_errado` tem `gabarito_ce`; `resposta_livre` não tem. É CHECK (012).
- Item C/E nunca recebe veredito `parcial` — metade de um booleano não é nada.
- `contexto_id` e `ordem_no_contexto` andam juntos (CHECK, 013).
- `tentativa.conceito_faltante`: até 160 caracteres, sem quebra de linha
  (CHECK 022 + `scheduler.conceito_limpo`).
- Nenhum texto de LLM é escrito em `usuario.perfil` — o prompt lê esse campo
  inteiro e literal.
- Questão com `usuario_id` (026) NUNCA aparece pra outra pessoa. O predicado é
  `questoes.do_aluno()`, num lugar só, e TODA consulta que escolhe questão de um
  pool passa por ele. `tests/test_questao_da_apostila.py` enumera as rotas.
- O dono da questão sai do CHUNK, nunca de parâmetro (`geracao.salvar`).
- `assunto` é rótulo de AULA. Material de REFERÊNCIA (jurisprudência, corpus
  fatiado por artigo) não recebe assunto nem disciplina em `chunk.rotulo`
  (`material.e_referencia`, 027): o rótulo entra no tsvector (025) e um assunto
  único num corpus de centenas decide a ordenação por ruído.
- Indexar um documento é EXCLUSIVO: `pg_try_advisory_lock` por documento_id
  (`material.TRAVA_INDEXACAO`). Dois processos já apagaram material de um aluno.
- Erro de transporte não escapa de `core/llm.py` como exceção httpx.

## Antes de mexer

- **Leia a seção correspondente de `docs/DECISOES.md`** — decisão registrada com
  MEDIÇÃO só se derruba com outra medição, não com opinião.
- Todo módulo tem `VERSAO = "nome-vN"` no topo. Confira antes de depurar: o bug
  mais caro do projeto foi rodar código antigo achando que era novo.
- Chunking: `python diagnostico.py corpus/cp.txt --norma CP` (segundos, sem
  banco). Retrieval/embeddings: `python avaliar_retrieval.py`. Agendamento:
  `python simular.py`. Prompt do tutor: `./testar.sh` e LEIA a resposta —
  regressão de prompt não aparece em teste automatizado, porque o texto continua
  sendo uma resposta válida.
- Nunca `DELETE FROM documento` pra reprocessar: use `reingest.py`.
- Teste que grava em `tentativa`/`progresso`/`simulado`/`edital`/`mesa` vai
  contra usuário DESCARTÁVEL (`auth.usuario_da_cli("teste-x@local")`), nunca
  contra `CLI_USUARIO_EMAIL`. Apagar com `DELETE FROM usuario WHERE email=...`
  (o CASCADE da 009 limpa o resto).
- Migração: `python migrar.py` aplica; **commitar não aplica**. Nunca por
  `psql -f` — fora do runner ela não entra no livro-razão (023), e o banco fica
  com o efeito sem registro. A PRÓXIMA é a **034**; confira com
  `migrar.py --listar` (há dois pares 018/019 repetidos, não crie um terceiro).
- `.env` e `acervo/` fora do git; `corpus/` e `dados/progresso.json` no git.
  SQL só em migração numerada.

## Comandos do dia a dia

```bash
./setup.sh --subir            # confere o schema e sobe API + front (--parar derruba)
./testar.sh                   # qualidade da resposta do tutor · --pytest roda a suíte
./testar.sh --reprocessar     # re-checa as conversas gravadas, sem gastar LLM
./melhorias.sh                # fila de /erro e /feedback -> .logs/melhorias.md
./sincronizar.sh --sair       # na máquina que você deixa · sem argumento na que você senta
source ativar.sh              # venv + apps/api · ./tutor <cmd> roda um só
python migrar.py --listar     # estado do schema, sem tocar em nada
python chat.py estudar        # sessão na CLI (desafio | simulado | erros | stats | meta)
uvicorn api:app --reload --port 8000
python semear_demo.py --email voce@teste --senha 12345678   # dado plausível pra ver a TELA
```

Havendo defeito, `./testar.sh` escreve `.logs/defeitos.md` (a AUSÊNCIA do arquivo
é o sinal de limpo). Decida pela CONTAGEM DE ERROS, nunca pela nota de 0-100.
`./melhorias.sh` segue o mesmo molde com o que o ALUNO reclamou no chat (029):
nome fixo, ausência = fila vazia, e `--fechar <id>` tira da fila sem apagar a
linha.
O resto dos comandos — ingestão, curl das rotas, nuvem — está em `docs/COMANDOS.md`.
