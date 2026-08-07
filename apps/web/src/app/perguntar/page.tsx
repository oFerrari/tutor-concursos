"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { NavBar } from "@/components/NavBar";
import { ErroApi, Fonte, getToken, limparToken, perguntar } from "@/lib/api";

type Item = { pergunta: string; resposta: string; citadas: string[]; consultadas: string[] };

function referencia(f: Fonte): string {
  return f.artigo ? `${f.titulo}, art. ${f.artigo}` : f.titulo;
}

function marca(f: Fonte): string {
  return f.artigo ? `art. ${f.artigo}` : f.titulo;
}

export default function PaginaPerguntar() {
  const router = useRouter();
  const [pergunta, setPergunta] = useState("");
  const [itens, setItens] = useState<Item[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  async function aoEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!pergunta.trim() || enviando) return;
    setEnviando(true);
    setErro(null);
    const perguntaAtual = pergunta;
    try {
      const r = await perguntar(perguntaAtual);
      // Listar tudo que foi recuperado engana: o modelo usa uma fração.
      // Mostra só o que ele realmente citou; o resto vai como "consultado" —
      // mesma lógica de chat.py perguntar().
      const citadas = new Set<string>();
      const consultadas = new Set<string>();
      for (const f of r.fontes) {
        (r.resposta.includes(marca(f)) ? citadas : consultadas).add(referencia(f));
      }
      setItens((prev) => [
        ...prev,
        { pergunta: perguntaAtual, resposta: r.resposta, citadas: [...citadas], consultadas: [...consultadas] },
      ]);
      setPergunta("");
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        limparToken();
        router.push("/login");
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <h1 className="mb-1 text-xl font-semibold">perguntar</h1>
      <p className="mb-6 text-sm opacity-70">pergunta livre, ancorada no acervo — não é a questão do quadro.</p>

      {itens.length === 0 && !enviando && (
        <p className="mb-6 text-sm opacity-50">nenhuma pergunta ainda.</p>
      )}

      <ul className="mb-6 space-y-4">
        {itens.map((it, i) => (
          <li key={i} className="rounded border border-black/10 p-4">
            <p className="text-sm font-medium opacity-70">{it.pergunta}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm">{it.resposta}</p>
            {(it.citadas.length > 0 || it.consultadas.length > 0) && (
              <div className="mt-3 space-y-1 text-xs opacity-60">
                {it.citadas.length > 0 && <p>citado: {it.citadas.join(" · ")}</p>}
                {it.consultadas.length > 0 && <p>consultado: {it.consultadas.join(" · ")}</p>}
              </div>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={aoEnviar} className="space-y-2">
        <textarea
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          rows={3}
          className="w-full rounded border border-black/20 p-3 text-sm"
          placeholder="ex.: diferença entre dolo eventual e culpa consciente"
        />
        {erro && <p className="text-sm text-red-600">{erro}</p>}
        <button
          type="submit"
          disabled={enviando || !pergunta.trim()}
          className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {enviando ? "consultando o acervo…" : "perguntar"}
        </button>
      </form>
    </main>
  );
}
