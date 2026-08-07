"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { NavBar } from "@/components/NavBar";
import { Desempenho, ErroApi, getStats, getToken, limparToken } from "@/lib/api";

function Barra({ pct, cor }: { pct: number; cor: string }) {
  const largura = Math.max(0, Math.min(100, pct));
  return (
    <div className="h-2 flex-1 overflow-hidden rounded-full bg-black/[0.06]">
      <div className={`h-full rounded-full ${cor}`} style={{ width: `${largura}%` }} />
    </div>
  );
}

export default function PaginaStats() {
  const router = useRouter();
  const [dados, setDados] = useState<Desempenho[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getStats()
      .then(setDados)
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
      });
  }, [router]);

  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <h1 className="mb-1 text-xl font-semibold">estatísticas</h1>
      <p className="mb-6 text-sm opacity-70">desempenho por disciplina — só o que você já respondeu.</p>

      {erro && <p className="text-red-600">{erro}</p>}
      {!erro && !dados && <p className="text-sm opacity-60">carregando…</p>}
      {dados && dados.length === 0 && (
        <p className="opacity-60">sem tentativas ainda — responda alguma questão na fila primeiro.</p>
      )}

      {dados && dados.length > 0 && (
        <ul className="space-y-5">
          {dados.map((d) => (
            <li key={d.disciplina} className="rounded border border-black/10 p-4">
              <div className="mb-3 flex items-baseline justify-between">
                <p className="font-medium">{d.disciplina}</p>
                <p className="text-xs opacity-60">
                  {d.dominadas}/{d.questoes} dominadas · {d.acertos}/{d.tentativas} tentativas certas
                </p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="w-20 text-xs opacity-60">acerto</span>
                  <Barra pct={d.pct_acerto} cor="bg-emerald-600" />
                  <span className="w-12 text-right text-xs tabular-nums">{d.pct_acerto.toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-20 text-xs opacity-60">cobertura</span>
                  <Barra pct={d.cobertura_pct} cor="bg-sky-600" />
                  <span className="w-12 text-right text-xs tabular-nums">{d.cobertura_pct.toFixed(0)}%</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
