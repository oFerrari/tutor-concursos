/**
 * ============================================================================
 * DADOS DE EXEMPLO DO PROTÓTIPO — NÃO SÃO DADOS REAIS.
 * ============================================================================
 *
 * Tudo neste arquivo veio do mockup `FerrarIA.dc.html` e existe por uma
 * razão só: as telas de mesas, biblioteca e onboarding foram desenhadas
 * antes de o `api.py` ter rota pra elas. Decisão consciente (e temporária)
 * de escrever a tela primeiro e ligar o dado depois.
 *
 * REGRA: nenhum número daqui pode vazar para uma tela que JÁ tem endpoint.
 * Panorama, fila, erros, simulado, desempenho e meta leem a API de verdade
 * e devem continuar assim — é o mesmo princípio de `socratic.explicar()` no
 * backend (a camada de apresentação LÊ resumo calculado, nunca inventa
 * percentual). Misturar número medido com número decorativo na mesma tela
 * ensina o usuário a não confiar em nenhum dos dois.
 *
 * COMO REMOVER: cada consumidor deste arquivo tem um comentário
 * `TODO(backend)` dizendo qual rota falta. Quando a rota existir, troque o
 * import e apague o bloco correspondente aqui. Quando este arquivo ficar
 * vazio, apague o arquivo — é esse o plano.
 *
 * Rotas que faltam: nenhuma das telas listadas aqui. O que sobrou neste
 * arquivo é número DECORATIVO (bloco abaixo) e a conversa de exemplo do
 * tutor, que depende de uma decisão de schema, não de uma rota.
 *
 * JÁ SAÍRAM DAQUI (o plano funcionando):
 *   - biblioteca → migração 019 + GET/POST/DELETE /materiais.
 *     `MATERIAIS_EXEMPLO` e `StatusMaterial` foram apagados. A migração ERA
 *     necessária, ao contrário do que este comentário previa: `documento`
 *     existia mas não tinha DONO, e a tela promete "só você tem acesso" —
 *     sem `usuario_id` a apostila de um aluno entraria no `retrieval.buscar`
 *     de todos. Ganhou também estado de processamento, porque o embedding
 *     roda local na CPU e leva minutos: o "187 de 340" precisa viver no
 *     banco pra sobreviver a um F5.
 *   - mesas → migração 010 + GET/POST /mesas. `MESA_ATUAL` e `MESAS_EXEMPLO`
 *     foram apagados; a tela /mesas, a sidebar e o raio-x leem a API.
 *   - onboarding → migração 015 + GET/PUT /me/perfil. `ENTREVISTA` mudou de
 *     dado decorativo pra config de tela real e mudou de arquivo: agora
 *     mora em `lib/perfil.ts`, usada pelo onboarding E por `/perfil`
 *     (editar depois que a entrevista inicial já passou).
 * ============================================================================
 */

/**
 * Números que o protótipo mostra e que NÃO EXISTEM no schema.
 *
 * Ficam aqui, num bloco só, porque a decisão foi manter o texto do
 * protótipo por ora — mas a fronteira precisa estar visível: tudo abaixo
 * é decorativo, e nenhum destes números muda quando você estuda.
 *
 * TODO(backend), em ordem de esforço:
 *   - tempo médio: `tentativa.segundos` JÁ é gravado. Falta um `avg()` em
 *     `scheduler.desempenho()` e o campo em `/stats`. É o mais barato.
 *   - ofensiva (dias seguidos): dá pra derivar de `tentativa.criado_em`
 *     com uma janela por dia — não exige coluna nova, exige a query.
 *   - liga/ranking: exige comparar usuários entre si. Hoje o acervo é
 *     compartilhado mas o progresso é isolado (migração 008), e não há
 *     nada que ordene contas. É o mais caro, e o menos útil.
 */
export const OFENSIVA = { dias: 12, recorde: 21 };
export const LIGA = { nome: "Ouro", posicao: "7º de 42" };
export const TEMPO_MEDIO = { valor: "1m 48s", nota: "por questão" };
export const ACERTO_NOTA = "+4 pts vs. mês anterior";
export const FLASHCARDS_NA_FILA = 28;


/**
 * Conversa de exemplo do tutor.
 *
 * TODO(backend): o `/perguntar` já responde pergunta livre e o
 * `/questoes/{id}/avaliar` já faz o diálogo socrático — mas o protótipo
 * mostra a questão com alternativas A/B/C, e `questao.gabarito` é texto
 * aberto no schema. Ligar esta tela na API de verdade é decidir antes se
 * a questão ganha alternativas (coluna nova) ou se a tela abandona o
 * múltipla-escolha e usa o campo de resposta livre que a `/fila` já usa.
 */
export const ROTA_DO_DIA = [
  { n: 1, texto: "3 revisões SM-2 de Penal · peculato e improbidade", tempo: "12 min" },
  { n: 2, texto: "Bloco novo de RLM · equivalências lógicas", tempo: "24 min" },
  { n: 3, texto: "6 erros do caderno para fechar o dia", tempo: "12 min" },
];

export const QUESTAO_EXEMPLO = {
  fonte: ["Questão · SM-2", "CESPE 2023", "Art. 312, CP"],
  enunciado: "Quanto ao peculato culposo, a reparação do dano antes da sentença irrecorrível produz qual efeito?",
  alternativas: [
    { letra: "A", texto: "Extingue a punibilidade." },
    { letra: "B", texto: "Reduz a pena pela metade." },
    { letra: "C", texto: "Nenhum efeito; a reparação é irrelevante." },
  ],
  correta: "A",
  dica:
    "Antes da sentença irrecorrível, extingue a punibilidade (§3º). Depois, apenas reduz a pena pela metade. " +
    "Seu erro recorrente é inverter esses dois momentos — e isso só vale para a modalidade culposa.",
};

export const FLASHCARD_EXEMPLO = {
  posicao: "2 de 5",
  frente: "Peculato culposo: reparação DEPOIS da sentença irrecorrível →",
  verso: "reduz a pena pela metade",
};

export const ABERTURA_TUTOR = {
  horario: "Hoje · 06:40",
  paragrafo1:
    "Bom dia, Andrei. Senti sua falta ontem — sua ofensiva de 12 dias quase caiu. Olhei sua memória: o SM-2 está pedindo socorro em 3 questões de Penal e você não toca em RLM há 9 dias.",
  paragrafo2Prefixo: "Faltam ",
  paragrafo2Destaque: "63 dias",
  paragrafo2Sufixo: " para a prova e 39% do edital ainda está aberto. Minha sugestão de rota para hoje, em 48 minutos:",
  perguntaUsuario: "Aceito, mas me explica peculato culposo primeiro. Erro sempre.",
  respostaSocratica:
    "Não vou te dar a regra pronta. Você errou 3× a mesma pegadinha, então vamos pelo caminho inverso: responda e eu te mostro onde seu raciocínio desvia.",
};
