"use client";

import { useRef, useState } from "react";
import {
  ErroApi,
  ErroSimulado,
  QuestaoSimulado,
  RelatorioDisciplina,
  ResultadoSimulado,
  responderSimulado,
} from "@/lib/api";

export type RelatorioSimulado = {
  resultado: ResultadoSimulado;
  relatorio: RelatorioDisciplina[];
  erros: ErroSimulado[];
};

type Props = {
  simuladoId: number;
  questoes: QuestaoSimulado[];
  onFinalizado: (r: RelatorioSimulado) => void;
  rotuloContinuar?: string;
};

/**
 * Responder → corrigir → relatório de um simulado já iniciado (a escolha de
 * N questões/minutos fica em `/simulado`, que é quem chama `POST /simulados`
 * antes de montar este componente). Extraído pra ser reaproveitado pelo
 * bloco 3 do desafio — mesmo espírito de `chat.simulado()` aceitar uma
 * lista pronta em vez de sempre sortear.
 */
export function SimuladoRunner({ simuladoId, questoes, onFinalizado, rotuloContinuar = "continuar" }: Props) {
  const [etapa, setEtapa] = useState<"respondendo" | "corrigindo" | "relatorio">("respondendo");
  const [indice, setIndice] = useState(0);
  const [resposta, setResposta] = useState("");
  const [respostas, setRespostas] = useState<{ questao_id: number; resposta: string; segundos: number }[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [relatorioFinal, setRelatorioFinal] = useState<RelatorioSimulado | null>(null);

  const inicioQuestao = useRef(Date.now());
  const inicioTotal = useRef(Date.now());

  function proxima(pular: boolean) {
    const segundos = Math.round((Date.now() - inicioQuestao.current) / 1000);
    const novasRespostas = [
      ...respostas,
      { questao_id: questoes[indice].id, resposta: pular ? "" : resposta, segundos },
    ];
    setRespostas(novasRespostas);
    setResposta("");
    inicioQuestao.current = Date.now();

    if (indice + 1 < questoes.length) {
      setIndice(indice + 1);
    } else {
      finalizar(novasRespostas);
    }
  }

  async function finalizarAgora() {
    if (respostas.length === 0) return; // nada respondido — não tem o que corrigir
    await finalizar(respostas);
  }

  async function finalizar(todasRespostas: typeof respostas) {
    setEtapa("corrigindo");
    const segundosTotal = Math.round((Date.now() - inicioTotal.current) / 1000);
    try {
      const r = await responderSimulado(simuladoId, todasRespostas, segundosTotal);
      setRelatorioFinal(r);
      setEtapa("relatorio");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra corrigir o simulado");
      setEtapa("respondendo");
    }
  }

  if (etapa === "corrigindo") {
    return <p className="text-sm opacity-60">corrigindo…</p>;
  }

  if (etapa === "relatorio" && relatorioFinal) {
    const { resultado, relatorio, erros } = relatorioFinal;
    return (
      <div>
        <div className="rounded border border-black/10 p-4">
          <p className="text-lg font-medium">
            {resultado.acertos}/{resultado.total} corretas ({resultado.nota_pct}%)
          </p>
          <p className="text-sm opacity-70">
            {resultado.parciais} parciais · {resultado.erros} erradas
          </p>
        </div>

        {relatorio.length > 0 && (
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b border-black/10 text-left opacity-60">
                <th className="py-1">disciplina</th>
                <th className="py-1 text-right">acertos</th>
                <th className="py-1 text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {relatorio.map((r) => (
                <tr key={r.disciplina} className="border-b border-black/5">
                  <td className="py-1">{r.disciplina}</td>
                  <td className="py-1 text-right tabular-nums">
                    {r.acertos}/{r.questoes}
                  </td>
                  <td className="py-1 text-right tabular-nums">{r.pct.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {erros.length > 0 && (
          <div className="mt-6">
            <h2 className="mb-2 text-sm font-medium opacity-70">revisão</h2>
            <ul className="space-y-3">
              {erros.map((e, i) => (
                <li key={i} className="rounded border border-amber-700/30 bg-amber-50 p-3 text-sm">
                  <p className="font-medium">{e.tema}</p>
                  <p className="mt-1 opacity-70">sua resposta: {e.resposta || "(em branco)"}</p>
                  <p className="mt-1">gabarito: {e.gabarito}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <button
          onClick={() => onFinalizado(relatorioFinal)}
          className="mt-6 rounded bg-black px-4 py-2 text-sm text-white"
        >
          {rotuloContinuar}
        </button>
      </div>
    );
  }

  const q = questoes[indice];
  return (
    <div>
      <div className="mb-4 flex items-center justify-between text-xs opacity-60">
        <span>
          {indice + 1}/{questoes.length} · {q.disciplina}
        </span>
        <button onClick={finalizarAgora} className="underline">
          finalizar agora
        </button>
      </div>
      <div className="rounded border border-black/10 p-4">
        <p>{q.enunciado}</p>
      </div>
      <textarea
        value={resposta}
        onChange={(e) => setResposta(e.target.value)}
        rows={4}
        className="mt-4 w-full rounded border border-black/20 p-3 text-sm"
        placeholder="sua resposta…"
      />
      {erro && <p className="mt-2 text-sm text-red-600">{erro}</p>}
      <div className="mt-3 flex justify-between">
        <button onClick={() => proxima(true)} className="text-sm underline opacity-60">
          pular
        </button>
        <button
          onClick={() => proxima(false)}
          disabled={!resposta.trim()}
          className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {indice + 1 < questoes.length ? "próxima" : "finalizar"}
        </button>
      </div>
    </div>
  );
}
