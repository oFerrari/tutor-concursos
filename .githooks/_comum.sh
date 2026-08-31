# Funções compartilhadas pelos hooks e pelo setup.sh. Não é executável: é
# `source`-ado.
#
# POR QUE O ESTADO VIAJA NUM REF PRÓPRIO (refs/heads/estado)
# ---------------------------------------------------------
# A primeira versão disto commitava `dados/progresso.json` no branch de
# trabalho. Dois defeitos MEDIDOS, os dois em repositório de teste antes de
# chegar aqui:
#
#   1. Push sem commit de código não levava nada. É o caso mais comum de
#      todos — você estudou, não programou. O hook precisava CRIAR um commit,
#      e um commit criado dentro do `pre-push` não entra no push que já está
#      em andamento: o git resolveu os refs antes de chamar o hook.
#   2. Empurrar o mesmo ref por dentro do hook faz o push original morrer com
#      `cannot lock ref / failed to push some refs` — vermelho na cara de
#      quem só queria enviar código. Verificado, não suposto.
#
# Num ref separado, os dois problemas desaparecem: o estado sobe sempre (com
# ou sem commit de código), o push de código segue intacto, e o JSON não
# existe no branch de trabalho — então nunca dá conflito de merge, que era o
# outro custo previsível de versioná-lo junto.
#
# `estado` é um branch de DADO, não de código. Não faça checkout nele: a
# árvore tem um arquivo só.
REF_ESTADO="refs/heads/estado"
ARQ_ESTADO="apps/api/dados/progresso.json"

_raiz() { git rev-parse --show-toplevel 2>/dev/null; }

_py() {
  local r; r="$(_raiz)"
  if [ -x "$r/apps/api/.venv/bin/python" ]; then
    echo "$r/apps/api/.venv/bin/python"
  else
    return 1
  fi
}

# Silencia o próprio hook quando o git está sendo chamado POR um hook.
_reentrante() { [ -n "$TUTOR_HOOK" ]; }

# Roda um comando do backend. Falha aqui NUNCA derruba a operação do git:
# banco desligado não pode impedir commit, push ou pull.
_backend() {
  local r py; r="$(_raiz)"; py="$(_py)" || { echo "  [tutor] venv ausente (rode ./setup.sh) — pulei"; return 1; }
  ( cd "$r/apps/api" && TUTOR_HOOK=1 "$py" "$@" ) || return 1
}

# Exporta o estado do banco local e empurra pro ref próprio.
estado_enviar() {
  local remoto="${1:-origin}" r blob tree pai commit
  r="$(_raiz)" || return 0
  _backend sincronizar.py exportar >/dev/null 2>&1 || {
    echo "  [tutor] nao consegui exportar o estado (banco de pe?) — push de codigo segue"
    return 0
  }
  [ -f "$r/$ARQ_ESTADO" ] || return 0
  blob=$(git hash-object -w "$r/$ARQ_ESTADO") || return 0
  tree=$(printf '100644 blob %s\tprogresso.json\n' "$blob" | git mktree) || return 0
  pai=""
  if git rev-parse -q --verify "$REF_ESTADO" >/dev/null; then
    # Nada mudou desde o último envio: não cria commit vazio a cada push.
    if [ "$(git rev-parse -q "$REF_ESTADO^{tree}")" = "$tree" ]; then
      echo "  [tutor] estado já estava em dia"
      return 0
    fi
    pai="-p $REF_ESTADO"
  fi
  commit=$(git commit-tree "$tree" $pai -m "estado $(date -Iseconds)") || return 0
  git update-ref "$REF_ESTADO" "$commit"
  # --no-verify: sem isto o push interno chama este mesmo hook, de novo, pra
  # sempre. Medido em repositório de teste: travou até o timeout.
  if TUTOR_HOOK=1 git push --no-verify -q "$remoto" "$REF_ESTADO:$REF_ESTADO" 2>/dev/null; then
    echo "  [tutor] estado enviado ($(du -h "$r/$ARQ_ESTADO" | cut -f1))"
  else
    echo "  [tutor] estado commitado localmente, mas o envio falhou (rede?)"
  fi
}

# Traz o estado do remoto e importa no banco local.
estado_receber() {
  local remoto="${1:-origin}" r; r="$(_raiz)" || return 0
  if ! TUTOR_HOOK=1 git fetch -q "$remoto" "$REF_ESTADO:refs/remotes/$remoto/estado" 2>/dev/null; then
    # Primeiro uso: o ref ainda não existe lá. Não é erro.
    git rev-parse -q --verify "refs/remotes/$remoto/estado" >/dev/null || return 0
  fi
  mkdir -p "$(dirname "$r/$ARQ_ESTADO")"
  git show "refs/remotes/$remoto/estado:progresso.json" > "$r/$ARQ_ESTADO" 2>/dev/null || return 0
  # Schema ANTES do dado: pacote novo contra schema velho falha no insert, e
  # é exatamente o buraco que a migração 023 fechou — `git pull` traz o
  # arquivo .sql e não aplica nada.
  _backend migrar.py >/dev/null 2>&1 || {
    echo "  [tutor] migracao pendente nao aplicada — rode ./setup.sh --subir"
    return 0
  }
  # Duas fases, e a razão é medida: o `git pull` do teste ficou MINUTOS preso
  # calculando o embedding de 240 trechos de material, com o terminal
  # travado. Fase 1 é o dado relacional (contas, mesas, edital, questões,
  # progresso, tentativas, conversas) e volta em segundos; fase 2 é o
  # embedding do material, que vai pro background com log.
  _backend sincronizar.py importar --material-depois \
    || { echo "  [tutor] importacao do estado falhou (banco de pe?)"; return 0; }
  local r py; r="$(_raiz)"; py="$(_py)" || return 0
  mkdir -p "$r/.logs"
  # setsid: sem isso o processo morre junto com o shell do hook, e o material
  # ficaria 'processando' pra sempre. Mesmo padrão do setup.sh com o uvicorn.
  ( cd "$r/apps/api" && TUTOR_HOOK=1 setsid nohup "$py" sincronizar.py material \
      > "$r/.logs/estado.log" 2>&1 & ) 2>/dev/null
  echo "  [tutor] material do aluno indexando em segundo plano (.logs/estado.log)"
}
