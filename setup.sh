#!/usr/bin/env bash
# Prepara o projeto do zero (máquina nova) ou retoma numa já usada.
# Idempotente: rodar de novo não duplica nada (ingest.py pula arquivo já
# ingerido pelo hash; venv só é criado se não existir).
#
#   ./setup.sh
#
# Rode da RAIZ do repo. No final, imprime os 2 comandos que faltam rodar
# em terminais separados (API e frontend — de propósito não ficam em
# background aqui, você vai querer ver o log dos dois).
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/6 banco =="
docker compose up -d
echo -n "esperando o Postgres ficar saudável"
until docker compose ps db --format json 2>/dev/null | grep -q '"Health":"healthy"'; do
  echo -n "."
  sleep 1
done
echo " ok"

cd apps/api

echo "== 2/6 venv + dependências =="
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt -r requirements-dev.txt

echo "== 3/6 .env =="
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

echo "== 4/6 corpus (reingestão — CPU local, sem custo de LLM, pula se já ingerido) =="
python ingest.py corpus/cp.txt      --disciplina "Direito Penal"             --tipo lei --norma CP
python ingest.py corpus/cf.txt      --disciplina "Direito Constitucional"    --tipo lei --norma CF
python ingest.py corpus/adct.txt    --disciplina "Direito Constitucional"    --tipo lei --norma ADCT --titulo ADCT
python ingest.py corpus/cpp.txt     --disciplina "Direito Processual Penal"  --tipo lei --norma CPP --titulo "Código de Processo Penal"
python ingest.py corpus/lei8112.txt --disciplina "Direito Administrativo"   --tipo lei --norma L8112 --titulo "Lei 8.112/1990"
python ingest.py corpus/CF88_Livro_EC91_2016.pdf --disciplina "Direito Constitucional" --tipo historico

echo "== 5/6 questões + progresso (veio pelo git em dados/progresso.json) =="
python sincronizar.py importar

echo "== 6/6 frontend =="
cd ../..
yarn install --silent
if [ ! -f apps/web/.env.local ]; then
  cp apps/web/.env.local.example apps/web/.env.local
fi

cat <<'EOF'

tudo pronto. Faltam 2 terminais:

  terminal 1 (API):
    cd ~/tutor-concursos/apps/api && source .venv/bin/activate && uvicorn api:app --reload --port 8000

  terminal 2 (frontend):
    cd apps/web && yarn dev

Depois: http://localhost:3000

  terminal 3 (opcional — testar o front publicado na Vercel contra esta API):
    ./subir-vercel.sh
    (sobe banco+API+túnel cloudflared sozinho e imprime a URL pública —
    cole em NEXT_PUBLIC_API_URL nas env vars do projeto na Vercel e faça
    redeploy. URL muda a cada reinício do túnel; ver subir-vercel.sh.)

Antes de sair desta máquina, sempre:
  cd apps/api && python sincronizar.py exportar && cd ../.. && git add -A && git commit -m progresso && git push
EOF
