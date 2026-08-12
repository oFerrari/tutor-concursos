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

/** Upload multipart — sem Content-Type manual (o browser define o boundary sozinho). */
async function chamarFormData<T>(caminho: string, form: FormData): Promise<T> {
  const token = getToken();
  const resposta = await fetch(`${API_URL}${caminho}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!resposta.ok) {
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
  // NULL quando a disciplina ainda não tem nenhuma tentativa (NULLIF na
  // view v_desempenho_disciplina, db/008_usuario.sql) — não é 0%, é "sem dado".
  pct_acerto: number | null;
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

// -------------------------------------------------------------- intervenção
export function getSugestao(): Promise<{ sugestao: string | null }> {
  return chamar("/sugestao");
}

// -------------------------------------------------------------- perguntar
export type Fonte = {
  id: number;
  titulo: string;
  norma?: string;
  artigo?: string;
  rubrica?: string;
};

export function perguntar(pergunta: string): Promise<{ resposta: string; fontes: Fonte[] }> {
  return chamar("/perguntar", {
    method: "POST",
    body: JSON.stringify({ pergunta }),
  });
}

// ------------------------------------------------------------ meta / edital
export type Probabilidade =
  | { erro: string }
  | {
      dias_restantes: number;
      topicos_totais: number;
      topicos_pendentes_estimado: number;
      ritmo_atual_topicos_dia: number;
      ritmo_necessario_topicos_dia: number | null;
      probabilidade_fechamento_pct: number;
    };

export type Meta = {
  dias_restantes: number | null;
  cobertura_pct: number;
  questoes_pendentes: number;
  questoes_respondidas: number;
  ritmo_necessario: number | null;
  pendentes_hoje: number;
  aviso?: string;
  edital?: string;
  probabilidade_fechamento?: Probabilidade;
};

// data no formato AAAA-MM-DD — sempre vence a do edital ingerido (mesma
// regra de `chat.py meta AAAA-MM-DD`).
export function getMeta(data?: string): Promise<Meta> {
  return chamar<Meta>(data ? `/meta?data=${data}` : "/meta");
}

export type CoberturaDisciplina = {
  disciplina: string;
  topicos_no_edital: number;
  questoes_disciplina: number;
  cobertura_pct: number;
  topicos_pendentes_estimado: number;
};

export type EditalAtual = { id: number; titulo: string; data_prova: string | null; cobertura: CoberturaDisciplina[] };

export function getEdital(): Promise<EditalAtual> {
  return chamar<EditalAtual>("/edital");
}

export type CandidatoData = { data: string; pontuacao: number; contexto: string };

export type ResultadoIngestaoEdital = {
  edital_id: number;
  data_prova: string | null;
  candidatos_data: CandidatoData[];
  topicos: number;
  disciplinas: string[];
};

export function ingerirEdital(
  arquivo: File,
  titulo?: string,
  orgao?: string,
  banca?: string
): Promise<ResultadoIngestaoEdital> {
  const form = new FormData();
  form.append("arquivo", arquivo);
  if (titulo) form.append("titulo", titulo);
  if (orgao) form.append("orgao", orgao);
  if (banca) form.append("banca", banca);
  return chamarFormData<ResultadoIngestaoEdital>("/edital", form);
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
