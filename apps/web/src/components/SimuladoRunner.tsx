"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, Pause, Play } from "lucide-react";
import {
  ErroApi,
  EstadoSimulado,
  finalizarSimulado,
  responderUmaSimulado,
  salvarTempoSimulado,
} from "@/lib/api";
import { decorridos } from "@/lib/tempo";
import { TextoAssociado } from "@/components/TextoAssociado";
import { RelatorioProva, RelatorioSimulado } from "@/components/RelatorioProva";

export type { RelatorioSimulado };

type Props = {
  /** Sempre o mesmo formato pra prova nova e prova retomada — uma prova
   *  nova é só um `estado` onde tudo já vem com `respondida: false` e
   *  `segundos_acumulados: 0` (ver /simulado/page.tsx e /desafio/page.tsx). */
  estado: EstadoSimulado;
  onFinalizado: (r: RelatorioSimulado) => void;
  /** Sair SEM finalizar — a prova fica "em andamento" (retomável depois),
   *  porque tudo que já foi respondido já está salvo. Omitir esconde o
   *  botão (não existe tela onde sair devesse ser proibido, mas o prop
   *  opcional deixa isso explícito no chamador, não implícito no componente). */
  onSair?: () => void;
  rotuloContinuar?: string;
};

function formatarRelogio(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * Responder → corrigir → relatório de um simulado. Migração 018: cada
 * resposta é salva NA HORA (`responderUmaSimulado`), não empilhada pra um
 * envio único no final — é o que faz a prova sobreviver a aba fechada,
 * conexão caindo ou bateria acabando no meio.
 *
 * "Pausar" NÃO esconde a questão — só congela o relógio. Uma tela cheia
 * de "simulado pausado" no lugar da pergunta impedia até RELER o
 * enunciado durante a pausa, que não é o que pausar deveria fazer. O
 * relógio em si é salvo explicitamente ao pausar/sair (`salvarTempoSimulado`)
 * e por um heartbeat a cada 20s enquanto ativo — sem isso, o único jeito
 * do tempo chegar ao banco era responder outra questão, e quem pausava
 * sem responder mais nada perdia o tempo decorrido (voltava contando do
 * último save, não de onde realmente parou).
 *
 * Navegar pra trás e REVISAR uma resposta é possível — uma prova real
 * deixa revisar antes de entregar. `respostasDadas` guarda o texto de
 * CADA questão (não só um `resposta` solto pra questão atual), seedado do
 * que `estado()` já devolve pra quem retoma uma prova de outra sessão —
 * sem isso, voltar reabria o campo em branco como se nunca tivesse
 * respondido nada.
 */
export function SimuladoRunner({ estado, onFinalizado, onSair, rotuloContinuar = "continuar" }: Props) {
  const primeiraPendente = estado.questoes.findIndex((q) => !q.respondida);
  const jaTerminou = primeiraPendente === -1;

  const [etapa, setEtapa] = useState<"respondendo" | "corrigindo" | "relatorio">(
    jaTerminou ? "corrigindo" : "respondendo"
  );
  const [indice, setIndice] = useState(jaTerminou ? estado.questoes.length - 1 : primeiraPendente);
  const [respostasDadas, setRespostasDadas] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      estado.questoes.filter((q) => q.resposta_dada != null).map((q) => [q.id, q.resposta_dada as string])
    )
  );
  const [pausado, setPausado] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [relatorioFinal, setRelatorioFinal] = useState<RelatorioSimulado | null>(null);

  // Relógio ATIVO — começa de onde a última sessão parou (`estado.segundos_
  // acumulados`), soma 1 por segundo enquanto NÃO pausado. É o número que
  // vai pro relatório como segundos_total: tempo de prova de verdade, sem
  // a pausa do banheiro nem o tempo com a aba fechada contando junto.
  const [segundosAtivos, setSegundosAtivos] = useState(estado.segundos_acumulados);
  // `null`, não `useRef(Date.now())` — o argumento do useRef é avaliado a
  // CADA render, e aí a impureza seria real (mesmo motivo documentado em
  // lib/tempo.ts). O marco de largada só é gravado dentro do efeito abaixo.
  const inicioPergunta = useRef<number | null>(null);

  useEffect(() => {
    if (pausado || etapa !== "respondendo") return;
    const id = setInterval(() => setSegundosAtivos((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [pausado, etapa]);

  // Heartbeat: salva o relógio a cada 20s enquanto ativo, sem depender de
  // responder outra questão — é a rede de segurança contra fechar a aba
  // ou a conexão cair no meio, sem apertar nem "pausar" nem "sair".
  const segundosRef = useRef(segundosAtivos);
  segundosRef.current = segundosAtivos;
  useEffect(() => {
    if (pausado || etapa !== "respondendo") return;
    const id = setInterval(() => {
      salvarTempoSimulado(estado.id, segundosRef.current).catch(() => {});
    }, 20_000);
    return () => clearInterval(id);
  }, [pausado, etapa, estado.id]);

  useEffect(() => {
    inicioPergunta.current = Date.now();
  }, [indice]);

  function pausar() {
    setPausado(true);
    salvarTempoSimulado(estado.id, segundosAtivos).catch(() => {});
  }

  function sair() {
    salvarTempoSimulado(estado.id, segundosAtivos).catch(() => {});
    onSair?.();
  }

  // Se a prova retomada já tinha TODAS as questões respondidas (a pessoa só
  // não tinha clicado em finalizar), finaliza direto — não tem questão
  // pendente pra mostrar.
  useEffect(() => {
    if (jaTerminou) finalizar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const q = estado.questoes[indice];
  const resposta = respostasDadas[q.id] ?? "";

  function setResposta(v: string) {
    setRespostasDadas((r) => ({ ...r, [q.id]: v }));
  }

  /** `escolha` só vem no item C/E, onde o clique JÁ é a resposta. */
  async function proxima(pular: boolean, escolha?: "C" | "E") {
    if (salvando) return;
    setSalvando(true);
    setErro(null);
    const segundosPergunta = decorridos(inicioPergunta.current);
    const respostaFinal = pular ? "" : escolha ?? resposta;
    try {
      await responderUmaSimulado(estado.id, q.id, respostaFinal, segundosPergunta, segundosAtivos);
      setRespostasDadas((r) => ({ ...r, [q.id]: respostaFinal }));
      if (indice + 1 < estado.questoes.length) {
        setIndice(indice + 1);
      } else {
        await finalizar();
      }
    } catch (e) {
      // NÃO avança — a resposta não foi confirmada salva. Tentar de novo é
      // seguro: revisão faz UPDATE, não INSERT (ver core/simulado.py), então
      // reenviar não duplica nem se o 1º envio TINHA chegado e só a
      // confirmação se perdeu.
      setErro(e instanceof ErroApi ? e.message : "não deu pra salvar — sua conexão pode ter caído. tente de novo.");
    } finally {
      setSalvando(false);
    }
  }

  async function finalizar() {
    setEtapa("corrigindo");
    try {
      const r = await finalizarSimulado(estado.id, segundosAtivos);
      setRelatorioFinal(r);
      setEtapa("relatorio");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra corrigir o simulado");
      setEtapa("respondendo");
    }
  }

  if (etapa === "corrigindo") {
    return <p className="text-sm text-muted">Corrigindo…</p>;
  }

  if (etapa === "relatorio" && relatorioFinal) {
    return (
      <RelatorioProva
        relatorio={relatorioFinal}
        segundosTotal={segundosAtivos}
        rotuloAcao={rotuloContinuar}
        onAcao={() => onFinalizado(relatorioFinal)}
      />
    );
  }

  // Estourou o orçamento de tempo desta prova — só quando ELA tem um
  // (`minutos_alvo`, definido ao criar); sem meta, não há "estourar".
  const estourado = estado.minutos_alvo != null && segundosAtivos > estado.minutos_alvo * 60;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between text-xs text-muted">
        <div className="flex items-center gap-2">
          {/* Voltar pra uma questão já respondida — não existia, e não ter
              isso é o mesmo tipo de "sem saída" que /simulado sem `onSair`
              tinha: uma prova real deixa revisar antes de entregar. */}
          <button
            onClick={() => setIndice(indice - 1)}
            disabled={indice === 0 || salvando}
            aria-label="questão anterior"
            className="link disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span>
            {indice + 1}/{estado.questoes.length} · {q.disciplina}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Cronômetro visível — o que faltava: o tempo corria escondido
              antes disso, só usado depois pra calcular a média. Vermelho +
              chacoalhando quando estoura a meta de minutos da prova. */}
          <span
            className={
              estourado
                ? "relogio-estourado font-mono font-bold tabular-nums text-danger"
                : "font-mono tabular-nums"
            }
          >
            {formatarRelogio(segundosAtivos)}
          </span>
          {pausado ? (
            <button onClick={() => setPausado(false)} className="link inline-flex items-center gap-1">
              <Play className="h-3.5 w-3.5" />
              retomar
            </button>
          ) : (
            <button onClick={pausar} className="link inline-flex items-center gap-1">
              <Pause className="h-3.5 w-3.5" />
              pausar
            </button>
          )}
          {/* Sem `disabled`: parar na 1ª de N é direito de quem está
              fazendo a prova — o backend preenche em branco (= errado) o
              que ficou pra trás ao finalizar, então a nota nunca mente
              sobre quantas foram respondidas de verdade. */}
          <button onClick={finalizar} className="link">
            finalizar agora
          </button>
          {onSair && (
            <button onClick={sair} className="link">
              sair
            </button>
          )}
        </div>
      </div>
      {pausado && (
        <p className="callout-info mb-3 !py-2 !px-3 text-[12.5px]">
          Pausado — o relógio parou. A questão continua aqui, sem pressa.
        </p>
      )}
      <TextoAssociado texto={q.contexto} ordem={q.ordem_no_contexto} />
      <div className="card">
        <p className="text-base font-medium leading-relaxed">{q.enunciado}</p>
      </div>
      {/* Item C/E: dois botões, e marcar JÁ AVANÇA. Numa prova Cebraspe de
          40 itens, exigir "marque e depois clique em próxima" dobra os
          cliques sem decidir nada — a escolha já é a resposta inteira. A
          correção continua no fim, como em qualquer simulado: o que muda é
          o formato de responder, não a regra de não corrigir durante. */}
      {q.tipo === "certo_errado" ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button
              onClick={() => proxima(false, "C")}
              disabled={salvando || pausado}
              className={`rounded-xl border py-3.5 text-[15px] font-medium transition-colors disabled:opacity-50 ${
                resposta === "C"
                  ? "border-success bg-surface-hover"
                  : "border-line-strong bg-surface hover:border-success hover:bg-surface-hover"
              }`}
            >
              Certo
            </button>
            <button
              onClick={() => proxima(false, "E")}
              disabled={salvando || pausado}
              className={`rounded-xl border py-3.5 text-[15px] font-medium transition-colors disabled:opacity-50 ${
                resposta === "E"
                  ? "border-accent bg-surface-hover"
                  : "border-line-strong bg-surface hover:border-accent hover:bg-surface-hover"
              }`}
            >
              Errado
            </button>
          </div>
          {erro && <p className="mt-2 text-sm text-danger">{erro}</p>}
          <div className="mt-3">
            <button onClick={() => proxima(true)} disabled={salvando || pausado} className="link">
              pular
            </button>
          </div>
        </>
      ) : (
        <>
          <textarea
            value={resposta}
            onChange={(e) => setResposta(e.target.value)}
            disabled={pausado}
            rows={4}
            className="field mt-4 disabled:opacity-60"
            placeholder={pausado ? "Pausado — retome pra continuar respondendo." : "Sua resposta…"}
          />
          {erro && <p className="mt-2 text-sm text-danger">{erro}</p>}
          <div className="mt-3 flex justify-between">
            <button onClick={() => proxima(true)} disabled={salvando || pausado} className="link">
              pular
            </button>
            <button
              onClick={() => proxima(false)}
              disabled={salvando || pausado || !resposta.trim()}
              className="btn-primary"
            >
              {salvando ? "salvando…" : indice + 1 < estado.questoes.length ? "próxima" : "finalizar"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
