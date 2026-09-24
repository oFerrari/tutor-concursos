"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Kpis, agregar } from "@/components/Kpis";
import {
  Carga,
  ConceitoFraco,
  Desempenho,
  ErroApi,
  getCarga,
  getConceitos,
  getStats,
  getToken,
} from "@/lib/api";
import { Carregando } from "@/components/Carregando";
import { gravarCache, sair, useCache } from "@/lib/cache";

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
  const [dados, setDados] = useCache<Desempenho[]>("stats");
  const [carga, setCarga] = useCache<Carga>("carga");
  const [conceitos, setConceitos] = useCache<ConceitoFraco[]>("conceitos");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getStats()
      .then((d) => {
        setDados(d);
        gravarCache("stats", d);
      })
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          sair();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
      });
    // A carga é contexto (ofensiva, revisões, tempo médio): se ela falhar, a
    // tela ainda tem o que mostrar — some a faixa, fica o detalhe.
    getCarga()
      .then((c) => {
        setCarga(c);
        gravarCache("carga", c);
      })
      .catch(() => {});
    // Também contexto, e também tolerante a falha: se esta cair, a tela
    // continua sendo o desempenho por matéria. O bloco só aparece quando há
    // conceito reincidente — lista vazia não vira seção vazia.
    getConceitos()
      .then((c) => {
        setConceitos(c);
        gravarCache("conceitos", c);
      })
      .catch(() => {});
    // Setters do `useCache` — estáveis; o lint só não vê através do hook.
  }, [router, setCarga, setConceitos, setDados]);

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

      {!erro && !dados && <Carregando linhas={4} titulo />}

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
                      : `${d.acertos} de ${d.tentativas} ${d.tentativas === 1 ? "tentativa" : "tentativas"}`
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

      {/* O QUE VOCÊ CONFUNDE — e não "o que você errou", que é o quadro
          acima. Vem do `conceito_faltante` que a correção já apontava em toda
          avaliação e que era descartado: gerado, pago, exibido uma vez e
          esquecido. Só entra conceito que reincidiu (>= 2 vezes): apontado
          uma vez é observação, e observação afirmada como padrão na tela do
          aluno é pior que silêncio.

          Some quando não há nada — seção vazia com título faz o aluno achar
          que o app quebrou, e aqui o vazio é a notícia boa. */}
      {conceitos && conceitos.length > 0 && (
        <section className="mt-3 rounded-2xl border border-line bg-surface px-[22px] py-5">
          <p className="rotulo mb-1">o que você confunde</p>
          <p className="mb-4 text-sm text-muted">
            Apontado pela correção das suas respostas, agrupado pelo que se repetiu.
          </p>
          <ul className="flex flex-col gap-2.5">
            {conceitos.map((c) => (
              <li
                key={`${c.disciplina}-${c.conceito}`}
                className="flex items-start justify-between gap-4 border-b border-line pb-2.5 last:border-0 last:pb-0"
              >
                <div className="min-w-0">
                  <p className="text-sm">{c.conceito}</p>
                  <p className="mt-0.5 text-xs text-subtle">{c.disciplina}</p>
                </div>
                {/* tabular-nums pelo mesmo motivo da TabelaPorDisciplina: sem
                    isso o número muda de largura e a coluna dança. */}
                <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-muted">
                  {c.vezes}x
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
