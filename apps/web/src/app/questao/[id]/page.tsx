"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { DialogoQuestao } from "@/components/DialogoQuestao";
import { Voltar } from "@/components/Voltar";
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
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="callout-danger">{erroCarregar}</p>
      </div>
    );
  }
  if (!questao) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="text-sm text-muted">carregando…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      {/* href fixo, não router.back(): a origem daqui é sempre a fila, e
          o back() do navegador poderia devolver pra uma questão já
          respondida se a pessoa chegou navegando entre elas. */}
      <Voltar href="/fila" rotulo="voltar pra fila" />
      <DialogoQuestao
        questao={questao}
        rotuloContinuar="voltar pra fila"
        onFechado={() => router.push("/fila")}
        onSair={() => router.push("/fila")}
      />
    </div>
  );
}
