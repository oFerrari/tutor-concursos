#!/usr/bin/env python3
"""
Aplica as migrações de `db/` que ainda não rodaram NESTE banco.

    python migrar.py                 aplica o que falta (é o caminho normal)
    python migrar.py --listar        só mostra o estado, não toca em nada
    python migrar.py --adotar        banco JÁ EM DIA: registra sem executar

POR QUE ISTO EXISTE
-------------------
`git pull` traz os ARQUIVOS de migração e não aplica nenhum. O
`docker-entrypoint-initdb.d` só roda em volume NOVO; volume que já existe ignora
tudo. Então chegar em outra máquina, dar pull e subir a aplicação deixava o
código novo conversando com o schema velho — e o modo de falha é o pior que
existe: **a aplicação sobe** e quebra depois, num lugar sem relação óbvia com o
schema. O CLAUDE.md registra o que isso já custou (o módulo de
Simulados/Estatísticas inteiro rodando contra a view antiga, `stats --json`
estourando em `Decimal`, `chat.py simulado` batendo em tabela inexistente) até
alguém tentar de verdade.

UM MECANISMO SÓ, E ESTE É ELE
-----------------------------
O mount do `docker-entrypoint-initdb.d` SAIU do `docker-compose.yml` junto com
este arquivo, e isso é a parte importante do desenho. Com os dois mecanismos
vivos, um banco novo teria sido preenchido pelo initdb (que roda tudo, em ordem
alfabética) e o runner não teria como distinguir isso de uma máquina atrasada
onde só parte rodou. Os dois estados são indistinguíveis olhando o banco, e
adivinhar errado significa pular migração calada ou explodir no primeiro
`ADD COLUMN`. Matar o segundo mecanismo é o que torna a pergunta respondível.

TRÊS ESTADOS, E O DO MEIO SE RECUSA A SUPOR
-------------------------------------------
  · sem `documento`     -> banco vazio. Aplica tudo, do 001 em diante.
  · com `documento`,
    sem livro-razão     -> máquina da era anterior a este script. PARA e
                           explica. Marcar tudo como aplicado seria catastrófico
                           num banco atrasado (pularia a 021 e a 022 caladas);
                           tentar aplicar tudo explode no primeiro ADD COLUMN.
                           Quem sabe em que estado o banco está é a pessoa, e é
                           ela que decide, com `--adotar` ou `down -v`.
  · com livro-razão     -> caminho normal: aplica o que falta.

Recusar-se a adivinhar não é indecisão: aqui, adivinhar errado perde dado.

TRANSAÇÃO POR MIGRAÇÃO
----------------------
`core/db.py` abre a conexão com `autocommit=True` — ótimo pro caminho normal do
app, e inútil aqui: sem transação, migração que falha no meio deixa o schema
meio-aplicado e sem nada pra reverter. É exatamente a armadilha que o
`reingest.py` documenta (DELETE antes de validar o INSERT, `autocommit=True`,
zero chunks e nada pra desfazer). Este script abre conexão própria, sem
autocommit, e o registro no livro-razão entra na MESMA transação do DDL: o
banco nunca fica com a migração aplicada e não registrada, nem o contrário.
"""
import argparse
import hashlib
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from core.config import DATABASE_URL

VERSAO = "migrar-v1"

DIR = Path(__file__).parent / "db"

# Tabela que existe desde a 001. Serve de sinal de "este banco já foi usado" —
# mais honesto que contar tabelas, que muda a cada migração.
SENTINELA = "documento"

DDL_LIVRO = """
CREATE TABLE IF NOT EXISTS migracao (
  nome        TEXT PRIMARY KEY,
  checksum    TEXT NOT NULL,
  aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def arquivos() -> list[Path]:
    """
    Ordem = nome do arquivo, e ela é DECLARADA em vez de acidental.

    Havia (e há) número duplicado neste diretório: 018_edital_cargo e
    018_simulado_resumavel, 019_material_do_aluno e 019_simulado_nome. O initdb
    resolvia isso por sorte, porque ordenar alfabeticamente calhava de dar uma
    sequência que funciona. Aqui a regra é a mesma, só que escrita — e
    `--listar` mostra a ordem inteira, pra que ninguém precise confiar na sorte
    duas vezes.
    """
    return sorted(DIR.glob("*.sql"))


def checksum(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]


def conectar() -> psycopg.Connection:
    """Sem autocommit — ver o docstring do módulo. Não reusa `core.db.conn()`
    de propósito: aquela conexão é autocommit por decisão do projeto, e mudar
    isso pra caber aqui mexeria no comportamento de toda rota."""
    return psycopg.connect(DATABASE_URL, autocommit=False, row_factory=dict_row)


def _existe(cur, tabela: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS t", (tabela,))
    return cur.fetchone()["t"] is not None


def _registradas(cur) -> dict[str, str]:
    if not _existe(cur, "migracao"):
        return {}
    cur.execute("SELECT nome, checksum FROM migracao")
    return {l["nome"]: l["checksum"] for l in cur.fetchall()}


def _avisar_editadas(registradas: dict[str, str], todos: list[Path]) -> None:
    """
    Migração aplicada e depois editada: o arquivo diz uma coisa, o banco tem
    outra. AVISA e segue — corrigir exigiria adivinhar o que a edição
    pretendia (o efeito já está no banco? é só comentário?), e adivinhar aqui
    é o que este script existe pra não fazer.

    Mesma classe do `documento.hash` do CP, que ficou dias desatualizado porque
    o corpus mudou depois da ingestão e nada comparava.
    """
    for p in todos:
        antigo = registradas.get(p.name)
        if antigo and antigo != checksum(p):
            print(f"  ! {p.name} foi EDITADO depois de aplicado "
                  f"(banco: {antigo}, arquivo: {checksum(p)})")
            print("    o efeito da edição NÃO está neste banco. Se ela importa, "
                  "faça uma migração nova.")


def listar() -> int:
    todos = arquivos()
    with conectar() as c, c.cursor() as cur:
        tem_schema = _existe(cur, SENTINELA)
        registradas = _registradas(cur)
        tem_livro = _existe(cur, "migracao")

    print(f"migrar {VERSAO} · {len(todos)} arquivo(s) em db/")
    print(f"banco: schema {'presente' if tem_schema else 'VAZIO'} · "
          f"livro-razão {'presente' if tem_livro else 'AUSENTE'} · "
          f"{len(registradas)} registrada(s)\n")
    for p in todos:
        marca = "ok " if p.name in registradas else "PENDENTE"
        print(f"  [{marca:>8}] {p.name}")
    _avisar_editadas(registradas, todos)
    pendentes = [p for p in todos if p.name not in registradas]
    print(f"\n{len(pendentes)} pendente(s)")
    return 0


def adotar(confirmado: bool) -> int:
    """
    "Este banco está em dia; registre o que existe, sem executar nada."

    Passo de uma vez só, pra sair da era em que o controle era humano. Lista o
    que vai marcar ANTES de marcar, porque marcar migração que na verdade não
    rodou é criar exatamente o silêncio que o livro-razão vem apagar — só que
    agora com aparência de controle, que é pior.
    """
    todos = arquivos()
    with conectar() as c, c.cursor() as cur:
        if not _existe(cur, SENTINELA):
            print("este banco está VAZIO — não há o que adotar. "
                  "Rode `python migrar.py` e ele aplica tudo.")
            return 1
        cur.execute(DDL_LIVRO)
        registradas = _registradas(cur)
        novas = [p for p in todos if p.name not in registradas]
        if not novas:
            print("nada a adotar: todas as migrações já estão registradas.")
            c.commit()
            return 0

        print("vou REGISTRAR (sem executar) estas migrações como já aplicadas:\n")
        for p in novas:
            print(f"  {p.name}")
        print("\nSó faça isso se este banco JÁ tem o efeito de TODAS elas.")
        print("Se ele está atrasado, o certo é `docker compose down -v` "
              "(perde os dados) e depois `python migrar.py`.")

        if not confirmado:
            try:
                resp = input("\nregistrar? [digite 'sim'] ")
            except EOFError:
                resp = ""
            if resp.strip().lower() != "sim":
                print("nada foi feito.")
                return 1

        for p in novas:
            cur.execute(
                "INSERT INTO migracao (nome, checksum) VALUES (%s, %s) "
                "ON CONFLICT (nome) DO NOTHING",
                (p.name, checksum(p)),
            )
        c.commit()
    print(f"\n{len(novas)} migração(ões) registrada(s). "
          "Daqui pra frente `python migrar.py` cuida sozinho.")
    return 0


def aplicar() -> int:
    todos = arquivos()
    if not todos:
        print(f"nenhum .sql em {DIR} — nada a fazer.")
        return 0

    with conectar() as c, c.cursor() as cur:
        tem_schema = _existe(cur, SENTINELA)
        tem_livro = _existe(cur, "migracao")

        # O estado do meio: banco usado, era anterior a este script. Não supõe.
        if tem_schema and not tem_livro:
            print("Este banco tem dados mas nunca foi controlado por migrar.py.\n")
            print("Não vou adivinhar o que já rodou: marcar tudo como aplicado")
            print("pularia migração de verdade num banco atrasado, e aplicar tudo")
            print("quebra no primeiro ALTER TABLE de coluna que já existe.\n")
            print("Escolha um caminho:\n")
            print("  banco EM DIA (é a máquina onde você vem trabalhando):")
            print("    python migrar.py --adotar\n")
            print("  banco ATRASADO ou você não tem certeza (recria do zero,")
            print("  PERDE os dados locais — o progresso volta pelo git):")
            print("    docker compose down -v && docker compose up -d")
            print("    python migrar.py && python sincronizar.py importar\n")
            print("  ver o que existe antes de decidir:")
            print("    python migrar.py --listar")
            return 2

        cur.execute(DDL_LIVRO)
        registradas = _registradas(cur)
        _avisar_editadas(registradas, todos)
        pendentes = [p for p in todos if p.name not in registradas]

        if not pendentes:
            print(f"banco em dia · {len(registradas)} migração(ões) aplicada(s), "
                  "nenhuma pendente.")
            c.commit()
            return 0

        print(f"{len(pendentes)} migração(ões) pendente(s):")
        for p in pendentes:
            print(f"  aplicando {p.name} … ", end="", flush=True)
            try:
                # DDL e registro na MESMA transação: o banco nunca fica com a
                # migração aplicada e não registrada, nem o contrário.
                cur.execute(p.read_text())
                cur.execute(
                    "INSERT INTO migracao (nome, checksum) VALUES (%s, %s)",
                    (p.name, checksum(p)),
                )
                c.commit()
            except psycopg.Error as e:
                c.rollback()
                print("FALHOU")
                print(f"\n{p.name} não foi aplicada e NADA dela ficou no banco "
                      "(transação revertida).")
                print(f"erro: {str(e).strip()}")
                print("\nAs anteriores continuam aplicadas e registradas — "
                      "conserte esta e rode de novo.")
                return 1
            print("ok")

    print(f"\npronto · {len(pendentes)} aplicada(s).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Aplica as migrações de db/ que faltam neste banco.")
    ap.add_argument("--listar", action="store_true",
                    help="mostra o estado sem tocar em nada")
    ap.add_argument("--adotar", action="store_true",
                    help="banco já em dia: registra as migrações sem executá-las")
    ap.add_argument("--sim", action="store_true",
                    help="não pergunta na confirmação do --adotar")
    a = ap.parse_args()

    try:
        if a.listar:
            return listar()
        if a.adotar:
            return adotar(a.sim)
        return aplicar()
    except psycopg.OperationalError as e:
        print(f"não deu pra falar com o Postgres: {str(e).strip()}")
        print("o container está de pé? `docker compose up -d`")
        return 1


if __name__ == "__main__":
    sys.exit(main())
