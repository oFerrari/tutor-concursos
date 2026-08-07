"""
Autenticação — hash de senha, token de sessão, e o usuário fixo da CLI.

Por que JWT e não sessão em tabela: mono-processo hoje (api.py e chat.py
não compartilham estado em memória), então não há onde guardar sessão sem
ser o próprio banco — e um token assinado evita mais uma tabela só para
isso. Trade-off aceito: revogar um token antes de expirar não existe (não
tem como invalidar sem lista de bloqueio); para uso pessoal/pequeno grupo,
expiração curta o suficiente (ver EXPIRA_HORAS) cobre o risco.

bcrypt, não SHA/MD5: hash de senha exige custo computacional deliberado
(salt automático, fator de custo ajustável) — hash rápido é o que torna
força-bruta de senha vazada viável.
"""
import bcrypt
import jwt

from . import db
from .config import JWT_SECRET

VERSAO = "auth-v1"

ALGORITMO = "HS256"
EXPIRA_HORAS = 24 * 7   # uma semana — uso pessoal/pequeno grupo, não banco


class ErroAuth(Exception):
    pass


def _checar_secret() -> None:
    if not JWT_SECRET:
        raise ErroAuth("JWT_SECRET não configurado no .env — gere com "
                       "`python -c \"import secrets; print(secrets.token_hex(32))\"`")


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def confere_senha(senha: str, hash_: str) -> bool:
    if not hash_:
        return False
    return bcrypt.checkpw(senha.encode("utf-8"), hash_.encode("utf-8"))


def registrar(email: str, senha: str) -> dict:
    email = email.strip().lower()
    if len(senha) < 8:
        raise ErroAuth("senha precisa de pelo menos 8 caracteres")
    existente = db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": email})
    if existente:
        raise ErroAuth(f"já existe conta com o email {email}")
    r = db.exec1(
        "INSERT INTO usuario (email, senha_hash) VALUES (%(e)s, %(h)s) RETURNING id",
        {"e": email, "h": hash_senha(senha)},
    )
    return {"id": r["id"], "email": email}


def autenticar(email: str, senha: str) -> dict:
    u = db.exec1("SELECT id, email, senha_hash FROM usuario WHERE email = %(e)s",
                 {"e": email.strip().lower()})
    if not u or not confere_senha(senha, u["senha_hash"]):
        # Mesma mensagem pra email inexistente e senha errada — dizer
        # "email não existe" confirma pra quem tenta adivinhar contas.
        raise ErroAuth("email ou senha incorretos")
    return {"id": u["id"], "email": u["email"]}


def emitir_token(usuario_id: int) -> str:
    _checar_secret()
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc)
    payload = {"usuario_id": usuario_id, "iat": agora, "exp": agora + timedelta(hours=EXPIRA_HORAS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITMO)


def usuario_id_do_token(token: str) -> int:
    _checar_secret()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITMO])
    except jwt.PyJWTError as e:
        raise ErroAuth(f"token inválido ou expirado: {e}")
    return payload["usuario_id"]


def usuario_da_cli(email: str) -> int:
    """
    A CLI não faz login — ela é UMA pessoa na sua própria máquina. Resolve
    (ou cria, sem senha usável) o usuário pelo email do .env, pra chat.py
    ter um usuario_id sem precisar de fluxo de auth. Login real (senha)
    só existe pelo caminho da API, pra quem for usar o futuro frontend.
    """
    email = email.strip().lower()
    u = db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": email})
    if u:
        return u["id"]
    r = db.exec1(
        "INSERT INTO usuario (email, senha_hash) VALUES (%(e)s, '') RETURNING id",
        {"e": email},
    )
    return r["id"]
