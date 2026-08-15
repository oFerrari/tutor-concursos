"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LayoutGrid, LogOut } from "lucide-react";
import { Usuario, limparToken } from "@/lib/api";

/**
 * O menu da conta — um só, usado pelo cabeçalho de /mesas e pelo rodapé da
 * sidebar.
 *
 * Existia em dois lugares com comportamentos DIFERENTES, e o da sidebar
 * estava errado: um ícone de "mais opções" (⋮) que deslogava na hora, sem
 * menu e sem aviso. Ícone de três pontos promete escolha; executar a ação
 * mais destrutiva da tela sob ele é a pior forma de surpresa — a pessoa
 * clica pra ver o que tem e perde a sessão.
 *
 * Duas cópias de um menu é como elas divergem; foi exatamente o que
 * aconteceu aqui (uma virou dropdown completo, a outra virou botão de
 * logout disfarçado). Mesma lição de `<Kpis>` e de `mesa.filtro`.
 *
 * `ancora` inverte a origem: no topo o menu desce, no rodapé da sidebar ele
 * sobe — senão abriria pra fora da tela.
 */
export function MenuConta({
  usuario,
  ancora = "abaixo",
  children,
}: {
  usuario: Usuario | null;
  ancora?: "abaixo" | "acima";
  /** O gatilho. Recebe o clique daqui — quem desenha o botão é a tela, que
   *  sabe se ele é uma pílula no topo ou uma linha no rodapé. */
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  // Esc fecha, como em qualquer camada sobreposta do app (o mesmo atalho
  // que sai do modo foco e fecha os drawers).
  useEffect(() => {
    if (!aberto) return;
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") setAberto(false);
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [aberto]);

  const posicao =
    ancora === "acima" ? "bottom-[calc(100%+8px)]" : "top-[calc(100%+8px)]";

  return (
    <div className="relative" ref={caixa}>
      <button
        onClick={() => setAberto((a) => !a)}
        aria-haspopup="menu"
        aria-expanded={aberto}
        className="block w-full text-left"
      >
        {children}
      </button>

      {aberto && (
        <>
          {/* Captura o clique fora. `fixed inset-0` em vez de listener no
              document: o overlay some junto com o menu, sem risco de deixar
              handler pendurado se o componente desmontar antes. */}
          <div onClick={() => setAberto(false)} className="fixed inset-0 z-[45]" />
          <div
            role="menu"
            className={`absolute right-0 ${posicao} z-[46] w-[232px] rounded-[14px] border border-line-strong bg-surface p-1.5 shadow-[var(--shadow-drawer)]`}
          >
            <div className="mb-1.5 border-b border-line-soft px-3 pb-3 pt-2.5">
              <p className="truncate font-mono text-[11px] text-subtle">
                {usuario?.email ?? "—"}
              </p>
            </div>

            {/* "Meu edital" e "Meus materiais" saíram daqui — duplicavam
                itens que já estão na sidebar, um clique acima disto. Menu
                de conta é conta (trocar mesa, sair), não navegação. */}
            <Link href="/mesas" onClick={() => setAberto(false)} className="item-menu">
              <LayoutGrid className="h-[15px] w-[15px]" />
              Trocar de mesa
            </Link>

            <div className="mx-1 my-1.5 h-px bg-line-soft" />
            <button
              onClick={() => {
                limparToken();
                router.push("/login");
              }}
              className="item-menu !text-danger"
            >
              <LogOut className="h-[15px] w-[15px]" />
              Sair da conta
            </button>
          </div>
        </>
      )}
    </div>
  );
}
