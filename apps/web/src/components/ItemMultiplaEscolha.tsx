"use client";

import { useState } from "react";
import { Avaliacao, ErroApi, Questao, avaliar, registrarTentativa } from "@/lib/api";
import { ResultadoQuestao } from "@/components/DialogoQuestao";
import { TextoAssociado } from "@/components/TextoAssociado";
import { Intervencao } from "@/components/Intervencao";

/**
 * MÚLTIPLA ESCOLHA (migração 037) — a questão de banca, literal do simulado
 * que o aluno subiu.
 *
 * Mesmo molde do `<ItemCertoErrado>` e pelo mesmo motivo: resposta única, sem
 * dica e sem segunda tentativa. Com cinco alternativas, "tente de novo" vira
 * eliminação por sorteio. O que fica no lugar é o COMENTÁRIO (o do professor,
 * quando a prova traz), mostrado junto do gabarito.
 *
 * A correção não passa pelo modelo: `/questoes/{id}/avaliar` compara a letra em
 * Python (`socratic.avaliar_multipla_escolha`).
 *
 * "Gabarito do tutor" aparece quando o arquivo não trazia o gabarito e o modelo
 * resolveu: o aluno precisa saber em qual gabarito pode confiar sem conferir.
 */
/** Fora do componente: o relógio só é lido no clique, nunca no render. */
function segundosDesde(inicio: number): number {
  return Math.round((Date.now() - inicio) / 1000);
}

export function ItemMultiplaEscolha({
  questao,
  rotuloContinuar = "próxima",
  conversaId,
  onFechado,
  onSair,
}: {
  questao: Questao;
  rotuloContinuar?: string;
  conversaId?: number;
  onFechado: (r: ResultadoQuestao) => void;
  onSair?: () => void;
}) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoQuestao | null>(null);
  const [marcada, setMarcada] = useState<string | null>(null);
  const [inicio] = useState(() => Date.now());
  const alternativas = questao.alternativas ?? [];

  async function responder(letra: string) {
    if (enviando || resultado) return;
    setMarcada(letra);
    setEnviando(true);
    setErro(null);
    try {
      const av: Avaliacao = await avaliar(questao.id, letra, 0, []);
      const segundos = segundosDesde(inicio);
      const r = await registrarTentativa(questao.id, av.veredito, letra, 0, segundos, conversaId);
      setResultado({ veredito: av.veredito, comentario: av.comentario, caixa: r.caixa,
                     prox_revisao: r.prox_revisao });
    } catch (e) {
      setMarcada(null);
      setErro(e instanceof ErroApi ? e.message : "Não deu pra registrar a resposta");
    } finally {
      setEnviando(false);
    }
  }

  const acertou = resultado?.veredito === "correta";
  const certa = questao.gabarito_letra;

  function classe(letra: string): string {
    const base = "flex w-full items-start gap-3 rounded-xl border px-3.5 py-3 text-left text-[15px] transition-colors";
    if (!resultado) {
      return `${base} border-line-strong bg-surface hover:border-accent hover:bg-surface-hover disabled:opacity-50`;
    }
    if (letra === certa) return `${base} border-success bg-surface-hover`;
    if (letra === marcada) return `${base} border-accent bg-surface-hover opacity-90`;
    return `${base} border-line bg-surface opacity-60`;
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs">
          <span className="badge-accent">{questao.disciplina}</span>
          <span className="truncate text-muted">{questao.tema}</span>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {questao.origem === "prova" && questao.numero_na_prova != null && (
            <span className="badge-neutral">questão {questao.numero_na_prova} da prova</span>
          )}
          {onSair && !resultado && (
            <button onClick={onSair} className="link">
              sair
            </button>
          )}
        </div>
      </div>

      <TextoAssociado texto={questao.contexto} ordem={questao.ordem_no_contexto} />

      <div className="card">
        <p className="whitespace-pre-line text-base leading-relaxed">{questao.enunciado}</p>
      </div>

      <div className="mt-4 space-y-2">
        {alternativas.map((a) => (
          <button key={a.letra} onClick={() => responder(a.letra)} disabled={enviando || !!resultado}
                  className={classe(a.letra)} aria-pressed={marcada === a.letra}>
            <span className="shrink-0 font-semibold">{a.letra})</span>
            <span className="leading-relaxed">{a.texto}</span>
          </button>
        ))}
      </div>

      {!resultado ? (
        <>
          {erro && <p className="mt-2 text-sm text-danger">{erro}</p>}
          <p className="mt-2.5 text-xs text-muted">Resposta única, sem dica: é assim que cai na prova.</p>
        </>
      ) : (
        <div>
          <div className={`mt-4 ${acertou ? "callout-success" : "callout-warning !p-4"}`}>
            <p className="font-medium">
              {acertou ? "Certa resposta" : "Resposta errada"}
              <span className="ml-2 font-normal opacity-80">
                · você marcou {marcada}, o gabarito é {certa}
                {questao.gabarito_fonte === "tutor" && " (gabarito do tutor: o arquivo não trazia)"}
              </span>
            </p>
            <p className="mt-2 whitespace-pre-line text-sm leading-relaxed opacity-90">{questao.gabarito}</p>
            <p className="mt-2.5 text-sm opacity-80">
              caixa {resultado.caixa} · volta em {resultado.prox_revisao}
            </p>
          </div>
          <button onClick={() => onFechado(resultado)} className="btn-primary mt-4">
            {rotuloContinuar}
          </button>
          <Intervencao />
        </div>
      )}
    </div>
  );
}
