import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL    = os.getenv("DATABASE_URL", "postgresql://tutor:tutor@localhost:5433/tutor")
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
# MEDIDO em 04/09/2026, plano gratuito: `gemini-3.5-flash-lite` devolveu 503 em
# praticamente toda chamada, e uma pergunta trivial de 10 tokens levava 33-42s
# quando passava. `gemini-3.1-flash-lite` no mesmo minuto: 1,6s / 3,8s / 10,2s.
# O default aponta pro que responde — trocar isto é uma linha no .env.
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# MODELOS DE RESERVA, tentados em ordem quando o principal devolve 5xx.
#
# O 503 do plano gratuito é por CAPACIDADE do modelo, não da conta — medido no
# mesmo minuto: `gemini-3.5-flash-lite` deu 503 em duas tentativas seguidas
# enquanto `gemini-3.1-flash-lite` respondeu em 2,1s. Repetir o mesmo modelo
# (o que `_post` fazia) espera 13s de backoff pra bater na mesma parede;
# trocar de modelo tem chance real de passar.
#
# Ordem: o principal primeiro, depois os irmãos mais próximos em capacidade. É
# uma LISTA e não uma regra esperta de propósito — quando o Google aposentar um
# nome, dá pra consertar no .env sem tocar em código.
GEMINI_RESERVAS = [m.strip() for m in os.getenv(
    "GEMINI_RESERVAS", "gemini-3.5-flash,gemini-flash-lite-latest,gemini-3.5-flash-lite"
).split(",") if m.strip()]
OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen3:8b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")

JWT_SECRET       = os.getenv("JWT_SECRET", "")
CLI_USUARIO_EMAIL = os.getenv("CLI_USUARIO_EMAIL", "estudante@local")

# origens que podem chamar a API do navegador (CORS). Lista separada por
# vírgula no .env; default cobre o Next.js local (apps/web, porta padrão).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]

# Intervalos da revisão espaçada, em dias. O índice é a coluna questao.caixa.
INTERVALOS = [1, 3, 7, 15, 30, 90]
