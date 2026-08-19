"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AvisoAcervo } from "@/components/AvisoAcervo";
import { QuestaoInterativa } from "@/components/QuestaoInterativa";
import { SimuladoRunner } from "@/components/SimuladoRunner";
import { Sugestao } from "@/components/Sugestao";
import {
  ErroApi,
  EstadoSimulado,
  Perfil,
  PlanoDesafio,
  getDesafio,
  getPerfil,
  getToken,
  iniciarSimuladoComIds,
} from "@/lib/api";
import { sair } from "@/lib/cache";

type Bloco = "plano" | "reincidentes" | "novas" | "simulado" | "fim";
const ORCAMENTOS = [10, 20, 30, null] as const;

/**
 * Espelha `core/desafio.minutos_do_perfil` — mesma aproximação declarada
 * lá (horas/dia tratado como minutos de UMA sessão). Existe duplicado nos
 * dois lados pelo mesmo motivo de MAX_DICAS/MAX_TENTATIVAS entre chat.py e
 * DialogoQuestao.tsx: é uma conta de uma linha, e o back não pode aplicar
 * isso sozinho sem arriscar confundir "ninguém escolheu ainda" com
 * "escolheu sessão cheia de propósito" (os dois chegam como minutos=null
 * na API) — só o front sabe em qual dos dois estados está.
 */
function minutosDoPerfil(perfil: Perfil): number | null {
  const m = /^(\d+)h\+?$/.exec(perfil.horas ?? "");
  return m ? Number(m[1]) * 60 : null;
}

/**
 * Composição, não módulo novo — mesmo espírito de core/desafio.py: este
 * componente só decide QUAL bloco mostrar agora; quem resolve de verdade é
 * <QuestaoInterativa> (blocos 1 e 2) e <SimuladoRunner> (bloco 3), os mesmos
 * componentes que /questao/[id] e /simulado já usam.
 */
export default function PaginaDesafio() {
  const router = useRouter();
  const [plano, setPlano] = useState<PlanoDesafio | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [bloco, setBloco] = useState<Bloco>("plano");
  const [indice, setIndice] = useState(0);
  const [sessaoSimulado, setSessaoSimulado] = useState<EstadoSimulado | null>(null);

  // Orçamento de tempo escolhido pelo aluno. `null` = desafio cheio.
  const [minutos, setMinutos] = useState<number | null>(null);
  // Chip "personalizado": ativa um campo numérico ao lado dos fixos, em
  // vez de forçar 10/20/30 quando a pessoa sabe exatamente quanto tempo
  // tem (ex.: 15 min entre uma aula e outra).
  const [personalizando, setPersonalizando] = useState(false);
  const [minutosPersonalizados, setMinutosPersonalizados] = useState("");

  // `buscar` NÃO mexe em estado de forma síncrona — o `setPlano` acontece
  // no `.then`. É o que permite chamá-la do efeito sem cascata de render;
  // o reset visual (limpar o plano na tela) mora no handler do clique,
  // que é onde ele é de fato um efeito de interação.
  const buscar = useCallback(
    (orcamento: number | null) => {
      getDesafio(orcamento ?? undefined)
        .then(setPlano)
        .catch((e) => {
          if (e instanceof ErroApi && e.status === 401) {
            sair();
            router.push("/login");
            return;
          }
          setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
        });
    },
    [router]
  );

  function trocarOrcamento(op: number | null) {
    setPlano(null);
    setMinutos(op);
    buscar(op);
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    // Primeira carga: calibra pelo perfil (horas/dia do onboarding) em vez
    // de abrir sempre em "sessão cheia" — só aqui, uma vez. Qualquer clique
    // do aluno depois disso (mesmo em "sessão cheia") é escolha explícita e
    // não passa mais por aqui.
    getPerfil()
      .then((perfil) => {
        const padrao = minutosDoPerfil(perfil);
        if (padrao == null) {
          buscar(null);
          return;
        }
        if ((ORCAMENTOS as readonly (number | null)[]).includes(padrao)) {
          setMinutos(padrao);
        } else {
          setPersonalizando(true);
          setMinutosPersonalizados(String(padrao));
        }
        buscar(padrao);
      })
      .catch(() => buscar(null));
  }, [router, buscar]);

  async function irPara(proximo: Bloco) {
    if (!plano) return;
    if (proximo === "novas" && plano.novas.length === 0) proximo = "simulado";
    if (proximo === "simulado" && plano.mini_simulado.length === 0) proximo = "fim";

    if (proximo === "simulado") {
      try {
        const r = await iniciarSimuladoComIds(plano.mini_simulado.map((q) => q.id));
        setSessaoSimulado({
          id: r.simulado_id,
          questoes: r.questoes.map((q) => ({ ...q, respondida: false, resposta_dada: null })),
          minutos_alvo: null,
          segundos_acumulados: 0,
          finalizado: false,
        });
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

        {/* "Só tenho N minutos hoje". A conta usa a SUA velocidade média
            real, então 20 minutos rendem mais pra quem responde rápido —
            número fixo pra todo mundo seria chute onde existe medida. */}
        <div className="mt-4">
          <p className="rotulo mb-2">tenho menos tempo hoje</p>
          <div className="flex flex-wrap items-center gap-2">
            {ORCAMENTOS.map((op) => (
              <button
                key={op ?? "cheio"}
                onClick={() => {
                  setPersonalizando(false);
                  trocarOrcamento(op);
                }}
                className={!personalizando && minutos === op ? "chip-ativo" : "chip"}
              >
                {op ? `${op} min` : "sessão cheia"}
              </button>
            ))}
            {/* Personalizado: os 3 fixos raramente batem com "tenho uns 15
                minutos entre uma aula e outra" — a conta de orçamento já
                aceita qualquer inteiro (core/desafio.montar(minutos=...)),
                só faltava a tela deixar digitar um. */}
            {personalizando ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const v = Number(minutosPersonalizados);
                  if (v > 0) trocarOrcamento(v);
                }}
                className="flex items-center gap-1.5"
              >
                <input
                  type="number"
                  min={1}
                  autoFocus
                  value={minutosPersonalizados}
                  onChange={(e) => setMinutosPersonalizados(e.target.value)}
                  placeholder="min"
                  className="field w-[72px] !py-1.5 text-center text-[13px]"
                />
                <button type="submit" className="chip-ativo">
                  ok
                </button>
              </form>
            ) : (
              <button onClick={() => setPersonalizando(true)} className="chip">
                personalizado
              </button>
            )}
          </div>
          {minutos !== null && plano.estimativa_minutos < minutos && (
            <p className="mt-2 text-[12.5px] text-subtle">
              Cabiam mais, mas o acervo desta mesa acabou antes do tempo.
            </p>
          )}
        </div>

        <button onClick={comecar} className="btn-primary mt-5">
          Começar
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
        <QuestaoInterativa
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
          estado={sessaoSimulado}
          rotuloContinuar="Concluir desafio"
          onFinalizado={() => setBloco("fim")}
          onSair={sairDoDesafio}
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
