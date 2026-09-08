"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Confirmar } from "@/components/Confirmar";
import { Check, ChevronDown, Download, Link2, Pencil, RotateCcw, Trash2, UploadCloud } from "lucide-react";
import {
  ErroApi,
  Material,
  Mesa,
  SugestoesMaterial,
  apagarMaterial,
  abrirMaterial,
  renomearDisciplina,
  baixarMaterial,
  classificarMaterial,
  getMateriais,
  getMesaAtual,
  getSugestoesMaterial,
  getToken,
  indexarLink,
  reindexarMaterial,
  subirMaterial,
} from "@/lib/api";
import { Carregando } from "@/components/Carregando";

/**
 * "Minha biblioteca" — alimentar o RAG com material PRÓPRIO.
 *
 * Tela REAL: `POST/GET/PATCH/DELETE /materiais` + `POST /materiais/link`
 * (migrações 019 e 020). O material é PRIVADO (`documento.usuario_id`), e é
 * isso que sustenta "só você tem acesso": `retrieval.buscar` devolve o público
 * MAIS o do próprio aluno — medido com dois usuários.
 *
 * DISCIPLINA É OPCIONAL, e a mudança veio do primeiro uso real: subir 14 aulas
 * de um curso significava digitar a mesma disciplina 14 vezes, e o caso que
 * mais importa é o material que a pessoa NÃO conhece ("joguei lá, não sei se
 * agrega"). Obrigar a rotular é obrigar a LER antes de subir. Quem descobre é
 * o classificador; o aluno corrige no lápis de cada linha.
 *
 * AGRUPADO POR DISCIPLINA pelo mesmo motivo: 14 linhas de um curso são
 * indistinguíveis numa lista chapada. É o `assunto` (020) que separa a aula 3
 * da aula 11, e é a disciplina que junta as 14 num bloco só.
 *
 * O LOTE fecha o mesmo problema pelo outro lado: os campos são preenchidos UMA
 * vez e valem pros N arquivos escolhidos juntos. Sem isso, "opcional" ainda
 * custava 14 idas ao seletor de arquivo.
 *
 * O POLLING é físico, não gosto: o embedding roda local na CPU, um PDF grande
 * leva minutos, e a rota responde na hora com `processando`. O progresso vive
 * no banco pra sobreviver a um F5.
 */

const SELO: Record<Material["status"], { classe: string; rotulo: string }> = {
  pronto: { classe: "selo-ok", rotulo: "Vetorizado e ativo" },
  processando: { classe: "selo-processando", rotulo: "IA lendo e processando..." },
  falha: { classe: "selo-falha", rotulo: "Falha na leitura" },
};

const TIPOS = [
  { valor: "aula", rotulo: "Aula / apostila" },
  { valor: "resumo", rotulo: "Resumo / anotação" },
  { valor: "jurisprudencia", rotulo: "Jurisprudência" },
];

/** Chave do grupo "ainda sem disciplina". Começa com espaço pra nunca colidir
 *  com nome real de matéria. */
const SEM_DISCIPLINA = " nao-classificado";

function detalhe(m: Material): string {
  if (m.status === "falha") return m.erro ?? "não deu pra ler";
  if (m.status === "processando") return `${m.chunks} de ${m.chunks_total ?? "?"}`;
  return `${m.chunks} trechos`;
}

/**
 * Campo com lista de sugestão que AINDA aceita digitar qualquer coisa.
 *
 * Era `<datalist>`, e a troca tem um motivo só: o popup nativo é desenhado pelo
 * NAVEGADOR, CSS não alcança ele, e o realce do item sob o mouse vem azul do
 * sistema — num site cuja paleta não tem azul. Não existe como pintar aquele
 * realce de rubro mantendo o controle nativo; trazer a lista pra dentro da
 * página é o único caminho.
 *
 * O que a troca NÃO pode custar é o motivo pelo qual `<datalist>` foi escolhido
 * antes: a lista é DICA, não domínio fechado. Por isso `livre` continua sendo um
 * `<input>` de verdade por baixo — quem digita matéria que não está na lista é
 * atendido igual, e o painel simplesmente para de mostrar opção quando nada
 * casa. `livre={false}` é pro campo que TEM domínio fechado (Tipo, que o banco
 * valida em `material.TIPOS`), e aí o gatilho é um botão, não um campo de texto.
 *
 * Teclado é requisito, não enfeite: era de graça no nativo e passa a ser
 * responsabilidade daqui — seta pra abrir e andar, Enter pra escolher, Esc pra
 * fechar, clique fora pra fechar.
 */
function Seletor({
  valor,
  aoMudar,
  opcoes,
  placeholder,
  className = "field",
  caixa = "relative w-full",
  livre = true,
  rotulo,
  aria,
}: {
  valor: string;
  aoMudar: (v: string) => void;
  opcoes: string[];
  placeholder?: string;
  className?: string;
  caixa?: string;
  livre?: boolean;
  /** Traduz valor -> texto exibido. Só o Tipo precisa (grava "aula", mostra
   *  "Aula / apostila"); nos rótulos livres o valor JÁ é o texto. */
  rotulo?: (v: string) => string;
  aria?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const [ativo, setAtivo] = useState(-1);
  const raiz = useRef<HTMLDivElement>(null);
  // `role="combobox"` exige `aria-controls` apontando pro painel, e o painel só
  // existe quando aberto — daí o id ser estável e gerado por instância.
  const idPainel = `${useId()}-painel`;

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (!raiz.current?.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [aberto]);

  /** No modo livre a lista FILTRA pelo que já foi digitado — com 14 matérias na
   *  biblioteca, rolar tudo depois de digitar três letras é pior que o nativo
   *  era. No modo fechado não filtra: ali a lista é o domínio inteiro. */
  const visiveis = useMemo(() => {
    if (!livre || !valor.trim()) return opcoes;
    const q = valor.trim().toLowerCase();
    return opcoes.filter((o) => o.toLowerCase().includes(q));
  }, [livre, valor, opcoes]);

  function escolher(v: string) {
    aoMudar(v);
    setAberto(false);
    setAtivo(-1);
  }

  function teclas(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setAberto(false);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!aberto) {
        setAberto(true);
        return;
      }
      if (!visiveis.length) return;
      const passo = e.key === "ArrowDown" ? 1 : -1;
      setAtivo((i) => (i + passo + visiveis.length) % visiveis.length);
      return;
    }
    // Enter só é sequestrado quando há item destacado: sem isso, Enter dentro
    // do formulário de correção de rótulo deixaria de salvar a linha.
    if (e.key === "Enter" && aberto && visiveis[ativo]) {
      e.preventDefault();
      escolher(visiveis[ativo]);
    }
  }

  return (
    <div ref={raiz} className={caixa}>
      {livre ? (
        <input
          value={valor}
          onChange={(e) => {
            aoMudar(e.target.value);
            setAberto(true);
            setAtivo(-1);
          }}
          onFocus={() => setAberto(true)}
          onKeyDown={teclas}
          placeholder={placeholder}
          className={className}
          autoComplete="off"
          role="combobox"
          aria-expanded={aberto}
          aria-controls={idPainel}
          aria-label={aria}
        />
      ) : (
        <button
          type="button"
          onClick={() => setAberto((a) => !a)}
          onKeyDown={teclas}
          className={`${className} flex items-center justify-between gap-2 text-left`}
          aria-expanded={aberto}
          aria-label={aria}
        >
          <span className="truncate">{rotulo ? rotulo(valor) : valor}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-subtle" />
        </button>
      )}

      {/* No modo livre a seta é um GATILHO à parte: sem ela, um campo de texto
          não anuncia que tem lista — foi exatamente a queixa que matou o chip
          como affordance. `tabIndex={-1}` porque o Tab deve ir pro próximo
          campo, não pra seta do campo atual. */}
      {livre && opcoes.length > 0 && (
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setAberto((a) => !a)}
          aria-label="ver sugestões"
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle transition-colors hover:text-accent-text"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
      )}

      {aberto && visiveis.length > 0 && (
        <div id={idPainel} className="seletor-painel" role="listbox">
          {visiveis.map((o, i) => (
            <button
              key={o}
              type="button"
              role="option"
              aria-selected={o === valor}
              onMouseEnter={() => setAtivo(i)}
              onClick={() => escolher(o)}
              className={`seletor-item ${i === ativo ? "seletor-item-ativo" : ""}`}
            >
              <span className="truncate">{rotulo ? rotulo(o) : o}</span>
              {o === valor && <Check className="h-3.5 w-3.5 shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PaginaMateriais() {
  const router = useRouter();
  const inputArquivo = useRef<HTMLInputElement>(null);
  const inputRetry = useRef<HTMLInputElement>(null);
  const [retryDe, setRetryDe] = useState<Material | null>(null);

  const [materiais, setMateriais] = useState<Material[] | null>(null);
  const [sugestoes, setSugestoes] = useState<SugestoesMaterial | null>(null);
  const [mesa, setMesa] = useState<Mesa | null>(null);
  const [disciplina, setDisciplina] = useState("");
  const [assunto, setAssunto] = useState("");
  const [tipo, setTipo] = useState("aula");
  const [url, setUrl] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  /** Aviso é diferente de ERRO: nada deu errado, mas houve algo que a pessoa
   *  precisa saber (material parado que voltou pra fila). Vermelho pra isso
   *  ensina a ignorar vermelho. */
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  /** Progresso do LOTE. `null` fora de um envio múltiplo. */
  const [lote, setLote] = useState<{ feitos: number; total: number } | null>(null);

  /** De onde vêm as sugestões de disciplina. Ligado quando a mesa declara
   *  matérias — ver `podeDoAlvo`. */
  const [doAlvo, setDoAlvo] = useState(false);


  /** Arraste: qual material está na mão e sobre qual grupo ele está. `sobre`
   *  existe só pra dar o realce do alvo — sem ele o aluno solta no escuro. */
  const [arrastando, setArrastando] = useState<number | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);

  /** Linha em edição de rótulo. Inline porque corrigir o palpite é um ajuste de
   *  duas palavras — abrir modal pra isso é mais clique que conteúdo. */
  const [editando, setEditando] = useState<number | null>(null);
  const [editDisc, setEditDisc] = useState("");
  const [editAssu, setEditAssu] = useState("");

  const carregar = useCallback(async () => {
    try {
      setMateriais((await getMateriais()).materiais);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) router.push("/login");
      else setErro(e instanceof ErroApi ? e.message : "Não deu pra carregar sua biblioteca");
    }
  }, [router]);

  /** As sugestões mudam a cada material classificado, então recarregam junto da
   *  lista — não uma vez só na montagem. */
  const carregarSugestoes = useCallback(async () => {
    try {
      setSugestoes(await getSugestoesMaterial());
    } catch {
      // Sugestão é conveniência: sem ela os campos continuam funcionando como
      // texto livre, que é o comportamento anterior. Não vale um erro na tela.
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar();
    carregarSugestoes();
    // A mesa resolvida vem do SERVIDOR (`GET /mesa`), não recalculada aqui: a
    // regra de fallback tem um dono só, e é ele que já resolveu edital vs alvo
    // manual em `origem_alvo`.
    getMesaAtual()
      .then((m) => {
        setMesa(m);
        // Ligado por padrão quando existe alvo: quem sobe material está
        // estudando PARA aquele concurso, e usar a grafia do edital faz a
        // biblioteca agrupar com o mesmo nome que o plano de estudo usa.
        setDoAlvo((m.disciplinas?.length ?? 0) > 0);
      })
      .catch(() => setMesa(null));
  }, [router, carregar, carregarSugestoes]);

  /**
   * Rolagem automática enquanto arrasta perto da borda.
   *
   * Com biblioteca grande, o grupo de destino simplesmente não está na tela: o
   * arraste nativo não rola nada, então mover um material pra um grupo lá
   * embaixo era impossível sem soltar, rolar e recomeçar.
   *
   * `dragover` no window (o `dragover` de elemento não dispara em toda a área) e
   * `requestAnimationFrame` pro movimento: um `setInterval` daria passo irregular
   * e um `scrollBy` por evento daria velocidade dependente da taxa de eventos do
   * navegador. Velocidade PROPORCIONAL à profundidade na zona — perto da borda
   * corre, na beirada da zona vai devagar; velocidade fixa passa do alvo.
   *
   * O rAF é cancelado quando o arraste acaba (o effect depende de `arrastando`),
   * senão sobraria um loop de animação vivo pelo resto da sessão.
   */
  useEffect(() => {
    if (arrastando === null) return;
    const ZONA = 120; // px de cada borda onde a rolagem começa
    const MAX = 24; // px por frame no encostado na borda
    let velocidade = 0;
    let raf = 0;
    const mirar = (e: DragEvent) => {
      const y = e.clientY;
      const h = window.innerHeight;
      if (y < ZONA) velocidade = -MAX * (1 - y / ZONA);
      else if (y > h - ZONA) velocidade = MAX * (1 - (h - y) / ZONA);
      else velocidade = 0;
    };
    const passo = () => {
      if (velocidade !== 0) window.scrollBy(0, velocidade);
      raf = requestAnimationFrame(passo);
    };
    window.addEventListener("dragover", mirar);
    raf = requestAnimationFrame(passo);
    return () => {
      window.removeEventListener("dragover", mirar);
      cancelAnimationFrame(raf);
    };
  }, [arrastando]);

  /**
   * Soltar FORA de qualquer bloco = tirar a matéria.
   *
   * É o gesto rápido: quem quer desclassificar não deveria ter que acertar uma
   * caixa. `dragover` global com `preventDefault` porque sem isso o navegador
   * recusa o drop fora dos alvos declarados e o gesto morre sem explicação.
   *
   * `defaultPrevented` é o que impede o duplo tratamento: quando um grupo (ou a
   * área de subir arquivo) já cuidou do drop, ele chamou `preventDefault`, e o
   * React despacha no container raiz — que fica DENTRO do body, então este
   * ouvinte de window roda depois e vê a marca. Sem essa checagem, soltar num
   * grupo também contaria como "Outros" e desfaria o que a pessoa acabou de
   * fazer.
   */
  useEffect(() => {
    if (arrastando === null) return;
    const permitir = (e: DragEvent) => e.preventDefault();
    const soltar = (e: DragEvent) => {
      if (e.defaultPrevented) return;
      e.preventDefault();
      mover(arrastando, SEM_DISCIPLINA);
    };
    window.addEventListener("dragover", permitir);
    window.addEventListener("drop", soltar);
    return () => {
      window.removeEventListener("dragover", permitir);
      window.removeEventListener("drop", soltar);
    };
    // `mover` é estável o bastante pro efeito (só depende de setState e das
    // funções de carregar): re-registrar a cada render trocaria o ouvinte no
    // meio do gesto.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arrastando]);

  // Só faz polling ENQUANTO há algo em curso: numa biblioteca parada isso seria
  // consulta a cada 3s pra sempre.
  const emCurso = materiais?.some((m) => m.status === "processando") ?? false;
  useEffect(() => {
    if (!emCurso) return;
    const t = setInterval(() => {
      carregar();
      carregarSugestoes();
    }, 3000);
    return () => clearInterval(t);
  }, [emCurso, carregar, carregarSugestoes]);

  /** Matérias que a MESA declara — do edital (011) ou escolhidas na mão (017).
   *  Os dois casos servem igual como sugestão: são as matérias daquele
   *  concurso. Quem diz de onde vieram é `origem_alvo`, e o rótulo do botão
   *  usa isso pra não chamar de "edital" o que o aluno digitou. */
  const materiasDoAlvo = useMemo(() => mesa?.disciplinas ?? [], [mesa]);
  const podeDoAlvo = materiasDoAlvo.length > 0;
  const usandoAlvo = doAlvo && podeDoAlvo;

  const opcoesDisc = usandoAlvo ? materiasDoAlvo : (sugestoes?.disciplinas ?? []);

  /** Assunto só tem sugestão quando a fonte é a BIBLIOTECA, porque o alvo da
   *  mesa não tem assunto pra oferecer — ele tem disciplina e tópico, e tópico
   *  é outra coisa (o edital da Dataprev tem 1015; uma datalist com isso não é
   *  sugestão, é um documento). Dentro da biblioteca, prefere os assuntos DA
   *  disciplina escolhida: oferecer "Remédios constitucionais" a quem está
   *  subindo Contabilidade é ruído. */
  const opcoesAssunto = useMemo(() => {
    if (usandoAlvo || !sugestoes) return [];
    return sugestoes.assuntos_por_disciplina[disciplina.trim()] ?? sugestoes.assuntos;
  }, [usandoAlvo, sugestoes, disciplina]);

  /** No lápis não há toggle: corrigir um rótulo é uma ação sobre a biblioteca,
   *  e esconder metade das grafias possíveis atrás de um botão de modo faria a
   *  correção depender de um estado que está no outro canto da tela. As duas
   *  fontes entram juntas, sem repetição. */
  const opcoesDiscEdicao = useMemo(
    () => [...new Set([...materiasDoAlvo, ...(sugestoes?.disciplinas ?? [])])].sort(),
    [materiasDoAlvo, sugestoes]
  );
  const opcoesAssuntoEdicao = useMemo(() => {
    if (!sugestoes) return [];
    return sugestoes.assuntos_por_disciplina[editDisc.trim()] ?? sugestoes.assuntos;
  }, [sugestoes, editDisc]);

  /**
   * Envia N arquivos com os MESMOS rótulos, um após o outro.
   *
   * Sequencial de propósito: o servidor indexa em background no próprio
   * processo, então disparar 14 de uma vez não termina mais rápido — só some
   * com o progresso e concorre por CPU com o embedding que já está rodando.
   *
   * Um arquivo ruim NÃO derruba o lote: quem escolheu 14 não deveria reenviar
   * 13 que já entraram por causa do que falhou. Os que falharam são nomeados no
   * fim, porque "3 falharam" sem dizer quais é um erro que não dá pra agir.
   */
  async function enviar(arquivos: File[]) {
    if (!arquivos.length) return;
    setErro(null);
    setAviso(null);
    setEnviando(true);
    setLote(arquivos.length > 1 ? { feitos: 0, total: arquivos.length } : null);
    const falhas: string[] = [];
    // RETOMADOS não são falhas, e contá-los como falha foi o que produziu a
    // mensagem mais confusa que este app já deu: depois de o servidor cair no
    // meio do lote, subir os 18 de novo dizia "18 de 18 não entraram" com
    // dezoito vezes "você já subiu este arquivo" — quando o servidor tinha
    // acabado de RECOLOCAR os dezoito na fila. O que entrou foi reportado
    // como o que não entrou.
    let retomados = 0;
    for (let i = 0; i < arquivos.length; i++) {
      try {
        const r = await subirMaterial(arquivos[i], { disciplina, assunto, tipo });
        if (r.retomado) retomados += 1;
      } catch (e) {
        falhas.push(`${arquivos[i].name}${e instanceof ErroApi ? ` (${e.message})` : ""}`);
      }
      if (arquivos.length > 1) setLote({ feitos: i + 1, total: arquivos.length });
      // Atualiza a lista a cada arquivo: num lote de 14 a pessoa vê as linhas
      // aparecendo, em vez de olhar uma tela parada por meio minuto.
      await carregar();
    }
    setLote(null);
    setEnviando(false);
    if (falhas.length) {
      setErro(
        `${falhas.length} de ${arquivos.length} não entraram: ${falhas.join("; ")}. Os outros estão processando.`
      );
    } else if (retomados) {
      // Aviso, não erro: nada deu errado — material que estava parado voltou
      // pra fila. Dizer QUANTOS evita a dúvida de "então não fez nada?".
      setAviso(
        retomados === arquivos.length
          ? `${retomados} ${retomados === 1 ? "arquivo já estava aqui e estava" : "arquivos já estavam aqui e estavam"} parados — coloquei de volta na fila de indexação.`
          : `${retomados} de ${arquivos.length} já estavam aqui, parados, e voltaram pra fila. O resto entrou agora.`
      );
      setAssunto("");
      await carregarSugestoes();
    } else {
      // Rótulo é do LOTE, não da sessão: limpar evita que o próximo arquivo
      // herde calado a disciplina do curso anterior.
      setAssunto("");
      await carregarSugestoes();
    }
  }

  async function enviarLink() {
    if (!url.trim()) return;
    setErro(null);
    setEnviando(true);
    try {
      await indexarLink({ url: url.trim(), disciplina, assunto, tipo });
      setUrl("");
      await carregar();
      await carregarSugestoes();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra indexar este link");
    } finally {
      setEnviando(false);
    }
  }

  async function retentar(arquivo: File) {
    const alvo = retryDe;
    setRetryDe(null);
    if (!alvo) return;
    setErro(null);
    try {
      await reindexarMaterial(alvo.id, arquivo);
      await carregar();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra tentar de novo");
    }
  }

  async function salvarRotulo(id: number) {
    setErro(null);
    try {
      await classificarMaterial(id, { disciplina: editDisc, assunto: editAssu });
      setEditando(null);
      await carregar();
      await carregarSugestoes();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra salvar o rótulo");
    }
  }

  /**
   * Solta o material no grupo de destino.
   *
   * Reusa `PATCH /materiais/{id}` — arrastar é a MESMA correção de rótulo que o
   * lápis faz, só com outro gesto; rota nova aqui seria um segundo caminho de
   * escrita pra mesma regra, e é assim que as duas divergem.
   *
   * Otimista: a linha pula de grupo antes da resposta, porque um arraste que
   * "não fez nada" por 200ms parece ter falhado e a pessoa arrasta de novo.
   * Erro devolve a lista do servidor, que é a verdade.
   */
  async function mover(id: number, destino: string) {
    const disciplina = destino === SEM_DISCIPLINA ? "" : destino;
    setArrastando(null);
    setSobre(null);
    setMateriais(
      (atual) =>
        atual?.map((m) =>
          m.id === id ? { ...m, disciplina: disciplina || null, classificado_por: "aluno" } : m
        ) ?? null
    );
    setErro(null);
    try {
      await classificarMaterial(id, { disciplina });
      await carregarSugestoes();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra mover este material");
      await carregar();
    }
  }

  const [renomeando, setRenomeando] = useState<string | null>(null);
  const [nomeNovo, setNomeNovo] = useState("");

  async function confirmarRenome(de: string) {
    const para = nomeNovo.trim();
    setRenomeando(null);
    if (!para || para === de) return;
    setErro(null);
    try {
      await renomearDisciplina(de, para);
      // Recarrega tudo: a renomeação mexe em VÁRIAS linhas e reenfileira a
      // indexação de cada uma, então o estado local não dá pra remendar — os
      // materiais voltam a `processando` e a lista tem de refletir isso.
      await carregar();
      await carregarSugestoes();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não consegui renomear");
    }
  }

  async function abrir(m: Material) {
    try {
      await abrirMaterial(m.id);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "não consegui abrir o arquivo");
    }
  }

  async function baixar(m: Material) {
    // Sem estado de "baixando": a resposta é local (o arquivo está no banco) e
    // um spinner que pisca por 200ms cansa mais do que informa. Erro, sim —
    // 404 aqui quer dizer que alguém apagou o material noutra aba, e ficar em
    // silêncio faria o clique parecer quebrado.
    try {
      await baixarMaterial(m.id, m.origem ?? `${m.titulo}.pdf`);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "não consegui baixar o arquivo");
    }
  }

  /** Apagar material passa pelo MESMO diálogo do resto do sistema.
   *
   *  Antes ia direto: um clique na lixeira e o material sumia, sem pergunta. É
   *  a ação mais destrutiva desta tela — leva os trechos, o arquivo original
   *  (024) e o rótulo que o aluno corrigiu — e era a única que não confirmava,
   *  enquanto apagar mesa e apagar conta confirmam. */
  const [aApagar, setAApagar] = useState<Material | null>(null);

  async function remover(m: Material) {
    setErro(null);
    setAApagar(null);
    try {
      await apagarMaterial(m.id);
      setMateriais((atual) => atual?.filter((x) => x.id !== m.id) ?? null);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra remover");
    }
  }

  /** Agrupado por disciplina, com o não-classificado por ÚLTIMO: ele é o que
   *  ainda vai mudar, e no topo faria o bloco pular de lugar a cada polling. */
  const grupos = useMemo(() => {
    const mapa = new Map<string, Material[]>();
    for (const m of materiais ?? []) {
      const k = m.disciplina ?? SEM_DISCIPLINA;
      mapa.set(k, [...(mapa.get(k) ?? []), m]);
    }
    return [...mapa.entries()].sort(([a], [b]) =>
      a === SEM_DISCIPLINA ? 1 : b === SEM_DISCIPLINA ? -1 : a.localeCompare(b)
    );
  }, [materiais]);

  const nomeDoAlvo = mesa?.origem_alvo === "manual" ? "minhas matérias" : "meu edital";

  return (
    <div className="mx-auto w-full max-w-[940px] px-6 pb-10 pt-6">
      <h1 className="text-[27px] tracking-[-0.3px]">Minha biblioteca</h1>
      <p className="mb-5 mt-1.5 text-[14.5px] text-muted">
        Alimente sua IA com seus PDFs, anotações e resumos privados. Só você tem acesso a este
        material.
      </p>

      {/* O INTERRUPTOR mudou de lugar: agora vive no cartão da mesa, em /mesas.
          É lá que a decisão pertence — é a mesa que declara se lê o material das
          outras, ao lado de tudo o mais que a define. Um controle, um lugar.

          Aqui fica só o ESTADO, em texto, com o caminho até ele: recurso que
          existe e não aparece em nenhum lugar da tela onde produz efeito é
          recurso que ninguém encontra. */}
      {mesa && !mesa.biblioteca_compartilhada && (
        <p className="mb-5 rounded-xl border border-success-line bg-success-soft px-3.5 py-2.5 text-[12.5px] text-body">
          <strong className="font-medium text-success">{mesa.nome} está isolada:</strong> o tutor
          desta mesa lê só o material subido nela (e o que não tem mesa). O material das outras
          aparece na lista marcado como inativo.{" "}
          <Link href="/mesas" className="underline underline-offset-2">
            mudar nas mesas
          </Link>
        </p>
      )}

      {erro && <p className="callout-danger mb-4 !p-3 text-[13px]">{erro}</p>}

      {aviso && <p className="callout-warning mb-4 !p-3 text-[13px]">{aviso}</p>}

      {/* Os três campos são OPCIONAIS e a tela diz isso. Preenchê-los é atalho
          pra quem já sabe do que é o material — poupa a chamada ao
          classificador e evita palpite errado. Deixar em branco é o caminho
          normal pra quem está jogando um curso inteiro aqui. E o que for
          preenchido vale pro LOTE inteiro, não por arquivo. */}
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="min-w-[210px] flex-1">
          <span className="mb-1.5 flex items-baseline justify-between gap-2 text-[12.5px] text-muted">
            <span>Disciplina (opcional)</span>
            {/* O botão só existe como escolha quando há de onde escolher:
                sem alvo declarado ele fica desabilitado, dizendo POR QUÊ, em
                vez de ligar e não sugerir nada. */}
            <button
              type="button"
              disabled={!podeDoAlvo}
              onClick={() => setDoAlvo((v) => !v)}
              title={
                podeDoAlvo
                  ? usandoAlvo
                    ? `Sugerindo as ${materiasDoAlvo.length} matérias de ${nomeDoAlvo}. Desligue pra usar as que você já cadastrou aqui.`
                    : `Sugerindo o que você já cadastrou aqui. Ligue pra usar as matérias de ${nomeDoAlvo}.`
                  : "Sua mesa ainda não declarou matérias — anexe o edital ou escolha as matérias na mão pra habilitar."
              }
              className="flex items-center gap-1.5 text-[12px] transition-colors disabled:cursor-not-allowed disabled:opacity-45"
              role="switch"
              aria-checked={usandoAlvo}
            >
              {/* O rótulo TROCA junto com a cor, e é a cor que resolve a
                  ambiguidade de um texto que muda: rubro está usando o edital,
                  verde está usando a biblioteca. Sem a cor, "usar meu edital"
                  poderia ser lido como o estado atual OU como o que o clique
                  vai fazer — foi por isso que o rótulo fixo veio antes. */}
              <span className={`switch ${usandoAlvo ? "switch-edital" : "switch-daqui"}`}>
                <span
                  className={`switch-bolinha ${usandoAlvo ? "left-[17px]" : "left-[2px]"}`}
                />
              </span>
              <span className={usandoAlvo ? "text-accent-text" : "text-success"}>
                {usandoAlvo ? `usar ${nomeDoAlvo}` : "usar sugestões daqui"}
              </span>
            </button>
          </span>
          <Seletor
            valor={disciplina}
            aoMudar={setDisciplina}
            opcoes={opcoesDisc}
            placeholder="deixe vazio e eu descubro"
            aria="disciplina do material"
          />
        </label>
        <label className="min-w-[210px] flex-1">
          <span className="mb-1.5 block text-[12.5px] text-muted">
            Assunto (opcional)
            {usandoAlvo && <span className="text-subtle"> · sem sugestão vindo do edital</span>}
          </span>
          <Seletor
            valor={assunto}
            aoMudar={setAssunto}
            opcoes={opcoesAssunto}
            placeholder="ex.: Remédios constitucionais"
            aria="assunto do material"
          />
        </label>
        {/* `<div>` e não `<label>`: o gatilho agora é um `<button>`, e label
            envolvendo botão promete um clique-pra-focar que não existe. */}
        <div className="min-w-[170px]">
          <span className="mb-1.5 block text-[12.5px] text-muted">Tipo</span>
          <Seletor
            valor={tipo}
            aoMudar={setTipo}
            opcoes={TIPOS.map((x) => x.valor)}
            rotulo={(v) => TIPOS.find((x) => x.valor === v)?.rotulo ?? v}
            livre={false}
            aria="tipo do material"
          />
        </div>
      </div>

      {/* O retry reenvia o arquivo porque o servidor guarda só o NOME em
          `documento.origem`, não os bytes — armazenar PDF exigiria storage que
          o projeto não tem. Pedir de novo é honesto; fingir que dá, não. */}
      <input
        ref={inputRetry}
        type="file"
        accept=".pdf,.txt,.md,.htm,.html"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) retentar(f);
        }}
      />
      <input
        ref={inputArquivo}
        type="file"
        accept=".pdf,.txt,.md,.htm,.html"
        multiple
        className="hidden"
        onChange={(e) => {
          const fs = [...(e.target.files ?? [])];
          // Zerar antes do await: `change` só dispara quando o valor MUDA, e
          // sem isso reenviar o MESMO arquivo depois de um erro não faz nada.
          e.target.value = "";
          enviar(fs);
        }}
      />

      <button
        type="button"
        disabled={enviando}
        onClick={() => inputArquivo.current?.click()}
        onDrop={(e) => {
          e.preventDefault();
          enviar([...(e.dataTransfer.files ?? [])]);
        }}
        onDragOver={(e) => e.preventDefault()}
        className="drop w-full"
      >
        <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent-text">
          <UploadCloud className="h-[21px] w-[21px]" strokeWidth={2.2} />
        </span>
        <span className="mb-1.5 block text-[15.5px] font-medium">
          {lote
            ? `Enviando ${lote.feitos} de ${lote.total}...`
            : enviando
              ? "Enviando..."
              : "Arraste seus PDFs aqui"}
        </span>
        <span className="block text-[13.5px] text-muted">
          Pode soltar vários de uma vez — os campos acima valem pro lote inteiro
        </span>
        <span className="mt-3 block font-mono text-[11.5px] text-label">PDF, TXT, MD ou HTML</span>
      </button>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          enviarLink();
        }}
        className="mt-3 flex items-center gap-2.5 rounded-xl border border-line-strong bg-surface-input px-3 py-2.5"
      >
        <Link2 className="h-4 w-4 shrink-0 text-subtle" strokeWidth={2.2} />
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Ou cole o link de um site ou lei seca aqui"
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-subtle"
        />
        <button
          type="submit"
          disabled={!url.trim() || enviando}
          className="btn-primary shrink-0 text-[12.5px]"
        >
          Indexar
        </button>
      </form>
      {/* O limite é dito ANTES de a pessoa colar e falhar: só endereço público
          é aceito, porque o pedido sai de dentro da rede do servidor. */}
      <p className="mt-1.5 text-[12px] text-subtle">
        Só endereço público (o servidor recusa IP interno). PDF ou página; o texto é extraído.
      </p>

      <div className="mb-2.5 mt-7 flex items-baseline justify-between gap-3">
        <p className="rotulo">processamento</p>
        {/* Arraste é gesto invisível: quem não souber que existe nunca tenta.
            A dica só aparece com mais de um grupo, porque com um só não há
            para onde mover. */}
        {grupos.length > 1 && (
          <p className="text-[12px] text-subtle">
            errou a matéria? arraste para outro grupo — ou solte fora deles pra tirar
          </p>
        )}
      </div>

      {materiais === null && <Carregando linhas={3} titulo rotulo="Carregando sua biblioteca" />}
      {materiais?.length === 0 && (
        <p className="text-[13.5px] text-muted">
          Nada aqui ainda. Suba uma apostila ou cole um link, e o tutor passa a citá-lo nas
          respostas, junto da lei.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {grupos.map(([disc, itens]) => (
          <div
            key={disc}
            onDragOver={(e) => {
              // `preventDefault` é o que AUTORIZA o soltar: sem ele o navegador
              // recusa o drop e o gesto morre sem explicação.
              if (arrastando === null) return;
              e.preventDefault();
              setSobre(disc);
            }}
            onDragLeave={() => setSobre((s) => (s === disc ? null : s))}
            onDrop={(e) => {
              e.preventDefault();
              if (arrastando !== null) mover(arrastando, disc);
            }}
            className={`overflow-hidden rounded-2xl border bg-surface transition-colors ${
              sobre === disc && arrastando !== null ? "border-accent" : "border-line"
            }`}
          >
            <div className="flex items-baseline justify-between gap-3 border-b border-line-soft bg-surface-raised px-5 py-2.5">
              {/* "Identificando" é PROMESSA: só vale enquanto alguma linha do
                  grupo ainda está processando. Terminado o classificador, o que
                  sobrou sem rótulo é "Outros" — dizer que ainda está
                  identificando seria esperar por algo que não vai acontecer. */}
              {/* O NOME DO GRUPO É EDITÁVEL. Pedido: "às vezes o mesmo assunto
                  cai em nomes de matérias diferentes" — Criminalística num
                  edital é Ciências Forenses no outro. Corrigir material por
                  material existia e custava treze cliques pra treze aulas do
                  mesmo curso. O grupo "Outros" não se renomeia: ele não é uma
                  matéria, é a ausência dela (arraste pra dar nome). */}
              {renomeando === disc ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    confirmarRenome(disc);
                  }}
                  className="flex items-center gap-1.5"
                >
                  <input
                    autoFocus
                    value={nomeNovo}
                    onChange={(e) => setNomeNovo(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setRenomeando(null)}
                    maxLength={120}
                    className="field !py-1 w-[220px] text-[12.5px]"
                    aria-label={`novo nome para ${disc}`}
                  />
                  <button type="submit" className="chip !py-1 text-[12px]">
                    Renomear
                  </button>
                  <button
                    type="button"
                    onClick={() => setRenomeando(null)}
                    className="chip !py-1 text-[12px]"
                  >
                    Cancelar
                  </button>
                </form>
              ) : (
                <p className="group/gr flex items-center gap-1.5 text-[13.5px] font-medium">
                  {disc !== SEM_DISCIPLINA ? (
                    <>
                      {disc}
                      <button
                        onClick={() => {
                          setRenomeando(disc);
                          setNomeNovo(disc);
                        }}
                        title="Renomear esta matéria em todos os materiais dela"
                        aria-label={`renomear ${disc}`}
                        className="flex h-5 w-5 items-center justify-center rounded-[6px] text-label opacity-0 transition-all hover:bg-surface-hover hover:text-accent-text focus-visible:opacity-100 group-hover/gr:opacity-100"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                    </>
                  ) : itens.some((m) => m.status === "processando") ? (
                    <span className="text-muted">Identificando a matéria...</span>
                  ) : (
                    <span className="text-muted">Outros</span>
                  )}
                </p>
              )}
              <p className="font-mono text-[11px] text-label">
                {itens.length} {itens.length === 1 ? "material" : "materiais"}
              </p>
            </div>

            {itens.map((m) => (
              <div
                key={m.id}
                // Não arrastável durante a edição inline: arrastar um campo de
                // texto selecionaria a linha em vez de deixar escrever nela.
                draggable={editando !== m.id}
                onDragStart={(e) => {
                  setArrastando(m.id);
                  e.dataTransfer.effectAllowed = "move";
                  // Firefox exige algum payload pra iniciar o arraste; o id vai
                  // como texto, mas quem manda é o estado (o payload não
                  // sobrevive a tudo entre navegadores).
                  e.dataTransfer.setData("text/plain", String(m.id));
                }}
                onDragEnd={() => {
                  setArrastando(null);
                  setSobre(null);
                }}
                className={`grid grid-cols-[minmax(0,1fr)_100px_180px_74px] items-center gap-3 border-b border-line-soft px-5 py-3.5 transition-colors last:border-b-0 hover:bg-surface-raised max-md:grid-cols-[minmax(0,1fr)_64px_100px_66px] ${
                  editando === m.id ? "" : "cursor-grab active:cursor-grabbing"
                } ${arrastando === m.id ? "opacity-40" : ""}`}
              >
                <div className="min-w-0">
                  {editando === m.id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        salvarRotulo(m.id);
                      }}
                      className="flex flex-wrap items-center gap-1.5"
                    >
                      <Seletor
                        valor={editDisc}
                        aoMudar={setEditDisc}
                        opcoes={opcoesDiscEdicao}
                        placeholder="disciplina"
                        className="field !py-1 text-[12.5px]"
                        caixa="relative w-[160px]"
                        aria="corrigir disciplina"
                      />
                      <Seletor
                        valor={editAssu}
                        aoMudar={setEditAssu}
                        opcoes={opcoesAssuntoEdicao}
                        placeholder="assunto"
                        className="field !py-1 text-[12.5px]"
                        caixa="relative w-[160px]"
                        aria="corrigir assunto"
                      />
                      <button type="submit" className="chip-ativo">
                        ok
                      </button>
                      <button type="button" onClick={() => setEditando(null)} className="chip">
                        cancelar
                      </button>
                    </form>
                  ) : (
                    <>
                      {/* O ASSUNTO é o título visível quando existe: dentro de
                          um bloco de disciplina, "Remédios constitucionais"
                          identifica a aula e "curso-392722-aula-03-6ca6" não. */}
                      {/* O TÍTULO ABRE O ARQUIVO. Pedido: "se eu clicar em cima
                          do material eu deveria abrir o pdf num popup, em vez
                          de ser obrigado a baixar". Ler a apostila é o caso
                          comum; guardar cópia é o raro, e continua no ícone de
                          download ao lado. Só é botão onde há arquivo —
                          material anterior à 024 não tem os bytes. */}
                      {m.tem_arquivo ? (
                        <button
                          onClick={() => abrir(m)}
                          title="Abrir o arquivo"
                          className="max-w-full truncate text-left text-[13.5px] underline-offset-2 hover:text-accent-text hover:underline"
                        >
                          {m.assunto ?? m.titulo}
                        </button>
                      ) : (
                        <p className="truncate text-[13.5px]">{m.assunto ?? m.titulo}</p>
                      )}
                      <p className="mt-0.5 truncate font-mono text-[11px] text-label">
                        {m.assunto ? `${m.titulo} · ` : ""}
                        {detalhe(m)}
                        {/* Só o PALPITE pede conferência. O que o aluno digitou
                            não precisa de aviso — ele sabe o que escreveu. */}
                        {m.classificado_por === "modelo" && (
                          <span className="text-warning"> · eu deduzi, confira</span>
                        )}
                      </p>
                      {/* A etiqueta da mesa em LINHA PRÓPRIA, e não pendurada no
                          fim da linha de cima: lá ela ficava dentro de um
                          `truncate` e era engolida pelo nome do arquivo — o
                          "(inativo aqui)", que é a informação que importa,
                          simplesmente não chegava à tela. */}
                      {m.mesa_id !== null && mesa && m.mesa_id !== mesa.id && (
                        <p className="mt-1">
                          <span
                            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] ${
                              mesa.biblioteca_compartilhada
                                ? "border-line-strong text-subtle"
                                : "border-warning-line bg-warning-soft text-warning"
                            }`}
                            title={
                              mesa.biblioteca_compartilhada
                                ? `Subido na mesa ${m.mesa_nome}, e esta mesa usa material de todas.`
                                : `Subido na mesa ${m.mesa_nome}. Como ${mesa.nome} está isolada, o tutor NÃO lê este material aqui.`
                            }
                          >
                            {m.mesa_nome}
                            {!mesa.biblioteca_compartilhada && " · inativo aqui"}
                          </span>
                        </p>
                      )}
                    </>
                  )}
                </div>
                <div className="font-mono text-[12px] text-muted">
                  {m.criado_em.slice(0, 10).split("-").reverse().join("/")}
                </div>
                <div>
                  <span className={SELO[m.status].classe}>
                    <span
                      className={`selo-ponto ${m.status === "processando" ? "animate-[pxPulse_1.2s_ease-in-out_infinite]" : ""}`}
                    />
                    {SELO[m.status].rotulo}
                  </span>
                </div>
                <div className="flex items-center justify-end gap-1">
                  {/* Só onde o arquivo EXISTE (024). Material anterior à migração
                      não tem os bytes, e um botão que sempre falha é pior que
                      botão ausente — foi a mesma escolha do retry, que só
                      aparece em falha/processando. */}
                  {m.tem_arquivo && (
                    <button
                      onClick={() => baixar(m)}
                      title={
                        m.arquivo_bytes
                          ? `Baixar o original (${Math.max(1, Math.round(m.arquivo_bytes / 1024))} KB)`
                          : "Baixar o arquivo original"
                      }
                      className="flex h-6 w-6 items-center justify-center rounded-[7px] text-label transition-colors hover:bg-surface-hover hover:text-accent-text"
                      aria-label={`baixar ${m.titulo}`}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setEditando(m.id);
                      setEditDisc(m.disciplina ?? "");
                      setEditAssu(m.assunto ?? "");
                    }}
                    title="Corrigir disciplina e assunto"
                    className="flex h-6 w-6 items-center justify-center rounded-[7px] text-label transition-colors hover:bg-surface-hover hover:text-accent-text"
                    aria-label={`corrigir rótulo de ${m.titulo}`}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  {(m.status === "falha" || m.status === "processando") && (
                    <button
                      onClick={() => {
                        setRetryDe(m);
                        inputRetry.current?.click();
                      }}
                      title={
                        m.status === "falha"
                          ? "Reenviar o arquivo e tentar indexar de novo"
                          : "Travado em processando? O servidor pode ter reiniciado — reenvie"
                      }
                      className="flex h-6 w-6 items-center justify-center rounded-[7px] text-label transition-colors hover:bg-surface-hover hover:text-accent-text"
                      aria-label={`tentar indexar ${m.titulo} de novo`}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => setAApagar(m)}
                    className="flex h-6 w-6 items-center justify-center rounded-[7px] text-label transition-colors hover:bg-surface-hover hover:text-danger"
                    aria-label={`remover ${m.titulo}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ))}

        {/* Zona de soltar "Outros" que só existe DURANTE o arraste, e só quando
            não há grupo sem matéria pra receber. Sem ela, desfazer a
            classificação era impossível justamente no caso normal — todos os
            materiais com rótulo, nenhum grupo "Outros" na tela, nada pra onde
            arrastar. Aparece no arraste e some depois porque alvo de drop
            parado numa tela sem nada sendo arrastado é ruído. */}
        {arrastando !== null && !grupos.some(([k]) => k === SEM_DISCIPLINA) && (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setSobre(SEM_DISCIPLINA);
            }}
            onDragLeave={() => setSobre((s) => (s === SEM_DISCIPLINA ? null : s))}
            onDrop={(e) => {
              e.preventDefault();
              if (arrastando !== null) mover(arrastando, SEM_DISCIPLINA);
            }}
            className={`rounded-2xl border border-dashed px-5 py-6 text-center transition-colors ${
              sobre === SEM_DISCIPLINA
                ? "border-accent bg-accent-soft text-accent-text"
                : "border-line-stronger text-muted"
            }`}
          >
            <p className="text-[13.5px] font-medium">Outros — tirar a matéria</p>
            <p className="mt-0.5 text-[12px] text-subtle">
              solte aqui pra deixar sem matéria; o assunto continua
            </p>
          </div>
        )}
      </div>

      <Confirmar
        aberto={aApagar !== null}
        destrutivo
        titulo={`Apagar "${aApagar?.titulo ?? ""}"?`}
        descricao={
          <>
            Os {aApagar?.chunks_total ?? 0} trechos saem da busca, e o tutor deixa de
            citar este material nas respostas.
          </>
        }
        detalhe={
          aApagar?.tem_arquivo
            ? "O arquivo original vai junto — se quiser guardá-lo, baixe antes."
            : "Seu progresso não é apagado: caixas, tentativas e caderno de erros continuam."
        }
        rotuloConfirmar="Apagar material"
        onConfirmar={() => aApagar && remover(aApagar)}
        onCancelar={() => setAApagar(null)}
      />
    </div>
  );
}
