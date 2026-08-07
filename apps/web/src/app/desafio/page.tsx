"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DialogoQuestao } from "@/components/DialogoQuestao";
import { NavBar } from "@/components/NavBar";
import { SimuladoRunner } from "@/components/SimuladoRunner";
import { Sugestao } from "@/components/Sugestao";
import { ErroApi, PlanoDesafio, getDesafio, getToken, iniciarSimuladoComIds, limparToken } from "@/lib/api";

type Bloco = "plano" | "reincidentes" | "novas" | "simulado" | "fim";

/**
 * Composição, não módulo novo — mesmo espírito de core/desafio.py: este
 * componente só decide QUAL bloco mostrar agora; quem resolve de verdade é
 * <DialogoQuestao> (blocos 1 e 2) e <SimuladoRunner> (bloco 3), os mesmos
 * componentes que /questao/[id] e /simulado já usam.
 */
export default function PaginaDesafio() {
  const router = useRouter();
  const [plano, setPlano] = useState<PlanoDesafio | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [bloco, setBloco] = useState<Bloco>("plano");
  const [indice, setIndice] = useState(0);
  const [sessaoSimulado, setSessaoSimulado] = useState<{ id: number; questoes: PlanoDesafio["mini_simulado"] } | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getDesafio()
      .then(setPlano)
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
      });
  }, [router]);

  async function irPara(proximo: Bloco) {
    if (!plano) return;
    if (proximo === "novas" && plano.novas.length === 0) proximo = "simulado";
    if (proximo === "simulado" && plano.mini_simulado.length === 0) proximo = "fim";

    if (proximo === "simulado") {
      try {
        const r = await iniciarSimuladoComIds(plano.mini_simulado.map((q) => q.id));
        setSessaoSimulado({ id: r.simulado_id, questoes: r.questoes });
      } catch (e) {
        setErro(e instanceof ErroApi ? e.message : "não deu pra iniciar o mini-simulado");
        setBloco("fim");
        return;
      }
    }
    setIndice(0);
    setBloco(proximo);
  }

  function comecar() {
    if (!plano) return;
    if (plano.reincidentes.length > 0) irPara("reincidentes");
    else if (plano.novas.length > 0) irPara("novas");
    else irPara("simulado");
  }

  function proximaDoBloco(atual: "reincidentes" | "novas") {
    const lista = atual === "reincidentes" ? plano!.reincidentes : plano!.novas;
    if (indice + 1 < lista.length) {
      setIndice(indice + 1);
    } else {
      irPara(atual === "reincidentes" ? "novas" : "simulado");
    }
  }

  function sairDoDesafio() {
    setBloco("fim");
  }

  if (erro && bloco === "plano") {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <NavBar />
        <p className="text-red-600">{erro}</p>
      </main>
    );
  }

  if (!plano) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <NavBar />
        <p className="text-sm opacity-60">carregando…</p>
      </main>
    );
  }

  if (bloco === "plano") {
    if (plano.total_questoes === 0) {
      return (
        <main className="mx-auto max-w-2xl p-8">
          <NavBar />
          <h1 className="mb-4 text-xl font-semibold">desafio de hoje</h1>
          <p className="opacity-60">
            nada pra compor um desafio ainda — responda algumas questões na fila primeiro.
          </p>
        </main>
      );
    }
    return (
      <main className="mx-auto max-w-2xl p-8">
        <NavBar />
        <Sugestao />
        <h1 className="mb-4 text-xl font-semibold">desafio de hoje</h1>
        <div className="rounded border border-black/10 p-4 text-sm">
          <p>{plano.reincidentes.length} pontos fracos</p>
          <p>{plano.novas.length} novas</p>
          <p>{plano.mini_simulado.length} mini-simulado</p>
          <p className="mt-2 opacity-60">~{plano.estimativa_minutos} min estimados</p>
        </div>
        <button onClick={comecar} className="mt-4 rounded bg-black px-4 py-2 text-sm text-white">
          começar
        </button>
      </main>
    );
  }

  if (bloco === "reincidentes" || bloco === "novas") {
    const q = (bloco === "reincidentes" ? plano.reincidentes : plano.novas)[indice];
    const total = (bloco === "reincidentes" ? plano.reincidentes : plano.novas).length;
    return (
      <main className="mx-auto max-w-2xl p-8">
        <p className="mb-4 text-xs uppercase tracking-wide opacity-50">
          {bloco === "reincidentes" ? "bloco 1 — pontos fracos" : "bloco 2 — novas"} · {indice + 1}/{total}
        </p>
        <DialogoQuestao
          questao={q}
          rotuloContinuar="próxima"
          onFechado={() => proximaDoBloco(bloco)}
          onSair={sairDoDesafio}
        />
      </main>
    );
  }

  if (bloco === "simulado" && sessaoSimulado) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <p className="mb-4 text-xs uppercase tracking-wide opacity-50">bloco 3 — mini-simulado</p>
        <SimuladoRunner
          simuladoId={sessaoSimulado.id}
          questoes={sessaoSimulado.questoes}
          rotuloContinuar="concluir desafio"
          onFinalizado={() => setBloco("fim")}
        />
      </main>
    );
  }

  // fim
  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <h1 className="mb-4 text-xl font-semibold">desafio concluído</h1>
      {erro && <p className="mb-4 text-red-600">{erro}</p>}
      <button onClick={() => router.push("/stats")} className="rounded bg-black px-4 py-2 text-sm text-white">
        ver estatísticas
      </button>
    </main>
  );
}
