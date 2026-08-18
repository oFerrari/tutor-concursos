"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronDown, Pencil, Plus, Trash2 } from "lucide-react";
import { Confirmar } from "@/components/Confirmar";
import { MenuConta } from "@/components/MenuConta";
import { Marca } from "@/components/Marca";
import {
  ErroApi,
  MesaNaLista,
  Usuario,
  apagarMesa,
  atualizarMesa,
  criarMesa,
  getMe,
  getMesaAtiva,
  getDisciplinasDoAcervo,
  getMesas,
  getToken,
  limparMesaAtiva,
  limparToken,
  setMesaAtiva,
} from "@/lib/api";

/**
 * "Mesas de estudo" — o lobby: cada mesa é um concurso-alvo, com o edital
 * dele, e RECORTA o que aparece no resto do app pelas disciplinas desse
 * edital (migração 010).
 *
 * O que a mesa NÃO isola é o que você aprendeu: caixa SM-2, tentativas e
 * caderno de erros são do ALUNO e atravessam as mesas — dominar o art. 312
 * estudando pra uma vale na outra. Por isso a barra do cartão é a cobertura
 * do SEU progresso dentro daquele recorte, não um progresso separado que
 * começaria do zero em cada mesa.
 *
 * Entrar numa mesa = gravar o id em localStorage; `lib/api.ts` passa a
 * mandar `X-Mesa-Id` em toda chamada. Sem mesa escolhida, a API cai na
 * padrão da conta — e é ELA que decide isso, não esta tela.
 */
function haQuantoTempo(iso: string | null): string {
  if (!iso) return "Ainda sem estudo aqui";
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 2) return "Último estudo agora há pouco";
  if (minutos < 60) return `Último estudo há ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `Último estudo há ${horas}h`;
  const dias = Math.floor(horas / 24);
  return `Último estudo há ${dias} ${dias === 1 ? "dia" : "dias"}`;
}

function CartaoMesa({
  mesa,
  ativa,
  onEntrar,
  onEditar,
  onApagar,
}: {
  mesa: MesaNaLista;
  ativa: boolean;
  onEntrar: () => void;
  onEditar: () => void;
  onApagar: () => void;
}) {
  // TÓPICOS é a unidade do edital — é assim que o concurseiro pensa a
  // prova ("faltam X tópicos"), e é a mesma conta que a probabilidade de
  // fechamento usa na tela de meta. Questões viram a unidade quando o alvo
  // foi declarado à mão (não há tópicos, mas há recorte).
  //
  // SEM ALVO NENHUM não há métrica pra mostrar, e isso é o conserto de um
  // defeito relatado em uso: mesa recém-criada aparecia com "4/54 questões
  // · 7%". O número era verdadeiro e estava no lugar errado — é o progresso
  // da PESSOA no acervo inteiro, exibido num cartão que promete o progresso
  // DAQUELA mesa. Gaveta nova que já nasce cheia.
  const semAlvo = mesa.origem_alvo === "nenhum";
  const porTopico = mesa.topicos > 0;
  const pct = porTopico ? mesa.cobertura_topicos_pct : mesa.cobertura_pct;
  const cor = pct >= 75 ? "var(--success)" : "var(--accent)";
  return (
    <div className="relative">
      <button
        onClick={onEntrar}
        className={`card-link flex min-h-[168px] w-full flex-col gap-3.5 !text-left ${
          ativa ? "!border-accent" : ""
        }`}
      >
        <div className="min-w-0">
          <p className="rotulo mb-2 flex items-center gap-1.5">
            {ativa && <Check className="h-3 w-3 shrink-0 text-accent-text" strokeWidth={3} />}
            <span className="truncate">
              {mesa.banca || mesa.orgao || (ativa ? "mesa atual" : "sem banca")}
            </span>
          </p>
          <p className="text-base font-semibold leading-snug">{mesa.nome}</p>
        </div>

        <div className="mt-auto w-full">
          {semAlvo ? (
            <>
              <p className="mb-1.5 text-[13px] text-body">Sem alvo definido ainda.</p>
              {/* Diz o que FAZER, não só o que falta. E as duas saídas: o
                  PDF (caminho normal) e a escolha manual (pra quem estuda
                  pra concurso cujo edital ainda não saiu — metade do tempo
                  de preparação de verdade). */}
              <p className="text-[12px] leading-relaxed text-subtle">
                Anexe o edital para mapear seu progresso — ou escolha as matérias no lápis
                acima, se o edital ainda não saiu.
              </p>
            </>
          ) : (
            <>
              <p
                className="mb-2 truncate text-[12px] text-subtle"
                title={mesa.disciplinas?.join(", ")}
              >
                {mesa.disciplinas?.length} disciplinas ·{" "}
                {mesa.origem_alvo === "manual" ? "escolhidas por você" : "do edital"}
              </p>
              <div className="mb-1.5 flex items-baseline justify-between gap-2.5">
                <span
                  className="font-mono text-[11.5px] text-subtle"
                  title={
                    porTopico
                      ? `estimado a partir de ${mesa.dominadas} de ${mesa.questoes} questões dominadas`
                      : undefined
                  }
                >
                  {porTopico
                    ? `${mesa.topicos_cobertos} / ${mesa.topicos} tópicos`
                    : `${mesa.dominadas} / ${mesa.questoes} questões`}
                </span>
                <span className="mono-num text-[12.5px]" style={{ color: cor }}>
                  {Math.round(pct)}%
                </span>
              </div>
              <div className="barra">
                <div className="barra-fill" style={{ width: `${pct}%`, background: cor }} />
              </div>
            </>
          )}
          <p className="mt-2.5 text-[12px] text-subtle">{haQuantoTempo(mesa.ultimo_estudo)}</p>
        </div>
      </button>

      {/* Fora do <button> de propósito: botão dentro de botão não é HTML
          válido e o clique nestes acabaria entrando na mesa. */}
      <div className="absolute right-2.5 top-3 flex items-center gap-0.5">
        <button
          onClick={onEditar}
          aria-label={`editar a mesa ${mesa.nome}`}
          className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-hover hover:text-foreground"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={onApagar}
          aria-label={`apagar a mesa ${mesa.nome}`}
          className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-hover hover:text-danger"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

function ConteudoMesas() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);

  const [mesas, setMesas] = useState<MesaNaLista[] | null>(null);
  const [ativa, setAtiva] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [criando, setCriando] = useState(false);
  const [nome, setNome] = useState("");
  const [orgao, setOrgao] = useState("");
  const [banca, setBanca] = useState("");
  const [salvando, setSalvando] = useState(false);
  // A mesa esperando confirmação. Guardar o OBJETO (e não um booleano
  // "modal aberto") é o que deixa o diálogo nomear qual mesa vai embora —
  // "Apagar a mesa?" sem o nome é onde se apaga a errada.
  const [paraApagar, setParaApagar] = useState<MesaNaLista | null>(null);
  // Editar reaproveita O MESMO formulário de criar: os campos são os
  // mesmos três (nome, órgão, banca) e manter dois formulários faria o
  // próximo campo novo nascer só num deles. `editando` diz qual mesa está
  // sendo alterada; `null` com `criando` verdadeiro = mesa nova.
  const [editando, setEditando] = useState<MesaNaLista | null>(null);
  /** `?editar=alvo` abre o editor da mesa ATIVA já no alvo. É o atalho do
   *  onboarding pra quem não vai subir edital agora: sem ele, "escolher as
   *  matérias na mão" viraria "vá pra /mesas, ache sua mesa, clique no lápis"
   *  — três passos pra uma decisão que a tela anterior já ofereceu. */
  const abrirAlvo = useSearchParams().get("editar") === "alvo";
  // Alvo declarado à mão, pra quem estuda pra concurso cujo edital ainda
  // não saiu. As opções saem do ACERVO (não de lista fixa): escolher uma
  // matéria que não existe no material daria fila vazia sem explicação.
  const [alvo, setAlvo] = useState<string[]>([]);
  const [doAcervo, setDoAcervo] = useState<string[]>([]);

  const carregar = useCallback(async () => {
    try {
      setMesas(await getMesas());
      setErro(null);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        limparToken();
        router.push("/login");
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
    }
  }, [router]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    // localStorage só existe no cliente — ler aqui, não no corpo do
    // componente, senão o HTML do servidor e o do browser divergem.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAtiva(getMesaAtiva());
    carregar();
    getDisciplinasDoAcervo().then((r) => setDoAcervo(r.disciplinas)).catch(() => {});
    getMe().then(setUsuario).catch(() => {});
  }, [router, carregar]);

  // Abre o editor DEPOIS que as mesas chegaram: `editando` guarda a mesa, não
  // um id, então antes do fetch não há o que abrir. Roda uma vez — daí o
  // `abriu`, senão fechar o editor com o query param ainda na URL o reabriria
  // no próximo render.
  const abriu = useRef(false);
  useEffect(() => {
    if (!abrirAlvo || abriu.current || !mesas) return;
    const alvoMesa = mesas.find((m) => m.id === getMesaAtiva()) ?? mesas[0];
    if (!alvoMesa) return;
    abriu.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEditando(alvoMesa);
    setNome(alvoMesa.nome);
    setOrgao(alvoMesa.orgao ?? "");
    setBanca(alvoMesa.banca ?? "");
    setAlvo(alvoMesa.disciplinas_manuais ?? []);
  }, [abrirAlvo, mesas]);

  function entrar(id: number) {
    setMesaAtiva(id);
    router.push("/");
  }

  function limparFormulario() {
    setNome("");
    setOrgao("");
    setBanca("");
    setAlvo([]);
    setCriando(false);
    setEditando(null);
  }

  async function aoSalvar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || salvando) return;
    setSalvando(true);
    setErro(null);

    // EDIÇÃO não redireciona: quem renomeia a mesa quer continuar no lobby
    // vendo o cartão com o nome novo. Só a CRIAÇÃO leva embora, porque a
    // mesa nova ainda não tem edital e o próximo passo é subir o PDF.
    if (editando) {
      try {
        await atualizarMesa(editando.id, {
          nome: nome.trim(),
          orgao: orgao.trim() || null,
          banca: banca.trim() || null,
          // Só manda o alvo manual quando NÃO há edital: com edital ele é
          // ignorado no backend de qualquer jeito (o PDF tem precedência),
          // e mandar assim mesmo daria a impressão de que a escolha valeu.
          ...(editando.origem_alvo === "edital" ? {} : { disciplinas: alvo }),
        });
        limparFormulario();
        await carregar();
      } catch (e) {
        setErro(e instanceof ErroApi ? e.message : "Não deu pra salvar a mesa");
      } finally {
        setSalvando(false);
      }
      return;
    }

    try {
      const nova = await criarMesa(nome.trim(), orgao || undefined, banca || undefined);
      limparFormulario();
      // Entra direto na mesa recém-criada E vai pro upload do edital.
      //
      // Mesa nova NUNCA tem edital — é o que a criação produz. Mandar pra
      // /meta fazia a tela abrir dizendo "esta mesa ainda não tem edital"
      // com um botão que leva exatamente pra /onboarding: um clique a mais
      // pra nenhuma informação nova. /meta é tela de LEITURA (quanto falta,
      // quanto está coberto) e não tem o que ler numa mesa recém-criada.
      //
      // Entrar numa mesa que JÁ existe continua indo pro panorama (ver
      // `entrar`) — lá há o que mostrar.
      setMesaAtiva(nova.id);
      router.push("/onboarding");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra criar a mesa");
      setSalvando(false);
    }
  }

  async function aoApagar() {
    const mesa = paraApagar;
    if (!mesa) return;
    setParaApagar(null);
    try {
      await apagarMesa(mesa.id);
      if (getMesaAtiva() === mesa.id) {
        // Sem isso, toda chamada seguinte mandaria o header de uma mesa
        // que não existe mais e voltaria 404.
        limparMesaAtiva();
        setAtiva(null);
      }
      await carregar();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra apagar a mesa");
    }
  }

  const inicial = (usuario?.email?.[0] ?? "?").toUpperCase();

  return (
    <div className="mx-auto w-full max-w-[940px] px-6 pb-12 pt-10">
      {/* ------------------------------------------------------ topo */}
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2.5">
          <Marca />
        </Link>

        <MenuConta usuario={usuario}>
          <span className="flex items-center gap-2.5 rounded-full border border-line-soft py-1.5 pl-2 pr-3 transition-colors hover:bg-surface-hover">
            <span className="flex h-[26px] w-[26px] items-center justify-center rounded-full border border-line-strong bg-surface-hover text-[12px] font-semibold text-accent-text">
              {inicial}
            </span>
            <span className="max-w-[160px] truncate text-[13px]">{usuario?.email ?? "conta"}</span>
            <ChevronDown className="h-3.5 w-3.5 text-subtle" />
          </span>
        </MenuConta>
      </div>

      <h1 className="text-[30px]">
        Bem-vindo de volta. Qual é a <span className="text-accent-text">missão de hoje</span>?
      </h1>
      <p className="mb-7 mt-2 text-[15px] text-muted">
        Cada mesa guarda o edital do seu concurso e recorta a fila, o painel e os simulados pelas
        disciplinas dele. O que você já aprendeu vale em todas elas.
      </p>

      {erro && <p className="callout-danger mb-5">{erro}</p>}

      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3">
        {mesas?.map((m) => (
          <CartaoMesa
            key={m.id}
            mesa={m}
            ativa={ativa === m.id}
            onEntrar={() => entrar(m.id)}
            onEditar={() => {
              setEditando(m);
              setNome(m.nome);
              setOrgao(m.orgao ?? "");
              setBanca(m.banca ?? "");
              setAlvo(m.disciplinas_manuais ?? []);
              setCriando(true);
            }}
            onApagar={() => setParaApagar(m)}
          />
        ))}

        {criando ? (
          <form
            onSubmit={aoSalvar}
            className="flex min-h-[168px] flex-col gap-2.5 rounded-[14px] border border-line-strong bg-surface p-4"
          >
            {/* `editando.nome` é o nome ORIGINAL (o estado guarda a mesa de
                quando o lápis foi clicado), então ele não muda enquanto se
                digita — é o que permite renomear sem perder a referência do
                que está sendo renomeado. */}
            {editando && <p className="rotulo mb-0.5">editando · {editando.nome}</p>}
            <input
              autoFocus
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Nome da mesa (ex.: PF Agente 2026)"
              className="field"
            />
            <input
              value={orgao}
              onChange={(e) => setOrgao(e.target.value)}
              placeholder="Órgão (opcional)"
              className="field"
            />
            <input
              value={banca}
              onChange={(e) => setBanca(e.target.value)}
              placeholder="Banca (opcional)"
              className="field"
            />

            {/* Só na EDIÇÃO e só sem edital. Na criação a mesa ainda vai
                direto pro upload do PDF, que é o caminho normal; oferecer
                as duas coisas ali faria a pessoa escolher antes de saber
                que o PDF resolve sozinho. */}
            {editando && editando.origem_alvo !== "edital" && (
              <div>
                <p className="rotulo mb-1.5">matérias desta mesa</p>
                {doAcervo.length === 0 ? (
                  <p className="text-[12px] text-subtle">
                    O acervo ainda não tem material nenhum ingerido.
                  </p>
                ) : (
                  <>
                    <div className="flex flex-wrap gap-1.5">
                      {doAcervo.map((d) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() =>
                            setAlvo((atual) =>
                              atual.includes(d)
                                ? atual.filter((x) => x !== d)
                                : [...atual, d]
                            )
                          }
                          className={alvo.includes(d) ? "chip-ativo" : "chip"}
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                    <p className="mt-1.5 text-[12px] text-subtle">
                      {alvo.length === 0
                        ? "Nenhuma escolhida — a mesa mostra o acervo inteiro."
                        : "O edital, quando você subir, substitui esta escolha."}
                    </p>
                  </>
                )}
              </div>
            )}
            <div className="mt-auto flex gap-2">
              <button type="submit" disabled={!nome.trim() || salvando} className="btn-primary">
                {salvando
                  ? "Salvando…"
                  : editando
                    ? "Salvar alterações"
                    : "Criar mesa"}
              </button>
              <button type="button" onClick={limparFormulario} className="btn-ghost">
                Cancelar
              </button>
            </div>
          </form>
        ) : (
          <button
            onClick={() => setCriando(true)}
            className="drop flex min-h-[168px] flex-col items-start justify-center gap-3 !text-left"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-accent-soft text-accent-text">
              <Plus className="h-[18px] w-[18px]" strokeWidth={2.4} />
            </span>
            <span>
              <span className="mb-1.5 block text-[15.5px] font-semibold">Criar nova mesa</span>
              <span className="block text-[13px] leading-relaxed text-muted">
                Dê um nome ao concurso. Em seguida você sobe o PDF do edital, e é ele que define
                quais disciplinas essa mesa mostra.
              </span>
            </span>
          </button>
        )}
      </div>

      {mesas !== null && mesas.length === 0 && !criando && (
        <p className="mt-5 callout-info">
          <span className="font-semibold text-accent-text">Primeira vez · </span>
          você ainda não criou nenhuma mesa. Enquanto não criar, o app usa uma mesa padrão sem
          edital — ou seja, mostra o acervo inteiro.
        </p>
      )}

      <Confirmar
        aberto={paraApagar !== null}
        destrutivo
        titulo={`Apagar a mesa "${paraApagar?.nome ?? ""}"?`}
        descricao={
          <>
            O edital dela vai junto, e com ele o recorte por disciplina que esta mesa aplica.
            {paraApagar?.topicos ? ` São ${paraApagar.topicos} tópicos.` : ""}
          </>
        }
        detalhe={
          <>
            Seu progresso <strong className="font-semibold">não</strong> é apagado — caixas,
            tentativas e caderno de erros são seus, não da mesa, e continuam valendo nas outras.
          </>
        }
        rotuloConfirmar="Apagar mesa"
        onConfirmar={aoApagar}
        onCancelar={() => setParaApagar(null)}
      />
    </div>
  );
}

/**
 * `useSearchParams()` obriga a ter fronteira de Suspense: sem ela o build de
 * produção falha ao pré-renderizar esta rota (`?editar=alvo`, que vem do
 * onboarding e do /meta, só existe no cliente). `fallback={null}` porque a
 * própria página já tem estado de carregando — dois avisos de espera
 * empilhados seriam pisca-pisca, não informação.
 */
export default function PaginaMesas() {
  return (
    <Suspense fallback={null}>
      <ConteudoMesas />
    </Suspense>
  );
}
