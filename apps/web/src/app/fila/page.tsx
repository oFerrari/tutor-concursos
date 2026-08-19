"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AvisoAcervo } from "@/components/AvisoAcervo";
import { GerarQuestoes } from "@/components/GerarQuestoes";
import { useRouter } from "next/navigation";
import { Sugestao } from "@/components/Sugestao";
import { Carga, ErroApi, Questao, getCarga, getFila, getToken } from "@/lib/api";
import { gravarCache, lerCache, sair } from "@/lib/cache";

export default function PaginaFila() {
  const router = useRouter();
  // Semeado do cache: a fila que você já viu nesta sessão volta na hora e
  // revalida por baixo, em vez de piscar "Carregando…" a cada navegação.
  const [questoes, setQuestoes] = useState<Questao[] | null>(() => lerCache("fila"));
  const [carga, setCarga] = useState<Carga | null>(() => lerCache("carga"));
  const [erro, setErro] = useState<string | null>(null);

  // Em `useCallback` porque quem gera questão precisa recarregar a fila
  // depois: sem isso a questão recém-criada só apareceria num F5, e o botão
  // pareceria não ter feito nada.
  const carregar = useCallback(() => {
    Promise.all([getFila(), getCarga()])
      .then(([f, c]) => {
        setQuestoes(f);
        setCarga(c);
        gravarCache("fila", f);
        gravarCache("carga", c);
      })
      .catch((e) => {
        // 401 = token expirado/invalido — mesma UX de "precisa logar de novo".
        if (e instanceof ErroApi && e.status === 401) {
          sair();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
      });
  }, [router]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    carregar();
  }, [router, carregar]);

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
          {/* Fila vazia tem duas causas opostas: você já estudou tudo hoje,
              ou nunca houve questão dessas disciplinas. Nos dois casos há o
              que oferecer — o acervo pode ter lei ainda não cobrada. Quem
              decide gastar cota é o aluno, clicando. */}
          <div className="mt-5">
            <GerarQuestoes
              rotulo="Criar questões desta mesa a partir do material"
              onPronto={carregar}
            />
          </div>
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
