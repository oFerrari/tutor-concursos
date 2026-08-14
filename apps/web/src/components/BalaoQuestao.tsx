"use client";

import { Questao } from "@/lib/api";
import { DialogoQuestao, ResultadoQuestao } from "@/components/DialogoQuestao";

/**
 * Os 3 formatos de questão que um concurso pode cobrar — não os 3 que o
 * backend já sabe fazer. Existir aqui como tipo é o que deixa o balão do
 * chat (/tutor) capaz de despachar por formato sem reescrever nada no dia
 * em que o segundo e o terceiro ganharem dado de verdade.
 */
export type TipoQuestao = "resposta_livre" | "multipla_escolha" | "certo_errado";

type Props = {
  tipo: TipoQuestao;
  questao: Questao;
  onFechado: (r: ResultadoQuestao) => void;
  onSair?: () => void;
};

const RUBRICA: Record<Exclude<TipoQuestao, "resposta_livre">, string> = {
  multipla_escolha: "múltipla escolha",
  certo_errado: "certo/errado",
};

/**
 * Dispatcher de tipo de questão dentro do balão de chat do /tutor.
 *
 * Hoje só "resposta_livre" tem questão de verdade por trás: `questao.gabarito`
 * no schema é texto aberto, avaliado por `socratic.avaliar()` — não existe
 * coluna de alternativas nem conceito de "certo/errado" em lugar nenhum do
 * banco. Por isso os outros dois cases não INVENTAM uma UI de múltipla
 * escolha sobre gabarito de texto (seria o mesmo erro que motivou tirar a
 * questão A/B/C mock daqui) — eles avisam que o tipo ainda não é real.
 *
 * A parte que reaproveita 100%: nenhuma lógica de avaliação, dica,
 * tentativa ou gravação foi reescrita — `resposta_livre` é literalmente o
 * `<DialogoQuestao>` que já roda em /questao/[id] e /desafio, só dentro de
 * um invólucro que cabe num balão de conversa em vez de página inteira.
 */
export function BalaoQuestao({ tipo, questao, onFechado, onSair }: Props) {
  if (tipo !== "resposta_livre") {
    return (
      <div className="callout-warning !p-4 text-sm">
        <p className="font-medium">Questão de {RUBRICA[tipo]} — ainda não existe no banco.</p>
        <p className="mt-1 opacity-90">
          O schema de <code className="font-mono">questao</code> só guarda gabarito em texto aberto. Assim
          que esse formato existir de verdade, este balão passa a renderizar a questão em vez deste aviso.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[14px] border border-line bg-surface px-[18px] py-4">
      <DialogoQuestao
        questao={questao}
        onFechado={onFechado}
        onSair={onSair}
        rotuloContinuar="Ok, entendi"
      />
    </div>
  );
}
