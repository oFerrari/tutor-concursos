"use client";

import { useEffect, useRef, useState } from "react";
import {
  ErroApi,
  ErroSimulado,
  QuestaoSimulado,
  RelatorioDisciplina,
  ResultadoSimulado,
  responderSimulado,
} from "@/lib/api";
import { decorridos } from "@/lib/tempo";

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

  // Relógios em null, não em Date.now(): `useRef(Date.now())` avalia o
  // relógio A CADA render (o valor só é usado no primeiro, mas a chamada
  // acontece sempre) — é impureza de render de verdade, não implicância do
  // linter. Quem marca a largada é o efeito, depois do primeiro paint.
  const inicioQuestao = useRef<number | null>(null);
  const inicioTotal = useRef<number | null>(null);

  useEffect(() => {
    inicioTotal.current = Date.now();
  }, []);

  // Zerar o cronômetro da questão ao TROCAR de questão, em vez de na mão
  // dentro de proxima(): o gatilho verdadeiro é "apareceu outra questão na
  // tela", e isso é exatamente o que `indice` diz. Cobre o mount também.
  useEffect(() => {
    inicioQuestao.current = Date.now();
  }, [indice]);

  function proxima(pular: boolean) {
    const segundos = decorridos(inicioQuestao.current);
    const novasRespostas = [
      ...respostas,
      { questao_id: questoes[indice].id, resposta: pular ? "" : resposta, segundos },
    ];
    setRespostas(novasRespostas);
    setResposta("");

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
    const segundosTotal = decorridos(inicioTotal.current);
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
    return <p className="text-sm text-muted">corrigindo…</p>;
  }

  if (etapa === "relatorio" && relatorioFinal) {
    const { resultado, relatorio, erros } = relatorioFinal;
    return (
      <div>
        <div className="card">
          <p className="text-lg font-medium">
            {resultado.acertos}/{resultado.total} corretas ({resultado.nota_pct}%)
          </p>
          <p className="text-sm text-muted">
            {resultado.parciais} parciais · {resultado.erros} erradas
          </p>
        </div>

        {relatorio.length > 0 && (
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="py-1.5">disciplina</th>
                <th className="py-1.5 text-right">acertos</th>
                <th className="py-1.5 text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {relatorio.map((r) => (
                <tr key={r.disciplina} className="border-b border-line">
                  <td className="py-1.5">{r.disciplina}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    {r.acertos}/{r.questoes}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{r.pct.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {erros.length > 0 && (
          <div className="mt-6">
            <h2 className="mb-2 text-sm font-medium text-muted">revisão</h2>
            <ul className="space-y-3">
              {erros.map((e, i) => (
                <li key={i} className="callout-warning !p-3">
                  <p className="font-medium">{e.tema}</p>
                  <p className="mt-1 opacity-80">sua resposta: {e.resposta || "(em branco)"}</p>
                  <p className="mt-1">gabarito: {e.gabarito}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <button onClick={() => onFinalizado(relatorioFinal)} className="btn-primary mt-6">
          {rotuloContinuar}
        </button>
      </div>
    );
  }

  const q = questoes[indice];
  return (
    <div>
      <div className="mb-4 flex items-center justify-between text-xs text-muted">
        <span>
          {indice + 1}/{questoes.length} · {q.disciplina}
        </span>
        <button onClick={finalizarAgora} className="link">
          finalizar agora
        </button>
      </div>
      <div className="card">
        <p className="text-base font-medium leading-relaxed">{q.enunciado}</p>
      </div>
      <textarea
        value={resposta}
        onChange={(e) => setResposta(e.target.value)}
        rows={4}
        className="field mt-4"
        placeholder="sua resposta…"
      />
      {erro && <p className="mt-2 text-sm text-danger">{erro}</p>}
      <div className="mt-3 flex justify-between">
        <button onClick={() => proxima(true)} className="link">
          pular
        </button>
        <button onClick={() => proxima(false)} disabled={!resposta.trim()} className="btn-primary">
          {indice + 1 < questoes.length ? "próxima" : "finalizar"}
        </button>
      </div>
    </div>
  );
}
