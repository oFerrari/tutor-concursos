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
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">simulado</h1>
        <p className="mt-1 text-sm text-muted">sem dica, sem correção durante a prova — gabarito só no final.</p>
      </div>

      <form onSubmit={comecar} className="card max-w-xs space-y-3">
        <div className="space-y-1">
          <label className="text-sm text-muted">quantas questões</label>
          <input
            type="number"
            min={1}
            value={n}
            onChange={(e) => setN(Number(e.target.value))}
            className="field"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm text-muted">meta de minutos (opcional)</label>
          <input
            type="number"
            min={1}
            value={minutos}
            onChange={(e) => setMinutos(e.target.value === "" ? "" : Number(e.target.value))}
            className="field"
          />
        </div>
        {erro && <p className="text-sm text-danger">{erro}</p>}
        <button type="submit" className="btn-primary">
          começar
        </button>
      </form>

      {historico && historico.length > 0 && (
        <div className="mt-10">
          <h2 className="mb-2 text-sm font-medium text-muted">histórico</h2>
          <ul className="space-y-1 text-sm">
            {historico.map((h) => (
              <li key={h.id} className="flex justify-between border-b border-line py-1.5">
                <span className="text-muted">{h.criado_em.slice(0, 10)}</span>
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
