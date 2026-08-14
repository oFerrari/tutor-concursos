"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, LogOut, Plus, Trash2 } from "lucide-react";
import { Marca } from "@/components/Marca";
import {
  ErroApi,
  MesaNaLista,
  Usuario,
  apagarMesa,
  criarMesa,
  getMe,
  getMesaAtiva,
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
  if (!iso) return "ainda sem estudo aqui";
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
  onApagar,
}: {
  mesa: MesaNaLista;
  ativa: boolean;
  onEntrar: () => void;
  onApagar: () => void;
}) {
  const cor = mesa.cobertura_pct >= 75 ? "var(--success)" : "var(--accent)";
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
          {/* CONTAGEM, não a lista. Despejar as disciplinas aqui fazia um
              cartão de 13 linhas ao lado de um de 3 — a grade perdia o
              alinhamento e o número, que é o que se compara entre mesas,
              sumia no meio do texto. A lista inteira fica no `title` (hover)
              e na tela do edital, onde ela é o assunto. */}
          <p
            className="mb-2 truncate text-[12px] text-subtle"
            title={mesa.disciplinas?.join(" · ")}
          >
            {mesa.disciplinas
              ? `${mesa.disciplinas.length} disciplinas · ${mesa.topicos} tópicos`
              : "sem edital — mostra o acervo inteiro"}
          </p>
          <div className="mb-1.5 flex items-baseline justify-between gap-2.5">
            {/* QUESTÕES, não tópicos: a barra mede o que o sistema
                realmente acompanha (caixa >= 3 por questão). Escrever
                "x / y tópicos" sugeriria um controle por tópico que não
                existe — a cobertura por tópico é estimada por disciplina
                inteira (aproximação declarada em core/edital.py). */}
            <span className="font-mono text-[11.5px] text-subtle">
              {mesa.dominadas} / {mesa.questoes} questões
            </span>
            <span className="mono-num text-[12.5px]" style={{ color: cor }}>
              {mesa.cobertura_pct}%
            </span>
          </div>
          <div className="barra">
            <div
              className="barra-fill"
              style={{ width: `${mesa.cobertura_pct}%`, background: cor }}
            />
          </div>
          <p className="mt-2.5 text-[12px] text-subtle">{haQuantoTempo(mesa.ultimo_estudo)}</p>
        </div>
      </button>

      {/* Fora do <button> de propósito: botão dentro de botão não é HTML
          válido e o clique de apagar acabaria entrando na mesa. */}
      <button
        onClick={onApagar}
        aria-label={`apagar a mesa ${mesa.nome}`}
        className="absolute right-3 top-3 rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-hover hover:text-danger"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export default function PaginaMesas() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [menuAberto, setMenuAberto] = useState(false);

  const [mesas, setMesas] = useState<MesaNaLista[] | null>(null);
  const [ativa, setAtiva] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [criando, setCriando] = useState(false);
  const [nome, setNome] = useState("");
  const [orgao, setOrgao] = useState("");
  const [banca, setBanca] = useState("");
  const [salvando, setSalvando] = useState(false);

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
      setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
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
    getMe().then(setUsuario).catch(() => {});
  }, [router, carregar]);

  function entrar(id: number) {
    setMesaAtiva(id);
    router.push("/");
  }

  async function aoCriar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || salvando) return;
    setSalvando(true);
    setErro(null);
    try {
      const nova = await criarMesa(nome.trim(), orgao || undefined, banca || undefined);
      setNome("");
      setOrgao("");
      setBanca("");
      setCriando(false);
      // Entra direto na mesa recém-criada: quem acabou de criar quer
      // estudar nela, e o próximo passo (subir o edital) é na tela dela.
      setMesaAtiva(nova.id);
      router.push("/meta");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra criar a mesa");
      setSalvando(false);
    }
  }

  async function aoApagar(mesa: MesaNaLista) {
    const ok = window.confirm(
      `Apagar a mesa "${mesa.nome}"?\n\nO edital dela vai junto. Seu progresso ` +
        `(caixas, tentativas, caderno de erros) NÃO é apagado — ele é seu, não da mesa.`
    );
    if (!ok) return;
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
      setErro(e instanceof ErroApi ? e.message : "não deu pra apagar a mesa");
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

        <div className="relative">
          <button
            onClick={() => setMenuAberto((a) => !a)}
            className="flex items-center gap-2.5 rounded-full border border-line-soft py-1.5 pl-2 pr-3 transition-colors hover:bg-surface-hover"
          >
            <span className="flex h-[26px] w-[26px] items-center justify-center rounded-full border border-line-strong bg-surface-hover text-[12px] font-semibold text-accent-text">
              {inicial}
            </span>
            <span className="max-w-[160px] truncate text-[13px]">{usuario?.email ?? "conta"}</span>
            <ChevronDown className="h-3.5 w-3.5 text-subtle" />
          </button>

          {menuAberto && (
            <>
              <div onClick={() => setMenuAberto(false)} className="fixed inset-0 z-[25]" />
              <div className="absolute right-0 top-[calc(100%+8px)] z-30 w-[232px] rounded-[14px] border border-line-strong bg-surface p-1.5 shadow-[var(--shadow-drawer)]">
                <div className="mb-1.5 border-b border-line-soft px-3 pb-3 pt-2.5">
                  <p className="font-mono text-[11px] text-subtle">{usuario?.email ?? "—"}</p>
                </div>
                <Link
                  href="/materiais"
                  className="block rounded-[9px] px-3 py-2.5 text-[13px] text-body transition-colors hover:bg-surface-hover hover:text-foreground"
                >
                  Meus materiais
                </Link>
                <Link
                  href="/meta"
                  className="block rounded-[9px] px-3 py-2.5 text-[13px] text-body transition-colors hover:bg-surface-hover hover:text-foreground"
                >
                  Meu edital
                </Link>
                <div className="mx-1 my-1.5 h-px bg-line-soft" />
                <button
                  onClick={() => {
                    limparToken();
                    router.push("/login");
                  }}
                  className="flex w-full items-center gap-2.5 rounded-[9px] px-3 py-2.5 text-[13px] text-danger transition-colors hover:bg-surface-hover"
                >
                  <LogOut className="h-[15px] w-[15px]" />
                  Sair da conta
                </button>
              </div>
            </>
          )}
        </div>
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
            onApagar={() => aoApagar(m)}
          />
        ))}

        {criando ? (
          <form
            onSubmit={aoCriar}
            className="flex min-h-[168px] flex-col gap-2.5 rounded-[14px] border border-line-strong bg-surface p-4"
          >
            <input
              autoFocus
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="nome da mesa (ex: PF Agente 2026)"
              className="field"
            />
            <input
              value={orgao}
              onChange={(e) => setOrgao(e.target.value)}
              placeholder="órgão (opcional)"
              className="field"
            />
            <input
              value={banca}
              onChange={(e) => setBanca(e.target.value)}
              placeholder="banca (opcional)"
              className="field"
            />
            <div className="mt-auto flex gap-2">
              <button type="submit" disabled={!nome.trim() || salvando} className="btn-primary">
                {salvando ? "criando…" : "criar mesa"}
              </button>
              <button type="button" onClick={() => setCriando(false)} className="btn-ghost">
                cancelar
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
          <span className="font-semibold text-accent-text">primeira vez · </span>
          você ainda não criou nenhuma mesa. Enquanto não criar, o app usa uma mesa padrão sem
          edital — ou seja, mostra o acervo inteiro.
        </p>
      )}
    </div>
  );
}
