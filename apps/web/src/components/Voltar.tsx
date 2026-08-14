"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

/**
 * Saída das telas em que você ENTRA a partir de outra: curadoria de
 * edital, responder questão. Sem isso a única saída é a nav lateral, que
 * troca de assunto em vez de desfazer o passo — e em tela estreita, onde a
 * nav é drawer, não há saída nenhuma.
 *
 * `href` quando existe um destino certo (voltar da questão é voltar pra
 * fila, sempre); `router.back()` quando a origem varia — a curadoria pode
 * ter vindo do onboarding ou do painel, e mandar pro lugar errado é pior
 * que devolver de onde veio.
 */
export function Voltar({ href, rotulo = "voltar" }: { href?: string; rotulo?: string }) {
  const router = useRouter();
  return (
    <button
      onClick={() => (href ? router.push(href) : router.back())}
      className="mb-5 inline-flex items-center gap-1.5 text-[13px] text-subtle transition-colors hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      {rotulo}
    </button>
  );
}
