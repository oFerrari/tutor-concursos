"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  EditalAtual,
  ErroApi,
  Meta,
  getEdital,
  getMeta,
  getToken,
  criarRascunho,
  limparToken,
} from "@/lib/api";

export default function PaginaMeta() {
  const router = useRouter();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [edital, setEdital] = useState<EditalAtual | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [enviando, setEnviando] = useState(false);

  async function carregar() {
    try {
      setMeta(await getMeta());
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        limparToken();
        router.push("/login");
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
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

  async function enviarEdital(arquivo: File) {
    setEnviando(true);
    setErro(null);
    try {
      // Vai pra CURADORIA, não direto pro banco: o edital pode ter vários
      // cargos, e quem escolhe qual entra na mesa é a pessoa.
      const d = await criarRascunho(arquivo, arquivo.name.replace(/\.pdf$/i, ""));
      router.push(`/edital/${d.id}`);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra ler o edital");
      setEnviando(false);
    }
  }

  const prob = meta?.probabilidade_fechamento;
  const probOk = prob && !("erro" in prob);

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">meta até a prova</h1>
        <p className="mt-1 text-sm text-muted">dias restantes, cobertura e probabilidade de fechamento.</p>
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
                cobertura {meta.cobertura_pct}% · {meta.questoes_pendentes} questões pendentes ·{" "}
                {meta.questoes_respondidas} já respondidas
              </p>
              {meta.ritmo_necessario != null && (
                <p className="mt-1 text-muted">ritmo necessário: {meta.ritmo_necessario} questões/dia</p>
              )}
              {probOk && (
                <p className="mt-3 font-medium">
                  probabilidade de fechamento: <span className="text-accent">{prob.probabilidade_fechamento_pct}%</span>
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
          <h2 className="mb-2 text-sm font-medium text-muted">cobertura por disciplina — {edital.titulo}</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="py-1.5">disciplina</th>
                <th className="py-1.5 text-right">tópicos</th>
                <th className="py-1.5 text-right">cobertura</th>
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

      <div className="mt-8 border-t border-line pt-6">
        <h2 className="mb-3 text-sm font-medium text-muted">
          {edital ? "ingerir outro edital" : "ingerir edital"}
        </h2>
        <input
          type="file"
          accept="application/pdf"
          disabled={enviando}
          onChange={(e) => {
            const f = e.target.files?.[0];
            // zera pra permitir reescolher o MESMO arquivo (o `change` só
            // dispara quando o value muda)
            e.target.value = "";
            if (f) enviarEdital(f);
          }}
          className="block w-full text-sm text-muted"
        />
        <p className="mt-2 text-[12px] text-subtle">
          {enviando
            ? "lendo o edital…"
            : "o PDF vai pra uma tela de conferência: você escolhe o cargo e revisa as matérias antes de valer."}
        </p>
      </div>
    </div>
  );
}
