"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { NavBar } from "@/components/NavBar";
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
        <p className="text-red-600">{erro}</p>
      </main>
    );
  }

  if (!questoes || !carga) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <NavBar />
        <p className="text-sm opacity-60">carregando…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <h1 className="mb-1 text-xl font-semibold">fila do dia</h1>
      <p className="mb-6 text-sm opacity-70">
        {questoes.length} questões · {carga.revisoes} revisões venceram, {carga.ineditas} inéditas
        {carga.atraso > 0 && <span className="text-amber-600"> · {carga.atraso} de atraso</span>}
      </p>

      {questoes.length === 0 ? (
        <p className="opacity-60">nada pendente hoje.</p>
      ) : (
        <ul className="space-y-3">
          {questoes.map((q) => (
            <li key={q.id}>
              <Link
                href={`/questao/${q.id}`}
                className="block rounded border border-black/10 p-4 hover:border-black/30"
              >
                <p className="mb-1 text-xs opacity-60">
                  {q.disciplina} · {q.tema} · caixa {q.caixa}
                </p>
                <p>{q.enunciado}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
