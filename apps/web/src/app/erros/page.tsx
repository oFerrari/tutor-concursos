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
  // SUPERADOS: errados um dia, hoje na caixa de 15 dias. Saem da lista principal
  // sem sumir — é a prova de que o caderno serviu.
  const [superados, setSuperados] = useState<ErroCaderno[]>([]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getErros(true)
      .then(setSuperados)
      .catch(() => {});
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
        <p className="text-muted">
          {superados.length > 0 ? "Nenhum erro pendente — todos os que você teve já foram vencidos." : "Nenhuma reincidência ainda — bom sinal."}
        </p>
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

      {superados.length > 0 && (
        <div className="mt-10">
          <h2 className="text-sm font-medium text-muted">Superados ({superados.length})</h2>
          <p className="mb-3 mt-1 text-[12.5px] text-subtle">
            Você errou e depois acertou até a revisão de 15 dias. Continuam na fila de revisão, fora da lista de erros.
          </p>
          <ul className="space-y-2">
            {superados.map((e) => (
              <li key={e.questao_id}>
                <Link href={`/questao/${e.questao_id}`} className="card-link cursor-pointer opacity-80">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="selo-ok">{e.disciplina}</span>
                    <span className="whitespace-nowrap text-xs text-muted">errou {e.vezes}×</span>
                  </div>
                  <p className="text-sm leading-relaxed text-body">{e.enunciado}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
