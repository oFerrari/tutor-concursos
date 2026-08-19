# Backend do tutor, pronto pra rodar fora desta máquina.
#
# POR QUE CONTAINER, E NÃO SERVERLESS
# -----------------------------------
# A Vercel hospeda o frontend e não pode hospedar isto: função serverless tem
# teto de 250 MB descompactados e só o torch passa de 750 MB. E não é excesso
# de dependência — é a decisão de "Pilha": os embeddings rodam LOCAIS, na CPU
# (`intfloat/multilingual-e5-base`, 768 dimensões). Trocar por API de
# embeddings deixaria a imagem em ~150 MB, mas exigiria `ALTER TABLE` na coluna
# vector, reindexar os 4.074 chunks e passar a gastar cota em TODA busca — que
# hoje custa zero. Escolha feita de propósito; ver CLAUDE.md.
#
# AS DUAS LINHAS QUE DECIDEM O TAMANHO DA IMAGEM
# ----------------------------------------------
# 1. `torch` vem do índice CPU-only da PyTorch, instalado ANTES do
#    requirements.txt. Sem isso o pip resolve o `torch` default, que arrasta as
#    bibliotecas CUDA da NVIDIA — mais de 2 GB de driver de GPU numa imagem que
#    nunca vai ver uma GPU. E `core/embeddings.py` fixa `device="cpu"` de
#    propósito (uma GPU incompatível com o build do torch quebra em runtime em
#    vez de nunca ser tocada — está nas Armadilhas de método).
# 2. O MODELO É BAIXADO PARA DENTRO DA IMAGEM, no build. Sem isso o primeiro
#    request em produção dispara download de 1,1 GB antes de responder: o
#    usuário vê a tela girando por minutos e o provedor pode matar o processo
#    por timeout de health check. Pagar isso uma vez no build é o certo.
ARG PYTHON=3.14
FROM python:${PYTHON}-slim

# `libpq5` porque `psycopg[binary]` traz o driver, mas o runtime do Postgres
# ainda é linkado dinamicamente em algumas plataformas; `curl` é o que o
# health check do provedor usa.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PYTHONUNBUFFERED: sem isso o log do uvicorn fica preso no buffer e o painel do
# provedor mostra "nenhum log" enquanto a aplicação já está falando.
# HF_HOME dentro de /app pra o modelo baixado no build ficar numa camada
# previsível, e não em /root/.cache (que alguns provedores montam por cima).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/hf \
    EMBEDDING_MODEL=intfloat/multilingual-e5-base

# Camadas separadas de propósito: torch e requirements mudam raramente, o
# código muda a cada deploy. Invertido, cada correção de uma linha reinstalaria
# 750 MB de torch.
COPY requirements.txt ./
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir -r requirements.txt

# O modelo, no build. Roda o mesmo caminho de código que a aplicação usa
# (`core/embeddings._modelo`) em vez de um `snapshot_download` paralelo, pra o
# que é baixado aqui ser exatamente o que é carregado lá — duas formas de baixar
# o mesmo modelo é como as duas divergem.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
import os; SentenceTransformer(os.environ['EMBEDDING_MODEL'], device='cpu')"

# O corpus VAI na imagem: é lei do Planalto (sem direito autoral, art. 8º IV da
# Lei 9.610) e é o que a ingestão lê. 19 MB, e resolve o mesmo bloqueio que
# resolve no git — reingerir num ambiente novo não depende de baixar de novo.
COPY . .

# Usuário sem privilégio. `chown` no /app inteiro porque o HF_HOME mora lá
# dentro e o processo precisa poder ler o modelo.
RUN useradd --create-home --uid 10001 tutor && chown -R tutor:tutor /app
USER tutor

# `$PORT` porque é assim que Render, Railway e Fly informam a porta; 8000 é o
# default local, pra `docker run` sem variável nenhuma funcionar igual.
ENV PORT=8000
EXPOSE 8000

# `sh -c` pra `$PORT` ser expandido — na forma exec do CMD não é.
# UM worker de propósito: o modelo de embeddings ocupa ~1 GB de RAM e cada
# worker carregaria a própria cópia. Concorrência aqui é do pool de threads do
# FastAPI (é o que `run_in_threadpool` usa pra indexação não travar o event
# loop), não de processos.
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT}"]
