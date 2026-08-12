"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { NavBar } from "@/components/NavBar";
import { ErroApi, ErroCaderno, getErros, getToken, limparToken } from "@/lib/api";

export default function PaginaErros() {
  const router = useRouter();
  const [erros, setErros] = useState<ErroCaderno[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getErros()
      .then(setErros)
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
      });
  }, [router]);

  return (
    <main className="mx-auto max-w-2xl p-8">
      <NavBar />
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">caderno de erros</h1>
        <p className="mt-1 text-sm text-muted">ordenado por reincidência — o que mais volta primeiro.</p>
      </div>

      {erro && <p className="callout-danger">{erro}</p>}
      {!erro && !erros && <p className="text-sm text-muted">carregando…</p>}
      {erros && erros.length === 0 && (
        <p className="text-muted">nenhuma reincidência ainda — bom sinal.</p>
      )}

      {erros && erros.length > 0 && (
        <ul className="space-y-3">
          {erros.map((e) => (
            <li key={e.questao_id}>
              <Link href={`/questao/${e.questao_id}`} className="card-link">
                <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                  <span className="badge-accent">
                    {e.disciplina} · {e.tema}
                  </span>
                  <span className="whitespace-nowrap text-muted">
                    {e.vezes}× · última {e.ultima}
                  </span>
                </div>
                <p className="text-sm">{e.enunciado}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
