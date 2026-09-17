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
    sem livro-razão     -> máquina da era anterior a este script. MEDE o schema
                           (bloco SONDAS): registra o que o banco comprovadamente
                           já tem e aplica só o resto. Antes ele parava aqui e
                           mandava a pessoa escolher entre `--adotar` (que pularia
                           migração de verdade num banco atrasado) e `down -v`
                           (que perde mesa, edital e conversa, nada disso viaja
                           no `sincronizar.py`) — duas respostas erradas pro caso
                           real, que era um banco atrasado E com dados. A recusa
                           a supor continua: medir não é supor. Só volta a
                           perguntar se faltar sonda pra alguma migração.
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

VERSAO = "migrar-v2"

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


# ---------------------------------------------------------------- sondas
# Cada migração da ERA ANTERIOR ao livro-razão tem aqui uma pergunta que o
# banco sabe responder: "o efeito principal deste arquivo está presente?".
#
# É isto que substitui o "decida você" que este script imprimia no estado do
# meio. A recusa a SUPOR continua de pé — o que mudou é que existe uma terceira
# saída além de supor e de perguntar: MEDIR. Um banco de 2026 não precisa que
# ninguém lembre se rodou a 021 na mão; a coluna está lá ou não está.
#
# A sonda é conservadora e checa o efeito PRINCIPAL, não todos. Errar pro lado
# de "não aplicada" é barato: o DDL explode no ADD COLUMN duplicado, a
# transação inteira volta e o script diz o que houve. Errar pro lado de
# "aplicada" é o caro (pula calada), e por isso a sonda aponta pro objeto que a
# migração existe pra criar, nunca pra um detalhe periférico.
#
# Arquivo NOVO não precisa entrar aqui: a partir da 023 o livro-razão responde
# sozinho, e este mapa só é consultado em banco que ainda não tem livro-razão
# nenhum. Migração sem sonda NESSE banco é justamente o caso em que o script
# volta a parar e perguntar — porque aí ele realmente não sabe.
COLUNA = ("SELECT 1 FROM information_schema.columns "
          "WHERE table_name = %s AND column_name = %s")
TABELA = "SELECT 1 WHERE to_regclass(%s) IS NOT NULL"
CHECK_COM = ("SELECT 1 FROM pg_constraint WHERE conname = %s "
             "AND pg_get_constraintdef(oid) LIKE %s")
FK_CASCADE = "SELECT 1 FROM pg_constraint WHERE conname = %s AND confdeltype = 'c'"

SONDAS: dict[str, tuple[str, tuple]] = {
    "001_schema.sql":                (TABELA, ("documento",)),
    "002_rubrica_secao.sql":         (COLUNA, ("chunk", "rubrica")),
    "003_embedding_cache.sql":       (TABELA, ("embedding_cache",)),
    "004_simulado.sql":              (TABELA, ("simulado",)),
    "005_desempenho_json.sql":       (COLUNA, ("v_desempenho_disciplina", "cobertura_pct")),
    "006_tipo_historico.sql":        (CHECK_COM, ("documento_tipo_check", "%historico%")),
    "007_edital.sql":                (TABELA, ("edital",)),
    "008_usuario.sql":               (TABELA, ("progresso",)),
    "009_cascade_usuario.sql":       (FK_CASCADE, ("tentativa_usuario_id_fkey",)),
    "010_mesa.sql":                  (TABELA, ("mesa",)),
    "011_edital_rascunho.sql":       (TABELA, ("edital_rascunho",)),
    "012_questao_tipo.sql":          (COLUNA, ("questao", "gabarito_ce")),
    "013_contexto.sql":              (TABELA, ("contexto",)),
    "014_conversa.sql":              (TABELA, ("conversa",)),
    "015_perfil.sql":                (COLUNA, ("usuario", "perfil")),
    "016_mensagem_evento.sql":       (CHECK_COM, ("mensagem_autor_check", "%evento%")),
    "017_mesa_disciplinas.sql":      (COLUNA, ("mesa", "disciplinas_manuais")),
    "018_edital_cargo.sql":          (COLUNA, ("edital", "cargo")),
    "018_simulado_resumavel.sql":    (COLUNA, ("simulado", "questao_ids")),
    "019_material_do_aluno.sql":     (COLUNA, ("documento", "usuario_id")),
    "019_simulado_nome.sql":         (COLUNA, ("simulado", "nome")),
    "020_material_classificado.sql": (COLUNA, ("documento", "assunto")),
    "021_biblioteca_por_mesa.sql":   (COLUNA, ("documento", "mesa_id")),
    "022_conceito_faltante.sql":     (COLUNA, ("tentativa", "conceito_faltante")),
    "023_migracao.sql":              (TABELA, ("migracao",)),
    "030_telemetria_llm.sql":        (TABELA, ("telemetria_llm",)),
    "031_estudo_teoria.sql":         (TABELA, ("estudo_teoria",)),
}


def _ja_aplicada(cur, nome: str) -> bool | None:
    """True/False pela sonda; None quando não existe sonda pra este arquivo."""
    sonda = SONDAS.get(nome)
    if sonda is None:
        return None
    sql, params = sonda
    cur.execute(sql, params)
    return cur.fetchone() is not None


def adotar_por_medicao(cur, todos: list[Path]) -> list[Path] | None:
    """
    Estado do meio, resolvido MEDINDO: registra o que o banco comprovadamente
    já tem e devolve o resto pra ser aplicado pelo caminho normal.

    Devolve None quando alguma migração não tem sonda — aí o script volta a
    parar e perguntar, que é a resposta honesta pra pergunta que ele não sabe
    responder.
    """
    sem_sonda = [p.name for p in todos if p.name not in SONDAS]
    if sem_sonda:
        print("não sei medir estas migrações (faltam em SONDAS):")
        for n in sem_sonda:
            print(f"  {n}")
        return None

    # Medir ANTES de criar o livro-razão, e a ordem é o ponto: a sonda da 023 é
    # a existência da tabela `migracao`, e criá-la primeiro faria ela medir o
    # que este próprio script acabou de fazer — 023 sempre "já aplicada", e o
    # COMMENT do arquivo nunca rodaria. Peguei rodando o teste C, não lendo.
    presentes = [p for p in todos if _ja_aplicada(cur, p.name)]
    faltando = [p for p in todos if p not in presentes]
    cur.execute(DDL_LIVRO)

    print("livro-razão ausente — MEDINDO o schema em vez de supor:\n")
    for p in todos:
        print(f"  [{'ja no banco' if p in presentes else 'FALTA':>11}] {p.name}")
    for p in presentes:
        cur.execute(
            "INSERT INTO migracao (nome, checksum) VALUES (%s, %s) "
            "ON CONFLICT (nome) DO NOTHING",
            (p.name, checksum(p)),
        )
    print(f"\n{len(presentes)} registrada(s) como já aplicada(s) · "
          f"{len(faltando)} a aplicar agora.\n")
    return faltando


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

        # O estado do meio: banco usado, era anterior a este script. Ele não
        # supõe — MEDE (ver o bloco de sondas). Só volta a parar e perguntar
        # quando a medição não cobre alguma migração, que é o único caso em que
        # a pergunta é mesmo da pessoa.
        if tem_schema and not tem_livro:
            pendentes = adotar_por_medicao(cur, todos)
            if pendentes is None:
                print("\nEste banco tem dados mas nunca foi controlado por migrar.py,")
                print("e eu não consigo medir tudo. Escolha um caminho:\n")
                print("  banco EM DIA:   python migrar.py --adotar")
                print("  banco ATRASADO: docker compose down -v && docker compose up -d")
                print("                  python migrar.py && python sincronizar.py importar")
                print("  ver o estado:   python migrar.py --listar")
                return 2
            c.commit()
            registradas = _registradas(cur)
            _avisar_editadas(registradas, todos)
        else:
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
