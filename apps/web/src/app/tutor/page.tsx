"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowUp } from "lucide-react";
import { MarcaGlifo } from "@/components/Marca";
import { BalaoQuestao } from "@/components/BalaoQuestao";
import { GerarQuestoes } from "@/components/GerarQuestoes";
import { ResultadoQuestao } from "@/components/DialogoQuestao";
import { ErroApi, Fonte, Questao, getFila, getToken, limparToken, perguntar } from "@/lib/api";
import { ABERTURA_TUTOR, FLASHCARD_EXEMPLO, ROTA_DO_DIA } from "@/mock/prototipo";

/**
 * O Tutor — tela principal do protótipo: conversa, e dentro da conversa a
 * questão socrática e o flashcard.
 *
 * O que é REAL aqui: o campo de baixo (chat livre, `POST /perguntar` — ver
 * distinção citado × consultado, absorvida de `/perguntar`, que era rota
 * paralela órfã do menu e foi removida depois de portar o que tinha de
 * único pra cá) E a questão embutida na conversa, que puxa a PRÓXIMA da
 * fila de verdade (`GET /fila`) e roda por `<BalaoQuestao>` — dispatcher
 * dinâmico por tipo (`components/BalaoQuestao.tsx`) que hoje só sabe
 * renderizar "resposta_livre" com dado de verdade, porque é o único tipo
 * que `questao.gabarito` (texto aberto) suporta; os outros dois tipos
 * (múltipla escolha, certo/errado) existem na arquitetura mas avisam que
 * ainda não têm base real, em vez de fingir. TODA a lógica de avaliação,
 * dica e gravação de tentativa é a mesma de `/questao/[id]` e `/desafio`
 * (`<DialogoQuestao>`) — nada foi reescrito, só reembalado pro formato de
 * balão de chat.
 *
 * O que continua vitrine: a abertura, a rota do dia e o flashcard, de
 * `mock/prototipo.ts` — nenhum dos dois foi tocado nesta revisão.
 *
 * Os botões "Errei · 1d / Difícil · 3d / Bom · 9d / Fácil · 21d" do
 * flashcard também são vitrine, e de um jeito que MERECE nota: o
 * agendamento real não é SM-2 com nota do usuário, é caixa de Leitner
 * decidida por `core/scheduler_regras.py` a partir do veredito e da
 * penalidade — quem escolhe o intervalo é a regra, não a pessoa. Ligar
 * esses botões seria trocar a regra de agendamento do produto, não
 * conectar um clique.
 */
type Mensagem =
  | { autor: "usuario"; texto: string }
  | { autor: "tutor"; texto: string; citadas: string[]; consultadas: string[] };

function referencia(f: Fonte): string {
  return f.artigo ? `${f.titulo}, art. ${f.artigo}` : f.titulo;
}

function marca(f: Fonte): string {
  return f.artigo ? `art. ${f.artigo}` : f.titulo;
}

export default function PaginaTutor() {
  const router = useRouter();
  const [virado, setVirado] = useState(false);

  // Questão embutida no chat: puxa a próxima da fila de verdade (mesma
  // fonte de /fila) uma vez, no mount. `resultado` fica null enquanto o
  // <BalaoQuestao> está interativo; vira objeto quando o aluno fecha a
  // questão, e o balão congela numa mensagem de resultado (não some, viraria
  // "onde foi minha resposta?" no meio da conversa).
  const [questao, setQuestao] = useState<Questao | null | undefined>(undefined); // undefined = carregando
  const [resultado, setResultado] = useState<ResultadoQuestao | null>(null);
  const [erroQuestao, setErroQuestao] = useState<string | null>(null);

  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [pensando, setPensando] = useState(false);
  const fim = useRef<HTMLDivElement>(null);

  // Última fala do aluno: o assunto corrente da conversa. Serve de tema pra
  // geração de questão — a busca precisa de um texto pra escolher o artigo,
  // e o que o aluno perguntou descreve melhor o que ele quer treinar do que
  // a resposta longa do tutor.
  const ultimoAssunto = [...mensagens].reverse().find((m) => m.autor === "usuario")?.texto;

  // Mesma guarda de toda outra tela autenticada (/fila, /stats, /questao/[id]
  // etc.) — o /tutor tinha ficado de fora dela, sozinho, antes desta rota
  // absorver o /perguntar (que tinha a guarda) e ganhar essa consistência.
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getFila()
      .then((fila) => setQuestao(fila[0] ?? null))
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) {
          limparToken();
          router.push("/login");
          return;
        }
        setErroQuestao(e instanceof ErroApi ? e.message : "Não deu pra buscar a fila");
        setQuestao(null);
      });
  }, [router]);

  const perguntarAoTutor = useCallback(async (texto: string) => {
    if (!texto) return;
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
    setPensando(true);
    try {
      const r = await perguntar(texto);
      // Só o que o modelo de fato citou no texto vira "citado" — o resto do
      // que a busca híbrida recuperou (mas o modelo não usou) vira
      // "consultado". Listar tudo igual como "fonte" mascarava essa
      // diferença; mesma lógica que existia em /perguntar e em chat.py.
      const citadas = new Set<string>();
      const consultadas = new Set<string>();
      for (const f of r.fontes) {
        (r.resposta.includes(marca(f)) ? citadas : consultadas).add(referencia(f));
      }
      setMensagens((m) => [
        ...m,
        { autor: "tutor", texto: r.resposta, citadas: [...citadas], consultadas: [...consultadas] },
      ]);
    } catch (err) {
      if (err instanceof ErroApi && err.status === 401) {
        limparToken();
        router.push("/login");
        return;
      }
      setMensagens((m) => [
        ...m,
        {
          autor: "tutor",
          texto: err instanceof ErroApi ? err.message : "Não deu pra conectar com a API",
          citadas: [],
          consultadas: [],
        },
      ]);
    } finally {
      setPensando(false);
      requestAnimationFrame(() => fim.current?.scrollIntoView({ behavior: "smooth" }));
    }
  }, [router]);

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

              {/* ------------------------------------- questão da fila */}
              {questao === undefined && (
                <p className="rotulo animate-[pxPulse_1.4s_ease-in-out_infinite]">buscando sua próxima questão</p>
              )}

              {questao === null && (
                <div className="callout-info !p-4 text-sm">
                  {erroQuestao ?? "Nenhuma questão pendente agora — sua fila está em dia."}{" "}
                  <Link href="/fila" className="link">Ver fila →</Link>
                </div>
              )}

              {questao && !resultado && (
                <BalaoQuestao tipo="resposta_livre" questao={questao} onFechado={setResultado} />
              )}

              {questao && resultado && (
                <div className={resultado.veredito === "correta" ? "callout-success" : "callout-warning !p-4"}>
                  <p className="font-medium capitalize">{resultado.veredito}</p>
                  <p className="mt-1 text-sm opacity-90">{resultado.comentario}</p>
                  <p className="mt-2 text-sm opacity-90">
                    caixa {resultado.caixa} · volta em {resultado.prox_revisao}
                  </p>
                </div>
              )}

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

          {/* --------------------------------------------- conversa real */}
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
                    {(m.citadas.length > 0 || m.consultadas.length > 0) && (
                      <div className="mt-3 space-y-1.5 border-t border-line-soft pt-3">
                        {m.citadas.length > 0 && (
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rotulo">citado</span>
                            {m.citadas.map((c) => (
                              <span key={c} className="badge-neutral">{c}</span>
                            ))}
                          </div>
                        )}
                        {m.consultadas.length > 0 && (
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rotulo text-subtle">consultado</span>
                            {m.consultadas.map((c) => (
                              <span key={c} className="badge-neutral opacity-60">{c}</span>
                            ))}
                          </div>
                        )}
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

          {/* Treinar o que acabou de ser explicado, sem trocar de tela. O
              tema é a última pergunta DO ALUNO — é o que ele está estudando
              agora, e é com ele que a busca escolhe de qual artigo cobrar.
              Antes, pedir questão no chat recebia "meu acervo não traz itens
              prontos": verdade sobre a tabela `questao`, e mentira sobre o
              que o sistema consegue fazer com a lei que já tem. */}
          {ultimoAssunto && !pensando && (
            <div className="mt-2 pl-[42px]">
              <GerarQuestoes
                tema={ultimoAssunto}
                quantidade={2}
                rotulo="Quero questões sobre isto"
                onPronto={() => router.push("/fila")}
              />
            </div>
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
