"use client";

import { Carga, Desempenho } from "@/lib/api";

/**
 * A faixa de quatro KPIs do protótipo — acerto geral, ofensiva, revisões
 * hoje, tempo médio.
 *
 * Mora num componente só porque aparece em DUAS telas (panorama e
 * desempenho), e KPI duplicado é a mesma armadilha de `mesa.filtro`: duas
 * cópias da regra divergem, e o sintoma seria o painel afirmar 62% de
 * acerto enquanto a tela de desempenho, logo ao lado no menu, afirma
 * outro. Um lugar só calcula, as duas telas exibem.
 *
 * Os quatro números são MEDIDOS: `pct_acerto`/`tentativas` vêm da view
 * `v_desempenho_disciplina` (por `/stats`), e ofensiva, revisões e tempo
 * médio de `scheduler.carga_hoje()` (por `/carga`). O protótipo trazia
 * junto "recorde: 21 dias" e "+4 pts vs. mês anterior" — os dois ficaram
 * de fora porque não existem no schema: ninguém guarda a maior ofensiva
 * já feita nem fecha o mês anterior pra comparar. Inventar a nota debaixo
 * de um número verdadeiro é o jeito mais rápido de fazer o número
 * verdadeiro parecer decorativo também.
 */
function formatarTempoMedio(segundos: number): string {
  const s = Math.round(segundos);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Acerto do usuário no recorte da mesa: soma as tentativas de todas as
 *  disciplinas, não a média dos percentuais — disciplina com 3 tentativas
 *  pesaria igual a uma com 300. */
export function agregar(desempenho: Desempenho[] | null) {
  const comAcerto = (desempenho ?? []).filter((d) => d.pct_acerto != null);
  const tentativas = comAcerto.reduce((s, d) => s + d.tentativas, 0);
  const acertos = comAcerto.reduce((s, d) => s + d.acertos, 0);
  return {
    tentativas,
    acertos,
    pct: tentativas > 0 ? (100 * acertos) / tentativas : null,
  };
}

export function Kpis({
  carga,
  desempenho,
}: {
  carga: Carga | null;
  desempenho: Desempenho[] | null;
}) {
  if (!carga) return null;
  const geral = agregar(desempenho);

  const kpis = [
    {
      rotulo: "acerto geral",
      valor: geral.pct == null ? "—" : `${geral.pct.toFixed(0)}%`,
      nota:
        geral.tentativas > 0
          ? `${geral.acertos} de ${geral.tentativas} ${geral.tentativas === 1 ? "tentativa" : "tentativas"}`
          : "sem tentativa ainda",
      cor: "var(--foreground)",
    },
    {
      rotulo: "ofensiva",
      valor: `${carga.ofensiva_dias} ${carga.ofensiva_dias === 1 ? "dia" : "dias"}`,
      nota: carga.ofensiva_dias > 0 ? "sequência ativa" : "estude hoje pra começar",
      cor: "var(--foreground)",
    },
    {
      rotulo: "revisões hoje",
      valor: String(carga.revisoes),
      nota: carga.atraso > 0 ? `${carga.atraso} em atraso` : "fila SM-2 em dia",
      cor: carga.revisoes > 0 ? "var(--accent-text)" : "var(--foreground)",
    },
    {
      rotulo: "tempo médio",
      valor: formatarTempoMedio(carga.tempo_medio_segundos),
      nota: "por questão",
      cor: "var(--foreground)",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {kpis.map((k) => (
        <div key={k.rotulo} className="rounded-[14px] border border-line bg-surface px-[18px] py-4">
          <p className="rotulo mb-2">{k.rotulo}</p>
          <p className="text-[25px] font-semibold tabular-nums" style={{ color: k.cor }}>
            {k.valor}
          </p>
          <p className="mt-0.5 text-[12.5px] text-muted">{k.nota}</p>
        </div>
      ))}
    </div>
  );
}
