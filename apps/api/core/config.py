import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL    = os.getenv("DATABASE_URL", "postgresql://tutor:tutor@localhost:5433/tutor")
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
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
