"use client";

import { Link2, Trash2, UploadCloud } from "lucide-react";
import { MATERIAIS_EXEMPLO, StatusMaterial } from "@/mock/prototipo";

/**
 * "Minha biblioteca" — alimentar o RAG com PDF próprio.
 *
 * ⚠ TELA DE VITRINE. A lista vem de `MATERIAIS_EXEMPLO`.
 *
 * TODO(backend): faltam `POST /materiais` (upload → `ingest.py`) e
 * `GET /materiais` (lista com contagem de chunks e estado). O caminho já
 * existe do lado do Python — `ingest.py` faz chunking + embedding e grava
 * em `documento`/`chunk`; o que não existe é a rota HTTP nem uma coluna de
 * estado de processamento (hoje a ingestão é síncrona e por CLI, então
 * "IA lendo e processando…" não tem onde ser lido).
 *
 * Cuidado que vale registrar antes de implementar: `ingest.py` recusa
 * gravar como `--tipo lei` quando a taxa de colisão de artigo passa de 5%
 * (material com "Redação Anterior" cai em `historico`). Essa decisão é do
 * ingestor, não do usuário — a tela precisa REPORTAR o que foi decidido,
 * não perguntar antes.
 */

const CLASSE_SELO: Record<StatusMaterial, string> = {
  ativo: "selo-ok",
  processando: "selo-processando",
  falha: "selo-falha",
};

export default function PaginaMateriais() {
  return (
    <div className="mx-auto w-full max-w-[940px] px-6 pb-10 pt-6">
      <h1 className="text-[27px] tracking-[-0.3px]">Minha biblioteca</h1>
      <p className="mb-5 mt-1.5 text-[14.5px] text-muted">
        Alimente sua IA com seus PDFs, anotações e resumos privados. Só você tem acesso a este material.
      </p>

      <p className="callout-info mb-5">
        <span className="font-semibold text-accent-text">vitrine · </span>
        a lista abaixo é exemplo do protótipo. O upload ainda não tem rota na API — hoje a ingestão de
        material roda pela CLI (<span className="font-mono text-[12.5px]">ingest.py</span>). Para o PDF do
        edital, que já tem rota, use <span className="font-mono text-[12.5px]">/onboarding</span>.
      </p>

      <div className="drop">
        <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent-text">
          <UploadCloud className="h-[21px] w-[21px]" strokeWidth={2.2} />
        </span>
        <p className="mb-1.5 text-[15.5px] font-medium">Arraste seus PDFs aqui</p>
        <p className="text-[13.5px] text-muted">
          Eu leio, divido em trechos e indexo para usar nas suas respostas
        </p>
      </div>

      <div className="mt-3 flex items-center gap-2.5 rounded-xl border border-line-strong bg-surface-input px-3 py-2.5">
        <Link2 className="h-4 w-4 shrink-0 text-subtle" strokeWidth={2.2} />
        <input
          disabled
          placeholder="Ou cole o link de um site ou lei seca aqui"
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-subtle"
        />
        <button disabled className="btn-primary shrink-0 text-[12.5px]">
          Indexar
        </button>
      </div>

      <p className="rotulo mb-2.5 mt-7">processamento</p>

      <div className="overflow-hidden rounded-2xl border border-line bg-surface">
        <div className="grid grid-cols-[minmax(0,1fr)_110px_190px_34px] gap-3 border-b border-line-soft px-5 py-3 font-mono text-[10.5px] uppercase tracking-[1.5px] text-label max-md:grid-cols-[minmax(0,1fr)_70px_104px_24px]">
          <div>Arquivo</div>
          <div>Envio</div>
          <div>Status</div>
          <div />
        </div>

        {MATERIAIS_EXEMPLO.map((m) => (
          <div
            key={m.arquivo}
            className="grid grid-cols-[minmax(0,1fr)_110px_190px_34px] items-center gap-3 border-b border-line-soft px-5 py-3.5 transition-colors last:border-b-0 hover:bg-surface-raised max-md:grid-cols-[minmax(0,1fr)_70px_104px_24px]"
          >
            <div className="min-w-0">
              <p className="truncate text-[13.5px]">{m.arquivo}</p>
              <p className="mt-0.5 font-mono text-[11px] text-label">{m.detalhe}</p>
            </div>
            <div className="font-mono text-[12px] text-muted">{m.data}</div>
            <div>
              <span className={CLASSE_SELO[m.status]}>
                <span
                  className={`selo-ponto ${m.status === "processando" ? "animate-[pxPulse_1.2s_ease-in-out_infinite]" : ""}`}
                />
                {m.rotulo}
              </span>
            </div>
            <button
              disabled
              className="flex h-6 w-6 items-center justify-center rounded-[7px] text-label transition-colors hover:bg-surface-hover"
              aria-label="remover material"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
