"use client";

import { useRef, useState } from "react";
import { Avaliacao, ErroApi, Questao, Turno, avaliar, registrarTentativa } from "@/lib/api";

// Mesmas constantes de chat.py — MAX_DICAS/MAX_TENTATIVAS são regra de
// produto, não capricho de UI, então ficam iguais dos dois lados.
const MAX_DICAS = 3;
const MAX_TENTATIVAS = 3;

export type ResultadoQuestao = {
  veredito: Avaliacao["veredito"];
  comentario: string;
  caixa: number;
  prox_revisao: string;
};

type Props = {
  questao: Questao;
  /** Chamado depois que o usuário clica "continuar" no resultado — segue o fluxo normal (próxima questão, ou fila). */
  onFechado: (r: ResultadoQuestao) => void;
  /** "sair" no meio: aborta o fluxo inteiro (não é "pular esta e seguir"). Omitir esconde o botão. */
  onSair?: () => void;
  rotuloContinuar?: string;
};

/**
 * O diálogo socrático de uma questão — dica, erro, pergunta-guia, gabarito
 * na 3ª tentativa, registro no final. Extraído de `/questao/[id]` pra ser
 * reaproveitado por `/desafio`, mesma razão que fez `chat._estudar_lista`
 * existir separado de `estudar()` do lado Python: um dos dois blocos do
 * desafio usa exatamente este mesmo loop, só a lista de onde tira a
 * próxima questão é diferente.
 */
export function DialogoQuestao({ questao, onFechado, onSair, rotuloContinuar = "continuar" }: Props) {
  const [resposta, setResposta] = useState("");
  const [historico, setHistorico] = useState<Turno[]>([]);
  const [erradas, setErradas] = useState(0);
  const [dicasMostradas, setDicasMostradas] = useState(0);
  const [dicasPedidas, setDicasPedidas] = useState(0);
  const [ultimaResposta, setUltimaResposta] = useState("");
  const [avisouContrato, setAvisouContrato] = useState(false);
  const [gabaritoRevelado, setGabaritoRevelado] = useState(false);
  const [resultado, setResultado] = useState<ResultadoQuestao | null>(null);
  const [viaSair, setViaSair] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const inicio = useRef<number>(Date.now());

  async function fechar(
    veredito: Avaliacao["veredito"],
    respostaFinal: string,
    erradasFinal: number,
    dicasPedidasFinal: number
  ) {
    // PENALIDADE = errar, não receber dica. Dica automática ao errar já
    // conta como erro; contar as duas juntaria a mesma falha duas vezes.
    const penalidade = erradasFinal + dicasPedidasFinal;
    const segundos = Math.round((Date.now() - inicio.current) / 1000);
    const r = await registrarTentativa(questao.id, veredito, respostaFinal, penalidade, segundos);
    setResultado({
      veredito,
      // "acertou de primeira" só quando penalidade é 0 — correta na 2ª
      // tentativa (após erro) segue mostrando o que aconteceu, porque foi
      // isso que decidiu se a caixa promoveu ou ficou igual.
      comentario:
        veredito === "correta" && penalidade === 0
          ? "acertou de primeira"
          : `${erradasFinal} erro(s), ${dicasPedidasFinal} dica(s) pedida(s)`,
      caixa: r.caixa,
      prox_revisao: r.prox_revisao,
    });
  }

  async function aoEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!resposta.trim() || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const av = await avaliar(questao.id, resposta, erradas, historico);
      setUltimaResposta(resposta);

      if (av.veredito === "correta") {
        setHistorico((h) => [...h, { resposta, comentario: av.comentario, pergunta: "" }]);
        await fechar("correta", resposta, erradas, dicasPedidas);
        return;
      }

      const novasErradas = erradas + 1;
      setErradas(novasErradas);
      setHistorico((h) => [...h, { resposta, comentario: av.comentario, pergunta: av.pergunta }]);
      if (av.pergunta) setAvisouContrato(true);

      let novasDicasMostradas = dicasMostradas;
      if (dicasMostradas < Math.min(MAX_DICAS, questao.dicas.length)) {
        novasDicasMostradas = dicasMostradas + 1;
        setDicasMostradas(novasDicasMostradas);
      }

      if (av.revelar_gabarito) {
        setGabaritoRevelado(true);
        await fechar(av.veredito, resposta, novasErradas, dicasPedidas);
      } else {
        setResposta("");
      }
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
    } finally {
      setEnviando(false);
    }
  }

  function pedirDica() {
    const limite = Math.min(MAX_DICAS, questao.dicas.length);
    if (dicasMostradas < limite) {
      setDicasMostradas((d) => d + 1);
      setDicasPedidas((d) => d + 1);
    }
  }

  async function sair() {
    if (!onSair) return;
    if (ultimaResposta && !resultado) {
      setViaSair(true);
      await fechar("incorreta", ultimaResposta, erradas, dicasPedidas);
      return;
    }
    onSair();
  }

  function continuar() {
    if (!resultado) return;
    if (viaSair) {
      onSair?.();
    } else {
      onFechado(resultado);
    }
  }

  if (resultado) {
    const cor = resultado.veredito === "correta" ? "text-emerald-700" : "text-amber-700";
    return (
      <div>
        <div className={`rounded border p-4 ${cor}`}>
          <p className="font-medium">{resultado.veredito}</p>
          <p className="text-sm opacity-80">{resultado.comentario}</p>
          <p className="mt-2 text-sm opacity-80">
            caixa {resultado.caixa} · volta em {resultado.prox_revisao}
          </p>
        </div>
        <button onClick={continuar} className="mt-4 rounded bg-black px-4 py-2 text-sm text-white">
          {viaSair ? "sair" : rotuloContinuar}
        </button>
      </div>
    );
  }

  const restamDicas = Math.min(MAX_DICAS, questao.dicas.length) - dicasMostradas;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-xs opacity-60">
          {questao.disciplina} · {questao.tema} · caixa {questao.caixa}
        </p>
        {onSair && (
          <button onClick={sair} className="text-sm underline opacity-60">
            sair
          </button>
        )}
      </div>

      <div className="rounded border border-black/10 p-4">
        <p>{questao.enunciado}</p>
      </div>

      {historico.length > 0 && (
        <div className="mt-4 space-y-3">
          {historico.map((t, i) => (
            <div key={i} className="rounded border border-black/10 bg-black/[0.02] p-3 text-sm">
              <p className="opacity-70">
                <span className="font-medium">você:</span> {t.resposta}
              </p>
              <p className="mt-1">{t.comentario}</p>
              {t.pergunta && <p className="mt-1 text-cyan-700">→ {t.pergunta}</p>}
            </div>
          ))}
          {avisouContrato && !gabaritoRevelado && (
            <p className="text-xs opacity-50">
              (a pergunta acima é uma pista; sua resposta continua valendo para a questão do quadro)
            </p>
          )}
        </div>
      )}

      {dicasMostradas > 0 && (
        <div className="mt-4 space-y-1">
          {questao.dicas.slice(0, dicasMostradas).map((d, i) => (
            <p key={i} className="text-sm text-amber-700">
              dica {i + 1}: {d}
            </p>
          ))}
        </div>
      )}

      {gabaritoRevelado ? (
        <div className="mt-4 rounded border border-emerald-700/30 bg-emerald-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-emerald-700">gabarito</p>
          <p className="mt-1 text-sm">{questao.gabarito}</p>
          <p className="mt-3 text-sm opacity-60">registrando…</p>
        </div>
      ) : (
        <form onSubmit={aoEnviar} className="mt-4 space-y-2">
          <textarea
            value={resposta}
            onChange={(e) => setResposta(e.target.value)}
            rows={3}
            className="w-full rounded border border-black/20 p-3 text-sm"
            placeholder="sua resposta…"
          />
          {erro && <p className="text-sm text-red-600">{erro}</p>}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={pedirDica}
              disabled={restamDicas <= 0}
              className="text-sm underline opacity-70 disabled:opacity-30"
            >
              pedir dica ({restamDicas} disponível{restamDicas === 1 ? "" : "eis"})
            </button>
            <button
              type="submit"
              disabled={enviando || !resposta.trim()}
              className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {enviando ? "corrigindo…" : "responder"}
            </button>
          </div>
          <p className="text-xs opacity-50">
            tentativa {erradas + 1} de {MAX_TENTATIVAS}
          </p>
        </form>
      )}
    </div>
  );
}
