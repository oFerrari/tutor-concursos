"use client";

import { usePathname } from "next/navigation";
import { Focus, Menu } from "lucide-react";
import { OFENSIVA } from "@/mock/prototipo";

/**
 * Cabeçalho fino do protótipo: rastro (breadcrumb) mono à esquerda,
 * controles de chrome à direita. NÃO é navegação — navegar continua sendo
 * papel exclusivo da sidebar (decisão antiga: "não coloque navegação
 * excessiva no topo"). O que mora aqui é só (a) onde eu estou e (b) o que
 * eu quero ver ou esconder.
 */

// Mapa explícito em vez de derivar do pathname com replace/capitalize: rota
// dinâmica (/questao/[id]) e rótulo que não é o slug (/stats → "desempenho")
// quebram qualquer derivação esperta, e um rastro errado é pior que nenhum.
const RASTRO: Record<string, string> = {
  "/": "panorama",
  "/tutor": "tutor",
  "/desafio": "sessão de estudo",
  "/fila": "fila do dia",
  "/erros": "caderno de erros",
  "/simulado": "montar simulado",
  "/stats": "desempenho",
  "/meta": "meu edital",
  "/materiais": "minha biblioteca",
};

function rastroDe(pathname: string): string {
  if (RASTRO[pathname]) return RASTRO[pathname];
  if (pathname.startsWith("/questao/")) return "fila do dia · questão";
  return pathname.replace(/^\//, "");
}

type Props = {
  railAberto: boolean;
  railDisponivel: boolean;
  onAlternarRail: () => void;
  onEntrarFoco: () => void;
  onAbrirMenu: () => void;
};

export function Header({ railAberto, railDisponivel, onAlternarRail, onEntrarFoco, onAbrirMenu }: Props) {
  const pathname = usePathname();

  return (
    <header className="flex shrink-0 items-center justify-between gap-2.5 border-b border-line-soft px-5 py-3">
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <button onClick={onAbrirMenu} className="btn-icone lg:hidden" aria-label="abrir menu">
          <Menu className="h-4 w-4" />
        </button>
        <p className="rotulo-lg min-w-0 truncate">ferraria / {rastroDe(pathname)}</p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {/* Vitrine (ver mock/prototipo.ts): não há sequência de dias no
            schema. Está aqui porque a decisão foi manter o protótipo. */}
        <span className="chip cursor-default font-mono text-[12px]">🔥 {OFENSIVA.dias}</span>

        {railDisponivel && (
          <button
            onClick={onAlternarRail}
            className="chip font-mono text-[12px]"
            aria-label={railAberto ? "esconder raio-x" : "mostrar raio-x"}
          >
            Raio-X {railAberto && <span className="text-subtle">✕</span>}
          </button>
        )}

        <button onClick={onEntrarFoco} className="chip font-mono text-[12px]" aria-label="entrar no modo foco">
          <Focus className="h-3.5 w-3.5" />
          Foco
        </button>
      </div>
    </header>
  );
}
