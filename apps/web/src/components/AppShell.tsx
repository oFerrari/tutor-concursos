"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";

const CHAVE_RECOLHIDA = "tutor_sidebar_recolhida";
// Rotas sem chrome nenhum — /login é a única tela onde não faz sentido
// mostrar navegação pra quem ainda não provou quem é.
const SEM_SIDEBAR = new Set(["/login"]);

/**
 * Substitui o padrão antigo de `<NavBar />` repetido em cada página: a
 * navegação agora vive UMA vez, aqui, fora do fluxo de cada rota — pedido
 * explícito ("não coloque navegação excessiva no topo", "navegação deve
 * viver na sidebar retrátil"). Client component porque decide o chrome
 * por pathname (usePathname só existe no cliente) — layout.tsx continua
 * Server Component por fora disto.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // Default expandida em toda renderização (servidor + primeiro paint no
  // cliente): ler localStorage no useEffect pode ajustar depois — um
  // possível "pulo" de largura é aceitável, tela em branco não é (o que
  // aconteceria gateando a renderização até o efeito rodar).
  const [recolhida, setRecolhida] = useState(false);

  useEffect(() => {
    // Ler a preferência salva só depois de montar é o jeito CORRETO de
    // evitar descompasso servidor/cliente aqui (localStorage não existe no
    // servidor) — ler no inicializador do useState é que causaria
    // descompasso de hidratação de verdade. A regra é genérica; este caso é seguro.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRecolhida(window.localStorage.getItem(CHAVE_RECOLHIDA) === "1");
  }, []);

  function alternar() {
    setRecolhida((r) => {
      window.localStorage.setItem(CHAVE_RECOLHIDA, r ? "0" : "1");
      return !r;
    });
  }

  if (SEM_SIDEBAR.has(pathname)) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar recolhida={recolhida} onAlternar={alternar} />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
