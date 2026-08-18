"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Upload, X } from "lucide-react";
import {
  EditalAtual,
  ErroApi,
  ajustarDisciplinasEdital,
  corrigirDataProva,
  Meta,
  getEdital,
  getMeta,
  getToken,
  limparToken,
} from "@/lib/api";

export default function PaginaMeta() {
  const router = useRouter();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [edital, setEdital] = useState<EditalAtual | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  /** Edição do edital JÁ confirmado. Fica atrás de um toggle porque a tela é
   *  de LEITURA (quanto falta, quanto cobri) e um X por linha convida ao
   *  clique acidental num dado que apaga tópicos. */
  const [editando, setEditando] = useState(false);
  const [novaDisc, setNovaDisc] = useState("");
  const [novaData, setNovaData] = useState("");
  const [ajustando, setAjustando] = useState(false);

  async function corrigirData(data: string) {
    if (ajustando) return;
    setAjustando(true);
    setErro(null);
    try {
      setEdital(await corrigirDataProva(data));
      // A meta INTEIRA muda com a data (dias restantes, ritmo, probabilidade),
      // não só o cabeçalho — recarregar as duas evita a tela afirmar prazo novo
      // com ritmo calculado no antigo.
      getMeta().then(setMeta).catch(() => {});
      setNovaData("");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra trocar a data da prova");
    } finally {
      setAjustando(false);
    }
  }

  async function ajustar(ajuste: { remover?: string[]; adicionar?: string[] }) {
    if (ajustando) return;
    setAjustando(true);
    setErro(null);
    try {
      const r = await ajustarDisciplinasEdital(ajuste);
      // Recarrega os DOIS: tirar matéria muda o denominador da cobertura e,
      // com ele, o ritmo necessário e a probabilidade de fechamento. Atualizar
      // só a tabela deixaria o cabeçalho afirmando um prazo que já mudou.
      setEdital((e) => (e ? { ...e, cobertura: r.cobertura } : e));
      getMeta().then(setMeta).catch(() => {});
      setNovaDisc("");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra ajustar as matérias");
    } finally {
      setAjustando(false);
    }
  }

  async function carregar() {
    try {
      setMeta(await getMeta());
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        limparToken();
        router.push("/login");
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
    }
    try {
      setEdital(await getEdital());
    } catch {
      setEdital(null); // 404 = ainda não ingeriu nenhum edital — normal, não é erro
    }
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    // Busca inicial no mount — carregar() já trata seus próprios erros
    // (401 redireciona, resto vira setErro), então chamar sem esperar aqui é seguro.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const prob = meta?.probabilidade_fechamento;
  const probOk = prob && !("erro" in prob);

  // PROVA VENCIDA é um estado próprio, não "0 dias". O edital da PF em corpus/
  // é de 2025: a meta dizia "0 dias restantes · probabilidade 0%" — números
  // verdadeiros e inúteis, porque sem prazo futuro não existe ritmo pra medir
  // contra. E quem estuda por edital antigo (concurso que vai reabrir) é o
  // caso NORMAL de preparação, não a exceção. Comparação por string ISO
  // funciona e evita fuso: "2025-07-27" < "2026-08-18" lexicograficamente.
  const hoje = new Date().toISOString().slice(0, 10);
  const provaVencida = !!edital?.data_prova && edital.data_prova < hoje;

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Meta até a prova</h1>
        <p className="mt-1 text-sm text-muted">Dias restantes, cobertura e probabilidade de fechamento.</p>
      </div>

      {erro && <p className="mb-4 callout-danger">{erro}</p>}

      {provaVencida && (
        <div className="callout-warning mb-4">
          <p className="mb-2.5 text-[13px]">
            <strong className="font-semibold">A data deste edital já passou</strong> (
            {edital?.data_prova}). Sem uma data futura eu não consigo medir sua meta: dias
            restantes, ritmo necessário e probabilidade de fechamento todos dependem do prazo.
            Se você estuda por este edital esperando o próximo, informe a data provável.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (novaData) corrigirData(novaData);
            }}
            className="flex flex-wrap items-center gap-2"
          >
            <input
              type="date"
              value={novaData}
              min={hoje}
              onChange={(e) => setNovaData(e.target.value)}
              className="field w-auto !py-1.5 text-[13px]"
            />
            <button type="submit" disabled={!novaData || ajustando} className="chip">
              usar esta data
            </button>
          </form>
        </div>
      )}

      {meta && (
        <div className="card text-sm">
          {meta.aviso ? (
            <p className="text-warning">{meta.aviso}</p>
          ) : (
            <>
              {/* A DATA e o CARGO ficam aqui, não escondidos. "0 dias
                  restantes · Ed_1_PF_25_Abertura" mostrava nome de ARQUIVO e
                  omitia as duas coisas que o aluno vem conferir: quando é a
                  prova e de quem é este plano. Num edital com 17 cargos (PF),
                  não dizer o cargo é omitir a informação mais importante da
                  tela — `edital.cargo` existe pra isso desde a migração 018. */}
              <p>
                {meta.dias_restantes} dias restantes
                {edital?.data_prova && (
                  <span className="text-muted"> · prova em {edital.data_prova}</span>
                )}
                {meta.edital && <span className="text-muted"> · {meta.edital}</span>}
              </p>
              {edital?.cargo && (
                <p className="text-muted">
                  Cargo: <span className="text-body">{edital.cargo}</span>
                </p>
              )}
              <p className="mt-1 text-muted">
                Cobertura {meta.cobertura_pct}% · {meta.questoes_pendentes} questões pendentes ·{" "}
                {meta.questoes_respondidas} já respondidas
              </p>
              {meta.ritmo_necessario != null && (
                <p className="mt-1 text-muted">Ritmo necessário: {meta.ritmo_necessario} questões/dia</p>
              )}
              {probOk && (
                <p className="mt-3 font-medium">
                  Probabilidade de fechamento: <span className="text-accent">{prob.probabilidade_fechamento_pct}%</span>
                  <span className="ml-2 font-normal text-muted">
                    (ritmo atual {prob.ritmo_atual_topicos_dia}, necessário{" "}
                    {prob.ritmo_necessario_topicos_dia ?? "—"} tópicos/dia)
                  </span>
                </p>
              )}
            </>
          )}
        </div>
      )}

      {edital && edital.cobertura.length > 0 && (
        <div className="mt-6">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-medium text-muted">
              Cobertura por disciplina — {edital.titulo}
            </h2>
            <button onClick={() => setEditando((v) => !v)} className="link">
              {editando ? "concluir" : "editar matérias"}
            </button>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="py-1.5">Disciplina</th>
                <th className="py-1.5 text-right">Tópicos</th>
                <th className="py-1.5 text-right">Cobertura</th>
              </tr>
            </thead>
            <tbody>
              {edital.cobertura.map((c) => (
                <tr key={c.disciplina} className="border-b border-line">
                  <td className="py-1.5">{c.disciplina}</td>
                  <td className="py-1.5 text-right tabular-nums">{c.topicos_no_edital}</td>
                  <td className="py-1.5 text-right tabular-nums">{c.cobertura_pct}%</td>
                  {editando && (
                    <td className="w-8 py-1.5 text-right">
                      <button
                        onClick={() => ajustar({ remover: [c.disciplina] })}
                        disabled={ajustando}
                        title={`Tirar ${c.disciplina} do edital`}
                        className="text-subtle transition-colors hover:text-danger"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>

          {editando && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (novaDisc.trim()) ajustar({ adicionar: [novaDisc.trim()] });
              }}
              className="mt-3 flex gap-2"
            >
              <input
                value={novaDisc}
                onChange={(e) => setNovaDisc(e.target.value)}
                placeholder="Acrescentar matéria que a leitura não achou"
                className="field !py-2 text-[13px]"
              />
              <button type="submit" disabled={!novaDisc.trim() || ajustando} className="chip">
                <Plus className="h-3.5 w-3.5" />
                adicionar
              </button>
            </form>
          )}
          {/* Matéria acrescentada na mão entra SEM os tópicos do edital, e a
              tela diz isso: ela conta pro recorte da mesa (é daí que
              `mesa.disciplinas()` sai) mas não tem árvore de tópicos pra
              medir cobertura. Prometer "0%" sem explicar seria número que
              responde outra pergunta. */}
          {editando && (
            <p className="mt-2.5 text-[12px] text-subtle">
              Tirar uma matéria apaga os tópicos dela deste edital e muda o ritmo necessário —
              seu progresso e suas respostas não são apagados. Matéria acrescentada aqui entra
              no recorte da mesa, mas sem os tópicos do edital.
            </p>
          )}
        </div>
      )}

      {/* Ingerir edital mora no /onboarding, não aqui. Esta tela é de
          LEITURA — quanto falta, quanto está coberto — e enfiar um upload
          no rodapé dela fazia a tela sem edital abrir com um formulário em
          vez de dizer o que está acontecendo. */}
      <div className="mt-8 border-t border-line pt-6">
        <h2 className="mb-2 text-sm font-medium text-muted">
          {edital ? "Trocar o edital desta mesa" : "Esta mesa ainda não tem edital"}
        </h2>
        <p className="mb-3.5 text-[13px] text-muted">
          {edital
            ? "Subir um edital novo substitui este nos cálculos de meta e no recorte da mesa."
            : "Sem edital eu não sei a data da prova, quantos tópicos faltam nem quais matérias " +
              "recortar — a mesa mostra o acervo inteiro e a meta fica sem prazo."}
        </p>
        <Link href="/onboarding" className="btn-primary inline-flex">
          <Upload className="h-4 w-4" />
          {edital ? "Subir outro edital" : "Subir o PDF do edital"}
        </Link>
      </div>
    </div>
  );
}
