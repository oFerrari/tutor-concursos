"use client";

import { useEffect, useLayoutEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { getMesaAtiva, limparToken } from "./api";

/**
 * Cache de tela: o que já foi visto volta INSTANTÂNEO e revalida por baixo.
 *
 * O sintoma que motivou isto foi relatado como lentidão do servidor: subir três
 * materiais e o resto do site "ficar carregando". MEDIDO que não era o servidor
 * — com quatro indexações em curso, `/fila` respondia em ~30ms contra 15ms de
 * baseline. O que acontecia é mais simples e mais fundo: cada tela nascia com
 * `useState(null)` e buscava na montagem, então TODA navegação recomeçava do
 * zero e mostrava "Carregando…", indexação ou não.
 *
 * `sessionStorage` e não memória de módulo: o Next remonta a árvore num
 * `router.push` para outra rota e a memória do módulo até sobrevive, mas um F5
 * (que o aluno dá) apagaria tudo. E não `localStorage`: dado de estudo
 * desatualizado de ontem reaparecendo hoje como se fosse de agora é pior que
 * um "Carregando…" honesto — a sessão é o horizonte certo.
 *
 * A CHAVE INCLUI A MESA, e isso não é detalhe: fila, caderno e desempenho são
 * recortados pelo header `X-Mesa-Id` (migração 010). Cache cego à mesa mostraria
 * a fila do outro concurso ao trocar de mesa — exatamente a falha silenciosa que
 * a decisão de "o servidor é o dono da regra de fallback" existe para evitar.
 *
 * É cache de EXIBIÇÃO, não fonte de verdade: a tela mostra o que tem e substitui
 * pelo que o servidor responder. Nada aqui decide nada.
 */
const PREFIXO = "tutor_cache:";

function chaveCompleta(chave: string): string {
  return `${PREFIXO}${getMesaAtiva() ?? "padrao"}:${chave}`;
}

export function lerCache<T>(chave: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const cru = sessionStorage.getItem(chaveCompleta(chave));
    return cru ? (JSON.parse(cru) as T) : null;
  } catch {
    // Cache corrompido ou storage bloqueado não pode derrubar a tela: cai no
    // comportamento anterior (busca e mostra "Carregando…").
    return null;
  }
}

export function gravarCache(chave: string, valor: unknown): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(chaveCompleta(chave), JSON.stringify(valor));
  } catch {
    // Cota estourada: seguir sem cache é degradação aceitável.
  }
}

/** Chamada ao sair da conta e ao trocar de mesa pelo seletor — dado de estudo
 *  de uma conta não pode sobrar na tela da próxima. */
export function limparCache(): void {
  if (typeof window === "undefined") return;
  try {
    for (const k of Object.keys(sessionStorage)) {
      if (k.startsWith(PREFIXO)) sessionStorage.removeItem(k);
    }
  } catch {
    /* nada a fazer */
  }
}

/** `limparToken` + cache, para o logout não deixar rastro. */
export function sair(): void {
  limparCache();
  limparToken();
}


/**
 * O MESMO cache, sem quebrar a hidratação.
 *
 * `useState(() => lerCache("fila"))` parece o jeito óbvio e tem um defeito que
 * só aparece com o servidor de pé: no SERVIDOR não existe `sessionStorage`,
 * então o HTML sai com o esqueleto de carregamento; no CLIENTE o inicializador
 * lê o cache e a PRIMEIRA renderização já vem com a tela cheia. Os dois não
 * batem, e o React descarta a árvore hidratada e refaz tudo — com um erro
 * vermelho na tela em desenvolvimento ("Hydration failed", relatado em
 * `/fila`). O cache existe pra economizar trabalho e estava causando o dobro.
 *
 * Aqui a primeira renderização é IGUAL nos dois lados (`null`, esqueleto) e o
 * cache entra num efeito de LAYOUT, que roda depois do commit e ANTES da
 * pintura — então continua sem piscar "Carregando…", que era o ponto.
 * `useEffect` no servidor é o de sempre: lá o efeito nunca roda, e usar
 * `useLayoutEffect` direto só renderia um aviso do React.
 */
const useEfeitoDeLayout = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function useCache<T>(chave: string): [T | null, Dispatch<SetStateAction<T | null>>] {
  const [valor, setValor] = useState<T | null>(null);
  useEfeitoDeLayout(() => {
    const doCache = lerCache<T>(chave);
    // Só SEMEIA: se a resposta do servidor já chegou (revalidação rápida ou
    // mesa trocada), sobrescrever com o cache seria andar pra trás.
    if (doCache !== null) setValor((atual) => (atual === null ? doCache : atual));
  }, [chave]);
  return [valor, setValor];
}
