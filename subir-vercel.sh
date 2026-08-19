#!/usr/bin/env bash
# Prepara e verifica o backend pra rodar NA NUVEM, atendendo o frontend
# publicado na Vercel.
#
#   ./subir-vercel.sh              prepara a nuvem: imagem, banco, schema, corpus
#   ./subir-vercel.sh --tunel      atalho de DEV: expõe a API desta máquina
#   ./subir-vercel.sh --status     o que está de pé, aqui e lá
#   ./subir-vercel.sh --parar      derruba o túnel (o banco e a API ficam)
#
# Roda de QUALQUER pasta do repositório. Idempotente: cada passo confere antes
# de agir, e rodar de novo não duplica nada.
#
# O QUE ESTE SCRIPT NÃO FAZ, E POR QUE
# ------------------------------------
# Ele não faz login no provedor nem cria o serviço. Isso exige token da sua
# conta, e token de infraestrutura não passa por dentro de um script que você
# não escreveu — nem por dentro de uma conversa. O que ele faz é tudo o resto,
# e para no ponto exato dizendo o comando literal que falta.
set -euo pipefail

# Duas linhas e não uma: `A || B && C` agrupa como `(A || B) && C`, então a
# versão de uma linha rodaria o `pwd` também quando o git acerta.
RAIZ=$(git rev-parse --show-toplevel 2>/dev/null) \
  || RAIZ=$(cd "$(dirname "$0")" && pwd)
cd "$RAIZ"

LOGS="$RAIZ/.logs"
mkdir -p "$LOGS"
PID_TUNEL="$LOGS/tunel.pid"
CLOUDFLARED="$HOME/.local/bin/cloudflared"
MODO="${1:-}"

vivo() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
titulo() { echo; echo "== $* =="; }

url_do_tunel() {
  grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$LOGS/tunel.log" 2>/dev/null | head -1 || true
}

parar_tunel() {
  if vivo "$PID_TUNEL"; then
    # Mata o GRUPO: o cloudflared sobe filhos, e matar só o pai deixa um órfão
    # segurando a URL — o próximo `--status` acha que o túnel está bom.
    kill -- -"$(cat "$PID_TUNEL")" 2>/dev/null || kill "$(cat "$PID_TUNEL")" 2>/dev/null || true
    echo "  túnel parado"
  else
    echo "  nenhum túnel meu de pé"
  fi
  rm -f "$PID_TUNEL"
}

# --------------------------------------------------------------------- parar
if [ "$MODO" = "--parar" ]; then
  titulo "parando"
  parar_tunel
  exit 0
fi

# -------------------------------------------------------------------- status
if [ "$MODO" = "--status" ]; then
  titulo "status"
  printf "  banco local:  "
  docker compose ps db --format json 2>/dev/null | grep -q '"Health":"healthy"' \
    && echo "de pé e saudável" || echo "parado"
  printf "  API local:    "
  curl -fsS -o /dev/null --max-time 2 http://localhost:8000/openapi.json \
    && echo "respondendo em :8000" || echo "não responde"
  printf "  túnel:        "
  if vivo "$PID_TUNEL"; then echo "$(url_do_tunel)"; else echo "desligado"; fi
  printf "  imagem:       "
  docker image inspect tutor-api:local >/dev/null 2>&1 \
    && echo "tutor-api:local construída ($(docker image inspect tutor-api:local \
         --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1048576}'))" \
    || echo "não construída"
  printf "  DATABASE_URL: "
  # Só a FORMA, nunca o valor: senha de banco impressa em terminal acaba em
  # histórico e em screenshot.
  if [ -n "${DATABASE_URL:-}" ]; then
    echo "presente no ambiente (host: $(echo "$DATABASE_URL" | sed -E 's#.*@([^:/?]+).*#\1#'))"
  else
    echo "ausente do ambiente"
  fi
  printf "  API na nuvem: "
  if [ -n "${API_PUBLICA:-}" ]; then
    curl -fsS -o /dev/null --max-time 5 "$API_PUBLICA/openapi.json" \
      && echo "respondendo em $API_PUBLICA" || echo "não responde em $API_PUBLICA"
  else
    echo "defina API_PUBLICA=https://... pra eu conferir"
  fi
  exit 0
fi

# --------------------------------------------------------------------- túnel
# Continua existindo porque é o laço de DEV mais rápido que existe aqui: sobe em
# segundos e não paga build de imagem. O que ele não é: hospedagem. A URL é
# efêmera (muda a cada reinício), e `NEXT_PUBLIC_*` só entra em build novo —
# então cada reinício custa um redeploy manual na Vercel. Foi essa fricção que
# motivou o caminho de nuvem acima.
if [ "$MODO" = "--tunel" ]; then
  titulo "1/3 banco"
  docker compose up -d
  printf "esperando o Postgres ficar saudável"
  until docker compose ps db --format json 2>/dev/null | grep -q '"Health":"healthy"'; do
    printf "."; sleep 1
  done
  echo " ok"

  titulo "2/3 API local"
  if curl -fsS -o /dev/null --max-time 2 http://localhost:8000/openapi.json; then
    echo "  já responde em :8000, não subi outra"
  else
    echo "  não está de pé. Suba com:  ./setup.sh --subir"
    exit 1
  fi

  titulo "3/3 túnel público"
  if vivo "$PID_TUNEL"; then
    echo "  já tem túnel meu de pé"
  else
    if [ ! -x "$CLOUDFLARED" ]; then
      cat <<'EOF'
  cloudflared não encontrado. Baixe uma vez:
    mkdir -p ~/.local/bin && curl -fsSL -o ~/.local/bin/cloudflared \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
      && chmod +x ~/.local/bin/cloudflared
EOF
      exit 1
    fi
    : > "$LOGS/tunel.log"
    setsid "$CLOUDFLARED" tunnel --url http://localhost:8000 >> "$LOGS/tunel.log" 2>&1 &
    echo $! > "$PID_TUNEL"
    printf "  esperando a URL aparecer"
    for _ in $(seq 30); do
      # A URL completa, não a palavra "trycloudflare.com": ela já aparece na
      # linha "Requesting new quick Tunnel on trycloudflare.com...", que sai
      # ANTES de a URL existir. Casar com a palavra soltava o break cedo.
      #
      # E o teste é CONDIÇÃO DE `if`, não `[ ... ] && break`: com `set -e`, a
      # forma curta encerra o script na primeira volta em que o teste é falso —
      # ou seja, sempre, porque na primeira volta a URL ainda não existe. Já
      # estava documentado neste arquivo pelo mesmo motivo, noutro laço, e eu
      # reintroduzi o defeito ao reescrever. Fica aqui de novo.
      if [ -n "$(url_do_tunel)" ]; then break; fi
      printf "."; sleep 1
    done
    echo " ok"
  fi

  URL=$(url_do_tunel)
  cat <<EOF

  URL desta sessão: ${URL:-"(não achei — veja $LOGS/tunel.log)"}

  Vercel → Settings → Environment Variables → NEXT_PUBLIC_API_URL = ${URL:-<url acima>}
  Depois: Deployments → ⋯ → Redeploy   (NEXT_PUBLIC_* só entra em build novo)

  Enquanto o túnel estiver de pé, sua API e seu Postgres locais ficam
  acessíveis publicamente por essa URL. Desligue quando terminar:
    ./subir-vercel.sh --parar
EOF
  exit 0
fi

# ================================================================== NUVEM
titulo "1/6 artefatos de deploy"
for f in apps/api/Dockerfile apps/api/.dockerignore render.yaml; do
  [ -f "$f" ] || { echo "  FALTA $f"; exit 1; }
  echo "  ok  $f"
done

titulo "2/6 imagem (build local antes de gastar build no provedor)"
# Construir aqui primeiro é o passo que evita o desperdício caro: build de
# imagem com torch leva minutos, e descobrir um erro de Dockerfile no painel do
# provedor custa o mesmo tempo mais o do fila dele. Se passa aqui, passa lá.
if docker build -q -t tutor-api:local apps/api > "$LOGS/build.log" 2>&1; then
  TAM=$(docker image inspect tutor-api:local --format '{{.Size}}' | awk '{printf "%.0f", $1/1048576}')
  echo "  construída: tutor-api:local — ${TAM} MB"
  # Referência medida: com torch CPU-only e o modelo dentro, a imagem fica na
  # casa de 2 GB. Muito acima disso quase sempre é o torch com CUDA — 2 GB de
  # driver de GPU numa imagem que fixa device="cpu".
  if [ "$TAM" -gt 3500 ]; then
    echo "  ! acima de 3,5 GB. Suspeita: torch com CUDA em vez do índice CPU."
    echo "    confira a primeira linha de pip install no Dockerfile."
  fi
else
  echo "  FALHOU. Últimas linhas de $LOGS/build.log:"
  tail -20 "$LOGS/build.log"
  exit 1
fi

titulo "3/6 banco na nuvem"
if [ -z "${DATABASE_URL:-}" ]; then
  cat <<'EOF'
  DATABASE_URL não está no ambiente, e sem ela não dá pra verificar nada do
  banco. Crie um Postgres COM pgvector (Neon e Supabase têm no plano gratuito;
  o Postgres gerenciado do provedor também serve se tiver a extensão) e:

    export DATABASE_URL='postgresql://...'
    ./subir-vercel.sh

  Não cole a URL aqui nem em nenhum arquivo do repositório: ela tem senha.
EOF
  exit 1
fi
echo "  URL presente (host: $(echo "$DATABASE_URL" | sed -E 's#.*@([^:/?]+).*#\1#'))"

cd apps/api
source .venv/bin/activate

# A GUARDA MAIS IMPORTANTE DESTE SCRIPT. `core/config.py` chama `load_dotenv()`,
# e o `.env` local tem uma DATABASE_URL apontando pro Postgres do docker. Hoje o
# `load_dotenv()` NÃO sobrescreve variável já exportada — então a URL da nuvem
# ganha, e eu conferi RODANDO, não lendo. Mas isso é detalhe de biblioteca, não
# contrato: bastaria alguém escrever `load_dotenv(override=True)` um dia e este
# script passaria a migrar e ingerir no banco LOCAL enquanto imprime o host da
# nuvem na tela. Migração aplicada no lugar errado, calada.
#
# Então a precedência é verificada, comparando o host que o Python VÊ com o que o
# shell exportou.
printf "  o Python vê a mesma URL? "
python - <<'CHECA_URL' || exit 1
import os, re, sys
from core.config import DATABASE_URL as VISTA
def host(u):
    m = re.search(r"@([^:/?]+)", u or "")
    return m.group(1) if m else "(sem host)"
esperado, visto = host(os.environ["DATABASE_URL"]), host(VISTA)
if esperado != visto:
    print(f"NÃO — o shell diz {esperado!r} e core.config diz {visto!r}", file=sys.stderr)
    print("  O .env está vencendo a variável exportada. Parei ANTES de migrar ou",
          file=sys.stderr)
    print("  ingerir qualquer coisa: seria no banco errado.", file=sys.stderr)
    sys.exit(1)
print("sim")
CHECA_URL

# pgvector VERIFICADO, não assumido. Descobrir que o provedor não tem a extensão
# depois de subir a imagem é o tipo de retrabalho que este projeto já pagou.
printf "  pgvector: "
if python - <<'PY'
import sys
import psycopg
from core.config import DATABASE_URL
try:
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
except Exception as e:
    print(f"INDISPONÍVEL — {str(e).strip().splitlines()[0]}", file=sys.stderr)
    sys.exit(1)
PY
then
  echo "disponível"
else
  echo
  echo "  Esse Postgres não tem pgvector, e o projeto inteiro depende dele"
  echo "  (busca híbrida, coluna vector de 768 dimensões). Troque de provedor"
  echo "  ou habilite a extensão antes de continuar."
  exit 1
fi

titulo "4/6 schema"
# O MESMO `migrar.py` de sempre, contra a URL da nuvem. Banco novo recebe as 25
# migrações em ordem; banco com dados e sem livro-razão PARA e pede decisão, que
# é o comportamento certo aqui também — adivinhar num banco remoto é pior, não
# melhor.
if ! python migrar.py; then
  echo
  echo "  parei: o schema do banco na nuvem precisa de uma decisão sua (acima)."
  exit 1
fi

titulo "5/6 corpus"
# A INGESTÃO RODA DAQUI, não dentro do container, e é decisão: o embedding é
# calculado na SUA CPU e só o vetor viaja. Fazer isso no container de produção
# significaria segurar o serviço por minutos num plano pequeno, competindo com
# request de usuário — o mesmo problema que `run_in_threadpool` resolveu no
# upload de material, um nível acima. `ingest.py` pula arquivo já ingerido pelo
# hash, então rodar de novo não duplica nada.
python ingest.py corpus/cp.txt      --disciplina "Direito Penal"            --tipo lei --norma CP
python ingest.py corpus/cf.txt      --disciplina "Direito Constitucional"   --tipo lei --norma CF
python ingest.py corpus/adct.txt    --disciplina "Direito Constitucional"   --tipo lei --norma ADCT --titulo ADCT
python ingest.py corpus/cpp.txt     --disciplina "Direito Processual Penal" --tipo lei --norma CPP --titulo "Código de Processo Penal"
python ingest.py corpus/lei8112.txt --disciplina "Direito Administrativo"   --tipo lei --norma L8112 --titulo "Lei 8.112/1990"
python ingest.py corpus/CF88_Livro_EC91_2016.pdf --disciplina "Direito Constitucional" --tipo historico
python sincronizar.py importar

RESUMO=$(python -c "
from core import db
d = db.query('SELECT count(*) c FROM documento WHERE usuario_id IS NULL')[0]['c']
k = db.query('SELECT count(*) c FROM chunk')[0]['c']
q = db.query('SELECT count(*) c FROM questao')[0]['c']
print(f'{d} documentos · {k} chunks · {q} questões')")
echo "  no banco da nuvem: $RESUMO"

cd "$RAIZ"

titulo "6/6 o que falta, e é só você que pode fazer"
VERCEL_DOMINIO="${VERCEL_DOMINIO:-https://SEU-PROJETO.vercel.app}"
cat <<EOF
O backend está pronto e o banco da nuvem já está migrado e populado. O que
sobra exige a SUA conta — token de infraestrutura não passa por aqui.

  1. Conecte o repositório ao provedor, UMA vez. Com o Blueprint no repo:
       painel do Render → New → Blueprint → escolha este repositório
     Ele lê o render.yaml e cria o serviço. Daí em diante, deploy = git push.

  2. Preencha os três segredos que o Blueprint pede (ele PEDE, não guarda):
       DATABASE_URL   a mesma que você exportou aqui
       GEMINI_API_KEY sua chave do AI Studio
       CORS_ORIGINS   ${VERCEL_DOMINIO}
     JWT_SECRET o provedor gera sozinho — não cole um.

  3. Confirme que a RAM do plano passa de 2 GB. O modelo de embeddings ocupa
     ~1 GB e o torch soma o dele; num plano de 512 MB o processo morre ao
     carregar o modelo e o sintoma é health check falhando SEM erro da
     aplicação no log.

  4. Na Vercel, aponte o front pra API nova:
       Settings → Environment Variables → NEXT_PUBLIC_API_URL = https://<sua-api>
       Deployments → ⋯ → Redeploy      (NEXT_PUBLIC_* só entra em build novo)

  5. Confira daqui, sem abrir o navegador:
       API_PUBLICA=https://<sua-api> ./subir-vercel.sh --status

E uma consequência boa de o banco sair da sua máquina: com DATABASE_URL única,
\`sincronizar.py exportar/importar\` deixa de ser necessário pra alternar entre
máquinas — é o item que o CLAUDE.md já listava como "se essa rotina cansar".
Mesa, edital, conversa e biblioteca, que nunca viajaram no arquivo, passam a
viajar de graça.
EOF
