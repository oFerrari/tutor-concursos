"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Book,
  ChevronsUpDown,
  ClipboardList,
  FileText,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  Rows3,
  X,
  type LucideIcon,
} from "lucide-react";
import { Marca, MarcaIcone } from "@/components/Marca";
import { HistoricoSimulado, Mesa, Usuario, getMe, getSimulados, limparToken } from "@/lib/api";

// Ordem e rótulos do protótipo. "Fila do dia" não existe lá — mas existe
// como rota real e funcionando aqui, e tirar do menu uma tela que funciona
// pra ficar igual ao mockup seria deixar o desenho mandar no produto.
const ITENS = [
  { href: "/", label: "Panorama", Icone: LayoutDashboard },
  { href: "/tutor", label: "Tutor", Icone: MessageSquare },
  { href: "/desafio", label: "Sessão de estudo", Icone: Play },
  { href: "/fila", label: "Fila do dia", Icone: Rows3 },
  { href: "/erros", label: "Caderno de erros", Icone: Book },
  { href: "/simulado", label: "Montar simulado", Icone: ClipboardList },
  { href: "/stats", label: "Desempenho", Icone: BarChart3 },
  { href: "/meta", label: "Meu edital", Icone: FileText },
  { href: "/materiais", label: "Meus materiais", Icone: FolderOpen },
];

function formatarData(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

function nomeDoEmail(email: string | undefined): string {
  if (!email) return "conta";
  const bruto = (email.split("@")[0] ?? "").split(/[._-]/)[0] ?? "";
  return bruto ? bruto.charAt(0).toUpperCase() + bruto.slice(1).toLowerCase() : "conta";
}

function ItemNav({
  href,
  label,
  Icone,
  ativo,
  mostrarLabel,
  onNavegar,
}: {
  href: string;
  label: string;
  Icone: LucideIcon;
  ativo: boolean;
  mostrarLabel: boolean;
  onNavegar?: () => void;
}) {
  return (
    <Link href={href} onClick={onNavegar} className={ativo ? "sidebar-link-ativo" : "sidebar-link"}>
      <Icone className="h-4 w-4 shrink-0 transition-colors" strokeWidth={2.2} />
      {mostrarLabel && <span className="truncate whitespace-nowrap">{label}</span>}
    </Link>
  );
}

type Props = {
  recolhida: boolean;
  onAlternar: () => void;
  /** Mesa em que a API está atendendo — resolvida uma vez no AppShell
   *  (GET /mesa), não aqui: quem decide o fallback de "sem header, usa a
   *  padrão" é o servidor, e uma segunda cópia dessa regra no cliente
   *  faria a nav afirmar um nome enquanto a fila responde por outra mesa. */
  mesa: Mesa | null;
  /** Drawer = sobreposta em tela estreita; coluna = fixa no grid. */
  drawer?: boolean;
  onFechar?: () => void;
};

const LARGURA_RECOLHIDA = "w-16";
const LARGURA_ABERTA = "w-[258px]";

/**
 * Recolhida = só ícone, MAS passar o mouse expande a sidebar inteira por
 * cima do conteúdo (overlay, sem empurrar o layout) até o mouse sair — o
 * botão de alternar fixa o estado permanente; o hover é só um "espiar".
 * Em tela estreita ela vira drawer (`drawer`), controlado pelo botão de
 * menu do cabeçalho.
 */
export function Sidebar({ recolhida, onAlternar, mesa, drawer = false, onFechar }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [recentes, setRecentes] = useState<HistoricoSimulado[] | null>(null);
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [espiando, setEspiando] = useState(false);

  useEffect(() => {
    // "Recentes" mostra simulados de verdade (têm data, são sessão
    // discreta) — não fingimos histórico de conversa tipo Claude, porque
    // o diálogo da fila não é persistido como sessão própria.
    getSimulados()
      .then((s) => setRecentes(s.slice(0, 5)))
      .catch(() => setRecentes([]));
    getMe()
      .then(setUsuario)
      .catch(() => {});
  }, []);

  function sair() {
    limparToken();
    router.push("/login");
  }

  const aberta = drawer || !recolhida || espiando;
  const nome = nomeDoEmail(usuario?.email);

  const conteudo = (
    <>
      {/* --------------------------------------------------------- marca */}
      <div className="flex items-center justify-between gap-2 px-1.5">
        <Link href="/" onClick={onFechar}>
          {aberta ? <Marca /> : <MarcaIcone />}
        </Link>
        {aberta &&
          (drawer ? (
            <button onClick={onFechar} className="btn-icone h-8 w-8" aria-label="fechar menu">
              <X className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={onAlternar}
              aria-label={recolhida ? "fixar sidebar aberta" : "recolher sidebar"}
              className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-hover hover:text-foreground"
            >
              {recolhida ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
            </button>
          ))}
      </div>

      {/* ------------------------------------------------ ação primária */}
      <Link
        href="/tutor"
        onClick={onFechar}
        className={aberta ? "btn-bloco" : "btn-bloco px-0"}
        aria-label="nova conversa com o tutor"
      >
        <Plus className="h-4 w-4 shrink-0" strokeWidth={2.6} />
        {aberta && <span>Nova conversa</span>}
      </Link>

      {/* ----------------------------------------------------- navegação */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto">
        {ITENS.map((item) => (
          <ItemNav
            key={item.href}
            href={item.href}
            label={item.label}
            Icone={item.Icone}
            ativo={pathname === item.href}
            mostrarLabel={aberta}
            onNavegar={onFechar}
          />
        ))}

        {/* ------------------------------------------- mesa de estudo */}
        {/* O seletor leva pro lobby, que é onde se troca de mesa. O
            subtítulo diz se ela recorta alguma coisa: mesa sem edital
            mostra o acervo inteiro, e é melhor a nav dizer isso do que a
            pessoa estranhar Direito Penal num concurso que não cobra. */}
        {aberta && (
          <Link
            href="/mesas"
            onClick={onFechar}
            className="mt-5 flex items-center gap-2.5 rounded-xl border border-line bg-surface px-3 py-2.5 transition-colors hover:border-line-stronger hover:bg-surface-raised"
          >
            <span className="min-w-0 flex-1">
              <span className="rotulo flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                mesa de estudo
              </span>
              <span className="mt-0.5 block truncate text-[13.5px]">
                {mesa?.nome ?? "—"}
              </span>
              {mesa && !mesa.disciplinas && (
                <span className="mt-0.5 block truncate text-[11.5px] text-subtle">
                  sem edital · acervo inteiro
                </span>
              )}
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-subtle" />
          </Link>
        )}

        {aberta && recentes && recentes.length > 0 && (
          <div className="pt-5">
            <p className="rotulo px-2.5 pb-2">recentes</p>
            <div className="space-y-0.5">
              {recentes.map((s) => (
                <Link
                  key={s.id}
                  href="/simulado"
                  onClick={onFechar}
                  className="flex items-center justify-between gap-2 rounded-[10px] px-2.5 py-1.5 text-[13px]
                             text-subtle transition-colors hover:bg-surface-hover hover:text-foreground"
                >
                  <span className="truncate">simulado · {formatarData(s.criado_em)}</span>
                  <span className="mono-num shrink-0 text-[12px]">{s.nota_pct ?? 0}%</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </nav>

      {/* ---------------------------------------------------- rodapé */}
      {/* O protótipo mostra "Plano Pro · renova 03/09". Não existe
          assinatura no schema, então o segundo nível mostra o e-mail REAL
          do `/me` — mesmo lugar, informação que existe. */}
      <div className="border-t border-line-soft pt-3">
        {aberta ? (
          <div className="flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-surface-hover">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface-hover text-[12px] font-semibold text-accent-text">
              {nome[0]}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13.5px] font-semibold">{nome}</span>
              <span className="block truncate font-mono text-[11px] text-subtle">
                {usuario?.email ?? "—"}
              </span>
            </span>
            <button onClick={sair} className="shrink-0 text-subtle transition-colors hover:text-danger" aria-label="sair da conta">
              <MoreVertical className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button onClick={sair} className="sidebar-link w-full justify-center" aria-label="sair da conta">
            <LogOut className="h-4 w-4 shrink-0" strokeWidth={2.2} />
          </button>
        )}
      </div>
    </>
  );

  if (drawer) {
    return (
      <aside className="chrome fixed inset-y-0 left-0 z-40 flex w-[258px] flex-col gap-4 overflow-y-auto border-r border-line-soft px-3.5 py-4 shadow-[0_0_60px_rgba(0,0,0,.7)]">
        {conteudo}
      </aside>
    );
  }

  return (
    <div className={`relative h-full shrink-0 ${recolhida ? LARGURA_RECOLHIDA : LARGURA_ABERTA}`}>
      <aside
        onMouseEnter={() => recolhida && setEspiando(true)}
        onMouseLeave={() => setEspiando(false)}
        className={`chrome absolute inset-y-0 left-0 z-30 flex h-full flex-col gap-4 border-r border-line-soft
                    px-3.5 py-4 transition-[width] duration-150
                    ${aberta ? `${LARGURA_ABERTA} ${espiando ? "shadow-[var(--shadow-drawer)]" : ""}` : LARGURA_RECOLHIDA}`}
      >
        {conteudo}
      </aside>
    </div>
  );
}
