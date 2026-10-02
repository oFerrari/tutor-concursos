"use client";

import { Questao } from "@/lib/api";
import { ResultadoQuestao } from "@/components/DialogoQuestao";
import { QuestaoInterativa } from "@/components/QuestaoInterativa";

/**
 * Os formatos que um concurso pode cobrar — não os que o backend já sabe
 * fazer. Existir aqui como tipo é o que deixa o balão despachar por formato
 * sem reescrever nada no dia em que o que falta ganhar dado de verdade.
 *
 * Os três são REAIS: `resposta_livre` e `certo_errado` desde a 012, e
 * `multipla_escolha` desde a 037 (alternativas em `questao_alternativa`).
 */
export type TipoQuestao = "resposta_livre" | "multipla_escolha" | "certo_errado";

type Props = {
  tipo: TipoQuestao;
  questao: Questao;
  conversaId?: number;
  onFechado: (r: ResultadoQuestao) => void;
  onSair?: () => void;
};

/**
 * Invólucro de balão de conversa em volta da questão do /tutor.
 *
 * A parte que reaproveita 100%: nenhuma lógica de avaliação, dica,
 * tentativa ou gravação é reescrita aqui — quem decide entre diálogo
 * socrático e item C/E é `<QuestaoInterativa>`, o mesmo dispatcher que
 * /fila, /questao/[id] e /desafio usam. Este arquivo só cuida da moldura.
 */
export function BalaoQuestao({ questao, conversaId, onFechado, onSair }: Props) {
  return (
    <div className="overflow-hidden rounded-[14px] border border-line bg-surface px-[18px] py-4">
      <QuestaoInterativa
        questao={questao}
        conversaId={conversaId}
        onFechado={onFechado}
        onSair={onSair}
        rotuloContinuar="Ok, entendi"
      />
    </div>
  );
}
