"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { ErroApi, apagarConta } from "@/lib/api";

/**
 * Diálogo de exclusão de conta — irmão do `<Confirmar>`, mas não podia SER
 * um `<Confirmar>`: `DELETE /me` exige a senha atual mesmo com token válido
 * (`core/auth.py` — token vazado não deveria bastar pra apagar a conta), e
 * `<Confirmar>` não tem onde colocar um campo. Daí este componente próprio,
 * com a mesma cara (alertdialog, foco no cancelar, Esc fecha, clique fora
 * cancela) e um input de senha no meio.
 *
 * Existia SÓ o caminho do banco pra isto: apagar conta de teste era abrir
 * `docker exec psql` e rodar `DELETE FROM usuario` na mão. Serve pra sair de
 * verdade E pra quem criou conta só pra testar — os dois merecem um botão,
 * não um terminal.
 *
 * Sem prop `aberto`, de propósito: quem chama só MONTA isto quando o
 * diálogo deve aparecer (`{excluindo && <ExcluirConta ... />}`). Montagem
 * nova dá estado (senha/erro) limpo de graça pelo valor inicial do
 * `useState` — nada de `setState` dentro de efeito só pra resetar o que a
 * abertura anterior deixou sujo.
 */
export function ExcluirConta({
  onExcluida,
  onCancelar,
}: {
  /** A conta já foi apagada no servidor — quem chama decide pra onde ir
   *  (token já limpo por dentro, não precisa limpar de novo). */
  onExcluida: () => void;
  onCancelar: () => void;
}) {
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState(false);
  const senhaRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    senhaRef.current?.focus();
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") onCancelar();
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [onCancelar]);

  async function confirmar() {
    if (!senha) {
      setErro("Digite sua senha pra confirmar");
      return;
    }
    setExcluindo(true);
    setErro(null);
    try {
      await apagarConta(senha);
      onExcluida();
    } catch (e) {
      // Mesma mensagem que a API devolve pra senha errada (auth.ErroAuth) —
      // não inventa texto novo aqui.
      setErro(e instanceof ErroApi ? e.message : "Não deu pra apagar a conta");
      setExcluindo(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-5"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="excluir-conta-titulo"
    >
      <div className="absolute inset-0 bg-black/70" onClick={excluindo ? undefined : onCancelar} />

      <div className="relative w-full max-w-[420px] rounded-[18px] border border-line-strong bg-surface p-5 shadow-[var(--shadow-drawer)]">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-danger-soft text-danger">
            <AlertTriangle className="h-[18px] w-[18px]" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="excluir-conta-titulo" className="text-[16.5px] font-semibold leading-snug">
              Excluir sua conta
            </h2>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
              Apaga sua conta, progresso, tentativas, caderno de erros, simulados, mesas e
              editais. Não tem como desfazer.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                confirmar();
              }}
              className="mt-3.5"
            >
              <input
                ref={senhaRef}
                type="password"
                autoComplete="current-password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                placeholder="sua senha atual"
                disabled={excluindo}
                className="field"
              />
              {erro && <p className="callout-danger mt-2.5 !p-2.5 text-[12.5px]">{erro}</p>}
            </form>
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2.5">
          <button onClick={onCancelar} disabled={excluindo} className="btn-ghost">
            Cancelar
          </button>
          <button onClick={confirmar} disabled={excluindo} className="btn-perigo">
            {excluindo ? "Excluindo…" : "Excluir minha conta"}
          </button>
        </div>
      </div>
    </div>
  );
}
