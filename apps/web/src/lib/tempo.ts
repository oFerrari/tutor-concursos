/**
 * Cronometragem de resposta — o número que vira `tentativa.segundos`.
 *
 * Fora de qualquer componente de propósito. Duas razões, e a segunda é a
 * que importa:
 *
 * 1. É a MESMA conta em `DialogoQuestao` e `SimuladoRunner`, e o projeto
 *    prefere uma definição a duas cópias que divergem (mesmo motivo de
 *    `core/mesa.filtro` existir num lugar só do lado Python).
 *
 * 2. `Date.now()` aqui é legítimo e o linter concorda — em escopo de
 *    módulo isto não é código de render. Dentro do componente, a mesma
 *    chamada é reportada por `react-hooks/purity` mesmo num handler, que
 *    é falso positivo da regra; extrair pra cá resolve pelo argumento
 *    certo (não é render) em vez de calar o aviso com um disable.
 *
 * O marco de largada continua sendo gravado num `useRef` preenchido por
 * efeito, NUNCA por `useRef(Date.now())`: o argumento do useRef é avaliado
 * a cada render, e aí a impureza seria real.
 */

/**
 * Segundos inteiros desde `desde`. `null` (efeito de largada ainda não
 * rodou — na prática impossível, exige interação do usuário) devolve 0 em
 * vez de ~1,8 bilhão: `tentativa.segundos` alimenta a média de tempo do
 * desafio, e um outlier desses envenenaria a estimativa de todo dia
 * seguinte com um número que ninguém saberia de onde veio.
 */
export function decorridos(desde: number | null): number {
  return Math.round((Date.now() - (desde ?? Date.now())) / 1000);
}
