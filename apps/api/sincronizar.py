#!/usr/bin/env python3
"""
Sincroniza o ESTADO INTEIRO do tutor entre máquinas, via arquivo no repositório.

    python sincronizar.py estado
    python sincronizar.py exportar     # antes de sair de uma máquina
    python sincronizar.py importar     # ao chegar na outra

Os hooks de `.githooks/` chamam os dois sozinhos (exporta no commit, importa
no pull), então na prática ninguém digita isto — ver `docs/DECISOES.md`.

O QUE VIAJA
-----------
Tudo o que uma pessoa produziu usando o sistema, e nada que o sistema saiba
reconstruir sozinho:

    usuario (com senha_hash e perfil)   conversa + mensagem
    mesa                                 simulado
    edital + topico                      progresso + tentativa
    contexto + questao                   documento do ALUNO + seus chunks
                                         erro_caderno (RECALCULADO, não copiado)

NÃO viajam os chunks e embeddings da LEI: são deriváveis do texto em `corpus/`
(que está no git) e reingerir custa segundos com o cache. Levá-los inflaria o
arquivo em dezenas de MB de vetor que o `ingest.py` recria igual.

POR QUE O PACOTE VIROU MULTIUSUÁRIO (v2 -> v3)
----------------------------------------------
O v2 exportava UM usuário, o `CLI_USUARIO_EMAIL`. Isso quebrava o caso real:
a CLI usa um email e a TELA usa outro, e o pacote levava só o primeiro — mesas
criadas no frontend nunca viajavam, e o importar as escrevia num terceiro
usuário. Agora o pacote leva todas as contas locais e cada dado pessoal
aponta pro EMAIL do dono, não pra um id que só existe naquele banco.

A senha_hash viaja porque sem ela a conta chega na outra máquina sem login
possível — e "o sistema vem 100%" inclui conseguir entrar na tela. É bcrypt
(não a senha), o repositório é privado, e este projeto por decisão não tem
dado de empresa nenhum. Quem não quiser: `exportar --sem-senha`.

MATERIAL DO ALUNO: O TEXTO VIAJA, O PDF NÃO
-------------------------------------------
`acervo/` está fora do git de propósito (PDF de cursinho, material pago), e
`documento.origem` guarda só o NOME do arquivo. Então material do aluno só
pode viajar de duas formas: levando o PDF (contraria a decisão do .gitignore)
ou levando os CHUNKS de texto já extraídos. Vai a segunda: é o que o RAG usa
de verdade, e a outra máquina recalcula o embedding em CPU local sem precisar
do arquivo original.

Consequência que precisa estar dita: o TEXTO do seu material passa a ficar no
repositório. Em repositório privado, para uso pessoal. Quem não quiser:
`exportar --sem-material` — a linha do documento viaja mesmo assim, marcada
`status='falha'`, pra biblioteca não mentir dizendo que está indexada.

A ARMADILHA DOS IDs
-------------------
Nenhum id sequencial atravessa: cada referência viaja por identidade natural.

    usuario     email                          questao    sha256 do enunciado
    mesa        (email, nome)                   contexto   sha256 do texto
    edital      (mesa, titulo, criado_em)       simulado   (email, criado_em)
    documento   (email, hash do arquivo)        conversa   (email, criada_em)
    chunk       (hash do documento, ordem)      tentativa  (email, questao, criada_em)

`questao.fonte_chunks` guarda ids de chunk, diferentes em cada banco: copiar
cru faria a questão apontar pra outro artigo, em silêncio. A exportação
traduz id -> `art:CP|312` (lei) ou `mat:<hash>|<ordem>` (material do aluno),
e a importação resolve de volta contra o banco local.

IMPORTAR É UNIÃO, NUNCA SUBSTITUIÇÃO
------------------------------------
Todo insert é idempotente por identidade natural: rodar duas vezes não
duplica, e o que existe só aqui não é apagado. Isso é o que torna o hook de
`post-merge` seguro — ele roda a cada pull, inclusive quando o pacote está
velho. A única exceção é `erro_caderno`, que é DERIVADO das tentativas e por
isso é recalculado (escopado ao usuário, nunca ao banco inteiro).

Conflito de merge no JSON não é tratado aqui: `.gitattributes` manda ficar
com a versão que veio do remoto, porque o lado local está no BANCO local e
volta ao arquivo no próximo `exportar`. Perder o arquivo local não perde dado.
"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

from core import auth, db
from core.config import CLI_USUARIO_EMAIL

VERSAO = "sincronizar-v6"
ARQUIVO = Path("dados/progresso.json")

# OS ARQUIVOS ORIGINAIS VIAJAM COMO BLOBS, FORA DO JSON.
#
# Meter PDF em base64 dentro do pacote foi descartado por um limite duro, não
# por gosto: base64 infla 33%, o pacote é UM arquivo, e o GitHub REJEITA push de
# arquivo acima de 100 MB. Vinte apostilas dariam ~133 MB num blob só — push
# recusado, não lento.
#
# Um arquivo por PDF resolve os três problemas de uma vez: cada blob fica no seu
# tamanho real, o git guarda binário nativamente (sem inflar) e PDF idêntico
# deduplica pelo próprio hash, porque o NOME do arquivo aqui É o sha256 do
# conteúdo — o mesmo hash que `documento.hash` usa como identidade natural.
# `_comum.sh` monta a árvore do ref `estado` com `mktree`, então acrescentar
# entradas é o caminho que já existe.
ARQUIVOS = Path("dados/arquivos")
LOTE_EMBEDDING = 32


# Duas importações ao mesmo tempo brigam pelo MESMO documento: `_materiais`
# apaga os chunks antes de reinserir, e dois processos nisso dão lock no
# Postgres e trabalho duplicado. Acontece de verdade — um `git pull` disparou
# a fase 2 em background e um segundo pull chegou antes de ela terminar.
# Advisory lock de sessão resolve sem tabela e sem arquivo de PID: quem chegou
# depois desiste em silêncio, porque o primeiro vai terminar o serviço.
TRAVA = 728301


def _travar() -> bool:
    r = db.exec1("SELECT pg_try_advisory_lock(%(k)s) AS ok", {"k": TRAVA})
    return bool(r and r["ok"])


def _destravar() -> None:
    try:
        db.query("SELECT pg_advisory_unlock(%(k)s)", {"k": TRAVA})
    except Exception:
        pass


def _extensao(origem: str | None) -> str:
    """A extensão do arquivo original, normalizada e com teto.

    Vem do `origem` (o nome que o aluno subiu) e não de `arquivo_tipo`: o MIME
    não diz extensão de volta sem uma tabela inversa, e o nome dentro de
    `dados/arquivos/` existe pra que uma pessoa consiga abrir o arquivo direto
    da pasta. Sem extensão, o sistema operacional não sabe com o que abrir.

    O teto de 5 e o filtro de caracteres não são paranoia decorativa: este
    pedaço entra num caminho de arquivo, e `origem` é texto que chegou pelo
    upload."""
    if not origem or "." not in origem:
        return ""
    ext = origem.rsplit(".", 1)[-1]
    ext = "".join(c for c in ext if c.isalnum())[:5].lower()
    return f".{ext}" if ext else ""


def chave(texto: str) -> str:
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()[:16]


def _serial(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(type(o))


def _iso(v):
    """Instante como string, pra servir de chave de dedupe nos dois lados."""
    return v.isoformat() if isinstance(v, (date, datetime)) else v


# =========================================================== exportar
def exportar(com_material: bool = True, com_senha: bool = True) -> int:
    emails = {r["id"]: r["email"] for r in db.query("SELECT id, email FROM usuario")}
    if not emails:
        print("nada a exportar: banco sem usuario.", file=sys.stderr)
        return 1

    # ---- referência de chunk: lei por (norma, artigo), material por (hash, ordem)
    ref_chunk: dict[int, str] = {}
    for c in db.query(
        """SELECT c.id, c.norma, c.artigo, c.ordem, d.hash AS doc_hash, d.usuario_id
           FROM chunk c JOIN documento d ON d.id = c.documento_id"""
    ):
        if c["artigo"]:
            ref_chunk[c["id"]] = f"art:{c['norma']}|{c['artigo']}"
        elif c["usuario_id"] and c["doc_hash"]:
            ref_chunk[c["id"]] = f"mat:{c['doc_hash']}|{c['ordem']}"

    doc_titulo = {r["id"]: r["titulo"] for r in db.query("SELECT id, titulo FROM documento")}

    # ---- contas
    usuarios = [
        {"email": u["email"],
         "senha_hash": u["senha_hash"] if com_senha else "",
         "perfil": u["perfil"], "criado_em": u["criado_em"]}
        for u in db.query("SELECT email, senha_hash, perfil, criado_em FROM usuario ORDER BY id")
    ]

    # ---- mesas
    mesas_rows = db.query(
        """SELECT id, usuario_id, nome, orgao, banca, criado_em,
                  disciplinas_manuais, biblioteca_compartilhada
           FROM mesa ORDER BY id"""
    )
    mesa_ref = {m["id"]: (emails[m["usuario_id"]], m["nome"]) for m in mesas_rows}
    mesas = [
        {"usuario": emails[m["usuario_id"]], "nome": m["nome"], "orgao": m["orgao"],
         "banca": m["banca"], "criado_em": m["criado_em"],
         "disciplinas_manuais": list(m["disciplinas_manuais"] or []),
         "biblioteca_compartilhada": m["biblioteca_compartilhada"]}
        for m in mesas_rows
    ]

    # ---- editais + tópicos (o edital é da MESA desde a 010)
    topicos: dict[int, list] = {}
    for t in db.query("SELECT edital_id, disciplina, ordem, texto FROM topico ORDER BY edital_id, ordem"):
        topicos.setdefault(t["edital_id"], []).append(
            {"disciplina": t["disciplina"], "ordem": t["ordem"], "texto": t["texto"]})
    editais = []
    for e in db.query(
        """SELECT id, titulo, orgao, banca, data_prova, arquivo, criado_em, mesa_id, cargo
           FROM edital ORDER BY id"""
    ):
        if e["mesa_id"] not in mesa_ref:
            continue
        usuario, mesa = mesa_ref[e["mesa_id"]]
        editais.append(
            {"usuario": usuario, "mesa": mesa, "titulo": e["titulo"], "orgao": e["orgao"],
             "banca": e["banca"], "data_prova": e["data_prova"], "arquivo": e["arquivo"],
             "cargo": e["cargo"], "criado_em": e["criado_em"],
             "topicos": topicos.get(e["id"], [])})

    # ---- contextos ("Texto associado" da 013) antes das questões que apontam pra eles
    ctx_rows = db.query(
        "SELECT id, documento_id, disciplina, texto, fonte_chunks, criada_em FROM contexto ORDER BY id")
    ctx_chave = {c["id"]: chave(c["texto"]) for c in ctx_rows}
    contextos = [
        {"chave": ctx_chave[c["id"]], "disciplina": c["disciplina"], "texto": c["texto"],
         "fontes": [ref_chunk[i] for i in (c["fonte_chunks"] or []) if i in ref_chunk],
         "doc_titulo": doc_titulo.get(c["documento_id"]), "criada_em": c["criada_em"]}
        for c in ctx_rows
    ]

    # ---- questões: compartilhadas por padrão (008) e, desde a 026, também
    #      privadas — as geradas da apostila do aluno. As duas viajam, e o
    #      `usuario` (email, ou None) é o que preserva a diferença: importar
    #      questão privada como pública a publicaria no acervo comum da outra
    #      máquina, com trecho de material pago dentro do enunciado. O material
    #      privado já viaja neste mesmo pacote (a seção `materiais`, com o PDF),
    #      então não é conteúdo novo saindo — é conteúdo saindo com o dono
    #      certo.
    q_rows = db.query(
        """SELECT id, documento_id, disciplina, tema, enunciado, gabarito, dicas,
                  fonte_chunks, criada_em, tipo, gabarito_ce, contexto_id,
                  ordem_no_contexto, usuario_id,
                  gabarito_letra, gabarito_fonte, origem, numero_na_prova
           FROM questao ORDER BY id"""
    )
    # Múltipla escolha (037): as alternativas viajam com a questão.
    alternativas: dict[int, list] = {}
    for a in db.query("SELECT questao_id, letra, texto FROM questao_alternativa ORDER BY questao_id, letra"):
        alternativas.setdefault(a["questao_id"], []).append([a["letra"], a["texto"]])
    q_chave = {q["id"]: chave(q["enunciado"]) for q in q_rows}
    questoes = [
        {"chave": q_chave[q["id"]], "disciplina": q["disciplina"], "tema": q["tema"],
         "enunciado": q["enunciado"], "gabarito": q["gabarito"], "dicas": q["dicas"],
         "criada_em": q["criada_em"], "doc_titulo": doc_titulo.get(q["documento_id"]),
         "tipo": q["tipo"], "gabarito_ce": q["gabarito_ce"],
         "gabarito_letra": q["gabarito_letra"], "gabarito_fonte": q["gabarito_fonte"],
         "origem": q["origem"], "numero_na_prova": q["numero_na_prova"],
         "alternativas": alternativas.get(q["id"], []),
         "usuario": emails.get(q["usuario_id"]),
         "contexto": ctx_chave.get(q["contexto_id"]),
         "ordem_no_contexto": q["ordem_no_contexto"],
         "fontes": [ref_chunk[i] for i in (q["fonte_chunks"] or []) if i in ref_chunk],
         # v2 lia "artigos"; mantido pra um pacote novo ainda ser legível por
         # uma máquina que só tenha o script antigo.
         "artigos": [ref_chunk[i][4:] for i in (q["fonte_chunks"] or [])
                     if i in ref_chunk and ref_chunk[i].startswith("art:")]}
        for q in q_rows
    ]

    # ---- material do aluno (019/020/021) + os chunks dele
    mat_rows = db.query(
        """SELECT id, titulo, disciplina, assunto, tipo, origem, hash, criado_em,
                  usuario_id, status, chunks_total, erro, classificado_por, mesa_id,
                  arquivo_tipo, arquivo_bytes, (arquivo IS NOT NULL) AS tem_arquivo
           FROM documento WHERE usuario_id IS NOT NULL ORDER BY id"""
    )
    mat_chunks: dict[int, list] = {}
    if com_material and mat_rows:
        for c in db.query(
            """SELECT documento_id, ordem, texto, norma, artigo, paragrafo, inciso,
                      rubrica, secao
               FROM chunk WHERE documento_id = ANY(%(ids)s) ORDER BY documento_id, ordem""",
            {"ids": [m["id"] for m in mat_rows]},
        ):
            mat_chunks.setdefault(c["documento_id"], []).append(
                {k: c[k] for k in ("ordem", "texto", "norma", "artigo", "paragrafo",
                                   "inciso", "rubrica", "secao")})
    # Grava os bytes um a um, cada um no seu arquivo. Um SELECT por documento e
    # não um `WHERE id = ANY(...)`: trazer vinte apostilas na mesma resposta
    # coloca ~100 MB na memória do processo de uma vez, e a conexão do projeto é
    # única (ver `core/db`). Um por vez é mais lento e não empilha.
    arquivos_gravados = bytes_gravados = 0
    if com_material:
        for m in mat_rows:
            if not (m["tem_arquivo"] and m["hash"]):
                continue
            destino = ARQUIVOS / f"{m['hash']}{_extensao(m['origem'])}"
            if destino.exists() and destino.stat().st_size == (m["arquivo_bytes"] or -1):
                arquivos_gravados += 1          # já está lá, e do tamanho certo
                bytes_gravados += destino.stat().st_size
                continue
            linha = db.exec1("SELECT arquivo FROM documento WHERE id = %(i)s", {"i": m["id"]})
            if not linha or linha["arquivo"] is None:
                continue
            ARQUIVOS.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(bytes(linha["arquivo"]))
            arquivos_gravados += 1
            bytes_gravados += destino.stat().st_size

    materiais = []
    for m in mat_rows:
        if not m["hash"]:
            # Sem hash não há identidade natural: seria impossível reconhecer o
            # mesmo material do outro lado, e cada pull criaria uma cópia.
            continue
        materiais.append(
            {"usuario": emails[m["usuario_id"]], "hash": m["hash"], "titulo": m["titulo"],
             "disciplina": m["disciplina"], "assunto": m["assunto"], "tipo": m["tipo"],
             "origem": m["origem"], "criado_em": m["criado_em"],
             "status": m["status"], "erro": m["erro"],
             "chunks_total": m["chunks_total"], "classificado_por": m["classificado_por"],
             "mesa": mesa_ref.get(m["mesa_id"], (None, None))[1],
             # O pacote referencia o arquivo, não o carrega. `arquivo` é o nome
             # dentro de `dados/arquivos/`, e é derivável do hash — guardado
             # explícito de propósito, pra quem lê o JSON não precisar conhecer a
             # regra de formação do nome.
             "arquivo": (f"{m['hash']}{_extensao(m['origem'])}"
                         if (com_material and m["tem_arquivo"]) else None),
             "arquivo_tipo": m["arquivo_tipo"], "arquivo_bytes": m["arquivo_bytes"],
             "chunks": mat_chunks.get(m["id"], [])})

    # ---- simulados (a tentativa aponta pra eles, então vêm antes)
    sim_rows = db.query(
        """SELECT id, usuario_id, mesa_id, n_questoes, minutos_alvo, segundos_total,
                  segundos_acumulados, nome, criado_em, questao_ids
           FROM simulado ORDER BY id"""
    )
    sim_ref = {s["id"]: (emails[s["usuario_id"]], _iso(s["criado_em"])) for s in sim_rows}
    simulados = [
        {"usuario": emails[s["usuario_id"]], "criado_em": s["criado_em"],
         "mesa": mesa_ref.get(s["mesa_id"], (None, None))[1],
         "n_questoes": s["n_questoes"], "minutos_alvo": s["minutos_alvo"],
         "segundos_total": s["segundos_total"],
         "segundos_acumulados": s["segundos_acumulados"], "nome": s["nome"],
         "questoes": [q_chave[i] for i in (s["questao_ids"] or []) if i in q_chave]}
        for s in sim_rows
    ]

    # ---- progresso e tentativas (o dado insubstituível)
    progresso = [
        {"usuario": emails[p["usuario_id"]], "questao": q_chave[p["questao_id"]],
         "caixa": p["caixa"], "prox_revisao": p["prox_revisao"]}
        for p in db.query("SELECT usuario_id, questao_id, caixa, prox_revisao FROM progresso")
        if p["questao_id"] in q_chave and p["usuario_id"] in emails
    ]
    tentativas = [
        {"usuario": emails[t["usuario_id"]], "questao": q_chave[t["questao_id"]],
         "resposta": t["resposta"], "veredito": t["veredito"],
         "dicas_usadas": t["dicas_usadas"], "segundos": t["segundos"],
         "criada_em": t["criada_em"], "conceito_faltante": t["conceito_faltante"],
         "simulado": sim_ref.get(t["simulado_id"], (None, None))[1]}
        for t in db.query(
            """SELECT usuario_id, questao_id, resposta, veredito, dicas_usadas, segundos,
                      criada_em, conceito_faltante, simulado_id
               FROM tentativa ORDER BY criada_em""")
        if t["questao_id"] in q_chave and t["usuario_id"] in emails
    ]

    # ---- conversas + mensagens (014/016): a memória do tutor
    msgs: dict[int, list] = {}
    for m in db.query(
        "SELECT conversa_id, autor, texto, fontes, criada_em FROM mensagem ORDER BY conversa_id, id"
    ):
        msgs.setdefault(m["conversa_id"], []).append(
            {"autor": m["autor"], "texto": m["texto"], "fontes": m["fontes"],
             "criada_em": m["criada_em"]})
    conversas = [
        {"usuario": emails[c["usuario_id"]], "titulo": c["titulo"],
         "mesa": mesa_ref.get(c["mesa_id"], (None, None))[1],
         "criada_em": c["criada_em"], "atualizada_em": c["atualizada_em"],
         "mensagens": msgs.get(c["id"], [])}
        for c in db.query(
            "SELECT id, usuario_id, mesa_id, titulo, criada_em, atualizada_em FROM conversa ORDER BY id")
        if c["usuario_id"] in emails
    ]

    pacote = {
        "versao": VERSAO,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        # Compat com o v2, que exigia esta chave pra saber de quem era o pacote.
        "usuario_email": CLI_USUARIO_EMAIL,
        "usuarios": usuarios,
        "mesas": mesas,
        "editais": editais,
        "contextos": contextos,
        "questoes": questoes,
        "materiais": materiais,
        "simulados": simulados,
        "progresso": progresso,
        "tentativas": tentativas,
        "conversas": conversas,
    }
    ARQUIVO.parent.mkdir(exist_ok=True)
    ARQUIVO.write_text(json.dumps(pacote, ensure_ascii=False, indent=1, default=_serial),
                       encoding="utf-8")
    print(f"exportado -> {ARQUIVO} ({ARQUIVO.stat().st_size // 1024} KB)")
    print(f"  {len(usuarios)} contas · {len(mesas)} mesas · {len(editais)} editais · "
          f"{len(questoes)} questoes · {len(contextos)} contextos")
    print(f"  {len(progresso)} progressos · {len(tentativas)} tentativas · "
          f"{len(simulados)} simulados · {len(conversas)} conversas "
          f"({sum(len(c['mensagens']) for c in conversas)} mensagens)")
    print(f"  {len(materiais)} materiais do aluno "
          f"({sum(len(m['chunks']) for m in materiais)} trechos"
          f"{'' if com_material else ', TEXTO DE FORA por --sem-material'})")
    if arquivos_gravados:
        # `// 1024 // 1024 or 1` mostrava "1 MB" pra 1920 bytes — número redondo
        # e errado, do tipo que faz você não confiar no resto do relatório.
        tam = (f"{bytes_gravados / 1048576:.1f} MB" if bytes_gravados >= 1048576
               else f"{bytes_gravados // 1024 or 1} KB")
        print(f"  {arquivos_gravados} arquivo(s) originais em {ARQUIVOS}/ "
              f"({tam}) — viajam como blobs, fora do pacote")
    return 0


# =========================================================== importar
def _usuarios(pacote) -> dict[str, int]:
    """email -> id local. Cria a conta que não existe, com a senha do pacote."""
    ids = {}
    lista = pacote.get("usuarios")
    if not lista:
        # Pacote v2: um usuário só, sem senha nem perfil.
        email = pacote.get("usuario_email") or CLI_USUARIO_EMAIL
        return {email: auth.usuario_da_cli(email)}
    for u in lista:
        email = (u["email"] or "").strip().lower()
        if not email:
            continue
        r = db.exec1(
            """INSERT INTO usuario (email, senha_hash, perfil, criado_em)
               VALUES (%(e)s, %(h)s, %(p)s, COALESCE(%(c)s, now()))
               ON CONFLICT (email) DO UPDATE SET
                 -- senha local vazia (conta criada pela CLI) aceita a do
                 -- pacote; senha local existente NÃO é sobrescrita: quem
                 -- trocou a senha aqui trocou por algum motivo.
                 senha_hash = CASE WHEN usuario.senha_hash = ''
                                   THEN EXCLUDED.senha_hash ELSE usuario.senha_hash END,
                 perfil = CASE WHEN usuario.perfil = '{}'::jsonb
                               THEN EXCLUDED.perfil ELSE usuario.perfil END
               RETURNING id""",
            {"e": email, "h": u.get("senha_hash") or "",
             "p": json.dumps(u.get("perfil") or {}), "c": u.get("criado_em")},
        )
        ids[email] = r["id"]
    return ids


def _mesas(pacote, uid: dict[str, int]) -> dict[tuple, int]:
    """(email, nome) -> id local. Identidade é o NOME dentro da conta."""
    ref = {}
    for m in pacote.get("mesas", []):
        u = uid.get(m["usuario"])
        if u is None:
            continue
        r = db.exec1(
            "SELECT id FROM mesa WHERE usuario_id = %(u)s AND nome = %(n)s",
            {"u": u, "n": m["nome"]},
        )
        if r:
            # Só completa o que está vazio aqui: mesa é editável na tela, e o
            # pacote não tem como saber qual lado é o mais recente.
            db.query(
                """UPDATE mesa SET orgao = COALESCE(orgao, %(o)s),
                                   banca = COALESCE(banca, %(b)s),
                                   disciplinas_manuais = CASE
                                     WHEN disciplinas_manuais = '{}'::text[]
                                     THEN %(d)s::text[] ELSE disciplinas_manuais END
                   WHERE id = %(i)s""",
                {"o": m.get("orgao"), "b": m.get("banca"),
                 "d": m.get("disciplinas_manuais") or [], "i": r["id"]},
            )
            ref[(m["usuario"], m["nome"])] = r["id"]
            continue
        r = db.exec1(
            """INSERT INTO mesa (usuario_id, nome, orgao, banca, criado_em,
                                 disciplinas_manuais, biblioteca_compartilhada)
               VALUES (%(u)s, %(n)s, %(o)s, %(b)s, COALESCE(%(c)s, now()),
                       %(d)s::text[], COALESCE(%(bc)s, true))
               RETURNING id""",
            {"u": u, "n": m["nome"], "o": m.get("orgao"), "b": m.get("banca"),
             "c": m.get("criado_em"), "d": m.get("disciplinas_manuais") or [],
             "bc": m.get("biblioteca_compartilhada")},
        )
        ref[(m["usuario"], m["nome"])] = r["id"]
    return ref


def _editais(pacote, mesa_id: dict[tuple, int]) -> int:
    n = 0
    for e in pacote.get("editais", []):
        mid = mesa_id.get((e["usuario"], e["mesa"]))
        if mid is None:
            continue
        ja = db.exec1(
            "SELECT id FROM edital WHERE mesa_id = %(m)s AND titulo = %(t)s",
            {"m": mid, "t": e["titulo"]},
        )
        if ja:
            continue
        r = db.exec1(
            """INSERT INTO edital (titulo, orgao, banca, data_prova, arquivo,
                                   criado_em, mesa_id, cargo)
               VALUES (%(t)s, %(o)s, %(b)s, %(d)s, %(a)s, COALESCE(%(c)s, now()),
                       %(m)s, %(g)s)
               RETURNING id""",
            {"t": e["titulo"], "o": e.get("orgao"), "b": e.get("banca"),
             "d": e.get("data_prova"), "a": e.get("arquivo"),
             "c": e.get("criado_em"), "m": mid, "g": e.get("cargo")},
        )
        for t in e.get("topicos", []):
            db.query(
                """INSERT INTO topico (edital_id, disciplina, ordem, texto)
                   VALUES (%(e)s, %(d)s, %(o)s, %(x)s)""",
                {"e": r["id"], "d": t["disciplina"], "o": t["ordem"], "x": t["texto"]},
            )
        n += 1
    return n


def _mapa_chunks() -> dict[str, int]:
    """ref textual -> chunk_id LOCAL. Lei e material do aluno no mesmo mapa."""
    mapa = {}
    for r in db.query(
        """SELECT c.id, c.norma, c.artigo, c.ordem, d.hash AS doc_hash, d.usuario_id
           FROM chunk c JOIN documento d ON d.id = c.documento_id"""
    ):
        if r["artigo"]:
            mapa[f"art:{r['norma']}|{r['artigo']}"] = r["id"]
        elif r["usuario_id"] and r["doc_hash"]:
            mapa[f"mat:{r['doc_hash']}|{r['ordem']}"] = r["id"]
    return mapa


def _refs(item) -> list[str]:
    """Fontes do pacote v3 ("fontes") ou do v2 ("artigos", só lei)."""
    if item.get("fontes") is not None:
        return item["fontes"]
    return [f"art:{a}" for a in (item.get("artigos") or [])]


def _materiais(pacote, uid, mesa_id, indexar: bool = True) -> tuple[int, int, int]:
    """
    Documento do aluno + chunks + o ARQUIVO original. Recalcula embedding em CPU
    local, porque o vetor não viaja (inflaria o pacote); o PDF viaja, mas como
    blob próprio em `dados/arquivos/`, nunca dentro do JSON — ver `ARQUIVOS`.

    `indexar=False` grava as LINHAS e para: quem chama assim é o hook de pull,
    que precisa devolver o terminal em segundos. O embedding de algumas
    centenas de trechos leva minutos de CPU, e travar o `git pull` nisso é
    exatamente o tipo de automação que a pessoa desliga na terceira vez.
    Quem termina o serviço depois é `sincronizar.py material`, e enquanto isso
    o documento fica 'processando' — estado que a biblioteca já mostra.
    """
    novos = reindexados = pulados = arquivos = 0
    pendentes = []
    for m in pacote.get("materiais", []):
        u = uid.get(m["usuario"])
        if u is None or not m.get("hash"):
            continue
        mid = mesa_id.get((m["usuario"], m.get("mesa"))) if m.get("mesa") else None
        ja = db.exec1(
            "SELECT id, chunks_total FROM documento WHERE usuario_id = %(u)s AND hash = %(h)s",
            {"u": u, "h": m["hash"]},
        )
        chunks = m.get("chunks") or []
        if ja:
            doc_id = ja["id"]
            locais = db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id = %(d)s",
                              {"d": doc_id})["n"]
            if locais and (not chunks or locais == len(chunks)):
                pulados += 1
                chunks = []          # nada a reindexar, mas o arquivo abaixo ainda entra
        else:
            r = db.exec1(
                """INSERT INTO documento (titulo, disciplina, assunto, tipo, origem, hash,
                                          criado_em, usuario_id, mesa_id, status,
                                          chunks_total, erro, classificado_por)
                   VALUES (%(t)s, %(d)s, %(a)s, %(tp)s, %(o)s, %(h)s,
                           COALESCE(%(c)s, now()), %(u)s, %(m)s, %(st)s, %(ct)s,
                           %(er)s, %(cp)s)
                   RETURNING id""",
                {"t": m["titulo"], "d": m.get("disciplina"), "a": m.get("assunto"),
                 "tp": m.get("tipo") or "aula", "o": m.get("origem"), "h": m["hash"],
                 "c": m.get("criado_em"), "u": u, "m": mid,
                 # Nunca 'pronto' antes de o chunk existir: se este processo
                 # morrer no meio da indexação (o hook de pull pode ser
                 # interrompido com Ctrl+C), a biblioteca estaria mentindo
                 # "indexado" sobre material sem trecho nenhum. 'processando'
                 # é o mesmo estado que material.py usa entre registrar e
                 # indexar, e a tela já sabe desenhá-lo.
                 "st": "processando" if chunks else "falha",
                 "ct": m.get("chunks_total"),
                 "er": None if chunks else "texto não veio no pacote (exportado com --sem-material)",
                 "cp": m.get("classificado_por")},
            )
            doc_id = r["id"]
            novos += 1
        # O ARQUIVO ENTRA MESMO EM DOCUMENTO QUE JÁ EXISTIA, e é de propósito:
        # material sincronizado antes da 024 está no banco sem bytes, e o pacote
        # novo é a única chance de completá-lo. Por isso a gravação fica FORA do
        # `else` do insert e roda também no caminho do `pulados` — só sobrescreve
        # quando ainda não há arquivo local.
        if m.get("arquivo"):
            caminho = ARQUIVOS / m["arquivo"]
            if caminho.exists():
                falta = db.exec1(
                    "SELECT 1 AS x FROM documento WHERE id=%(d)s AND arquivo IS NULL",
                    {"d": doc_id})
                if falta:
                    dados = caminho.read_bytes()
                    # Confere o hash antes de gravar: o nome do blob É o sha256
                    # do conteúdo, então divergência quer dizer arquivo trocado
                    # ou truncado no caminho, e gravar um binário corrompido
                    # como "o original" é pior que não ter original.
                    if hashlib.sha256(dados).hexdigest() == m["hash"]:
                        db.query(
                            """UPDATE documento SET arquivo = %(b)s, arquivo_tipo = %(t)s,
                                                    arquivo_bytes = %(n)s
                                WHERE id = %(d)s""",
                            {"b": dados, "t": m.get("arquivo_tipo"),
                             "n": len(dados), "d": doc_id})
                        arquivos += 1
                    else:
                        print(f"  arquivo de {m['titulo']!r} com hash divergente — ignorado")
        if chunks:
            # O RÓTULO VIAJA JUNTO na fila de indexação: é ele que entra no
            # vetor (`material.texto_para_vetor`), e buscá-lo de novo no banco
            # aqui seria uma consulta por documento pra ler o que o pacote já
            # trouxe.
            pendentes.append((doc_id, chunks, m.get("disciplina"), m.get("assunto")))

    if arquivos:
        print(f"  {arquivos} arquivo(s) original(is) gravado(s) no banco")
    if pendentes and not indexar:
        return novos, 0, pulados
    if pendentes:
        # Import tardio: carregar o modelo custa segundos e RAM, e a maioria
        # dos pulls não tem material novo nenhum.
        from core import embeddings
        from core import material as material_mod
        for doc_id, chunks, disc, assu in pendentes:
            db.query("DELETE FROM chunk WHERE documento_id = %(d)s", {"d": doc_id})
            for i in range(0, len(chunks), LOTE_EMBEDDING):
                lote = chunks[i:i + LOTE_EMBEDDING]
                # MESMA regra de `material.texto_para_vetor`, importada e não
                # copiada: material indexado pelo pull tem de ser encontrável
                # pela mesma consulta que acha o indexado pelo upload. Duas
                # fórmulas de "o que vai ao vetor" produziriam biblioteca em que
                # metade do material responde à busca e metade não, dependendo
                # de por qual caminho entrou.
                vetores = embeddings.embed_passagens(
                    [material_mod.texto_para_vetor(x["texto"], disc, assu) for x in lote])
                for x, v in zip(lote, vetores):
                    db.query(
                        """INSERT INTO chunk (documento_id, ordem, texto, norma, artigo,
                                              paragrafo, inciso, rubrica, secao, embedding,
                                              rotulo)
                           VALUES (%(d)s,%(o)s,%(t)s,%(n)s,%(a)s,%(p)s,%(i)s,%(r)s,%(s)s,
                                   %(e)s,%(rot)s)
                           ON CONFLICT (documento_id, ordem) DO NOTHING""",
                        {"d": doc_id, "o": x["ordem"], "t": x["texto"], "n": x.get("norma"),
                         "a": x.get("artigo"), "p": x.get("paragrafo"), "i": x.get("inciso"),
                         "r": x.get("rubrica"), "s": x.get("secao"), "e": v,
                         # 025: mesmo rótulo que o upload grava, senão material
                         # que chegou pelo pull não responderia à busca por
                         # matéria e o que veio pelo upload sim.
                         # Assunto primeiro, igual a `material.texto_para_vetor`:
                         # nome de disciplina muda entre editais, assunto não.
                         "rot": ". ".join(y for y in (assu, disc) if y) or None},
                    )
            db.query(
                "UPDATE documento SET status='pronto', erro=NULL, chunks_total=%(n)s WHERE id=%(d)s",
                {"n": len(chunks), "d": doc_id},
            )
            reindexados += 1
    return novos, reindexados, pulados


def importar(indexar_material: bool = True) -> int:
    if not ARQUIVO.exists():
        print(f"{ARQUIVO} nao existe. Rode 'exportar' na outra maquina e faça git pull.",
              file=sys.stderr)
        return 1
    pacote = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    versao_pacote = pacote.get("versao", "?")

    # UMA transação para o import inteiro, por duas razões, a primeira medida:
    #
    #   · velocidade — a conexão do projeto é autocommit (é o certo pro
    #     caminho normal, um request curto por vez), e aqui são ~1100 inserts
    #     pequenos. Um fsync por insert deu 1m21s de relógio com 1,9s de CPU:
    #     o tempo todo era commit. Em transação única cai pra segundos, e é o
    #     que torna aceitável rodar isto dentro de um hook de `git pull`.
    #   · atomicidade — pull interrompido no meio (Ctrl+C acontece) não deixa
    #     metade das mesas criadas e nenhuma tentativa.
    #
    # O autocommit VOLTA no finally: a conexão é global e do módulo, e
    # devolvê-la em outro modo quebraria quem chamar depois no mesmo processo.
    if not _travar():
        print("outra sincronizacao esta rodando agora — nao faco nada "
              "(ela termina o servico)")
        return 0
    c = db.conn()
    c.autocommit = False
    try:
        n = _importar_tudo(pacote, indexar_material)
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.autocommit = True
        _destravar()
    return _relatorio(pacote, **n)


def _importar_tudo(pacote, indexar_material: bool = True) -> dict:
    uid = _usuarios(pacote)
    mesa_id = _mesas(pacote, uid)
    editais_novos = _editais(pacote, mesa_id)

    mapa = _mapa_chunks()
    docs = {r["titulo"]: r["id"] for r in db.query("SELECT id, titulo FROM documento")}

    # ---- material ANTES das questões: questão gerada de material do aluno
    # aponta pra chunk dele, e o mapa precisa já ter esses ids.
    mat_novos, mat_reindex, mat_pulados = _materiais(pacote, uid, mesa_id,
                                                     indexar=indexar_material)
    if mat_novos or mat_reindex:
        mapa = _mapa_chunks()

    # ---- contextos (013) antes das questões que os referenciam
    ctx_id = {c["chave"]: c["id"] for c in
              [{"chave": chave(r["texto"]), "id": r["id"]}
               for r in db.query("SELECT id, texto FROM contexto")]}
    for c in pacote.get("contextos", []):
        if c["chave"] in ctx_id:
            continue
        r = db.exec1(
            """INSERT INTO contexto (documento_id, disciplina, texto, fonte_chunks, criada_em)
               VALUES (%(d)s, %(disc)s, %(t)s, %(f)s, COALESCE(%(c)s, now()))
               RETURNING id""",
            {"d": docs.get(c.get("doc_titulo")), "disc": c["disciplina"], "t": c["texto"],
             "f": [mapa[x] for x in _refs(c) if x in mapa], "c": c.get("criada_em")},
        )
        ctx_id[c["chave"]] = r["id"]

    # ---- questões (compartilhadas)
    existentes = {chave(r["enunciado"]): r["id"]
                  for r in db.query("SELECT id, enunciado FROM questao")}
    id_por_chave = dict(existentes)
    novas = atualizadas = sem_fonte = sem_dono = 0
    for q in pacote["questoes"]:
        # Questão privada cujo dono não veio no pacote não entra: publicá-la
        # seria vazar material de alguém que esta máquina nem conhece.
        if q.get("usuario") and q["usuario"] not in uid:
            sem_dono += 1
            continue
        refs = _refs(q)
        chunks = [mapa[x] for x in refs if x in mapa]
        if refs and not chunks:
            # Ingira o material ANTES de importar, senão a questão entra sem
            # fonte rastreável e a cobertura passa a mentir.
            sem_fonte += 1
        if q["chave"] in existentes:
            db.query("UPDATE questao SET fonte_chunks = %(f)s WHERE id = %(i)s",
                     {"f": chunks, "i": existentes[q["chave"]]})
            atualizadas += 1
            continue
        r = db.exec1(
            """INSERT INTO questao (documento_id, disciplina, tema, enunciado, gabarito,
                                    dicas, fonte_chunks, criada_em, tipo, gabarito_ce,
                                    contexto_id, ordem_no_contexto, usuario_id,
                                    gabarito_letra, gabarito_fonte, origem, numero_na_prova)
               VALUES (%(d)s, %(disc)s, %(t)s, %(e)s, %(g)s, %(dic)s, %(f)s,
                       COALESCE(%(cr)s, now()), COALESCE(%(tp)s, 'resposta_livre'),
                       %(ce)s, %(ctx)s, %(ord)s, %(dono)s,
                       %(letra)s, %(gfonte)s, COALESCE(%(orig)s, 'gerada'), %(num)s)
               RETURNING id""",
            # `dono` só é preenchido pra questão que JÁ era privada e cujo dono
            # existe neste banco. Pacote da era anterior à 026 não tem o campo:
            # `.get` devolve None e a questão entra pública, que é o que ela
            # era. Dono que não veio no pacote também cai em None — mas aí a
            # questão perderia o sigilo, então é descarte, não publicação.
            {"d": docs.get(q.get("doc_titulo")), "disc": q["disciplina"], "t": q["tema"],
             "dono": uid.get(q["usuario"]) if q.get("usuario") else None,
             "e": q["enunciado"], "g": q["gabarito"], "dic": json.dumps(q["dicas"]),
             "f": chunks, "cr": q.get("criada_em"), "tp": q.get("tipo"),
             "ce": q.get("gabarito_ce"),
             "ctx": ctx_id.get(q.get("contexto")),
             "ord": q.get("ordem_no_contexto"),
             "letra": q.get("gabarito_letra"), "gfonte": q.get("gabarito_fonte"),
             "orig": q.get("origem"), "num": q.get("numero_na_prova")},
        )
        for letra, texto in q.get("alternativas") or []:
            db.query("""INSERT INTO questao_alternativa (questao_id, letra, texto)
                        VALUES (%(q)s, %(l)s, %(t)s) ON CONFLICT DO NOTHING""",
                     {"q": r["id"], "l": letra, "t": texto})
        id_por_chave[q["chave"]] = r["id"]
        novas += 1

    # ---- simulados antes das tentativas (a tentativa aponta pro simulado)
    sim_id = {}
    for s in pacote.get("simulados", []):
        u = uid.get(s["usuario"])
        if u is None:
            continue
        ja = db.exec1(
            "SELECT id FROM simulado WHERE usuario_id = %(u)s AND criado_em = %(c)s",
            {"u": u, "c": s["criado_em"]},
        )
        if ja:
            sim_id[(s["usuario"], _iso(s["criado_em"]))] = ja["id"]
            continue
        r = db.exec1(
            """INSERT INTO simulado (n_questoes, minutos_alvo, segundos_total, criado_em,
                                     usuario_id, mesa_id, questao_ids,
                                     segundos_acumulados, nome)
               VALUES (%(n)s, %(m)s, %(st)s, %(c)s, %(u)s, %(mesa)s, %(q)s,
                       COALESCE(%(sa)s, 0), %(nome)s)
               RETURNING id""",
            {"n": s["n_questoes"], "m": s.get("minutos_alvo"),
             "st": s.get("segundos_total"), "c": s["criado_em"], "u": u,
             "mesa": mesa_id.get((s["usuario"], s.get("mesa"))) if s.get("mesa") else None,
             "q": [id_por_chave[k] for k in s.get("questoes", []) if k in id_por_chave],
             "sa": s.get("segundos_acumulados"), "nome": s.get("nome")},
        )
        sim_id[(s["usuario"], _iso(s["criado_em"]))] = r["id"]

    # ---- progresso: upsert por (usuario, questao) — mesmo padrão de scheduler.registrar()
    prog = 0
    for p in pacote.get("progresso", []):
        u = uid.get(p.get("usuario") or pacote.get("usuario_email"))
        qid = id_por_chave.get(p["questao"])
        if u is None or qid is None:
            continue
        db.query(
            """INSERT INTO progresso (usuario_id, questao_id, caixa, prox_revisao)
               VALUES (%(u)s, %(q)s, %(c)s, %(p)s)
               ON CONFLICT (usuario_id, questao_id) DO UPDATE
                 SET caixa = %(c)s, prox_revisao = %(p)s""",
            {"u": u, "q": qid, "c": p["caixa"], "p": p["prox_revisao"]},
        )
        prog += 1

    # ---- tentativas: dedupe por (usuario, questao, instante). Reimportar não duplica.
    ja_t = {(r["usuario_id"], r["questao_id"], r["criada_em"].isoformat())
            for r in db.query("SELECT usuario_id, questao_id, criada_em FROM tentativa")}
    inseridas = 0
    for t in pacote["tentativas"]:
        u = uid.get(t.get("usuario") or pacote.get("usuario_email"))
        qid = id_por_chave.get(t["questao"])
        if u is None or qid is None or (u, qid, _iso(t["criada_em"])) in ja_t:
            continue
        db.query(
            """INSERT INTO tentativa (usuario_id, questao_id, resposta, veredito,
                                      dicas_usadas, segundos, criada_em, simulado_id,
                                      conceito_faltante)
               VALUES (%(u)s, %(q)s, %(r)s, %(v)s, %(d)s, %(s)s, %(c)s, %(sim)s, %(cf)s)""",
            {"u": u, "q": qid, "r": t["resposta"], "v": t["veredito"],
             "d": t["dicas_usadas"], "s": t["segundos"], "c": t["criada_em"],
             "sim": sim_id.get((t.get("usuario"), _iso(t.get("simulado")))) if t.get("simulado") else None,
             "cf": t.get("conceito_faltante")},
        )
        inseridas += 1

    # ---- conversas + mensagens (a memória do tutor)
    conv_novas = msg_novas = 0
    for c in pacote.get("conversas", []):
        u = uid.get(c["usuario"])
        if u is None:
            continue
        ja = db.exec1(
            "SELECT id FROM conversa WHERE usuario_id = %(u)s AND criada_em = %(c)s",
            {"u": u, "c": c["criada_em"]},
        )
        if ja:
            cid = ja["id"]
        else:
            r = db.exec1(
                # `::timestamptz` nos DOIS usos de %(c)s, e no %(a)s: o mesmo
                # parâmetro aparece na coluna (que dá o tipo) e dentro de um
                # COALESCE cujo primeiro argumento chega NULL — o Postgres
                # deduz `text` ali e estoura AmbiguousParameter ("text versus
                # timestamp with time zone"), abortando a importação inteira na
                # primeira conversa sem `atualizada_em`. Terceira vez desta
                # classe no projeto (o `::text` do classificado_por e o
                # `::bigint[]` do reingest.py): parâmetro que o Postgres não
                # consegue tipar pelo contexto se anota na mão.
                """INSERT INTO conversa (usuario_id, mesa_id, titulo, criada_em, atualizada_em)
                   VALUES (%(u)s, %(m)s, %(t)s, %(c)s::timestamptz,
                           COALESCE(%(a)s::timestamptz, %(c)s::timestamptz))
                   RETURNING id""",
                {"u": u, "m": mesa_id.get((c["usuario"], c.get("mesa"))) if c.get("mesa") else None,
                 "t": c["titulo"], "c": c["criada_em"], "a": c.get("atualizada_em")},
            )
            cid = r["id"]
            conv_novas += 1
        vistas = {(r["autor"], r["criada_em"].isoformat())
                  for r in db.query(
                      "SELECT autor, criada_em FROM mensagem WHERE conversa_id = %(c)s",
                      {"c": cid})}
        for m in c.get("mensagens", []):
            if (m["autor"], _iso(m["criada_em"])) in vistas:
                continue
            db.query(
                """INSERT INTO mensagem (conversa_id, autor, texto, fontes, criada_em)
                   VALUES (%(c)s, %(a)s, %(t)s, %(f)s, %(cr)s)""",
                {"c": cid, "a": m["autor"], "t": m["texto"],
                 "f": json.dumps(m.get("fontes") or []), "cr": m["criada_em"]},
            )
            msg_novas += 1

    # ---- erro_caderno é DERIVADO: recalculado por usuário tocado, nunca copiado
    for email, u in uid.items():
        db.query("DELETE FROM erro_caderno WHERE usuario_id = %(u)s", {"u": u})
        db.query(
            """INSERT INTO erro_caderno (usuario_id, questao_id, disciplina, tema, vezes, ultima)
               SELECT %(u)s, q.id, q.disciplina, q.tema, count(*), max(t.criada_em)::date
               FROM tentativa t JOIN questao q ON q.id = t.questao_id
               WHERE t.usuario_id = %(u)s AND t.veredito <> 'correta'
               GROUP BY q.id""",
            {"u": u},
        )

    return {"contas": sorted(uid), "mesas": len(mesa_id), "editais": editais_novos,
            "q_novas": novas, "q_atualizadas": atualizadas, "prog": prog,
            "tentativas": inseridas, "conversas": conv_novas, "mensagens": msg_novas,
            "mat_novos": mat_novos, "mat_reindex": mat_reindex,
            "mat_pulados": mat_pulados, "sem_fonte": sem_fonte,
            "sem_dono": sem_dono,
            "indexou_material": indexar_material}


def _relatorio(pacote, contas, mesas, editais, q_novas, q_atualizadas, prog, tentativas,
               conversas, mensagens, mat_novos, mat_reindex, mat_pulados, sem_fonte,
               sem_dono, indexou_material) -> int:
    print(f"pacote {pacote.get('versao', '?')} · {len(contas)} conta(s): {', '.join(contas)}")
    print(f"  mesas: {mesas} resolvidas · editais: {editais} novos")
    print(f"  questoes: {q_novas} novas, {q_atualizadas} atualizadas")
    print(f"  progresso: {prog} upserts · tentativas: {tentativas} inseridas")
    print(f"  conversas: {conversas} novas ({mensagens} mensagens)")
    print(f"  material: {mat_novos} novos, {mat_reindex} indexados, {mat_pulados} já em dia")
    if mat_novos and not indexou_material:
        print(f"  ({mat_novos} material(is) ficaram 'processando' — "
              f"'sincronizar.py material' calcula os embeddings)")
    if sem_fonte:
        print(f"ATENCAO: {sem_fonte} questoes sem chunk correspondente. "
              f"Ingira o material antes de importar, senao a cobertura mente.")
    if sem_dono:
        # Não é erro do pacote: é a conta do dono não existir aqui. Publicar
        # a questão resolveria o número e vazaria o material (026).
        print(f"  {sem_dono} questao(oes) privada(s) puladas: a conta do dono "
              f"nao existe neste banco (nao entram como publicas).")
    return 0


# =========================================================== material (fase 2)
def material() -> int:
    """
    Termina o que `importar --material-depois` deixou: calcula o embedding do
    material do aluno que chegou pelo pacote. Idempotente — o que já está
    indexado é pulado, então rodar de novo depois de uma interrupção retoma.
    """
    if not ARQUIVO.exists():
        print(f"{ARQUIVO} nao existe.", file=sys.stderr)
        return 1
    pacote = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    uid = {u["email"]: r["id"] for u in pacote.get("usuarios", [])
           for r in [db.exec1("SELECT id FROM usuario WHERE email = %(e)s", {"e": u["email"]})]
           if r}
    mesa_id = {(m["usuario"], m["nome"]): r["id"] for m in pacote.get("mesas", [])
               if m["usuario"] in uid
               for r in [db.exec1("SELECT id FROM mesa WHERE usuario_id = %(u)s AND nome = %(n)s",
                                  {"u": uid[m["usuario"]], "n": m["nome"]})] if r}
    # Mesma transação única do importar, e pelo mesmo motivo medido (fsync por
    # insert). Interromper aqui desfaz o documento inteiro em vez de deixá-lo
    # com metade dos trechos — e retomar é só rodar de novo.
    if not _travar():
        print("outra sincronizacao esta rodando agora — nao faco nada")
        return 0
    c = db.conn()
    c.autocommit = False
    try:
        novos, reindexados, pulados = _materiais(pacote, uid, mesa_id, indexar=True)
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.autocommit = True
        _destravar()
    print(f"material: {novos} novos, {reindexados} indexados, {pulados} já em dia")
    return 0


# =========================================================== estado
def estado() -> int:
    n = db.exec1(
        """SELECT (SELECT count(*) FROM usuario) u, (SELECT count(*) FROM mesa) m,
                  (SELECT count(*) FROM questao) q, (SELECT count(*) FROM chunk) c,
                  (SELECT count(*) FROM tentativa) t, (SELECT count(*) FROM conversa) cv,
                  (SELECT count(*) FROM documento WHERE usuario_id IS NOT NULL) mat"""
    )
    print(f"banco local : {n['u']} contas · {n['m']} mesas · {n['q']} questoes · "
          f"{n['c']} chunks · {n['t']} tentativas · {n['cv']} conversas · "
          f"{n['mat']} materiais")
    if ARQUIVO.exists():
        p = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        print(f"arquivo     : {p.get('versao')} gerado {p.get('gerado_em')} · "
              f"{len(p.get('usuarios', []))} contas · {len(p.get('mesas', []))} mesas · "
              f"{len(p.get('questoes', []))} questoes · "
              f"{len(p.get('tentativas', []))} tentativas · "
              f"{len(p.get('conversas', []))} conversas · "
              f"{len(p.get('materiais', []))} materiais "
              f"({ARQUIVO.stat().st_size // 1024} KB)")
    else:
        print(f"arquivo     : {ARQUIVO} nao existe")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["exportar", "importar", "material", "estado"])
    ap.add_argument("--sem-material", action="store_true",
                    help="não põe o TEXTO do material do aluno no pacote")
    ap.add_argument("--sem-senha", action="store_true",
                    help="não põe a senha_hash das contas no pacote")
    ap.add_argument("--material-depois", action="store_true",
                    help="importar: grava a linha do material e NÃO calcula embedding "
                         "(quem termina é 'sincronizar.py material')")
    a = ap.parse_args()
    if a.acao == "exportar":
        return exportar(com_material=not a.sem_material, com_senha=not a.sem_senha)
    if a.acao == "importar":
        return importar(indexar_material=not a.material_depois)
    return {"material": material, "estado": estado}[a.acao]()


if __name__ == "__main__":
    sys.exit(main())
