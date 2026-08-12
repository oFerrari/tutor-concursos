"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CalendarClock, Layers, RotateCcw, type LucideIcon } from "lucide-react";
import {
  Carga,
  Desempenho,
  ErroApi,
  ErroCaderno,
  Meta,
  getCarga,
  getErros,
  getMeta,
  getStats,
  getSugestao,
  getToken,
  limparToken,
} from "@/lib/api";

function saudacaoPorHorario(): string {
  const h = new Date().getHours();
  if (h < 5) return "Boa noite";
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

/**
 * A tela inicial não é um dashboard estático — é o "professor proativo"
 * dando um panorama do dia com dados REAIS (carga, sugestão de
 * core/ritmo.py, meta do edital), nunca um número inventado no front. O
 * mesmo princípio de sempre neste projeto: "retenção/decisão imposta em
 * código, não no que a tela finge saber".
 */
export default function PaginaInicial() {
  const router = useRouter();
  const [nome] = useState(""); // sem endpoint de perfil com nome ainda — fica pro backend decidir, não o front
  const [carga, setCarga] = useState<Carga | null>(null);
  const [sugestao, setSugestao] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [pontosFracos, setPontosFracos] = useState<Desempenho[] | null>(null);
  const [erros, setErros] = useState<ErroCaderno[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    Promise.all([getCarga(), getStats(), getErros()])
      .then(([c, s, e]) => {
        setCarga(c);
        setPontosFracos([...s].sort((a, b) => (a.pct_acerto ?? -1) - (b.pct_acerto ?? -1)).slice(0, 3));
        setErros(e);
      })
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
      });
    // sugestão/meta são extras — não bloqueiam a tela se falharem (ex.: sem edital ainda)
    getSugestao().then((r) => setSugestao(r.sugestao)).catch(() => {});
    getMeta().then(setMeta).catch(() => {});
  }, [router]);

  if (erro) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <p className="callout-danger">{erro}</p>
      </div>
    );
  }

  if (!carga) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <p className="text-sm text-muted">carregando…</p>
      </div>
    );
  }

  const panorama =
    carga.atraso > 0
      ? `Você tem ${carga.atraso} revisão(ões) atrasada(s) — vamos recuperar o ritmo.`
      : carga.revisoes > 0
        ? `${carga.revisoes} revisão(ões) venceram hoje.`
        : "Nenhuma revisão vencida hoje — bom momento pra avançar em conteúdo novo.";

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6 md:p-10">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {saudacaoPorHorario()}{nome ? `, ${nome}` : ""}.
        </h1>
        <p className="mt-2 text-muted">{panorama}</p>
        {sugestao && <p className="mt-3 callout-info inline-block">💡 {sugestao}</p>}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metrica Icone={RotateCcw} rotulo="revisões vencidas" valor={carga.revisoes} destaque={carga.revisoes > 0} />
        <Metrica Icone={Layers} rotulo="inéditas na fila" valor={carga.ineditas} />
        <Metrica Icone={AlertTriangle} rotulo="caderno de erros" valor={erros?.length ?? "—"} />
        <Metrica
          Icone={CalendarClock}
          rotulo="dias até a prova"
          valor={meta?.dias_restantes ?? "—"}
          destaque={meta?.dias_restantes != null && meta.dias_restantes <= 14}
        />
      </div>

      <a href="/fila" className="btn-primary w-full sm:w-auto">
        começar sessão de hoje
      </a>

      {pontosFracos && pontosFracos.length > 0 && (
        <div className="widget">
          <h2 className="mb-3 text-sm font-medium text-muted">pontos de atenção</h2>
          <ul className="space-y-2">
            {pontosFracos.map((d) => (
              <li key={d.disciplina} className="flex items-center justify-between text-sm">
                <span>{d.disciplina}</span>
                <span className="tabular-nums text-muted">
                  {d.pct_acerto == null ? "sem tentativas" : `${d.pct_acerto.toFixed(0)}% de acerto`}
                </span>
              </li>
            ))}
          </ul>
          <a href="/stats" className="link mt-3 inline-block">
            ver desempenho completo →
          </a>
        </div>
      )}
    </div>
  );
}

function Metrica({
  Icone,
  rotulo,
  valor,
  destaque,
}: {
  Icone: LucideIcon;
  rotulo: string;
  valor: number | string;
  destaque?: boolean;
}) {
  return (
    <div className="widget">
      <Icone className={`h-4 w-4 ${destaque ? "text-accent" : "text-muted"}`} strokeWidth={1.75} />
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${destaque ? "text-accent" : ""}`}>{valor}</p>
      <p className="mt-1 text-xs text-muted">{rotulo}</p>
    </div>
  );
}
