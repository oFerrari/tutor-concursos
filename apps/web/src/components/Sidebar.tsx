"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  BarChart3,
  CalendarClock,
  ClipboardCheck,
  LogOut,
  MessageCircleQuestion,
  PanelLeftClose,
  PanelLeftOpen,
  Target,
  Rows3,
} from "lucide-react";
import { HistoricoSimulado, getSimulados, limparToken } from "@/lib/api";

const ITENS = [
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
        <button
          onClick={onAlternar}
          className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
          title={recolhida ? "expandir" : "recolher"}
        >
          {recolhida ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3">
        {ITENS.map((item) => {
          const ativo = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={recolhida ? item.label : undefined}
              className={
                ativo
                  ? "flex items-center gap-3 rounded-r-md border-l-2 border-accent bg-accent-soft px-3 py-2 text-sm font-medium text-accent"
                  : "sidebar-link"
              }
            >
              <item.Icone className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              {!recolhida && <span>{item.label}</span>}
            </Link>
          );
        })}

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
        <button onClick={sair} className={recolhida ? "sidebar-link w-full justify-center" : "sidebar-link w-full"}>
          <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.75} />
          {!recolhida && <span>sair</span>}
        </button>
      </div>
    </aside>
  );
}
