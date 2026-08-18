/**
 * As três perguntas do perfil de estudo (horas/nível/turno) — migração 015,
 * `usuario.perfil` (JSONB), `GET/PUT /me/perfil`.
 *
 * Morava em `mock/prototipo.ts` por herança do protótipo original, mas não
 * é dado decorativo: é a config de uma tela que já grava de verdade desde
 * a 015. Fica aqui porque tem DOIS consumidores agora — o onboarding
 * (primeiro contato) e `/perfil` (editar depois) — e `mock/` é
 * explicitamente pra número que ainda NÃO tem endpoint por trás.
 */
export const ENTREVISTA = [
  { chave: "horas", rotulo: "Horas por dia", opcoes: ["1h", "2h", "4h", "6h+"], padrao: "2h" },
  { chave: "nivel", rotulo: "Seu nível hoje", opcoes: ["Começando", "Intermediário", "Avançado"], padrao: "Intermediário" },
  { chave: "turno", rotulo: "Melhor horário", opcoes: ["Manhã", "Tarde", "Noite", "Madrugada"], padrao: "Manhã" },
] as const;
