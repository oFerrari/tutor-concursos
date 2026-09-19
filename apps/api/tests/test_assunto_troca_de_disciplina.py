import pytest

from core import assunto

HISTORICO = [
    {"autor": "aluno", "texto": "competência no direito administrativo"},
    {"autor": "tutor", "texto":
        "No Direito Administrativo, competência é o poder atribuído por "
        "lei ao agente público para praticar o ato. Você sabe diferenciar "
        "competência vinculada de discricionária?"},
]
DISCIPLINAS = ["Direito Administrativo", "Direito Processual Penal",
               "Direito Constitucional"]
TROCA = "e no processo penal?"

# --- diagnóstico: documenta a CAUSA. Deve passar HOJE. ---


def test_causa_troca_curta_nao_conta_como_pedido():
    assert assunto.pede_assunto(TROCA) is False


def test_causa_turno_anterior_do_tutor_termina_em_pergunta():
    assert HISTORICO[-1]["autor"] == "tutor"
    assert "?" in HISTORICO[-1]["texto"]


# --- alvo: comportamento desejado. Deve FALHAR hoje. ---


@pytest.mark.xfail(strict=True, reason=
    "DEFEITO CONHECIDO, medido e não corrigido. Troca curta de "
    "disciplina sem verbo de pedido ('e no processo penal?') cai no "
    "caminho do ECO e a consulta vira a fala do tutor sobre a "
    "disciplina ANTERIOR. Corrigir exige mexer em pede_assunto, e_eco, "
    "_com_assunto e disciplina_citada ao mesmo tempo — tentado em "
    "2026-09-19 e revertido: o novo filtro de em_foco derruba "
    "test_citacao_sozinha_conta_como_assunto, e disciplina_citada não "
    "casa 'processo penal' contra 'Direito Processual Penal'. "
    "Ver docs/LIMITACOES.md.")
def test_troca_curta_de_disciplina_retoma_a_iniciativa():
    assert assunto.e_eco(TROCA, HISTORICO) is False


@pytest.mark.xfail(strict=True, reason=
    "DEFEITO CONHECIDO, medido e não corrigido. Troca curta de "
    "disciplina sem verbo de pedido ('e no processo penal?') cai no "
    "caminho do ECO e a consulta vira a fala do tutor sobre a "
    "disciplina ANTERIOR. Corrigir exige mexer em pede_assunto, e_eco, "
    "_com_assunto e disciplina_citada ao mesmo tempo — tentado em "
    "2026-09-19 e revertido: o novo filtro de em_foco derruba "
    "test_citacao_sozinha_conta_como_assunto, e disciplina_citada não "
    "casa 'processo penal' contra 'Direito Processual Penal'. "
    "Ver docs/LIMITACOES.md.")
def test_consulta_segue_a_disciplina_que_o_aluno_pediu():
    tema = (assunto.em_foco(HISTORICO, pergunta=TROCA,
                            disciplinas=DISCIPLINAS) or "").lower()
    assert "processo penal" in tema, f"consulta saiu: {tema!r}"


def test_disciplina_como_resposta_nao_vira_consulta():
    historico = [
        {"autor": "aluno", "texto": "boa noite"},
        {"autor": "tutor", "texto": "Por onde você quer começar, "
                                    "Direito Constitucional ou Direito Penal?"},
    ]
    tema = assunto.em_foco(historico, pergunta="direito penal",
                           disciplinas=DISCIPLINAS)
    assert tema is None, f"nome de disciplina virou consulta: {tema!r}"
