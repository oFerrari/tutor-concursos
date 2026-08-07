/**
 * Cliente da API (apps/api) — um fetch tipado por rota, sem framework de
 * requisição por cima. Fica aqui (não em packages/sdk) porque só existe
 * um consumidor até agora; migra pra lá quando apps/mobile precisar do
 * mesmo cliente — não antes (ver README da raiz sobre packages/ vazio).
 *
 * Token guardado em localStorage: mais simples pra provar o fluxo (login
 * -> fila) e suficiente pra uso pessoal local. Não é a escolha certa se
 * isto for exposto na internet — SIMPLIFICAÇÃO CONHECIDA, não decisão
 * final (o candidato certo depois é cookie httpOnly + rota de servidor).
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHAVE_TOKEN = "tutor_token";

export class ErroApi extends Error {
  status: number;
  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(CHAVE_TOKEN);
}

export function setToken(token: string): void {
  window.localStorage.setItem(CHAVE_TOKEN, token);
}

export function limparToken(): void {
  window.localStorage.removeItem(CHAVE_TOKEN);
}

async function chamar<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const token = getToken();
  const resposta = await fetch(`${API_URL}${caminho}`, {
    ...opcoes,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opcoes.headers,
    },
  });

  if (!resposta.ok) {
    // /auth/* devolve {"detail": "..."}; o resto das rotas idem (HTTPException do FastAPI).
    const corpo = await resposta.json().catch(() => ({}));
    throw new ErroApi(resposta.status, corpo.detail ?? `erro ${resposta.status}`);
  }
  return resposta.json() as Promise<T>;
}

// ---------------------------------------------------------------------- auth
export type Usuario = { id: number; email: string };
export type RespostaAuth = { token: string; usuario: Usuario };

export function login(email: string, senha: string): Promise<RespostaAuth> {
  return chamar<RespostaAuth>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
}

export function registrar(email: string, senha: string): Promise<RespostaAuth> {
  return chamar<RespostaAuth>("/auth/registrar", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
}

// ----------------------------------------------------------------------- fila
export type Questao = {
  id: number;
  disciplina: string;
  tema: string;
  enunciado: string;
  gabarito: string;
  dicas: string[];
  caixa: number;
  prox_revisao: string;
};

export function getFila(): Promise<Questao[]> {
  return chamar<Questao[]>("/fila");
}

export type Carga = { revisoes: number; ineditas: number; teto: number; atraso: number };

export function getCarga(): Promise<Carga> {
  return chamar<Carga>("/carga");
}

export function getQuestao(id: number): Promise<Questao> {
  return chamar<Questao>(`/questoes/${id}`);
}

// ------------------------------------------------------------- diálogo/responder
// Mesmo par avaliar/registrar que chat._estudar_lista usa: avaliar() é um
// turno (não grava nada), registrar() fecha a questão de vez.
export type Turno = { resposta: string; comentario: string; pergunta: string };

export type Avaliacao = {
  veredito: "correta" | "parcial" | "incorreta";
  comentario: string;
  pergunta: string;
  conceito_faltante: string;
  revelar_gabarito: boolean;
};

export function avaliar(
  questaoId: number,
  resposta: string,
  nivel: number,
  historico: Turno[]
): Promise<Avaliacao> {
  return chamar<Avaliacao>(`/questoes/${questaoId}/avaliar`, {
    method: "POST",
    body: JSON.stringify({ resposta, nivel, historico }),
  });
}

// -------------------------------------------------------------------- stats
export type Desempenho = {
  disciplina: string;
  questoes: number;
  dominadas: number;
  tentativas: number;
  acertos: number;
  pct_acerto: number;
  cobertura_pct: number;
};

export function getStats(): Promise<Desempenho[]> {
  return chamar<Desempenho[]>("/stats");
}

// ---------------------------------------------------------- caderno de erros
export type ErroCaderno = {
  questao_id: number;
  disciplina: string;
  tema: string;
  vezes: number;
  ultima: string;
  enunciado: string;
};

export function getErros(): Promise<ErroCaderno[]> {
  return chamar<ErroCaderno[]>("/erros");
}

// ------------------------------------------------------------------ simulado
// Sem dica, sem caixa exibida — a questão do simulado é mais magra de
// propósito (core/simulado.py: "prova real não escolhe o que cai").
export type QuestaoSimulado = {
  id: number;
  disciplina: string;
  tema: string;
  enunciado: string;
  gabarito: string;
};

export function iniciarSimulado(
  n: number,
  minutos?: number,
  disciplina?: string
): Promise<{ simulado_id: number; questoes: QuestaoSimulado[] }> {
  return chamar("/simulados", {
    method: "POST",
    body: JSON.stringify({ n, minutos, disciplina }),
  });
}

/** Pula o sorteio — usa exatamente essas questões (bloco mini-simulado do desafio). */
export function iniciarSimuladoComIds(
  questaoIds: number[],
  minutos?: number
): Promise<{ simulado_id: number; questoes: QuestaoSimulado[] }> {
  return chamar("/simulados", {
    method: "POST",
    body: JSON.stringify({ questao_ids: questaoIds, minutos }),
  });
}

export type RespostaSimuladoItem = { questao_id: number; resposta: string; segundos: number };
export type ResultadoSimulado = { total: number; acertos: number; parciais: number; erros: number; nota_pct: number };
export type RelatorioDisciplina = { disciplina: string; questoes: number; acertos: number; pct: number };
export type ErroSimulado = { tema: string; enunciado: string; gabarito: string; resposta: string; veredito: string };

export function responderSimulado(
  simuladoId: number,
  respostas: RespostaSimuladoItem[],
  segundosTotal: number
): Promise<{ resultado: ResultadoSimulado; relatorio: RelatorioDisciplina[]; erros: ErroSimulado[] }> {
  return chamar(`/simulados/${simuladoId}/respostas`, {
    method: "POST",
    body: JSON.stringify({ respostas, segundos_total: segundosTotal }),
  });
}

export type HistoricoSimulado = {
  id: number;
  n_questoes: number;
  minutos_alvo: number | null;
  segundos_total: number | null;
  criado_em: string;
  acertos: number;
  respondidas: number;
  nota_pct: number | null;
};

export function getSimulados(): Promise<HistoricoSimulado[]> {
  return chamar<HistoricoSimulado[]>("/simulados");
}

// -------------------------------------------------------------------- desafio
export type PlanoDesafio = {
  reincidentes: Questao[];
  novas: Questao[];
  mini_simulado: QuestaoSimulado[];
  total_questoes: number;
  estimativa_minutos: number;
};

export function getDesafio(): Promise<PlanoDesafio> {
  return chamar<PlanoDesafio>("/desafio");
}

export type Registro = { caixa: number; prox_revisao: string };

export function registrarTentativa(
  questaoId: number,
  veredito: "correta" | "parcial" | "incorreta",
  resposta: string,
  dicasUsadas: number,
  segundos: number
): Promise<Registro> {
  return chamar<Registro>(`/questoes/${questaoId}/registrar`, {
    method: "POST",
    body: JSON.stringify({
      veredito,
      resposta,
      dicas_usadas: dicasUsadas,
      segundos,
    }),
  });
}
