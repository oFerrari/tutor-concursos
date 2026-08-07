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
    <nav className="mb-6 flex items-center justify-between border-b border-black/10 pb-3">
      <div className="flex gap-4 text-sm">
        {ITENS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={pathname === item.href ? "font-semibold" : "opacity-60 hover:opacity-100"}
          >
            {item.label}
          </Link>
        ))}
      </div>
      <button onClick={sair} className="text-sm underline opacity-60">
        sair
      </button>
    </nav>
  );
}
