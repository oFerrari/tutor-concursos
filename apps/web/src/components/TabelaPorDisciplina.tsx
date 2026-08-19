import { X } from "lucide-react";

/**
 * Tabela "Disciplina + dois números à direita" — a forma que o /meta (tópicos e
 * cobertura) e o relatório de simulado (acertos e %) já usavam, cada um com sua
 * cópia do `<thead>`, do zebrado e do alinhamento.
 *
 * Extraído porque a repetição estava nos DETALHES que ninguém lembra de manter
 * iguais: `tabular-nums` na coluna numérica (sem isso o número dança de largura
 * a cada render), `text-right`, a borda de baixo em cada linha. É esse tipo de
 * coisa que divergiu primeiro nas duas cópias.
 *
 * A ação por linha é opcional e chega como render prop: o /meta remove matéria
 * do edital ali, o relatório não remove nada. Fixar um botão de X aqui obrigaria
 * o relatório a passar um `aoRemover` vazio, e prop que existe só pra ser
 * ignorada é convite pra alguém ligá-la sem querer.
 */
export type LinhaTabela = {
  disciplina: string;
  /** Já formatado por quem chama: "12", "3/8", "0%". A tabela não calcula. */
  a: string | number;
  b: string | number;
};

export function TabelaPorDisciplina({
  colunas,
  linhas,
  aoRemover,
  removendo = false,
}: {
  /** Rótulos das duas colunas numéricas, na ordem. */
  colunas: [string, string];
  linhas: LinhaTabela[];
  /** Ausente = tabela só de leitura. */
  aoRemover?: (disciplina: string) => void;
  removendo?: boolean;
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-line text-left text-muted">
          <th className="py-1.5">Disciplina</th>
          <th className="py-1.5 text-right">{colunas[0]}</th>
          <th className="py-1.5 text-right">{colunas[1]}</th>
          {aoRemover && <th className="w-8" />}
        </tr>
      </thead>
      <tbody>
        {linhas.map((l) => (
          <tr key={l.disciplina} className="border-b border-line">
            <td className="py-1.5">{l.disciplina}</td>
            <td className="py-1.5 text-right tabular-nums">{l.a}</td>
            <td className="py-1.5 text-right tabular-nums">{l.b}</td>
            {aoRemover && (
              <td className="w-8 py-1.5 text-right">
                <button
                  onClick={() => aoRemover(l.disciplina)}
                  disabled={removendo}
                  title={`Tirar ${l.disciplina}`}
                  className="text-subtle transition-colors hover:text-danger disabled:opacity-40"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
