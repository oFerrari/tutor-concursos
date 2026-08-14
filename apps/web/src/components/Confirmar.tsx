"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * Diálogo de confirmação com a cara do produto, no lugar de
 * `window.confirm`.
 *
 * Não é só estética. O `confirm` do browser tem três defeitos concretos
 * aqui: ele estampa "localhost:3000 diz" acima do texto (o produto some e
 * vira uma URL), não distingue ação destrutiva de ação comum (o "OK" de
 * apagar uma mesa tem o mesmo peso do "OK" de qualquer coisa), e não deixa
 * formatar — o parágrafo sobre o progresso NÃO ser apagado, que é
 * justamente o que tira o medo de clicar, sai como texto corrido no meio.
 *
 * Além disso `confirm` BLOQUEIA a thread principal: enquanto a caixa está
 * aberta, nenhum estado do React atualiza. Numa tela que está buscando
 * mesas em paralelo, isso congela tudo até a pessoa decidir.
 *
 * Acessibilidade não é enfeite num diálogo destrutivo: `role="alertdialog"`
 * faz o leitor de tela anunciar como aviso e não como região qualquer; o
 * foco vai pro botão de CANCELAR (não pro de apagar — o gesto perigoso não
 * deve estar sob o Enter distraído); e Esc fecha, porque toda saída de
 * emergência precisa do gesto que todo mundo já conhece.
 */
export function Confirmar({
  aberto,
  titulo,
  descricao,
  detalhe,
  rotuloConfirmar = "Confirmar",
  rotuloCancelar = "Cancelar",
  destrutivo = false,
  onConfirmar,
  onCancelar,
}: {
  aberto: boolean;
  titulo: string;
  descricao: React.ReactNode;
  /** Linha secundária — o que NÃO acontece. É o que tira o medo de clicar. */
  detalhe?: React.ReactNode;
  rotuloConfirmar?: string;
  rotuloCancelar?: string;
  destrutivo?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  const cancelar = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!aberto) return;
    cancelar.current?.focus();
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") onCancelar();
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [aberto, onCancelar]);

  if (!aberto) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-5"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirmar-titulo"
    >
      {/* Clicar fora cancela — nunca confirma. Toque acidental fora de um
          diálogo destrutivo tem que ser a saída segura, não a perigosa. */}
      <div className="absolute inset-0 bg-black/70" onClick={onCancelar} />

      <div className="relative w-full max-w-[420px] rounded-[18px] border border-line-strong bg-surface p-5 shadow-[var(--shadow-drawer)]">
        <div className="flex items-start gap-3">
          {destrutivo && (
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-danger-soft text-danger">
              <AlertTriangle className="h-[18px] w-[18px]" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id="confirmar-titulo" className="text-[16.5px] font-semibold leading-snug">
              {titulo}
            </h2>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{descricao}</p>
            {detalhe && (
              <p className="mt-2.5 rounded-xl border border-line bg-surface-hover px-3 py-2.5 text-[12.5px] leading-relaxed text-body">
                {detalhe}
              </p>
            )}
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2.5">
          <button ref={cancelar} onClick={onCancelar} className="btn-ghost">
            {rotuloCancelar}
          </button>
          <button
            onClick={onConfirmar}
            className={destrutivo ? "btn-perigo" : "btn-primary"}
          >
            {rotuloConfirmar}
          </button>
        </div>
      </div>
    </div>
  );
}
