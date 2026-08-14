"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Kpis, agregar } from "@/components/Kpis";
import {
  Carga,
  Desempenho,
  ErroApi,
  getCarga,
  getStats,
  getToken,
  limparToken,
} from "@/lib/api";

/**
 * Desempenho — a mesma faixa de KPIs do panorama, e abaixo dela o detalhe
 * por matéria que só existe aqui.
 *
 * Os KPIs vêm de `<Kpis>`, não recalculados: repetir a conta nas duas telas
 * é como o número do painel e o do cartão de mesa divergiriam.
 *
 * DUAS barras por matéria, não uma. O protótipo mostra só "acerto por
 * matéria", mas acerto e cobertura respondem perguntas diferentes e a
 * confusão entre elas é fácil: 100% de acerto em 2 de 30 questões não é
 * domínio da matéria, é amostra pequena — exatamente o erro que
 * `v_desempenho_disciplina` foi corrigida pra não cometer (o denominador
 * da cobertura é o acervo INTEIRO da disciplina, não só o que a pessoa
 * tocou). Mostrar as duas juntas é o que impede ler uma como se fosse a
 * outra.
 */
function corDoPct(pct: number | null): string {
  if (pct == null) return "var(--line-strong)";
  if (pct < 50) return "var(--accent)";
  if (pct < 75) return "var(--body)";
  return "var(--success)";
}

function Linha({
  nome,
  pct,
  nota,
  cor,
}: {
  nome: string;
  pct: number | null;
  nota: string;
  cor: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="text-[14px]">{nome}</span>
        <span className="mono-num text-[12.5px]" style={{ color: cor }}>
          {pct == null ? "—" : `${pct.toFixed(0)}%`}
        </span>
      </div>
      <div className="barra">
        <div
          className="barra-fill"
          style={{ width: `${pct == null ? 0 : Math.max(0, Math.min(100, pct))}%`, background: cor }}
        />
      </div>
      <p className="mt-1 text-[12px] text-subtle">{nota}</p>
    </div>
  );
}

export default function PaginaStats() {
  const router = useRouter();
  const [dados, setDados] = useState<Desempenho[] | null>(null);
  const [carga, setCarga] = useState<Carga | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getStats()
      .then(setDados)
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
      });
    // A carga é contexto (ofensiva, revisões, tempo médio): se ela falhar, a
    // tela ainda tem o que mostrar — some a faixa, fica o detalhe.
    getCarga().then(setCarga).catch(() => {});
  }, [router]);

  const geral = agregar(dados);
  // ORDENADO POR PIOR ACERTO, como no protótipo: quem abre esta tela quer
  // ver primeiro o que está mal. Disciplina sem tentativa nenhuma
  // (pct_acerto null) vai pro fim — não é "0%", é "sem dado", e colocá-la
  // no topo faria a lista abrir com a matéria de que menos se sabe.
  const ordenadas = [...(dados ?? [])].sort((a, b) => {
    if (a.pct_acerto == null) return 1;
    if (b.pct_acerto == null) return -1;
    return a.pct_acerto - b.pct_acerto;
  });

  return (
    <div className="mx-auto w-full max-w-[1000px] px-6 pb-10 pt-6">
      <h1 className="text-[27px] md:text-[30px]">Desempenho</h1>
      {/* SEM "últimos 30 dias": nada aqui é recortado por janela de tempo —
          a view agrega o histórico inteiro. Escrever a janela que o
          protótipo escreve deixaria a legenda mentindo sobre um número
          verdadeiro. */}
      <p className="mb-5 mt-1 text-sm text-muted">
        {geral.tentativas > 0
          ? `Histórico completo · ${geral.tentativas} ${
              geral.tentativas === 1 ? "resposta registrada" : "respostas registradas"
            }`
          : "Só o que você já respondeu — nesta mesa, ainda nada."}
      </p>

      {erro && <p className="callout-danger mb-4">{erro}</p>}

      <div className="mb-3">
        <Kpis carga={carga} desempenho={dados} />
      </div>

      {!erro && !dados && <p className="text-sm text-muted">Carregando…</p>}

      {dados && dados.length === 0 && (
        <p className="callout-info">
          Sem tentativas ainda — responda alguma questão na fila e este quadro começa a existir.
        </p>
      )}

      {ordenadas.length > 0 && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <section className="rounded-2xl border border-line bg-surface px-[22px] py-5">
            <p className="rotulo mb-4">acerto por matéria</p>
            <div className="flex flex-col gap-3.5">
              {ordenadas.map((d) => (
                <Linha
                  key={d.disciplina}
                  nome={d.disciplina}
                  pct={d.pct_acerto}
                  cor={corDoPct(d.pct_acerto)}
                  nota={
                    d.pct_acerto == null
                      ? "sem tentativa ainda"
                      : `${d.acertos} de ${d.tentativas} tentativas`
                  }
                />
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-surface px-[22px] py-5">
            <p className="rotulo mb-4">cobertura do acervo</p>
            <div className="flex flex-col gap-3.5">
              {ordenadas.map((d) => (
                <Linha
                  key={d.disciplina}
                  nome={d.disciplina}
                  pct={d.cobertura_pct}
                  cor={corDoPct(d.cobertura_pct)}
                  nota={`${d.dominadas} de ${d.questoes} questões dominadas`}
                />
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
