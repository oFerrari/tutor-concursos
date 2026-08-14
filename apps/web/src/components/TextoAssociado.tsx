"use client";

/**
 * O "Texto associado" da prova do Cebraspe: a situação hipotética que
 * vários itens julgam (migração 013).
 *
 * Componente separado porque aparece em DOIS lugares com a mesma forma —
 * o item na fila/tutor e o item dentro do simulado — e porque ele tem uma
 * regra de leitura própria: o texto-base é para ser LIDO, o item é para ser
 * JULGADO, e a tela precisa deixar claro qual é qual. Sem separação visual,
 * o aluno lê a assertiva como continuação da situação e julga o texto
 * inteiro em vez do item.
 *
 * Devolve `null` quando não há contexto — item avulso continua sendo o caso
 * normal, e a maioria do acervo é assim.
 */
export function TextoAssociado({
  texto,
  ordem,
}: {
  texto: string | null;
  ordem: number | null;
}) {
  if (!texto) return null;
  return (
    <div className="mb-3 rounded-[14px] border border-line bg-surface-hover px-[18px] py-4">
      <p className="rotulo mb-2">
        texto associado{ordem ? ` · item ${ordem}` : ""}
      </p>
      {/* `whitespace-pre-line`: a situação pode vir com quebras (proposições
          A, B e C em linhas próprias, como na prova). Colapsar isso num
          parágrafo só embaralharia exatamente o que precisa ficar separado. */}
      <p className="whitespace-pre-line text-[14.5px] leading-relaxed text-body">{texto}</p>
    </div>
  );
}
