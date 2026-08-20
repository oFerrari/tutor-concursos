"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Hand } from "lucide-react";
import { Intervencao as Dados, getSugestao } from "@/lib/api";

/**
 * O tutor tomando o volante: aparece DEPOIS de uma resposta, quando a regra
 * de ritmo diz que continuar é pior que parar (3 erros seguidos).
 *
 * Por que aqui e não na fila: o momento em que a interrupção significa
 * alguma coisa é o instante seguinte ao erro, com o resultado ainda na
 * tela. Um banner no topo da fila seria lido como mais um aviso — e a
 * diferença entre isto e o `<Sugestao />` é justamente essa: sugestão é
 * tendência para ler quando quiser, intervenção é estado de AGORA.
 *
 * Ela nunca bloqueia: o botão de continuar segue ali, ao lado. Tutor que
 * impede o aluno de estudar é pior que tutor calado — o que se ganha aqui
 * é a oferta de saída, não o controle da sessão.
 *
 * Monta e busca uma vez, sem polling: quem renderiza este componente
 * acabou de registrar uma tentativa, então o dado do servidor já está
 * atualizado quando a requisição sai.
 */
export function Intervencao() {
  const router = useRouter();
  const pathname = usePathname();
  const [dados, setDados] = useState<Dados | null>(null);
  const [dispensado, setDispensado] = useState(false);

  useEffect(() => {
    getSugestao()
      .then((r) => setDados(r.intervencao))
      .catch(() => {});
  }, []);

  if (!dados || dispensado) return null;

  return (
    <div className="callout-warning mt-4 !p-4">
      <p className="flex items-start gap-2.5 text-sm font-medium">
        <Hand className="mt-0.5 h-4 w-4 shrink-0" />
        {dados.texto}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => {
            // Leva a pergunta PRONTA: pedir pro aluno formular "o que estou
            // errando?" no momento em que ele acabou de errar três vezes é
            // exigir energia justamente de quem já está sem ela.
            //
            // ESTANDO JÁ NO /tutor, `router.push("/tutor?q=...")` NÃO FAZ NADA:
            // o Next não remonta a rota pra ela mesma. E é o caso mais comum —
            // a questão que gerou os 3 erros costuma ser a que está embutida no
            // chat (`BalaoQuestao` -> `DialogoQuestao` -> este componente).
            // Relatado assim: "cliquei em pausar e entender isso e ele não fez
            // nada". É o mesmo defeito que o botão "Nova conversa" da sidebar já
            // tinha, e a saída é a mesma: CustomEvent pra página irmã.
            //
            // Mandar pra conversa ATUAL, e não abrir uma nova, é melhor de
            // propósito: "pausar e entender ISTO" só quer dizer algo com o que
            // acabou de acontecer na tela.
            if (pathname === "/tutor") {
              window.dispatchEvent(
                new CustomEvent("tutor:perguntar", { detail: { pergunta: dados.pergunta } })
              );
              setDispensado(true);
            } else {
              router.push(`/tutor?q=${encodeURIComponent(dados.pergunta)}`);
            }
          }}
          className="btn-primary"
        >
          Pausar e entender isto
        </button>
        <button onClick={() => setDispensado(true)} className="btn-ghost">
          Continuar mesmo assim
        </button>
      </div>
    </div>
  );
}
