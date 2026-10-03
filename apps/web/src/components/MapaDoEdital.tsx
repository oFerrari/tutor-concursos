"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import { getMapaDeDominio, MapaDeDominio } from "@/lib/api";

/**
 * O edital ligado ao material, assunto por assunto — com as MESMAS contas do Mapa
 * de domínio (`core/dominio.py`).
 *
 * Até 02/10/2026 este quadro vinha da conferência por SUBITEM (035): contava outra
 * coisa (87 subitens onde o edital tem 5 assuntos de Direito Penal) e dava "sem
 * material" para quase tudo, inclusive onde havia apostila. Duas telas contando
 * diferente o mesmo edital é o defeito; agora a ligação é a do índice do material
 * (038), que diz também quanto de cada material já foi lido.
 *
 * LIGANDO: material ou edital novo é ligado em segundo plano; a tela pergunta de
 * novo a cada 8 s, no máximo 15 vezes.
 */
const INTERVALO_MS = 8000;
const MAX_TENTATIVAS = 15;

const paginas = (i: number | null, f: number | null) =>
  i == null ? "" : `, p. ${i}${f && f !== i ? `–${f}` : ""}`;

export function MapaDoEdital() {
  const [mapa, setMapa] = useState<MapaDeDominio | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<string | null>(null);
  const [tentativas, setTentativas] = useState(0);

  useEffect(() => {
    let vivo = true;
    getMapaDeDominio()
      .then((m) => vivo && setMapa(m))
      .catch(() => vivo && setErro("Não deu para carregar o mapa do edital agora."));
    return () => {
      vivo = false;
    };
  }, [tentativas]);

  const ligando = mapa?.ligando ?? false;
  useEffect(() => {
    if (!ligando || tentativas >= MAX_TENTATIVAS) return;
    const t = setTimeout(() => setTentativas((n) => n + 1), INTERVALO_MS);
    return () => clearTimeout(t);
  }, [ligando, tentativas]);

  if (erro) return <p className="mt-6 text-[13px] text-muted">{erro}</p>;
  if (!mapa || !mapa.totais) return null;

  return (
    <div className="mt-8">
      <h2 className="mb-1 text-sm font-medium text-muted">O que do edital está no seu material</h2>
      <p className="mb-3 text-[12.5px] text-subtle">
        {mapa.totais.com_material} de {mapa.totais.total} assuntos do edital têm material seu — onde está e quanto
        você já leu. O mesmo cálculo do{" "}
        <Link href="/mapa" className="link">
          Mapa de domínio
        </Link>
        .{ligando && " Ligando o material novo aos assuntos…"}
      </p>
      <div className="space-y-2">
        {mapa.disciplinas.map((d) => {
          const abertaAqui = aberta === d.nome;
          const lidos = d.com_material - d.material_nao_lido;
          return (
            <div key={d.nome} className="rounded-xl border border-line bg-surface">
              <button
                type="button"
                onClick={() => setAberta(abertaAqui ? null : d.nome)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
                aria-expanded={abertaAqui}
              >
                {abertaAqui ? (
                  <ChevronDown className="h-4 w-4 shrink-0 text-muted" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] text-foreground">{d.nome}</span>
                  <span className="block text-[12px] text-muted">
                    {d.com_material} de {d.total} assuntos com material
                    {d.com_material > 0 && ` · ${lidos} lido${lidos === 1 ? "" : "s"}`}
                    {d.total - d.com_material > 0 && ` · ${d.total - d.com_material} sem material`}
                  </span>
                </span>
                <span className="w-24 shrink-0">
                  <span className="flex h-1.5 overflow-hidden rounded-full bg-line">
                    <span className="h-full bg-success" style={{ width: `${(100 * lidos) / d.total}%` }} />
                    <span className="h-full bg-warning" style={{ width: `${(100 * d.material_nao_lido) / d.total}%` }} />
                  </span>
                </span>
              </button>
              {abertaAqui && (
                <ul className="space-y-2 border-t border-line-soft px-4 py-3">
                  {d.assuntos.map((a) => (
                    <li key={a.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span
                        className={
                          a.material_trechos === 0 ? "selo-falha" : a.nivel === "lido" ? "selo-ok" : "selo-processando"
                        }
                      >
                        {a.material_trechos === 0 ? "sem material" : `${a.leitura_pct}% lido`}
                      </span>
                      <span className="text-[13px] text-foreground">{a.item}</span>
                      {a.materiais.length > 0 && (
                        <span className="text-[12px] text-muted">
                          {a.materiais
                            .slice(0, 4)
                            .map((m) => `${m.material} · ${m.assunto}${paginas(m.pagina_inicio, m.pagina_fim)}`)
                            .join(" — ")}
                          {a.materiais.length > 4 && ` — e mais ${a.materiais.length - 4}`}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
