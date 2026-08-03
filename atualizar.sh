#!/usr/bin/env bash
set -euo pipefail
DL="${DL:-/mnt/c/Users/andrei.domingos/Downloads}"
MIN="${MIN:-360}"
PY="chunking retrieval embeddings llm socratic scheduler config db ingest chat gerar reingest diagnostico api"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
Z=$(find "$DL" -maxdepth 1 -name 'files*.zip' -mmin -"$MIN" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)
if [ -n "$Z" ]; then
  echo "origem: zip $Z"; unzip -oq "$Z" -d "$TMP"
else
  echo "origem: arquivos soltos dos ultimos $MIN min"
  for n in $PY; do
    f=$(find "$DL" -maxdepth 1 -name "$n*.py" -mmin -"$MIN" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)
    [ -n "$f" ] && cp "$f" "$TMP/$n.py"
  done
  f=$(find "$DL" -maxdepth 1 -regextype posix-extended -regex '.*/[0-9]{3}_[a-z_]+( \([0-9]+\))?\.sql' -mmin -"$MIN" 2>/dev/null || true)
  for x in $f; do cp "$x" "$TMP"/; done
fi
mkdir -p core db
find "$TMP" -type f \( -name '*.py' -o -name '*.sql' \) | while read -r f; do
  b=$(basename "$f" | sed -E 's/ ?\([0-9]+\)//')
  case "$b" in
    chunking.py|retrieval.py|embeddings.py|llm.py|socratic.py|scheduler.py|config.py|db.py) d=core ;;
    0[0-9][0-9]_*.sql) d=db ;;
    ingest.py|chat.py|gerar.py|reingest.py|diagnostico.py|api.py) d=. ;;
    *) echo "  IGNORADO (fora da lista): $b"; continue ;;
  esac
  cp "$f" "$d/$b"; echo "  -> $d/$b   $(date -r "$f" '+%H:%M')"
done
if python -m compileall -q core *.py; then echo "sintaxe: ok"; else echo "SINTAXE COM ERRO"; fi
grep -m1 -H '^VERSAO' core/*.py *.py 2>/dev/null | sed 's|^|  |' || true
