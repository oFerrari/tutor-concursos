import { RelatorioDisciplina, ResultadoSimulado, ErroSimulado } from "@/lib/api";
import { TabelaPorDisciplina } from "@/components/TabelaPorDisciplina";

export type RelatorioSimulado = {
  resultado: ResultadoSimulado;
  relatorio: RelatorioDisciplina[];
  erros: ErroSimulado[];
};

type Props = {
  relatorio: RelatorioSimulado;
  /** "3:04 de prova" — só existe na prova RECÉM-terminada (o relógio vive
   *  no estado do runner). Reabrindo pelo histórico não tem de onde tirar
   *  isso sem um round-trip extra só pra um número decorativo; omitir é
   *  melhor que inventar. */
  segundosTotal?: number;
  rotuloAcao: string;
  onAcao: () => void;
};

function formatarRelogio(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * O relatório de uma prova — extraído de `SimuladoRunner` pra ser
 * reaproveitado por QUEM REABRE uma prova já fechada pelo histórico
 * (`/simulado`, "ver revisão"). As duas telas usam o MESMO formato porque
 * são o mesmo dado (`GET /simulados/{id}/relatorio` lê exatamente o que
 * `POST .../finalizar` já tinha calculado) — a diferença é só quando cada
 * uma é chamada, nunca o que mostram.
 */
export function RelatorioProva({ relatorio, segundosTotal, rotuloAcao, onAcao }: Props) {
  const { resultado, relatorio: porDisciplina, erros } = relatorio;
  return (
    <div>
      <div className="card">
        <p className="text-lg font-medium">
          {resultado.acertos}/{resultado.total} corretas ({resultado.nota_pct}%)
        </p>
        <p className="text-sm text-muted">
          {resultado.parciais} parciais · {resultado.erros} erradas
          {segundosTotal != null && ` · ${formatarRelogio(segundosTotal)} de prova`}
        </p>
      </div>

      {porDisciplina.length > 0 && (
        <div className="mt-4">
          <TabelaPorDisciplina
            colunas={["Acertos", "%"]}
            linhas={porDisciplina.map((r) => ({
              disciplina: r.disciplina,
              a: `${r.acertos}/${r.questoes}`,
              b: `${r.pct}%`,
            }))}
          />
        </div>
      )}

      {erros.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-muted">Revisão</h2>
          <ul className="space-y-3">
            {erros.map((e, i) => (
              <li key={i} className="callout-warning !p-3">
                <p className="font-medium">{e.tema}</p>
                <p className="mt-1 opacity-80">Sua resposta: {e.resposta || "(em branco)"}</p>
                <p className="mt-1">Gabarito: {e.gabarito}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button onClick={onAcao} className="btn-primary mt-6">
        {rotuloAcao}
      </button>
    </div>
  );
}
