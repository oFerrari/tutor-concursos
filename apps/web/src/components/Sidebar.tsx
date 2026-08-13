"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  BarChart3,
  CalendarClock,
  ClipboardCheck,
  Home,
  LogOut,
  MessageCircleQuestion,
  PanelLeftClose,
  PanelLeftOpen,
  Target,
  Rows3,
  type LucideIcon,
} from "lucide-react";
import { HistoricoSimulado, getSimulados, limparToken } from "@/lib/api";

const ITENS = [
  { href: "/", label: "início", Icone: Home },
  { href: "/fila", label: "fila", Icone: Rows3 },
  { href: "/desafio", label: "desafio", Icone: Target },
  { href: "/erros", label: "erros", Icone: AlertTriangle },
  { href: "/simulado", label: "simulado", Icone: ClipboardCheck },
  { href: "/stats", label: "desempenho", Icone: BarChart3 },
  { href: "/perguntar", label: "perguntar", Icone: MessageCircleQuestion },
  { href: "/meta", label: "meta", Icone: CalendarClock },
];

function formatarData(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

/**
 * Tooltip próprio, não o `title` nativo do navegador — o nativo tem
 * atraso (~1s) e visual fora do nosso controle. Só existe quando a
 * sidebar está recolhida (com texto visível ao lado do ícone, a etiqueta
 * já está na tela, tooltip seria redundante). `group-hover` com transição
 * rápida (100ms) é o que dá a sensação de "aparece na hora".
 */
function Etiqueta({ texto }: { texto: string }) {
  return (
    <span
      className="pointer-events-none absolute left-full top-1/2 z-20 ml-3 -translate-y-1/2 whitespace-nowrap
                 rounded-md bg-foreground px-2.5 py-1.5 text-xs font-medium text-background opacity-0
                 shadow-md transition-opacity duration-100 group-hover:opacity-100"
    >
      {texto}
    </span>
  );
}

function ItemNav({
  href,
  label,
  Icone,
  ativo,
  recolhida,
}: {
  href: string;
  label: string;
  Icone: LucideIcon;
  ativo: boolean;
  recolhida: boolean;
}) {
  return (
    <div className="group relative">
      <Link href={href} className={ativo ? "sidebar-link-ativo" : "sidebar-link"}>
        <Icone className="h-5 w-5 shrink-0" strokeWidth={1.75} />
        {!recolhida && <span>{label}</span>}
      </Link>
      {recolhida && <Etiqueta texto={label} />}
    </div>
  );
}

type Props = {
  recolhida: boolean;
  onAlternar: () => void;
};

export function Sidebar({ recolhida, onAlternar }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [recentes, setRecentes] = useState<HistoricoSimulado[] | null>(null);

  useEffect(() => {
    // "Recentes" mostra simulados de verdade (têm data, são sessão
    // discreta) — não fingimos histórico de conversa tipo Claude, porque
    // o diálogo da fila não é persistido como sessão própria.
    getSimulados()
      .then((s) => setRecentes(s.slice(0, 5)))
      .catch(() => setRecentes([]));
  }, []);

  function sair() {
    limparToken();
    router.push("/login");
  }

  return (
    <aside
      className={`flex h-full flex-col border-r border-line bg-surface transition-[width] duration-200 ${
        recolhida ? "w-16" : "w-64"
      }`}
    >
      <div className="flex items-center justify-between gap-2 px-4 py-4">
        {!recolhida && (
          <Link href="/" className="text-sm font-bold tracking-tight text-accent">
            FerrarIA
          </Link>
        )}
        <div className="group relative">
          <button
            onClick={onAlternar}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
          >
            {recolhida ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
          </button>
          {recolhida && <Etiqueta texto="expandir" />}
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3">
        {ITENS.map((item) => (
          <ItemNav
            key={item.href}
            href={item.href}
            label={item.label}
            Icone={item.Icone}
            ativo={pathname === item.href}
            recolhida={recolhida}
          />
        ))}

        {!recolhida && recentes && recentes.length > 0 && (
          <div className="mt-6">
            <p className="px-3 text-xs font-medium uppercase tracking-wide text-muted">recentes</p>
            <div className="mt-1 space-y-0.5">
              {recentes.map((s) => (
                <Link
                  key={s.id}
                  href="/simulado"
                  className="flex items-center justify-between rounded-lg px-3 py-1.5 text-xs text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
                >
                  <span>simulado · {formatarData(s.criado_em)}</span>
                  <span className="tabular-nums">{s.nota_pct ?? 0}%</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </nav>

      <div className="border-t border-line px-3 py-3">
        <div className="group relative">
          <button onClick={sair} className={recolhida ? "sidebar-link w-full justify-center" : "sidebar-link w-full"}>
            <LogOut className="h-5 w-5 shrink-0" strokeWidth={1.75} />
            {!recolhida && <span>sair</span>}
          </button>
          {recolhida && <Etiqueta texto="sair" />}
        </div>
      </div>
    </aside>
  );
}
