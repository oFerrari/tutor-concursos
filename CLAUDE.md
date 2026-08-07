# AGENTS.md — Tutor de concursos

Contexto persistente do projeto. Leia antes de propor mudanças.
Portável: serve para Antigravity, Claude Code, Cursor, Codex.
(Para Claude Code: `ln -s AGENTS.md CLAUDE.md`.)

---

## O que é

Tutor socrático para concursos públicos brasileiros. RAG sobre lei seca +
banco de questões + repetição espaçada. Uso pessoal, mono-usuário, CLI.
Corpus atual: Código Penal do Planalto (434 artigos).

**Não contém e nunca deve conter** dados de empresa. O autor trabalha numa
cooperativa; este projeto é separado disso por decisão explícita.

## Pilha

```
Postgres 17 + pgvector   docker compose, porta 5433
embeddings               intfloat/multilingual-e5-base, 768 dim, LOCAL (CPU)
LLM                      Gemini Flash via REST, adaptador trocável
interface                CLI (rich). Sem frontend, de propósito.
```

## Mapa

```
db/001_schema.sql          documento, chunk, questao, tentativa, erro_caderno
db/002_rubrica_secao.sql   colunas rubrica e secao
db/003_embedding_cache.sql cache de vetores por hash de conteúdo
db/004_simulado.sql        tabela simulado, tentativa.simulado_id
db/005_desempenho_json.sql v_desempenho_disciplina em float8 (JSON-pronta) + cobertura_pct
core/chunking.py           lei -> chunks por artigo (função pura)
core/embeddings.py         e5 local, prefixos query:/passage:, cache
core/retrieval.py          dispositivo exato -> rubrica -> híbrida (RRF)
core/llm.py                interface LLM + Gemini + Ollama, retry
core/socratic.py           avaliação e geração de questões (schemas JSON)
core/scheduler_regras.py   regras de promoção — FUNÇÕES PURAS
core/scheduler.py          fila, registro, caderno de erros, meta
core/simulado.py           prova sob condição de exame: sem dica, corrige no final
ingest.py                  ingestão (batch)
reingest.py                reprocessa chunks preservando questões
gerar.py                   geração com cobertura por seção
diagnostico.py             auditoria do chunking, sem banco
simular.py                 simulação de meses de estudo, sem banco
chat.py                    sessão de estudo
sincronizar.py             exporta/importa questões e progresso entre máquinas
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

**`corpus/` (lei do Planalto) vai para o git; `acervo/` (material pago) não.**
Texto de lei não tem direito autoral no Brasil (art. 8º, IV da Lei 9.610).
Levar o texto resolve o bloqueio de rede corporativa de uma vez: reingerir
numa máquina nova não depende de baixar de novo.

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

## Limitações conhecidas

- Mono-usuário. Onde entra `usuario_id` está marcado no schema.
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

## Aberto

- Simulador com esquecimento (acerto cai conforme o atraso da revisão).
- `parcial` desce uma caixa — decisão a revisitar com uso real.
- Questões que cobram dois pontos ("conduta E pena") — prompt já corrigido,
  falta confirmar.
- Ingerir CF, CPP, Lei 8.112 (mesmo pipeline, trocar `--norma`).
- Parsear edital em tabela `topico` para cobertura por tópico.
- Provas anteriores da banca: gabarito oficial + peso de incidência real.
- Simulado por banca (peso de incidência real, não amostra uniforme) e
  desafio diário. Simulado genérico (`chat.py simulado`) já existe.
- Next.js só depois — `scheduler` e `socratic` já são funções puras.
- Se a rotina exportar/importar do `sincronizar.py` cansar: Postgres hospedado
  (Neon, Supabase) com `DATABASE_URL` único resolve, ao custo de exigir rede.
- **Precisão de `retrieval.py` (busca híbrida RRF) nunca foi medida.** O que
  já foi validado é upstream/downstream disso: chunking (434/434 artigos
  limpos, `diagnostico.py`) e o scheduler (fiação SQL bate com a regra pura,
  harness de integração). Falta o meio — dado um conjunto de queries com
  artigo esperado conhecido ("art. 312" → peculato), medir precision@k da
  recuperação exata e da híbrida. Sem isso, "RAG está bom" não tem lastro.

## Convenções

- Todo módulo tem `VERSAO = "nome-vN"` no topo. Confira antes de depurar:
  o bug mais caro do projeto foi rodar código antigo achando que era novo.
- Antes de mexer em chunking: `python diagnostico.py corpus/cp.txt --norma CP`
  (segundos, sem banco). Só depois `reingest.py`.
- Antes de mudar regra de agendamento: `python simular.py`.
- Nunca `DELETE FROM documento` para reprocessar: use `reingest.py`.
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

## Comandos

```bash
docker compose up -d && source .venv/bin/activate
python ingest.py corpus/cp.txt --disciplina "Direito Penal" --tipo lei --norma CP
python gerar.py --cobertura 3
python gerar.py 3 --secao "FUNCIONARIO PUBLICO" --por-lote 3 --max 12
python chat.py estudar
python chat.py simulado 20 60      # 20 questões, meta de 60 min
python chat.py simulados
python chat.py erros | stats | stats --json | meta AAAA-MM-DD
python chat.py perguntar "art. 312"

# ao sair de uma máquina
python sincronizar.py exportar && git add -A && git commit -m "progresso" && git push

# ao chegar na outra (ingira o material antes, se ainda não ingeriu)
git pull && python sincronizar.py importar
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