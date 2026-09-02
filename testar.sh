#!/usr/bin/env bash
# Põe um ALUNO SINTÉTICO a conversar com o tutor e mostra na tela, turno a
# turno, o que o sistema fez por dentro: o que virou vetor, o que a busca
# devolveu e o que a resposta tem de errado.
#
#   ./testar.sh                    roteiro das regressões conhecidas + juiz
#   ./testar.sh --pedirmaisquestoes  só o pedido de N questões no chat (4 turnos)
#   ./testar.sh --livre            o aluno é um LLM (conversa que ninguém escreveu)
#   ./testar.sh --livre --persona cético --turnos 8
#   ./testar.sh --falas "oi" "me explica peculato"
#   ./testar.sh --rapido           sem o juiz (uma chamada de LLM a menos)
#   ./testar.sh --pytest           a suíte inteira ANTES da avaliação do chat
#   ./testar.sh --so-pytest        só a suíte, nenhuma chamada de LLM
#   ./testar.sh --mesa "PC-PR Investigador"   avalia com o edital dessa mesa
#   ./testar.sh --cenario listar   os cenários disponíveis (um por risco)
#   ./testar.sh --cenario direto    roda um cenário só
#   ./testar.sh --cenario todos     a coleção inteira: a leitura mais completa
#   ./testar.sh --refazer          roda de novo tudo o que o defeitos.md registrou,
#                                  de uma vez, com o antes × depois de cada um
#   ./testar.sh --reprocessar      re-checa TODAS as conversas já gravadas (grátis)
#   ./testar.sh --placar           histórico de notas, sem gastar LLM
#   ./testar.sh --limpar           apaga a conta descartável e sai
#
# Havendo defeito, sai um `.logs/defeitos.md` de nome FIXO com só o que falhou —
# turno, consulta, trechos, resposta e onde a causa costuma estar. É o arquivo
# pra entregar a um agente de IA: "conserta os defeitos em .logs/defeitos.md".
# O nome não é carimbado justamente pra essa frase não depender de você copiar
# um timestamp da tela.
#
# Roda de QUALQUER pasta do repositório. Qualquer flag que este script não
# conheça é repassada ao avaliar_chat.py, então `./testar.sh --email conta@teste`
# funciona sem precisar ser listada aqui.
#
# POR QUE ELE EXISTE, E POR QUE O PADRÃO É O CHAT E NÃO O PYTEST
# --------------------------------------------------------------
# `pytest` já respondia "o código quebrou?". A pergunta que não tinha comando
# era a outra, e é a que o AGENTS.md manda fazer à mão antes de mexer no prompt:
# "a resposta ficou RUIM?". As duas piores regressões deste projeto passaram
# verdes na suíte, porque texto ruim é texto válido — nada lança exceção quando
# o tutor narra a escada pedagógica ou escreve questão de múltipla escolha no
# chat.
#
# Um script chamado `testar.sh` que não roda a suíte seria uma armadilha, então ela
# está aqui em `--pytest`. Mas o padrão é o chat: é o que ninguém rodava por
# depender de lembrar, que é exatamente o problema que o commit anterior
# resolveu pro sincronismo. Automação que depende de lembrar não é automação.
#
# CUSTA COTA DO GEMINI. O padrão são 7 chamadas (6 turnos + 1 juiz); `--livre`
# dobra a parte dos turnos, porque o aluno também é um modelo. Está dito na
# tela antes de começar, junto do que vai ser gasto.
set -euo pipefail

RAIZ=$(git rev-parse --show-toplevel 2>/dev/null) \
  || RAIZ=$(cd "$(dirname "$0")" && pwd)
cd "$RAIZ"

MODO_JUIZ="--juiz"
RODAR_PYTEST=0
SO_PYTEST=0
SO_PLACAR=0
ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --livre)      ARGS+=("--aluno" "llm"); shift ;;
    # Atalho pedido pelo nome: testa só o pedido de N questões no chat.
    --pedirmaisquestoes) ARGS+=("--cenario" "quantas"); MODO_JUIZ=""; shift ;;
    --rapido)     MODO_JUIZ=""; shift ;;
    --pytest)     RODAR_PYTEST=1; shift ;;
    --so-pytest)  SO_PYTEST=1; RODAR_PYTEST=1; shift ;;
    # `--falas` é o nome amigável de `--roteiro`, e consome o resto da linha:
    # são falas com espaço, e exigir aspas já é o bastante.
    --falas)      shift; ARGS+=("--roteiro" "$@"); break ;;
    --limpar)     MODO_JUIZ=""; ARGS+=("--limpar"); shift ;;
    # --placar não conversa com ninguém: nem banco, nem chave, nem LLM. Sai
    # antes de tudo isso pra poder ser consultado com o Docker desligado.
    --placar)     MODO_JUIZ=""; SO_PLACAR=1; ARGS+=("--placar"); shift ;;
    # Não toca em banco nem LLM: sai pelo mesmo atalho do --placar.
    --reprocessar) MODO_JUIZ=""; SO_PLACAR=3; shift ;;
    # --refazer traz o juiz de cada receita gravada; não force o daqui.
    --refazer)    MODO_JUIZ=""; ARGS+=("--refazer"); shift ;;
    # `--cenario listar` não gasta LLM nem precisa de banco: sai pelo mesmo
    # atalho do --placar.
    --cenario)    [ "${2:-}" = "listar" ] && SO_PLACAR=2
                  ARGS+=("--cenario" "${2:-}"); shift 2 ;;
    -h|--help)    sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            ARGS+=("$1"); shift ;;
  esac
done

# ------------------------------------------------------------------- ambiente
if [ ! -d "$RAIZ/apps/api/.venv" ]; then
  echo "não há venv ainda — rode ./setup.sh primeiro." >&2
  exit 1
fi
PY="$RAIZ/apps/api/.venv/bin/python"

if [ "$SO_PLACAR" = 1 ]; then
  cd "$RAIZ/apps/api"
  exec "$PY" avaliar_chat.py --placar
fi
if [ "$SO_PLACAR" = 2 ]; then
  cd "$RAIZ/apps/api"
  exec "$PY" avaliar_chat.py --cenario listar
fi
if [ "$SO_PLACAR" = 3 ]; then
  cd "$RAIZ/apps/api"
  exec "$PY" avaliar_chat.py --reprocessar
fi

# O banco é pré-requisito de tudo aqui (conta descartável, conversa, busca
# vetorial). Subir sozinho é melhor que falhar com `connection refused`, que
# manda a pessoa depurar Postgres quando ela só queria testar o chat.
if ! docker compose ps --format '{{.Name}} {{.State}}' 2>/dev/null | grep -q 'tutor-db running'; then
  echo "== subindo o banco =="
  docker compose up -d
  for _ in $(seq 1 30); do
    docker exec tutor-db pg_isready -q 2>/dev/null && break
    sleep 1
  done
fi

# --------------------------------------------------------------------- pytest
if [ "$RODAR_PYTEST" = 1 ]; then
  echo "== suíte (pytest) =="
  ( cd "$RAIZ/apps/api" && "$RAIZ/apps/api/.venv/bin/pytest" -q ) || {
    echo
    echo "a suíte falhou. Conserte isso antes de julgar a QUALIDADE das respostas:" >&2
    echo "avaliar o texto de um sistema quebrado é medir a coisa errada." >&2
    exit 1
  }
  echo
  [ "$SO_PYTEST" = 1 ] && exit 0
fi

# ------------------------------------------------------- a chave, antes do resto
# Falhar aqui, ANTES de mexer no banco e imprimir cabeçalho, é o que evita a
# rodada que morre no primeiro turno depois de você já estar olhando a tela.
if ! grep -qE '^GEMINI_API_KEY=.+' "$RAIZ/apps/api/.env" 2>/dev/null; then
  echo "GEMINI_API_KEY não está no apps/api/.env — a avaliação do chat precisa de LLM." >&2
  echo "Só a suíte, sem LLM: ./testar.sh --so-pytest" >&2
  exit 1
fi

# O `cd` NÃO é cosmético: `core/config.py` chama `load_dotenv()` sem caminho, e
# essa busca começa no diretório ATUAL e sobe. Rodando da raiz, o
# `apps/api/.env` fica invisível e tudo cai no default — GEMINI_API_KEY vazia,
# banco na URL de fábrica. O sintoma seria "LLM indisponível" no primeiro turno,
# com a chave lá, certa, no arquivo. Mesmo motivo do `cd` do ./tutor.
cd "$RAIZ/apps/api"
exec "$PY" avaliar_chat.py ${MODO_JUIZ:+$MODO_JUIZ} "${ARGS[@]+"${ARGS[@]}"}"
