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

function ItemNav({
  href,
  label,
  Icone,
  ativo,
  mostrarLabel,
}: {
  href: string;
  label: string;
  Icone: LucideIcon;
  ativo: boolean;
  mostrarLabel: boolean;
}) {
  return (
    <Link href={href} className={ativo ? "sidebar-link-ativo" : "sidebar-link"}>
      <Icone className="h-5 w-5 shrink-0" strokeWidth={1.75} />
      {mostrarLabel && <span className="whitespace-nowrap">{label}</span>}
    </Link>
  );
}

type Props = {
  recolhida: boolean;
  onAlternar: () => void;
};

const LARGURA_RECOLHIDA = "w-16";
const LARGURA_ABERTA = "w-64";

/**
 * Recolhida = só ícone, MAS passar o mouse expande a sidebar inteira por
 * cima do conteúdo (overlay, sem empurrar o layout) até o mouse saltar
 * pra fora — o botão de alternar (`onAlternar`) continua fixando o estado
 * permanente; o hover é só um "espiar" temporário. Dois elementos: o
 * placeholder reserva o espaço real no layout (nunca muda de largura
 * sozinho), a <aside> de dentro é quem visualmente cresce.
 */
export function Sidebar({ recolhida, onAlternar }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [recentes, setRecentes] = useState<HistoricoSimulado[] | null>(null);
  const [espiando, setEspiando] = useState(false);

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

  const aberta = !recolhida || espiando;

  return (
    <div className={`relative h-full shrink-0 ${recolhida ? LARGURA_RECOLHIDA : LARGURA_ABERTA}`}>
      <aside
        onMouseEnter={() => recolhida && setEspiando(true)}
        onMouseLeave={() => setEspiando(false)}
        className={`absolute inset-y-0 left-0 z-30 flex h-full flex-col border-r border-line bg-surface
                    transition-[width] duration-150 ${aberta ? `${LARGURA_ABERTA} shadow-xl` : LARGURA_RECOLHIDA}`}
      >
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          {aberta && (
            <Link href="/" className="text-sm font-bold tracking-tight text-accent">
              FerrarIA
            </Link>
          )}
          <button
            onClick={onAlternar}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
          >
            {recolhida ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3">
          {ITENS.map((item) => (
            <ItemNav
              key={item.href}
              href={item.href}
              label={item.label}
              Icone={item.Icone}
              ativo={pathname === item.href}
              mostrarLabel={aberta}
            />
          ))}

          {aberta && recentes && recentes.length > 0 && (
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
          <button onClick={sair} className={aberta ? "sidebar-link w-full" : "sidebar-link w-full justify-center"}>
            <LogOut className="h-5 w-5 shrink-0" strokeWidth={1.75} />
            {aberta && <span>sair</span>}
          </button>
        </div>
      </aside>
    </div>
  );
}
