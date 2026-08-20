"use client";

import { useCallback, useEffect, useState } from "react";
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
  MessageSquare,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  Rows3,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import { Marca, MarcaIcone } from "@/components/Marca";
import { MenuConta } from "@/components/MenuConta";
import { ConversaNaLista, Mesa, Usuario, apagarConversa, getConversas, getMe } from "@/lib/api";
import { Confirmar } from "@/components/Confirmar";

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
  const [recentes, setRecentes] = useState<ConversaNaLista[] | null>(null);
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [espiando, setEspiando] = useState(false);
  // A conversa esperando confirmação. Guarda o OBJETO e não um booleano pelo
  // mesmo motivo do cartão de mesa: o diálogo precisa dizer QUAL conversa vai
  // apagar, e "tem certeza?" sem nome é onde a pessoa apaga a errada.
  const [aApagar, setAApagar] = useState<ConversaNaLista | null>(null);
  const [apagando, setApagando] = useState(false);

  // "Recentes" são CONVERSAS de verdade (migração 014). Antes mostrava
  // simulados no lugar, porque o diálogo não era persistido — um rótulo
  // dizendo uma coisa e listando outra. Ordenadas por atividade: conversa
  // retomada ontem importa mais que uma aberta há um mês e abandonada.
  const carregarRecentes = useCallback(() => {
    getConversas()
      .then((c) => setRecentes(c.slice(0, 6)))
      .catch(() => setRecentes([]));
  }, []);

  useEffect(() => {
    carregarRecentes();
    getMe()
      .then(setUsuario)
      .catch(() => {});
  }, [carregarRecentes]);

  // A LISTA PRECISA SABER QUE UMA CONVERSA NASCEU. Relatado em uso: começar um
  // chat novo e ele não aparecer nos recentes. A causa é que a sidebar buscava
  // `/conversas` UMA vez, na montagem, e quem cria a conversa é o `POST
  // /perguntar` da página irmã — que fica em outra árvore de componentes.
  //
  // Canal é o mesmo `CustomEvent` que já leva "nova conversa" no sentido
  // contrário (sidebar -> página): não existe store nem contexto neste app, e
  // inventar um pra dois sinais seria infraestrutura maior que o problema.
  // Recarrega a lista inteira em vez de inserir o item na mão — o título e a
  // contagem de mensagens são calculados pelo servidor, e montar aqui uma
  // versão local deles é como as duas divergem.
  useEffect(() => {
    window.addEventListener("tutor:conversas-mudaram", carregarRecentes);
    return () => window.removeEventListener("tutor:conversas-mudaram", carregarRecentes);
  }, [carregarRecentes]);

  const aberta = drawer || !recolhida || espiando;
  const nome = nomeDoEmail(usuario?.email);

  async function apagar() {
    if (!aApagar || apagando) return;
    const alvo = aApagar;
    setApagando(true);
    try {
      await apagarConversa(alvo.id);
      // Tira da lista aqui e AVISA a página: se a conversa apagada é a que está
      // aberta, deixá-la na tela daria um chat que responde num histórico que
      // não existe mais — o próximo turno abriria conversa nova sem ninguém
      // pedir, e o aluno acharia que perdeu a mensagem que acabou de escrever.
      setRecentes((atual) => (atual ?? []).filter((c) => c.id !== alvo.id));
      window.dispatchEvent(
        new CustomEvent("tutor:conversa-apagada", { detail: { id: alvo.id } })
      );
      setAApagar(null);
    } catch {
      // Falhou: recarrega do servidor em vez de adivinhar o estado. Some o
      // diálogo, a lista volta a ser a verdade.
      setAApagar(null);
      carregarRecentes();
    } finally {
      setApagando(false);
    }
  }

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
      {/* Não é `<Link href="/tutor">`: estando JÁ no /tutor, o Next não
          remonta a rota pra ela mesma, e a conversa carregada continuaria
          na tela — "nova conversa" que não abre nada. Com conversa
          persistida (014) isso deixou de ser detalhe.

          O evento existe porque não há estado compartilhado no app (nem
          store, nem contexto): a sidebar precisa avisar uma página irmã, e
          um CustomEvent é o canal mais simples que não inventa
          infraestrutura pra um sinal só. */}
      <button
        onClick={() => {
          onFechar?.();
          if (pathname === "/tutor") {
            window.dispatchEvent(new CustomEvent("tutor:nova"));
          } else {
            router.push("/tutor");
          }
        }}
        className={aberta ? "btn-bloco" : "btn-bloco px-0"}
        aria-label="nova conversa com o tutor"
      >
        <Plus className="h-4 w-4 shrink-0" strokeWidth={2.6} />
        {aberta && <span>Nova conversa</span>}
      </button>

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
              {recentes.map((c) => (
                /* A lixeira é IRMÃ do link, não filha: botão dentro de âncora é
                   HTML inválido e o clique navegaria antes de apagar — mesma
                   armadilha do interruptor da biblioteca dentro do cartão de
                   mesa. Daí o wrapper `relative` e a lixeira posicionada por
                   cima da borda direita. */
                <div key={c.id} className="group relative">
                  <Link
                    href={`/tutor?c=${c.id}`}
                    onClick={(e) => {
                      onFechar?.();
                      // ESTANDO JÁ NO /tutor, o Link não resolve: o Next não
                      // remonta a rota pra ela mesma, e o efeito que lê `?c=`
                      // depende da montagem. O clique navegava (o log mostrava
                      // `GET /tutor?c=413 200`) e a conversa não voltava.
                      // Mesmo padrão do "Nova conversa" logo acima.
                      if (pathname === "/tutor") {
                        e.preventDefault();
                        window.dispatchEvent(
                          new CustomEvent("tutor:abrir-conversa", { detail: { id: c.id } })
                        );
                      }
                    }}
                    title={c.mesa_nome ? `conversa na mesa ${c.mesa_nome}` : undefined}
                    className="flex items-center justify-between gap-2 rounded-[10px] px-2.5 py-1.5 text-[13px]
                               text-subtle transition-colors hover:bg-surface-hover hover:text-foreground"
                  >
                    <span className="truncate">{c.titulo}</span>
                    {/* A contagem SOME no hover pra a lixeira ocupar o lugar
                        dela, em vez de as duas disputarem a mesma borda e
                        empurrarem o título (que é `truncate` e encurtaria a
                        cada passada de mouse). */}
                    <span className="mono-num shrink-0 text-[11.5px] opacity-70 group-hover:opacity-0">
                      {c.mensagens}
                    </span>
                  </Link>
                  <button
                    onClick={() => setAApagar(c)}
                    title={`Apagar "${c.titulo}"`}
                    aria-label={`apagar conversa ${c.titulo}`}
                    /* `focus-visible` além de `group-hover` porque quem navega
                       por teclado nunca dispara hover — sem isso a ação
                       simplesmente não existiria pra essa pessoa. */
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-subtle opacity-0
                               transition-opacity hover:text-danger focus-visible:opacity-100
                               group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
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
          /* O ⋮ ANTES deslogava direto: ícone de "mais opções" executando a
             ação mais destrutiva da tela, sem menu e sem aviso. Agora ele
             abre o mesmo menu do lobby — a pessoa clica pra ver o que tem e
             vê o que tem. */
          <MenuConta usuario={usuario} ancora="acima">
            <span className="flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-surface-hover">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface-hover text-[12px] font-semibold text-accent-text">
                {nome[0]}
              </span>
              <span className="min-w-0 flex-1 text-left">
                <span className="block truncate text-[13.5px] font-semibold">{nome}</span>
                <span className="block truncate font-mono text-[11px] text-subtle">
                  {usuario?.email ?? "—"}
                </span>
              </span>
              <MoreVertical className="h-4 w-4 shrink-0 text-subtle" />
            </span>
          </MenuConta>
        ) : (
          /* Recolhida também abre o MENU, não desloga direto: "trocar de
             mesa" é a opção mais usada daqui, e ela sumia justamente no
             estado em que a nav ocupa menos espaço. */
          <MenuConta usuario={usuario} ancora="acima">
            <span className="sidebar-link w-full justify-center" aria-label="conta">
              <span className="flex h-7 w-7 items-center justify-center rounded-full border border-line-strong bg-surface-hover text-[11px] font-semibold text-accent-text">
                {nome[0]}
              </span>
            </span>
          </MenuConta>
        )}
      </div>

      <Confirmar
        aberto={aApagar !== null}
        titulo="Apagar esta conversa?"
        descricao={
          <>
            <span className="font-medium text-foreground">{aApagar?.titulo}</span> e as{" "}
            {aApagar?.mensagens} mensagens dela saem do histórico. Não tem como desfazer.
          </>
        }
        /* O que NÃO acontece é a parte que tira o medo de clicar — e aqui é
           verdade estrutural, não conforto: `progresso`, `tentativa` e
           `erro_caderno` não têm vínculo com `conversa` (decisão da 014, a
           conversa é etiquetada pela mesa com SET NULL). O SM-2 não sente. */
        detalhe="As questões que você respondeu e o seu progresso não são afetados."
        rotuloConfirmar={apagando ? "Apagando…" : "Apagar conversa"}
        destrutivo
        onConfirmar={apagar}
        onCancelar={() => setAApagar(null)}
      />
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
