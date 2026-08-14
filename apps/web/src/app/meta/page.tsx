"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import {
  EditalAtual,
  ErroApi,
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

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Meta até a prova</h1>
        <p className="mt-1 text-sm text-muted">Dias restantes, cobertura e probabilidade de fechamento.</p>
      </div>

      {erro && <p className="mb-4 callout-danger">{erro}</p>}

      {meta && (
        <div className="card text-sm">
          {meta.aviso ? (
            <p className="text-warning">{meta.aviso}</p>
          ) : (
            <>
              <p>{meta.dias_restantes} dias restantes {meta.edital && <span className="text-muted">· {meta.edital}</span>}</p>
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
          <h2 className="mb-2 text-sm font-medium text-muted">Cobertura por disciplina — {edital.titulo}</h2>
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
                </tr>
              ))}
            </tbody>
          </table>
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
