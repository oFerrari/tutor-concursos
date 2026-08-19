# Ativa o venv do backend de QUALQUER pasta do repo. Use com `source`:
#
#   source ativar.sh
#
# Existe porque o venv mora em apps/api/.venv (o backend inteiro mora lá) e a
# raiz é onde a gente entra. Sem isto, "ativar o ambiente" era decorar
# `source apps/api/.venv/bin/activate` — e errar isso não dá erro claro, dá
# "No module named 'psycopg'" ou "python: command not found", que parece defeito
# do projeto e é caminho errado.
#
# Depois de ativar, você fica em apps/api: é de lá que TODO comando do
# CLAUDE.md roda (migrar.py, chat.py, ingest.py). Quem só quer rodar um comando
# sem mudar o shell usa `./tutor <comando>`.
_raiz=$(git rev-parse --show-toplevel 2>/dev/null || echo .)
if [ ! -d "$_raiz/apps/api/.venv" ]; then
  echo "não há venv ainda — rode ./setup.sh primeiro (ele cria e instala tudo)."
else
  # shellcheck disable=SC1091
  . "$_raiz/apps/api/.venv/bin/activate"
  cd "$_raiz/apps/api" || return 1
  echo "venv ativo · você está em apps/api (python $(python -V 2>&1 | cut -d' ' -f2))"
fi
unset _raiz
