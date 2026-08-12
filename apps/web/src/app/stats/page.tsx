"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Desempenho, ErroApi, getStats, getToken, limparToken } from "@/lib/api";

function Barra({ pct, cor }: { pct: number | null; cor: string }) {
  const largura = pct == null ? 0 : Math.max(0, Math.min(100, pct));
  return (
    <div className="h-2 flex-1 overflow-hidden rounded-full bg-line">
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
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">estatísticas</h1>
        <p className="mt-1 text-sm text-muted">desempenho por disciplina — só o que você já respondeu.</p>
      </div>

      {erro && <p className="callout-danger">{erro}</p>}
      {!erro && !dados && <p className="text-sm text-muted">carregando…</p>}
      {dados && dados.length === 0 && (
        <p className="text-muted">sem tentativas ainda — responda alguma questão na fila primeiro.</p>
      )}

      {dados && dados.length > 0 && (
        <ul className="space-y-4">
          {dados.map((d) => (
            <li key={d.disciplina} className="card">
              <div className="mb-3 flex items-baseline justify-between">
                <p className="font-medium">{d.disciplina}</p>
                <p className="text-xs text-muted">
                  {d.dominadas}/{d.questoes} dominadas · {d.acertos}/{d.tentativas} tentativas certas
                </p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="w-20 text-xs text-muted">acerto</span>
                  <Barra pct={d.pct_acerto} cor="bg-success" />
                  <span className="w-12 text-right text-xs tabular-nums">
                    {d.pct_acerto == null ? "—" : `${d.pct_acerto.toFixed(0)}%`}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-20 text-xs text-muted">cobertura</span>
                  <Barra pct={d.cobertura_pct} cor="bg-accent" />
                  <span className="w-12 text-right text-xs tabular-nums">{d.cobertura_pct.toFixed(0)}%</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
