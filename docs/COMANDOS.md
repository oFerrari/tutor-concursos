# Comandos — catálogo completo

Saiu do `CLAUDE.md` porque aquele arquivo entra em TODO prompt e isto aqui é
consulta, não contexto. Os do dia a dia continuam lá; o resto é isto.

Tudo relativo a `apps/api/` (`source ativar.sh`), exceto `docker compose` e os
scripts da raiz.


```bash
# CAMINHO NORMAL — de qualquer pasta do repo, sobe banco, schema, API e front:
./setup.sh                    # máquina nova ou depois de pull que mexeu em dependência
./setup.sh --subir            # dia a dia: confere o schema e sobe os dois
./setup.sh --parar            # derruba API e front (o banco fica)

# QUALIDADE DA RESPOSTA do tutor (não "o código quebrou?" — isso é o pytest):
./testar.sh                      # aluno sintético + juiz; mostra o que virou vetor
./testar.sh --livre --persona cético --turnos 8   # o aluno também é um LLM
./testar.sh --falas "oi" "me explica peculato"    # suas falas
./testar.sh --rapido             # sem o juiz (uma chamada de LLM a menos)
./testar.sh --pytest             # a suíte ANTES da avaliação · --so-pytest: só ela
./testar.sh --cenario listar     # os 11 cenários, um por risco
./testar.sh --cenario forense_do_zero --mesa "PC-PR Investigador"
./testar.sh --cenario direto     # roda um só · --cenario todos: a coleção inteira
./testar.sh --reprocessar        # re-checa TODAS as conversas gravadas (grátis)
./testar.sh --cenario todos      # a bateria inteira: 10 cenários, ~53 chamadas
./testar.sh --placar             # histórico de notas, sem gastar LLM
./testar.sh --limpar             # apaga a conta descartável
# havendo defeito, sai .logs/defeitos.md (nome FIXO) só com o que falhou, e a
# frase pra entregar a um agente: "conserta os defeitos em .logs/defeitos.md"
# com o juiz, a rodada entra em .logs/placar.jsonl com a nota de naturalidade

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
python edital.py corpus/edital.pdf --mesa "X" --email teste@local # conta descartável, pra experimentar
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

# backend na nuvem (frontend na Vercel): prepara e VERIFICA tudo o que não
# exige credencial; para no login dizendo o comando que falta
export DATABASE_URL='postgresql://...'   # Postgres com pgvector (Neon/Supabase)
./subir-vercel.sh                        # imagem + pgvector + schema + corpus
./subir-vercel.sh --tunel                # atalho de DEV: expõe esta máquina
./subir-vercel.sh --status               # o que está de pé, aqui e lá
API_PUBLICA=https://sua-api ./subir-vercel.sh --status

# TROCAR DE MÁQUINA — um comando de cada lado (de qualquer pasta do repo)
./sincronizar.sh --sair       # na que você deixa: manda estado (e pergunta do código)
./sincronizar.sh              # na que você senta: pull + schema + estado + relatório
./sincronizar.sh --subir      # o mesmo, e ainda sobe API e frontend
./sincronizar.sh --status     # o que está fora de sincronia, sem tocar em nada

# as peças, se quiser rodar isolado
python sincronizar.py exportar        # o pacote, do banco pro dados/progresso.json
python sincronizar.py importar        # o pacote pro banco (união, idempotente)
python sincronizar.py estado          # o que tem no banco e no arquivo, sem escrever

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
# o arquivo ORIGINAL de volta (024) — 404 pra material de outro dono ou anterior à migração
curl -s -OJ localhost:8000/materiais/12/arquivo -H "Authorization: Bearer $TOKEN"
# disciplina e assunto são OPCIONAIS — sem eles, o classificador descobre
curl -s -X POST localhost:8000/materiais -H "Authorization: Bearer $TOKEN" \
     -F "arquivo=@aula-03.pdf" -F "tipo=aula"
curl -s -X POST localhost:8000/materiais/link -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"url":"https://exemplo.org/lei.pdf"}'
# o que alimenta o seletor da tela: só os rótulos DESTE aluno
curl -s localhost:8000/materiais/sugestoes -H "Authorization: Bearer $TOKEN"

# o que o aluno CONFUNDE (022) — agregado do conceito_faltante das tentativas
curl -s localhost:8000/conceitos -H "Authorization: Bearer $TOKEN"

# renomear a matéria de TODO o material dela (o mesmo assunto cai com nomes
# diferentes de edital pra edital) — reindexa, porque o rótulo entra na busca (025)
curl -s -X PATCH localhost:8000/materiais/disciplina -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' \
     -d '{"de":"Criminalística","para":"Ciências Forenses"}'
# o PDF ABERTO na tela (inline) em vez de baixado; ?baixar=1 força o download
curl -s localhost:8000/materiais/12/arquivo -H "Authorization: Bearer $TOKEN"

# editar o alvo DEPOIS de o edital estar valendo, sem subir o PDF de novo
curl -s -X PATCH localhost:8000/edital/disciplinas -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"remover":["Contabilidade"]}'
curl -s -X PATCH localhost:8000/edital/data-prova -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"data_prova":"2026-11-15"}'
```

## Bateria de conversa sobre material real (sem gravar nada)

```bash
python bateria_conversa.py cenarios/leitura_e_sem_material.json --email voce@x
```

Roda os cenários (fala + expectativa: `"sem"`, `"ler:<disciplina>"`, `"busca"`)
com o modelo real sobre a biblioteca e o edital da conta, e marca ✗ o que falhar.
Não grava conversa, mensagem nem diário. Uma chamada ao modelo por turno. Sai com
código 1 se houver falha.


## Bateria de descoberta (antes de funcionalidade nova)

```bash
python bateria_decisoes.py                  # PASSO 1, cota zero: falas reais pela lógica de decisão -> .logs/decisoes.md
python roteiro_modelo.py                    # PASSO 2, ~17 chamadas: falas fixas, sem juiz, LEIA .logs/roteiro.md
./testar.sh --descobrir                      # caro (centenas de chamadas): falas reais + 5 conversas simuladas + contradições
./testar.sh --descobrir --so contradicoes    # só prompt e decisões (poucas chamadas)
./testar.sh --descobrir --so reais           # só as falas reais
./testar.sh --descobrir --episodios 10 --turnos 8
```

Conta descartável (`cenarios/descoberta.json`), apagada no fim junto com toda
questão pública que a rodada gerar. Relatório em `.logs/descoberta.md` (a ausência
dele é o limpo) e as conversas inteiras em `.logs/descoberta-conversas.md`, para
LER. Diante de 503 ela espera um minuto e repete; cota DO DIA esgotada interrompe na hora, e a rodada sai marcada INCOMPLETA. Orçamento de 150 chamadas por rodada (`DESCOBERTA_ORCAMENTO`): a cota gratuita do modelo do tutor é 500 por dia, e o app precisa do resto. O revisor é
`LLM_REVISOR` (padrão `gemini-3.5-flash`). Com mais de uma conta real no banco,
`--conta-id` diz de quem são as falas.

## Índice de assuntos (036)

```bash
python -m core.indice            # indexa com o modelo os materiais pendentes ou em reserva, no orçamento do dia
```

Roda sozinho ao fim de cada indexação de material. `LLM_INDICE` escolhe o modelo,
que nunca é o do tutor, e `INDICE_ORCAMENTO_DIA` (150) limita as chamadas por dia.

## Questões de prova (037)

```bash
python -m core.prova             # reimporta os simulados com questão sem gabarito (gabarito chegou, ou há cota para o tutor resolver)
```

Roda sozinho ao fim da indexação de todo material do tipo "Simulado / questões".
