"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, CalendarClock, Check, FolderOpen, Plus, X } from "lucide-react";
import {
  EditalAtual,
  ErroApi,
  Mesa,
  criarEditalManual,
  getDisciplinasDoAcervo,
  getEdital,
  getMesaAtual,
  getToken,
} from "@/lib/api";
import { limparCache } from "@/lib/cache";

/**
 * "Ainda não tenho o edital" — declarar o concurso à mão (017).
 *
 * Duas versões anteriores erraram, e o uso mostrou as duas:
 *
 * 1. A primeira mandava pra `/mesas?editar=alvo`. Quem acabou de dizer "não
 *    tenho o edital" não quer administrar mesas, quer montar o plano.
 * 2. A segunda só gravava `disciplinas_manuais`. Numa mesa com edital ela
 *    deixava escolher, avisava que não ia valer, e a lista não voltava —
 *    porque o edital vence inteiro. Tela que aceita trabalho que o servidor
 *    ignora é pior que tela que recusa.
 *
 * A correção de fundo veio do relato certo: estudo avulso não é uma lista de
 * matérias, é **um concurso com nome e, às vezes, uma data prevista**. Então
 * esta tela cria um EDITAL de verdade (`POST /edital/manual`), sem PDF. A
 * alternativa era guardar a data prevista numa coluna nova da mesa e ensinar
 * `scheduler.meta` a olhar em dois lugares — e aí o recorte viria de uma fonte e
 * o prazo de outra, exatamente o que a 010 evitou ao fazer disciplina e data
 * saírem do MESMO último edital.
 *
 * Consequência boa: o campo de texto livre VOLTA a ser honesto. Ele tinha saído
 * porque `mesa.atualizar` recusa nome fora do acervo; o caminho do edital não
 * recusa — edital real traz matéria que o acervo não tem ("Finanças Públicas") e
 * a tela marca "sem material" na linha. Digitar deixou de prometer o que o
 * backend nega.
 *
 * Tudo é opcional menos o vazio completo: só matérias (avulso sem prazo), só
 * data ("a prova deve ser em novembro"), só nome. Exigir os três transformaria
 * um chute legítimo em bloqueio.
 */
export default function PaginaAlvo() {
  const router = useRouter();
  const [mesa, setMesa] = useState<Mesa | null>(null);
  const [edital, setEdital] = useState<EditalAtual | null>(null);
  const [acervo, setAcervo] = useState<string[] | null>(null);

  const [titulo, setTitulo] = useState("");
  const [data, setData] = useState("");
  const [escolhidas, setEscolhidas] = useState<string[]>([]);
  const [nova, setNova] = useState("");

  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  /** Segundo passo quando já existe edital: substituir é destrutivo e não
   *  acontece no primeiro clique. Sem edital, este passo nem existe — seria
   *  clique inútil. */
  const [confirmando, setConfirmando] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    Promise.all([
      getMesaAtual(),
      getDisciplinasDoAcervo(),
      // 404 aqui é a resposta NORMAL de "esta mesa não tem edital" — não é
      // falha, e derrubar a tela por isso transformaria o caso comum em erro.
      getEdital().catch(() => null),
    ])
      .then(([m, d, e]) => {
        setMesa(m);
        setAcervo(d.disciplinas);
        setEdital(e);
        // Semeia com o que a mesa JÁ tem, venha de onde vier. Recomeçar de uma
        // tela vazia foi o relato: "escolhi, salvei, e não voltou".
        setEscolhidas(m.disciplinas ?? []);
        setTitulo(e?.titulo ?? "");
        setData(e?.data_prova ?? "");
      })
      .catch((err) => {
        if (err instanceof ErroApi && err.status === 401) router.push("/login");
        else setErro(err instanceof ErroApi ? err.message : "Não deu pra carregar as matérias");
      });
  }, [router]);

  const disponiveis = useMemo(
    () => (acervo ?? []).filter((d) => !escolhidas.includes(d)),
    [acervo, escolhidas]
  );

  /** Matéria sem material no acervo entra no plano (o edital manda), mas não
   *  gera questão. Dizer AGORA, na linha dela — descobrir depois com a fila
   *  vazia é o defeito que a 017 documenta. */
  const semMaterial = useMemo(
    () => escolhidas.filter((d) => acervo !== null && !acervo.includes(d)),
    [escolhidas, acervo]
  );

  const hoje = new Date().toISOString().slice(0, 10);
  const dataNoPassado = data !== "" && data < hoje;
  /** O servidor recusa só o vazio completo — o botão espelha essa regra em vez
   *  de inventar uma mais dura. */
  const temAlgo = titulo.trim() !== "" || data !== "" || escolhidas.length > 0;
  const carregando = mesa === null && erro === null;

  function acrescentar() {
    const nome = nova.trim().replace(/\s+/g, " ");
    if (!nome) return;
    // Duplicata ignorando caixa: "direito penal" e "Direito Penal" são a mesma
    // matéria, e duas linhas iguais na lista fariam o recorte parecer errado.
    if (escolhidas.some((d) => d.toLowerCase() === nome.toLowerCase())) {
      setNova("");
      return;
    }
    setEscolhidas([...escolhidas, nome]);
    setNova("");
  }

  async function salvar() {
    setErro(null);
    setSalvando(true);
    try {
      await criarEditalManual({
        titulo: titulo.trim() || undefined,
        data_prova: data || null,
        disciplinas: escolhidas,
      });
      // O recorte e o prazo mudaram: fila, caderno, desempenho e meta em cache
      // passariam a mentir.
      limparCache();
      router.push("/meta");
    } catch (e) {
      setErro(
        e instanceof ErroApi
          ? e.message
          : "Não deu pra salvar. Nada foi alterado — tente de novo."
      );
      setSalvando(false);
      setConfirmando(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 pb-10 pt-6">
      <h1 className="text-[27px] tracking-[-0.3px]">
        {edital ? "Ajustar o edital desta mesa" : "Montar meu edital na mão"}
      </h1>
      <p className="mb-6 mt-1.5 text-[14.5px] text-muted">
        Sem o PDF publicado, você mesmo declara o concurso. Nome e data são opcionais — se você só
        sabe as matérias, ou só a data provável, já dá pra começar. É isso que recorta a fila, o
        desempenho e o simulado, e é daqui que sai o prazo da meta.
      </p>

      {erro && <p className="callout-danger mb-4 !p-3 text-[13px]">{erro}</p>}

      {carregando && (
        <div className="animate-pulse">
          <div className="mb-3 h-11 rounded-xl bg-surface-raised" />
          <div className="mb-3 h-11 w-1/2 rounded-xl bg-surface-raised" />
          <div className="mb-2 h-11 rounded-xl bg-surface-raised" />
          <div className="h-11 w-2/3 rounded-xl bg-surface-raised" />
        </div>
      )}

      {mesa !== null && (
        <>
          {/* ------------------------------------------ nome e data */}
          <div className="mb-6 flex flex-wrap items-end gap-3">
            <label className="min-w-[260px] flex-1">
              <span className="mb-1.5 block text-[12.5px] text-muted">
                Nome do concurso (opcional)
              </span>
              <input
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                maxLength={200}
                placeholder={mesa.nome}
                className="field"
              />
            </label>
            <label className="min-w-[190px]">
              <span className="mb-1.5 block text-[12.5px] text-muted">
                Data prevista da prova (opcional)
              </span>
              <input
                type="date"
                value={data}
                onChange={(e) => setData(e.target.value)}
                className="field"
              />
            </label>
          </div>
          {titulo.trim() === "" && (
            <p className="-mt-4 mb-5 text-[12px] text-subtle">
              Sem nome, uso <strong>{mesa.nome}</strong> — o nome que você deu à mesa.
            </p>
          )}
          {/* Data no passado é ACEITA (quem espera o próximo edital é caso
              corrente), mas dita na hora — não no /meta depois, com "0 dias
              restantes" e a pessoa sem entender. */}
          {dataNoPassado && (
            <p className="callout-warning mb-5 !p-3 text-[12.5px]">
              <CalendarClock className="mr-1.5 inline h-3.5 w-3.5" />
              Essa data já passou. Dá pra salvar assim, mas a meta vai mostrar 0 dias restantes até
              você informar uma data futura.
            </p>
          )}
          {data === "" && (
            <p className="-mt-4 mb-5 text-[12px] text-subtle">
              Sem data, a meta não calcula prazo nem probabilidade — o resto (fila, caderno,
              desempenho) funciona igual.
            </p>
          )}

          {/* ------------------------------------------------ matérias */}
          <p className="rotulo mb-2.5">
            matérias · {escolhidas.length} {escolhidas.length === 1 ? "escolhida" : "escolhidas"}
          </p>

          {escolhidas.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line-stronger px-4 py-6 text-center text-[13.5px] text-muted">
              Nenhuma ainda. Escolha abaixo, ou digite as do seu concurso.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {escolhidas.map((d) => (
                <li
                  key={d}
                  className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-2.5"
                >
                  <span className="min-w-0 flex-1 truncate text-[14px]">{d}</span>
                  {semMaterial.includes(d) && (
                    <span
                      className="shrink-0 rounded-md border border-warning-line bg-warning-soft px-1.5 py-0.5 text-[10.5px] text-warning"
                      title="Entra no seu plano e aparece no raio-x, mas o acervo ainda não tem material dela — então não gera questão. Suba material em Meus materiais."
                    >
                      sem material
                    </span>
                  )}
                  <button
                    onClick={() => setEscolhidas(escolhidas.filter((x) => x !== d))}
                    aria-label={`tirar ${d}`}
                    className="shrink-0 rounded-lg p-1 text-subtle transition-colors hover:bg-surface-hover hover:text-danger"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {semMaterial.length > 0 && (
            <p className="mt-2.5 text-[12.5px] text-warning">
              {semMaterial.length === 1 ? "1 matéria" : `${semMaterial.length} matérias`} sem
              material no acervo {semMaterial.length === 1 ? "entra" : "entram"} no plano, mas não{" "}
              {semMaterial.length === 1 ? "gera" : "geram"} questão.{" "}
              <Link href="/materiais" className="underline underline-offset-2">
                subir material {semMaterial.length === 1 ? "dela" : "delas"}
              </Link>
            </p>
          )}

          <p className="rotulo mb-2.5 mt-7">o que o acervo tem</p>
          {disponiveis.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {disponiveis.map((d) => (
                <button key={d} onClick={() => setEscolhidas([...escolhidas, d])} className="chip">
                  <Plus className="h-3.5 w-3.5" />
                  {d}
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-line-stronger px-4 py-5 text-center">
              <p className="text-[13.5px] text-muted">
                {acervo && acervo.length > 0
                  ? "Você já escolheu tudo que o acervo tem."
                  : "O acervo ainda não tem matéria nenhuma pra oferecer."}
              </p>
              <Link
                href="/materiais"
                className="mt-2.5 inline-flex items-center gap-1.5 text-[13px] text-accent-text underline underline-offset-2"
              >
                <FolderOpen className="h-3.5 w-3.5" />
                subir meu material
              </Link>
            </div>
          )}

          {/* Digitar é legítimo aqui: o caminho do edital não exige que a matéria
              exista no acervo, e edital real traz matéria que o acervo não tem.
              O preço está dito no selo da linha, não escondido. */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              acrescentar();
            }}
            className="mt-5 flex gap-2"
          >
            <input
              value={nova}
              onChange={(e) => setNova(e.target.value)}
              maxLength={120}
              placeholder="Outra matéria que vai cair na sua prova"
              className="field flex-1"
            />
            <button type="submit" disabled={!nova.trim()} className="btn-ghost shrink-0">
              <Plus className="h-4 w-4" />
              adicionar
            </button>
          </form>

          {/* --------------------------------------------- confirmar */}
          <div className="mt-8 border-t border-line pt-6">
            {confirmando && edital ? (
              <div className="callout-warning !p-4">
                <p className="flex items-center gap-2 text-[14px] font-medium">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  Isto substitui o edital atual desta mesa
                </p>
                <ul className="mt-2.5 flex flex-col gap-1 text-[13px]">
                  <li>
                    sai <strong>{edital.titulo}</strong>
                    {edital.data_prova && <> · prova em {edital.data_prova}</>}
                    {edital.cargo && <> · cargo {edital.cargo}</>}
                  </li>
                  <li>
                    entra o que está nesta tela: {escolhidas.length}{" "}
                    {escolhidas.length === 1 ? "matéria" : "matérias"}
                    {data ? <> · prova em {data}</> : <> · sem prazo</>}
                  </li>
                  <li>
                    o PDF não fica guardado no servidor — para voltar ao original, é subir o arquivo
                    de novo
                  </li>
                  <li className="text-muted">
                    o que você já respondeu NÃO se perde: progresso é seu, não do edital
                  </li>
                </ul>
                <div className="mt-3.5 flex flex-wrap items-center gap-3">
                  <button onClick={salvar} disabled={salvando} className="btn-primary">
                    <Check className="h-4 w-4" />
                    {salvando ? "Substituindo…" : "Substituir mesmo assim"}
                  </button>
                  <button onClick={() => setConfirmando(false)} disabled={salvando} className="link">
                    cancelar
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => (edital ? setConfirmando(true) : salvar())}
                    disabled={salvando || !temAlgo}
                    className="btn-primary"
                  >
                    <Check className="h-4 w-4" />
                    {salvando
                      ? "Salvando…"
                      : edital
                        ? "Substituir o edital por este"
                        : "Confirmar meu edital"}
                  </button>
                  <button onClick={() => router.push("/")} className="link">
                    deixar pra depois
                  </button>
                </div>
                <p className="mt-2 text-[12.5px] text-subtle">
                  {!temAlgo
                    ? "Preencha ao menos o nome, a data prevista ou uma matéria."
                    : "Só agora isso vira o edital da mesa e passa a contar na meta e na fila."}
                </p>
                {/* Caminho ALTERNATIVO dito na tela: quem só quer consertar uma
                    matéria do edital que já existe não deveria descobrir sozinho
                    que existe outro lugar pra isso. */}
                {edital && (
                  <p className="mt-2 text-[12.5px] text-subtle">
                    Só quer corrigir uma matéria do edital atual, sem trocá-lo?{" "}
                    <Link href="/meta" className="underline underline-offset-2">
                      editar matérias do edital
                    </Link>
                  </p>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
