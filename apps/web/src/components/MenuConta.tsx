"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { LayoutGrid, LogOut, SlidersHorizontal, Trash2 } from "lucide-react";
import { Usuario } from "@/lib/api";
import { sair } from "@/lib/cache";
import { ExcluirConta } from "@/components/ExcluirConta";

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
 *
 * Dois itens dependem de ONDE o menu abre, por `usePathname()` — não por
 * prop, porque as duas cópias já divergiram uma vez e a rota é o dado que
 * as duas instâncias já enxergam sozinhas:
 *   - "Trocar de mesa" some em `/mesas`: o link leva pra lá, e mostrar "vá
 *     pra onde você já está" é a nav sendo burra sobre o próprio estado.
 *   - "Excluir minha conta" só aparece em `/mesas`: é a ação mais grave do
 *     menu, e `/mesas` é justamente a tela SEM sessão de estudo em curso —
 *     ninguém deveria topar com ela no meio de uma fila ou de um simulado.
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
  const pathname = usePathname();
  const emMesas = pathname === "/mesas";
  const [aberto, setAberto] = useState(false);
  // Diálogo próprio (pede senha) — não é o mesmo menu dropdown, então tem
  // estado separado e sobrevive ao menu fechar (clique fora do menu não
  // pode fechar o diálogo de exclusão por baixo dele).
  const [excluindo, setExcluindo] = useState(false);
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
                de conta é conta (trocar mesa, preferências, sair) —
                "trocar de mesa" só entra fora de `/mesas`, onde ela é
                atalho de verdade e não "vá pra onde você já está". */}
            {!emMesas && (
              <Link href="/mesas" onClick={() => setAberto(false)} className="item-menu">
                <LayoutGrid className="h-[15px] w-[15px]" />
                Trocar de mesa
              </Link>
            )}

            {/* As três respostas da entrevista (horas/nível/turno,
                migração 015) — só se gravava no dia do onboarding; agora
                tem pra onde voltar quando a rotina muda. */}
            <Link href="/perfil" onClick={() => setAberto(false)} className="item-menu">
              <SlidersHorizontal className="h-[15px] w-[15px]" />
              Preferências de estudo
            </Link>

            <div className="mx-1 my-1.5 h-px bg-line-soft" />
            <button
              onClick={() => {
                sair();
                router.push("/login");
              }}
              className="item-menu !text-danger"
            >
              <LogOut className="h-[15px] w-[15px]" />
              Sair da conta
            </button>

            {/* Só em `/mesas`, de propósito: é a ação mais grave do menu, e
                `/mesas` é a tela SEM sessão de estudo em curso — ninguém
                deveria topar com "excluir conta" no meio de uma fila ou de
                um simulado. Separada de "sair" por um traço próprio (não o
                mesmo agrupamento): um desloga, o outro apaga tudo, e
                parecer a mesma categoria de ação é o tipo de vizinhança que
                faz gente clicar errado. Antes disto, a única saída era
                `docker exec psql` na mão (conta de teste ou gente que só
                quer sair de verdade). */}
            {emMesas && (
              <>
                <div className="mx-1 my-1.5 h-px bg-line-soft" />
                <button
                  onClick={() => {
                    setAberto(false);
                    setExcluindo(true);
                  }}
                  className="item-menu !text-danger"
                >
                  <Trash2 className="h-[15px] w-[15px]" />
                  Excluir minha conta
                </button>
              </>
            )}
          </div>
        </>
      )}

      {excluindo && (
        <ExcluirConta
          onCancelar={() => setExcluindo(false)}
          onExcluida={() => {
            sair();
            router.push("/login");
          }}
        />
      )}
    </div>
  );
}
