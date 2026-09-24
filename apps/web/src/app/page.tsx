"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUp } from "lucide-react";
import { Kpis } from "@/components/Kpis";
import {
  Carga,
  Desempenho,
  ErroApi,
  ErroCaderno,
  Mesa,
  Meta,
  Usuario,
  getCarga,
  getErros,
  getMe,
  getMesaAtual,
  getMeta,
  getStats,
  getSugestao,
  getToken,
} from "@/lib/api";
import { sair } from "@/lib/cache";

function saudacao(): string {
  const h = new Date().getHours();
  if (h < 5) return "boa noite";
  if (h < 12) return "bom dia";
  if (h < 18) return "boa tarde";
  return "boa noite";
}

/** Primeiro nome a partir do e-mail — dado real do usuário, não um nome
 *  inventado. Sem endpoint de perfil com nome próprio, é o melhor que
 *  existe; se um dia houver campo `nome`, troca aqui e some esta função. */
function primeiroNome(email: string | undefined): string {
  if (!email) return "";
  const bruto = (email.split("@")[0] ?? "").split(/[._-]/)[0] ?? "";
  return bruto ? bruto.charAt(0).toUpperCase() + bruto.slice(1).toLowerCase() : "";
}

function corDoPct(pct: number): string {
  if (pct < 50) return "var(--accent)";
  if (pct < 75) return "var(--body)";
  return "var(--success)";
}

/**
 * Panorama — a tela de abertura do protótipo.
 *
 * TODO número aqui é MEDIDO: vem de `/carga`, `/stats`, `/erros`, `/meta`
 * e `/sugestao`. O protótipo mostrava também "ofensiva 12 dias" e "tempo
 * médio 1m48s" entre os KPIs; nenhum dos dois existe no schema (não há
 * sequência de dias, e `tentativa.segundos` não é exposto agregado), então
 * saíram em vez de virarem número decorativo ao lado de número real — a
 * mesma regra que rege `socratic.explicar()` no backend.
 */
export default function PaginaPanorama() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  // Só pra saber SE há alvo — o número é o mesmo com ou sem, o que muda
  // é o que ele significa, e o rótulo precisa dizer qual dos dois é.
  const [mesa, setMesa] = useState<Mesa | null>(null);
  const [carga, setCarga] = useState<Carga | null>(null);
  const [sugestao, setSugestao] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [desempenho, setDesempenho] = useState<Desempenho[] | null>(null);
  const [erros, setErros] = useState<ErroCaderno[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [pergunta, setPergunta] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    Promise.all([getCarga(), getStats(), getErros()])
      .then(([c, s, e]) => {
        setCarga(c);
        setDesempenho(s);
        setErros(e);
      })
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          sair();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
      });
    // extras — falhar aqui não deve derrubar a tela (ex.: sem edital ingerido)
    getMe().then(setUsuario).catch(() => {});
    getMesaAtual().then(setMesa).catch(() => {});
    getSugestao().then((r) => setSugestao(r.sugestao)).catch(() => {});
    getMeta().then(setMeta).catch(() => {});
  }, [router]);

  if (erro) {
    return (
      <div className="mx-auto max-w-[1000px] p-6">
        <p className="callout-danger">{erro}</p>
      </div>
    );
  }

  if (!carga || !desempenho || !erros) {
    return (
      <div className="mx-auto max-w-[1000px] p-6">
        <p className="rotulo animate-[pxPulse_1.4s_ease-in-out_infinite]">carregando</p>
      </div>
    );
  }

  const comDado = desempenho.filter((d) => d.pct_acerto != null);
  const ordenadas = [...comDado].sort((a, b) => (a.pct_acerto ?? 0) - (b.pct_acerto ?? 0));
  const pior = ordenadas[0] ?? null;

  const nome = primeiroNome(usuario?.email);

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1000px] flex-col px-6 pb-10 pt-6">
      <p className="rotulo-accent mb-2.5">
        {`// ${saudacao()}${nome ? `, ${nome.toLowerCase()}` : ""}`}
      </p>
      <h1 className="mb-5 text-[27px] md:text-[30px]">
        {meta?.dias_restantes != null ? (
          <>
            Faltam <span className="text-accent-text">{meta.dias_restantes} dias</span>
            {meta.cobertura_pct < 100 && ` e ${(100 - meta.cobertura_pct).toFixed(0)}% do edital está aberto.`}
          </>
        ) : (
          <>
            Sua rota de hoje, <span className="text-accent-text">montada pelo tutor</span>.
          </>
        )}
      </h1>

      {/* KPIs: mesma faixa da tela de desempenho, do mesmo componente —
          dois cálculos do "acerto geral" divergiriam entre as duas telas. */}
      <div className="mb-3">
        <Kpis carga={carga} desempenho={desempenho} />
      </div>

      {/* ------------------------------------------------------- split */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        {/* ------------------------------------------ maestria por matéria */}
        <section className="rounded-2xl border border-line bg-surface px-[22px] py-5">
          {/* Mesmo cuidado do raio-x: sem alvo, isto é o histórico inteiro
              do aluno, não o recorte de uma mesa. O rótulo diz qual dos
              dois é, porque o número é o mesmo e o significado não. */}
          <p className="rotulo mb-4">
            maestria por matéria
            {mesa?.origem_alvo === "nenhum" && (
              <span className="opacity-60"> · acervo inteiro</span>
            )}
          </p>
          {ordenadas.length === 0 ? (
            <p className="text-sm text-muted">
              nenhuma disciplina com tentativa registrada ainda — responda a fila de hoje e este quadro
              começa a existir.
            </p>
          ) : (
            <div className="flex flex-col gap-3.5">
              {ordenadas.map((d) => {
                const pct = d.pct_acerto ?? 0;
                return (
                  <div key={d.disciplina}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-2.5">
                      <span className="truncate text-sm">{d.disciplina}</span>
                      <span className="mono-num text-[12.5px]" style={{ color: corDoPct(pct) }}>
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="barra">
                      <div className="barra-fill" style={{ width: `${pct}%`, background: corDoPct(pct) }} />
                    </div>
                    <p className="mt-1.5 text-[11.5px] text-subtle">
                      {d.dominadas} de {d.questoes} dominadas · {d.cobertura_pct.toFixed(0)}% coberto
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* ------------------------------------- edital fechado + alertas */}
        <div className="flex flex-col gap-3">
          <section className="rounded-2xl border border-line bg-surface px-5 py-[18px]">
            <p className="rotulo mb-3">edital fechado</p>
            {/* GET /meta responde 200 mesmo sem edital nenhum ingerido (só
                com dias_restantes: null e um aviso) — checar `meta` sozinho
                nunca cai no branch de baixo, então quem pulou o onboarding
                ficava sem NENHUM link de volta nesta seção (só um texto
                pequeno, sem ação). O sinal certo de "tem edital" é
                dias_restantes, mesmo padrão já usado em RaioX.tsx. */}
            {meta && meta.dias_restantes != null ? (
              <>
                <div className="mb-2 flex items-baseline justify-between">
                  <span className="text-[25px] font-semibold tabular-nums">
                    {meta.cobertura_pct.toFixed(0)}%
                  </span>
                  <span className="mono-num text-[12px] text-subtle">
                    {meta.questoes_respondidas} / {meta.questoes_respondidas + meta.questoes_pendentes}
                  </span>
                </div>
                <div className="barra-grossa">
                  <div className="barra-fill bg-accent" style={{ width: `${meta.cobertura_pct}%` }} />
                </div>
                <p className="mt-2 text-[12px] text-subtle">
                  {meta.ritmo_necessario != null
                    ? `Ritmo necessário: ${meta.ritmo_necessario.toFixed(1)} questões/dia`
                    : "Sem data de prova — ingira o edital para eu calcular seu ritmo."}
                </p>
              </>
            ) : (
              <Link href="/onboarding" className="link">
                nenhum edital ingerido — mandar o PDF →
              </Link>
            )}
          </section>

          <section className="rounded-2xl border border-line bg-surface px-5 py-[18px]">
            <p className="rotulo mb-3">alertas</p>
            <div className="flex flex-col gap-2.5 text-[13.5px] leading-relaxed">
              {/* Intervenção proativa de core/ritmo_regras.py — no máximo UMA
                  por sessão, decidida por regra no backend, não pelo front. */}
              {sugestao && <p>{sugestao}</p>}
              {pior && pior.pct_acerto != null && (
                <p>
                  <span className="text-accent-text">{pior.disciplina}</span> — {pior.pct_acerto.toFixed(0)}%
                  de acerto em {pior.tentativas} {pior.tentativas === 1 ? "tentativa" : "tentativas"}.
                </p>
              )}
              {carga.atraso > 0 && (
                <p>
                  <span className="text-warning">
                    {carga.atraso} {carga.atraso === 1 ? "revisão atrasada" : "revisões atrasadas"}
                  </span> — entram primeiro
                  na fila de hoje.
                </p>
              )}
              {!sugestao && !pior && carga.atraso === 0 && (
                <p className="text-muted">Nada gritando hoje. Bom sinal.</p>
              )}
            </div>
            {erros.length > 0 && (
              <Link href="/erros" className="btn-ghost mt-3.5 w-full text-[12.5px]">
                Abrir o caderno ({erros.length} {erros.length === 1 ? "reincidência" : "reincidências"})
              </Link>
            )}
          </section>
        </div>
      </div>

      {/* ---------------------------------------------------- composer */}
      {/* O protótipo põe a caixa de conversa no rodapé do painel: falar com
          o tutor é a ação primária, e ela fica igual em todas as telas. O
          texto vai pro /tutor, que é quem tem o `POST /perguntar`.
          `mt-auto` (num container `flex min-h-full flex-col`) é o que ancora
          o composer no FIM da página de verdade — sem isso, com pouco
          conteúdo acima (poucas disciplinas, sem alerta), ele ficava
          flutuando no meio da tela com um vão vazio embaixo. */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const t = pergunta.trim();
          router.push(t ? `/tutor?q=${encodeURIComponent(t)}` : "/tutor");
        }}
        className="mt-auto rounded-[18px] border border-line-strong bg-surface-input px-3.5 pb-2.5 pt-3.5 shadow-[var(--shadow-float)] focus-within:border-accent"
      >
        <input
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          placeholder="Fale com a FerrarIA e o painel sai da frente…"
          className="w-full bg-transparent text-[15px] text-foreground outline-none placeholder:text-subtle"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
            <Link href="/meta" className="chip text-[12.5px]">
              Meu edital
            </Link>
            <Link href="/desafio" className="chip text-[12.5px]">
              Rota do dia
            </Link>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2.5">
            <span className="font-mono text-[11px] text-label">FerrarIA 2.0</span>
            <button
              type="submit"
              className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-accent text-accent-foreground transition-colors hover:bg-accent-hover"
              aria-label="falar com o tutor"
            >
              <ArrowUp className="h-[17px] w-[17px]" strokeWidth={2.6} />
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
