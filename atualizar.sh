#!/usr/bin/env bash
# Instala no projeto os arquivos baixados do chat.
#   ./atualizar.sh            janela padrao de 20 min
#   MIN=120 ./atualizar.sh    janela maior
set -euo pipefail
DL="${DL:-/mnt/c/Users/andrei.domingos/Downloads}"
MIN="${MIN:-20}"
PY="chunking retrieval embeddings llm socratic scheduler config db ingest chat gerar reingest diagnostico api"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

recente() { find "$DL" -maxdepth 1 -name "$1" -mmin -"$MIN" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1; }

Z=$(recente 'files*.zip')
if [ -n "$Z" ]; then
  ZT=${Z%% *}; ZP=${Z#* }
  echo "zip:   $(basename "$ZP")  $(date -r "$ZP" '+%H:%M')"
  unzip -oq "$ZP" -d "$TMP"
else
  ZT=0
fi

# Arquivo solto MAIS NOVO que o zip sobrescreve o que veio dele. Sem isso,
# um zip de tres minutos antes vencia o arquivo corrigido baixado agora.
for n in $PY; do
  L=$(recente "$n*.py") || true
  [ -z "$L" ] && continue
  LT=${L%% *}; LP=${L#* }
  if awk "BEGIN{exit !($LT > $ZT)}"; then
    cp "$LP" "$TMP/$n.py"
    echo "solto: $(basename "$LP")  $(date -r "$LP" '+%H:%M')"
  fi
done
for f in $(find "$DL" -maxdepth 1 -regextype posix-extended -regex '.*/[0-9]{3}_[a-z_]+( \([0-9]+\))?\.sql' -mmin -"$MIN" 2>/dev/null || true); do
  cp "$f" "$TMP"/
done

mkdir -p core db
find "$TMP" -type f \( -name '*.py' -o -name '*.sql' \) | while read -r f; do
  b=$(basename "$f" | sed -E 's/ ?\([0-9]+\)//')
  case "$b" in
    chunking.py|retrieval.py|embeddings.py|llm.py|socratic.py|scheduler.py|config.py|db.py) d=core ;;
    0[0-9][0-9]_*.sql) d=db ;;
    ingest.py|chat.py|gerar.py|reingest.py|diagnostico.py|api.py) d=. ;;
    *) echo "  IGNORADO (fora da lista): $b"; continue ;;
  esac
  cp "$f" "$d/$b"; echo "  -> $d/$b"
done

if python -m compileall -q core *.py; then echo "sintaxe: ok"; else echo "SINTAXE COM ERRO"; fi
grep -m1 -H '^VERSAO' core/*.py *.py 2>/dev/null | sed 's|^|  |' || true
