"""Biblioteca do aluno (019): material privado indexado no acervo comum."""
import pytest

from core import db, material, retrieval

VERSAO = "test-material-v1"
TXT = ("MEU RESUMO PARTICULAR\n\nO mnemônico QUIXOTEBRAVO organiza os prazos "
       "recursais do processo penal conforme minha anotação de aula. " * 10).encode()


def _material(client, headers, nome="Resumo.txt", disciplina="Direito Processual Penal"):
    return client.post("/materiais",
                       files={"arquivo": (nome, TXT, "text/plain")},
                       data={"disciplina": disciplina, "tipo": "resumo"},
                       headers=headers)


def test_sobe_lista_e_apaga(client, usuario):
    r = _material(client, usuario["headers"])
    assert r.status_code == 201, r.text
    doc = r.json()
    # Responde NA HORA com processando: o embedding leva minutos e não pode
    # acontecer dentro do request.
    assert doc["status"] == "processando" and doc["chunks_total"] >= 1

    lista = client.get("/materiais", headers=usuario["headers"]).json()["materiais"]
    assert [m["id"] for m in lista] == [doc["id"]]

    assert client.delete(f"/materiais/{doc['id']}", headers=usuario["headers"]).status_code == 200
    assert client.get("/materiais", headers=usuario["headers"]).json()["materiais"] == []


def test_disciplina_e_OPCIONAL_e_o_sistema_descobre(client, usuario, llm_falso):
    """MUDANÇA DELIBERADA (020). Antes a disciplina era obrigatória e isso não
    sobreviveu ao primeiro uso real: subir 14 aulas de um curso é digitar a
    mesma coisa 14 vezes, e o caso que mais importa é o material que a pessoa
    NÃO conhece ("joguei lá, não sei se agrega"). Obrigar a rotular é obrigar a
    LER antes de subir — inverte quem trabalha."""
    llm_falso.retorno = '{"disciplina": "Direito Processual Penal", "assunto": "Prazos recursais"}'
    r = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                    data={"tipo": "resumo"}, headers=usuario["headers"])
    assert r.status_code == 201
    doc = r.json()
    assert doc["disciplina"] is None and doc["classificado_por"] is None

    material.indexar(doc["id"], "x.txt", TXT)
    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["disciplina"] == "Direito Processual Penal"
    assert m["assunto"] == "Prazos recursais"
    assert m["classificado_por"] == "modelo"


def test_palpite_do_modelo_nao_sobrescreve_o_que_o_aluno_disse(client, usuario, llm_falso):
    """Quem informou a matéria decidiu. Um palpite passando por cima é o
    sistema discordando de quem tem mais contexto — mas o campo VAZIO ainda é
    completado, porque "informei a disciplina, descubra o assunto" é normal."""
    llm_falso.retorno = '{"disciplina": "Outra Coisa", "assunto": "Prazos recursais"}'
    doc = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                      data={"disciplina": "Direito Penal", "tipo": "resumo"},
                      headers=usuario["headers"]).json()
    assert doc["classificado_por"] == "aluno"
    material.indexar(doc["id"], "x.txt", TXT)
    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["disciplina"] == "Direito Penal"      # preservado
    assert m["assunto"] == "Prazos recursais"      # completado
    assert m["classificado_por"] == "aluno"        # a parte que recorta é dele


def test_falha_do_classificador_nao_perde_o_material(client, usuario, llm_falso):
    """Sem cota, o material continua indexado e buscável — só aparece sem
    rótulo. Perder o material porque a cota acabou seria trocar um defeito
    pequeno por um grande."""
    llm_falso.excecao = RuntimeError("sem cota")
    doc = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                      data={"tipo": "resumo"}, headers=usuario["headers"]).json()
    material.indexar(doc["id"], "x.txt", TXT)
    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["status"] == "pronto" and m["chunks"] >= 1
    assert m["disciplina"] is None


def test_aluno_corrige_o_palpite(client, usuario):
    doc = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                      data={"tipo": "resumo"}, headers=usuario["headers"]).json()
    r = client.patch(f"/materiais/{doc['id']}",
                     json={"disciplina": "Direito Constitucional", "assunto": "Remédios"},
                     headers=usuario["headers"])
    assert r.status_code == 200
    assert r.json()["disciplina"] == "Direito Constitucional"
    assert r.json()["classificado_por"] == "aluno"


def test_corrigir_material_de_outro_da_404(client, usuario, outro_usuario):
    doc = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                      data={"tipo": "resumo"}, headers=usuario["headers"]).json()
    r = client.patch(f"/materiais/{doc['id']}", json={"disciplina": "X"},
                     headers=outro_usuario["headers"])
    assert r.status_code == 404


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/admin",
    "http://localhost/admin",
    "http://169.254.169.254/latest/meta-data/",   # credencial de instância em nuvem
    "http://10.0.0.5/interno",
    "file:///etc/passwd",
])
def test_link_recusa_endereco_interno(client, usuario, url):
    """SSRF: o pedido sai de DENTRO da rede. A checagem é sobre o IP RESOLVIDO,
    não sobre o texto da URL — `http://meu-dominio.com` pode apontar pra
    127.0.0.1, e olhar só a string não veria."""
    r = client.post("/materiais/link", json={"url": url}, headers=usuario["headers"])
    assert r.status_code == 400


def test_tipo_lei_e_recusado(client, usuario):
    """Material do aluno NUNCA entra como lei: `chunk_lei` extrai (norma,
    artigo) pra citação exata, e apostila comentada cita "art. 312" no meio do
    texto do professor — viraria chunk com artigo='312' e `por_dispositivo`
    devolveria o comentário em vez da lei."""
    r = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                    data={"disciplina": "Direito Penal", "tipo": "lei"},
                    headers=usuario["headers"])
    assert r.status_code == 400


def test_texto_curto_avisa_sobre_ocr(client, usuario):
    """PDF escaneado é imagem: o texto extraído vem quase vazio. Dizer "falhou"
    não deixa o aluno agir; dizer "rode OCR" deixa."""
    r = client.post("/materiais", files={"arquivo": ("x.txt", b"tres palavras aqui", "text/plain")},
                    data={"disciplina": "Direito Penal", "tipo": "resumo"},
                    headers=usuario["headers"])
    assert r.status_code == 400 and "OCR" in r.json()["detail"]


def test_mesmo_arquivo_duas_vezes_e_barrado(client, usuario):
    assert _material(client, usuario["headers"]).status_code == 201
    r = _material(client, usuario["headers"])
    assert r.status_code == 400 and "já subiu" in r.json()["detail"]


def test_material_de_outro_aluno_nao_aparece_nem_apaga(client, usuario, outro_usuario):
    """O contrato da tela ("só você tem acesso") tem que ser do BANCO, não da
    interface. 404 e não 403 pra não confirmar a quem chuta um id."""
    doc = _material(client, usuario["headers"]).json()
    assert client.get("/materiais", headers=outro_usuario["headers"]).json()["materiais"] == []
    assert client.delete(f"/materiais/{doc['id']}", headers=outro_usuario["headers"]).status_code == 404


def test_busca_isola_biblioteca_entre_alunos(client, usuario, outro_usuario):
    """O teste que justifica a migração inteira: sem `documento.usuario_id`, a
    apostila paga de um aluno entraria no prompt do tutor de todos os outros."""
    doc = _material(client, usuario["headers"]).json()
    material.indexar(doc["id"], "Resumo.txt", TXT)   # síncrono aqui: sem background

    def achou(uid):
        return any("QUIXOTEBRAVO" in c["texto"]
                   for c in retrieval.buscar("QUIXOTEBRAVO prazos recursais", n=6, usuario_id=uid))

    assert achou(usuario["id"]), "o dono tem que achar o próprio material"
    assert not achou(outro_usuario["id"]), "outro aluno NÃO pode achar"
    assert not achou(None), "sem usuário (CLI/avaliar_retrieval) vê só o acervo público"


def test_falha_no_indexar_vira_status_e_nao_excecao(client, usuario, monkeypatch):
    """Exceção em background task morre sem ninguém ver, e o aluno ficaria com
    "processando" pra sempre. Vira `status='falha'` com a razão em texto."""
    doc = _material(client, usuario["headers"]).json()
    monkeypatch.setattr(material.embeddings, "embed_passagens",
                        lambda _: (_ for _ in ()).throw(RuntimeError("modelo fora do ar")))
    material.indexar(doc["id"], "Resumo.txt", TXT)
    m = db.exec1("SELECT status, erro FROM documento WHERE id = %(i)s", {"i": doc["id"]})
    assert m["status"] == "falha" and "modelo fora do ar" in m["erro"]


def test_indexar_e_idempotente(client, usuario):
    """Reindexar não pode dobrar os trechos. Acontece de verdade em dois casos:
    o processo reinicia no meio (linha fica "processando" e alguém manda tentar
    de novo) e o retry manual da tela."""
    doc = _material(client, usuario["headers"]).json()
    for _ in range(3):
        material.indexar(doc["id"], "Resumo.txt", TXT)
    n = db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id=%(i)s", {"i": doc["id"]})["n"]
    assert n == doc["chunks_total"]


def test_reindexar_de_outro_aluno_da_404(client, usuario, outro_usuario):
    doc = _material(client, usuario["headers"]).json()
    r = client.post(f"/materiais/{doc['id']}/reindexar",
                    files={"arquivo": ("Resumo.txt", TXT, "text/plain")},
                    headers=outro_usuario["headers"])
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Sugestões de rótulo (o seletor da tela de biblioteca)
# ---------------------------------------------------------------------------

def _subir(client, headers, nome, disciplina=None, assunto=None):
    """Como `_material`, mas com rótulo à escolha e conteúdo único por nome —
    `registrar` barra o MESMO arquivo duas vezes (hash), e um lote de teste
    precisa de linhas distintas."""
    dados = {"tipo": "resumo"}
    if disciplina is not None:
        dados["disciplina"] = disciplina
    if assunto is not None:
        dados["assunto"] = assunto
    corpo = (f"MEU RESUMO {nome}\n\n" + TXT.decode()).encode()
    return client.post("/materiais", files={"arquivo": (nome, corpo, "text/plain")},
                       data=dados, headers=headers)


def test_sugestoes_saem_so_da_biblioteca_de_quem_pergunta(client, usuario, outro_usuario):
    """Sugerir a disciplina que OUTRO aluno cadastrou vazaria o que ele estuda.

    Mesmo princípio já testado em `listar`/`buscar`, aqui num campo que parece
    inofensivo — nome de matéria — mas que revela o material de outra pessoa."""
    _subir(client, usuario["headers"], "meu.txt", "Direito Penal", "Peculato")
    _subir(client, outro_usuario["headers"], "dele.txt", "Contabilidade", "DRE")

    s = client.get("/materiais/sugestoes", headers=usuario["headers"]).json()
    assert s["disciplinas"] == ["Direito Penal"]
    assert s["assuntos"] == ["Peculato"]
    assert "Contabilidade" not in s["disciplinas"] and "DRE" not in s["assuntos"]


def test_sugestoes_agrupam_assunto_por_disciplina(client, usuario):
    """A tela oferece o assunto DA matéria escolhida — oferecer "Remédios
    constitucionais" a quem digita Contabilidade é ruído, não sugestão."""
    h = usuario["headers"]
    _subir(client, h, "a.txt", "Direito Penal", "Peculato")
    _subir(client, h, "b.txt", "Direito Penal", "Concussão")
    _subir(client, h, "c.txt", "Direito Constitucional", "Remédios")

    s = client.get("/materiais/sugestoes", headers=h).json()
    assert s["assuntos_por_disciplina"]["Direito Penal"] == ["Concussão", "Peculato"]
    assert s["assuntos_por_disciplina"]["Direito Constitucional"] == ["Remédios"]


def test_sugestoes_nao_oferecem_vazio_nem_repetem(client, usuario, llm_falso):
    """Disciplina é OPCIONAL (020), então a biblioteca tem linhas sem rótulo —
    e nenhuma delas pode virar opção em branco na lista. Repetição também não:
    14 aulas do mesmo curso são UMA sugestão, e é justamente o lote de 14 (os
    campos preenchidos uma vez só) que produz esse caso.

    `llm_falso` devolvendo lixo é de propósito: sem ele o classificador REAL
    roda e rotula os sem-rótulo — comportamento correto (é o que a 020 existe
    pra fazer), mas que apagaria justamente o caso que este teste mede, além
    de gastar cota a cada pytest."""
    llm_falso.retorno = "isto não é json"
    h = usuario["headers"]
    for i in range(3):
        _subir(client, h, f"aula-{i}.txt", "Direito Penal", "Peculato")
    _subir(client, h, "sem-rotulo.txt")
    _subir(client, h, "so-assunto.txt", assunto="Avulso")

    s = client.get("/materiais/sugestoes", headers=h).json()
    assert s["disciplinas"] == ["Direito Penal"]
    assert s["assuntos"] == ["Avulso", "Peculato"]
    # Assunto sem disciplina não inventa grupo: nem chave vazia, nem null.
    assert list(s["assuntos_por_disciplina"]) == ["Direito Penal"]


def test_sugestoes_nao_sao_engolidas_pela_rota_de_id(client, usuario):
    """`/materiais/sugestoes` conviver com `/materiais/{id}` é ordem de
    registro, não sorte: uma rota de path param declarada antes tentaria
    converter "sugestoes" em int. Este teste quebra se alguém reordenar."""
    r = client.get("/materiais/sugestoes", headers=usuario["headers"])
    assert r.status_code == 200 and "disciplinas" in r.json()


# ---------------------------------------------------------------------------
# Sanitização do texto extraído
# ---------------------------------------------------------------------------

def test_nul_do_pdf_nao_derruba_a_indexacao(client, usuario, llm_falso):
    """Bug REAL, com nome e sobrenome: uma aula de curso (a que traz marca
    d'água por página) trouxe `\\x00` na extração e o Postgres recusou —
    "text fields cannot contain NUL (0x00)" — deixando o material em `falha`
    depois de o aluno já ter esperado a indexação.

    O nulo é do PDF, não do nosso código: o pypdf devolve o que está lá. Por
    isso a limpeza fica na EXTRAÇÃO e não em cada INSERT — o texto tem três
    destinos (documento, chunk, classificador) e limpar em cada um é a receita
    pro dia em que um caminho novo esquecer."""
    llm_falso.retorno = "não é json"
    corpo = ("MEU RESUMO\x00 COM NULO\n\n"
             "Prazo\x01 recursal\x07 e o mnemônico QUIXOTEBRAVO. " * 12).encode()
    r = client.post("/materiais", files={"arquivo": ("aula-com-nulo.txt", corpo, "text/plain")},
                    data={"tipo": "resumo"}, headers=usuario["headers"])
    assert r.status_code == 201, r.text
    doc = r.json()

    m = [x for x in client.get("/materiais", headers=usuario["headers"]).json()["materiais"]
         if x["id"] == doc["id"]][0]
    assert m["status"] == "pronto", m["erro"]
    assert m["chunks"] >= 1

    # E o texto gravado não carrega o lixo: ele iria pro embedding e pro prompt,
    # onde ninguém consegue vê-lo pra depurar.
    texto = db.exec1("SELECT texto FROM chunk WHERE documento_id = %(d)s LIMIT 1",
                     {"d": doc["id"]})["texto"]
    assert "\x00" not in texto and "\x01" not in texto and "\x07" not in texto
    assert "QUIXOTEBRAVO" in texto


def test_limpar_preserva_a_estrutura_do_texto():
    """Tab, `\\n` e `\\r` NÃO são lixo: são o que separa parágrafo de parágrafo,
    e é por parágrafo que `chunk_generico` divide o material do aluno. Limpar
    demais aqui viraria um chunk gigante só."""
    assert material._limpar("a\x00b\x1fc") == "abc"
    assert material._limpar("linha1\nlinha2\tcol\r\n") == "linha1\nlinha2\tcol\r\n"


# ---------------------------------------------------------------------------
# Biblioteca por mesa (migração 021)
# ---------------------------------------------------------------------------

def test_mesa_isolada_nao_le_o_material_da_outra(client, usuario):
    """Relatado em uso: "ele estuda informática e não quer contaminar o ambiente
    dele com direito".

    A 019 pôs dono no material e resolveu o vazamento ENTRE ALUNOS; não resolveu
    a separação DENTRO do mesmo aluno. Quem prepara dois concursos ao mesmo tempo
    — o caso normal, e a razão de a 010 existir — via o tutor citando a apostila
    de Direito Penal numa pergunta de Redes.

    O recorte entra DENTRO das CTEs de `retrieval`, junto do predicado de dono e
    pelo mesmo motivo: filtrar depois de rankear faria o material da outra mesa
    gastar vaga no top-6 e sair da lista, e a pergunta perderia contexto sem
    ninguém ver por quê."""
    ti = client.post("/mesas", json={"nome": "TI 021"}, headers=usuario["headers"]).json()
    dg = client.post("/mesas", json={"nome": "Delegado 021"}, headers=usuario["headers"]).json()
    cab_ti = {**usuario["headers"], "X-Mesa-Id": str(ti["id"])}
    cab_dg = {**usuario["headers"], "X-Mesa-Id": str(dg["id"])}

    client.post("/materiais", headers=cab_ti, data={"tipo": "resumo", "disciplina": "Informática"},
                files={"arquivo": ("redes.txt",
                                   ("MNEMONICO ZORBAXTI organiza as camadas. " * 30).encode(),
                                   "text/plain")})
    client.post("/materiais", headers=cab_dg, data={"tipo": "resumo", "disciplina": "Direito Penal"},
                files={"arquivo": ("penal.txt",
                                   ("MNEMONICO QUIXOTEPENAL organiza os crimes. " * 30).encode(),
                                   "text/plain")})

    def ve(termo, mesa_id):
        return any(termo in (c.get("texto") or "") for c in
                   retrieval.buscar(termo, n=6, usuario_id=usuario["id"], mesa_id=mesa_id))

    # COMPARTILHADA é o default, e tem que continuar sendo: quem já subiu
    # material está usando tudo em todas as mesas, e entrar isolando calado
    # mudaria o resultado do tutor sem ninguém pedir.
    assert client.get("/mesa", headers=cab_ti).json()["biblioteca_compartilhada"] is True
    # `mesa_id=None` significa "não recorte". O BUG que só apareceu medindo: sem
    # a guarda `%(mid)s::bigint IS NULL`, isto EXCLUÍA todo material que tem
    # mesa, porque `d.mesa_id = NULL` é NULL e nunca true em SQL — o caso comum
    # ficava sem ver a própria biblioteca.
    assert ve("ZORBAXTI", None) and ve("QUIXOTEPENAL", None)

    # ISOLADO: cada mesa vê só o seu.
    assert ve("ZORBAXTI", ti["id"]) and not ve("QUIXOTEPENAL", ti["id"])
    assert ve("QUIXOTEPENAL", dg["id"]) and not ve("ZORBAXTI", dg["id"])

    # E o acervo PÚBLICO atravessa qualquer isolamento: lei seca serve a todo
    # concurso, e cortá-la daria "não encontrei" pra pergunta que o acervo
    # responde.
    assert retrieval.buscar("art. 312", n=4, usuario_id=usuario["id"], mesa_id=ti["id"])


def test_interruptor_da_biblioteca_e_reversivel_e_nao_move_material(client, usuario):
    """O pedido foi explícito: "isso deve ser alterado a qualquer instante por
    ele". Então o interruptor não move nem apaga nada — só muda o que a busca vê.

    E `None` no PATCH PRESERVA: um pedido que só troca o nome da mesa não pode
    religar a biblioteca compartilhada de volta sem ninguém pedir."""
    m = client.post("/mesas", json={"nome": "Vai e volta"}, headers=usuario["headers"]).json()
    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}
    client.post("/materiais", headers=cab, data={"tipo": "resumo"},
                files={"arquivo": ("x.txt", ("material qualquer. " * 30).encode(), "text/plain")})
    antes = db.exec1("SELECT count(*) n FROM documento WHERE mesa_id = %(m)s", {"m": m["id"]})["n"]

    client.patch(f"/mesas/{m['id']}", json={"biblioteca_compartilhada": False},
                 headers=usuario["headers"])
    assert client.get("/mesa", headers=cab).json()["biblioteca_compartilhada"] is False

    client.patch(f"/mesas/{m['id']}", json={"nome": "Só o nome"}, headers=usuario["headers"])
    assert client.get("/mesa", headers=cab).json()["biblioteca_compartilhada"] is False

    client.patch(f"/mesas/{m['id']}", json={"biblioteca_compartilhada": True},
                 headers=usuario["headers"])
    assert client.get("/mesa", headers=cab).json()["biblioteca_compartilhada"] is True
    assert db.exec1("SELECT count(*) n FROM documento WHERE mesa_id = %(m)s",
                    {"m": m["id"]})["n"] == antes


def test_apagar_mesa_nao_apaga_o_material(client, usuario):
    """`ON DELETE SET NULL`, não CASCADE: o PDF é do ALUNO, não do concurso —
    mesma decisão que fez `simulado -> mesa` ser SET NULL na 010, e pelo mesmo
    motivo (a mesa é etiqueta, não dona). Perder a apostila paga porque a mesa
    foi criada errada e apagada seria o pior estrago possível nesta tela.

    O material cai no POOL COMUM (`mesa_id NULL`), que toda mesa lê — inclusive
    as isoladas. Some da etiqueta, não da biblioteca."""
    m = client.post("/mesas", json={"nome": "Mesa efêmera"}, headers=usuario["headers"]).json()
    cab = {**usuario["headers"], "X-Mesa-Id": str(m["id"])}
    r = client.post("/materiais", headers=cab, data={"tipo": "resumo"},
                    files={"arquivo": ("sobrevive.txt",
                                       ("MNEMONICO SOBREVIVENTE. " * 30).encode(), "text/plain")})
    doc = r.json()["id"]

    client.delete(f"/mesas/{m['id']}", headers=usuario["headers"])
    linha = db.exec1("SELECT usuario_id, mesa_id FROM documento WHERE id = %(d)s", {"d": doc})
    assert linha is not None and linha["usuario_id"] == usuario["id"]
    assert linha["mesa_id"] is None
    assert doc in [x["id"] for x in client.get("/materiais", headers=usuario["headers"]).json()["materiais"]]


def test_subir_material_nao_bloqueia_o_event_loop(client, usuario):
    """Travamento MEDIDO e relatado: "a API parece sobrecarregar a aplicação
    inteira" ao subir PDF.

    `POST /materiais` é `async def`, e dentro de uma corrotina qualquer chamada
    bloqueante para o EVENT LOOP INTEIRO — todas as requisições, de todos os
    usuários. `registrar` extrai o PDF, divide em trechos, calcula hash e escreve
    no banco: num edital de 1,5 MB isso levou 9,8s.

    Sondando `/fila` a cada 200ms durante o upload, antes do conserto: latência
    de 289ms (baseline) para 9.295ms, e só 2 sondas completaram em ~10s em vez de
    ~50. Depois de mover o trabalho pro pool de threads, MESMO PDF: 14 sondas,
    pior caso 360ms, nenhuma acima de 1s.

    Este teste não mede latência (o TestClient é síncrono e não reproduz
    concorrência) — ele trava o CONSERTO: garante que a rota não voltou a chamar
    `registrar` direto do corpo da corrotina. Sem isso, o defeito volta na
    primeira vez que alguém "simplificar" o `await run_in_threadpool`."""
    import inspect
    import api as apimod

    fonte = inspect.getsource(apimod.rota_subir_material)
    assert inspect.iscoroutinefunction(apimod.rota_subir_material)
    assert "run_in_threadpool" in fonte, (
        "rota async voltou a chamar código bloqueante no event loop")
    # A chamada direta não pode reaparecer fora do executor.
    assert "material.registrar(" not in fonte.replace("material.registrar,", "")

    fonte_re = inspect.getsource(apimod.rota_reindexar_material)
    assert "run_in_threadpool" in fonte_re

    # E o caminho continua funcionando ponta a ponta.
    r = client.post("/materiais", headers=usuario["headers"], data={"tipo": "resumo"},
                    files={"arquivo": ("no-pool.txt",
                                       ("material que passa pelo pool. " * 30).encode(),
                                       "text/plain")})
    assert r.status_code == 201 and r.json()["status"] == "processando"
