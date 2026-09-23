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


def test_troca_curta_de_disciplina_retoma_a_iniciativa():
    assert assunto.e_eco(TROCA, HISTORICO, DISCIPLINAS) is False


def test_consulta_segue_a_disciplina_que_o_aluno_pediu():
    tema = (assunto.em_foco(HISTORICO, pergunta=TROCA,
                            disciplinas=DISCIPLINAS) or "").lower()
    assert tema == TROCA, f"consulta saiu: {tema!r}"


def test_processo_penal_casa_direito_processual_penal():
    assert assunto.disciplina_citada(TROCA, DISCIPLINAS) == "Direito Processual Penal"


def test_disciplina_como_resposta_nao_vira_consulta():
    historico = [
        {"autor": "aluno", "texto": "boa noite"},
        {"autor": "tutor", "texto": "Por onde você quer começar, "
                                    "Direito Constitucional ou Direito Penal?"},
    ]
    tema = assunto.em_foco(historico, pergunta="direito penal",
                           disciplinas=DISCIPLINAS)
    assert tema is None, f"nome de disciplina virou consulta: {tema!r}"
