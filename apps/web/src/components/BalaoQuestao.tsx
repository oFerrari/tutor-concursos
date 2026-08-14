"use client";

import { Questao } from "@/lib/api";
import { ResultadoQuestao } from "@/components/DialogoQuestao";
import { QuestaoInterativa } from "@/components/QuestaoInterativa";

/**
 * Os formatos que um concurso pode cobrar — não os que o backend já sabe
 * fazer. Existir aqui como tipo é o que deixa o balão despachar por formato
 * sem reescrever nada no dia em que o que falta ganhar dado de verdade.
 *
 * `resposta_livre` e `certo_errado` são REAIS desde a migração 012:
 * `questao.tipo` + `questao.gabarito_ce`, com CHECK casada no banco. Falta
 * só múltipla escolha, que precisa de tabela de alternativas — modelagem
 * inteira, não uma coluna, e por isso ficou de fora da 012 em vez de virar
 * um valor gravável e não renderizável.
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
export function BalaoQuestao({ tipo, questao, conversaId, onFechado, onSair }: Props) {
  if (tipo === "multipla_escolha") {
    return (
      <div className="callout-warning !p-4 text-sm">
        <p className="font-medium">Questão de múltipla escolha — ainda não existe no banco.</p>
        <p className="mt-1 opacity-90">
          Guardar alternativas exige tabela própria (texto, ordem e qual é a correta), não uma
          coluna. Enquanto ela não existir, este balão avisa em vez de inventar uma UI de
          alternativas sobre um gabarito que não as tem.
        </p>
      </div>
    );
  }

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
