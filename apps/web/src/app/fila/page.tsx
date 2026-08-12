"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { NavBar } from "@/components/NavBar";
import { Sugestao } from "@/components/Sugestao";
import { Carga, ErroApi, Questao, getCarga, getFila, getToken, limparToken } from "@/lib/api";

export default function PaginaFila() {
  const router = useRouter();
  const [questoes, setQuestoes] = useState<Questao[] | null>(null);
  const [carga, setCarga] = useState<Carga | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    Promise.all([getFila(), getCarga()])
      .then(([f, c]) => {
        setQuestoes(f);
        setCarga(c);
      })
      .catch((e) => {
        // 401 = token expirado/invalido — mesma UX de "precisa logar de novo".
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
      });
  }, [router]);

  if (erro) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <NavBar />
        <p className="callout-danger">{erro}</p>
      </main>
    );
  }

  if (!questoes || !carga) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <NavBar />
        <p className="text-sm text-muted">carregando…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <Sugestao />
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">fila do dia</h1>
        <p className="mt-1 text-sm text-muted">
          {questoes.length} questões · {carga.revisoes} revisões venceram, {carga.ineditas} inéditas
          {carga.atraso > 0 && <span className="text-warning"> · {carga.atraso} de atraso</span>}
        </p>
      </div>

      {questoes.length === 0 ? (
        <p className="text-muted">nada pendente hoje.</p>
      ) : (
        <ul className="space-y-3">
          {questoes.map((q) => (
            <li key={q.id}>
              <Link href={`/questao/${q.id}`} className="card-link">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="badge-accent">{q.disciplina}</span>
                  <span className="badge-neutral">caixa {q.caixa}</span>
                </div>
                <p className="text-xs text-muted">{q.tema}</p>
                <p className="mt-1">{q.enunciado}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
