"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ErroApi, ErroCaderno, getErros, getToken } from "@/lib/api";
import { Carregando } from "@/components/Carregando";
import { gravarCache, sair, useCache } from "@/lib/cache";

export default function PaginaErros() {
  const router = useRouter();
  // Do cache primeiro: o caderno visto nesta sessão aparece na hora.
  const [erros, setErros] = useCache<ErroCaderno[]>("erros");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getErros()
      .then((e) => {
        setErros(e);
        gravarCache("erros", e);
      })
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          sair();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
      });
    // `setErros` vem do `useCache`: é o setter do `useState` de lá, estável,
    // mas o lint não enxerga a origem e pede que ele seja declarado.
  }, [router, setErros]);

  return (
    <div className="mx-auto max-w-3xl p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Caderno de erros</h1>
        <p className="mt-1 text-sm text-muted">Ordenado por reincidência — o que mais volta primeiro.</p>
      </div>

      {erro && <p className="callout-danger">{erro}</p>}
      {!erro && !erros && <Carregando linhas={4} />}
      {erros && erros.length === 0 && (
        <p className="text-muted">Nenhuma reincidência ainda — bom sinal.</p>
      )}

      {erros && erros.length > 0 && (
        <ul className="space-y-3">
          {erros.map((e) => (
            <li key={e.questao_id}>
              <Link href={`/questao/${e.questao_id}`} className="card-link cursor-pointer">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="badge-accent">{e.disciplina}</span>
                  <span className="whitespace-nowrap text-xs text-muted">
                    {e.vezes}× · última {e.ultima}
                  </span>
                </div>
                <p className="mb-2 text-sm text-muted">{e.tema}</p>
                <p className="text-base font-medium leading-relaxed text-foreground">{e.enunciado}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
