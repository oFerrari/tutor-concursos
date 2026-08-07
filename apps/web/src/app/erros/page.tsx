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
      <h1 className="mb-1 text-xl font-semibold">caderno de erros</h1>
      <p className="mb-6 text-sm opacity-70">ordenado por reincidência — o que mais volta primeiro.</p>

      {erro && <p className="text-red-600">{erro}</p>}
      {!erro && !erros && <p className="text-sm opacity-60">carregando…</p>}
      {erros && erros.length === 0 && (
        <p className="opacity-60">nenhuma reincidência ainda — bom sinal.</p>
      )}

      {erros && erros.length > 0 && (
        <ul className="space-y-3">
          {erros.map((e) => (
            <li key={e.questao_id}>
              <Link
                href={`/questao/${e.questao_id}`}
                className="block rounded border border-black/10 p-4 hover:border-black/30"
              >
                <div className="mb-1 flex items-center justify-between text-xs opacity-60">
                  <span>
                    {e.disciplina} · {e.tema}
                  </span>
                  <span className="whitespace-nowrap">
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
