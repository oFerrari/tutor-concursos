#!/usr/bin/env bash
# Põe ESTA máquina em dia — código, schema e estado — num comando.
#
#   ./sincronizar.sh              cheguei nesta máquina: traz tudo e confere
#   ./sincronizar.sh --subir      o mesmo, e ainda sobe API e frontend
#   ./sincronizar.sh --sair       vou desligar: manda o estado (e o código)
#   ./sincronizar.sh --status     só diagnostica, não toca em nada
#
# POR QUE ELE EXISTE, SE OS HOOKS JÁ FAZEM ISSO
# ---------------------------------------------
# Fazem, e continuam sendo o caminho principal: `pre-push` manda o estado num
# ref próprio e `post-merge` recebe, migra e importa (ver .githooks/_comum.sh).
# Este script NÃO reimplementa nada disso — chama as mesmas funções.
#
# Ele existe por causa de uma decisão dos hooks que está certa e cobra um
# preço: falha dentro de um hook NUNCA derruba a operação do git, porque banco
# desligado não pode impedir um commit. Então um `git pull` com migração
# pendente imprime "migracao pendente nao aplicada" no meio da saída do git e
# segue em frente. A linha passa batida, o código novo conversa com o schema
# velho, e a aplicação SOBE pra quebrar depois — que é exatamente o modo de
# falha que a migração 023 existe pra fechar.
#
# Aqui a mesma falha PARA o comando e diz o que fazer. É a diferença entre um
# aviso e um portão.
#
# Roda de QUALQUER pasta do repositório.
set -euo pipefail

RAIZ=$(git rev-parse --show-toplevel 2>/dev/null) \
  || RAIZ=$(cd "$(dirname "$0")" && pwd)
cd "$RAIZ"

MODO="${1:-}"
case "$MODO" in
  ""|--subir|--sair|--status) ;;
  -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "não conheço \"$MODO\". Use --subir, --sair, --status ou nada." >&2; exit 2 ;;
esac

# `TUTOR_HOOK` é lido por `_comum.sh` e pode não existir. Com `set -u` isso
# aborta o script na primeira chamada — não é hipótese, é o que acontece.
TUTOR_HOOK="${TUTOR_HOOK:-}"
# shellcheck source=.githooks/_comum.sh
. "$RAIZ/.githooks/_comum.sh"

PY="$RAIZ/apps/api/.venv/bin/python"
REMOTO=$(git remote 2>/dev/null | head -1)
REMOTO="${REMOTO:-origin}"

aviso() { printf '\n== %s ==\n' "$1"; }

# --------------------------------------------------------------- pré-requisitos
if [ ! -x "$PY" ]; then
  echo "não há venv em apps/api/.venv — rode ./setup.sh primeiro (é a preparação"
  echo "completa: dependências, .env, corpus). Este script assume tudo isso pronto." >&2
  exit 1
fi

# Os hooks são config LOCAL (`core.hooksPath`), não viajam no clone. Instalar
# aqui também, e não só no setup.sh, é o que faz o sincronismo valer numa
# máquina onde alguém rodou este script primeiro.
if [ -d "$RAIZ/.githooks" ] \
   && [ "$(git config --get core.hooksPath 2>/dev/null)" != ".githooks" ]; then
  git config core.hooksPath .githooks
  echo "hooks de sincronismo instalados (.githooks)"
fi

# Banco de pé é pré-requisito de migração e de estado. Subir sozinho é melhor
# que falhar com `connection refused`, que manda a pessoa depurar Postgres
# quando ela só queria sincronizar. Mesmo padrão do testar.sh.
subir_banco() {
  if docker compose ps --format '{{.Name}} {{.State}}' 2>/dev/null \
       | grep -q 'tutor-db running'; then
    return 0
  fi
  aviso "banco"
  docker compose up -d
  for _ in $(seq 1 30); do
    docker exec tutor-db pg_isready -q 2>/dev/null && return 0
    sleep 1
  done
  echo 'o banco não respondeu em 30s. "docker compose logs tutor-db" diz por quê.' >&2
  exit 1
}

# ------------------------------------------------------------------- relatório
# O que ficou pendente DEPOIS de tudo. Existe porque duas coisas deste projeto
# terminam em segundo plano — o embedding do material que veio no pacote e a
# reindexação que uma migração pediu (a 027 marca material de referência como
# `processando` de propósito, pro vetor perder o assunto que não devia estar
# lá). Sem esta linha, "acabou" e "está trabalhando" ficam iguais na tela.
pendencias() {
  local n
  # O `cd` não é cosmético: `core/config.py` chama `load_dotenv()` sem caminho,
  # e sem estar em apps/api o import falha e a contagem sai como "?". Mesmo
  # motivo do `cd` do testar.sh e do ./tutor.
  n=$( cd "$RAIZ/apps/api" && "$PY" - <<'EOF' 2>/dev/null || echo "?"
from core import db
print(db.exec1("SELECT count(*) n FROM documento WHERE status = 'processando'")["n"])
EOF
  )
  [ "$n" = "0" ] && return 0
  echo "  material indexando em segundo plano: $n (log em .logs/estado.log)"
  echo "  a biblioteca já responde; o que falta é só o vetor dos que sobraram."
}

estado_resumido() { ( cd "$RAIZ/apps/api" && "$PY" sincronizar.py estado ); }

# ---------------------------------------------------------------------- status
if [ "$MODO" = "--status" ]; then
  aviso "git"
  git status -sb | head -1
  git fetch -q "$REMOTO" 2>/dev/null || echo "  (sem rede — o que segue é do último fetch)"
  atras=$(git rev-list --count "HEAD..@{u}" 2>/dev/null || echo 0)
  frente=$(git rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0)
  echo "  $frente commit(s) a enviar · $atras a receber"
  aviso "schema"
  ( cd "$RAIZ/apps/api" && "$PY" migrar.py --listar | tail -4 )
  aviso "estado"
  estado_resumido
  pendencias
  exit 0
fi

# ------------------------------------------------------------------------ sair
if [ "$MODO" = "--sair" ]; then
  subir_banco
  aviso "estado desta máquina -> $REMOTO"
  # A MESMA função do `pre-push`. Ela exporta do banco, monta o commit no ref
  # `estado` e empurra. Chamar aqui é pra quem estudou e não programou: sem
  # commit de código não há push, e sem push o hook não roda.
  estado_enviar "$REMOTO"

  frente=$(git rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0)
  if [ "$frente" != "0" ]; then
    aviso "código"
    echo "  $frente commit(s) local(is) ainda não enviado(s):"
    git log --oneline "@{u}..HEAD" | sed 's/^/    /'
    # PERGUNTA, não faz. Mandar o ESTADO é rotina de dado e o hook já faria
    # sozinho; publicar CÓDIGO é decisão de quem escreveu, e um script que
    # empurra commit sem perguntar tira essa decisão de quem a tem.
    #
    # O `-t 0` não é zelo excessivo: sem terminal (chamado por outro script,
    # por cron, por um agente) o `read` FALHA, e com `set -e` isso aborta o
    # script depois de o estado já ter sido enviado — parando no meio, do lado
    # errado da única parte que não dá pra repetir de graça.
    if [ -t 0 ]; then
      read -rp "  enviar agora? [s/N] " ok
      case "$ok" in [sS]*) git push "$REMOTO" HEAD ;; *) echo "  não enviei." ;; esac
    else
      echo "  (sem terminal pra perguntar — envie com: git push $REMOTO HEAD)"
    fi
  fi

  if [ -n "$(git status --porcelain)" ]; then
    aviso "atenção"
    echo "  há mudança não commitada aqui — ela NÃO viaja:"
    git status --short | sed 's/^/    /'
  fi
  echo
  echo "pode desligar. Na outra máquina: ./sincronizar.sh"
  exit 0
fi

# ----------------------------------------------------- o padrão: cheguei aqui
subir_banco

aviso "código de $REMOTO"
# --ff-only de propósito: um merge automático nas suas costas é a última coisa
# que um script de conveniência deve fazer. Divergência é decisão sua, e a
# mensagem abaixo diz qual.
if git pull --ff-only "$REMOTO" "$(git rev-parse --abbrev-ref HEAD)"; then
  :
else
  echo
  echo "não deu fast-forward: esta máquina tem commit que o remoto não tem," >&2
  echo 'ou o contrário. Resolva com "git rebase" ou "git merge" e rode de novo.' >&2
  echo "Nada foi alterado no banco." >&2
  exit 1
fi

# SCHEMA ANTES DO DADO, e este é o portão que dá razão ao script existir:
# `git pull` traz os arquivos .sql e não aplica nenhum, e o hook que aplicaria
# engole a falha pra não derrubar o git. Aqui, falha para.
aviso "schema"
if ! ( cd "$RAIZ/apps/api" && "$PY" migrar.py ); then
  echo
  echo "parei: a migração precisa de uma decisão sua (mensagem acima)." >&2
  echo "O ESTADO não foi importado — pacote novo contra schema velho falha no" >&2
  echo "insert, e falhar no meio de uma importação é o pior lugar pra falhar." >&2
  exit 1
fi

aviso "estado de $REMOTO"
# A MESMA função do `post-merge`. Traz o ref `estado`, os PDFs originais e
# importa em duas fases (relacional na hora, embedding em segundo plano).
# Idempotente: a importação é união, então rodar de novo não duplica nada.
estado_receber "$REMOTO"

aviso "como ficou"
estado_resumido
pendencias

if [ "$MODO" = "--subir" ]; then
  exec "$RAIZ/setup.sh" --subir
fi

echo
echo "pra subir API e frontend:  ./setup.sh --subir"
echo "(ou rode  ./sincronizar.sh --subir  na próxima, que faz os dois)"
