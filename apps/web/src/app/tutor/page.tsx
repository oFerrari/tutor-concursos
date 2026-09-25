"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, ArrowUp, Check, ClipboardList, Eye, EyeOff, Pencil, Square } from "lucide-react";
import { MarcaGlifo } from "@/components/Marca";
import { BalaoQuestao } from "@/components/BalaoQuestao";
import { GerarQuestoes } from "@/components/GerarQuestoes";
import { TextoDoTutor } from "@/components/TextoDoTutor";
import {
  COMANDOS,
  comandosSugeridos,
  desfazerTurno,
  ehComandoDeFeedback,
  ErroApi,
  Fonte,
  getConversa,
  getToken,
  perguntar,
  Questao,
} from "@/lib/api";
import { sair } from "@/lib/cache";
import { usePreferencia } from "@/lib/preferencia";

/**
 * O Tutor — conversa real com o professor e questões pedidas durante ela.
 *
 * O campo de baixo usa o chat livre (`POST /perguntar` — ver
 * distinção citado × consultado, absorvida de `/perguntar`, que era rota
 * paralela órfã do menu e foi removida depois de portar o que tinha de
 * único pra cá). Questões aparecem apenas quando o aluno as pede nesta
 * conversa e usam `<BalaoQuestao>`, com a mesma avaliação, dicas e gravação
 * de tentativa das demais telas. A antiga abertura de demonstração foi
 * removida: misturar conversa, números, questão e flashcard fictícios com a
 * sessão real fazia conteúdo de Penal parecer resposta do tutor antes de o
 * aluno escolher qualquer assunto.
 */
type Mensagem =
  | { autor: "usuario"; texto: string }
  | { autor: "tutor"; texto: string; citadas: string[]; consultadas: string[]; leitura: boolean }
  // O AVISO DO PRÓPRIO APP (029), não fala de ninguém: "feedback salvo". Terceiro
  // valor em vez de um balão de tutor com texto fabricado — a 016 já resolveu
  // isso no BANCO quando `autor` ganhou `evento`, e escrever aqui um balão do
  // tutor que o modelo nunca gerou seria trazer o mesmo defeito pela tela.
  | { autor: "sistema"; texto: string };

/** Faixa de páginas legível: [3, 4, 5, 9] -> "3–5, 9". */
function paginas(ps: number[]): string {
  const ordenadas = [...new Set(ps)].sort((a, b) => a - b);
  const faixas: string[] = [];
  for (let i = 0; i < ordenadas.length; i++) {
    const ini = ordenadas[i];
    while (i + 1 < ordenadas.length && ordenadas[i + 1] === ordenadas[i] + 1) i++;
    faixas.push(ini === ordenadas[i] ? `${ini}` : `${ini}–${ordenadas[i]}`);
  }
  return faixas.join(", ");
}

/**
 * As etiquetas de fonte de uma resposta, citadas e consultadas.
 *
 * MATERIAL DO ALUNO PELO ASSUNTO, e com as páginas: o `titulo` dele é o nome
 * do PDF ("curso-392569-aula-00-prof-juliana-sganzerla-9bbd-completo"), que
 * aparecia repetido quatro vezes embaixo de uma resposta. Os trechos do mesmo
 * material viram UMA etiqueta com a faixa de páginas. Lei continua "título,
 * art. N". Uma função para os dois caminhos — ao vivo e reabrindo a conversa —,
 * porque foi a divergência entre eles que já deixou etiqueta repetida passar.
 */
function etiquetas(fontes: Fonte[]) {
  const grupos = new Map<string, { citada: boolean; paginas: number[] }>();
  for (const f of fontes) {
    const nome = f.artigo ? `${f.titulo}, art. ${f.artigo}` : f.assunto || f.titulo;
    const g = grupos.get(nome) ?? { citada: false, paginas: [] };
    g.citada ||= f.citada === true;
    if (!f.artigo && f.pagina) g.paginas.push(f.pagina);
    grupos.set(nome, g);
  }
  const citadas: string[] = [];
  const consultadas: string[] = [];
  for (const [nome, g] of grupos) {
    const rotulo = g.paginas.length ? `${nome}, p. ${paginas(g.paginas)}` : nome;
    (g.citada ? citadas : consultadas).push(rotulo);
  }
  return { citadas, consultadas, leitura: fontes.some((f) => f.sequencial === true) };
}

export default function PaginaTutor() {
  const router = useRouter();

  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  // O id da conversa em curso. `null` = ainda não existe; a primeira
  // pergunta abre uma no servidor e devolve o id, então não há chamada
  // extra só pra criar (migração 014).
  const [conversaId, setConversaId] = useState<number | null>(null);
  // O OLHO DAS FONTES. Pedido do dono (24/09/2026): a lista do que o tutor leu
  // fica sempre à mostra e disputa a atenção com a resposta. Uma escolha só,
  // para todas as respostas, e lembrada neste navegador.
  const [fontesVisiveis, setFontesVisiveis] = usePreferencia("tutor:fontes-visiveis", true);
  // Questões geradas DENTRO desta conversa, respondidas aqui mesmo. Antes o
  // botão empurrava pra /fila: você pedia questão no meio de um raciocínio
  // e era jogado pra outra tela — o que quebra exatamente o que a conversa
  // acabou de construir. Elas continuam entrando na fila normal (são
  // gravadas no acervo); a diferença é onde você as responde.
  //
  // ANCORADAS NA CONVERSA (24/09/2026): cada questão guarda depois de QUAL fala
  // do aluno ela nasceu (`ancora` = quantas falas dele existiam). Antes elas
  // ficavam sempre no fim da lista, e a fala seguinte do aluno — "continua o
  // conteúdo de Administrativo" — aparecia ACIMA delas, com a resposta nova
  // espremida entre questões de outro assunto.
  const [geradas, setGeradas] = useState<{ q: Questao; ancora: number }[]>([]);
  // Questões de falas anteriores ficam recolhidas; o aluno abre as que quiser.
  const [abertas, setAbertas] = useState<Set<number>>(new Set());
  const falasDoAluno = useRef(0);
  /** O acervo não tinha trecho do assunto da conversa e o gerador caiu pro
   *  recorte da mesa. As questões valem e têm proveniência — só não são do que
   *  vocês estavam tratando, e dizer isso é obrigação: sem o aviso, o tutor
   *  abria com "vamos treinar isso" e vinham questões de outra matéria. */
  const [foraDoAssunto, setForaDoAssunto] = useState(false);
  /** A fala pedia SIMULADO formal (prova cronometrada, correção no fim). O
   *  servidor reconhece e NÃO gera questão — simulado tem tela própria. A tela
   *  mostra o caminho, porque o servidor não deve navegar por conta própria no
   *  meio de um chat.
   *
   *  Isto existia na resposta da API e a tela IGNORAVA: o resultado foi o tutor
   *  dizendo "não tenho uma ferramenta de cronômetro ou interface de simulado
   *  formal" — falso, e o aluno acredita e deixa de usar o que existe. */
  const [pediuSimulado, setPediuSimulado] = useState(false);
  const [pensando, setPensando] = useState(false);
  // O texto da resposta enquanto ela CHEGA (`/perguntar/fluxo`). `null` = nada
  // transmitido ainda; o balão provisório some quando a resposta final entra.
  const [rascunho, setRascunho] = useState<string | null>(null);
  // Qual comando está destacado no menu da barra. Vive aqui e não dentro do
  // menu porque o TECLADO é quem o move, e o teclado está no campo.
  const [comandoAtivo, setComandoAtivo] = useState(0);
  // O COMANDO VIRA FICHA, e sai do texto. Enquanto ele era só as primeiras
  // letras da mensagem não havia como saber, olhando, se o app já entendeu que
  // aquilo é comando — "/feedb" e "/feedback " parecem a mesma coisa. Fora do
  // texto ele é um objeto na tela: dá pra ver, dá pra apagar inteiro, e o campo
  // guarda só o que interessa, que é o relato.
  const [comando, setComando] = useState<string | null>(null);
  // Primeiro Backspace ARMA (a ficha fica em vermelho, como texto selecionado),
  // o segundo apaga. Um toque só apagando seria perder o comando por um
  // Backspace de mais na hora de corrigir uma palavra — e o gesto de dois
  // tempos é o que todo campo de etiqueta faz.
  const [comandoArmado, setComandoArmado] = useState(false);
  /** Controlador do pedido em voo, pra PARAR. `useRef` e não estado: trocar de
   *  controlador não precisa redesenhar nada, e um `useState` aqui faria o
   *  botão remontar no meio do clique. */
  const abortar = useRef<AbortController | null>(null);
  /** A última pergunta ENVIADA, guardada no cliente.
   *
   *  Existe pra que cancelar seja INSTANTÂNEO. A primeira versão do `parar()`
   *  pedia a pergunta de volta ao servidor pra repor no campo — ou seja,
   *  cancelar custava um ida-e-volta de rede, e quem digitou errado esperava
   *  DUAS vezes: a resposta que não queria e o cancelamento dela. O texto já
   *  está aqui; buscá-lo de novo é atravessar a rede pra saber o que a própria
   *  tela acabou de mandar. */
  const ultimaPergunta = useRef<string>("");
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
  // Para cada mensagem, quantas falas do aluno existem até ela: é a âncora das
  // questões geradas naquele turno.
  const ordinalDaFala = useMemo(() => {
    let n = 0;
    return mensagens.map((m) => (m.autor === "usuario" ? ++n : n));
  }, [mensagens]);
  const falasDoAlunoNaTela = ordinalDaFala.length ? ordinalDaFala[ordinalDaFala.length - 1] : 0;
  useEffect(() => {
    falasDoAluno.current = falasDoAlunoNaTela;
  }, [falasDoAlunoNaTela]);

  /** As questões nascidas no turno `ancora`, no ponto da conversa em que
   *  nasceram. Depois que o aluno fala de novo, recolhem numa linha — mas
   *  continuam montadas (só escondidas): desmontar perderia a resposta em
   *  curso e dispararia o registro de abandono do `DialogoQuestao`. */
  function questoesDa(ancora: number) {
    return geradas
      .filter((g) => g.ancora === ancora)
      .map(({ q }) => {
        const recolhida = ancora < falasDoAlunoNaTela && !abertas.has(q.id);
        return (
          <div key={q.id} className="mt-3">
            {recolhida && (
              <button
                type="button"
                onClick={() => setAbertas((a) => new Set(a).add(q.id))}
                className="btn-ghost inline-flex max-w-full items-center gap-1.5 text-[12.5px]"
              >
                <ClipboardList className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">Questão · {q.tema}</span>
                <span className="shrink-0 text-subtle">— abrir</span>
              </button>
            )}
            <div className={recolhida ? "hidden" : ""}>
              <BalaoQuestao
                tipo={q.tipo}
                questao={q}
                conversaId={conversaId ?? undefined}
                onFechado={() => setGeradas((atual) => atual.filter((x) => x.q.id !== q.id))}
              />
            </div>
          </div>
        );
      });
  }
  const ultimaResposta = [...mensagens].reverse().find((m) => m.autor === "tutor");
  const ultimaRespostaTemFonte =
    ultimaResposta?.autor === "tutor" && (ultimaResposta.citadas.length > 0 || ultimaResposta.leitura);

  // Mesma guarda de toda outra tela autenticada (/fila, /stats, /questao/[id]
  // etc.) — o /tutor tinha ficado de fora dela, sozinho, antes desta rota
  // absorver o /perguntar (que tinha a guarda) e ganhar essa consistência.
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
    }
  }, [router]);

  /** PARA a resposta em voo e desfaz o turno no servidor.

   *

   *  Duas metades, e as duas importam. Abortar o fetch libera a pessoa; desfazer

   *  o turno tira do histórico a pergunta que ela não quis — ela é gravada ANTES

   *  de o modelo ser chamado (014), então sem isto sobraria pergunta sem resposta,

   *  e o prompt do turno seguinte a leria como parte da conversa.

   *

   *  O que NÃO se recupera: o pedido ao modelo que já saiu. Ele é feito no início

   *  do turno, então não há promessa de economizar essa chamada — o que se evita é

   *  a geração de questões e o resto do turno.

   */

  function parar() {
    // TUDO O QUE A PESSOA VÊ ACONTECE AQUI, sem await: aborta, tira o balão,
    // repõe o texto do REF e devolve o foco. Zero rede no caminho — cancelar
    // uma coisa que você não quer não pode custar outra espera.
    abortar.current?.abort();
    abortar.current = null;
    setPensando(false);
    setMensagens((ms) => ms.slice(0, -1));
    setGeradas([]);
    setPergunta(ultimaPergunta.current);
    campo.current?.focus();

    // A limpeza do servidor vai SEM ESPERAR. Ela existe porque a pergunta é
    // gravada antes de o modelo ser chamado (014) e sobraria órfã no
    // histórico — mas é serviço de bastidor, e prender a tela nele foi o
    // defeito que esta versão conserta.
    //
    // Falhando (rede caiu no exato instante), a pergunta órfã fica: o custo é
    // o prompt do próximo turno ver uma pergunta sem resposta, o que é ruim e
    // não é grave. Travar o cancelamento pra evitar isso seria trocar um
    // problema raro por um atrito em todo cancelamento.
    if (conversaId !== null) void desfazerTurno(conversaId).catch(() => {});
  }


  /** EDITAR a última pergunta: desfaz o turno e devolve o texto ao campo.

   *

   *  É o gesto do "digitei errado" — sem ele a pessoa reescreve a pergunta inteira

   *  e a versão errada fica no histórico, sendo lida pelo prompt do próximo turno

   *  como se fizesse parte da conversa.

   */

  function editarUltima() {
    if (conversaId === null || pensando) return;
    // O texto vem da TELA, não do servidor: ele está no balão que a pessoa
    // acabou de clicar. Mesmo motivo do `parar()` — pedir de volta o que já
    // está aqui é atravessar a rede por nada.
    const ultima = [...mensagens].reverse().find((m) => m.autor === "usuario");
    if (!ultima) return;
    setMensagens((ms) => {
      // Corta o par pelo FIM. `filter` por texto seria errado: a mesma
      // pergunta pode ter sido feita antes, e sumiriam as duas.
      const corte = [...ms];
      while (corte.length && corte[corte.length - 1].autor !== "usuario") corte.pop();
      corte.pop();
      return corte;
    });
    setGeradas([]);
    setPergunta(ultima.texto);
    campo.current?.focus();
    void desfazerTurno(conversaId).catch(() => {});
  }


  // MENU DA BARRA. Derivado da fala, não guardado: estado que espelha outro
  // estado é a fonte clássica de tela e campo discordando.
  const sugestoes = comandosSugeridos(pergunta);

  function completar(nome: string) {
    setComando(nome);
    setComandoArmado(false);
    // TIRA SÓ O COMANDO, mantém o que já estava escrito depois dele. A versão
    // anterior limpava o campo inteiro, e desde que o menu passou a aparecer
    // com texto adiante isso virou perda de trabalho: escolher "/feedback" em
    // "/feedb ficou raso demais" apagava o "ficou raso demais".
    setPergunta((atual) => atual.replace(/^\s*\/[a-zà-ú]*\s*/i, ""));
    setComandoAtivo(0);
    campo.current?.focus();
  }

  /** O que o aluno digitou VIRA ficha sozinho ao bater o espaço.
   *
   *  Digitar o comando inteiro à mão é tão válido quanto escolher no menu, e
   *  quem digita "/feedback " esperando que o app entenda não deve precisar
   *  descobrir que precisava ter clicado. O espaço é o gatilho porque é onde a
   *  palavra termina — antes dele "/bug" ainda pode virar "/bugado". */
  function aoDigitar(valor: string) {
    setComandoArmado(false);
    // `[\s\S]*` e não `.` com a flag `s`: o alvo de compilação do projeto é
    // anterior ao dotAll, e o relato pode ter quebra de linha.
    const m = comando === null ? /^\s*(\/[a-zà-ú]+)\s([\s\S]*)$/i.exec(valor) : null;
    if (m && COMANDOS.some((c) => c.nome === m[1].toLowerCase())) {
      setComando(m[1].toLowerCase());
      setPergunta(m[2]);
      setComandoAtivo(0);
      return;
    }
    setPergunta(valor);
    setComandoAtivo(0);
  }

  const perguntarAoTutor = useCallback(async (texto: string) => {
    if (!texto) return;
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
    ultimaPergunta.current = texto;
    // `/erro` e `/feedback` NÃO acendem o "pensando": eles nem chegam ao modelo
    // (o servidor grava e responde na hora, ver 029). Balão de carregamento num
    // caminho que não pensa é mentira curta, e é o que faz um comando parecer
    // uma pergunta que deu errado.
    const ehFeedback = ehComandoDeFeedback(texto);
    if (!ehFeedback) setPensando(true);
    // Rola JÁ ao mandar, não só ao receber: o balão do aluno mais o "pensando"
    // já empurram o fim da conversa pra fora da tela, e era aí que começava o
    // "tenho que ficar scrollando pra baixo".
    irAoFim(true);
    const controlador = new AbortController();
    abortar.current = controlador;
    try {
      const r = await perguntar(texto, conversaId ?? undefined, controlador.signal, (pedaco) => {
        // Acompanha o texto só de quem já está no fim: quem subiu para reler um
        // parágrafo não pode ser arrastado para baixo a cada pedaço.
        const el = scroller.current;
        const noFim = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        setRascunho((atual) => (atual ?? "") + pedaco);
        if (noFim) irAoFim();
      });
      setRascunho(null);
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
      // O servidor leu as citações ANTES de limpar os colchetes da prosa e
      // devolve a decisão por fonte. Recalcular por `art. N` na tela marcava
      // CP 312 E CPP 312 como citados quando a resposta usava só um deles.
      const rotulos = etiquetas(r.fontes);
      // FEEDBACK: cartão do sistema, e o turno acaba aqui. Não há fontes pra
      // separar em citadas/consultadas, não há questão pra gerar, e a conversa
      // não guarda o bilhete — por isso o `return` em vez de seguir o fluxo
      // normal com listas vazias.
      if (ehFeedback) {
        setMensagens((m) => [...m, { autor: "sistema", texto: r.resposta }]);
        irAoFim(true);
        return;
      }
      setMensagens((m) => [
        ...m,
        { autor: "tutor", texto: r.resposta, ...rotulos },
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
      setPediuSimulado(Boolean(r.simulado_pedido));
      if (r.questoes?.length) {
        setGeradas((atual) => [
          ...atual,
          ...r.questoes.map((q) => ({
            q: { ...q, caixa: 0, prox_revisao: "" } as Questao,
            ancora: falasDoAluno.current,
          })),
        ]);
      }
    } catch (err) {
      // ABORTO NÃO É ERRO. Quem clicou em parar já sabe o que
      // aconteceu; um balão vermelho dizendo "não deu pra conectar"
      // culparia a rede por uma decisão da pessoa.
      if (err instanceof DOMException && err.name === "AbortError") return;
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
          leitura: false,
        },
      ]);
    } finally {
      abortar.current = null;
      setRascunho(null);
      setPensando(false);
      irAoFim(true);
    }
  }, [router, conversaId, irAoFim]);
  // Reabrir uma conversa gravada (014). Num `useCallback` porque agora tem DOIS
  // gatilhos: o `?c=` de quem chega de outra tela, e o evento de quem clica no
  // recente já estando aqui.
  const abrirConversa = useCallback((id: number) => {
    // Cartões gerados pertencem à conversa em que nasceram. Sem limpar aqui,
    // abrir um recente carregava as mensagens certas com as questões da
    // conversa anterior ainda embaixo — visualmente parecia que o servidor
    // acabara de gerar questões fora do assunto.
    setGeradas([]);
    setForaDoAssunto(false);
    setPediuSimulado(false);
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
              return { autor: "tutor" as const, texto: m.texto, ...etiquetas(m.fontes) };
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
      setGeradas([]);
      setForaDoAssunto(false);
      setPediuSimulado(false);
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
    // A ficha volta pro texto na hora de mandar: o servidor continua recebendo
    // "/feedback isso ficou raso", e a regra de quem intercepta continua num
    // lugar só (`core/melhoria.py`). A ficha é da TELA.
    const texto = [comando, pergunta.trim()].filter(Boolean).join(" ").trim();
    if (!texto || pensando) return;
    setPergunta("");
    setComando(null);
    setComandoArmado(false);
    perguntarAoTutor(texto);
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-5 pb-2 pt-6">
        <div className="mx-auto flex max-w-[720px] flex-col gap-[18px]">
          {mensagens.length === 0 && !pensando && (
            <div className="flex items-start gap-3">
              <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-accent-foreground">
                <MarcaGlifo className="h-4 w-4" />
              </span>
              <div className="balao-tutor">
                <p className="text-[15px] leading-[1.65]">
                  Pergunte sobre uma matéria do seu edital ou diga o que quer treinar.
                </p>
              </div>
            </div>
          )}

          {/* --------------------------------------------- conversa real */}
          {mensagens.map((m, i) =>
            m.autor === "sistema" ? (
              /* CARTÃO DO APP, não balão de ninguém: sem avatar, sem fontes,
                 centrado e discreto. Ele confirma um registro — se parecesse
                 fala do tutor, o aluno leria "Feedback salvo com sucesso!" como
                 se o modelo tivesse dito isso, que é o mesmo engano que a 016
                 evitou no banco. */
              <div key={i} className="flex justify-center py-1">
                <p className="inline-flex items-center gap-2 rounded-full border border-line
                              bg-surface px-3.5 py-1.5 text-[12.5px] text-muted">
                  <Check className="h-3.5 w-3.5 text-accent-text" aria-hidden />
                  {m.texto}
                </p>
              </div>
            ) : m.autor === "usuario" ? (
              <div key={i} className="group/msg flex items-center justify-end gap-1.5">
                {/* O lápis só na ÚLTIMA pergunta, e só com a conversa parada.
                    Editar uma pergunta do meio significaria descartar tudo o
                    que veio depois dela — e a pessoa não pediu isso ao clicar
                    num lápis. */}
                {i === mensagens.length - 1 && !pensando && conversaId !== null && (
                  <button
                    onClick={editarUltima}
                    title="Editar esta pergunta"
                    aria-label="editar a última pergunta"
                    className="flex h-6 w-6 items-center justify-center rounded-[7px] text-label opacity-0 transition-all hover:bg-surface-hover hover:text-accent-text focus-visible:opacity-100 group-hover/msg:opacity-100"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
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
                    {(m.citadas.length > 0 || m.consultadas.length > 0) && !fontesVisiveis && (
                      <button
                        type="button"
                        onClick={() => setFontesVisiveis(true)}
                        className="mt-3 inline-flex items-center gap-1.5 text-[12px] text-subtle hover:text-muted"
                        aria-label="mostrar as fontes das respostas"
                        title="Mostrar as fontes"
                      >
                        <EyeOff className="h-3.5 w-3.5" />
                        fontes ({m.citadas.length + m.consultadas.length})
                      </button>
                    )}
                    {(m.citadas.length > 0 || m.consultadas.length > 0) && fontesVisiveis && (
                      <div className="relative mt-3 space-y-1.5 border-t border-line-soft pt-3 pr-7">
                        <button
                          type="button"
                          onClick={() => setFontesVisiveis(false)}
                          className="absolute right-0 top-2.5 rounded-md p-1 text-subtle hover:bg-surface-hover hover:text-muted"
                          aria-label="ocultar as fontes das respostas"
                          title="Ocultar as fontes"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                        {m.citadas.length > 0 && (
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rotulo">{m.leitura ? "lido do material" : "citado"}</span>
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
                  {/* CONTINUAR A LEITURA é botão, não frase. O prompt mandava o
                      tutor fechar dizendo 'diga "continua"', e em quatro turnos
                      seguidos a frase saiu igual — virou tique. A tela oferece o
                      passo; o texto só diz o que vem a seguir. Só na ÚLTIMA
                      resposta: nas antigas o botão avançaria de onde a leitura
                      já não está. */}
                  {(i === mensagens.length - 1 || mensagens[i + 1].autor === "usuario") &&
                    questoesDa(ordinalDaFala[i])}
                  {m.leitura && i === mensagens.length - 1 && !pensando && (
                    <button
                      type="button"
                      onClick={() => perguntarAoTutor("continua")}
                      className="btn-ghost mt-2 inline-flex items-center gap-1.5 text-[12.5px]"
                    >
                      Continuar a leitura
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            )
          )}

          {rascunho && (
            <div className="flex items-start gap-3">
              <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-accent text-accent-foreground">
                <MarcaGlifo className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="balao-tutor">
                  <TextoDoTutor texto={rascunho} />
                </div>
              </div>
            </div>
          )}

          {pensando && (
            <div className="flex items-center gap-3 pl-[42px]">
              <p className="rotulo animate-[pxPulse_1.4s_ease-in-out_infinite]">
                {rascunho ? "escrevendo" : "consultando o acervo"}
              </p>
              {/* PARAR. O quadradinho é a convenção de todo chat, e a razão é
                  prática: digitou errado, viu na hora, e não quer esperar a
                  resposta inteira pra reescrever. Parar também DESFAZ o turno,
                  senão a pergunta indesejada fica no histórico e o prompt do
                  turno seguinte a lê como parte da conversa. */}
              <button
                onClick={parar}
                title="Parar e editar a pergunta"
                aria-label="parar a resposta"
                className="flex h-6 w-6 items-center justify-center rounded-[6px] border border-line-stronger text-label transition-colors hover:border-danger hover:text-danger"
              >
                <Square className="h-2.5 w-2.5 fill-current" />
              </button>
            </div>
          )}

          {/* As questões criadas nesta conversa, respondidas AQUI. Cada uma
              com `key` própria: sem isso o React reaproveita a instância e a
              segunda questão abre já mostrando o resultado da primeira — o
              mesmo bug que o /desafio teve. */}
          {pediuSimulado && !pensando && (
            <div className="mt-2 pl-[42px]">
              <Link
                href="/simulado"
                className="inline-flex items-center gap-2 rounded-[10px] border border-line-stronger bg-surface-hover px-3 py-2 text-[13.5px] transition-colors hover:border-accent hover:text-accent-text"
              >
                <ClipboardList className="h-4 w-4" />
                Montar simulado com cronômetro
              </Link>
            </div>
          )}
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

          {/* Treinar o que acabou de ser explicado, sem trocar de tela. Só
              `conversaId` vai daqui: o servidor lê a conversa e decide o assunto
              (`core/assunto.py`). Antes, pedir questão no chat recebia "meu
              acervo não traz itens prontos": verdade sobre a tabela `questao`, e
              mentira sobre o que o sistema consegue fazer com a lei que já tem. */}
          {/* "ISTO" PRECISA EXISTIR. O botão aparecia sob qualquer resposta —
              inclusive a que não se apoiou em trecho nenhum, como a aula
              inventada sobre a estrutura da PC-PR (24/09/2026), sem material da
              matéria. Aí o gerador caía no recorte da mesa e as questões vinham
              de outro assunto. Só com fonte citada (ou leitura do material) na
              última resposta há de onde tirar questão com proveniência. */}
          {alunoJaFalou && !pensando && ultimaRespostaTemFonte && (
            <div className="mt-2 pl-[42px]">
              <GerarQuestoes
                quantidade={2}
                rotulo="Quero questões sobre isto"
                conversaId={conversaId ?? undefined}
                onQuestoes={(qs) =>
                  setGeradas((atual) => [
                    ...atual,
                    ...qs.map((q) => ({
                      q: { ...q, caixa: 0, prox_revisao: "" } as Questao,
                      ancora: falasDoAluno.current,
                    })),
                  ])
                }
              />
            </div>
          )}

          <div ref={fim} />
        </div>
      </div>

      {/* ------------------------------------------------- composer */}
      <div className="shrink-0 px-5 pb-5 pt-3">
        {/* Menu dos comandos de barra (029). Fica ACIMA do campo e não abaixo:
            embaixo ele cairia fora da tela em telefone, e o olho já está no fim
            da conversa. `aria-activedescendant` não entra porque isto não é um
            combobox de formulário — é um atalho de digitação, e o campo continua
            sendo um textarea comum pra quem não usa a barra. */}
        {sugestoes.length > 0 && (
          <div className="mx-auto mb-2 w-full max-w-3xl overflow-hidden rounded-[14px]
                          border border-line bg-surface shadow-[var(--shadow-drawer)]">
            <p className="rotulo px-3.5 pt-2.5">comandos</p>
            <ul className="p-1.5">
              {sugestoes.map((c, i) => (
                <li key={c.nome}>
                  <button
                    type="button"
                    onMouseEnter={() => setComandoAtivo(i)}
                    onClick={() => completar(c.nome)}
                    className={`flex w-full items-baseline gap-2.5 rounded-[10px] px-2 py-1.5
                                text-left transition-colors ${
                                  i === Math.min(comandoAtivo, sugestoes.length - 1)
                                    ? "bg-surface-hover"
                                    : ""
                                }`}
                  >
                    <span className="font-mono text-[13px] text-accent-text">{c.nome}</span>
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-muted">
                      {c.descricao}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="border-t border-line-soft px-3.5 py-1.5 text-[11.5px] text-subtle">
              ↑↓ para escolher · Enter ou Tab completa · Esc cancela
            </p>
          </div>
        )}

        <form
          onSubmit={enviar}
          /* SEM `focus-within:border-accent`: o vermelho da marca em volta do
             campo enquanto se digita foi relatado como desagradável, e ele
             também gasta a cor de ÊNFASE no estado mais comum da tela. O anel
             de foco fica discreto (borda mais clara), que é o que qualquer chat
             faz — o vermelho continua reservado pro que é ação. */
          className="mx-auto max-w-[720px] rounded-[18px] border border-line-strong bg-surface-input px-3.5 pb-2.5 pt-3.5 shadow-[var(--shadow-float)] transition-colors focus-within:border-line-stronger"
        >
          {/* A FICHA, NA LINHA DO TEXTO. Ela ocupa o lugar exato onde o comando
              estava enquanto era letra — em cima, virava um segundo bloco e
              empurrava o campo pra baixo. Quadrada e de borda discreta: é um
              rótulo do que já está entendido, não um botão a ser clicado.
              Sem "×": quem quer tirar usa Backspace, que é o gesto de quem já
              está digitando, e a legenda avisa disso quando a ficha está
              armada. */}
          <div className="flex items-start gap-2">
            {comando && (
              <span
                className={`mt-[3px] shrink-0 rounded-[5px] px-1.5 py-0.5 font-mono
                            text-[12.5px] leading-[1.35] transition-colors ${
                              comandoArmado
                                ? "bg-accent text-accent-foreground"
                                : "border border-line-strong bg-surface-hover text-muted"
                            }`}
                title={COMANDOS.find((c) => c.nome === comando)?.descricao}
              >
                {comando}
              </span>
            )}

            <textarea
              ref={campo}
            rows={1}
            value={pergunta}
            onChange={(e) => aoDigitar(e.target.value)}
            onKeyDown={(e) => {
              // BACKSPACE NO COMEÇO DO CAMPO É SOBRE A FICHA, não sobre o
              // texto: não há texto à esquerda pra apagar. Primeiro toque arma,
              // segundo apaga — e qualquer outra tecla desarma, no `aoDigitar`.
              const noComeco = e.currentTarget.selectionStart === 0
                && e.currentTarget.selectionEnd === 0;
              if (e.key === "Backspace" && comando && noComeco) {
                e.preventDefault();
                if (comandoArmado) {
                  setComando(null);
                  setComandoArmado(false);
                } else {
                  setComandoArmado(true);
                }
                return;
              }
              // COM O MENU ABERTO, o campo é navegação. Enter completa em vez
              // de enviar: mandar "/er" pro servidor seria enviar meia palavra
              // pro modelo, que é exatamente o que o menu existe pra evitar.
              if (sugestoes.length > 0) {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  setComandoAtivo((i) =>
                    (i + (e.key === "ArrowDown" ? 1 : sugestoes.length - 1)) % sugestoes.length
                  );
                  return;
                }
                if (e.key === "Enter" || e.key === "Tab") {
                  e.preventDefault();
                  completar(sugestoes[Math.min(comandoAtivo, sugestoes.length - 1)].nome);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  // Esc LIMPA a barra em vez de só fechar o menu: sem isso o
                  // menu reabriria no próximo render, porque ele é derivado da
                  // fala, e a tecla pareceria não ter feito nada.
                  setPergunta("");
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                enviar(e);
              }
            }}
            /* COM FICHA, SEM EXEMPLO. O exemplo dizia "ficou raso demais" e
               ensinava o óbvio: quem digitou /feedback já sabe o que é
               feedback. O rótulo da ficha basta. */
            placeholder={comando ? "" : "Pergunte sobre a lei — ex.: art. 312 do CP"}
              className="max-h-40 min-w-0 flex-1 resize-none overflow-y-auto bg-transparent text-[15px] leading-relaxed text-foreground outline-none placeholder:text-subtle"
            />
          </div>
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
