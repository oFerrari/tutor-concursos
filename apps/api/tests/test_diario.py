"""Regressões do diário de teoria e do uso dele pelo tutor."""

from core import diario, socratic

VERSAO = "test-diario-v1"


def test_resumo_separa_materia_de_assunto(monkeypatch):
    monkeypatch.setattr(diario, "recentes", lambda *_args, **_kwargs: [
        {"dias_atras": 1, "assunto": "Peculato", "disciplina": "Direito Penal",
         "turnos": 5, "questoes_no_dia": 0},
        {"dias_atras": 2, "assunto": "Detração", "disciplina": "Direito Penal",
         "turnos": 1, "questoes_no_dia": 2},
        {"dias_atras": 2, "assunto": "Processo Legislativo",
         "disciplina": "Direito Constitucional", "turnos": 2,
         "questoes_no_dia": None},
    ])

    resumo = diario.resumo_para_prompt(1914)

    assert resumo.splitlines()[0] == (
        "Matérias com teoria conversada nesta janela: Direito Penal, "
        "Direito Constitucional")
    assert "ASSUNTO: Peculato; MATÉRIA: Direito Penal" in resumo
    assert "ASSUNTO: Processo Legislativo; MATÉRIA: Direito Constitucional" in resumo


def test_prompt_distingue_materia_de_assunto():
    texto = socratic.SISTEMA_TUTOR
    assert "ASSUNTO/TÓPICO é o conteúdo dentro dela" in texto
    assert "Nunca liste Peculato, Detração, Processo Legislativo" in texto


def test_prompt_planejamento_nao_reabre_conteudo_anterior():
    texto = socratic.SISTEMA_TUTOR
    assert "não retome nem teste o conteúdo que estava sendo tratado antes" in texto
    assert "não pergunte qual matéria quer começar" in texto


def test_prompt_localiza_subtopico_dentro_do_mesmo_item():
    assert "continuamos no 2.1; agora, papiloscopia" in socratic.SISTEMA_TUTOR


def test_prompt_acompanha_humor_em_vez_de_so_confirmar():
    texto = socratic.SISTEMA_TUTOR
    assert '"kkk", "rs"' in texto
    assert "não apenas \"é verdade\"" in texto
    assert "Mencionar manhã/tarde/noite não é cumprimentar" in texto


def test_humor_da_fala_vira_sinal_local_sem_contaminar_outros_turnos():
    for fala in ("nunca nem vi kkk", "rsrs esqueci da hora", "podia ter mais humor"):
        sinal = socratic._tom_da_fala(fala)
        assert sinal and "NESTA fala" in sinal
        assert "Não dê saudação" in sinal
    assert socratic._tom_da_fala("me explica desconcentração") is None
