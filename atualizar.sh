#!/usr/bin/env bash
# Instala no projeto os arquivos baixados do chat.
#   ./atualizar.sh            janela padrao de 20 min
#   MIN=120 ./atualizar.sh    janela maior
set -euo pipefail
DL="${DL:-/mnt/c/Users/andrei.domingos/Downloads}"
MIN="${MIN:-20}"
NUCLEO="chunking retrieval embeddings llm socratic scheduler scheduler_regras config db"
RAIZ="ingest chat gerar reingest diagnostico simular api"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

recente() { find "$DL" -maxdepth 1 -name "$1" -mmin -"$MIN" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1; }

Z=$(recente 'files*.zip')
if [ -n "$Z" ]; then
  ZT=${Z%% *}; ZP=${Z#* }
  echo "zip:   $(basename "$ZP")  $(date -r "$ZP" '+%H:%M')"
  unzip -oqj "$ZP" -d "$TMP"
else
  ZT=0
fi

# Arquivo solto mais novo que o zip sobrescreve o que veio dele.
for n in $NUCLEO $RAIZ; do
  L=$(recente "$n*.py") || true
  [ -z "$L" ] && continue
  LT=${L%% *}; LP=${L#* }
  if awk "BEGIN{exit !($LT > $ZT)}"; then
    cp "$LP" "$TMP/$n.py"; echo "solto: $(basename "$LP")  $(date -r "$LP" '+%H:%M')"
  fi
done
for f in $(find "$DL" -maxdepth 1 -regextype posix-extended -regex '.*/[0-9]{3}_[a-z_]+( \([0-9]+\))?\.sql' -mmin -"$MIN" 2>/dev/null || true); do
  cp "$f" "$TMP"/
done

mkdir -p core db
find "$TMP" -type f \( -name '*.py' -o -name '*.sql' \) | while read -r f; do
  b=$(basename "$f" | sed -E 's/ ?\([0-9]+\)//')
  nome="${b%.py}"; d=""
  case "$b" in
    0[0-9][0-9]_*.sql) d=db ;;
    *.py)
      # 1) listas explicitas  2) se o arquivo ja existe no projeto, ele se
      # roteia sozinho — evita ter de editar este script a cada modulo novo.
      for x in $NUCLEO; do [ "$nome" = "$x" ] && d=core; done
      for x in $RAIZ;   do [ "$nome" = "$x" ] && d=.;    done
      [ -z "$d" ] && [ -f "core/$b" ] && d=core
      [ -z "$d" ] && [ -f "./$b" ]   && d=.
      ;;
  esac
  if [ -z "$d" ]; then
    echo "  IGNORADO: $b  (nao esta na lista nem existe no projeto)"; continue
  fi
  cp "$f" "$d/$b"; echo "  -> $d/$b"
done

if python -m compileall -q core *.py; then echo "sintaxe: ok"; else echo "SINTAXE COM ERRO"; fi
grep -m1 -H '^VERSAO' core/*.py *.py 2>/dev/null | sed 's|^|  |' || true
