"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Preferência de TELA deste navegador — "mostrar as fontes do tutor" e afins.
 *
 * `useSyncExternalStore` e não `useState` + efeito: ler o localStorage no
 * primeiro render quebra a hidratação (o servidor não tem localStorage), e
 * copiá-lo para o estado num efeito é o `set-state-in-effect` que o lint do
 * projeto proíbe. Assim o servidor renderiza o padrão e o cliente assume o
 * valor guardado sem pisca-pisca de estado intermediário.
 *
 * Só para conveniência: acesso bloqueado (aba anônima, cota) cai no padrão,
 * e nada que precise persistir de verdade mora aqui.
 */
const EVENTO = "tutor:preferencia";

function ler(chave: string): string | null {
  try {
    return window.localStorage.getItem(chave);
  } catch {
    return null;
  }
}

function assinar(avisar: () => void) {
  window.addEventListener("storage", avisar);
  window.addEventListener(EVENTO, avisar);
  return () => {
    window.removeEventListener("storage", avisar);
    window.removeEventListener(EVENTO, avisar);
  };
}

export function usePreferencia(chave: string, padrao: boolean): [boolean, (v: boolean) => void] {
  const bruto = useSyncExternalStore(
    assinar,
    () => ler(chave),
    () => null
  );
  const valor = bruto === null ? padrao : bruto === "1";
  const definir = useCallback(
    (v: boolean) => {
      try {
        window.localStorage.setItem(chave, v ? "1" : "0");
      } catch {
        // sem armazenamento a escolha não fica — a tela segue no padrão
      }
      window.dispatchEvent(new Event(EVENTO));
    },
    [chave]
  );
  return [valor, definir];
}
