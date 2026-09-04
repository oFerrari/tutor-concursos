"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowUp } from "lucide-react";
import { MarcaGlifo } from "@/components/Marca";
import { BalaoQuestao } from "@/components/BalaoQuestao";
import { GerarQuestoes } from "@/components/GerarQuestoes";
import { ResultadoQuestao } from "@/components/DialogoQuestao";
import { TextoDoTutor } from "@/components/TextoDoTutor";
import {
  ErroApi,
  Fonte,
  Questao,
  getConversa,
  getFila,
  getToken,
  perguntar,
} from "@/lib/api";
import { sair } from "@/lib/cache";
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
  // O id da conversa em curso. `null` = ainda não existe; a primeira
  // pergunta abre uma no servidor e devolve o id, então não há chamada
  // extra só pra criar (migração 014).
  const [conversaId, setConversaId] = useState<number | null>(null);
  // Questões geradas DENTRO desta conversa, respondidas aqui mesmo. Antes o
  // botão empurrava pra /fila: você pedia questão no meio de um raciocínio
  // e era jogado pra outra tela — o que quebra exatamente o que a conversa
  // acabou de construir. Elas continuam entrando na fila normal (são
  // gravadas no acervo); a diferença é onde você as responde.
  const [geradas, setGeradas] = useState<Questao[]>([]);
  /** O acervo não tinha trecho do assunto da conversa e o gerador caiu pro
   *  recorte da mesa. As questões valem e têm proveniência — só não são do que
   *  vocês estavam tratando, e dizer isso é obrigação: sem o aviso, o tutor
   *  abria com "vamos treinar isso" e vinham questões de outra matéria. */
  const [foraDoAssunto, setForaDoAssunto] = useState(false);
  const [pensando, setPensando] = useState(false);
  const fim = useRef<HTMLDivElement>(null);
  // O CONTAINER que rola, não o `window`. Há DOIS scrollers aninhados aqui (o
  // <main> do AppShell e este), e `scrollIntoView` decide sozinho qual ancestral
  // mexer — foi por isso que a rolagem "funcionava" no meu teste e não na tela.
  // Mexer no scrollTop do container certo é determinístico.
  const scroller = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  // `suave` só quando o movimento COMUNICA algo (chegou resposta). Ao reabrir uma
  // conversa inteira, animar a rolagem demora e parece travamento.
  const irAoFim = useCallback((suave = false) => {
    const el = scroller.current;
    if (!el) return;
    // Dois quadros: o primeiro roda antes de o React pintar o conteúdo novo, e
    // aí `scrollHeight` ainda é o de antes — a rolagem para no meio.
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        el.scrollTo({ top: el.scrollHeight, behavior: suave ? "smooth" : "auto" })
      )
    );
  }, []);

  // TEXTAREA QUE CRESCE COM O TEXTO, como em qualquer chat moderno. Era
  // `rows={1}` fixo: quem escrevia três linhas via uma. `auto` antes de medir
  // porque `scrollHeight` não DIMINUI enquanto a altura fixa anterior o segura —
  // sem o reset, o campo cresce e nunca volta ao apagar texto.
  useEffect(() => {
    const el = campo.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [pergunta]);

  // O botão aparece quando o aluno já falou alguma coisa — e é só isso que esta
  // tela decide. QUAL é o assunto da conversa quem responde é o servidor, que
  // tem a conversa inteira no banco.
  //
  // Antes daqui saía `tema = última fala do aluno`, literal. Numa conversa real
  // a última fala foi "vamos", então o backend rodou `buscar("vamos")` e gerou
  // questão de CP art. 352 (evasão) e CF art. 200 (SUS) no meio de uma conversa
  // inteira sobre eficácia das normas constitucionais. O cliente estava
  // respondendo uma pergunta que não é dele — a mesma razão de a mesa padrão ser
  // resolvida no servidor e nunca recalculada aqui.
  const alunoJaFalou = mensagens.some((m) => m.autor === "usuario");

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
          sair();
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
    // Rola JÁ ao mandar, não só ao receber: o balão do aluno mais o "pensando"
    // já empurram o fim da conversa pra fora da tela, e era aí que começava o
    // "tenho que ficar scrollando pra baixo".
    irAoFim(true);
    try {
      const r = await perguntar(texto, conversaId ?? undefined);
      // Guardar o id é o que faz o SEGUNDO turno ter memória do
      // primeiro: sem ele cada pergunta abriria conversa nova e o
      // histórico não voltaria pro modelo.
      setConversaId(r.conversa_id);
      // AVISA A SIDEBAR. Relatado em uso: "comecei outro chat com ele e ele não
      // jogou nos recentes". A conversa nasce aqui (o `POST /perguntar` cria
      // quando não recebe id), e a lista vive noutra árvore de componentes que
      // buscava `/conversas` só na montagem.
      //
      // Dispara em TODO turno, não só no primeiro: o `titulo` e a contagem de
      // mensagens são calculados pelo servidor, e sem o aviso a linha ficaria
      // marcando "1" pra sempre numa conversa de vinte mensagens.
      window.dispatchEvent(new CustomEvent("tutor:conversas-mudaram"));
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
      // QUESTÕES QUE O SERVIDOR JÁ GEROU porque a fala pedia treino
      // (`core/pedido.py`). Mesmo destino das que vinham do botão — `setGeradas`
      // as desenha aqui mesmo, com `<DialogoQuestao>` —, e mesmo estado no
      // banco: proveniência, gravação e fila SM-2. O clique é que sumiu.
      //
      // `caixa: 0` e `prox_revisao: ""` são o mesmo preenchimento que o caminho
      // do botão faz: questão recém-criada não tem progresso ainda, e é a fila
      // que passa a contá-la.
      setForaDoAssunto(Boolean(r.questoes_fora_do_assunto));
      if (r.questoes?.length) {
        setGeradas(
          r.questoes.map((q) => ({ ...q, caixa: 0, prox_revisao: "" }) as Questao)
        );
      }
    } catch (err) {
      if (err instanceof ErroApi && err.status === 401) {
        sair();
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
      irAoFim(true);
    }
  }, [router, conversaId, irAoFim]);
  // Reabrir uma conversa gravada (014). Num `useCallback` porque agora tem DOIS
  // gatilhos: o `?c=` de quem chega de outra tela, e o evento de quem clica no
  // recente já estando aqui.
  const abrirConversa = useCallback((id: number) => {
    getConversa(id)
      .then((conv) => {
        setConversaId(conv.id);
        // O que foi gravado volta como veio: as fontes de cada turno ficaram
        // salvas justamente pra reabrir a conversa ancorada. Sem isso o aluno
        // leria uma resposta que citava a lei e voltaria a ela sem as citações —
        // pior que não ter citação nenhuma.
        setMensagens(
          conv.mensagens
            // EVENTO (016) NÃO É BALÃO. "Você propôs 2 questões sobre X" caía no
            // `else` do ternário abaixo e aparecia como fala do TUTOR —
            // inventando na tela uma resposta que o modelo nunca gerou. É o erro
            // que a decisão da 016 evitou NO BANCO (foi por isso que `autor`
            // ganhou um terceiro valor) e que voltou pela porta da frente do
            // front. O texto é escrito PRA O MODELO, em segunda pessoa dirigida
            // ao tutor; ele segue trabalhando em `historico_para_prompt`.
            .filter((m) => m.autor !== "evento")
            .map((m) => {
              if (m.autor === "aluno") {
                return { autor: "usuario" as const, texto: m.texto };
              }
              // SET, não array: o mesmo documento aparece em mais de um chunk, e
              // `referencia()` devolve só o título quando não há artigo (material
              // do aluno, tipo `historico`) — então a mesma etiqueta repetia. O
              // React reclamou disso no log, com a chave literal:
              // "Encountered two children with the same key,
              // `curso-392722-aula-04-2787-completo`". O caminho AO VIVO já
              // deduplicava com Set; só o de reabrir não, e a divergência entre
              // os dois é que deixou passar.
              const citadas = new Set<string>();
              const consultadas = new Set<string>();
              for (const f of m.fontes) {
                (m.texto.includes(marca(f)) ? citadas : consultadas).add(referencia(f));
              }
              return {
                autor: "tutor" as const,
                texto: m.texto,
                citadas: [...citadas],
                consultadas: [...consultadas],
              };
            })
        );
        // AO REABRIR, CAI NO FIM — é onde a conversa parou. `irAoFim` mexe no
        // scrollTop do container certo; `scrollIntoView` escolhia sozinho entre
        // os dois scrollers aninhados e não funcionava na tela.
        irAoFim();
      })
      .catch(() => {});
  }, [irAoFim]);

  // Dois parâmetros, lidos de `window.location` num efeito e não com
  // `useSearchParams` — o hook obrigaria envolver a página num <Suspense> só pra
  // ler algo opcional.
  //
  //   ?q=  o composer do panorama manda a pergunta pra cá
  //   ?c=  a sidebar reabre uma conversa antiga, vindo de OUTRA tela
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    const c = Number(params.get("c"));

    if (Number.isInteger(c) && c > 0) {
      window.history.replaceState(null, "", "/tutor");
      abrirConversa(c);
      return;
    }

    if (q) {
      window.history.replaceState(null, "", "/tutor");
      perguntarAoTutor(q.trim());
    }
  }, [perguntarAoTutor, abrirConversa]);

  // CLICAR NO RECENTE ESTANDO JÁ NO /tutor. O efeito acima só funciona na
  // MONTAGEM: ele lê `window.location.search` e depende de
  // `[perguntarAoTutor, abrirConversa]` — ir de /tutor?c=1 pra /tutor?c=413 não
  // remonta a rota nem muda essas dependências, então ele nunca reroda. E o
  // `replaceState` ainda apaga a query, então nem dependência nova resolveria.
  // Relatado: "não tá mais funcionando o recentes, ele não tá recuperando a
  // conversa" — com `GET /tutor?c=413 200` no log, porque a navegação acontecia
  // e a leitura não.
  //
  // É o TERCEIRO botão deste app com o mesmo defeito (nova conversa, pausar e
  // entender, e agora este), e o padrão de conserto já existe: CustomEvent da
  // sidebar pra cá.
  useEffect(() => {
    function abrir(e: Event) {
      const id = (e as CustomEvent<{ id: number }>).detail?.id;
      if (Number.isInteger(id) && id > 0) abrirConversa(id);
    }
    window.addEventListener("tutor:abrir-conversa", abrir);
    return () => window.removeEventListener("tutor:abrir-conversa", abrir);
  }, [abrirConversa]);


  // "Nova conversa" (sidebar) zera a tela sem trocar de rota. Ver o
  // comentário no botão: o Next não remonta /tutor pra ele mesmo.
  useEffect(() => {
    function nova() {
      setConversaId(null);
      setMensagens([]);
      setPergunta("");
    }
    window.addEventListener("tutor:nova", nova);
    return () => window.removeEventListener("tutor:nova", nova);
  }, []);

  // Apagou pela lixeira da sidebar a conversa que está ABERTA: a tela tem que
  // esvaziar. Deixar as mensagens ali daria um chat conversando sobre um
  // histórico que não existe mais — o próximo turno abriria conversa nova em
  // silêncio, e o aluno leria isso como "perdi o que escrevi".
  //
  // Só reage se o id bater. Apagar uma conversa antiga enquanto se conversa
  // noutra não pode limpar a tela de quem está no meio de uma frase.
  useEffect(() => {
    function apagada(e: Event) {
      const id = (e as CustomEvent<{ id: number }>).detail?.id;
      setConversaId((atual) => {
        if (atual === null || atual !== id) return atual;
        setMensagens([]);
        setPergunta("");
        setGeradas([]);
        return null;
      });
    }
    window.addEventListener("tutor:conversa-apagada", apagada);
    return () => window.removeEventListener("tutor:conversa-apagada", apagada);
  }, []);

  // "Pausar e entender isto" (`<Intervencao>`), quando a questão que gerou os 3
  // erros está EMBUTIDA nesta conversa. O botão fazia
  // `router.push("/tutor?q=...")` e o Next não remonta a rota pra ela mesma:
  // clique sem efeito nenhum, relatado assim mesmo. Aqui a pergunta entra na
  // conversa ATUAL, que é o que "entender ISTO" quer dizer.
  useEffect(() => {
    function perguntarDeFora(e: Event) {
      const q = (e as CustomEvent<{ pergunta: string }>).detail?.pergunta?.trim();
      if (q) perguntarAoTutor(q);
    }
    window.addEventListener("tutor:perguntar", perguntarDeFora);
    return () => window.removeEventListener("tutor:perguntar", perguntarDeFora);
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
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-5 pb-2 pt-6">
        <div className="mx-auto flex max-w-[720px] flex-col gap-[18px]">
          <p className="text-center font-mono text-[11px] uppercase tracking-[1.5px] text-[#45454d]">
            {ABERTURA_TUTOR.horario}
          </p>

          {/* ------------------------------------------ abertura + rota */}
          <div className="balao-subida flex items-start gap-3" style={{ animationDelay: "40ms" }}>
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
          <div className="balao-subida flex justify-end" style={{ animationDelay: "170ms" }}>
            <div className="balao-usuario">{ABERTURA_TUTOR.perguntaUsuario}</div>
          </div>

          {/* ------------------------------- resposta socrática + questão */}
          <div className="balao-subida flex items-start gap-3" style={{ animationDelay: "300ms" }}>
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
                <BalaoQuestao tipo={questao.tipo} questao={questao} onFechado={setResultado} />
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
                    <TextoDoTutor texto={m.texto} />
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

          {/* As questões criadas nesta conversa, respondidas AQUI. Cada uma
              com `key` própria: sem isso o React reaproveita a instância e a
              segunda questão abre já mostrando o resultado da primeira — o
              mesmo bug que o /desafio teve. */}
          {geradas.length > 0 && foraDoAssunto && (
            <div className="mt-2 pl-[42px]">
              <p className="callout-warning !p-3 text-[13px]">
                Não tenho trecho de lei do que estávamos tratando, então estas questões são
                de outros pontos do seu edital. Suba material desse assunto na{" "}
                <Link href="/materiais" className="underline underline-offset-2">
                  sua biblioteca
                </Link>{" "}
                e eu passo a cobrar dele.
              </p>
            </div>
          )}
          {geradas.map((q) => (
            <div key={q.id} className="pl-[42px]">
              <BalaoQuestao
                tipo={q.tipo}
                questao={q}
                conversaId={conversaId ?? undefined}
                onFechado={() => setGeradas((atual) => atual.filter((x) => x.id !== q.id))}
              />
            </div>
          ))}

          {/* Treinar o que acabou de ser explicado, sem trocar de tela. Só
              `conversaId` vai daqui: o servidor lê a conversa e decide o assunto
              (`core/assunto.py`). Antes, pedir questão no chat recebia "meu
              acervo não traz itens prontos": verdade sobre a tabela `questao`, e
              mentira sobre o que o sistema consegue fazer com a lei que já tem. */}
          {alunoJaFalou && !pensando && (
            <div className="mt-2 pl-[42px]">
              <GerarQuestoes
                quantidade={2}
                rotulo="Quero questões sobre isto"
                conversaId={conversaId ?? undefined}
                onQuestoes={(qs) =>
                  setGeradas(
                    qs.map((q) => ({ ...q, caixa: 0, prox_revisao: "" }) as Questao)
                  )
                }
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
          /* SEM `focus-within:border-accent`: o vermelho da marca em volta do
             campo enquanto se digita foi relatado como desagradável, e ele
             também gasta a cor de ÊNFASE no estado mais comum da tela. O anel
             de foco fica discreto (borda mais clara), que é o que qualquer chat
             faz — o vermelho continua reservado pro que é ação. */
          className="mx-auto max-w-[720px] rounded-[18px] border border-line-strong bg-surface-input px-3.5 pb-2.5 pt-3.5 shadow-[var(--shadow-float)] transition-colors focus-within:border-line-stronger"
        >
          <textarea
            ref={campo}
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
            className="max-h-40 w-full resize-none overflow-y-auto bg-transparent text-[15px] leading-relaxed text-foreground outline-none placeholder:text-subtle"
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
