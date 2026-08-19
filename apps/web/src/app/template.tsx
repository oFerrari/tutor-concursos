"use client";

import { usePathname } from "next/navigation";

/**
 * Reexecuta a CADA troca de rota — diferente de `layout.tsx`, que persiste
 * entre navegações. É o que dá a cada página uma entrada com transição em
 * vez de trocar seco: sair do Panorama e cair no /tutor (ex.: `Enter` no
 * composer) agora sobe e esmaece em vez de cortar duro.
 *
 * `key={pathname}` é o que FORÇA a remontagem de verdade. Sem ele, o
 * `template.tsx` sozinho nem sempre garante que o React descarte o nó do
 * DOM e crie outro — se o mesmo elemento sobrevive entre navegações, a
 * animação CSS não tem "entrada" nova pra tocar (ela só dispara quando o
 * elemento é inserido pela primeira vez). Trocar a `key` a cada pathname
 * obriga o React a tratar como componente novo, sempre — é o que faz a
 * animação disparar TODA vez, sem depender de garantia implícita do Next.
 *
 * Só o MIOLO roteado anima — sidebar e Raio-X ficam parados, porque
 * `AppShell` (em layout.tsx) os renderiza em volta de `{children}`, não
 * dentro dele; este template só embrulha o que troca.
 *
 * CSS puro (`@keyframes` em globals.css), não a View Transitions API do
 * React/Next (ainda instável nesta versão, ver `node_modules/next` — ver
 * AGENTS.md do frontend) nem Framer Motion: uma animação de entrada simples
 * é robusta o bastante pro efeito pedido sem depender de API experimental
 * pra polimento visual. Sem transição de SAÍDA — a página antiga só
 * desmonta; ir atrás disso é sair do território de CSS puro.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="animar-entrada-pagina h-full">
      {children}
    </div>
  );
}
