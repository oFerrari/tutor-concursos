"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";
import { Avaliacao, ErroApi, Questao, avaliar, registrarTentativa } from "@/lib/api";
import { ResultadoQuestao } from "@/components/DialogoQuestao";

/**
 * Item CERTO/ERRADO — o formato do Cebraspe (migração 012).
 *
 * Componente SEPARADO do `<DialogoQuestao>`, e não um `if` dentro dele, por
 * uma razão de produto e não de código: o diálogo socrático (dica →
 * pergunta-guia → gabarito, 3 tentativas) NÃO SE APLICA aqui. Numa
 * assertiva binária, qualquer dica é a resposta, e "tente de novo" vira
 * cara ou coroa com o gabarito garantido na segunda. Enfiar os dois fluxos
 * no mesmo componente significaria carregar estado (dicasMostradas,
 * erradas, historico, avisouContrato) que este formato nunca usa — e a
 * primeira mudança no fluxo discursivo passaria a arriscar quebrar este.
 *
 * O que este formato tem no lugar do diálogo: JULGAMENTO IMEDIATO e a
 * justificativa. É assim que se estuda item Cebraspe — o aprendizado está
 * em ler POR QUE a assertiva estava errada (qual prazo foi trocado, qual
 * "poderá" virou "deverá"), não em tentar de novo.
 *
 * A correção não passa pelo LLM: `/questoes/{id}/avaliar` despacha por tipo
 * e compara booleano em Python. Some a latência, some o custo, e some a
 * chance de o modelo discordar de si mesmo entre duas execuções.
 */
export function ItemCertoErrado({
  questao,
  rotuloContinuar = "próxima",
  onFechado,
  onSair,
}: {
  questao: Questao;
  rotuloContinuar?: string;
  onFechado: (r: ResultadoQuestao) => void;
  onSair?: () => void;
}) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoQuestao | null>(null);
  const [marcado, setMarcado] = useState<"C" | "E" | null>(null);
  const [inicio] = useState(() => Date.now());

  async function responder(escolha: "C" | "E") {
    if (enviando || resultado) return;
    setMarcado(escolha);
    setEnviando(true);
    setErro(null);
    try {
      const av: Avaliacao = await avaliar(questao.id, escolha, 0, []);
      const segundos = Math.round((Date.now() - inicio) / 1000);
      // dicas_usadas = 0 SEMPRE: não existe dica neste formato, então acerto
      // sempre promove a caixa. É o mesmo raciocínio do simulado, que também
      // nunca oferece dica — mesma regra de promoção, sinal limpo.
      const r = await registrarTentativa(questao.id, av.veredito, escolha, 0, segundos);
      setResultado({
        veredito: av.veredito,
        comentario: av.comentario,
        caixa: r.caixa,
        prox_revisao: r.prox_revisao,
      });
    } catch (e) {
      setMarcado(null);
      setErro(e instanceof ErroApi ? e.message : "Não deu pra registrar a resposta");
    } finally {
      setEnviando(false);
    }
  }

  const acertou = resultado?.veredito === "correta";

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <span className="badge-accent">{questao.disciplina}</span>
          <span className="text-muted">{questao.tema}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="badge-neutral">Caixa {questao.caixa}</span>
          {onSair && !resultado && (
            <button onClick={onSair} className="link">
              sair
            </button>
          )}
        </div>
      </div>

      {/* "Julgue o item" é a instrução literal da prova. Sem ela, uma
          assertiva solta parece um enunciado truncado. */}
      <div className="card">
        <p className="rotulo mb-2">julgue o item</p>
        <p className="text-base leading-relaxed">{questao.enunciado}</p>
      </div>

      {!resultado ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button
              onClick={() => responder("C")}
              disabled={enviando}
              className="flex items-center justify-center gap-2 rounded-xl border border-line-strong bg-surface py-3.5 text-[15px] font-medium transition-colors hover:border-success hover:bg-surface-hover disabled:opacity-50"
            >
              <Check className="h-4 w-4" strokeWidth={2.6} />
              Certo
            </button>
            <button
              onClick={() => responder("E")}
              disabled={enviando}
              className="flex items-center justify-center gap-2 rounded-xl border border-line-strong bg-surface py-3.5 text-[15px] font-medium transition-colors hover:border-accent hover:bg-surface-hover disabled:opacity-50"
            >
              <X className="h-4 w-4" strokeWidth={2.6} />
              Errado
            </button>
          </div>
          {erro && <p className="mt-2 text-sm text-danger">{erro}</p>}
          <p className="mt-2.5 text-xs text-muted">
            Resposta única, sem dica — é assim que o item cai na prova.
          </p>
        </>
      ) : (
        <div>
          <div className={`mt-4 ${acertou ? "callout-success" : "callout-warning !p-4"}`}>
            <p className="font-medium">
              {acertou ? "Certa resposta" : "Resposta errada"}
              <span className="ml-2 font-normal opacity-80">
                · você marcou {marcado === "C" ? "Certo" : "Errado"}, o gabarito é{" "}
                {questao.gabarito_ce ? "Certo" : "Errado"}
              </span>
            </p>
            {/* A justificativa é o produto aqui. Sem ela o aluno só sabe que
                errou, e itens C/E errados costumam falhar por UM detalhe —
                é esse detalhe que precisa ficar. */}
            <p className="mt-2 text-sm leading-relaxed opacity-90">{questao.gabarito}</p>
            <p className="mt-2.5 text-sm opacity-80">
              caixa {resultado.caixa} · volta em {resultado.prox_revisao}
            </p>
          </div>
          <button onClick={() => onFechado(resultado)} className="btn-primary mt-4">
            {rotuloContinuar}
          </button>
        </div>
      )}
    </div>
  );
}
