"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

/**
 * A lista de matérias que se tira e se acrescenta — a mesma nas DUAS telas que
 * declaram o alvo de uma mesa: a curadoria de edital (011) e o edital manual
 * (017).
 *
 * Existe porque a duplicação era real e recente: ao criar a `/alvo` eu copiei o
 * bloco da curadoria em vez de extrair, e aí o mesmo componente visual passou a
 * viver em dois arquivos — é assim que os dois divergem no primeiro ajuste de
 * padding e o produto fica com duas listas parecidas mas diferentes.
 *
 * O que ele NÃO faz é uniformizar as duas telas à força. Elas mostram coisas
 * diferentes de propósito: a curadoria tem contagem de tópicos e o selo
 * "confira" (tópico demais pode ser cabeçalho que a leitura não reconheceu); o
 * alvo manual não tem tópico nenhum e usa o selo "sem material". Por isso
 * `contagem` e `selo` são por LINHA e opcionais — quem chama decide, o
 * componente só desenha.
 */
export type LinhaDisciplina = {
  nome: string;
  /** Número à direita. `undefined` esconde a coluna: alvo manual não tem tópico,
   *  e mostrar "—" ali prometeria um detalhamento que não existe. */
  contagem?: number;
  /** Etiqueta curta com explicação no `title`. Cada tela tem a sua. */
  selo?: { texto: string; titulo: string };
};

export function ListaDisciplinas({
  linhas,
  aoTirar,
  aoAdicionar,
  placeholderNovo,
  vazio,
  desabilitado = false,
}: {
  linhas: LinhaDisciplina[];
  /** Recebe o índice, não o nome: a curadoria aceita nomes repetidos vindos de
   *  um PDF mal lido, e apagar "por nome" tiraria as duas linhas de uma vez. */
  aoTirar: (indice: number) => void;
  /** Ausente esconde o campo de acrescentar — há telas que só tiram. */
  aoAdicionar?: (nome: string) => void;
  placeholderNovo?: string;
  vazio?: React.ReactNode;
  desabilitado?: boolean;
}) {
  const [nova, setNova] = useState("");

  return (
    <>
      {linhas.length === 0
        ? (vazio ?? (
            <p className="rounded-xl border border-dashed border-line-stronger px-4 py-6 text-center text-[13.5px] text-muted">
              Nenhuma matéria aqui.
            </p>
          ))
        : (
          <ul className="flex flex-col gap-2">
            {linhas.map((l, i) => (
              <li
                key={`${l.nome}-${i}`}
                className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-2.5"
              >
                <span className="min-w-0 flex-1 truncate text-[14px]">{l.nome}</span>
                {l.selo && (
                  <span
                    className="shrink-0 rounded-md border border-warning-line bg-warning-soft px-1.5 py-0.5 text-[10.5px] text-warning"
                    title={l.selo.titulo}
                  >
                    {l.selo.texto}
                  </span>
                )}
                {l.contagem !== undefined && (
                  <span className="mono-num shrink-0 text-[12px] text-subtle">
                    {l.contagem || "—"}
                  </span>
                )}
                <button
                  onClick={() => aoTirar(i)}
                  disabled={desabilitado}
                  aria-label={`tirar ${l.nome}`}
                  className="shrink-0 rounded-lg p-1 text-subtle transition-colors hover:bg-surface-hover hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <X className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}

      {aoAdicionar && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            // Normaliza aqui, uma vez: espaço duplo e quebra de linha colados de
            // PDF fariam o nome não casar com o acervo no ILIKE de
            // `mesa.filtro`, e o sintoma seria fila vazia sem explicação.
            const nome = nova.trim().replace(/\s+/g, " ");
            if (!nome) return;
            aoAdicionar(nome);
            setNova("");
          }}
          className="mt-3 flex gap-2"
        >
          <input
            value={nova}
            onChange={(e) => setNova(e.target.value)}
            maxLength={120}
            placeholder={placeholderNovo ?? "Acrescentar matéria"}
            className="field flex-1"
          />
          <button
            type="submit"
            disabled={!nova.trim() || desabilitado}
            className="btn-ghost shrink-0"
          >
            <Plus className="h-4 w-4" />
            adicionar
          </button>
        </form>
      )}
    </>
  );
}
