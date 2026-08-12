"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { DialogoQuestao } from "@/components/DialogoQuestao";
import { ErroApi, Questao, getQuestao, getToken } from "@/lib/api";

export default function PaginaResponder() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const questaoId = Number(params.id);

  const [questao, setQuestao] = useState<Questao | null>(null);
  const [erroCarregar, setErroCarregar] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getQuestao(questaoId)
      .then(setQuestao)
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          router.push("/login");
          return;
        }
        setErroCarregar(e instanceof ErroApi ? e.message : "não deu pra carregar a questão");
      });
  }, [questaoId, router]);

  if (erroCarregar) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <p className="callout-danger">{erroCarregar}</p>
      </main>
    );
  }
  if (!questao) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <p className="text-sm text-muted">carregando…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <DialogoQuestao
        questao={questao}
        rotuloContinuar="voltar pra fila"
        onFechado={() => router.push("/fila")}
        onSair={() => router.push("/fila")}
      />
    </main>
  );
}
