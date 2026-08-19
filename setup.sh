#!/usr/bin/env bash
# Sobe o projeto inteiro: banco, schema, dependências, corpus, API e frontend.
#
#   ./setup.sh                 prepara tudo e SOBE os dois serviços
#   ./setup.sh --subir         pula a preparação e só sobe (o dia a dia)
#   ./setup.sh --parar         derruba API e frontend (o banco fica de pé)
#   ./setup.sh --so-preparar   prepara e NÃO sobe nada
#
# Roda de QUALQUER pasta do repositório — inclusive de apps/api ou apps/web.
# Idempotente: rodar de novo não duplica nada (ingest.py pula arquivo já
# ingerido pelo hash; venv só é criado se não existir; migração só roda uma vez).
set -euo pipefail

# ---------------------------------------------------------------- onde estamos
# Antes isto era `cd "$(dirname "$0")"`, que só acerta quando você invoca o
# script pelo caminho dele. Quem está em apps/api e digita `../../setup.sh`
# funcionava por acaso; quem chama por um link simbólico, não. `git rev-parse`
# responde a pergunta certa — "qual é a raiz deste repositório?" — de onde
# quer que você esteja. O `dirname` fica como reserva pra cópia sem .git.
#
# Duas linhas e não uma: `A || B && C` agrupa como `(A || B) && C`, então a
# versão de uma linha rodava o `pwd` TAMBÉM quando o git acertava, e RAIZ vinha
# com dois caminhos. Peguei rodando, não lendo.
RAIZ=$(git rev-parse --show-toplevel 2>/dev/null) \
  || RAIZ=$(cd "$(dirname "$0")" && pwd)
cd "$RAIZ"

LOGS="$RAIZ/.logs"
mkdir -p "$LOGS"
PID_API="$LOGS/api.pid"
PID_WEB="$LOGS/web.pid"

vivo() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

parar() {
  for par in "API:$PID_API" "frontend:$PID_WEB"; do
    nome=${par%%:*}; arq=${par#*:}
    if vivo "$arq"; then
      # Mata o GRUPO de processos, não só o PID. `uvicorn --reload` e o
      # `next dev` cada um sobe filhos; matar o pai deixa o filho segurando a
      # porta, e o próximo setup.sh acha que o serviço está de pé quando é um
      # órfão respondendo.
      kill -- -"$(cat "$arq")" 2>/dev/null || kill "$(cat "$arq")" 2>/dev/null || true
      echo "  $nome parado"
    fi
    rm -f "$arq"
  done
}

MODO="${1:-}"

if [ "$MODO" = "--parar" ]; then
  echo "== parando =="
  parar
  echo "banco continua de pé (docker compose stop, se quiser derrubar também)."
  exit 0
fi

# O banco sobe em TODOS os modos: até o `--subir` precisa dele, e é o passo
# mais rápido e mais idempotente de todos.
# ------------------------------------------------------------------ 1/7 banco
echo "== 1/7 banco =="
docker compose up -d
printf "esperando o Postgres ficar saudável"
until docker compose ps db --format json 2>/dev/null | grep -q '"Health":"healthy"'; do
  printf "."
  sleep 1
done
echo " ok"

cd apps/api

# `--subir` é o caminho do DIA A DIA, e existe porque a preparação inteira é
# caríssima em tempo pra repetir a cada vez que você senta pra trabalhar: pip
# install, seis ingestões e um yarn install que já estão prontos. Ele confere o
# schema (que é o que muda quando você dá git pull) e sobe. Preparação completa
# é pra máquina nova, ou pra depois de um pull que mexeu em dependência.
if [ "$MODO" = "--subir" ]; then
  source .venv/bin/activate
  echo "== schema =="
  if ! python migrar.py; then
    echo
    echo "parei: o schema precisa de uma decisão sua (instruções acima)."
    exit 1
  fi
  cd "$RAIZ"
else

# ------------------------------------------------------- 2/7 venv + requisitos
echo "== 2/7 venv + dependências =="
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt -r requirements-dev.txt

# ------------------------------------------------------------------- 3/7 .env
echo "== 3/7 .env =="
if [ ! -f .env ]; then
  cp .env.example .env
  # JWT_SECRET não precisa de julgamento humano — gera sozinho.
  # GEMINI_API_KEY precisa da SUA chave: fica marcado pra você editar.
  SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=${SECRET}/" .env
  echo "  .env criado. FALTA: cole sua GEMINI_API_KEY em apps/api/.env antes de continuar."
  echo "  (pegue em https://aistudio.google.com/apikey)"
  read -rp "  pressione Enter depois de colar a chave, ou Ctrl+C pra editar com calma agora... "
else
  echo "  .env já existe, não toquei."
fi

# --------------------------------------------------------------- 4/7 migrações
# ANTES do corpus, de propósito: `ingest.py` gasta minutos de CPU calculando
# embedding, e contra schema velho ele falha no fim — depois de pagar o custo
# inteiro. E é o passo que faltava neste script: `git pull` traz os ARQUIVOS de
# migração e não aplica nenhum, então o código novo conversava com o schema
# velho e a aplicação SUBIA pra quebrar depois, num lugar sem relação óbvia.
# Banco da era anterior ao livro-razão não para mais aqui: `migrar.py` MEDE o
# schema (bloco SONDAS) e aplica só o que falta. Este passo voltou a ser um
# comando em vez de uma conversa — que era o ponto do script.
echo "== 4/7 schema (migrações pendentes) =="
if ! python migrar.py; then
  echo
  echo "parei aqui: o schema precisa de uma decisão sua (as instruções estão acima)."
  echo "nada foi ingerido e nenhum serviço subiu."
  exit 1
fi

# ------------------------------------------------------------------ 5/7 corpus
echo "== 5/7 corpus (CPU local, sem custo de LLM, pula se já ingerido) =="
python ingest.py corpus/cp.txt      --disciplina "Direito Penal"             --tipo lei --norma CP
python ingest.py corpus/cf.txt      --disciplina "Direito Constitucional"    --tipo lei --norma CF
python ingest.py corpus/adct.txt    --disciplina "Direito Constitucional"    --tipo lei --norma ADCT --titulo ADCT
python ingest.py corpus/cpp.txt     --disciplina "Direito Processual Penal"  --tipo lei --norma CPP --titulo "Código de Processo Penal"
python ingest.py corpus/lei8112.txt --disciplina "Direito Administrativo"   --tipo lei --norma L8112 --titulo "Lei 8.112/1990"
python ingest.py corpus/CF88_Livro_EC91_2016.pdf --disciplina "Direito Constitucional" --tipo historico

echo "== 6/7 questões + progresso (veio pelo git em dados/progresso.json) =="
python sincronizar.py importar

# ---------------------------------------------------------------- 7/7 frontend
echo "== 7/7 frontend (dependências) =="
cd "$RAIZ"
yarn install --silent
if [ ! -f apps/web/.env.local ]; then
  cp apps/web/.env.local.example apps/web/.env.local
fi

fi   # fim do bloco de preparação (pulado por --subir)

if [ "$MODO" = "--so-preparar" ]; then
  echo
  echo "preparado. Nada foi subido (--so-preparar)."
  echo "pra subir: ./setup.sh"
  exit 0
fi

# ------------------------------------------------------------------- subir
# Antes este script terminava imprimindo dois comandos pra você colar em dois
# terminais. Isso era escolha ("você vai querer ver o log dos dois") e virou
# atrito: são dois `cd` com caminho absoluto e um `source .venv/bin/activate`
# decorado, toda vez, nas duas máquinas.
#
# Agora ele sobe os dois e faz `tail` dos dois logs junto: você vê o mesmo que
# veria nos dois terminais, e Ctrl+C derruba tudo (trap abaixo). Quem quiser
# deixar rodando e fechar o terminal usa `--so-preparar` e sobe à mão.
echo
echo "== subindo API e frontend =="

porta_ocupada() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

# Rastreia o que ESTE script subiu. Sem isso, o fim do script prometia que
# Ctrl+C derruba os dois mesmo quando os dois já estavam de pé por outra via —
# e `parar()` só mata PID que este script escreveu, então a promessa era falsa.
# Serviço que eu não subi eu também não derrubo.
SUBI=0

if vivo "$PID_API"; then
  echo "  API já está de pé (pid $(cat "$PID_API"))"
elif porta_ocupada 8000; then
  echo "  porta 8000 ocupada por um processo que não é deste script — não subi a API."
  echo "  (se for um uvicorn órfão: ./setup.sh --parar, ou mate o processo na mão)"
else
  cd apps/api
  # setsid pra ganhar um grupo de processos próprio — é o que faz o --parar
  # conseguir derrubar o uvicorn E os filhos que o --reload cria.
  setsid ./.venv/bin/uvicorn api:app --reload --port 8000 > "$LOGS/api.log" 2>&1 &
  echo $! > "$PID_API"
  cd "$RAIZ"
  echo "  API subindo (pid $(cat "$PID_API")) · log em .logs/api.log"
  SUBI=1
fi

if vivo "$PID_WEB"; then
  echo "  frontend já está de pé (pid $(cat "$PID_WEB"))"
elif porta_ocupada 3000; then
  echo "  porta 3000 ocupada por um processo que não é deste script — não subi o frontend."
else
  cd apps/web
  setsid yarn dev > "$LOGS/web.log" 2>&1 &
  echo $! > "$PID_WEB"
  cd "$RAIZ"
  echo "  frontend subindo (pid $(cat "$PID_WEB")) · log em .logs/web.log"
  SUBI=1
fi

# Espera as duas RESPONDEREM, não só existirem: processo vivo não quer dizer
# porta aberta, e mandar a pessoa abrir o navegador antes disso dá "não é
# possível acessar esse site" — que parece defeito e é pressa.
esperar() {  # $1=url  $2=nome  $3=segundos
  printf "  esperando %s" "$2"
  for _ in $(seq "$3"); do
    if curl -fsS -o /dev/null --max-time 2 "$1"; then echo " ok"; return 0; fi
    printf "."
    sleep 1
  done
  echo " não respondeu em ${3}s — veja o log (.logs/)"
  return 1
}

OK_API=0; OK_WEB=0
esperar http://localhost:8000/openapi.json "a API" 60 && OK_API=1
esperar http://localhost:3000 "o frontend" 90 && OK_WEB=1

echo
if [ "$OK_API" = 1 ] && [ "$OK_WEB" = 1 ]; then
  cat <<EOF
tudo de pé:

  aplicação   http://localhost:3000
  API (docs)  http://localhost:8000/docs

Pra rodar comando do backend noutro terminal, sem decorar caminho:
  cd $RAIZ && source ativar.sh      (ativa o venv e te deixa em apps/api)
  ./tutor migrar.py --listar        (roda um comando só, sem mudar o shell)

Antes de sair desta máquina, sempre:
  cd apps/api && python sincronizar.py exportar && cd "$RAIZ" && git add -A && git commit -m progresso && git push
EOF
else
  echo "algo não respondeu — o log de quem subiu vem abaixo."
fi

# Nada subido por mim = nada meu pra acompanhar nem pra derrubar. Sai limpo em
# vez de dar `tail` em log que não existe (o que quebrava o script no fim, com
# `tail: no files remaining`, justamente no caminho mais comum: rodar de novo
# com tudo já de pé).
if [ "$SUBI" = 0 ]; then
  echo
  echo "os dois já estavam de pé — não subi nem vou derrubar nada."
  echo "pra reiniciar:  ./setup.sh --parar && ./setup.sh --subir"
  exit 0
fi

echo
echo "Ctrl+C aqui derruba o que este script subiu. O banco continua rodando."
echo "Pra parar depois, de qualquer pasta do repo:  ./setup.sh --parar"
echo
echo "--- log a partir daqui ---"

# O trap fica DEPOIS de subir e antes do tail: assim Ctrl+C durante o tail
# derruba os serviços, que é o que "sair" significa aqui.
trap 'echo; echo "derrubando..."; parar; exit 0' INT TERM
# Só os logs que existem: `tail` de arquivo ausente aborta a lista inteira e,
# com `set -e`, o script todo.
LOGS_VIVOS=()
[ -f "$LOGS/api.log" ] && LOGS_VIVOS+=("$LOGS/api.log")
[ -f "$LOGS/web.log" ] && LOGS_VIVOS+=("$LOGS/web.log")
tail -n +1 -f "${LOGS_VIVOS[@]}"
