"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { NavBar } from "@/components/NavBar";
import { SimuladoRunner } from "@/components/SimuladoRunner";
import { ErroApi, HistoricoSimulado, QuestaoSimulado, getSimulados, getToken, iniciarSimulado, limparToken } from "@/lib/api";

export default function PaginaSimulado() {
  const router = useRouter();
  const [erro, setErro] = useState<string | null>(null);
  const [historico, setHistorico] = useState<HistoricoSimulado[] | null>(null);

  const [n, setN] = useState(10);
  const [minutos, setMinutos] = useState<number | "">("");

  const [sessao, setSessao] = useState<{ id: number; questoes: QuestaoSimulado[] } | null>(null);
  const [finalizado, setFinalizado] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getSimulados()
      .then(setHistorico)
      .catch(() => {}); // histórico é só um extra — não bloqueia o form se falhar
  }, [router]);

  async function comecar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const r = await iniciarSimulado(n, minutos === "" ? undefined : minutos);
      if (r.questoes.length === 0) {
        setErro("nenhuma questão no acervo ainda.");
        return;
      }
      setSessao({ id: r.simulado_id, questoes: r.questoes });
      setFinalizado(false);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        limparToken();
        router.push("/login");
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
    }
  }

  if (sessao && !finalizado) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <SimuladoRunner
          simuladoId={sessao.id}
          questoes={sessao.questoes}
          rotuloContinuar="novo simulado"
          onFinalizado={() => {
            setFinalizado(true);
            setSessao(null);
            getSimulados().then(setHistorico).catch(() => {});
          }}
        />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <h1 className="mb-1 text-xl font-semibold">simulado</h1>
      <p className="mb-6 text-sm opacity-70">sem dica, sem correção durante a prova — gabarito só no final.</p>

      <form onSubmit={comecar} className="max-w-xs space-y-3">
        <div>
          <label className="text-sm">quantas questões</label>
          <input
            type="number"
            min={1}
            value={n}
            onChange={(e) => setN(Number(e.target.value))}
            className="w-full rounded border border-black/20 px-3 py-2"
          />
        </div>
        <div>
          <label className="text-sm">meta de minutos (opcional)</label>
          <input
            type="number"
            min={1}
            value={minutos}
            onChange={(e) => setMinutos(e.target.value === "" ? "" : Number(e.target.value))}
            className="w-full rounded border border-black/20 px-3 py-2"
          />
        </div>
        {erro && <p className="text-sm text-red-600">{erro}</p>}
        <button type="submit" className="rounded bg-black px-4 py-2 text-sm text-white">
          começar
        </button>
      </form>

      {historico && historico.length > 0 && (
        <div className="mt-10">
          <h2 className="mb-2 text-sm font-medium opacity-70">histórico</h2>
          <ul className="space-y-1 text-sm">
            {historico.map((h) => (
              <li key={h.id} className="flex justify-between border-b border-black/5 py-1">
                <span className="opacity-60">{h.criado_em.slice(0, 10)}</span>
                <span>
                  {h.respondidas}/{h.n_questoes} · {h.nota_pct ?? 0}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}
