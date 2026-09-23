"use client";

import Link from "next/link";
import { X } from "lucide-react";
import { Carga, Desempenho, EditalAtual, ErroCaderno, Mesa, Meta } from "@/lib/api";

/**
 * "Raio-X do aluno" — a terceira coluna do protótipo. Painel de contexto
 * permanente: o que a tela do meio estiver fazendo, esta coluna responde
 * sempre às mesmas perguntas (quanto falta, onde estou fraco, quanto a
 * memória está devendo).
 *
 * Meta, maestria, carga e ofensiva vêm de endpoint real (`/meta`,
 * `/edital`, `/stats`, `/carga`, `/erros`) — ofensiva saiu do mock nesta
 * revisão (era OFENSIVA.dias; agora é `carga.ofensiva_dias`, calculado em
 * `scheduler.ofensiva_dias()`). Liga e "flashcards na fila" SAÍRAM em
 * 22/09/2026: eram constantes do protótipo (28 flashcards, 7º de 42) exibidas
 * como dado numa conta sem questão nenhuma. Número fictício na coluna que o
 * aluno lê como "quanto a memória está devendo" é pior que coluna menor.
 */

function formatarDataProva(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [ano, mes, dia] = iso.split("-");
  return ano && mes && dia ? `${dia}/${mes}` : null;
}

function corDoPct(pct: number): string {
  if (pct < 50) return "var(--accent-text)";
  if (pct < 75) return "var(--body)";
  return "var(--success)";
}

type Props = {
  meta: Meta | null;
  /** Mesa ativa — o nome dela é o subtítulo quando ainda não há edital
   *  ingerido (antes vinha de MESA_ATUAL, que era decorativo). */
  mesa: Mesa | null;
  edital: EditalAtual | null;
  desempenho: Desempenho[] | null;
  carga: Carga | null;
  erros: ErroCaderno[] | null;
  onFechar: () => void;
};

export function RaioX({ meta, mesa, edital, desempenho, carga, erros, onFechar }: Props) {
  const dataProva = formatarDataProva(edital?.data_prova);
  // Sem alvo, os blocos deste rail mostram o histórico INTEIRO do aluno. O
  // rail continua útil assim (é raio-x DO ALUNO, não da mesa) — o que não
  // pode é rotular isso como progresso de um edital que não existe.
  // Sem alvo, o link vai pra onde se DEFINE o alvo (`/alvo`); tendo alvo
  // mas sem data, vai pra onde se LÊ a meta (`/meta`). Antes os dois iam
  // pro `/meta`, que só exibe — clicar em "sem alvo" levava a uma tela
  // que também dizia que não havia alvo.
  const semAlvo = mesa?.origem_alvo === "nenhum";
  const comDado = (desempenho ?? []).filter((d) => d.pct_acerto != null);
  const ordenadas = [...comDado].sort((a, b) => (a.pct_acerto ?? 0) - (b.pct_acerto ?? 0));

  return (
    <aside
      className="chrome fixed inset-y-0 right-0 z-40 flex w-[300px] max-w-[88vw] shrink-0 flex-col gap-4
                 overflow-y-auto border-l border-line-soft px-[18px] pb-7 pt-[18px]
                 shadow-[var(--shadow-drawer)]
                 xl:static xl:z-auto xl:max-w-none xl:shadow-none"
    >
      <div className="flex items-center justify-between gap-2.5">
        <p className="rotulo tracking-[1.8px]">raio-x do aluno</p>
        <button onClick={onFechar} className="btn-icone h-7 w-7 xl:hidden" aria-label="fechar raio-x">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* ------------------------------------------------ meta até a prova */}
      <div className="painel p-4">
        <p className="rotulo mb-2">meta até a prova</p>
        {meta?.dias_restantes != null ? (
          <div className="flex items-baseline gap-2">
            <span className="text-[34px] font-bold leading-none tabular-nums text-accent-text">
              {meta.dias_restantes}
            </span>
            <span className="text-[13.5px] text-muted">dias{dataProva ? ` · ${dataProva}` : ""}</span>
          </div>
        ) : (
          <Link
            href={semAlvo ? "/alvo" : "/meta"}
            className="text-[13.5px] text-muted underline-offset-2 hover:text-foreground"
          >
            {semAlvo ? "sem alvo nesta mesa →" : "sem data de prova →"}
          </Link>
        )}
        <p className="mt-1.5 text-[12.5px] text-subtle">
          {edital?.titulo ?? mesa?.nome ?? "—"}
        </p>

        {/* SEM ALVO não existe "edital fechado" pra medir: o percentual
            aqui seria a cobertura do acervo INTEIRO com o rótulo de um
            edital que não existe — exatamente o "4/54 · 7%" que saiu do
            cartão do lobby, e que continuava vivo aqui. Em vez do número,
            a explicação do que os blocos abaixo estão mostrando: eles são
            do ALUNO, e sem recorte eles cobrem tudo. */}
        {semAlvo ? (
          <p className="mt-3 text-[12px] leading-relaxed text-subtle">
            Sem alvo definido, os números abaixo são do seu histórico inteiro — não do
            recorte desta mesa. Nada foi perdido: seu progresso é seu, e passa a ser
            filtrado assim que a mesa tiver edital ou matérias escolhidas.
          </p>
        ) : (
          meta && (
            <div className="mt-3.5">
              <div className="mb-1.5 flex items-baseline justify-between gap-2">
                {/* "edital fechado" só quando existe edital. Com alvo
                    manual é a mesma conta e outro nome — chamar de edital
                    o que a pessoa escolheu à mão faria a tela afirmar um
                    documento que não foi subido. */}
                <span className="rotulo">
                  {mesa?.origem_alvo === "manual" ? "matérias fechadas" : "edital fechado"}
                </span>
                <span className="mono-num text-[12.5px] text-foreground">{meta.cobertura_pct.toFixed(0)}%</span>
              </div>
              <div className="barra-grossa">
                <div
                  className="barra-fill bg-accent"
                  style={{ width: `${Math.max(0, Math.min(100, meta.cobertura_pct))}%` }}
                />
              </div>
              <p className="mt-1.5 text-[12px] text-subtle">
                {meta.questoes_respondidas} de {meta.questoes_respondidas + meta.questoes_pendentes} questões
                {meta.ritmo_necessario != null && ` · ritmo: ${meta.ritmo_necessario.toFixed(1)}/dia`}
              </p>
            </div>
          )
        )}
      </div>

      {/* ------------------------------------------------------ ofensiva */}
      {/* A "liga" (Ouro, 7º de 42) saiu: era constante do protótipo, sem ranking
          nenhum por trás, e mostrava 42 alunos numa base com um usuário só. */}
      <div className="painel">
        <p className="rotulo mb-1.5">ofensiva</p>
        <p className="text-xl font-semibold">🔥 {carga?.ofensiva_dias ?? 0}</p>
        <p className="mt-0.5 text-[11.5px] text-subtle">
          {carga?.ofensiva_dias ? "dias seguidos" : "estude hoje pra começar"}
        </p>
      </div>

      {/* --------------------------------------------- cards de maestria */}
      {ordenadas.length > 0 && (
        <div>
          <p className="rotulo mb-2.5">
            cards de maestria{semAlvo && <span className="opacity-60"> · acervo inteiro</span>}
          </p>
          <div className="flex flex-col gap-2">
            {ordenadas.slice(0, 5).map((d) => {
              const pct = d.pct_acerto ?? 0;
              return (
                <Link
                  key={d.disciplina}
                  href="/stats"
                  className="rounded-xl border border-line bg-surface px-3.5 py-3 transition-all
                             hover:border-line-stronger hover:bg-surface-raised"
                >
                  <div className="mb-2 flex items-baseline justify-between gap-2.5">
                    <span className="truncate text-[13.5px]">{d.disciplina}</span>
                    <span className="mono-num shrink-0 text-[12px]" style={{ color: corDoPct(pct) }}>
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-[5px] overflow-hidden rounded-full bg-line-soft">
                    <div
                      className="barra-fill"
                      style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: corDoPct(pct) }}
                    />
                  </div>
                  <p className="mt-1.5 text-[11.5px] text-subtle">
                    {d.dominadas} de {d.questoes} dominadas · {d.cobertura_pct.toFixed(0)}% coberto
                  </p>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* ------------------------------------------- carga de memória */}
      {carga && (
        <div className="painel p-4">
          <p className="rotulo mb-2.5">
            carga de memória{semAlvo && <span className="opacity-60"> · acervo inteiro</span>}
          </p>
          <div className="flex flex-col gap-2">
            <div className="dado-linha">
              <span className="text-[#b6b6bd]">Revisões SM-2 hoje</span>
              <span className={`mono-num ${carga.revisoes > 0 ? "text-accent-text" : "text-body"}`}>
                {carga.revisoes}
              </span>
            </div>
            <div className="dado-linha">
              <span className="text-[#b6b6bd]">Erros pendentes</span>
              <span className={`mono-num ${(erros?.length ?? 0) > 0 ? "text-accent-text" : "text-body"}`}>
                {erros?.length ?? 0}
              </span>
            </div>
          </div>
          <Link href="/fila" className="btn-ghost mt-3.5 w-full text-[12.5px]">
            Abrir a fila
          </Link>
        </div>
      )}
    </aside>
  );
}
