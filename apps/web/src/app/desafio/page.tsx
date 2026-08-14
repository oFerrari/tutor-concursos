"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AvisoAcervo } from "@/components/AvisoAcervo";
import { DialogoQuestao } from "@/components/DialogoQuestao";
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
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
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
        setErro(e instanceof ErroApi ? e.message : "Não deu pra iniciar o mini-simulado");
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
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="callout-danger">{erro}</p>
      </div>
    );
  }

  if (!plano) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="text-sm text-muted">Carregando…</p>
      </div>
    );
  }

  if (bloco === "plano") {
    if (plano.total_questoes === 0) {
      return (
        <div className="mx-auto max-w-2xl p-6 md:p-10">
          <h1 className="mb-4 text-2xl font-semibold tracking-tight">Desafio de hoje</h1>
          <AvisoAcervo />
          <p className="mt-4 text-muted">
            nada pra compor um desafio ainda — responda algumas questões na fila primeiro.
          </p>
        </div>
      );
    }
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <Sugestao />
        <h1 className="mb-4 text-2xl font-semibold tracking-tight">Desafio de hoje</h1>
        <div className="card space-y-1 text-sm">
          <p>{plano.reincidentes.length} pontos fracos</p>
          <p>{plano.novas.length} novas</p>
          <p>{plano.mini_simulado.length} mini-simulado</p>
          <p className="mt-2 text-muted">~{plano.estimativa_minutos} min estimados</p>
        </div>
        <button onClick={comecar} className="btn-primary mt-4">
          começar
        </button>
      </div>
    );
  }

  if (bloco === "reincidentes" || bloco === "novas") {
    const q = (bloco === "reincidentes" ? plano.reincidentes : plano.novas)[indice];
    const total = (bloco === "reincidentes" ? plano.reincidentes : plano.novas).length;
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="mb-4 text-xs font-medium uppercase tracking-wide text-muted">
          {bloco === "reincidentes" ? "bloco 1 — pontos fracos" : "bloco 2 — novas"} · {indice + 1}/{total}
        </p>
        {/* key={q.id} NÃO é detalhe de performance — é o que faz a próxima
            questão realmente começar do zero. Sem key, o React reaproveita
            a MESMA instância (mesmo tipo, mesma posição) e todo o estado
            interno sobrevive: `resultado` continua preenchido, então a
            questão 2 abria já na tela de resultado da questão 1, e clicar
            "próxima" pulava o bloco inteiro sem registrar tentativa
            nenhuma. Encontrado ao conferir o cronômetro, não em produção. */}
        <DialogoQuestao
          key={q.id}
          questao={q}
          rotuloContinuar="Próxima"
          onFechado={() => proximaDoBloco(bloco)}
          onSair={sairDoDesafio}
        />
      </div>
    );
  }

  if (bloco === "simulado" && sessaoSimulado) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="mb-4 text-xs font-medium uppercase tracking-wide text-muted">Bloco 3 — mini-simulado</p>
        <SimuladoRunner
          simuladoId={sessaoSimulado.id}
          questoes={sessaoSimulado.questoes}
          rotuloContinuar="Concluir desafio"
          onFinalizado={() => setBloco("fim")}
        />
      </div>
    );
  }

  // fim
  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <h1 className="mb-4 text-2xl font-semibold tracking-tight">Desafio concluído</h1>
      {erro && <p className="mb-4 callout-danger">{erro}</p>}
      <button onClick={() => router.push("/stats")} className="btn-primary">
        ver estatísticas
      </button>
    </div>
  );
}
