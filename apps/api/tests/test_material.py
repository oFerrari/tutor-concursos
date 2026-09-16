"""Biblioteca do aluno (019): material privado indexado no acervo comum."""
import time

import pytest

from core import db, material, retrieval

VERSAO = "test-material-v10"
TXT = ("MEU RESUMO PARTICULAR\n\nO mnemônico QUIXOTEBRAVO organiza os prazos "
       "recursais do processo penal conforme minha anotação de aula. " * 10).encode()


def _material(client, headers, nome="Resumo.txt", disciplina="Direito Processual Penal"):
    return client.post("/materiais",
                       files={"arquivo": (nome, TXT, "text/plain")},
                       data={"disciplina": disciplina, "tipo": "resumo"},
                       headers=headers)


def _esperar_indexacao():
    """A indexação agora é ASSÍNCRONA de verdade (fila com um trabalhador).

    Antes o `BackgroundTasks` do FastAPI rodava dentro da própria requisição do
    `TestClient`, então dava pra subir material e afirmar `pronto` na linha
    seguinte. Isso escondia o comportamento real — e escondeu justamente o que
    derrubou o servidor no upload de 20 apostilas, porque em teste as vinte
    nunca corriam ao mesmo tempo."""
    # No teste a indexação é SÍNCRONA (ver `_indexar_sincrono` no conftest), então
    # não há fila pra esperar — esta função existe pra que os testes não precisem
    # saber disso, e pra continuar valendo se um dia a fila voltar pra cá.
    assert material.esperar_fila(30), "a fila de indexação não drenou no tempo"


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
    # ORDEM: drena a fila PRIMEIRO, e só então indexa à mão. O trabalhador é
    # global e o `llm_falso` é por teste — indexar em paralelo com ele fazia
    # este teste depender de quem escrevia por último, e ele passava sozinho e
    # falhava na suíte inteira. Com a fila vazia antes, o `indexar` daqui é o
    # único escritor deste documento e o duplê está garantidamente ativo.
    _esperar_indexacao()
    material.indexar(doc["id"], "x.txt", TXT)
    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["status"] == "pronto" and m["chunks"] >= 1
    assert m["disciplina"] is None


def test_nome_do_arquivo_e_evidencia_pro_classificador(client, usuario, llm_falso):
    """O nome com que o material subiu VAI pro prompt, rotulado.

    O classificador lia só o começo do texto, e o começo de uma apostila é a
    capa do primeiro vídeo — uma aula de princípios do direito administrativo
    foi classificada como "Regime jurídico administrativo", que é o tópico 2 de
    7 dela. Quem nomeia o arquivo de "Direito Administrativo - Princípios" leu o
    material e já disse do que ele trata; ignorar isso é jogar fora a única
    evidência que cobre o documento inteiro."""
    llm_falso.retorno = '{"disciplina": "Direito Administrativo", "assunto": "Princípios"}'
    nome = "direito administrativo - Princípios do Direito Administrativo.txt"
    r = client.post("/materiais", files={"arquivo": (nome, TXT, "text/plain")},
                    data={"tipo": "aula"}, headers=usuario["headers"])
    assert r.status_code == 201, r.text
    doc = r.json()
    _esperar_indexacao()

    chamada = llm_falso.chamadas[-1]
    assert "NOME DO ARQUIVO: direito administrativo - Princípios do Direito Administrativo" \
        in chamada["prompt"], chamada["prompt"][:400]
    # SEM a extensão, e o trecho continua indo junto: o nome é evidência a mais,
    # não substituto do texto.
    assert ".txt" not in chamada["prompt"].splitlines()[0]
    assert "MEU RESUMO PARTICULAR" in chamada["prompt"]
    # E as duas ordens viajam com ele: descartar nome inútil (sem isso
    # "scan_001" vira assunto) e, quando nome e texto discordam, obedecer ao
    # TEXTO — um PDF renomeado à mão de "Direitos Humanos" sobre os arts. 6º a
    # 11 da CF é aula de direitos sociais, e é o texto que sabe disso.
    assert "IGNORADO" in chamada["sistema"]
    assert "CONTRADIZ" in chamada["sistema"] and "o texto SEMPRE ganha" in chamada["sistema"]

    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["id"] == doc["id"] and m["assunto"] == "Princípios"


def test_sem_nome_o_prompt_nao_fala_de_arquivo(llm_falso):
    """Regra órfã é instrução pra ninguém: o modelo recebendo "use o nome do
    arquivo" sem nome nenhum tem uma ordem a menos pra cumprir e uma chance a
    mais de inventar. `classificar` é chamável sem a origem — a assinatura é
    opcional de propósito, pra CLI e reprocessamento antigo continuarem valendo."""
    llm_falso.retorno = '{"disciplina": "Direito Penal", "assunto": "Dosimetria"}'
    assert material.classificar("texto qualquer de apostila") == {
        "disciplina": "Direito Penal", "assunto": "Dosimetria"}
    chamada = llm_falso.chamadas[-1]
    assert "NOME DO ARQUIVO" not in chamada["prompt"]
    assert "NOME ORIGINAL DO ARQUIVO" not in chamada["sistema"]


def test_material_so_fica_pronto_depois_de_rotulado(client, usuario, llm_falso):
    """`pronto` é promessa pra TELA, e a tela para de perguntar quando a ouve.

    O polling da biblioteca roda só enquanto existe material `processando`.
    Anunciar `pronto` antes de classificar deixava uma janela de segundos em que
    a lista era buscada já pronta e ainda sem disciplina — a tela desenhava
    "Outros" e congelava assim até um F5. Relatado como "ele não identificou a
    matéria", com a matéria gravada no banco.

    O duplê do LLM CHECA o banco no meio da classificação: é o único jeito de
    afirmar a ordem, porque no fim os dois campos estão certos de qualquer
    maneira."""
    visto = {}
    # Busca pela ORIGEM e não pelo id: a indexação é síncrona no teste, então o
    # classificador roda DENTRO do `client.post` — o id ainda não voltou pra cá
    # quando este código executa.
    nome = "espia-da-ordem.txt"

    class _Espia(type(llm_falso)):
        def gerar(self, *a, **k):
            visto["status"] = db.exec1(
                "SELECT status FROM documento WHERE origem = %(o)s ORDER BY id DESC LIMIT 1",
                {"o": nome})["status"]
            return '{"disciplina": "Direito Penal", "assunto": "Dosimetria"}'

    espia = _Espia()
    from core import llm as _llm
    _llm.obter = lambda: espia  # o monkeypatch do fixture já restaura no fim

    r = client.post("/materiais", files={"arquivo": (nome, TXT, "text/plain")},
                    data={"tipo": "resumo"}, headers=usuario["headers"])
    assert r.status_code == 201, r.text
    _esperar_indexacao()

    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["status"] == "pronto" and m["disciplina"] == "Direito Penal"
    assert visto.get("status") == "processando", \
        "o material foi anunciado pronto antes de ter rótulo — a tela para de atualizar aí"


def test_reindexar_nao_promove_palpite_a_resposta_do_aluno(client, usuario, llm_falso):
    """Material deduzido continua deduzido depois de reindexar.

    A regra antiga decidia a procedência por "a disciplina já está preenchida?",
    o que é verdade na primeira passada e MENTIRA na segunda: quem preencheu foi
    o próprio modelo. Visto acontecer ao reindexar o doc 789 — ele perdeu o
    aviso "eu deduzi, confira" sem ninguém confirmar nada, e um palpite sem
    aviso é pior que um palpite."""
    llm_falso.retorno = '{"disciplina": "Direito Penal", "assunto": "Dosimetria"}'
    doc = client.post("/materiais", files={"arquivo": ("x.txt", TXT, "text/plain")},
                      data={"tipo": "resumo"}, headers=usuario["headers"]).json()
    _esperar_indexacao()
    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["classificado_por"] == "modelo" and m["disciplina"] == "Direito Penal"

    material.indexar(doc["id"], "x.txt", TXT)
    m = client.get("/materiais", headers=usuario["headers"]).json()["materiais"][0]
    assert m["classificado_por"] == "modelo", \
        "reindexar promoveu o palpite do modelo a resposta do aluno"


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
    """Duplicata é barrada — DEPOIS de o primeiro terminar.

    A espera não é detalhe de teste, é a regra: material `processando` sem
    trecho nenhum passou a ser RETOMADO em vez de recusado, porque duplicata
    parada não é duplicata, é serviço inacabado (ver
    `test_subir_de_novo_material_parado_retoma_em_vez_de_recusar`). Sem esperar,
    este teste media a janela em que o primeiro upload ainda estava na fila."""
    assert _material(client, usuario["headers"]).status_code == 201
    _esperar_indexacao()
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
    # ESPERA a fila antes de mexer no mesmo documento: o trabalhador já está
    # indexando este doc, e sem isto a corrida decide o resultado — o `indexar`
    # à mão escreve `falha` e o trabalhador escreve `pronto` em cima (ou o
    # contrário). Corrida que o upload síncrono de antes não tinha.
    _esperar_indexacao()
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


def test_sugestoes_trazem_os_topicos_do_edital_da_mesa(client, usuario):
    """O campo de assunto tem DUAS fontes, e a segunda é o edital.

    O interruptor da tela ("usar sugestões daqui" × "usar do edital") mandava só
    na disciplina: do lado do assunto não havia o que oferecer, porque tópico
    não era exposto por rota nenhuma — só a CONTAGEM dele. O relato foi "sem tá
    obedecendo a nossa opção".

    Por disciplina e nunca chapado: a objeção medida contra tópico como sugestão
    (1015 num edital real) só cai porque a tela pede a lista de UM material, que
    tem UMA disciplina. E é da MESA do cabeçalho — edital de outra mesa não pode
    sugerir aqui, senão o recorte que a 010 criou vazaria pelo seletor.
    """
    h = usuario["headers"]
    m = client.post("/mesas", json={"nome": "PC-PR"}, headers=h).json()
    eid = db.exec1("INSERT INTO edital (mesa_id, titulo) VALUES (%(m)s,'e') RETURNING id",
                   {"m": m["id"]})["id"]
    for i, (disc, texto) in enumerate([("Direito Constitucional", "Nacionalidade"),
                                       ("Direito Constitucional", "Direitos políticos"),
                                       ("Direito Penal", "Peculato")]):
        db.query("""INSERT INTO topico (edital_id, disciplina, ordem, texto)
                    VALUES (%(e)s, %(d)s, %(o)s, %(t)s)""",
                 {"e": eid, "d": disc, "o": i, "t": texto})

    cab = {**h, "X-Mesa-Id": str(m["id"])}
    s = client.get("/materiais/sugestoes", headers=cab).json()
    assert s["topicos_por_disciplina"]["Direito Constitucional"] == [
        "Nacionalidade", "Direitos políticos"], "perdeu a ordem do edital"
    assert s["topicos_por_disciplina"]["Direito Penal"] == ["Peculato"]

    # Outra mesa, outro recorte: o edital da PC-PR não sugere nada aqui.
    outra = client.post("/mesas", json={"nome": "Sem edital"}, headers=h).json()
    s2 = client.get("/materiais/sugestoes",
                    headers={**h, "X-Mesa-Id": str(outra["id"])}).json()
    assert s2["topicos_por_disciplina"] == {}


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

    _esperar_indexacao()
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

    # A busca só vê o que já foi indexado, e a indexação agora é assíncrona
    # (fila com um trabalhador). Sem esperar, este teste afirmava isolamento
    # sobre uma biblioteca ainda vazia — passava por não achar nada em lugar
    # nenhum, que é o pior jeito de um teste de isolamento passar.
    _esperar_indexacao()

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


# ------------------------------------------- arquivo original (migração 024)
def test_arquivo_original_volta_igual_e_so_pro_dono(client, usuario, outro_usuario):
    """Os BYTES do upload são guardados e devolvidos idênticos, só ao dono.

    Existe porque a alternativa era o aluno guardar o PDF no computador pra
    sempre — `documento.origem` guardava só o NOME, e o docstring de
    `para_reindexar` dizia "quem tem que reenviar o arquivo é ele". O pedido
    real foi reler a apostila sem depender da máquina onde ela foi subida.

    Trava as três coisas que podem regredir juntas e em silêncio: o byte-a-byte
    (um encode no meio do caminho corromperia sem erro nenhum), o 404 pra
    material de outro dono (id sequencial na URL entregaria apostila paga
    alheia) e o nome no Content-Disposition, que sai de `origem` e não do
    título — o título é editável e pode ter virado "Aula 4 — revisar", que não é
    nome de arquivo."""
    conteudo = ("Preservacao do local de crime. " * 90).encode("utf-8")
    r = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                    files={"arquivo": ("aula-024.txt", conteudo, "text/plain")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]

    na_lista = next(m for m in client.get("/materiais", headers=usuario["headers"])
                    .json()["materiais"] if m["id"] == doc_id)
    assert na_lista["tem_arquivo"] is True
    assert na_lista["arquivo_bytes"] == len(conteudo)

    baixado = client.get(f"/materiais/{doc_id}/arquivo", headers=usuario["headers"])
    assert baixado.status_code == 200
    assert baixado.content == conteudo
    assert 'filename="aula-024.txt"' in baixado.headers["content-disposition"]

    # 404 e não 403: não confirmar a quem chuta um id que ele existe.
    assert client.get(f"/materiais/{doc_id}/arquivo",
                      headers=outro_usuario["headers"]).status_code == 404


def test_rotulo_corrigido_entra_no_indice_e_a_busca_acha(client, usuario):
    """Corrigir disciplina/assunto muda o que a BUSCA encontra (024 + 025).

    Era o buraco que o dono apontou: o rótulo que ele digitava valia pra lista,
    pra geração de questão e pro seletor da tela, e NÃO pra busca — só o corpo
    do trecho era indexado. Rotular uma apostila como "Ciências Forenses" não
    fazia a busca achá-la quando ele perguntava de ciências forenses.

    DUAS ARMADILHAS QUE ESTE TESTE JÁ CAIU, e por isso ele é assim:

    1. Afirmar "fora do top6 antes, dentro depois" NÃO serve: `hibrida()` é
       k-vizinhos SEM piso de relevância (é a razão de `core/assunto.py`
       existir), então sempre devolve 6, e "estar fora" depende de quanto
       material concorrente há no banco. Mesma fragilidade do `LIMIT 1` sem
       `ORDER BY` que quebrou o test_geracao. A asserção é sobre o TSVECTOR,
       que é determinístico.

    2. Subir sem rótulo pra medir o "antes" também não serve: `_classificar_se_faltar`
       roda em background e ACERTOU sozinho — leu "crista, desenho imutável,
       pontos característicos" e rotulou como papiloscopia antes de o teste
       corrigir. Então o material entra com um rótulo EXPLÍCITO e errado, o que
       tem o bônus de provar algo mais forte: o índice segue a correção nos dois
       sentidos, ganhando o termo novo e perdendo o velho.
    """
    corpo = ("A crista termina em um ponto e reinicia adiante formando ilha. "
             "O desenho e unico e imutavel ao longo da vida. ") * 12
    r = client.post("/materiais", headers=usuario["headers"],
                    data={"tipo": "aula", "disciplina": "Direito Civil",
                          "assunto": "Contratos"},
                    files={"arquivo": ("aula-025.txt", corpo.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    material.indexar(doc_id, "aula-025.txt", corpo.encode())

    def casa(termo: str) -> bool:
        return bool(db.exec1(
            """SELECT 1 AS x FROM chunk
                WHERE documento_id = %(d)s
                  AND busca @@ websearch_to_tsquery('portuguese', %(t)s) LIMIT 1""",
            {"d": doc_id, "t": termo}))

    assert casa("contratos"), "o rótulo do upload não entrou no índice"
    assert not casa("papiloscopia")

    r2 = material.atualizar(usuario["id"], doc_id, "Ciências Forenses", "Papiloscopia")
    assert r2["reindexar"] is True, "sem arquivo guardado (024) não há como reindexar"
    nome, dados = material.bytes_do_arquivo(usuario["id"], doc_id)
    material.indexar(doc_id, nome, dados)

    assert casa("papiloscopia"), "o assunto corrigido não chegou ao índice"
    assert casa("ciências forenses"), "a disciplina corrigida não chegou ao índice"
    assert not casa("contratos"), "o rótulo ANTIGO ficou no índice depois da correção"

    alvo = {c["id"] for c in db.query(
        "SELECT id FROM chunk WHERE documento_id = %(d)s", {"d": doc_id})}
    for consulta in ("papiloscopia", "ciências forenses"):
        achados = retrieval.buscar(consulta, n=6, usuario_id=usuario["id"])
        assert alvo & {c["id"] for c in achados}, f"busca por {consulta!r} não achou"

    linha = db.exec1("SELECT texto, rotulo FROM chunk WHERE documento_id = %(d)s "
                     "ORDER BY ordem LIMIT 1", {"d": doc_id})
    # ASSUNTO PRIMEIRO: nome de disciplina muda entre editais ("Direito
    # Administrativo" × "Noções de Direito Administrativo" × "... e Gestão
    # Pública" — a PC-PR tem duas dessas ao mesmo tempo), e apostila rotulada
    # com o nome de um edital deixaria de ser achada ao trocar de concurso. O
    # assunto não tem esse problema.
    assert linha["rotulo"] == "Papiloscopia. Ciências Forenses"
    assert not linha["texto"].startswith("Ciências Forenses"), \
        "o rótulo vazou pro texto exibido — o prompt leria isso como conteúdo"


def test_indexacao_pendente_e_retomada_sem_reenviar_o_arquivo(client, usuario):
    """Restart no meio da indexação deixa de ser perda (024 + retomada).

    A indexação roda em background NO PROCESSO — não há worker. Antes de os
    bytes ficarem no banco, um `--reload` do uvicorn no meio deixava a linha em
    `processando` PRA SEMPRE, e o único jeito de sair era o aluno reenviar o
    PDF. É isso que tornava carga grande uma aposta: subir vinte apostilas
    exigia que nada reiniciasse por horas.

    O teste simula o restart do jeito mais direto: `registrar` grava a linha
    como `processando` e NÃO indexa (é `indexar` que faz isso, noutra thread).
    Então o estado logo após `registrar` é exatamente o estado em que um crash
    deixaria o material.
    """
    corpo = ("Preservacao do local de crime e cadeia de custodia. " * 60).encode()
    r = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                    files={"arquivo": ("aula-retomar.txt", corpo, "text/plain")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    db.query("DELETE FROM chunk WHERE documento_id = %(d)s", {"d": doc_id})
    db.query("UPDATE documento SET status='processando' WHERE id = %(d)s", {"d": doc_id})

    assert doc_id in [d["id"] for d in material.pendentes_retomaveis()]

    # `retomar_pendentes` ENFILEIRA — quem trabalha é o trabalhador único da
    # fila, noutra thread. Esperar aqui é o que o teste tem de fazer; antes
    # `retomar_pendentes` indexava em série e o assert vinha logo depois.
    material.retomar_pendentes()
    for _ in range(120):
        if material.tamanho_da_fila() == 0 and db.exec1(
                "SELECT status FROM documento WHERE id = %(d)s",
                {"d": doc_id})["status"] != "processando":
            break
        time.sleep(1)

    linha = db.exec1("SELECT status FROM documento WHERE id = %(d)s", {"d": doc_id})
    assert linha["status"] == "pronto", "a retomada não terminou o serviço"
    assert db.exec1("SELECT count(*) AS n FROM chunk WHERE documento_id = %(d)s",
                    {"d": doc_id})["n"] > 0


def test_arquivo_gigante_falha_antes_de_extrair():
    """Teto no upload DIRETO. Só o caminho por link tinha (`MAX_BYTES_URL`); o
    arrastar-e-soltar não tinha nenhum, e com a 024 um PDF de 200 MB passaria a
    ser gravado inteiro no banco. Falhar antes de extrair é falhar barato."""
    with pytest.raises(material.ErroMaterial, match="o teto é"):
        material.registrar(1, "gigante.txt", b"x" * (material.MAX_BYTES_ARQUIVO + 1),
                           tipo="aula")


def test_subir_de_novo_material_parado_retoma_em_vez_de_recusar(client, usuario):
    """Duplicata PARADA não é duplicata — é serviço inacabado.

    Relatado do jeito mais claro possível: o servidor caiu no meio do upload de
    20 apostilas, o dono subiu as 18 restantes de novo, e recebeu "você já subiu
    este arquivo" DEZOITO vezes — enquanto as linhas estavam no banco sem um
    único trecho indexado. A reação certa dele era terminar o serviço; o sistema
    tratou como erro dele.

    O que continua recusado é a duplicata REAL (`pronto` com trechos): ali
    reindexar seria pagar CPU de novo pelo mesmo material.
    """
    corpo = ("Local de crime e cadeia de custodia. " * 90).encode()
    r1 = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                     files={"arquivo": ("aula-dup.txt", corpo, "text/plain")})
    assert r1.status_code == 201, r1.text
    doc_id = r1.json()["id"]

    # O estado exato em que um crash deixa o material.
    _esperar_indexacao()
    db.query("DELETE FROM chunk WHERE documento_id = %(d)s", {"d": doc_id})
    db.query("UPDATE documento SET status='processando' WHERE id = %(d)s", {"d": doc_id})

    r2 = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                     files={"arquivo": ("aula-dup.txt", corpo, "text/plain")})
    assert r2.status_code == 201, r2.text
    assert r2.json()["retomado"] is True, "recusou como duplicata em vez de retomar"
    assert r2.json()["id"] == doc_id, "criou uma linha nova em vez de retomar a que existia"

    _esperar_indexacao()
    assert db.exec1("SELECT status FROM documento WHERE id = %(d)s",
                    {"d": doc_id})["status"] == "pronto"

    # Agora que está pronto DE VERDADE, a duplicata volta a ser recusada.
    r3 = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                     files={"arquivo": ("aula-dup.txt", corpo, "text/plain")})
    assert r3.status_code == 400
    assert "já subiu" in r3.json()["detail"]

    # E nunca houve mais de UMA linha pra este arquivo.
    assert db.exec1("SELECT count(*) AS n FROM documento WHERE usuario_id = %(u)s",
                    {"u": usuario["id"]})["n"] == 1


def test_material_pre_024_recebe_o_arquivo_de_volta_sem_reindexar(client, usuario):
    """Material de ANTES da 024 está indexado, mas sem o PDF — e subir de novo
    ANEXA o original em vez de recusar como duplicata.

    O relato: oito aulas subidas antes de a 024 existir, quando o upload extraía
    o texto e descartava o arquivo. A busca achava tudo, mas a biblioteca não
    mostrava "abrir" nem "baixar" — os bytes não existiam. Reenviar batia em
    "você já subiu este arquivo", e a única saída era APAGAR o material e
    reindexar do zero: pagar 268 trechos de embedding de novo pra recuperar um
    PDF que a pessoa tinha na mão.

    O que este teste prende é a metade que não se vê: NÃO REINDEXAR. Os trechos
    têm que ser os MESMOS (ids inclusive), não trechos novos com o mesmo texto —
    é a diferença entre esta porta e a do retomado logo acima.
    """
    corpo = ("Nacionalidade originaria e naturalizacao. " * 90).encode()
    subir = lambda: client.post(
        "/materiais", headers=usuario["headers"], data={"tipo": "aula"},
        files={"arquivo": ("aula-sem-pdf.txt", corpo, "text/plain")})

    r1 = subir()
    assert r1.status_code == 201, r1.text
    doc_id = r1.json()["id"]
    _esperar_indexacao()
    antes = db.exec1("""SELECT count(*) AS n, max(id) AS ultimo FROM chunk
                         WHERE documento_id = %(d)s""", {"d": doc_id})
    assert antes["n"] > 0

    # O estado exato em que a migração 024 deixou todo material já existente.
    db.query("""UPDATE documento SET arquivo = NULL, arquivo_tipo = NULL,
                       arquivo_bytes = NULL WHERE id = %(d)s""", {"d": doc_id})
    assert client.get(f"/materiais/{doc_id}/arquivo",
                      headers=usuario["headers"]).status_code == 404
    lista = client.get("/materiais", headers=usuario["headers"]).json()["materiais"]
    assert [m for m in lista if m["id"] == doc_id][0]["tem_arquivo"] is False

    r2 = subir()
    assert r2.status_code == 201, r2.text
    assert r2.json()["arquivo_anexado"] is True, "recusou como duplicata em vez de anexar"
    assert r2.json()["id"] == doc_id, "criou uma linha nova em vez de completar a que existia"
    assert r2.json().get("retomado") is not True, "anexar arquivo não é retomar indexação"
    # A resposta já diz que o botão pode aparecer, sem esperar o recarregamento.
    assert r2.json()["tem_arquivo"] is True

    _esperar_indexacao()
    baixado = client.get(f"/materiais/{doc_id}/arquivo", headers=usuario["headers"])
    assert baixado.status_code == 200 and baixado.content == corpo

    depois = db.exec1("""SELECT count(*) AS n, max(id) AS ultimo FROM chunk
                          WHERE documento_id = %(d)s""", {"d": doc_id})
    assert (depois["n"], depois["ultimo"]) == (antes["n"], antes["ultimo"]), \
        "reindexou: os trechos são outros"
    assert db.exec1("SELECT status FROM documento WHERE id = %(d)s",
                    {"d": doc_id})["status"] == "pronto"
    assert db.exec1("SELECT count(*) AS n FROM documento WHERE usuario_id = %(u)s",
                    {"u": usuario["id"]})["n"] == 1

    # Com o arquivo no lugar, duplicata volta a ser duplicata.
    r3 = subir()
    assert r3.status_code == 400 and "já subiu" in r3.json()["detail"]


def test_html_por_arquivo_vira_texto_e_nao_tags(client, usuario):
    """Arrastar um .htm salvo do Planalto tem de indexar o TEXTO, não as tags.

    HTML por LINK já era tratado em `baixar` (pelo content-type); por ARQUIVO
    caía no `decode` genérico e indexava `<div class=...>` como se fosse
    conteúdo. Quem salva a página da CF e arrasta o arquivo é o caso mais
    provável deste projeto, e foi relatado como "nem me dá suporte pra
    alimentar com arquivos html".

    O cp1252 está no teste de propósito: é o que o Planalto serve, e decodificar
    como utf-8 com `errors="ignore"` come os acentos em silêncio — texto sem
    acento casa pior na busca lexical e fica ilegível na citação que o aluno lê.
    """
    corpo = ("<html><head><style>p{color:red}</style></head><body>"
             "<h1>Art. 37</h1><p>A administra\xe7\xe3o p\xfablica obedecer\xe1 aos "
             "princ\xedpios de legalidade, impessoalidade, moralidade, publicidade "
             "e efici\xeancia.</p></body></html>" * 6).encode("cp1252")

    texto = material._extrair("constituicao.htm", corpo)
    assert "<p>" not in texto and "style" not in texto, "indexou as tags"
    assert "administração pública" in texto, "acento perdido na decodificação"
    assert "Art. 37" in texto

    r = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                    files={"arquivo": ("constituicao.htm", corpo, "text/html")})
    assert r.status_code == 201, r.text


def test_cabecalhos_de_navegador_no_download_por_link():
    """O Planalto DERRUBA cliente que não parece navegador.

    Medido no mesmo minuto: sem `User-Agent` de navegador, `ReadTimeout`; com,
    HTTP 200 e 1,8 MB. O aluno via "Não deu pra indexar este link" numa URL
    perfeitamente válida — e a URL era a da Constituição, a fonte mais óbvia de
    lei seca deste projeto.

    Testa a CONSTANTE e não a rede: teste que depende do Planalto estar de pé
    falha por motivo alheio ao código, e este arquivo já sofreu com teste
    frágil hoje."""
    ua = material.CABECALHOS_URL.get("User-Agent", "")
    assert "Mozilla" in ua, "sem UA de navegador o Planalto derruba a conexão"


def _aula_que_transcreve_a_lei(n_artigos: int = 55) -> bytes:
    """Apostila DE VERDADE: transcreve o dispositivo e comenta embaixo.

    É a forma do material que quebrou — não é apostila que cita "art. 312" no
    meio da frase (essa a regra antiga já protegia), é a que abre linha com o
    artigo inteiro, como a lei faz, dezenas de vezes."""
    corpo = []
    for n in range(6, 6 + n_artigos):
        corpo.append(f"Art. {n}º São direitos sociais a educação, a saúde, o trabalho, "
                     f"a moradia, o transporte, o lazer e a segurança, na forma desta "
                     f"Constituição.")
        corpo.append(f"Pessoal, observe que o dispositivo acima é o coração da aula: a "
                     f"banca FGV já cobrou o inciso {n} duas vezes, e o professor "
                     f"costuma pedir a literalidade. Vamos analisar cada termo.")
    cabeca = ["Aula 04", "Prof. Herbert Almeida", "Índice",
              "Questões Comentadas - Direitos Sociais - FGV",
              "Lista de Questões - Direitos Sociais - FGV", "Gabarito"]
    return ("\n".join(cabeca + corpo)).encode()


def test_apostila_que_transcreve_a_lei_nao_e_lei_seca(client, usuario):
    """O contador de artigos sozinho classificou aula como lei — e o estrago não
    parou no chunk.

    Relatado com dois materiais reais (Direitos Sociais e Processo Legislativo):
    uma aula que transcreve os arts. 6º a 11 da CF bate 57 "Art." em começo de
    linha, passa dos 40 e é fatiada por artigo. Aí `e_referencia` vê chunk com
    artigo, chama de poço de consulta e a 027 SUPRIME o assunto — a tela cai no
    nome do arquivo, que era justamente o nome errado que o dono tinha digitado.
    Um limiar de contagem decidindo três comportamentos.

    O que separa não é quantidade de artigo, é a companhia: nenhuma das oito
    leis medidas cita banca, e nenhuma apostila medida fica sem citar."""
    r = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                    files={"arquivo": ("aula-04.txt", _aula_que_transcreve_a_lei(),
                                       "text/plain")})
    assert r.status_code == 201, r.text
    doc = r.json()["id"]

    chunks = db.exec1("SELECT count(*) AS t, count(artigo) AS a FROM chunk "
                      "WHERE documento_id = %(d)s", {"d": doc})
    assert chunks["t"] > 0 and chunks["a"] == 0, \
        "aula que transcreve a lei foi fatiada por artigo — perde a explicação do professor"
    # E o efeito que o aluno VÊ: não vira material de consulta, então o assunto
    # continua sendo pedido em vez de suprimido pela 027.
    assert not material.e_referencia("aula", [dict(r) for r in db.query(
        "SELECT artigo FROM chunk WHERE documento_id = %(d)s", {"d": doc})])


def test_edital_com_muitos_artigos_tambem_nao_e_lei_seca():
    """Caso vizinho, achado na mesma medição: o edital da PC-PR tem 72 "Art." em
    começo de linha (as regras do certame) e caía na mesma armadilha. Sem banco:
    a regra é pura."""
    edital = "\n".join(
        [f"Art. {n}. O candidato deverá observar o disposto neste edital." for n in range(1, 80)]
        + ["A banca examinadora FGV divulgará o gabarito preliminar.",
           "A FGV não se responsabiliza por inscrição não recebida.",
           "Recursos serão julgados pela FGV em até 10 dias."])
    assert not material._e_lei_seca(edital)
    # E a lei continua sendo lei: mesma contagem, sem a companhia de curso.
    assert material._e_lei_seca("\n".join(
        f"Art. {n}. Fica estabelecido o disposto neste artigo." for n in range(1, 80)))


def test_lei_seca_do_aluno_vira_chunk_por_artigo(client, usuario):
    """Subir a lei INTEIRA é dividido por artigo; apostila continua por janela.

    Relatado: o dono colou o link da Constituição e depois subiu o .htm dela, e
    as duas viraram ~2100 janelas genéricas com `artigo` NULO. Medido, o efeito
    era quádruplo — não achava por dispositivo, não gerava questão (o gerador
    exige `artigo IS NOT NULL`), a citação saía "constituicao, p. 14" em vez de
    "CF, art. 37", e os 2100 trechos COMPETIAM na busca com a CF do acervo, que
    já estava lá dividida por artigo.

    O outro lado é o que a decisão original protegia, e continua protegido:
    apostila cita "art. 312" no meio do parágrafo do professor, e virar chunk
    com `artigo='312'` faria `por_dispositivo` devolver o comentário em vez da
    lei. O que separa os dois casos é POSIÇÃO e VOLUME: lei publicada abre linha
    com "Art. N" (584 vezes na CF); apostila cita no meio da frase.
    """
    lei = "\n".join(
        f"Art. {n}. Fica estabelecido o disposto neste artigo para fins de teste "
        f"do chunker, com texto suficientemente longo para ser indexado." for n in range(1, 61))
    apostila = ("Nesta aula o professor comenta o art. 312 do CP e também o art. 313, "
                "explicando a diferença entre apropriação e desvio. " * 40)

    r = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                    files={"arquivo": ("lei-teste.txt", lei.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    doc_lei = r.json()["id"]

    r2 = client.post("/materiais", headers=usuario["headers"], data={"tipo": "aula"},
                     files={"arquivo": ("aula-teste.txt", apostila.encode(), "text/plain")})
    assert r2.status_code == 201, r2.text
    doc_aula = r2.json()["id"]

    com_artigo = db.exec1(
        "SELECT count(artigo) AS n FROM chunk WHERE documento_id = %(d)s", {"d": doc_lei})["n"]
    assert com_artigo > 0, "lei seca do aluno não foi dividida por artigo"

    sem_artigo = db.exec1(
        "SELECT count(*) AS t, count(artigo) AS a FROM chunk WHERE documento_id = %(d)s",
        {"d": doc_aula})
    assert sem_artigo["a"] == 0, \
        "apostila virou chunk por artigo — `por_dispositivo` passaria a devolver o comentário"

    # A NORMA fica nula mesmo na lei do aluno: nome de norma é do acervo
    # público, e inventar um aqui misturaria a cópia dele com a oficial.
    assert db.exec1("SELECT count(norma) AS n FROM chunk WHERE documento_id = %(d)s",
                    {"d": doc_lei})["n"] == 0


def test_dois_indexadores_no_mesmo_documento_nao_se_atropelam(client, usuario):
    """O DEFEITO QUE APAGOU A CONSTITUIÇÃO DE UM ALUNO.

    `uvicorn --reload` chama `retomar_pendentes()` a cada boot, e um comando de
    manutenção rodando o mesmo noutro processo pegou o MESMO documento no mesmo
    instante. Os dois apagaram os trechos, os dois começaram a inserir, e o
    segundo bateu em `duplicate key ... chunk_documento_id_ordem_key`. O
    documento terminou 'falha' com ZERO trechos.

    A idempotência do DELETE não protege disto — ela cobre duas passadas em
    SEQUÊNCIA. A fila com um trabalhador também não: ela é do PROCESSO, e dois
    processos têm duas filas que não conversam. A coordenação tem de estar no
    banco (`pg_try_advisory_lock`), e é isso que este teste exerce: duas
    threads chamando `indexar` no mesmo documento, ao mesmo tempo.
    """
    import threading

    doc = _material(client, usuario["headers"], nome="Concorrente.txt").json()
    _esperar_indexacao()
    linha = db.exec1("SELECT origem, arquivo FROM documento WHERE id = %(i)s",
                     {"i": doc["id"]})
    antes = db.exec1("SELECT count(*) n FROM chunk WHERE documento_id = %(i)s",
                     {"i": doc["id"]})["n"]
    assert antes > 0

    erros: list[Exception] = []

    def indexar_agora():
        try:
            material.indexar(doc["id"], linha["origem"], bytes(linha["arquivo"]))
        except Exception as e:      # noqa: BLE001 — o teste é sobre não haver
            erros.append(e)

    fios = [threading.Thread(target=indexar_agora) for _ in range(2)]
    for f in fios:
        f.start()
    for f in fios:
        f.join(timeout=240)

    assert erros == [], f"indexação concorrente estourou: {erros}"
    fim = db.exec1("SELECT status, erro FROM documento WHERE id = %(i)s", {"i": doc["id"]})
    assert fim["status"] == "pronto", fim["erro"]
    # O NÚMERO é o que prova: sem a trava dava zero (os dois apagaram) ou o
    # dobro (os dois inseriram).
    assert db.exec1("SELECT count(*) n FROM chunk WHERE documento_id = %(i)s",
                    {"i": doc["id"]})["n"] == antes


def test_listar_diz_qual_material_e_copia_de_lei(client, usuario):
    """A tela precisa poder AFIRMAR que não há cópia de lei na biblioteca.

    Relato: o aluno apagou a cópia da Constituição e ficou sem como conferir —
    "ficou ainda algum rastro do link da CF que ele mapeou como aula, porém eu
    não consigo saber, ele não me dá essa informação". Estava limpo; o defeito
    era a tela não saber dizer nem que estava nem que não, com 18 linhas em três
    abas pra varrer à mão.

    `fatiado_por_artigo` é o sinal certo, e não o tipo que a pessoa escolheu no
    seletor: a CF colada pelo link virou "aula" e continuava sendo lei dividida
    em 543 artigos. Aula de verdade é janela de parágrafo, sem artigo nenhum."""
    _material(client, usuario["headers"], nome="Aula.txt")
    _esperar_indexacao()

    ms = material.listar(usuario["id"])
    assert ms, "o material de teste não entrou"
    # Nenhuma aula é fatiada por artigo — é o caso normal, e é o que deixa a
    # tela dizer "nenhuma cópia de lei aqui" com base em dado, não em silêncio.
    assert all(m["fatiado_por_artigo"] is False for m in ms), \
        [m["titulo"] for m in ms if m["fatiado_por_artigo"]]
    assert all("fatiado_por_artigo" in m for m in ms), "campo ausente na listagem"


def test_material_de_link_guarda_o_endereco(client, usuario):
    """DE ONDE VEIO (028), e por que a coluna existe.

    `POST /materiais/link` chamava `material.baixar(url)`, que devolve um NOME
    derivado do endereço, e era esse nome que ia pra `origem`. A URL morria ali:
    do banco em diante, material vindo de link era indistinguível de arquivo
    arrastado com o mesmo nome — e "constituicao.txt" não diz que veio do
    Planalto. O relato foi literal: "ainda não mostra qual arquivo tá com o
    link".

    Sem rede: `baixar` é substituído. O que se afirma aqui é o ENCANAMENTO da
    URL até a listagem, não o download."""
    def falso_baixar(url):
        return "lei-falsa.txt", TXT

    import core.material as mod
    original = mod.baixar
    mod.baixar = falso_baixar
    try:
        r = client.post("/materiais/link", headers=usuario["headers"],
                        json={"url": "https://exemplo.gov.br/pasta/lei-falsa.htm"})
        assert r.status_code in (200, 201), r.text
        _esperar_indexacao()
    finally:
        mod.baixar = original

    achados = [m for m in material.listar(usuario["id"]) if m["url"]]
    assert len(achados) == 1, achados
    do_link = achados[0]
    assert do_link["url"] == "https://exemplo.gov.br/pasta/lei-falsa.htm"
    # TÍTULO SEM A EXTENSÃO, igual ao de arquivo arrastado. A rota passava
    # `titulo=nome`, o que pulava a tira-extensão do `registrar` e deixava
    # material de link titulado "constituicao.txt" ao lado de "aula-local".
    assert do_link["titulo"] == "lei-falsa"
    # `origem` continua sendo o NOME DE ARQUIVO, e isso não é redundância: é
    # ele que `indexar` passa pro `_extrair`, que escolhe o leitor pela
    # extensão. Guardar a URL ali quebraria a reextração, silenciosamente.
    assert do_link["origem"] == "lei-falsa.txt"

    # Arquivo enviado direto não tem URL — é a diferença que a tela mostra.
    # Conteúdo DIFERENTE do `TXT` de propósito: o duplê de download devolveu
    # `TXT`, e subir os mesmos bytes cairia na recusa por hash igual — o teste
    # falharia por duplicata, dizendo `KeyError: 'id'`, que não explica nada.
    outro = TXT + b"\n\nParagrafo que muda o hash deste arquivo."
    doc = client.post("/materiais", headers=usuario["headers"],
                      files={"arquivo": ("Arrastado.txt", outro, "text/plain")},
                      data={"tipo": "resumo"}).json()
    _esperar_indexacao()
    direto = [m for m in material.listar(usuario["id"]) if m["id"] == doc["id"]][0]
    assert direto["url"] is None
