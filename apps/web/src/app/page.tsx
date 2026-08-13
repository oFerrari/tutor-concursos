"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Brain,
  CalendarClock,
  ShieldAlert,
  Sparkles,
  Target,
  type LucideIcon,
} from "lucide-react";
import {
  Carga,
  Desempenho,
  ErroApi,
  ErroCaderno,
  Meta,
  Usuario,
  getCarga,
  getErros,
  getMe,
  getMeta,
  getStats,
  getSugestao,
  getToken,
  limparToken,
} from "@/lib/api";

function saudacao(): string {
  const h = new Date().getHours();
  if (h < 5) return "Boa noite";
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

/** Primeiro nome a partir do e-mail — dado real do usuário, não um nome
 *  inventado. Sem endpoint de perfil com nome próprio, é o melhor que
 *  existe; se um dia houver campo `nome`, troca aqui e some esta função. */
function primeiroNome(email: string | undefined): string {
  if (!email) return "";
  const local = email.split("@")[0] ?? "";
  const bruto = local.split(/[._-]/)[0] ?? "";
  if (!bruto) return "";
  return bruto.charAt(0).toUpperCase() + bruto.slice(1).toLowerCase();
}

/**
 * Monta a fala do tutor a partir dos números REAIS do banco — nunca de um
 * texto de exemplo fixo. É o mesmo princípio que rege `socratic.explicar()`
 * no backend: o modelo (e aqui, a tela) só LÊ um resumo já calculado, nunca
 * inventa um percentual. Uma tela que diz "33% em Direito Penal" quando o
 * banco diz outra coisa é pior que uma tela sem número nenhum.
 *
 * Função pura de propósito (recebe dados, devolve string) — mesma
 * separação de `scheduler_regras.py`: decisão sem efeito colateral.
 */
function falaDoTutor(
  carga: Carga,
  pior: Desempenho | null,
  reincidencias: number
): string {
  const partes: string[] = [];

  if (carga.atraso > 0) {
    partes.push(
      `Você acumulou ${carga.atraso} ${carga.atraso === 1 ? "revisão atrasada" : "revisões atrasadas"} — ` +
        `elas entram primeiro hoje, porque revisão atrasada é conhecimento se perdendo agora.`
    );
  } else if (carga.revisoes > 0) {
    partes.push(
      `${carga.revisoes} ${carga.revisoes === 1 ? "revisão venceu" : "revisões venceram"} hoje e já estão no topo da sua fila.`
    );
  } else {
    partes.push("Nenhuma revisão venceu hoje — sua memória está em dia, então podemos avançar em conteúdo novo.");
  }

  if (pior && pior.pct_acerto != null) {
    partes.push(
      `Analisei seu histórico: seu ponto mais frágil é ${pior.disciplina}, com ${pior.pct_acerto.toFixed(0)}% de acerto.`
    );
  }

  if (reincidencias > 0) {
    partes.push(
      `Separei ${reincidencias} ${reincidencias === 1 ? "questão" : "questões"} que você errou mais de uma vez para um diálogo socrático antes de avançarmos.`
    );
  }

  if (carga.ineditas > 0) {
    partes.push(`Depois disso, há ${carga.ineditas} inéditas liberadas.`);
  }

  return partes.join(" ");
}

export default function PaginaInicial() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carga, setCarga] = useState<Carga | null>(null);
  const [sugestao, setSugestao] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [desempenho, setDesempenho] = useState<Desempenho[] | null>(null);
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
        setDesempenho(s);
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
    // extras — falhar aqui não deve derrubar a tela (ex.: sem edital ingerido ainda)
    getMe().then(setUsuario).catch(() => {});
    getSugestao().then((r) => setSugestao(r.sugestao)).catch(() => {});
    getMeta().then(setMeta).catch(() => {});
  }, [router]);

  if (erro) {
    return (
      <div className="mx-auto max-w-4xl p-6 md:p-10">
        <p className="callout-danger">{erro}</p>
      </div>
    );
  }

  if (!carga || !desempenho || !erros) {
    return (
      <div className="mx-auto max-w-4xl p-6 md:p-10">
        <p className="text-sm text-muted">carregando…</p>
      </div>
    );
  }

  // "Mais frágil" só entre disciplinas COM tentativa registrada — ordenar
  // incluindo pct_acerto nulo apontaria como pior justamente a disciplina
  // que o usuário nunca tocou, que é falta de dado, não fraqueza.
  const comDado = desempenho.filter((d) => d.pct_acerto != null);
  const ordenadas = [...comDado].sort((a, b) => (a.pct_acerto ?? 0) - (b.pct_acerto ?? 0));
  const pior = ordenadas[0] ?? null;

  const nome = primeiroNome(usuario?.email);

  return (
    <div className="mx-auto max-w-4xl space-y-10 p-6 md:p-10">
      {/* ---------------------------------------------- mensagem do tutor */}
      <section className="flex gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent-soft ring-1 ring-accent/30">
          <Sparkles className="h-5 w-5 text-accent" strokeWidth={2} />
        </div>
        <div className="min-w-0 pt-1">
          <p className="text-lg leading-relaxed text-foreground md:text-xl">
            <span className="font-semibold">
              {saudacao()}
              {nome ? `, ${nome}` : ""}.
            </span>{" "}
            <span className="text-muted">{falaDoTutor(carga, pior, erros.length)}</span>
          </p>
          {/* Intervenção proativa de core/ritmo_regras.py — no máximo UMA
              por sessão, decidida por regra no backend, não pelo front. */}
          {sugestao && (
            <p className="mt-4 rounded-xl border border-accent/20 bg-accent-soft/50 px-4 py-3 text-sm text-foreground">
              <span className="font-semibold text-accent">Sugestão do tutor · </span>
              {sugestao}
            </p>
          )}
        </div>
      </section>

      {/* ------------------------------------------------ trilha do dia */}
      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted">a trilha de hoje</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <CardTrilha
            href="/fila"
            Icone={Brain}
            titulo="Revisão SM-2"
            valor={carga.revisoes}
            unidade={carga.revisoes === 1 ? "pendente" : "pendentes"}
            destaque={carga.revisoes > 0}
            nota={carga.atraso > 0 ? `${carga.atraso} em atraso` : undefined}
          />
          <CardTrilha
            href="/fila"
            Icone={Target}
            titulo="Inéditas"
            valor={carga.ineditas}
            unidade={carga.ineditas === 1 ? "liberada" : "liberadas"}
          />
          <CardTrilha
            href="/erros"
            Icone={ShieldAlert}
            titulo="Caderno de erros"
            valor={erros.length}
            unidade={erros.length === 1 ? "reincidência" : "reincidências"}
            destaque={erros.length > 0}
          />
          <CardTrilha
            href="/meta"
            Icone={CalendarClock}
            titulo="Até a prova"
            valor={meta?.dias_restantes ?? "—"}
            unidade={meta?.dias_restantes == null ? "sem edital" : "dias"}
            destaque={meta?.dias_restantes != null && meta.dias_restantes <= 30}
          />
        </div>
      </section>

      {/* ------------------------------------------------------- CTA */}
      <section className="flex flex-col items-center gap-3 py-2">
        <Link href="/desafio" className="btn-cta">
          <Sparkles className="h-5 w-5" strokeWidth={2} />
          começar sessão de hoje
        </Link>
        <p className="text-xs text-muted">
          o tutor monta a ordem: reincidentes primeiro, depois inéditas, e fecha com mini-simulado
        </p>
      </section>

      {/* --------------------------------------------- pontos de atenção */}
      {ordenadas.length > 0 && (
        <section className="widget">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-foreground">pontos de atenção</h2>
            <Link href="/stats" className="link">
              desempenho completo →
            </Link>
          </div>
          <ul className="space-y-3">
            {ordenadas.slice(0, 3).map((d) => {
              const pct = d.pct_acerto ?? 0;
              return (
                <li key={d.disciplina}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate">{d.disciplina}</span>
                    <span className="shrink-0 tabular-nums text-muted">
                      {pct.toFixed(0)}% · {d.acertos}/{d.tentativas}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-line">
                    <div
                      className={`h-full rounded-full ${pct < 50 ? "bg-accent" : "bg-success"}`}
                      style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

function CardTrilha({
  href,
  Icone,
  titulo,
  valor,
  unidade,
  destaque,
  nota,
}: {
  href: string;
  Icone: LucideIcon;
  titulo: string;
  valor: number | string;
  unidade: string;
  destaque?: boolean;
  nota?: string;
}) {
  return (
    <Link href={href} className="widget-acao group">
      <Icone
        className={`h-5 w-5 transition-colors ${destaque ? "text-accent" : "text-muted group-hover:text-foreground"}`}
        strokeWidth={1.75}
      />
      <p className="mt-3 text-xs font-medium uppercase tracking-wide text-muted">{titulo}</p>
      <p className="mt-1 flex items-baseline gap-1.5">
        <span className={`text-3xl font-bold tabular-nums ${destaque ? "text-accent" : "text-foreground"}`}>
          {valor}
        </span>
        <span className="text-xs text-muted">{unidade}</span>
      </p>
      {nota && <p className="mt-1 text-xs font-medium text-warning">{nota}</p>}
    </Link>
  );
}
