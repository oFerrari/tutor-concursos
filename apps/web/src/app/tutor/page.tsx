"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUp } from "lucide-react";
import { MarcaGlifo } from "@/components/Marca";
import { ErroApi, Fonte, perguntar } from "@/lib/api";
import { ABERTURA_TUTOR, FLASHCARD_EXEMPLO, QUESTAO_EXEMPLO, ROTA_DO_DIA } from "@/mock/prototipo";

/**
 * O Tutor — tela principal do protótipo: conversa, e dentro da conversa a
 * questão socrática e o flashcard.
 *
 * O que é REAL aqui: o campo de baixo. Ele chama `POST /perguntar`, que é
 * a busca híbrida sobre a lei seca (`core/retrieval.py` + `socratic.explicar`)
 * e devolve resposta COM as fontes — e as fontes aparecem, porque uma
 * resposta sobre lei sem o artigo de origem é exatamente o tipo de coisa
 * que o projeto inteiro existe pra não fazer.
 *
 * O que é vitrine: a abertura, a rota do dia, a questão A/B/C e o
 * flashcard, todos de `mock/prototipo.ts`.
 *
 * TODO(backend): a questão do protótipo tem alternativas A/B/C; a `questao`
 * do schema tem `gabarito` em TEXTO ABERTO e o diálogo real
 * (`/questoes/{id}/avaliar`) avalia resposta escrita, com dica e revelação
 * de gabarito na 3ª tentativa. São dois modelos diferentes de questão, e
 * ligar esta tela é decidir qual vale — não é fiação. O caminho de resposta
 * aberta já funciona hoje em `/fila` e `/desafio` (`<DialogoQuestao>`).
 *
 * Os botões "Errei · 1d / Difícil · 3d / Bom · 9d / Fácil · 21d" também
 * são vitrine, e de um jeito que MERECE nota: o agendamento aqui não é
 * SM-2 com nota do usuário, é caixa de Leitner decidida por
 * `core/scheduler_regras.py` a partir do veredito e da penalidade — quem
 * escolhe o intervalo é a regra, não a pessoa. Ligar esses botões seria
 * trocar a regra de agendamento do produto, não conectar um clique.
 */
type Mensagem =
  | { autor: "usuario"; texto: string }
  | { autor: "tutor"; texto: string; fontes?: Fonte[] };

export default function PaginaTutor() {
  const [escolhida, setEscolhida] = useState<string | null>(null);
  const [respondida, setRespondida] = useState(false);
  const [virado, setVirado] = useState(false);

  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [pensando, setPensando] = useState(false);
  const fim = useRef<HTMLDivElement>(null);

  const perguntarAoTutor = useCallback(async (texto: string) => {
    if (!texto) return;
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
    setPensando(true);
    try {
      const r = await perguntar(texto);
      setMensagens((m) => [...m, { autor: "tutor", texto: r.resposta, fontes: r.fontes }]);
    } catch (err) {
      setMensagens((m) => [
        ...m,
        { autor: "tutor", texto: err instanceof ErroApi ? err.message : "não deu pra conectar com a API" },
      ]);
    } finally {
      setPensando(false);
      requestAnimationFrame(() => fim.current?.scrollIntoView({ behavior: "smooth" }));
    }
  }, []);

  // O composer do panorama manda pra cá com `?q=`. Lido de
  // `window.location` num efeito, e não com `useSearchParams`, porque o
  // hook obrigaria envolver a página inteira num <Suspense> só pra ler um
  // parâmetro opcional que só existe quando alguém veio do painel.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      window.history.replaceState(null, "", "/tutor");
      perguntarAoTutor(q.trim());
    }
  }, [perguntarAoTutor]);

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    const texto = pergunta.trim();
    if (!texto || pensando) return;
    setPergunta("");
    perguntarAoTutor(texto);
  }

  const acertou = escolhida === QUESTAO_EXEMPLO.correta;

  function classeOpcao(letra: string): string {
    if (respondida && letra === QUESTAO_EXEMPLO.correta) return "opcao-certa";
    if (respondida && letra === escolhida) return "opcao-errada";
    if (escolhida === letra) return "opcao-ativa";
    return "opcao";
  }

  function classeLetra(letra: string): string {
    if (respondida && letra === QUESTAO_EXEMPLO.correta) return "letra-certa";
    if (escolhida === letra) return "letra-ativa";
    return "letra";
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-2 pt-6">
        <div className="mx-auto flex max-w-[720px] flex-col gap-[18px]">
          <p className="text-center font-mono text-[11px] uppercase tracking-[1.5px] text-[#45454d]">
            {ABERTURA_TUTOR.horario}
          </p>

          {/* ------------------------------------------ abertura + rota */}
          <div className="flex items-start gap-3">
            <span className="mt-0 flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-accent-foreground">
              <MarcaGlifo className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="rotulo mb-2">FerrarIA · iniciou a conversa</p>
              <div className="balao-tutor">
                <p className="text-[15px] leading-[1.65]">{ABERTURA_TUTOR.paragrafo1}</p>
                <p className="mt-3 text-[15px] leading-[1.65] text-[#b6b6bd]">
                  {ABERTURA_TUTOR.paragrafo2Prefixo}
                  <span className="font-semibold text-accent-text">{ABERTURA_TUTOR.paragrafo2Destaque}</span>
                  {ABERTURA_TUTOR.paragrafo2Sufixo}
                </p>

                <div className="mt-3.5 flex flex-col gap-2">
                  {ROTA_DO_DIA.map((r) => (
                    <div key={r.n} className="passo-rota">
                      <span className="passo-numero">{r.n}</span>
                      <span className="min-w-0 flex-1 text-[13.5px]">{r.texto}</span>
                      <span className="shrink-0 font-mono text-[11.5px] text-subtle">{r.tempo}</span>
                    </div>
                  ))}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Link href="/desafio" className="btn-primary">
                    Aceitar a rota
                  </Link>
                  <Link href="/fila" className="btn-ghost">
                    Só tenho 20 min
                  </Link>
                  <Link href="/simulado" className="btn-ghost">
                    Quero simulado
                  </Link>
                </div>
              </div>
            </div>
          </div>

          {/* ------------------------------------------- fala do aluno */}
          <div className="flex justify-end">
            <div className="balao-usuario">{ABERTURA_TUTOR.perguntaUsuario}</div>
          </div>

          {/* ------------------------------- resposta socrática + questão */}
          <div className="flex items-start gap-3">
            <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-accent-foreground">
              <MarcaGlifo className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="balao-tutor mb-3">
                <p className="text-[15px] leading-[1.65]">{ABERTURA_TUTOR.respostaSocratica}</p>
              </div>

              {/* ---------------------------------------------- questão */}
              <div
                className="overflow-hidden rounded-[14px] border bg-surface"
                style={{
                  borderColor: respondida
                    ? acertou
                      ? "var(--success-line)"
                      : "var(--danger-line)"
                    : "var(--line)",
                }}
              >
                <div className="faixa-card">
                  <span className="text-accent-text">{QUESTAO_EXEMPLO.fonte[0]}</span>
                  <span>{QUESTAO_EXEMPLO.fonte[1]}</span>
                  <span>{QUESTAO_EXEMPLO.fonte[2]}</span>
                </div>

                <div className="px-[18px] py-4">
                  <p className="mb-4 text-[14.5px] leading-relaxed">{QUESTAO_EXEMPLO.enunciado}</p>

                  <div className="flex flex-col gap-2">
                    {QUESTAO_EXEMPLO.alternativas.map((a) => (
                      <button
                        key={a.letra}
                        disabled={respondida}
                        onClick={() => setEscolhida(a.letra)}
                        className={classeOpcao(a.letra)}
                      >
                        <span className={classeLetra(a.letra)}>{a.letra}</span>
                        <span className="flex-1 leading-relaxed">{a.texto}</span>
                        {respondida && (a.letra === QUESTAO_EXEMPLO.correta || a.letra === escolhida) && (
                          <span
                            className="shrink-0 text-[13px] font-bold"
                            style={{
                              color:
                                a.letra === QUESTAO_EXEMPLO.correta ? "var(--success)" : "var(--accent-text)",
                            }}
                          >
                            {a.letra === QUESTAO_EXEMPLO.correta ? "✓" : "✕"}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>

                  {!respondida ? (
                    <div className="mt-3.5 flex flex-wrap items-center justify-between gap-3">
                      <span className="font-mono text-[11px] text-label">A–C selecionar</span>
                      <button
                        disabled={!escolhida}
                        onClick={() => setRespondida(true)}
                        className="btn-primary"
                      >
                        Responder
                      </button>
                    </div>
                  ) : (
                    <div className="mt-4 border-t border-line-soft pt-3.5">
                      <div className="mb-2.5 flex items-center gap-2.5">
                        <span
                          className="flex h-[22px] w-[22px] items-center justify-center rounded-full text-[12px] font-bold text-accent-foreground"
                          style={{ background: acertou ? "var(--success)" : "var(--accent)" }}
                        >
                          {acertou ? "✓" : "✕"}
                        </span>
                        <span className="text-sm font-semibold">
                          {acertou
                            ? "Correto — extingue a punibilidade"
                            : `Marcou ${escolhida} · a correta é ${QUESTAO_EXEMPLO.correta}`}
                        </span>
                      </div>
                      <p className="rotulo mb-2">dica socrática</p>
                      <p className="mb-3 text-sm leading-[1.65] text-[#b6b6bd]">{QUESTAO_EXEMPLO.dica}</p>
                      <div className="flex flex-wrap gap-2">
                        {["Errei · 1d", "Difícil · 3d", "Bom · 9d"].map((r) => (
                          <button
                            key={r}
                            onClick={() => {
                              setRespondida(false);
                              setEscolhida(null);
                            }}
                            className="btn-ghost text-[12.5px]"
                          >
                            {r}
                          </button>
                        ))}
                        <button
                          onClick={() => {
                            setRespondida(false);
                            setEscolhida(null);
                          }}
                          className="btn-primary text-[12.5px]"
                        >
                          Fácil · 21d
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* -------------------------------------------- flashcard */}
              <div className="mt-3 overflow-hidden rounded-[14px] border border-line bg-surface">
                <div className="faixa-card justify-between">
                  <span className="text-accent-text">Flashcard · fixação</span>
                  <span>{FLASHCARD_EXEMPLO.posicao}</span>
                </div>
                <div className="px-[18px] py-5 text-center">
                  <p className="mb-3.5 text-[15.5px] font-medium">{FLASHCARD_EXEMPLO.frente}</p>
                  {virado ? (
                    <div>
                      <p className="mb-3.5 text-[17px] font-semibold text-accent-text">
                        {FLASHCARD_EXEMPLO.verso}
                      </p>
                      <button onClick={() => setVirado(false)} className="btn-ghost text-[12.5px]">
                        Esconder
                      </button>
                    </div>
                  ) : (
                    <button onClick={() => setVirado(true)} className="btn-ghost">
                      Mostrar resposta
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* --------------------------------- conversa real (/perguntar) */}
          {mensagens.map((m, i) =>
            m.autor === "usuario" ? (
              <div key={i} className="flex justify-end">
                <div className="balao-usuario">{m.texto}</div>
              </div>
            ) : (
              <div key={i} className="flex items-start gap-3">
                <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-accent-foreground">
                  <MarcaGlifo className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="balao-tutor">
                    <p className="whitespace-pre-wrap text-[15px] leading-[1.65]">{m.texto}</p>
                    {m.fontes && m.fontes.length > 0 && (
                      <div className="mt-3 border-t border-line-soft pt-3">
                        <p className="rotulo mb-2">fontes</p>
                        <div className="flex flex-wrap gap-2">
                          {m.fontes.map((f) => (
                            <span key={f.id} className="badge-neutral">
                              {f.norma && f.artigo ? `${f.norma} art. ${f.artigo}` : f.titulo}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          )}

          {pensando && (
            <p className="rotulo animate-[pxPulse_1.4s_ease-in-out_infinite] pl-[42px]">consultando o acervo</p>
          )}

          <div ref={fim} />
        </div>
      </div>

      {/* ------------------------------------------------- composer */}
      <div className="shrink-0 px-5 pb-5 pt-3">
        <form
          onSubmit={enviar}
          className="mx-auto max-w-[720px] rounded-[18px] border border-line-strong bg-surface-input px-3.5 pb-2.5 pt-3.5 shadow-[var(--shadow-float)] focus-within:border-accent"
        >
          <textarea
            rows={1}
            value={pergunta}
            onChange={(e) => setPergunta(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                enviar(e);
              }
            }}
            placeholder="Pergunte sobre a lei — ex.: art. 312 do CP"
            className="max-h-40 w-full resize-none bg-transparent text-[15px] leading-relaxed text-foreground outline-none placeholder:text-subtle"
          />
          <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
              <Link href="/meta" className="chip text-[12.5px]">
                Meu edital
              </Link>
              <span className="chip cursor-default text-[12.5px]">Modo Socrático</span>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-2.5">
              <span className="font-mono text-[11px] text-label">FerrarIA 2.0</span>
              <button
                type="submit"
                disabled={!pergunta.trim() || pensando}
                className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-accent text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-40"
                aria-label="enviar pergunta"
              >
                <ArrowUp className="h-[17px] w-[17px]" strokeWidth={2.6} />
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
