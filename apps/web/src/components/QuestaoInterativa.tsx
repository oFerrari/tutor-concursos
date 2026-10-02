"use client";

import { DialogoQuestao, ResultadoQuestao } from "@/components/DialogoQuestao";
import { ItemCertoErrado } from "@/components/ItemCertoErrado";
import { ItemMultiplaEscolha } from "@/components/ItemMultiplaEscolha";
import { Questao } from "@/lib/api";

/**
 * Escolhe COMO uma questão é respondida, pelo tipo dela.
 *
 * Existe pelo mesmo motivo de `socratic.avaliar_questao` existir no
 * backend: há quatro telas que abrem questão (fila, /questao/[id], desafio,
 * tutor) e cada uma que esquecesse de olhar o tipo mostraria um item
 * Cebraspe com caixa de texto e três dicas — formato errado, correção
 * errada. Um lugar decide, quatro consomem.
 *
 * Múltipla escolha entrou com a migração 037 (questões de prova).
 */
export function QuestaoInterativa(props: {
  questao: Questao;
  rotuloContinuar?: string;
  /** Quando a questão é respondida dentro de uma conversa do tutor. */
  conversaId?: number;
  onFechado: (r: ResultadoQuestao) => void;
  onSair?: () => void;
}) {
  if (props.questao.tipo === "certo_errado") {
    return <ItemCertoErrado {...props} />;
  }
  if (props.questao.tipo === "multipla_escolha") {
    return <ItemMultiplaEscolha {...props} />;
  }
  return <DialogoQuestao {...props} />;
}
