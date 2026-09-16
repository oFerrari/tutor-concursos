#!/usr/bin/env bash
# O que o ALUNO pediu pra melhorar, num arquivo só, pronto pra entregar.
#
#   ./melhorias.sh                 escreve .logs/melhorias.md com a fila pendente
#   ./melhorias.sh --fechar 3 7    marca esses itens como resolvidos
#   ./melhorias.sh --limite 10     só os 10 mais recentes
#
# A fila se enche sozinha: dentro do chat, `/erro` e `/feedback` gravam o
# bilhete PRESO à resposta que ele comenta (migração 029). Este script é a outra
# ponta — em vez de abrir o banco, achar a conversa, copiar a resposta e montar
# o contexto à mão, sai um markdown com o relato, a resposta reclamada, as
# fontes daquele turno e os turnos anteriores.
#
# O NOME DO ARQUIVO É FIXO, e é pelo mesmo motivo do `.logs/defeitos.md`: a
# frase que se entrega a um agente de IA —
#
#     "conserta o que está em .logs/melhorias.md"
#
# — não pode depender de você copiar um timestamp da tela. E a AUSÊNCIA do
# arquivo é o sinal de fila vazia: um markdown velho dizendo "3 pendentes"
# depois de tudo resolvido é pior que arquivo nenhum.
#
# Roda de QUALQUER pasta do repositório e não gasta cota de LLM: é leitura de
# banco. Qualquer flag não listada aqui vai direto pro melhorias.py.
set -euo pipefail

RAIZ=$(git rev-parse --show-toplevel 2>/dev/null) \
  || RAIZ=$(cd "$(dirname "$0")" && pwd)
cd "$RAIZ"

if [ ! -d apps/api/.venv ]; then
  echo "não há venv ainda — rode ./setup.sh primeiro." >&2
  exit 1
fi

saida=$("$RAIZ/tutor" melhorias.py "$@")
echo "$saida"

# A DICA SÓ APARECE QUANDO HÁ O QUE ENTREGAR. Imprimir "cole isto no Claude"
# numa fila vazia é ruído que ensina a ignorar a saída do script.
if [ -f "$RAIZ/.logs/melhorias.md" ] && [[ "$saida" != *"fechado(s)"* ]]; then
  cat <<'DICA'

pra entregar a um agente de IA, dentro do repositório:

  conserta o que está em .logs/melhorias.md

depois de consertar, feche os itens:  ./melhorias.sh --fechar <id> [<id>...]
DICA
fi
