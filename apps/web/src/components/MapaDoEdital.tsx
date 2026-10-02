"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { getMapaDoEdital, MapaDoEdital as Mapa, SubitemDoEdital } from "@/lib/api";

/**
 * O edital ligado ao material, subitem por subitem (035, `core/cobertura.py`).
 *
 * É a promessa "domina o seu edital" na tela: para cada ponto do programa, em
 * que apostila e em que páginas ele está — ou que o material não o traz. Antes
 * a tela só tinha a porcentagem por disciplina, e a pergunta "o item 2.3 está
 * em algum material meu?" não tinha onde ser respondida.
 *
 * CONFERINDO: disciplina com material novo (ou edital recém-confirmado) é
 * conferida em segundo plano pelo servidor. Enquanto houver alguma, a tela
 * pergunta de novo a cada 8 s, no máximo 15 vezes — dois minutos cobrem uma
 * disciplina inteira; mais que isso, quem estiver olhando recarrega.
 */
const INTERVALO_MS = 8000;
const MAX_TENTATIVAS = 15;

const SELO: Record<SubitemDoEdital["estado"], { classe: string; rotulo: string }> = {
  coberto: { classe: "selo-ok", rotulo: "no seu material" },
  citado: { classe: "selo-processando", rotulo: "só citado" },
  sem_material: { classe: "selo-falha", rotulo: "sem material" },
  pendente: { classe: "badge-neutral", rotulo: "conferindo…" },
};

export function MapaDoEdital() {
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<string | null>(null);
  const [tentativas, setTentativas] = useState(0);

  useEffect(() => {
    let vivo = true;
    getMapaDoEdital()
      .then((m) => vivo && setMapa(m))
      .catch(() => vivo && setErro("Não deu para carregar o mapa do edital agora."));
    return () => {
      vivo = false;
    };
  }, [tentativas]);

  const conferindo = (mapa?.verificando.length ?? 0) > 0;
  useEffect(() => {
    if (!conferindo || tentativas >= MAX_TENTATIVAS) return;
    const t = setTimeout(() => setTentativas((n) => n + 1), INTERVALO_MS);
    return () => clearTimeout(t);
  }, [conferindo, tentativas]);

  if (erro) return <p className="mt-6 text-[13px] text-muted">{erro}</p>;
  if (!mapa || mapa.itens.length === 0) return null;

  return (
    <div className="mt-8">
      <h2 className="mb-1 text-sm font-medium text-muted">O que do edital está no seu material</h2>
      <p className="mb-3 text-[12.5px] text-subtle">
        Cada ponto do programa conferido contra as suas apostilas: onde está, ou que ainda não há
        material dele.
        {conferindo && ` Conferindo agora: ${mapa.verificando.join(", ")}.`}
      </p>
      <div className="space-y-2">
        {mapa.resumo
          .filter((r) => r.subitens > 0)
          .map((r) => {
            const itens = mapa.itens.filter((i) => i.disciplina === r.disciplina);
            const abertaAqui = aberta === r.disciplina;
            const pct = Math.round((100 * (r.cobertos + r.citados)) / r.subitens);
            return (
              <div key={r.disciplina} className="rounded-xl border border-line bg-surface">
                <button
                  type="button"
                  onClick={() => setAberta(abertaAqui ? null : r.disciplina)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left"
                  aria-expanded={abertaAqui}
                >
                  {abertaAqui ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] text-foreground">{r.disciplina}</span>
                    <span className="block text-[12px] text-muted">
                      {r.cobertos} de {r.subitens} no seu material
                      {r.citados > 0 && ` · ${r.citados} só citado${r.citados === 1 ? "" : "s"}`}
                      {r.sem_material > 0 && ` · ${r.sem_material} sem material`}
                      {r.pendentes > 0 && ` · ${r.pendentes} conferindo`}
                    </span>
                  </span>
                  <span className="w-24 shrink-0">
                    <span className="block h-1.5 overflow-hidden rounded-full bg-line">
                      <span className="block h-full bg-accent" style={{ width: `${pct}%` }} />
                    </span>
                  </span>
                </button>
                {abertaAqui && (
                  <div className="space-y-4 border-t border-line-soft px-4 py-3">
                    {itens.map((item) => (
                      <div key={item.topico_id}>
                        {/* Item sem lista de subitens tem UM subitem, que é o próprio
                            item: o título não se repete embaixo dele. */}
                        {!(item.subitens.length === 1 && item.subitens[0].texto === item.item) && (
                          <p className="mb-1.5 text-[13px] font-medium text-foreground">{item.item}</p>
                        )}
                        <ul className="space-y-1.5">
                          {item.subitens.map((s) => (
                            <li key={s.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                              <span className={SELO[s.estado].classe}>{SELO[s.estado].rotulo}</span>
                              <span className="text-[13px] text-foreground">{s.texto}</span>
                              {s.materiais.length > 0 && (
                                <span className="text-[12px] text-muted">
                                  {s.materiais
                                    .map((m) => (m.paginas ? `${m.assunto}, p. ${m.paginas}` : m.assunto))
                                    .join(" · ")}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
