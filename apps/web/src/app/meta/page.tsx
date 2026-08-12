"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  EditalAtual,
  ErroApi,
  Meta,
  ResultadoIngestaoEdital,
  getEdital,
  getMeta,
  getToken,
  ingerirEdital,
  limparToken,
} from "@/lib/api";

export default function PaginaMeta() {
  const router = useRouter();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [edital, setEdital] = useState<EditalAtual | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [arquivo, setArquivo] = useState<File | null>(null);
  const [orgao, setOrgao] = useState("");
  const [banca, setBanca] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [resultadoUpload, setResultadoUpload] = useState<ResultadoIngestaoEdital | null>(null);

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

  async function aoEnviarEdital(e: React.FormEvent) {
    e.preventDefault();
    if (!arquivo || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      // Sem título explícito, a API cairia no nome do arquivo TEMPORÁRIO
      // (aleatório, ilegível) — o nome do PDF enviado é o fallback que
      // faz sentido, não o arquivo interno que o servidor cria pra salvar o upload.
      const tituloPadrao = arquivo.name.replace(/\.pdf$/i, "");
      const r = await ingerirEdital(arquivo, tituloPadrao, orgao || undefined, banca || undefined);
      setResultadoUpload(r);
      await carregar(); // meta/edital agora refletem o que acabou de subir
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra ingerir o edital");
    } finally {
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
        <form onSubmit={aoEnviarEdital} className="max-w-sm space-y-3">
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-muted"
          />
          <input
            type="text"
            placeholder="órgão (opcional)"
            value={orgao}
            onChange={(e) => setOrgao(e.target.value)}
            className="field"
          />
          <input
            type="text"
            placeholder="banca (opcional)"
            value={banca}
            onChange={(e) => setBanca(e.target.value)}
            className="field"
          />
          <button type="submit" disabled={!arquivo || enviando} className="btn-primary">
            {enviando ? "processando…" : "enviar"}
          </button>
        </form>

        {resultadoUpload && (
          <div className="mt-4 card text-sm">
            <p>
              data da prova identificada: <strong>{resultadoUpload.data_prova ?? "não encontrada"}</strong>
            </p>
            {resultadoUpload.candidatos_data.length > 1 && (
              <div className="mt-2 text-xs text-muted">
                <p>outros candidatos (confira se a escolha acima está certa):</p>
                <ul className="mt-1 space-y-1">
                  {resultadoUpload.candidatos_data.slice(1).map((c, i) => (
                    <li key={i}>
                      {c.data} (pontuação {c.pontuacao}) — …{c.contexto}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-2 text-muted">
              {resultadoUpload.topicos} tópicos em {resultadoUpload.disciplinas.length} disciplinas
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
