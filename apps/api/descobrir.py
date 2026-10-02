"""
BATERIA DE DESCOBERTA — acha o defeito que ninguém previu, antes do aluno achar.

POR QUE ESTE ARQUIVO EXISTE (28/09/2026)
----------------------------------------
Numa conversa real, o dono achou em dez minutos o que as baterias não acharam em
semanas: card de questão que ninguém pediu, material consultado numa pergunta
sobre o próprio tutor, conta sem conta, mapa mental quebrado. O diagnóstico, que
mora em `docs/DECISOES.md`, foi de DESENHO, não de azar:

  · o juiz tinha o defeito do código. `avaliar_chat.py` confere "veio card sem
    pedido?" com o próprio `pedido.treino` — quando a regra erra, o teste erra
    junto e aprova;
  · os roteiros eram de Direito, numa conta sem apostila: ninguém colava questão,
    pedia conta, mapa mental ou reclamava "cadê o cálculo";
  · ninguém olhava a TELA: a crase apagada e o `\\text` comido aconteciam depois
    do modelo, no caminho até o aluno;
  · bateria escrita depois do defeito confirma o conserto, não descobre o próximo.

O QUE ESTA FAZ DIFERENTE
------------------------
1. O ORÁCULO É INDEPENDENTE. Um juiz (modelo) lê a conversa COMO O ALUNO VIU — o
   texto já desenhado pela tela, os cartões de questão e a lista de consultado —
   sem conhecer regra nenhuma do tutor, e diz o que o aluno pediu e se recebeu.
   O código compara o juiz com o que o sistema FEZ. Nenhuma função do tutor é
   usada para julgar o tutor.
2. AS FALAS SÃO DE GENTE. As mensagens reais do aluno (as conversas da conta
   real, no banco local) são repetidas numa conta DESCARTÁVEL; e um aluno
   simulado persegue OBJETIVOS (colar questão, pedir conta, mapa mental, trocar
   de matéria, perguntar do tutor...), não matérias — vale para qualquer edital.
3. A TELA É CONFERIDA. Toda resposta passa pelo `TextoDoTutor` de verdade
   (`apps/web/scripts/texto-na-tela.cjs`); marcação que sobrar crua é defeito.
4. CONTRADIÇÃO É PROCURADA. Os blocos do prompt que podem vir juntos são lidos
   juntos, e cada decisão nova de `docs/DECISOES.md` é comparada com as antigas
   mais parecidas. A memória dos agentes não faz isso: `DECISOES.md` fica fora
   dela de propósito (`.ai-memory.toml`).

A CONTA É DA BATERIA. Nasce `bateria-…@local` com o material de
`cenarios/descoberta.json` e é apagada no fim; questão pública que a rodada gerar
é apagada também (a de 28/09 sobreviveu à conta e derrubou 8 testes). Das contas
reais só se LÊ a fala do aluno; nada é escrito nelas. Havendo mais de uma conta
real, `--conta-id` é obrigatório: fala de um aluno não vira teste sem se saber
de quem é.

    ./testar.sh --descobrir                  # o caminho normal
    python descobrir.py --so contradicoes    # só a leitura de contradições (barata)
    python descobrir.py --episodios 10 --turnos 8

Saída: `.logs/descoberta.md` só quando há defeito (a AUSÊNCIA é o sinal de
limpo, como `.logs/defeitos.md`) e `.logs/descoberta-conversas.md` sempre, para
LER. Sai com código 1 havendo defeito grave ou médio.

Custo: ~2 chamadas por turno real, ~3 por turno simulado, 1 de juiz por
conversa. A rodada inteira passa de 200 chamadas, e a cota gratuita é POR DIA e
por modelo (500 no do tutor, 20 no revisor forte — medido em 28/09/2026, quando
quatro rodadas seguidas deixaram o dono sem tutor). Por isso há ORÇAMENTO: 150
chamadas por rodada (`DESCOBERTA_ORCAMENTO`), e o que não couber fica marcado
INCOMPLETO. Cota do dia esgotada interrompe na hora; limite por minuto espera.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time
import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

import api
from bateria_conversa import montar_conta
from core import assunto, auth, db, llm, socratic

VERSAO = "descobrir-v2"

AQUI = Path(__file__).parent
RAIZ = AQUI.parents[1]
LOGS = RAIZ / ".logs"
RELATORIO = LOGS / "descoberta.md"
TRANSCRICAO = LOGS / "descoberta-conversas.md"
RENDERIZADOR = RAIZ / "apps" / "web" / "scripts" / "texto-na-tela.cjs"
CENARIO = AQUI / "cenarios" / "descoberta.json"

# O REVISOR (juiz e contradições) é mais forte que o tutor, de propósito: medido
# em 28/09/2026, o modelo do tutor leu a seção 9 do prompt ("nunca escreva a
# questão") junto do bloco de resolução ("escreva o enunciado com as
# alternativas") e respondeu "nenhum conflito". Julgar pede mais raciocínio que
# responder. Outro provedor, `LLM_REVISOR=…`; a reserva é a lista de sempre.
REVISOR = __import__("os").getenv("LLM_REVISOR", "gemini-3.5-flash")


def revisor() -> llm.LLM:
    """O modelo forte primeiro (20 chamadas/dia no gratuito, medido); depois as
    reservas — nunca o PRINCIPAL do tutor, cuja cota a própria rodada consome.
    Atenção a apelido: `flash-lite-latest` É o `3.5-flash-lite` (mesma cota)."""
    if llm.LLM_PROVIDER != "gemini":
        return llm.obter()
    return llm.Gemini(REVISOR, evitar=(llm.GEMINI_MODEL, "gemini-flash-lite-latest"))


# ORÇAMENTO. A cota gratuita é por DIA e por modelo (500 no do tutor, medido em
# 28/09/2026), e quatro rodadas no mesmo dia a gastaram inteira: o dono ficou sem
# tutor. A rodada para ao chegar aqui, contando TODA chamada (tutor, gerador,
# aluno simulado, juiz) pela telemetria (030).
ORCAMENTO = int(__import__("os").getenv("DESCOBERTA_ORCAMENTO", "150"))


def gasto_desde(inicio) -> int:
    return db.exec1("SELECT count(*) AS n FROM telemetria_llm WHERE criado_em >= %(t)s",
                    {"t": inicio})["n"]


# PACIÊNCIA COM A COTA. O plano gratuito limita por MINUTO: medido em 28/09/2026,
# a rodada parou no 429 e, dois minutos depois, o modelo respondia de novo.
# Esperar e repetir cabe na cota; desistir no primeiro 429 deixava a rodada pela
# metade toda vez.
ESPERA_S = 65
TENTATIVAS = 4


def paciente(chamar):
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return chamar()
        except llm.CotaDiaria:
            raise                    # esperar minutos não traz de volta a cota do dia
        except llm.ErroLLM:
            if tentativa == TENTATIVAS:
                raise
            print(f"    (modelo sem resposta; esperando {ESPERA_S}s, tentativa {tentativa + 1})")
            time.sleep(ESPERA_S)


# ══════════════════════════════════════════════════════════ as falas

def _conta_real(conta_id: int | None) -> int | None:
    if conta_id:
        return conta_id
    reais = db.query("""SELECT u.id FROM usuario u
                         WHERE u.email NOT LIKE '%%@local'
                           AND EXISTS (SELECT 1 FROM conversa c WHERE c.usuario_id = u.id)""")
    if len(reais) > 1:
        sys.exit(f"há {len(reais)} contas reais com conversa; diga de qual são as falas com "
                 "--conta-id (fala de aluno não vira teste sem se saber de quem é).")
    return reais[0]["id"] if reais else None


def conversas_reais(conta_id: int | None, limite: int | None, turnos: int) -> list[tuple[str, list[str]]]:
    """As falas do ALUNO de cada conversa real, na ordem. Comando (/erro,
    /feedback) fica de fora: é conversa com o app, não com o tutor."""
    uid = _conta_real(conta_id)
    if not uid:
        return []
    ids = db.query("""SELECT c.id FROM conversa c
                       WHERE c.usuario_id = %(u)s
                         AND EXISTS (SELECT 1 FROM mensagem m WHERE m.conversa_id = c.id AND m.autor = 'aluno')
                       ORDER BY c.id DESC""", {"u": uid})
    saida = []
    for n, c in enumerate(ids[:limite] if limite else ids, 1):
        falas = [m["texto"] for m in db.query(
            "SELECT texto FROM mensagem WHERE conversa_id = %(c)s AND autor = 'aluno' ORDER BY id",
            {"c": c["id"]}) if (m["texto"] or "").strip() and not m["texto"].lstrip().startswith("/")]
        if falas:
            saida.append((f"real {n} (conversa {c['id']})", falas[:turnos]))
    return saida


# Objetivos, não matérias: `{d}` é uma disciplina do edital sorteada, `{d_sem}` a
# que o edital cobra e a biblioteca não tem. Vale para qualquer concurso.
OBJETIVOS = [
    "saber o que o tutor consegue fazer por você e o que ainda falta nele; depois pedir para começar {d}",
    "colar uma questão de prova de {d} (invente uma realista, com enunciado e 4 ou 5 alternativas, "
    "como quem copia de um site de questões) e pedir ajuda; depois cobrar o raciocínio ou a conta",
    "pedir para o tutor resolver questões de um assunto de {d} que envolva cálculo, e cobrar a fórmula "
    "e a conta se não vierem",
    "pedir um mapa mental de um assunto de {d} e, depois, uma tabela de bizus do mesmo assunto",
    "pedir questões para treinar um assunto específico de {d}; responder uma delas no chat",
    "estudar {d} pela sua apostila, na ordem, dizendo 'continua' algumas vezes, e fazer uma dúvida no meio",
    "estudar {d_sem}: descobrir se o tutor tem material disso e o que ele consegue fazer mesmo assim",
    "começar em {d}, trocar para outra matéria do seu edital no meio e depois pedir para voltar de onde parou",
    "perguntar o que você já estudou, o que falta do edital e quais apostilas você tem",
    "chegar cansado e desanimado, desabafar um pouco, e só depois pedir algo leve de {d}",
    # Defeitos da conversa real de 01/10/2026:
    "estudar {d} e dizer 'vamos pros cálculos'; aceitar a questão que o tutor oferecer pedindo "
    "'sim, já com a resolução'; depois perguntar 'e da questão anterior?'",
    "quando o tutor perguntar por onde começar, responder só com a SIGLA da matéria (ex.: 'rlm'); depois "
    "pedir 'traga todo conceito', dizer 'certo..' e perguntar 'é só isso que tem no material?'",
    "pedir 'me explica' um assunto da sua apostila de {d}; depois fazer uma pergunta pontual curta "
    "('o que é ...?') e conferir se a resposta é curta e direta",
]

ALUNO_SISTEMA = """Você é um aluno brasileiro estudando para concurso público, conversando pelo \
chat com um tutor de IA. Escreva SÓ a sua próxima mensagem, como um aluno de verdade escreve no \
celular: curta (em geral uma linha), informal, às vezes sem acento ou com erro de digitação, sem \
saudação formal e sem se apresentar. Reaja ao que o tutor acabou de responder. Se ele não \
entregou o que você pediu, fugiu do assunto ou mostrou algo que você não pediu, reclame como um \
aluno reclamaria ("mas eu pedi...", "cadê..."). Quando o objetivo mandar colar uma questão, cole \
o enunciado inteiro com as alternativas. Nunca diga que é uma simulação."""


def fala_simulada(objetivo: str, contexto: str, historia: list[dict], n: int, total: int) -> str:
    conversa = "\n".join(
        f"{'Você' if t['autor'] == 'aluno' else 'Tutor'}: {t['texto']}" for t in historia) or "(vazia)"
    prompt = (f"{contexto}\nSeu objetivo nesta conversa: {objetivo}.\n\nConversa até aqui:\n"
              f"{conversa}\n\nSua mensagem número {n} de {total}:")
    fala = paciente(lambda: llm.obter().gerar(prompt, ALUNO_SISTEMA, max_tokens=600))
    return fala.strip().strip('"')[:1500]


# ══════════════════════════════════════════════════════════ a tela

def na_tela(textos: list[str]) -> list[str]:
    """O texto como o aluno o LÊ, pelo `TextoDoTutor` de verdade."""
    if not textos:
        return []
    try:
        r = subprocess.run(["node", str(RENDERIZADOR)], input=json.dumps(textos),
                           capture_output=True, text=True, timeout=60, check=True)
        return json.loads(r.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        return [f"[[não deu para desenhar: {e}]]"] * len(textos)


# Marcação que não pode sobrar depois de desenhada: comando LaTeX, cifrão de
# fórmula, cerca de código, negrito, título, separador de tabela, tabulação.
RE_MARCACAO_CRUA = re.compile(
    r"\\[A-Za-z]{2,}|\$\$|(?<![R\w])\$(?=[^\s\d])|```|\*\*|(?m:^\s*#{1,4}\s)|\|\s*:?-{3,}|\t"
    r"|\[\[ERRO AO DESENHAR|\[\[não deu para desenhar")


def rotulo_da_fonte(f: dict) -> str:
    return (f.get("assunto") or f.get("titulo") or f.get("norma") or "?") + \
        (f" (art. {f['artigo']})" if f.get("artigo") else "")


# ══════════════════════════════════════════════════════════ o juiz

JUIZ_SISTEMA = """Você avalia a conversa de um aluno de concurso com um tutor de IA, do ponto de \
vista do ALUNO. Você não conhece as regras internas do tutor e não deve adivinhá-las: julgue só se \
a conversa serviu a quem estava estudando.

Além do texto do tutor (já como aparece na tela), a tela mostra:
- CARTÕES DE QUESTÃO: exercícios para o aluno responder. Só deveriam aparecer quando o aluno pediu, \
NESTA fala, questões, exercícios ou treino para ELE responder — ou continuou um pedido desses \
("manda mais duas"). Pedir que o TUTOR resolva uma questão, colar uma questão ou pedir exemplo \
resolvido não é pedir cartão.
- CONSULTADO: a lista de trechos do material que o tutor consultou. Faz sentido quando a fala é de \
conteúdo de estudo. Em pergunta sobre o próprio tutor, sobre quais materiais o aluno tem, sobre o \
desempenho dele, em cumprimento ou desabafo, lista de material é defeito — e material de outro \
assunto que o da fala também é.

Para cada turno do tutor, diga: o que o aluno pediu; se a resposta entregou isso; se deviam \
aparecer cartões; se fazia sentido consultar material; e os defeitos que um aluno exigente \
apontaria: não responder o que foi perguntado, trocar de assunto, inventar informação, prometer o \
que a tela não mostra, formato pedido que não veio (tabela, mapa, fórmula, conta), conta errada, \
repetir o turno anterior, texto quebrado ou com marcação crua, tom de robô. Defeito é o que \
atrapalha o estudo, não gosto pessoal de estilo. Sem defeito, lista vazia. \
Gravidade: "grave" = o aluno sai errado ou sem o que pediu; "medio" = atrapalha, mas ele consegue; \
"leve" = incômodo."""

ESQUEMA_JUIZ = {
    "type": "OBJECT",
    "properties": {"turnos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {
            "turno": {"type": "INTEGER"},
            "pedido": {"type": "STRING"},
            "atendeu": {"type": "BOOLEAN"},
            "cartoes_devidos": {"type": "BOOLEAN"},
            "consultado_devido": {"type": "BOOLEAN"},
            "defeitos": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {"gravidade": {"type": "STRING", "enum": ["grave", "medio", "leve"]},
                               "descricao": {"type": "STRING"}},
                "required": ["gravidade", "descricao"]}},
        },
        "required": ["turno", "pedido", "atendeu", "cartoes_devidos", "consultado_devido", "defeitos"],
    }}},
    "required": ["turnos"],
}


def _turno_para_juiz(n: int, t: dict) -> str:
    cartoes = (f"{len(t['cartoes'])} ({'; '.join(t['cartoes'])})" if t["cartoes"] else "nenhum")
    consultado = "; ".join(t["consultado"]) if t["consultado"] else "nenhum"
    return (f"[Turno {n}]\nALUNO: {t['fala']}\nTUTOR (na tela): {t['tela']}\n"
            f"TELA: cartões de questão: {cartoes} | consultado: {consultado}")


JUIZES: list[str] = []   # que modelo julgou cada conversa, na ordem — vai ao relatório


def julgar(turnos: list[dict]) -> list[dict]:
    prompt = "\n\n".join(_turno_para_juiz(n, t) for n, t in enumerate(turnos, 1))
    juiz = revisor()
    try:
        r = paciente(lambda: juiz.gerar_json(prompt, JUIZ_SISTEMA, max_tokens=16000,
                                             schema=ESQUEMA_JUIZ, temperatura=0.0))
    except llm.ErroLLM as e:
        JUIZES.append("nenhum")
        return [{"turno": 0, "erro": str(e)}]
    JUIZES.append(getattr(juiz, "ultimo_modelo", None) or "?")
    return r.get("turnos", []) if isinstance(r, dict) else []


def divergencias(turnos: list[dict], veredito: list[dict]) -> list[dict]:
    """O que o JUIZ disse que devia acontecer contra o que o SISTEMA fez, mais os
    defeitos que ele apontou e os da tela. Cada item: turno, gravidade, origem, texto."""
    achados = []
    por_turno = {v.get("turno"): v for v in veredito}
    if 0 in por_turno:
        achados.append({"turno": 0, "gravidade": "medio", "origem": "juiz",
                        "texto": f"o juiz não respondeu: {por_turno[0].get('erro')}"})
    for n, t in enumerate(turnos, 1):
        if t.get("erro"):
            achados.append({"turno": n, "gravidade": "grave", "origem": "rota", "texto": t["erro"]})
            continue
        crua = RE_MARCACAO_CRUA.findall(t["tela"])
        if crua:
            achados.append({"turno": n, "gravidade": "medio", "origem": "tela",
                            "texto": f"marcação crua na tela: {sorted(set(crua))[:6]}"})
        v = por_turno.get(n)
        if not v:
            continue
        if v["cartoes_devidos"] and not t["cartoes"]:
            achados.append({"turno": n, "gravidade": "grave", "origem": "cartões",
                            "texto": f"o aluno pediu questões e nenhum cartão veio ({v['pedido']})"})
        if t["cartoes"] and not v["cartoes_devidos"]:
            achados.append({"turno": n, "gravidade": "grave", "origem": "cartões",
                            "texto": f"cartão sem pedido: {t['cartoes']} ({v['pedido']})"})
        if t["consultado"] and not v["consultado_devido"]:
            achados.append({"turno": n, "gravidade": "medio", "origem": "consultado",
                            "texto": f"material consultado sem motivo: {t['consultado'][:4]}"})
        if not v["atendeu"]:
            achados.append({"turno": n, "gravidade": "grave", "origem": "juiz",
                            "texto": f"não entregou o pedido: {v['pedido']}"})
        for d in v.get("defeitos") or []:
            achados.append({"turno": n, "gravidade": d.get("gravidade", "medio"), "origem": "juiz",
                            "texto": d.get("descricao", "")})
    return achados


# ══════════════════════════════════════════════════════════ a conversa

class Interrompida(Exception):
    """O MODELO parou de responder (cota, 5xx). Não é defeito do tutor, e seguir
    só gasta o resto da cota em turnos que voltam 503 — medido na primeira
    rodada, 28/09/2026: 42 "defeitos", dos quais 22 eram HTTP 503 de cota."""

def conversar(cli: TestClient, cab: dict, falas: list[str] | None, objetivo: str | None,
              contexto: str, n_turnos: int, questoes_publicas: set[int]) -> list[dict]:
    """Uma conversa pela ROTA do chat. `falas` = repetição real; `objetivo` =
    aluno simulado, que vê os cartões como o aluno veria."""
    turnos, historia, cid = [], [], None
    total = len(falas) if falas else n_turnos
    for n in range(1, total + 1):
        try:
            fala = falas[n - 1] if falas else fala_simulada(objetivo, contexto, historia, n, total)
        except llm.ErroLLM as e:
            raise Interrompida(f"aluno simulado sem modelo no turno {n}: {e}", turnos) from e
        t0 = time.time()
        for tentativa in range(1, TENTATIVAS + 1):
            r = cli.post("/perguntar", headers=cab,
                         json={"pergunta": fala, **({"conversa_id": cid} if cid else {})})
            if r.status_code != 503 or tentativa == TENTATIVAS:
                break
            try:                    # cota do DIA? então esperar não adianta
                llm.obter().gerar("responda só: ok", max_tokens=5)
            except llm.CotaDiaria as e:
                _desenhar(turnos)
                raise Interrompida(f"cota diária do tutor esgotada no turno {n}: {e}", turnos) from e
            except llm.ErroLLM:
                pass
            # A fala ficou gravada sem resposta: desfaz, espera a cota, repete.
            if cid:
                cli.post(f"/conversas/{cid}/desfazer", headers=cab)
            print(f"    (tutor sem modelo; esperando {ESPERA_S}s, tentativa {tentativa + 1})")
            time.sleep(ESPERA_S)
        if r.status_code == 503:
            _desenhar(turnos)
            raise Interrompida(f"tutor sem modelo no turno {n} (HTTP 503, {TENTATIVAS} tentativas)", turnos)
        if r.status_code != 200:
            turnos.append({"fala": fala, "texto": "", "tela": "", "cartoes": [], "consultado": [],
                           "erro": f"HTTP {r.status_code}: {r.text[:200]}", "s": time.time() - t0})
            print(f"    ✗ {n}: HTTP {r.status_code}")
            continue
        r = r.json()
        cid = r["conversa_id"]
        questoes = r.get("questoes") or []
        questoes_publicas.update(q["id"] for q in questoes if q.get("id"))
        turnos.append({"fala": fala, "texto": r["resposta"], "cartoes": [q.get("tema") or "?" for q in questoes],
                       "consultado": sorted({rotulo_da_fonte(f) for f in r.get("fontes") or []}),
                       "s": time.time() - t0})
        historia += [{"autor": "aluno", "texto": fala}, {"autor": "tutor", "texto": r["resposta"] + (
            f"\n[na tela apareceram {len(questoes)} cartões de questão para você responder: "
            f"{', '.join(q.get('tema') or '?' for q in questoes)}]" if questoes else "")}]
        print(f"    {n}: {time.time() - t0:4.1f}s · {len(questoes)} cartão(ões) · "
              f"{len(r.get('fontes') or [])} fonte(s) · {fala[:60]!r}")
    _desenhar(turnos)
    return turnos


def _desenhar(turnos: list[dict]) -> None:
    for t, tela in zip(turnos, na_tela([t["texto"] for t in turnos])):
        t["tela"] = t.get("tela") or tela


# ══════════════════════════════════════════════════════════ contradições

PROMPT_CONTRADICAO = """Você revisa as instruções de um assistente. O BLOCO BASE vai em toda \
chamada; o BLOCO EXTRA é acrescentado ao fim dele em alguns turnos, e aí os dois valem juntos.

Percorra o BLOCO EXTRA instrução por instrução. Para cada uma, procure no BLOCO BASE alguma regra \
que ela obrigue a violar (proibição que o extra manda fazer, obrigação que o extra manda não \
fazer, limite de tamanho ou formato que o extra excede). Liste cada choque, citando os dois \
trechos literalmente.

Só NÃO é choque quando o próprio texto resolve, por escrito, apontando a regra: "exceto...", \
"aqui não vale X", "isto vence X". Um "isto vence" genérico só cobre as regras que ele nomeia. \
Sem choque, lista vazia."""

PROMPT_DECISAO = """Você revisa o registro de decisões de um projeto. Compare a decisão NOVA com as \
ANTIGAS. Liste só contradição real: a nova manda fazer o que uma antiga, com medição, mandou não \
fazer (ou o contrário), SEM dizer que a substitui nem por quê. Evolução declarada não é \
contradição. Sem conflito, lista vazia."""

ESQUEMA_CONFLITOS = {
    "type": "OBJECT",
    "properties": {"conflitos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"a": {"type": "STRING"}, "b": {"type": "STRING"}, "quando": {"type": "STRING"}},
        "required": ["a", "b", "quando"]}}},
    "required": ["conflitos"],
}


PROMPT_VERIFICA = """Você confere uma SUSPEITA de contradição entre instruções. Leia o texto \
inteiro e responda se o próprio texto já RESOLVE o choque por escrito — uma exceção, um "aqui não \
vale", um "isto vence" que alcance a regra em questão — ou se o assistente, com as duas instruções \
presentes, fica mesmo sem ter como cumprir ambas. Na dúvida, resolvido = false."""

ESQUEMA_VERIFICA = {
    "type": "OBJECT",
    "properties": {"resolvido": {"type": "BOOLEAN"}, "frase_que_resolve": {"type": "STRING"}},
    "required": ["resolvido"],
}

# DUAS LEITURAS E UMA CONFERÊNCIA. Medido em 28/09/2026 com o mesmo texto e
# temperatura 0: uma rodada achou o choque, a seguinte não; e a mesma rodada
# apontou como choque uma exceção que o bloco declarava por escrito. A união de
# duas leituras cobre o que uma perde; a conferência corta o que já tem exceção.
LEITURAS = 2


def _suspeitas(texto: str, sistema: str) -> list[dict]:
    vistas, saida = set(), []
    for _ in range(LEITURAS):
        r = paciente(lambda: revisor().gerar_json(texto, sistema, max_tokens=12000,
                                                  schema=ESQUEMA_CONFLITOS, temperatura=0.0))
        for c in (r or {}).get("conflitos", []):
            chave = (re.sub(r"\W+", "", c["a"].lower())[:50], re.sub(r"\W+", "", c["b"].lower())[:50])
            if chave not in vistas and chave[::-1] not in vistas:
                vistas.add(chave)
                saida.append(c)
    return saida


def _confirmadas(texto: str, suspeitas: list[dict]) -> list[dict]:
    fica = []
    for c in suspeitas:
        prompt = (f"{texto}\n\n=== SUSPEITA ===\nA: {c['a']}\nB: {c['b']}\nQuando: {c['quando']}")
        v = paciente(lambda: revisor().gerar_json(prompt, PROMPT_VERIFICA, max_tokens=6000,
                                                  schema=ESQUEMA_VERIFICA, temperatura=0.0))
        if not (v or {}).get("resolvido"):
            fica.append(c)
    return fica


def _secoes(texto: str) -> list[tuple[str, str]]:
    partes = re.split(r"(?m)^(?=## )", texto)
    return [(p.splitlines()[0][3:].strip(), p) for p in partes if p.startswith("## ")]


def _palavras(texto: str) -> set[str]:
    return {assunto._sem_acento(p) for p in re.findall(r"[A-Za-zÀ-ú_]{6,}", texto.lower())}


def contradicoes(desde: str) -> list[dict]:
    achados = []
    # Cada bloco condicional contra o base, um por vez: lidos todos juntos, o
    # modelo não achou nem a contradição que motivou isto (seção 9 × resolução).
    for extra in ("SISTEMA_LEITURA", "SISTEMA_RESOLUCAO", "SISTEMA_FORMATO"):
        if not hasattr(socratic, extra):
            continue
        texto = (f"=== BLOCO BASE ===\n{socratic.SISTEMA_TUTOR}\n\n"
                 f"=== BLOCO EXTRA ({extra}) ===\n{getattr(socratic, extra)}")
        try:
            for c in _confirmadas(texto, _suspeitas(texto, PROMPT_CONTRADICAO)):
                achados.append({"onde": f"prompt: base × {extra}", **c})
        except llm.ErroLLM as e:
            achados.append({"onde": f"prompt: base × {extra}", "a": "", "b": "", "quando": f"não verificado: {e}"})

    arquivo = RAIZ / "docs" / "DECISOES.md"
    diff = subprocess.run(["git", "-C", str(RAIZ), "diff", desde, "--unified=0", "--", str(arquivo)],
                          capture_output=True, text=True).stdout
    novos_titulos = {l[4:].strip() for l in diff.splitlines() if l.startswith("+## ")}
    secoes = _secoes(arquivo.read_text(encoding="utf-8"))
    antigas = [(t, s) for t, s in secoes if t not in novos_titulos]
    for titulo, secao in ((t, s) for t, s in secoes if t in novos_titulos):
        chave = _palavras(secao)
        parecidas = sorted(antigas, key=lambda ts: -len(chave & _palavras(ts[1])))[:4]
        prompt = (f"=== DECISÃO NOVA: {titulo} ===\n{secao[:6000]}\n\n" +
                  "\n\n".join(f"=== ANTIGA: {t} ===\n{s[:5000]}" for t, s in parecidas))
        try:
            for c in _confirmadas(prompt, _suspeitas(prompt, PROMPT_DECISAO)):
                achados.append({"onde": f"DECISOES: {titulo}", **c})
        except llm.ErroLLM as e:
            achados.append({"onde": f"DECISOES: {titulo}", "a": "", "b": "", "quando": f"não verificado: {e}"})
    return achados


# ══════════════════════════════════════════════════════════ relatório

def _gravar(conversas: list[tuple[str, list[dict], list[dict]]], conflitos: list[dict],
            incompleta: str | None = None) -> int:
    LOGS.mkdir(exist_ok=True)
    linhas = [f"# Descoberta — {time.strftime('%d/%m/%Y %H:%M')} · {VERSAO}\n"]
    if incompleta:
        linhas.append(f"> **RODADA INCOMPLETA** — {incompleta}. Rode de novo quando o modelo voltar.\n")
    for i, (nome, turnos, achados) in enumerate(conversas):
        juiz = JUIZES[i] if i < len(JUIZES) else "?"
        linhas.append(f"\n## {nome}\n\n_juiz: {juiz}_\n")
        por_turno: dict[int, list[dict]] = {}
        for a in achados:
            por_turno.setdefault(a["turno"], []).append(a)
        for n, t in enumerate(turnos, 1):
            linhas.append(f"**{n}. Aluno:** {t['fala']}\n")
            linhas.append(f"**Tutor** ({t.get('s', 0):.1f}s):\n\n{t['texto'] or t.get('erro')}\n")
            if t["cartoes"] or t["consultado"]:
                linhas.append(f"_cartões: {t['cartoes'] or '—'} · consultado: {t['consultado'] or '—'}_\n")
            for a in por_turno.get(n, []):
                linhas.append(f"> ⚠ **{a['gravidade']}** [{a['origem']}] {a['texto']}\n")
    TRANSCRICAO.write_text("\n".join(linhas), encoding="utf-8")

    contam = [(nome, a) for nome, _, ach in conversas for a in ach if a["gravidade"] in ("grave", "medio")]
    leves = [(nome, a) for nome, _, ach in conversas for a in ach if a["gravidade"] == "leve"]
    if not contam and not conflitos and not leves and not incompleta:
        RELATORIO.unlink(missing_ok=True)
        return 0
    rel = [f"# Defeitos achados pela descoberta — {time.strftime('%d/%m/%Y %H:%M')}\n",
           *([f"**RODADA INCOMPLETA** — {incompleta}. Ausência de defeito abaixo NÃO é sinal de limpo.\n"]
             if incompleta else []),
           f"Juízes: {', '.join(sorted(set(JUIZES))) or '—'} (o preferido é {REVISOR}; reserva leve erra mais).\n",
           f"{len(contam)} grave/médio · {len(leves)} leve · {len(conflitos)} contradição(ões). "
           f"A conversa inteira de cada um está em `.logs/{TRANSCRICAO.name}`.\n"]
    if contam:
        rel.append("\n## Grave e médio\n")
        rel += [f"- **{a['gravidade']}** · {nome}, turno {a['turno']} · [{a['origem']}] {a['texto']}"
                for nome, a in sorted(contam, key=lambda x: x[1]["gravidade"] != "grave")]
    if conflitos:
        rel.append("\n## Contradições\n")
        rel += [f"- **{c['onde']}** — \"{c['a']}\" × \"{c['b']}\" — {c['quando']}" for c in conflitos]
    if leves:
        rel.append("\n## Leve\n")
        rel += [f"- {nome}, turno {a['turno']} · [{a['origem']}] {a['texto']}" for nome, a in leves]
    RELATORIO.write_text("\n".join(rel) + "\n", encoding="utf-8")
    return len(contam) + len(conflitos)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--so", choices=["reais", "simulados", "contradicoes"])
    ap.add_argument("--conta-id", type=int, help="de qual conta real vêm as falas (se houver mais de uma)")
    ap.add_argument("--conversas", type=int, help="quantas conversas reais (padrão: todas)")
    ap.add_argument("--episodios", type=int, default=5, help="conversas do aluno simulado (padrão 5)")
    ap.add_argument("--turnos", type=int, default=6, help="turnos por conversa simulada (padrão 6); "
                                                          "a real vai até 2x isso")
    ap.add_argument("--semente", type=int, default=int(date.today().strftime("%Y%m%d")),
                    help="sorteio de objetivos e disciplinas (padrão: a data, muda todo dia)")
    ap.add_argument("--desde", default="HEAD", help="decisões novas desde esta referência do git")
    args = ap.parse_args()

    # A TELA ANTES DA COTA. Sem o renderizador (node fora do PATH, script quebrado),
    # `na_tela` devolve "[[não deu para desenhar…]]" para todo turno, o juiz julga a
    # mensagem de erro e a rodada inteira vira defeito falso — em 29/09/2026, 188 de
    # 195, com 152 chamadas gastas. Uma resposta de prova, desenhada ANTES de montar
    # conta e de chamar modelo, separa "tutor ruim" de "bateria cega".
    if args.so != "contradicoes":
        prova = na_tela(["ok"])[0]
        if RE_MARCACAO_CRUA.search(prova) or prova.strip() != "ok":
            print(f"✗ a tela não desenha: {prova[:300]}\n  nada rodou, nenhuma chamada gasta.",
                  file=sys.stderr)
            return 2

    inicio = db.exec1("SELECT now() AS t")["t"]
    conflitos = [] if args.so in ("reais", "simulados") else contradicoes(args.desde)
    print(f"contradições: {len(conflitos)}")
    conversas: list[tuple[str, list[dict], list[dict]]] = []
    incompleta: str | None = None
    if args.so != "contradicoes":
        dados = json.loads(CENARIO.read_text(encoding="utf-8"))["conta"]
        com_material = {m["disciplina"] for m in dados["materiais"] if m.get("disciplina")}
        disciplinas = list(dados["edital"])
        sem_material = [d for d in disciplinas if d not in com_material] or disciplinas
        contexto = ("Seu concurso tem estas disciplinas no edital: " + ", ".join(disciplinas) +
                    ". Você subiu apostilas de: " + ", ".join(sorted(com_material)) + ".")
        roteiro = []
        if args.so != "simulados":
            roteiro += [(nome, falas, None) for nome, falas in
                        conversas_reais(args.conta_id, args.conversas, args.turnos * 2)]
        if args.so != "reais":
            sorteio = random.Random(args.semente)
            objetivos = sorteio.sample(OBJETIVOS, k=min(args.episodios, len(OBJETIVOS)))
            for i, obj in enumerate(objetivos, 1):
                obj = obj.format(d=sorteio.choice(sorted(com_material)), d_sem=sorteio.choice(sem_material))
                roteiro.append((f"simulado {i}: {obj}", None, obj))
        uid = auth.usuario_da_cli(f"bateria-{uuid.uuid4().hex[:12]}@local")
        publicas: set[int] = set()
        try:
            print("montando a conta descartável…")
            mid = montar_conta(uid, dados)
            cli = TestClient(api.app)
            cab = {"Authorization": f"Bearer {auth.emitir_token(uid)}", "X-Mesa-Id": str(mid)}
            for nome, falas, obj in roteiro:
                gasto = gasto_desde(inicio)
                if gasto >= ORCAMENTO:
                    incompleta = (f"orçamento de {ORCAMENTO} chamadas atingido ({gasto}) antes de "
                                  f"\"{nome}\"; {len(roteiro) - len(conversas)} conversa(s) não rodaram "
                                  f"(DESCOBERTA_ORCAMENTO=… para mudar)")
                    print(f"   ✗ {incompleta}")
                    break
                print(f"\n== {nome}  (gasto até aqui: {gasto}/{ORCAMENTO})")
                try:
                    turnos = conversar(cli, cab, falas, obj, contexto, args.turnos, publicas)
                except Interrompida as e:
                    motivo, turnos = e.args
                    incompleta = f"{nome}: {motivo}; {len(roteiro) - len(conversas) - 1} conversa(s) não rodaram"
                    print(f"   ✗ RODADA INTERROMPIDA — {motivo}")
                    if turnos:
                        conversas.append((nome, turnos, divergencias(turnos, julgar(turnos))))
                    break
                achados = divergencias(turnos, julgar(turnos))
                print(f"   → {sum(a['gravidade'] != 'leve' for a in achados)} defeito(s) grave/médio")
                conversas.append((nome, turnos, achados))
        finally:
            if publicas:
                db.query("DELETE FROM questao WHERE id = ANY(%(i)s) AND usuario_id IS NULL",
                         {"i": list(publicas)})
            db.query("DELETE FROM usuario WHERE id = %(u)s", {"u": uid})
    n = _gravar(conversas, conflitos, incompleta)
    print(f"chamadas ao modelo nesta rodada: {gasto_desde(inicio)}")
    print(f"\n{'DEFEITOS: ' + str(n) + ' → .logs/' + RELATORIO.name if n else 'nenhum defeito grave/médio'}"
          f" · conversas em .logs/{TRANSCRICAO.name}")
    return 1 if n or incompleta else 0


if __name__ == "__main__":
    sys.exit(main())
