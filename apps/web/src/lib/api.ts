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
 *
 * MESA ATIVA (migração 010): a API decide o recorte pelo header
 * `X-Mesa-Id`, por requisição — não há mesa ativa guardada no servidor.
 * Aqui ela vive em localStorage e é injetada em `chamar`/`chamarFormData`,
 * num lugar só: se cada tela lembrasse de mandar o header, a primeira que
 * esquecesse leria outra mesa sem ninguém perceber.
 *
 * Sem mesa escolhida, o header não vai e a API cai na mesa padrão da conta
 * — o cliente NÃO reimplementa essa regra de fallback (é o que `GET /mesa`
 * existe pra responder).
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHAVE_TOKEN = "tutor_token";
const CHAVE_MESA = "tutor_mesa";

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
  // Sair da conta limpa a mesa junto: a mesa é de um usuário, e deixar o id
  // pendurado faria o próximo login mandar o header de uma mesa que não é
  // dele — o que a API responderia com 404 em toda tela.
  window.localStorage.removeItem(CHAVE_MESA);
}

export function getMesaAtiva(): number | null {
  if (typeof window === "undefined") return null;
  const bruto = window.localStorage.getItem(CHAVE_MESA);
  const n = bruto ? Number(bruto) : NaN;
  return Number.isInteger(n) ? n : null;
}

export function setMesaAtiva(id: number): void {
  window.localStorage.setItem(CHAVE_MESA, String(id));
}

export function limparMesaAtiva(): void {
  window.localStorage.removeItem(CHAVE_MESA);
}

function cabecalhoMesa(): Record<string, string> {
  const id = getMesaAtiva();
  return id === null ? {} : { "X-Mesa-Id": String(id) };
}

/**
 * 404 "mesa não encontrada" significa que o id guardado aqui não existe
 * mais (apagada noutra aba, ou banco recriado). Esquecer a escolha faz a
 * próxima chamada cair na mesa padrão em vez de repetir o mesmo 404 pra
 * sempre — mas o erro SOBE assim mesmo: quem chamou precisa saber que esta
 * resposta não veio, e a tela de mesas é quem mostra a lista de verdade.
 */
function tratarMesaSumida(status: number, detalhe: string): void {
  if (status === 404 && detalhe === "mesa não encontrada" && getMesaAtiva() !== null) {
    limparMesaAtiva();
  }
}

async function chamar<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const token = getToken();
  const resposta = await fetch(`${API_URL}${caminho}`, {
    ...opcoes,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...cabecalhoMesa(),
      ...opcoes.headers,
    },
  });

  if (!resposta.ok) {
    // /auth/* devolve {"detail": "..."}; o resto das rotas idem (HTTPException do FastAPI).
    const corpo = await resposta.json().catch(() => ({}));
    const detalhe = corpo.detail ?? `erro ${resposta.status}`;
    tratarMesaSumida(resposta.status, detalhe);
    throw new ErroApi(resposta.status, detalhe);
  }
  return resposta.json() as Promise<T>;
}

/** Upload multipart — sem Content-Type manual (o browser define o boundary sozinho). */
async function chamarFormData<T>(caminho: string, form: FormData): Promise<T> {
  const token = getToken();
  const resposta = await fetch(`${API_URL}${caminho}`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...cabecalhoMesa(),
    },
    body: form,
  });
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => ({}));
    const detalhe = corpo.detail ?? `erro ${resposta.status}`;
    tratarMesaSumida(resposta.status, detalhe);
    throw new ErroApi(resposta.status, detalhe);
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

/** Conta autenticada (id + email). Hoje só o e-mail existe — a saudação da
 *  home deriva o primeiro nome dele. Se um dia a tabela `usuario` ganhar
 *  coluna `nome`, o campo aparece aqui e a derivação some. */
export function getMe(): Promise<Usuario> {
  return chamar<Usuario>("/me");
}

/** Apaga a conta — irreversível, `DELETE /me` exige a senha atual mesmo já
 *  autenticada por token (`core/auth.py`): um token vazado não deveria
 *  bastar pra sequestrar E apagar a conta. `ON DELETE CASCADE` (migração
 *  009) limpa tentativa/progresso/erro_caderno/simulado/mesa(+edital+tópico)
 *  de uma vez — não existe desfazer depois disto. */
export function apagarConta(senha: string): Promise<{ ok: true }> {
  return chamar("/me", { method: "DELETE", body: JSON.stringify({ senha }) });
}

export type Perfil = { horas?: string; nivel?: string; turno?: string };

/** As três respostas do onboarding (horas/nível/turno). Faz merge no
 *  servidor: mandar só `turno` não apaga o que já estava lá. */
export function salvarPerfil(perfil: Perfil): Promise<{ perfil: Record<string, string> }> {
  return chamar("/me/perfil", { method: "PUT", body: JSON.stringify(perfil) });
}

/** Faltava o caminho de volta — só existia gravar. `/desafio` usa isto pra
 *  calibrar o orçamento padrão de UMA sessão pelas horas/dia declaradas. */
export function getPerfil(): Promise<Perfil> {
  return chamar<Perfil>("/me/perfil");
}

// ---------------------------------------------------------------------- mesas
/**
 * Uma mesa é um concurso-alvo: guarda o edital e RECORTA o que aparece
 * (fila, painel, caderno, simulado) pelas disciplinas dele. O que ela NÃO
 * guarda é progresso — a caixa SM-2 é do aluno e atravessa as mesas
 * (migração 010). Por isso `cobertura_pct` aqui é a mesma definição do
 * painel, só que restrita às disciplinas desta mesa.
 */
export type Mesa = {
  id: number;
  nome: string;
  orgao: string | null;
  banca: string | null;
  criado_em: string;
  // null = ninguém declarou alvo ainda → não filtra nada (ver 017).
  disciplinas: string[] | null;
  /** DE ONDE veio o recorte. Sem isso "5 disciplinas" parece a mesma coisa
   *  vindo do PDF ou escolhido à mão, e o aluno não sabe se ainda falta
   *  subir o edital. */
  origem_alvo: "edital" | "manual" | "nenhum";
  disciplinas_manuais: string[];
};

export type MesaNaLista = Mesa & {
  edital_id: number | null;
  edital_titulo: string | null;
  data_prova: string | null;
  topicos: number;
  questoes: number;
  dominadas: number;
  cobertura_pct: number;
  /** Tópicos do edital ESTIMADOS como cobertos — mesma conta que a
   *  probabilidade de fechamento usa (cobertura de questões da disciplina
   *  aplicada aos tópicos dela). Sem edital, 0. */
  topicos_cobertos: number;
  cobertura_topicos_pct: number;
  ultimo_estudo: string | null;
};

/** O que existe no acervo pra escolher como alvo. Sai do acervo e não de
 *  lista fixa: uma mesa de TI num banco só de Direito precisa VER que não
 *  há o que escolher. */
export function getDisciplinasDoAcervo(): Promise<{ disciplinas: string[] }> {
  return chamar("/disciplinas");
}

export function getMesas(): Promise<MesaNaLista[]> {
  return chamar<MesaNaLista[]>("/mesas");
}

/** Em qual mesa a API está me atendendo agora — com o fallback já
 *  resolvido lá, pra este cliente não ter uma segunda cópia da regra.
 *  `questoes` = quantas questões do acervo caem no recorte desta mesa;
 *  serve pras telas de estudo explicarem o vazio em vez de exibi-lo. */
export function getMesaAtual(): Promise<Mesa & { questoes: number }> {
  return chamar<Mesa & { questoes: number }>("/mesa");
}

export function criarMesa(nome: string, orgao?: string, banca?: string): Promise<Mesa> {
  return chamar<Mesa>("/mesas", {
    method: "POST",
    body: JSON.stringify({ nome, orgao, banca }),
  });
}

export function atualizarMesa(
  id: number,
  campos: {
    nome?: string;
    orgao?: string | null;
    banca?: string | null;
    /** Alvo declarado à mão, pra mesa sem edital publicado. `[]` limpa. */
    disciplinas?: string[];
  }
): Promise<Mesa> {
  return chamar<Mesa>(`/mesas/${id}`, {
    method: "PATCH",
    body: JSON.stringify(campos),
  });
}

export function apagarMesa(id: number): Promise<{ ok: boolean }> {
  return chamar(`/mesas/${id}`, { method: "DELETE" });
}

// ----------------------------------------------------------------------- fila
export type TipoQuestao = "resposta_livre" | "certo_errado";

export type Questao = {
  id: number;
  disciplina: string;
  tema: string;
  enunciado: string;
  /** Discursiva: o gabarito. Item C/E: a JUSTIFICATIVA (por que está certo
   *  ou errado) — a coluna é NOT NULL nos dois tipos, com papéis diferentes
   *  (migração 012). */
  gabarito: string;
  dicas: string[];
  tipo: TipoQuestao;
  /** Só no item C/E; `null` na discursiva (CHECK no banco garante). */
  gabarito_ce: boolean | null;
  /** "Texto associado" do Cebraspe (migração 013): o texto-base que VÁRIOS
   *  itens julgam. `null` = item avulso, que se basta. Vem junto da questão
   *  por JOIN, nunca numa segunda chamada — assertiva sem o texto-base é
   *  ilegível ("com base no argumento acima"), e buscar separado criaria um
   *  instante em que a tela tem a pergunta e não tem o enunciado. */
  contexto: string | null;
  contexto_id: number | null;
  /** Posição dentro da série ("item 2"). A ordem importa: itens do Cebraspe
   *  encadeiam raciocínio sobre o mesmo caso. */
  ordem_no_contexto: number | null;
  caixa: number;
  prox_revisao: string;
};

export function getFila(): Promise<Questao[]> {
  return chamar<Questao[]>("/fila");
}

export type Carga = {
  revisoes: number;
  ineditas: number;
  teto: number;
  atraso: number;
  // Antes eram os 2 KPIs mock do painel (OFENSIVA/TEMPO_MEDIO de
  // mock/prototipo.ts) — agora vêm de scheduler.carga_hoje() de verdade.
  tempo_medio_segundos: number;
  ofensiva_dias: number;
};

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
  /** Discursiva: gabarito. Item C/E: justificativa (migração 012). */
  gabarito: string;
  tipo: TipoQuestao;
  gabarito_ce: boolean | null;
  contexto: string | null;
  contexto_id: number | null;
  ordem_no_contexto: number | null;
};

export function iniciarSimulado(
  n: number,
  minutos?: number,
  disciplina?: string,
  nome?: string
): Promise<{ simulado_id: number; questoes: QuestaoSimulado[] }> {
  return chamar("/simulados", {
    method: "POST",
    body: JSON.stringify({ n, minutos, disciplina, nome: nome || undefined }),
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

export type ResultadoSimulado = { total: number; acertos: number; parciais: number; erros: number; nota_pct: number };
export type RelatorioDisciplina = { disciplina: string; questoes: number; acertos: number; pct: number };
export type ErroSimulado = { tema: string; enunciado: string; gabarito: string; resposta: string; veredito: string };

/**
 * Salva UMA resposta na hora (migração 018) — não é lote no final. É o que
 * faz o simulado sobreviver a aba fechada ou conexão caindo no meio: cada
 * resposta já está no banco antes da próxima pergunta aparecer, não só
 * depois de "finalizar". `segundosAcumulados` é o relógio ATIVO da prova
 * (exclui tempo pausado) — quem manda o valor certo é `SimuladoRunner`.
 */
export function responderUmaSimulado(
  simuladoId: number,
  questaoId: number,
  resposta: string,
  segundosPergunta: number,
  segundosAcumulados: number
): Promise<{ ok: boolean; ja_respondida: boolean }> {
  return chamar(`/simulados/${simuladoId}/responder`, {
    method: "POST",
    body: JSON.stringify({
      questao_id: questaoId,
      resposta,
      segundos_pergunta: segundosPergunta,
      segundos_acumulados: segundosAcumulados,
    }),
  });
}

/** Só o relógio, sem responder questão nenhuma — "pausar" e "sair" chamam
 *  isto pra não perder o tempo decorrido quando não há resposta nova
 *  nesta visita (sem isso, só `responderUmaSimulado` salvava o tempo). */
export function salvarTempoSimulado(
  simuladoId: number,
  segundosAcumulados: number
): Promise<{ ok: boolean }> {
  return chamar(`/simulados/${simuladoId}/tempo`, {
    method: "POST",
    body: JSON.stringify({ segundos_acumulados: segundosAcumulados }),
  });
}

export type EstadoSimulado = {
  id: number;
  questoes: (QuestaoSimulado & { respondida: boolean; resposta_dada: string | null })[];
  minutos_alvo: number | null;
  segundos_acumulados: number;
  finalizado: boolean;
};

/** Reconstrói uma prova em andamento — o que a tela usa pra "continuar de
 *  onde parei": pula as já respondidas, retoma o relógio do ponto salvo. */
export function getEstadoSimulado(simuladoId: number): Promise<EstadoSimulado> {
  return chamar<EstadoSimulado>(`/simulados/${simuladoId}/estado`);
}

/** Fecha a prova e devolve o relatório. Não manda respostas — todas já
 *  foram salvas via `responderUmaSimulado`, uma a uma. */
export function finalizarSimulado(
  simuladoId: number,
  segundosTotal: number
): Promise<{ resultado: ResultadoSimulado; relatorio: RelatorioDisciplina[]; erros: ErroSimulado[] }> {
  return chamar(`/simulados/${simuladoId}/finalizar`, {
    method: "POST",
    body: JSON.stringify({ segundos_total: segundosTotal }),
  });
}

/** Tira a prova do histórico — não mexe em tentativa/progresso, só na
 *  etiqueta "isso foi uma prova" (ver core/simulado.apagar). */
export function apagarSimulado(simuladoId: number): Promise<{ ok: boolean }> {
  return chamar(`/simulados/${simuladoId}`, { method: "DELETE" });
}

/** Reabre a revisão de uma prova — em andamento ou já fechada, tanto faz.
 *  Só LÊ (nunca re-finaliza) — é o que o histórico usa pro "ver revisão"
 *  continuar disponível bem depois da prova ter acabado. */
export function getRelatorioSimulado(
  simuladoId: number
): Promise<{ resultado: ResultadoSimulado; relatorio: RelatorioDisciplina[]; erros: ErroSimulado[] }> {
  return chamar(`/simulados/${simuladoId}/relatorio`);
}

export type HistoricoSimulado = {
  id: number;
  nome: string | null;
  n_questoes: number;
  minutos_alvo: number | null;
  segundos_total: number | null;
  criado_em: string;
  em_andamento: boolean;
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
  /** O que foi PEDIDO, pra tela poder dizer "você pediu 20, cabem 18"
   *  quando o acervo acaba antes do tempo. `null` = sem orçamento. */
  minutos_pedidos: number | null;
};

/** `minutos` = "só tenho N minutos hoje". O servidor corta os blocos pra
 *  caber usando a SUA velocidade média real, não um número fixo. */
export function getDesafio(minutos?: number): Promise<PlanoDesafio> {
  return chamar<PlanoDesafio>(minutos ? `/desafio?minutos=${minutos}` : "/desafio");
}

// -------------------------------------------------------------- intervenção
/** `sugestao` = aviso passivo (tendência). `intervencao` = o pedido de
 *  PARAR agora, com uma pergunta pronta pro tutor — interromper sem
 *  oferecer pra onde ir é só atrapalhar. */
export type Intervencao = { motivo: string; texto: string; pergunta: string };

export function getSugestao(): Promise<{
  sugestao: string | null;
  intervencao: Intervencao | null;
}> {
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

/** Um turno do chat. Sem `conversaId`, o servidor abre uma conversa e
 *  devolve o id — o cliente não paga uma chamada a mais só pra existir. */
export function perguntar(
  pergunta: string,
  conversaId?: number
): Promise<{ resposta: string; fontes: Fonte[]; conversa_id: number; titulo: string }> {
  return chamar("/perguntar", {
    method: "POST",
    body: JSON.stringify({ pergunta, conversa_id: conversaId }),
  });
}

// ------------------------------------------------------------------ conversas
export type ConversaNaLista = {
  id: number;
  titulo: string;
  mesa_id: number | null;
  mesa_nome: string | null;
  mensagens: number;
  atualizada_em: string;
};

export type MensagemSalva = {
  id: number;
  autor: "aluno" | "tutor";
  texto: string;
  fontes: Fonte[];
  criada_em: string;
};

export function getConversas(): Promise<ConversaNaLista[]> {
  return chamar<ConversaNaLista[]>("/conversas");
}

export function getConversa(
  id: number
): Promise<ConversaNaLista & { mensagens: MensagemSalva[] }> {
  return chamar(`/conversas/${id}`);
}

export function apagarConversa(id: number): Promise<{ ok: boolean }> {
  return chamar(`/conversas/${id}`, { method: "DELETE" });
}

/** Questão criada na hora a partir do acervo, quando o banco não tem o que
 *  servir. `descartadas` é o número de questões que o modelo devolveu e o
 *  backend recusou por proveniência — mostrar isso é o oposto de esconder
 *  que a IA erra. */
export type QuestoesGeradas = {
  questoes: Omit<Questao, "caixa" | "prox_revisao">[];
  descartadas: number;
  motivos: string[];
  fontes: string[];
};

export function gerarQuestoes(
  tema?: string,
  quantidade = 3,
  /** Omitido = o servidor decide pela banca da mesa (Cebraspe -> item
   *  C/E). A regra de "qual formato treinar" tem um dono só, e é ele. */
  tipo?: TipoQuestao,
  /** Quando a questão nasce DENTRO de uma conversa, o fato entra na linha
   *  do tempo dela — senão o tutor propõe o exercício e não fica sabendo. */
  conversaId?: number
): Promise<QuestoesGeradas> {
  return chamar<QuestoesGeradas>("/questoes/gerar", {
    method: "POST",
    body: JSON.stringify({ tema, quantidade, tipo, conversa_id: conversaId }),
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

export type EditalAtual = {
  id: number; titulo: string; data_prova: string | null;
  /** Cargo escolhido na curadoria (migração 018). null = não declarado:
   *  concurso de cargo único, ingestão por CLI, ou o aluno seguiu sem nomear
   *  o próprio cargo. Tratar como ausência, nunca como erro. */
  cargo: string | null;
  cobertura: CoberturaDisciplina[];
};

/** Tira ou acrescenta matéria num edital JÁ confirmado, sem subir o PDF de
 *  novo. A curadoria acontecia uma vez só; o aluno muda de ideia no MEIO do
 *  estudo, que é quando ele sabe o que está sobrando. */
export function ajustarDisciplinasEdital(
  ajuste: { remover?: string[]; adicionar?: string[] }
): Promise<{ cobertura: CoberturaDisciplina[] }> {
  return chamar("/edital/disciplinas", { method: "PATCH", body: JSON.stringify(ajuste) });
}

/** Aponta uma data futura quando a do edital já passou. Prova vencida deixa a
 *  meta em "0 dias / 0%" — verdadeiro e inútil: sem prazo não há ritmo. */
export function corrigirDataProva(data_prova: string): Promise<EditalAtual> {
  return chamar("/edital/data-prova", { method: "PATCH", body: JSON.stringify({ data_prova }) });
}

/** Um material da biblioteca privada do aluno (migração 019). */
export type Material = {
  id: number;
  titulo: string;
  /** null = ainda não classificado (020). O classificador roda em background
   *  depois de indexar; a tela mostra "identificando…" nesse meio-tempo. */
  disciplina: string | null;
  /** Um nível abaixo da disciplina — é o que distingue a aula 3 da aula 11 de
   *  um mesmo curso, que caem todas na mesma disciplina. */
  assunto: string | null;
  /** Procedência do rótulo: `aluno` digitou, `modelo` leu o começo do texto.
   *  A tela usa isso pra pedir conferência só no palpite. */
  classificado_por: "aluno" | "modelo" | "acervo" | null;
  tipo: "aula" | "resumo" | "jurisprudencia";
  status: "processando" | "pronto" | "falha";
  /** Razão da falha, em texto — "PDF protegido", "precisa de OCR". null quando
   *  não falhou. Sem ela o aluno vê "falha" e não sabe o que fazer. */
  erro: string | null;
  /** Trechos ESPERADOS (gravado antes de indexar) e os já indexados. Os dois
   *  juntos dão o "187 de 340" enquanto o embedding roda. */
  chunks_total: number | null;
  chunks: number;
  origem: string | null;
  criado_em: string;
};

/** Rótulos que ESTE aluno já usou, pro seletor da tela oferecer em vez de
 *  exigir que ele lembre da grafia exata que digitou semana passada.
 *
 *  `assuntos_por_disciplina` existe porque assunto só faz sentido DENTRO de uma
 *  matéria: oferecer "Remédios constitucionais" a quem está subindo
 *  Contabilidade é ruído. A lista chapada serve pra quando não há disciplina
 *  escolhida ainda. */
export type SugestoesMaterial = {
  disciplinas: string[];
  assuntos: string[];
  assuntos_por_disciplina: Record<string, string[]>;
};

export function getSugestoesMaterial(): Promise<SugestoesMaterial> {
  return chamar("/materiais/sugestoes");
}

export function getMateriais(): Promise<{ materiais: Material[] }> {
  return chamar("/materiais");
}

/** O embedding roda local na CPU e leva minutos num PDF grande, então isto
 *  responde na hora com `status: "processando"` — quem acompanha o progresso é
 *  o polling da lista, não esta chamada. */
export function subirMaterial(
  arquivo: File,
  dados: { disciplina?: string; assunto?: string; tipo: string; titulo?: string }
): Promise<Material> {
  const fd = new FormData();
  fd.append("arquivo", arquivo);
  // Disciplina e assunto são OPCIONAIS (020): vazio significa "descubra você",
  // e o classificador preenche. Mandar string vazia seria o mesmo que mandar
  // nada, mas explicitar evita gravar "" como se fosse rótulo.
  if (dados.disciplina?.trim()) fd.append("disciplina", dados.disciplina.trim());
  if (dados.assunto?.trim()) fd.append("assunto", dados.assunto.trim());
  fd.append("tipo", dados.tipo);
  if (dados.titulo) fd.append("titulo", dados.titulo);
  return chamarFormData("/materiais", fd);
}

/** Indexa uma URL pública. O servidor resolve o DNS e recusa IP não-público
 *  (SSRF) — ver `material.baixar`, que também diz o que isso NÃO cobre. */
export function indexarLink(dados: {
  url: string;
  disciplina?: string;
  assunto?: string;
  tipo?: string;
}): Promise<Material> {
  return chamar("/materiais/link", { method: "POST", body: JSON.stringify(dados) });
}

/** Corrige o palpite do classificador. Passa a valer como `aluno`. */
export function classificarMaterial(
  id: number,
  dados: { disciplina?: string; assunto?: string }
): Promise<Material> {
  return chamar(`/materiais/${id}`, { method: "PATCH", body: JSON.stringify(dados) });
}

/** Tenta indexar de novo. O arquivo volta porque o servidor guarda só o NOME
 *  em `documento.origem`, não os bytes — e `indexar` é idempotente, então isto
 *  não duplica trechos. */
export function reindexarMaterial(id: number, arquivo: File): Promise<{ ok: true }> {
  const fd = new FormData();
  fd.append("arquivo", arquivo);
  return chamarFormData(`/materiais/${id}/reindexar`, fd);
}

export function apagarMaterial(id: number): Promise<{ ok: true }> {
  return chamar(`/materiais/${id}`, { method: "DELETE" });
}

export function getEdital(): Promise<EditalAtual> {
  return chamar<EditalAtual>("/edital");
}

// ------------------------------------------------- edital: curadoria
// Subir o PDF cria um RASCUNHO, não um edital. Nada vira fila SM-2 antes
// de a pessoa escolher o cargo e revisar as disciplinas — um edital tem
// vários cargos, e somar todos põe matéria de Advocacia no plano de quem
// vai prestar TI. Ver core/rascunho.py.
export type DisciplinaEdital = { disciplina: string; topicos: string[] };
export type CargoEdital = { nome: string; disciplinas: DisciplinaEdital[] };
export type EstruturaEdital = { comuns: DisciplinaEdital[]; cargos: CargoEdital[] };

export type Rascunho = {
  id: number;
  titulo: string;
  arquivo: string | null;
  data_prova: string | null;
  candidatos_data: { data: string; pontuacao: number; contexto: string }[];
  estrutura: EstruturaEdital;
  /** quem extraiu. "llm" merece revisão mais atenta que "parser". */
  origem: "parser" | "llm" | "parser_apos_falha";
  expira_em: string;
};

export function criarRascunho(arquivo: File, titulo?: string): Promise<Rascunho> {
  const form = new FormData();
  form.append("arquivo", arquivo);
  if (titulo) form.append("titulo", titulo);
  return chamarFormData<Rascunho>("/editais/rascunho", form);
}

export function getRascunho(id: number): Promise<Rascunho> {
  return chamar<Rascunho>(`/editais/rascunho/${id}`);
}

export function confirmarRascunho(
  id: number,
  dados: {
    disciplinas: DisciplinaEdital[];
    titulo?: string;
    data_prova?: string;
    orgao?: string;
    banca?: string;
    /** Cargo escolhido na curadoria — vai pra `edital.cargo` (018). */
    cargo?: string;
  }
): Promise<{ edital_id: number; disciplinas: number; topicos: number }> {
  return chamar(`/editais/rascunho/${id}/confirmar`, {
    method: "POST",
    body: JSON.stringify(dados),
  });
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
  segundos: number,
  /** Respondida DENTRO de uma conversa: o resultado entra na linha do tempo
   *  dela, e o tutor considera isso no próximo turno em vez de continuar
   *  explicando como se nada tivesse acontecido. */
  conversaId?: number
): Promise<Registro> {
  return chamar<Registro>(`/questoes/${questaoId}/registrar`, {
    method: "POST",
    body: JSON.stringify({
      veredito,
      resposta,
      dicas_usadas: dicasUsadas,
      segundos,
      conversa_id: conversaId,
    }),
  });
}
