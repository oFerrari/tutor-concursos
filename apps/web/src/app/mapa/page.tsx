"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { AlertTriangle, Search } from "lucide-react";
import {
  AssuntoDoMapa,
  DisciplinaDoMapa,
  EstadoDoAssunto,
  MapaDeDominio,
  getMapaDeDominio,
} from "@/lib/api";

/**
 * MAPA DE DOMÍNIO — o edital da mesa assunto por assunto (038, `core/dominio.py`).
 *
 * Desenho do protótipo "Mapa de Domínio v3": três visões (cobertura, revisões,
 * completo), filtros com contagem, busca, ciclo de revisão em nós e a gaveta do
 * assunto com o porquê da recomendação. Os dados são os do aluno: "estudado" é
 * ter lido o trecho com o tutor ou respondido questão do assunto; o ciclo é o da
 * questão mais fraca dele.
 *
 * O botão da gaveta não abre tela nova: manda a fala ao tutor ("me explica…",
 * "quero questões de…"), que já decide pela intenção o que fazer.
 *
 * LIGANDO: material ou edital novo é ligado ao edital em segundo plano; enquanto
 * isso a tela pergunta de novo a cada 8 s, no máximo 15 vezes (mesmo molde do
 * `MapaDoEdital`).
 */
const INTERVALO_MS = 8000;
const MAX_TENTATIVAS = 15;

type Visao = "cov" | "rev" | "full";
type Filtro =
  | "all" | "studied" | "in_progress" | "not_started" | "unread"
  | "today" | "overdue" | "no_review" | "stale" | "on_track" | "attention";

// Material com leitura abaixo do limiar: tem apostila do assunto e ela não foi lida.
const naoLido = (a: AssuntoDoMapa) => a.material_trechos > 0 && a.nivel !== "lido";

const CASA: Record<Filtro, (a: AssuntoDoMapa) => boolean> = {
  all: () => true,
  studied: (a) => a.estudado,
  in_progress: (a) => a.nivel === "contato",
  not_started: (a) => a.nivel === "nenhum",
  unread: naoLido,
  today: (a) => a.estado === "td",
  overdue: (a) => a.estado === "od",
  no_review: (a) => a.estado === "nr",
  stale: (a) => a.estado === "st",
  on_track: (a) => a.estado === "sc",
  attention: (a) => ["od", "st", "nr"].includes(a.estado) || naoLido(a),
};

const FILTROS: Record<Visao, [Filtro, string][]> = {
  cov: [["all", "Todos"], ["studied", "Estudados"], ["in_progress", "Em andamento"], ["not_started", "Não estudados"],
    ["unread", "Material não lido"]],
  rev: [["all", "Todos"], ["today", "Hoje"], ["overdue", "Atrasados"], ["no_review", "Sem revisão"],
    ["stale", "Sem contato"], ["on_track", "Em dia"]],
  full: [["all", "Todos"], ["attention", "Atenção"], ["not_started", "Não estudados"]],
};

const VAZIO_DISCIPLINA: Partial<Record<Filtro, string>> = {
  not_started: "Todo o conteúdo desta disciplina já foi começado.",
  studied: "Nenhum assunto desta disciplina foi estudado ainda.",
  in_progress: "Nenhum assunto em andamento nesta disciplina.",
  unread: "✓ Todo o material desta disciplina foi lido.",
  overdue: "✓ Tudo em dia. Nenhuma revisão atrasada.",
  today: "Nenhuma revisão prevista para hoje.",
  no_review: "Todos os assuntos estudados já entraram no ciclo de revisão.",
  stale: "Nenhum assunto sem contato recente.",
  on_track: "Nenhuma revisão em dia nesta disciplina.",
  attention: "✓ Nada pede atenção nesta disciplina.",
};

const VAZIO_GERAL: Partial<Record<Filtro, [string, string]>> = {
  overdue: ["✓ Tudo em dia", "Nenhuma revisão está atrasada."],
  not_started: ["✓ Edital começado", "Todo assunto já teve algum contato."],
  unread: ["✓ Material lido", "Todo o material ligado ao edital já foi lido."],
  attention: ["✓ Tudo em ordem", "Nenhum assunto precisa de atenção agora."],
};

const HIST: Record<string, [string, string]> = {
  c: ["Acerto", "var(--success)"],
  d: ["Acerto com dica", "var(--warning)"],
  e: ["Erro", "var(--danger)"],
};

const sem = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const dias = (n: number) => (n === 1 ? "1 dia" : `${n} dias`);
const atras = (n: number) => (n === 0 ? "Hoje" : n === 1 ? "Ontem" : `${n} dias atrás`);
const pct = (n: number, t: number) => (t ? Math.round((n / t) * 100) : 0);
// Abaixo disto o "dominado" se apoia em pouca coisa e a tela diz isso.
const EVIDENCIA_MINIMA = 3;
const poucaEvidencia = (a: AssuntoDoMapa) => a.dominado && a.questoes_distintas < EVIDENCIA_MINIMA;

function corAtual(e: EstadoDoAssunto) {
  return e === "od" ? "var(--danger)" : e === "td" || e === "st" ? "var(--warning)" : "var(--success)";
}

function rotuloRevisao(a: AssuntoDoMapa, curto = false): [string, string, number] {
  const faltam = a.proxima_em ?? 0;
  switch (a.estado) {
    case "ns":
      return ["não estudado", "var(--label)", 400];
    case "nr":
      return ["sem revisão", "var(--muted)", 400];
    case "sc":
      if (faltam === 1) return ["amanhã", "var(--body)", 500];
      return [curto ? `${faltam}d` : `em ${dias(faltam)}`, "var(--muted)", 400];
    case "td":
      return ["hoje", "var(--warning)", 600];
    case "od":
      return [curto ? "atrasado" : `atrasado ${-faltam}d`, "var(--danger)", 600];
    case "st":
      return [curto ? "sem contato" : "sem contato recente", "var(--warning)", 500];
  }
}

function porque(a: AssuntoDoMapa, d: DisciplinaDoMapa, depois: number): string {
  const ultimo = a.historico.slice(-1);
  const faltam = a.proxima_em ?? 0;
  // O material vem antes do ciclo: questão em dia com a apostila sem ler não é domínio.
  if (naoLido(a) && a.nivel === "contato") {
    return a.questoes_em_dia
      ? `Você acerta as questões, mas leu só ${a.leitura_pct}% do material deste assunto. Ele só conta como estudado — e dominado — depois da leitura.`
      : `Você leu ${a.leitura_pct}% do material deste assunto. Ele conta como estudado a partir de 70% lido.`;
  }
  if (a.nivel === "so_questoes" && a.estado === "nr") {
    return "Não há material deste assunto no seu acervo; ele conta pelas questões respondidas.";
  }
  switch (a.estado) {
    case "ns":
      return a.material_trechos
        ? `Você tem material deste assunto e ainda não começou. Estudá-lo leva ${d.nome} para ${depois}% estudado.`
        : `Não há material deste assunto no seu acervo. Suba uma apostila ou estude por questões; isso leva ${d.nome} para ${depois}% estudado.`;
    case "nr":
      return a.ultimo_contato != null
        ? `Você estudou este assunto há ${dias(a.ultimo_contato)}, mas ainda não respondeu questão dele — é a questão que coloca o assunto no ciclo de revisão.`
        : "Você estudou este assunto, mas ainda não respondeu questão dele.";
    case "od":
      return `${ultimo === "e" ? "Você errou este assunto na última sessão e a revisão prevista já venceu" : "A revisão prevista já venceu"} há ${dias(-faltam)}.`;
    case "td":
      return `A revisão deste assunto está prevista para hoje, no estágio de ${dias(a.estagio)}.`;
    case "st":
      return `Último contato há ${dias(a.ultimo_contato ?? 0)}. Para o estágio atual, o esperado seria um contato a cada ${dias(a.estagio)}, aproximadamente.`;
    case "sc":
      return ultimo === "c"
        ? `Sua última revisão foi bem-sucedida. Próximo contato recomendado em ${dias(faltam)}.`
        : `Você acertou com ajuda na última sessão: o assunto fica no mesmo estágio até acertar de primeira. Próximo contato em ${dias(faltam)}.`;
  }
}

// ---- Medidas do protótipo "Mapa de Domínio v3" (cores pelos tokens do app, que são
// as mesmas do protótipo; as que o tema não tem vão como valor literal do protótipo).

/** Os nós do ciclo (1, 3, 7, 15, 30, 90 dias). Na linha: 132 px, embaixo do nome. */
function Ciclo({ a, intervalos, grande = false }: { a: AssuntoDoMapa; intervalos: number[]; grande?: boolean }) {
  const idx = intervalos.indexOf(a.estagio);
  const cor = corAtual(a.estado);
  const fim = intervalos.length - 1;
  const no = (k: number) => {
    const atual = k === idx;
    const passou = k < idx;
    const tam = atual ? (grande ? 9 : 7) : grande ? 7 : 5;
    return {
      width: tam,
      height: tam,
      background: atual ? cor : passou ? "#5a5a62" : "#0e0e10",
      border: `1px solid ${atual ? cor : passou ? "#5a5a62" : "#33333a"}`,
      boxShadow: atual && grande ? `0 0 0 3px color-mix(in srgb, ${cor} 15%, transparent)` : "none",
    };
  };
  if (!grande) {
    return (
      <span className="relative flex h-[7px] w-[132px] items-center justify-between">
        <span className="absolute left-[3px] right-[3px] top-[3px] h-px bg-[#222228]" />
        <span className="absolute left-[3px] top-[3px] h-px bg-[#4a4a52]" style={{ width: `${(Math.max(0, idx) * 126) / fim}px` }} />
        {intervalos.map((s, k) => (
          <span key={s} className="relative rounded-full" style={no(k)} />
        ))}
      </span>
    );
  }
  return (
    <div className="relative flex justify-between">
      <span className="absolute left-[14px] right-[14px] top-[4px] h-px bg-[#222228]" />
      <span
        className="absolute left-[14px] top-[4px] h-px bg-[#4a4a52]"
        style={{ width: `calc((100% - 28px) * ${Math.max(0, idx) / fim})` }}
      />
      {intervalos.map((s, k) => (
        <span key={s} className="relative flex w-[28px] flex-col items-center gap-2">
          <span className="flex h-[9px] items-center">
            <span className="rounded-full" style={no(k)} />
          </span>
          <span
            className="font-mono text-[10.5px]"
            style={{ color: k === idx ? "var(--foreground)" : k < idx ? "var(--muted)" : "#4a4a52" }}
          >
            {s}d
          </span>
        </span>
      ))}
    </div>
  );
}

/** Ícone da linha: estudado (check verde) · em andamento (meio círculo) · nada (círculo). */
function Icone({ a, visao }: { a: AssuntoDoMapa; visao: Visao }) {
  if (visao === "rev") {
    const tocado = a.nivel !== "nenhum";
    return (
      <span
        className="ml-[5px] h-[5px] w-[5px] rounded-full"
        style={{ background: tocado ? (a.estagio ? corAtual(a.estado) : "#5a5a62") : "#2e2e34" }}
      />
    );
  }
  if (a.estudado) {
    return (
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
        <circle cx="8" cy="8" r="7.25" stroke="#2f6b52" strokeWidth="1.2" />
        <path d="m5 8.2 2 2 4-4.2" stroke="#3ecf8e" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (a.nivel === "contato") {
    return (
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
        <circle cx="8" cy="8" r="6.75" stroke="#5c4a1d" strokeWidth="1.3" />
        <path d="M8 1.25a6.75 6.75 0 0 1 0 13.5z" fill="#f5b83d" opacity="0.75" />
      </svg>
    );
  }
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="8" cy="8" r="6.75" stroke="#44444c" strokeWidth="1.3" />
    </svg>
  );
}

/** O que vai à direita do nome. Divide o MESMO espaço com o botão do hover (os dois
 *  ocupam a mesma célula, um some quando o outro aparece): passar o mouse não muda
 *  a largura do nome, então a linha não cresce. */
function direita(a: AssuntoDoMapa, visao: Visao): [string, string, number] | null {
  if (visao === "rev") return rotuloRevisao(a);
  if (visao === "full") return rotuloRevisao(a, true);
  if (a.leitura_pct != null && a.nivel !== "lido") {
    return [a.leitura_pct === 0 ? "material não lido" : `${a.leitura_pct}% lido`, "var(--subtle)", 400];
  }
  if (poucaEvidencia(a)) {
    return [a.questoes_distintas === 1 ? "1 questão" : `${a.questoes_distintas} questões`, "var(--subtle)", 400];
  }
  if (a.nivel === "so_questoes") return ["só por questões", "var(--subtle)", 400];
  return null;
}

export default function PaginaMapa() {
  const router = useRouter();
  const [mapa, setMapa] = useState<MapaDeDominio | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativas, setTentativas] = useState(0);
  const [visao, setVisao] = useState<Visao>("cov");
  const [filtro, setFiltro] = useState<Filtro>("all");
  const [busca, setBusca] = useState("");
  const [abertas, setAbertas] = useState<Record<string, boolean>>({});
  const [sel, setSel] = useState<number | null>(null);

  useEffect(() => {
    let vivo = true;
    getMapaDeDominio()
      .then((m) => {
        if (!vivo) return;
        setMapa(m);
        // A primeira disciplina com algo começado abre sozinha.
        setAbertas((a) => {
          if (Object.keys(a).length) return a;
          const d = m.disciplinas.find((x) => x.tocados > 0) ?? m.disciplinas[0];
          return d ? { [d.nome]: true } : a;
        });
      })
      .catch(() => vivo && setErro("Não deu para carregar o mapa agora."));
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

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setSel(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const todos = useMemo(() => mapa?.disciplinas.flatMap((d) => d.assuntos) ?? [], [mapa]);
  const conta = (f: Filtro) => todos.filter(CASA[f]).length;

  function irPara(v: Visao, f: Filtro = "all") {
    setVisao(v);
    setFiltro(f);
  }

  function pedirAoTutor(a: AssuntoDoMapa) {
    // Material sem ler vem antes de questão: é o que falta para o assunto contar.
    const fala = a.estado === "ns" || naoLido(a) ? `me explica ${a.item}` : `quero questões de ${a.item}`;
    router.push(`/tutor?q=${encodeURIComponent(fala)}`);
  }

  const casca = "mx-auto max-w-[820px] px-4 pb-20 pt-8 sm:px-6 sm:pb-24 sm:pt-[52px]";
  if (erro) return <div className={`${casca} text-[13.5px] text-muted`}>{erro}</div>;
  if (!mapa) return <div className={`${casca} text-[13.5px] text-muted`}>Carregando o mapa…</div>;
  if (!mapa.totais) {
    return (
      <div className={casca}>
        <h1 className="mb-2.5 text-[28px] font-semibold tracking-[-0.4px]">Mapa de domínio</h1>
        <p className="text-[14px] text-muted">
          Esta mesa ainda não tem edital. Suba o edital em Meu edital e o mapa mostra cada assunto dele.
        </p>
      </div>
    );
  }

  const q = sem(busca.trim());
  const buscando = q.length > 0;
  const forcado = buscando || filtro !== "all";
  const od = conta("overdue");
  const stl = conta("stale");
  const nr = conta("no_review");
  const nl = conta("unread");
  const atencao = conta("attention");
  const todasAbertas = mapa.disciplinas.every((d) => abertas[d.nome]);

  const visiveis = mapa.disciplinas.flatMap((d) => {
    const bateDisc = buscando && sem(d.nome).includes(q);
    const lista = d.assuntos.filter((a) => CASA[filtro](a) && (!buscando || bateDisc || sem(a.nome).includes(q)));
    if (buscando && lista.length === 0) return [];
    return [{ d, lista }];
  });
  const mostrados = visiveis.reduce((n, v) => n + v.lista.length, 0);
  const selecionado = sel != null ? mapa.disciplinas.flatMap((d) => d.assuntos.map((a) => ({ a, d }))).find((x) => x.a.id === sel) : null;
  const vazio = buscando
    ? ["Nenhum resultado", `Nenhum assunto encontrado para “${busca.trim()}”.`]
    : (VAZIO_GERAL[filtro] ?? ["Nada por aqui", "Nenhum assunto corresponde a este filtro."]);

  return (
    <div className={casca}>
      <h1 className="mb-2.5 text-[28px] font-semibold tracking-[-0.4px]">Mapa de domínio</h1>
      <div className="mb-7 flex flex-wrap gap-x-5 gap-y-1.5 text-[14px] text-muted">
        <span>
          <span className="font-medium text-foreground">{pct(mapa.totais.estudados, mapa.totais.total)}%</span> do edital estudado
        </span>
        <span>
          <span className="font-medium text-foreground">
            {mapa.totais.estudados} de {mapa.totais.total}
          </span>{" "}
          assuntos
        </span>
        {mapa.totais.em_andamento > 0 && (
          <span>
            <span className="font-medium text-foreground">{mapa.totais.em_andamento}</span> em andamento
          </span>
        )}
        <span>
          <span className="font-medium text-foreground">{mapa.totais.dominados}</span> dominados
        </span>
        <span>
          <span className="font-medium text-foreground">{mapa.totais.hoje}</span> revisões para hoje
        </span>
      </div>
      {ligando && <p className="-mt-4 mb-6 text-[12.5px] text-subtle">Ligando o seu material novo aos assuntos do edital…</p>}

      {atencao > 0 && (
        <div className="mb-8 flex flex-wrap items-center gap-x-3.5 gap-y-1.5 rounded-xl border border-line px-3.5 py-3 text-[13.5px]">
          <button type="button" onClick={() => irPara("full", "attention")} className="flex items-center gap-2 font-medium text-foreground">
            <AlertTriangle className="h-3.5 w-3.5 text-[#f5b83d]" strokeWidth={2.2} />
            {atencao} {atencao === 1 ? "ponto precisa" : "pontos precisam"} de atenção
          </button>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {(
              [
                [od, od === 1 ? "revisão atrasada" : "revisões atrasadas", "var(--danger)", "overdue"],
                [stl, "sem contato recente", "#f5b83d", "stale"],
                [nr, nr === 1 ? "estudado sem revisão" : "estudados sem revisão", "var(--body)", "no_review"],
                [nl, "com material não lido", "#f5b83d", "unread"],
              ] as [number, string, string, Filtro][]
            )
              .filter(([n]) => n > 0)
              .map(([n, rotulo, cor, f]) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => irPara(f === "unread" ? "cov" : "rev", f)}
                  className="text-[13px] text-muted underline decoration-[#33333a] underline-offset-[3px] hover:text-body"
                >
                  <span style={{ color: cor }}>{n}</span> {rotulo}
                </button>
              ))}
          </div>
        </div>
      )}

      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-0.5 rounded-[10px] border border-[#222228] p-[3px]">
          {(
            [
              ["cov", "Cobertura"],
              ["rev", "Revisões"],
              ["full", "Completo"],
            ] as [Visao, string][]
          ).map(([v, rotulo]) => (
            <button
              key={v}
              type="button"
              onClick={() => irPara(v)}
              className={`rounded-[7px] px-3.5 py-1.5 text-[13px] transition-colors ${visao === v ? "bg-[#1e1e22] font-medium text-foreground" : "text-muted"}`}
            >
              {rotulo}
            </button>
          ))}
        </div>
        <label className="flex min-w-[200px] flex-[0_1_280px] items-center gap-2 rounded-[10px] border border-[#222228] bg-[#0e0e10] px-3 py-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-subtle" strokeWidth={2.2} />
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar no edital…"
            className="min-w-0 flex-1 bg-transparent text-[13.5px] text-foreground outline-none placeholder:text-label"
          />
          {buscando && (
            <button type="button" onClick={() => setBusca("")} aria-label="Limpar busca" className="px-0.5 text-[15px] leading-none text-muted">
              ×
            </button>
          )}
        </label>
      </div>

      <div className="mb-9 flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap gap-1.5">
          {FILTROS[visao].map(([f, rotulo]) => (
            <button
              key={f}
              type="button"
              onClick={() => setFiltro(f)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-[11px] py-[5px] text-[12.5px] ${filtro === f ? "border-[#36363e] bg-[#1a1a1e] text-foreground" : "border-[#222228] text-[#a6a6ad]"}`}
            >
              {rotulo} <span className="font-mono text-[11px] text-subtle">{conta(f)}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => {
            setFiltro("all");
            setBusca("");
            setAbertas(todasAbertas ? {} : Object.fromEntries(mapa.disciplinas.map((d) => [d.nome, true])));
          }}
          className="py-1 text-[12.5px] text-muted"
        >
          {todasAbertas ? "Recolher todas" : "Expandir todas"}
        </button>
      </div>

      {mostrados === 0 && (
        <div className="border-t border-line-soft py-14 text-center">
          <div className="mb-1.5 text-[16px] font-medium">{vazio[0]}</div>
          <div className="text-[13.5px] text-muted">{vazio[1]}</div>
        </div>
      )}

      <div className="flex flex-col gap-9">
        {visiveis.map(({ d, lista }) => {
          const aberta = forcado || !!abertas[d.nome];
          const c = (f: Filtro) => d.assuntos.filter(CASA[f]).length;
          const resumo: [number, string, string][] =
            visao === "rev"
              ? ([
                  [c("on_track"), " em dia", "var(--muted)"],
                  [c("today"), " hoje", "#f5b83d"],
                  [c("overdue"), c("overdue") > 1 ? " atrasados" : " atrasado", "var(--danger)"],
                  [c("stale"), " sem contato", "#f5b83d"],
                  [c("no_review"), " sem revisão", "var(--muted)"],
                  [c("not_started"), c("not_started") > 1 ? " não estudados" : " não estudado", "var(--subtle)"],
                ] as [number, string, string][]).filter(([n]) => n > 0)
              : ([
                  [d.estudados, ` de ${d.total} assuntos estudados`, "var(--body)"],
                  [d.em_andamento, " em andamento", "#f5b83d"],
                  [d.dominados, d.dominados === 1 ? " dominado" : " dominados", "var(--success)"],
                  ...(visao === "full"
                    ? ([
                        [c("overdue"), c("overdue") > 1 ? " atrasados" : " atrasado", "var(--danger)"],
                        [c("today"), " hoje", "#f5b83d"],
                      ] as [number, string, string][])
                    : ([[d.material_nao_lido, " com material não lido", "var(--subtle)"]] as [number, string, string][])),
                ] as [number, string, string][]).filter(([n], i) => i === 0 || n > 0);
          return (
            <section key={d.nome}>
              <button
                type="button"
                onClick={() => !forcado && setAbertas((a) => ({ ...a, [d.nome]: !a[d.nome] }))}
                aria-expanded={aberta}
                className="flex w-full flex-col gap-2 border-b border-line pb-3.5 text-left text-foreground"
              >
                <span className="flex w-full items-baseline justify-between gap-4">
                  <span className="flex min-w-0 items-baseline gap-2.5">
                    <span
                      className="inline-block shrink-0 text-[9px] text-label transition-transform duration-[180ms]"
                      style={{ transform: aberta ? "rotate(90deg)" : "none" }}
                    >
                      ▶
                    </span>
                    <span className="text-[16px] font-semibold leading-[1.4] [text-wrap:pretty]">{d.nome}</span>
                  </span>
                  {visao !== "rev" && (
                    <span className="whitespace-nowrap text-[15px] font-medium">{pct(d.estudados, d.total)}%</span>
                  )}
                </span>
                <span className="flex flex-wrap gap-x-[7px] gap-y-0.5 pl-[19px] text-[12.5px] text-muted">
                  {resumo.map(([n, rotulo, cor], i) => (
                    <span key={rotulo} className="inline-flex gap-[7px]">
                      {i > 0 && <span className="text-[#3a3a42]">·</span>}
                      <span>
                        <span style={{ color: cor }}>{n}</span>
                        {rotulo}
                      </span>
                    </span>
                  ))}
                </span>
                {visao !== "rev" && (
                  // estudado (claro) + em andamento (escuro): o mesmo traço do protótipo
                  <span className="ml-[19px] flex h-[3px] overflow-hidden rounded-full bg-line-soft">
                    <span className="h-full bg-body transition-[width] duration-300" style={{ width: `${pct(d.estudados, d.total)}%` }} />
                    <span className="h-full bg-[#4a4a52] transition-[width] duration-300" style={{ width: `${pct(d.em_andamento, d.total)}%` }} />
                  </span>
                )}
              </button>
              {aberta && (
                <div className="flex flex-col pt-1.5">
                  {lista.map((a) => {
                    const dir = direita(a, visao);
                    const acao = visao === "cov" ? (a.nivel === "nenhum" ? "Estudar" : "Abrir") : null;
                    return (
                      <div
                        key={a.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSel(a.id)}
                        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setSel(a.id)}
                        className={`group -mx-2.5 grid cursor-pointer grid-cols-[16px_minmax(0,1fr)] gap-3.5 rounded-[10px] px-2.5 py-3 transition-colors duration-[120ms] ${sel === a.id ? "bg-[#141417]" : "hover:bg-[#111114]"}`}
                      >
                        <span className="flex h-[21px] items-center">
                          <Icone a={a} visao={visao} />
                        </span>
                        <span className="flex min-w-0 flex-col gap-2">
                          <span className="flex min-w-0 flex-col gap-x-4 gap-y-1 sm:flex-row sm:items-baseline">
                            <span
                              className={`min-w-0 flex-auto text-[14.5px] leading-[1.45] [text-wrap:pretty] ${a.nivel !== "nenhum" ? "text-foreground" : "text-muted"}`}
                            >
                              {a.nome}
                            </span>
                            {(dir || acao) && (
                              // MESMA CÉLULA para a informação e o botão do hover: nada muda de largura.
                              <span className="grid shrink-0 justify-items-end">
                                {dir && (
                                  <span
                                    className={`col-start-1 row-start-1 whitespace-nowrap text-[12.5px] leading-[1.6] ${acao ? "sm:group-hover:invisible" : ""}`}
                                    style={{ color: dir[1], fontWeight: dir[2] }}
                                  >
                                    {dir[0]}
                                  </span>
                                )}
                                {acao && (
                                  <span className="invisible col-start-1 row-start-1 self-center whitespace-nowrap rounded-full border border-[#2a2a30] px-2.5 py-0.5 text-[12px] leading-[1.3] text-body sm:group-hover:visible">
                                    {acao}
                                  </span>
                                )}
                              </span>
                            )}
                          </span>
                          {visao === "rev" && a.estagio > 0 && <Ciclo a={a} intervalos={mapa.intervalos} />}
                        </span>
                      </div>
                    );
                  })}
                  {lista.length === 0 && <div className="pb-1 pl-[30px] pt-4 text-[13.5px] text-muted">{VAZIO_DISCIPLINA[filtro] ?? ""}</div>}
                  {d.questoes_sem_assunto > 0 && filtro === "all" && !buscando && (
                    <div className="pb-1 pl-[30px] pt-3 text-[12.5px] text-subtle">
                      {d.questoes_sem_assunto} {d.questoes_sem_assunto === 1 ? "questão respondida" : "questões respondidas"} desta
                      disciplina sem assunto do edital identificado — contam no desempenho, não neste mapa.
                    </div>
                  )}
                </div>
              )}
            </section>
          );
        })}
      </div>

      {/* PORTAL: a área de conteúdo rola dentro de um contêiner próprio, e `fixed`
          ali dentro ficava preso a ele — com a lista rolada, a gaveta abria no topo
          do conteúdo, fora da vista (medido em 02/10/2026). */}
      {selecionado &&
        createPortal(
          <Gaveta
            a={selecionado.a}
            d={selecionado.d}
            intervalos={mapa.intervalos}
            aoFechar={() => setSel(null)}
            aoAgir={() => pedirAoTutor(selecionado.a)}
          />,
          document.body,
        )}
    </div>
  );
}

function Gaveta({
  a,
  d,
  intervalos,
  aoFechar,
  aoAgir,
}: {
  a: AssuntoDoMapa;
  d: DisciplinaDoMapa;
  intervalos: number[];
  aoFechar: () => void;
  aoAgir: () => void;
}) {
  const tocado = a.nivel !== "nenhum";
  const faltam = a.proxima_em ?? 0;
  const ultimo = a.historico ? HIST[a.historico.slice(-1)] : null;
  const depois = pct(d.estudados + 1, d.total);
  const titulo: Record<EstadoDoAssunto, [string, string]> = {
    ns: ["Ainda não estudado", "var(--muted)"],
    nr: [a.estudado ? "Estudado, ainda sem questão respondida" : "Em andamento, ainda sem questão respondida", "var(--body)"],
    sc: [faltam === 1 ? "Em dia · próxima revisão amanhã" : `Em dia · próxima revisão em ${dias(faltam)}`, "var(--success)"],
    td: ["Revisão prevista para hoje", "#f5b83d"],
    od: [`Revisão atrasada há ${dias(-faltam)}`, "var(--danger)"],
    st: ["Sem contato recente", "#f5b83d"],
  };
  // Material sem ler manda no título: é o que falta para o assunto contar.
  const [manchete, corManchete] =
    naoLido(a) && a.nivel === "contato" ? [`Em andamento · ${a.leitura_pct}% do material lido`, "#f5b83d"] : titulo[a.estado];
  const proxima: Record<EstadoDoAssunto, string> = {
    ns: "—",
    nr: "Ainda não agendada",
    sc: faltam === 1 ? "Amanhã" : `Em ${dias(faltam)}`,
    td: "Hoje",
    od: "Atrasada",
    st: "Recomendada agora",
  };
  const fatos: [string, string, string][] = tocado
    ? [
        ["Último contato", a.ultimo_contato != null ? atras(a.ultimo_contato) : "—", a.estado === "st" ? "#f5b83d" : "var(--foreground)"],
        ["Última sessão", ultimo ? ultimo[0] : "Nenhuma", ultimo ? ultimo[1] : "var(--muted)"],
        ["Próxima revisão", proxima[a.estado], a.estado === "od" ? "var(--danger)" : a.estado === "td" ? "#f5b83d" : "var(--foreground)"],
        ["Questões realizadas", a.questoes_distintas && a.questoes !== a.questoes_distintas
          ? `${a.questoes} (${a.questoes_distintas} diferentes)` : String(a.questoes), "var(--foreground)"],
      ]
    : [["Estudado na disciplina", `${pct(d.estudados, d.total)}% → ${depois}%`, "var(--foreground)"]];
  if (a.material_trechos) {
    fatos.push(["Material lido", `${a.leitura_pct}% · ${a.material_lidos} de ${a.material_trechos} trechos`,
      a.nivel === "lido" ? "var(--success)" : "var(--foreground)"]);
  }
  const acao: Record<EstadoDoAssunto, string> = {
    ns: "Estudar assunto",
    nr: "Fazer questões",
    sc: "Praticar assunto",
    td: "Revisar agora",
    od: "Revisar agora",
    st: "Revisar agora",
  };
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/55 [animation:mdFade_.18s_ease-out_both]" onClick={aoFechar} />
      <aside
        role="dialog"
        aria-label={a.nome}
        className="fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-full flex-col border-l border-line bg-[#0e0e10] [animation:mdIn_.24s_cubic-bezier(.2,.8,.2,1)_both] sm:w-[440px]"
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line-soft px-6 py-4">
          <span className="min-w-0 truncate font-mono text-[11px] uppercase tracking-[1.5px] text-subtle">{d.nome}</span>
          <button type="button" onClick={aoFechar} aria-label="Fechar" className="px-1.5 py-1 text-[20px] leading-none text-muted">
            ×
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-[30px] overflow-y-auto px-6 py-7">
          <div className="shrink-0">
            <h2 className="mb-2.5 text-[20px] font-semibold leading-[1.35] tracking-[-0.2px] [text-wrap:pretty]">{a.nome}</h2>
            <div className="text-[14px] font-medium" style={{ color: corManchete }}>
              {manchete}
            </div>
          </div>

          {tocado && (
            <div className="shrink-0">
              <div className="mb-3.5 flex items-baseline justify-between">
                <span className="text-[12px] text-subtle">Ciclo de revisão</span>
                <span className="text-[12px] text-muted">{a.estagio ? `estágio atual: ${dias(a.estagio)}` : "ainda fora do ciclo"}</span>
              </div>
              <Ciclo a={a} intervalos={intervalos} grande />
            </div>
          )}

          <div className="flex shrink-0 flex-col">
            {fatos.map(([k, v, cor]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-[#18181c] py-[11px] text-[13.5px]">
                <span className="text-muted">{k}</span>
                <span className="text-right" style={{ color: cor }}>
                  {v}
                </span>
              </div>
            ))}
          </div>

          {a.materiais.length > 0 && (
            <div className="shrink-0">
              <div className="mb-2.5 text-[12px] text-subtle">Onde está no seu material</div>
              <div className="flex flex-col gap-2">
                {a.materiais.map((m) => (
                  <div key={`${m.documento_id}-${m.assunto}`} className="flex items-baseline justify-between gap-3 text-[13.5px] text-body">
                    <span className="min-w-0">
                      {m.assunto}
                      <span className="text-subtle">
                        {" "}
                        · {m.material}
                        {m.pagina_inicio != null &&
                          `, p. ${m.pagina_inicio}${m.pagina_fim && m.pagina_fim !== m.pagina_inicio ? `–${m.pagina_fim}` : ""}`}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[11.5px]" style={{ color: m.lidos >= m.trechos ? "var(--success)" : "var(--subtle)" }}>
                      {pct(m.lidos, m.trechos)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {a.historico && (
            <div className="shrink-0">
              <div className="mb-2.5 text-[12px] text-subtle">Últimas sessões</div>
              <div className="flex flex-col gap-2">
                {a.historico
                  .split("")
                  .reverse()
                  .slice(0, 5)
                  .map((ch, i) => (
                    <div key={i} className="flex items-center gap-2.5 text-[13.5px] text-body">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: HIST[ch][1] }} />
                      {HIST[ch][0]}
                    </div>
                  ))}
              </div>
            </div>
          )}

          <div className="shrink-0 rounded-[10px] bg-[#131316] px-4 py-3.5">
            <div className="mb-1.5 text-[11.5px] text-subtle">Por que esta recomendação</div>
            <div className="text-[13.5px] leading-[1.55] text-body [text-wrap:pretty]">
              {porque(a, d, depois)}
              {poucaEvidencia(a) &&
                ` Este domínio se apoia em ${a.questoes_distintas === 1 ? "uma questão só" : `${a.questoes_distintas} questões`}: faça mais questões do assunto para confirmar.`}
            </div>
          </div>
        </div>
        <div className="shrink-0 border-t border-line-soft px-6 py-4">
          <button
            type="button"
            onClick={aoAgir}
            className="w-full rounded-xl bg-[#ff2f3a] p-[13px] text-[14px] font-semibold text-[#0a0a0b] hover:bg-accent-hover"
          >
            {naoLido(a) ? (a.material_lidos ? "Continuar a leitura" : "Ler o material") : acao[a.estado]}
          </button>
        </div>
      </aside>
    </>
  );
}
