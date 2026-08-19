"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Mesa, getMesaAtual } from "@/lib/api";

/**
 * Explica o vazio nas telas de ESTUDO (fila, desafio, simulado) quando o
 * acervo não cobre as disciplinas da mesa.
 *
 * Por que aqui e não no cartão da mesa: listar o edital é útil por si só —
 * dá pra subir um PDF só pra ver quais matérias aquele concurso cobra, sem
 * ter material nenhum ingerido. O cartão deve listar normalmente. O vazio
 * só vira problema na hora de RESOLVER questão, e é aí que ele precisa de
 * justificativa em vez de uma lista vazia sem motivo aparente.
 *
 * A ferramenta não é de Direito: o recorte da mesa é por NOME de
 * disciplina e vale igual pra TI, bancária, fiscal ou policial. O que
 * limita é só o que já foi ingerido no acervo — e é exatamente isso que
 * este aviso diz.
 *
 * Devolve `null` quando não há o que explicar (mesa sem edital, ou acervo
 * cobrindo o recorte): aí o vazio tem outra causa — você já estudou tudo
 * hoje — e essa a própria tela explica.
 */
export function AvisoAcervo() {
  const [mesa, setMesa] = useState<(Mesa & { questoes: number }) | null>(null);

  useEffect(() => {
    getMesaAtual()
      .then(setMesa)
      .catch(() => setMesa(null));
  }, []);

  if (!mesa || !mesa.disciplinas || mesa.questoes > 0) return null;

  return (
    <div className="callout-info">
      <p className="text-sm">
        O acervo ainda não tem questão nenhuma das disciplinas de{" "}
        <span className="font-semibold text-accent-text">{mesa.nome}</span>.
      </p>
      <p className="mt-1.5 text-[13px] opacity-90">
        O edital foi lido normalmente — são {mesa.disciplinas.length} disciplinas, e dá pra
        conferir todas em <Link href="/meta" className="underline underline-offset-2">Meu edital</Link>.
        Só não há material ingerido que as cubra, então não há o que perguntar ainda.
      </p>
      <p className="mt-1.5 font-mono text-[11.5px] opacity-70">
        {mesa.disciplinas.slice(0, 6).join(" · ")}
        {mesa.disciplinas.length > 6 && ` · +${mesa.disciplinas.length - 6}`}
      </p>
    </div>
  );
}
