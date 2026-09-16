"use client";

import { ArrowUp } from "lucide-react";
import { usePathname } from "next/navigation";
import { RefObject, useEffect, useState } from "react";

/**
 * Setinha de voltar ao topo, no canto de baixo da coluna de conteúdo.
 *
 * O relato: no relatório de uma prova de 10 questões e no caderno de erros, a
 * única saída ficava depois de TUDO — rolar a lista inteira pra achar um botão
 * e rolar de volta pra chegar em qualquer outro lugar. Página longa precisa de
 * saída onde a pessoa ESTÁ, e a pessoa está no fim.
 *
 * QUEM ROLA AQUI NÃO É A JANELA. O `AppShell` dá `h-screen overflow-hidden` no
 * corpo e a barra de rolagem vive no `<main>` — `window.scrollTo(0, 0)` não
 * faria nada, e `window.scrollY` seria sempre 0. Por isso o alvo chega por ref
 * de quem criou o elemento, em vez de um `querySelector` adivinhando.
 *
 * `absolute` dentro da `<section>` (que é `relative`) e não `fixed`: no
 * desktop o Raio-X é COLUNA ao lado, então a coluna de conteúdo encolhe e a
 * seta acompanha; com `fixed` ela ficaria por cima do painel. E fora do
 * `<main>`, que é o que rola — dentro, ela rolaria junto e sumiria.
 */
const LIMIAR = 600;

export function VoltarAoTopo({ alvo }: { alvo: RefObject<HTMLElement | null> }) {
  const [visivel, setVisivel] = useState(false);
  const caminho = usePathname();

  useEffect(() => {
    const el = alvo.current;
    if (!el) return;
    const medir = () => setVisivel(el.scrollTop > LIMIAR);
    // Mede JÁ, sem esperar rolagem: trocar de rota mantém o mesmo `<main>`
    // montado (ele mora no layout), e o Next reposiciona o scroll sem
    // necessariamente disparar evento — a seta ficaria acesa numa página curta
    // que nem rola.
    medir();
    el.addEventListener("scroll", medir, { passive: true });
    return () => el.removeEventListener("scroll", medir);
  }, [alvo, caminho]);

  // Sem `useCallback`: o compilador do React memoiza sozinho, e a versão
  // manual daqui ele RECUSA — a função lê `alvo.current`, dependência que ele
  // infere e que a lista `[alvo]` não declara (nem poderia: `.current` não
  // dispara render). Memoização manual que faz o compilador desistir do
  // arquivo inteiro custa mais do que economiza.
  function subir() {
    // Respeita quem pediu menos movimento no sistema: rolagem suave de 4 mil
    // pixels é exatamente o tipo de animação que essa preferência existe pra
    // desligar.
    const suave = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    alvo.current?.scrollTo({ top: 0, behavior: suave ? "smooth" : "auto" });
  }

  return (
    <button
      onClick={subir}
      aria-label="voltar ao topo"
      title="voltar ao topo"
      // Fica MONTADA e some por opacidade, pra entrar e sair com transição em
      // vez de piscar. `pointer-events-none` junto: invisível que ainda recebe
      // clique é armadilha, e `aria-hidden` tira do leitor de tela o botão que
      // não está lá.
      aria-hidden={!visivel}
      tabIndex={visivel ? 0 : -1}
      className={`btn-icone absolute bottom-5 right-5 z-30 !rounded-full bg-surface/90
                  shadow-[var(--shadow-drawer)] backdrop-blur transition-all duration-200
                  ${visivel ? "opacity-100" : "pointer-events-none translate-y-1 opacity-0"}`}
    >
      <ArrowUp className="h-4 w-4" />
    </button>
  );
}
