"use client";

import { useEffect, useState } from "react";
import { Voltar } from "@/components/Voltar";
import { EditorPerfil } from "@/components/EditorPerfil";
import { ENTREVISTA } from "@/lib/perfil";
import { getPerfil, salvarPerfil } from "@/lib/api";

/**
 * "Preferências de estudo" — o mesmo editor do onboarding, fora do fluxo de
 * primeiro contato.
 *
 * Faltava isto: `usuario.perfil` (migração 015) e o `GET/PUT /me/perfil`
 * já existiam, mas o único jeito de gravar era responder a entrevista no
 * dia em que a conta nasce. Rotina muda — quem disse "2h" pode passar a
 * ter 4, quem disse "Começando" pode estar "Avançado" três meses depois —
 * e não existia pra onde voltar. `EditorPerfil` já era a peça certa: o
 * onboarding só precisava dela como componente, não como página.
 *
 * Igual à entrevista original: grava a cada clique, sem botão de "salvar".
 * Sem edital pra subir aqui — é só as três perguntas.
 */
export default function PaginaPerfil() {
  const [respostas, setRespostas] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    // Padrão primeiro, resposta real por cima: um campo que o aluno nunca
    // tocou não pode chegar como `undefined` no editor — nenhum chip
    // aceso pareceria "ainda não decidi", quando na verdade é "usando o
    // valor padrão da entrevista".
    const padrao = Object.fromEntries(ENTREVISTA.map((p) => [p.chave, p.padrao]));
    getPerfil()
      .then((p) => setRespostas({ ...padrao, ...p }))
      .catch(() => setRespostas(padrao));
  }, []);

  function escolherResposta(chave: string, valor: string) {
    if (!respostas) return;
    const novas = { ...respostas, [chave]: valor };
    setRespostas(novas);
    salvarPerfil(novas).catch(() => {});
  }

  return (
    <div className="mx-auto w-full max-w-[680px] px-6 pb-10 pt-7">
      <Voltar />

      <div className="mb-5">
        <p className="rotulo mb-2">conta · preferências de estudo</p>
        <h1 className="text-[22px] leading-tight tracking-[-0.3px]">Suas horas, nível e turno</h1>
        <p className="mt-2.5 text-[15px] leading-[1.65] text-muted">
          O tutor usa isto pra calibrar o tamanho do que sugere na fila, no desafio e no
          simulado — não adianta propor três horas de estudo a quem tem uma.
        </p>
      </div>

      {respostas && <EditorPerfil respostas={respostas} onEscolher={escolherResposta} />}

      <p className="mt-4 text-[12px] text-subtle">Salvo a cada escolha.</p>
    </div>
  );
}
