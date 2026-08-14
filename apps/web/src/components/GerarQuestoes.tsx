"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { ErroApi, QuestoesGeradas, gerarQuestoes } from "@/lib/api";

/**
 * "Não tem questão disto? Faça." — o botão que fecha o buraco entre ter
 * material no acervo e ter o que estudar.
 *
 * Até aqui a fila só servia o que já estava na tabela `questao`, e essa
 * tabela só crescia por `gerar.py`, rodado à mão numa máquina. Toda mesa
 * cujo edital cobrisse disciplina ainda não gerada abria vazia — de TI,
 * bancária, fiscal, e também Direito Administrativo, que tinha 245 chunks
 * da Lei 8.112 no acervo e zero questão. O material estava lá.
 *
 * EXPLÍCITO, nunca automático: gerar gasta cota de LLM e ESCREVE no acervo
 * compartilhado. Disparar isso sozinho ao abrir a fila faria cada refresh
 * queimar cota — custo que aparece na fatura antes de aparecer na tela.
 *
 * O 409 tem texto próprio: "o acervo não tem material dessa matéria" e "a
 * IA falhou agora" pedem ações opostas do aluno (ingerir material × tentar
 * de novo), e um "erro" genérico faria as duas parecerem a mesma coisa.
 */
export function GerarQuestoes({
  tema,
  quantidade = 3,
  rotulo = "Gerar questões a partir do material",
  conversaId,
  onPronto,
  onQuestoes,
}: {
  tema?: string;
  quantidade?: number;
  rotulo?: string;
  /** Gerando DENTRO de uma conversa: o fato entra na linha do tempo dela. */
  conversaId?: number;
  onPronto?: () => void;
  /** Recebe as questões criadas. Quem passa isto RESPONDE ali mesmo, em vez
   *  de mandar o aluno pra outra tela — no chat, ser jogado pra /fila no
   *  meio de um raciocínio quebra justamente o que a conversa construiu. */
  onQuestoes?: (qs: QuestoesGeradas["questoes"]) => void;
}) {
  const [gerando, setGerando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [semMaterial, setSemMaterial] = useState(false);
  const [resumo, setResumo] = useState<string | null>(null);

  async function gerar() {
    if (gerando) return;
    setGerando(true);
    setErro(null);
    setSemMaterial(false);
    setResumo(null);
    try {
      const r = await gerarQuestoes(tema, quantidade, undefined, conversaId);
      const n = r.questoes.length;
      setResumo(
        n === 0
          ? "A IA não produziu nenhuma questão utilizável desta vez — tente de novo."
          : `${n} ${n === 1 ? "questão criada" : "questões criadas"} de ${r.fontes.join(", ")}` +
            (r.descartadas > 0
              ? ` · ${r.descartadas} descartada${r.descartadas > 1 ? "s" : ""} por citar artigo fora do material`
              : "")
      );
      if (n > 0) {
        onQuestoes?.(r.questoes);
        onPronto?.();
      }
    } catch (e) {
      if (e instanceof ErroApi && e.status === 409) setSemMaterial(true);
      else setErro(e instanceof ErroApi ? e.message : "Não deu pra gerar agora");
    } finally {
      setGerando(false);
    }
  }

  return (
    <div>
      <button onClick={gerar} disabled={gerando} className="btn-primary">
        <Sparkles className="h-4 w-4" />
        {gerando ? "Criando questões…" : rotulo}
      </button>
      {gerando && (
        <p className="mt-2 text-[12.5px] text-subtle">
          A IA está lendo os trechos de lei do acervo e escrevendo as perguntas. Leva alguns
          segundos.
        </p>
      )}
      {resumo && <p className="mt-2.5 text-[13px] text-muted">{resumo}</p>}
      {semMaterial && (
        <p className="mt-2.5 text-[13px] text-warning">
          Não há material dessas disciplinas no acervo — não é a IA que falhou. Ingira a lei
          correspondente antes (as leis públicas ficam em <span className="font-mono">corpus/</span>).
        </p>
      )}
      {erro && <p className="mt-2.5 text-[13px] text-danger">{erro}</p>}
    </div>
  );
}
