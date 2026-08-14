"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AvisoAcervo } from "@/components/AvisoAcervo";
import { useRouter } from "next/navigation";
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
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
      });
  }, [router]);

  if (erro) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="callout-danger">{erro}</p>
      </div>
    );
  }

  if (!questoes || !carga) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="text-sm text-muted">Carregando…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl p-6 md:p-10">
      <Sugestao />
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Fila do dia</h1>
        <p className="mt-1 text-sm text-muted">
          {questoes.length} questões · {carga.revisoes} revisões venceram, {carga.ineditas} inéditas
          {carga.atraso > 0 && <span className="text-warning"> · {carga.atraso} de atraso</span>}
        </p>
      </div>

      {questoes.length === 0 ? (
        <>
          <AvisoAcervo />
          <p className="mt-4 text-muted">Nada pendente hoje.</p>
        </>
      ) : (
        <ul className="space-y-3">
          {questoes.map((q) => (
            <li key={q.id}>
              <Link href={`/questao/${q.id}`} className="card-link cursor-pointer">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="badge-accent">{q.disciplina}</span>
                  <span className="badge-neutral">Caixa {q.caixa}</span>
                </div>
                <p className="mb-2 text-sm text-muted">{q.tema}</p>
                <p className="text-base font-medium leading-relaxed text-foreground">{q.enunciado}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
