#!/usr/bin/env bash
# Sobe banco + API + túnel público, pra testar o front publicado na Vercel
# contra o backend desta máquina (uso local/dev — ver "Aberto" no
# AGENTS.md/CLAUDE.md sobre backend hospedado de verdade, que é o passo
# seguinte quando isso cansar).
#
# Rode da RAIZ do repo:
#   ./subir-vercel.sh
#
# Idempotente: se banco/API/túnel já estiverem de pé, não duplica nada —
# só imprime a URL do túnel de novo.
#
# IMPORTANTE: a URL do túnel (cloudflared "quick tunnel") é EFÊMERA — muda
# toda vez que o túnel é reiniciado (reboot, `pkill cloudflared`, etc).
# Depois de rodar este script, sempre que a URL mudar:
#   1. Vercel → tutor-concursos-web → Settings → Environment Variables
#   2. NEXT_PUBLIC_API_URL = <url impressa abaixo>
#   3. Deployments → ⋯ no último deploy → Redeploy
#      (NEXT_PUBLIC_* só entra em build novo)
set -euo pipefail
cd "$(dirname "$0")"

CLOUDFLARED="$HOME/.local/bin/cloudflared"
LOG_DIR="/tmp/tutor-concursos-dev"
mkdir -p "$LOG_DIR"

echo "== 1/3 banco =="
docker compose up -d
echo -n "esperando o Postgres ficar saudável"
until docker compose ps db --format json 2>/dev/null | grep -q '"Health":"healthy"'; do
  echo -n "."
  sleep 1
done
echo " ok"

echo "== 2/3 API =="
if curl -s -o /dev/null -w "" http://localhost:8000/docs 2>/dev/null; then
  echo "  já está rodando em localhost:8000, não subi outra."
else
  cd apps/api
  source .venv/bin/activate
  nohup uvicorn api:app --port 8000 > "$LOG_DIR/api.log" 2>&1 &
  disown
  cd ../..
  echo -n "  esperando a API responder"
  for _ in $(seq 1 20); do
    # "cmd && break" solto quebraria o script no 1º "cmd" que falhar (set -e
    # não perdoa && fora de if/while) — por isso o teste vira condição de if.
    if curl -s -o /dev/null http://localhost:8000/docs 2>/dev/null; then
      break
    fi
    echo -n "."
    sleep 1
  done
  echo " ok (log em $LOG_DIR/api.log)"
fi

echo "== 3/3 túnel público (cloudflared) =="
if pgrep -f "cloudflared tunnel" > /dev/null; then
  echo "  já tem um túnel rodando — pegando a URL dele:"
else
  if [ ! -x "$CLOUDFLARED" ]; then
    echo "  cloudflared não encontrado em $CLOUDFLARED. Baixe com:"
    echo "  mkdir -p ~/.local/bin && curl -fsSL -o ~/.local/bin/cloudflared \\"
    echo "    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \\"
    echo "    && chmod +x ~/.local/bin/cloudflared"
    exit 1
  fi
  : > "$LOG_DIR/cloudflared.log"
  nohup "$CLOUDFLARED" tunnel --url http://localhost:8000 >> "$LOG_DIR/cloudflared.log" 2>&1 &
  disown
  echo -n "  esperando o túnel abrir"
  for _ in $(seq 1 30); do
    # Precisa da URL completa, não só da palavra "trycloudflare.com" — essa
    # palavra já aparece antes, na linha "Requesting new quick Tunnel on
    # trycloudflare.com...", que sai ANTES da URL de verdade existir. Casar
    # com isso primeiro fazia o loop soltar o "break" cedo demais.
    if grep -qo 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null; then
      break
    fi
    echo -n "."
    sleep 1
  done
  echo " ok"
fi

# tail -1, não head -1: o log pode ter mais de uma URL (túnel reiniciado sem
# o log ser truncado). A que vale é a ÚLTIMA — pegar a primeira devolve um
# endereço morto, que é indistinguível de "backend fora do ar" na tela.
URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null | tail -1 || true)

if [ -z "$URL" ]; then
  echo
  echo "ERRO: o túnel não devolveu URL. Veja $LOG_DIR/cloudflared.log"
  echo "      (pra recomeçar do zero: pkill -f 'cloudflared tunnel' && ./subir-vercel.sh)"
  exit 1
fi

# Confere o que o site publicado REALMENTE tem embutido. NEXT_PUBLIC_* entra
# no bundle em tempo de BUILD: trocar a variável na Vercel não muda o deploy
# que já existe. Sem esta conferência, "não consigo acessar o backend" parece
# problema de túnel/CORS quando na verdade o site está chamando uma URL morta.
NO_AR=$(curl -s --max-time 20 https://tutor-concursos-web.vercel.app/ 2>/dev/null \
        | grep -o '/_next/static/immutable/chunks/[^"]*\.js' | sort -u \
        | while read -r js; do
            curl -s --max-time 20 "https://tutor-concursos-web.vercel.app$js" 2>/dev/null \
            | grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com'
          done | sort -u | head -1 || true)

echo
echo "────────────────────────────────────────────────────────────────"
echo "Vercel → tutor-concursos-web → Settings → Environment Variables"
echo
echo "  KEY     NEXT_PUBLIC_API_URL"
echo "  VALUE   $URL"
echo
if [ "$NO_AR" = "$URL" ]; then
  echo "  O site publicado JÁ usa essa URL. Não precisa fazer nada:"
  echo "  https://tutor-concursos-web.vercel.app"
else
  echo "  PRECISA REDEPLOY. O site publicado hoje chama:"
  echo "  ${NO_AR:-"(não consegui ler — confira na mão)"}"
  echo
  echo "  1. cole o VALUE acima na variável NEXT_PUBLIC_API_URL"
  echo "  2. Deployments → ⋯ no deploy de Production → Redeploy"
  echo "  3. DESMARQUE \"Use existing Build Cache\" e confirme"
fi
echo "────────────────────────────────────────────────────────────────"

# WSL: já deixa o VALUE colado na área de transferência do Windows, que é
# onde ele vai ser usado (o navegador).
if command -v clip.exe > /dev/null 2>&1; then
  printf '%s' "$URL" | clip.exe 2>/dev/null && echo "(o VALUE já está na sua área de transferência — é só Ctrl+V)"
fi

cat <<EOF

Enquanto o túnel ficar de pé, seu Postgres/API local ficam acessíveis
publicamente por essa URL — não deixe ligado indefinidamente.

Pra desligar tudo depois:
  pkill -f "cloudflared tunnel"; pkill -f "uvicorn api:app"; docker compose down
EOF
