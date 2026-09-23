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
 * arquivo é somente número DECORATIVO (bloco abaixo).
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
export const TEMPO_MEDIO = { valor: "1m 48s", nota: "por questão" };
export const ACERTO_NOTA = "+4 pts vs. mês anterior";
