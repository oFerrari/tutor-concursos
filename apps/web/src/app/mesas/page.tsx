"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, LogOut, Plus } from "lucide-react";
import { Marca } from "@/components/Marca";
import { Usuario, getMe, limparToken } from "@/lib/api";
import { MESAS_EXEMPLO } from "@/mock/prototipo";

/**
 * "Mesas de estudo" — o lobby do protótipo: cada mesa guarda seu próprio
 * edital, fila SM-2, caderno de erros e histórico.
 *
 * ⚠ TELA DE VITRINE. Os cartões vêm de `MESAS_EXEMPLO`, não do banco,
 * porque MESA NÃO EXISTE NO SCHEMA — hoje o edital pertence ao `usuario`
 * (migração 007 + 008), não a uma mesa, e `progresso`/`tentativa` também.
 * Fazer isso valer de verdade é uma migração 010 com escopo de mesa em
 * cinco tabelas, não uma tela.
 *
 * Por isso os cartões levam para `/` (o painel único que existe). Clicar
 * em "Analista TRF" e "Banco do Brasil" abre O MESMO progresso — é o que
 * o backend tem hoje, e é melhor a tela ser honesta sobre isso do que
 * fingir três contextos separados que ela não consegue manter.
 */
export default function PaginaMesas() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [menuAberto, setMenuAberto] = useState(false);

  useEffect(() => {
    getMe()
      .then(setUsuario)
      .catch(() => {});
  }, []);

  const inicial = (usuario?.email?.[0] ?? "?").toUpperCase();

  return (
    <div className="mx-auto w-full max-w-[940px] px-6 pb-12 pt-10">
      {/* ------------------------------------------------------ topo */}
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2.5">
          <Marca />
        </Link>

        <div className="relative">
          <button
            onClick={() => setMenuAberto((a) => !a)}
            className="flex items-center gap-2.5 rounded-full border border-line-soft py-1.5 pl-2 pr-3 transition-colors hover:bg-surface-hover"
          >
            <span className="flex h-[26px] w-[26px] items-center justify-center rounded-full border border-line-strong bg-surface-hover text-[12px] font-semibold text-accent-text">
              {inicial}
            </span>
            <span className="max-w-[160px] truncate text-[13px]">{usuario?.email ?? "conta"}</span>
            <ChevronDown className="h-3.5 w-3.5 text-subtle" />
          </button>

          {menuAberto && (
            <>
              <div onClick={() => setMenuAberto(false)} className="fixed inset-0 z-[25]" />
              <div className="absolute right-0 top-[calc(100%+8px)] z-30 w-[232px] rounded-[14px] border border-line-strong bg-surface p-1.5 shadow-[var(--shadow-drawer)]">
                <div className="mb-1.5 border-b border-line-soft px-3 pb-3 pt-2.5">
                  <p className="font-mono text-[11px] text-subtle">{usuario?.email ?? "—"}</p>
                </div>
                <Link
                  href="/materiais"
                  className="block rounded-[9px] px-3 py-2.5 text-[13px] text-body transition-colors hover:bg-surface-hover hover:text-foreground"
                >
                  Meus materiais
                </Link>
                <Link
                  href="/meta"
                  className="block rounded-[9px] px-3 py-2.5 text-[13px] text-body transition-colors hover:bg-surface-hover hover:text-foreground"
                >
                  Meu edital
                </Link>
                <div className="mx-1 my-1.5 h-px bg-line-soft" />
                <button
                  onClick={() => {
                    limparToken();
                    window.location.href = "/login";
                  }}
                  className="flex w-full items-center gap-2.5 rounded-[9px] px-3 py-2.5 text-[13px] text-danger transition-colors hover:bg-surface-hover"
                >
                  <LogOut className="h-[15px] w-[15px]" />
                  Sair da conta
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <h1 className="text-[30px]">
        Bem-vindo de volta. Qual é a <span className="text-accent-text">missão de hoje</span>?
      </h1>
      <p className="mb-7 mt-2 text-[15px] text-muted">
        Cada mesa guarda seu próprio edital, fila SM-2, caderno de erros e histórico.
      </p>

      {/* Aviso no lugar de esconder: a tela mostra exemplo, e diz que é. */}
      <p className="callout-info mb-5">
        <span className="font-semibold text-accent-text">vitrine · </span>
        as mesas abaixo são exemplo do protótipo. O backend ainda guarda um edital por conta, então
        qualquer uma delas abre o mesmo progresso.
      </p>

      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3">
        {MESAS_EXEMPLO.map((m) => (
          <Link key={m.id} href="/" className="card-link flex flex-col gap-3.5">
            <div>
              <p className="rotulo mb-2">{m.banca}</p>
              <p className="text-base font-semibold leading-snug">{m.nome}</p>
            </div>
            <div className="mt-auto">
              <div className="mb-1.5 flex items-baseline justify-between gap-2.5">
                <span className="font-mono text-[11.5px] text-subtle">{m.topicos}</span>
                <span
                  className="mono-num text-[12.5px]"
                  style={{ color: m.pct >= 75 ? "var(--success)" : "var(--accent-text)" }}
                >
                  {m.pct}%
                </span>
              </div>
              <div className="barra">
                <div
                  className="barra-fill"
                  style={{
                    width: `${m.pct}%`,
                    background: m.pct >= 75 ? "var(--success)" : "var(--accent)",
                  }}
                />
              </div>
              <p className="mt-2.5 text-[12px] text-subtle">{m.ultimo}</p>
            </div>
          </Link>
        ))}

        <Link
          href="/onboarding"
          className="drop flex min-h-[176px] flex-col items-start justify-center gap-3 !text-left"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-accent-soft text-accent-text">
            <Plus className="h-[18px] w-[18px]" strokeWidth={2.4} />
          </span>
          <span>
            <span className="mb-1.5 block text-[15.5px] font-semibold">Criar nova mesa</span>
            <span className="block text-[13px] leading-relaxed text-muted">
              Arraste o PDF do seu edital aqui e a IA configura tudo sozinha.
            </span>
          </span>
        </Link>
      </div>
    </div>
  );
}
