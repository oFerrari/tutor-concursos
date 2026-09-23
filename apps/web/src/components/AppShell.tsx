"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Header } from "@/components/Header";
import { RaioX } from "@/components/RaioX";
import { VoltarAoTopo } from "@/components/VoltarAoTopo";
import { Sidebar } from "@/components/Sidebar";
import {
  Carga,
  Desempenho,
  EditalAtual,
  ErroCaderno,
  Mesa,
  Meta,
  getCarga,
  getEdital,
  getErros,
  getMesaAtual,
  getMesas,
  getMeta,
  getStats,
  getToken,
} from "@/lib/api";

const CHAVE_RECOLHIDA = "tutor_sidebar_recolhida";

// Telas de entrada — sem casca nenhuma. No protótipo elas são o "lobby":
// tela cheia, sem nav, sem cabeçalho, sem rail, porque ainda não há sessão
// de estudo pra navegar.
const SEM_CASCA = new Set(["/login", "/cadastro", "/mesas", "/onboarding"]);

// O rail só faz sentido onde há contexto pra ele comentar. No protótipo é
// exatamente isto: panorama e tutor. Numa tela de responder questão ele
// seria distração — e o modo foco existe justamente pra tirar tudo.
const COM_RAIL = new Set(["/", "/tutor"]);

/**
 * Casca de três colunas do protótipo: nav à esquerda, conteúdo no meio,
 * Raio-X à direita, com um cabeçalho fino por cima do conteúdo.
 *
 * Os dados do Raio-X (e o contador do cabeçalho) são buscados AQUI, uma
 * vez, e descem por prop — não em cada painel. Se cada bloco do rail
 * buscasse o próprio dado, trocar de rota dispararia cinco requisições
 * repetidas por render, e o número do cabeçalho poderia divergir do número
 * do painel logo abaixo dele.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const semCasca = SEM_CASCA.has(pathname);
  const railDisponivel = COM_RAIL.has(pathname);

  const [recolhida, setRecolhida] = useState(false);
  const [montado, setMontado] = useState(false);
  const [estreito, setEstreito] = useState(false);

  const [foco, setFoco] = useState(false);
  const [menuAberto, setMenuAberto] = useState(false);
  const [railAberto, setRailAberto] = useState(false);

  const [carga, setCarga] = useState<Carga | null>(null);
  const [mesa, setMesa] = useState<Mesa | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [edital, setEdital] = useState<EditalAtual | null>(null);
  const [desempenho, setDesempenho] = useState<Desempenho[] | null>(null);
  const [erros, setErros] = useState<ErroCaderno[] | null>(null);

  // Medir a janela só depois de montar: `window` não existe no servidor, e
  // gatear a renderização até o efeito rodar daria tela branca. O rail
  // também só entra depois disto — em tela estreita ele é drawer, e um
  // drawer aberto no primeiro paint seria pior que um rail que aparece
  // 16ms depois.
  useEffect(() => {
    function medir() {
      setEstreito(window.innerWidth < 1280);
    }
    medir();
    // O disable cobre os três setState abaixo (a regra reporta uma vez por
    // efeito): medir a janela EXIGE o browser, e o valor certo só existe
    // depois do mount — é o caso legítimo que a regra não distingue.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRecolhida(window.localStorage.getItem(CHAVE_RECOLHIDA) === "1");
    setRailAberto(window.innerWidth >= 1280);
    setMontado(true);
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, []);

  // Esc sai do foco e fecha qualquer drawer — mesmo atalho do protótipo.
  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setFoco(false);
      setMenuAberto(false);
      if (window.innerWidth < 1280) setRailAberto(false);
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  const carregar = useCallback(() => {
    if (!getToken()) return;
    // Falhar aqui não pode derrubar a tela: o rail é contexto, não
    // conteúdo. Sem edital ingerido, /meta e /edital respondem erro — e a
    // resposta certa é o painel dizer "sem edital", não a página quebrar.
    getCarga().then(setCarga).catch(() => {});
    // Uma requisição só pro nome da mesa, aqui — nav e rail leem a mesma
    // resposta. Sem isso os dois pediriam a mesma coisa a cada rota, e
    // poderiam divergir enquanto uma das duas ainda não voltou.
    getMesaAtual().then(setMesa).catch(() => setMesa(null));
    getMeta().then(setMeta).catch(() => {});
    getEdital().then(setEdital).catch(() => setEdital(null));
    getStats().then(setDesempenho).catch(() => {});
    getErros().then(setErros).catch(() => {});
  }, []);

  // PORTÃO DA MESA. Conta sem mesa nenhuma vai pro lobby ANTES de o miolo
  // montar — e o motivo é o backend: `mesa.padrao()` cria "Mesa principal"
  // sozinho na primeira requisição que chega sem X-Mesa-Id (é o que a CLI e os
  // testes esperam). Qualquer tela do app dispara requisições assim ao montar,
  // então no primeiro acesso a mesa aparecia criada sem o aluno ter criado
  // nada — relatado em 22/09/2026. `GET /mesas` só LÊ, não cria.
  //
  // Sem token não trava: a própria página manda pro login.
  const router = useRouter();
  const [liberado, setLiberado] = useState(false);
  useEffect(() => {
    if (semCasca || liberado) return;
    let vivo = true;
    const temMesa = getToken() ? getMesas().then((ms) => ms.length > 0) : Promise.resolve(true);
    temMesa
      .then((tem) => {
        if (!vivo) return;
        if (tem) setLiberado(true);
        else router.replace("/mesas");
      })
      // API fora do ar não pode prender a tela: a página mostra o erro dela.
      .catch(() => vivo && setLiberado(true));
    return () => {
      vivo = false;
    };
  }, [pathname, semCasca, liberado, router]);

  useEffect(() => {
    if (semCasca || !liberado) return;
    carregar();
  }, [pathname, semCasca, liberado, carregar]);

  // O elemento que de fato ROLA (o `<main>`) — a seta de voltar ao topo
  // precisa dele, e ninguém mais deve ter que adivinhar qual é.
  const conteudoRef = useRef<HTMLElement>(null);

  function alternarSidebar() {
    setRecolhida((r) => {
      window.localStorage.setItem(CHAVE_RECOLHIDA, r ? "0" : "1");
      return !r;
    });
  }

  // -------------------------------------------------------------- lobby
  if (semCasca) {
    return (
      <div className="relative flex h-screen overflow-hidden">
        <div className="brilho-topo" />
        <div className="relative z-[1] flex min-w-0 flex-1 flex-col overflow-y-auto">{children}</div>
      </div>
    );
  }

  // Enquanto o portão confere, nada do miolo monta — é ele que dispararia a
  // criação automática da mesa.
  if (!liberado) {
    return <div className="flex h-screen overflow-hidden" />;
  }

  const railVisivel = montado && railDisponivel && railAberto && !foco;
  // Escurece o fundo só quando algo SOBREPÕE o conteúdo: o menu em tela
  // estreita, ou o rail abaixo de 1280px (onde ele deixa de ser coluna do
  // grid e vira drawer). No desktop largo nada sobrepõe, nada escurece.
  const fundoEscurecido = menuAberto || (railVisivel && estreito);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ------------------------------------------------------- nav */}
      {!foco && (
        <div className="hidden lg:block">
          <Sidebar recolhida={recolhida} onAlternar={alternarSidebar} mesa={mesa} />
        </div>
      )}
      {!foco && menuAberto && (
        <Sidebar
          recolhida={false}
          onAlternar={alternarSidebar}
          mesa={mesa}
          drawer
          onFechar={() => setMenuAberto(false)}
        />
      )}

      {/* -------------------------------------------------- conteúdo */}
      <div className="relative flex min-w-0 flex-1">
        <section className="relative flex min-w-0 flex-1 flex-col">
          <div className="brilho-topo" />
          {!foco && (
            <Header
              carga={carga}
              railAberto={railAberto}
              railDisponivel={railDisponivel}
              onAlternarRail={() => setRailAberto((r) => !r)}
              onEntrarFoco={() => setFoco(true)}
              onAbrirMenu={() => setMenuAberto(true)}
            />
          )}
          <main ref={conteudoRef} className="relative z-[1] min-h-0 flex-1 overflow-y-auto">
            {children}
          </main>

          {/* FORA do <main>: é ele que rola, e a seta tem de ficar parada.
              Dentro da <section>, que é `relative`, pra encolher junto com a
              coluna quando o Raio-X abre como coluna no desktop. */}
          {!foco && <VoltarAoTopo alvo={conteudoRef} />}

          {/* Saída do foco no ALTO E À DIREITA, onde o botão "Foco" estava
              antes de o cabeçalho sumir: entrar e sair no mesmo canto é o que
              faz o gesto ser reversível sem procurar. A dica do atalho fica
              visível junto, e não só o botão — quem entrou sem querer precisa
              saber como sair. */}
          {foco && (
            <button
              onClick={() => setFoco(false)}
              className="chip fixed right-5 top-4 z-40 font-mono text-[12px]"
            >
              <X className="h-3.5 w-3.5" />
              Sair do modo foco · esc
            </button>
          )}
        </section>

        {/* ---------------------------------------------------- rail */}
        {railVisivel && <RaioX
          meta={meta}
          mesa={mesa}
          edital={edital}
          desempenho={desempenho}
          carga={carga}
          erros={erros}
          onFechar={() => setRailAberto(false)}
        />}
      </div>

      {/* Fundo escurecido só quando algo está SOBREPONDO o conteúdo — no
          desktop o rail é coluna do grid e não sobrepõe nada. */}
      {fundoEscurecido && (
        <div
          onClick={() => {
            setMenuAberto(false);
            if (estreito) setRailAberto(false);
          }}
          className="fixed inset-0 z-[35] bg-black/60 xl:hidden"
        />
      )}
    </div>
  );
}
