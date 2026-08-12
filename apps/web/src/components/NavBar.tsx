"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { limparToken } from "@/lib/api";

// Só rotas que já existem — cresce junto com o backlog (erros, simulado,
// desafio entram aqui quando as telas ficarem prontas, não antes).
const ITENS = [
  { href: "/fila", label: "fila" },
  { href: "/desafio", label: "desafio" },
  { href: "/erros", label: "erros" },
  { href: "/simulado", label: "simulado" },
  { href: "/stats", label: "stats" },
  { href: "/perguntar", label: "perguntar" },
  { href: "/meta", label: "meta" },
];

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();

  function sair() {
    limparToken();
    router.push("/login");
  }

  return (
    <nav className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-1">
        <Link href="/fila" className="mr-3 text-sm font-bold tracking-tight text-accent">
          tutor
        </Link>
        {ITENS.map((item) => {
          const ativo = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                ativo
                  ? "rounded-full bg-accent-soft px-3 py-1.5 text-sm font-medium text-accent"
                  : "rounded-full px-3 py-1.5 text-sm text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
              }
            >
              {item.label}
            </Link>
          );
        })}
      </div>
      <button onClick={sair} className="link">
        sair
      </button>
    </nav>
  );
}
