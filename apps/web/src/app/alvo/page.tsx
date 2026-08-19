"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, Check, FolderOpen, Plus, X } from "lucide-react";
import {
  EditalAtual,
  ErroApi,
  Mesa,
  atualizarMesa,
  getDisciplinasDoAcervo,
  getEdital,
  getMesaAtual,
  getToken,
  removerEdital,
} from "@/lib/api";
import { limparCache } from "@/lib/cache";

/**
 * "Ainda não tenho o edital" — declarar as matérias na mão (migração 017).
 *
 * Antes este caminho ia para `/mesas?editar=alvo`, e isso pedia a coisa errada:
 * quem acabou de dizer "não tenho o edital" não quer administrar mesas, quer
 * montar o plano. A tela de mesas abre o editor de UMA mesa entre várias, com
 * criar/renomear/apagar em volta — trabalho de organização, não de conteúdo.
 *
 * A PRIMEIRA versão desta tela era incoerente e o próprio uso mostrou: numa mesa
 * com edital ela deixava escolher, avisava num quadro amarelo que a escolha não
 * ia valer, e a lista não voltava depois — porque o edital vence inteiro (017) e
 * o manual ficava guardado sem efeito. Tela que aceita trabalho que o servidor
 * ignora é pior que tela que recusa; o aviso só documentava a incoerência.
 *
 * Agora há UM caminho por intenção, e cada um mexe no que promete:
 *
 *   · corrigir uma matéria DO edital  ->  /meta -> "editar matérias"
 *   · abandonar o edital e estudar avulso -> aqui, e o edital SAI
 *
 * A substituição é explícita e diz o que se perde (data da prova, tópicos,
 * cargo), porque o servidor não guarda os bytes do PDF — só o extraído. Voltar
 * exige subir o arquivo de novo, e isso tem que estar dito ANTES do clique.
 *
 * A origem das matérias é o ACERVO, sem campo de texto livre, e não é economia
 * de tela: `mesa.atualizar` RECUSA nome que não existe no acervo (017 — nome que
 * não casa nada vira fila vazia sem explicação). Um campo livre aqui prometeria
 * o que o backend nega. Quem não acha a matéria tem caminho de verdade: subir
 * material dela em /materiais faz o nome aparecer nesta lista.
 */
export default function PaginaAlvo() {
  const router = useRouter();
  const [mesa, setMesa] = useState<Mesa | null>(null);
  const [edital, setEdital] = useState<EditalAtual | null>(null);
  const [acervo, setAcervo] = useState<string[] | null>(null);
  const [escolhidas, setEscolhidas] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  /** Segundo passo do "substituir o edital". Só existe quando há edital: sem
   *  ele não há o que confirmar, e um modal a mais seria clique inútil. */
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
      // falha, e derrubar a tela por isso seria transformar o caso comum em
      // erro. Qualquer outro status também cai em null: a tela funciona sem
      // saber do edital, só perde o aviso de substituição.
      getEdital().catch(() => null),
    ])
      .then(([m, d, e]) => {
        setMesa(m);
        setAcervo(d.disciplinas);
        setEdital(e);
        // Semeia com o que a mesa JÁ recorta, seja de onde vier: com edital,
        // as matérias dele; sem edital, as manuais. A pessoa vê o que tem e
        // edita, em vez de recomeçar de uma lista vazia e não entender por que
        // a escolha anterior "não voltou".
        setEscolhidas(m.disciplinas ?? []);
      })
      .catch((err) => {
        if (err instanceof ErroApi && err.status === 401) router.push("/login");
        else setErro(err instanceof ErroApi ? err.message : "Não deu pra carregar as matérias");
      });
  }, [router]);

  /** O que sobrou do acervo pra oferecer — o que já está na lista sai daqui. */
  const disponiveis = useMemo(
    () => (acervo ?? []).filter((d) => !escolhidas.includes(d)),
    [acervo, escolhidas]
  );

  /** Só o que o acervo tem pode ser salvo (o backend recusa o resto). Matéria
   *  semeada de um edital que o acervo não cobre entra aqui — e é justamente o
   *  caso comum: o edital traz "Finanças Públicas", o acervo não tem. */
  const semMaterial = useMemo(
    () => escolhidas.filter((d) => acervo !== null && !acervo.includes(d)),
    [escolhidas, acervo]
  );
  const salvaveis = useMemo(
    () => escolhidas.filter((d) => acervo === null || acervo.includes(d)),
    [escolhidas, acervo]
  );

  const carregando = mesa === null && erro === null;

  async function salvar() {
    if (!mesa) return;
    setErro(null);
    setSalvando(true);
    try {
      // ORDEM DELIBERADA: grava o alvo ANTES de tirar o edital. Se o segundo
      // passo falhar, a mesa continua com o edital mandando — nada visível
      // mudou e dá pra tentar de novo. Na ordem inversa, uma falha deixaria a
      // mesa SEM edital e SEM alvo, ou seja, pior do que começou.
      await atualizarMesa(mesa.id, { disciplinas: salvaveis });
      if (edital) await removerEdital();
      // O recorte mudou, então fila/caderno/desempenho em cache mentem: são
      // exatamente os números que dependem das matérias da mesa.
      limparCache();
      router.push("/");
    } catch (e) {
      setErro(
        e instanceof ErroApi
          ? e.message
          : "Não deu pra salvar suas matérias. Nada foi alterado — tente de novo."
      );
      setSalvando(false);
      setConfirmando(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 pb-10 pt-6">
      <h1 className="text-[27px] tracking-[-0.3px]">Quais matérias você vai estudar?</h1>
      <p className="mb-6 mt-1.5 text-[14.5px] text-muted">
        Isso é o que recorta a fila, o desempenho e o simulado. Dá pra trocar depois — e se o edital
        sair, ele assume.
      </p>

      {erro && <p className="callout-danger mb-4 !p-3 text-[13px]">{erro}</p>}

      {/* ------------------------------------------------------- carregando */}
      {carregando && (
        <div className="animate-pulse">
          <div className="mb-3 h-3 w-40 rounded bg-surface-raised" />
          <div className="mb-2 h-11 rounded-xl bg-surface-raised" />
          <div className="mb-2 h-11 rounded-xl bg-surface-raised" />
          <div className="h-11 w-2/3 rounded-xl bg-surface-raised" />
        </div>
      )}

      {mesa !== null && (
        <>
          <p className="rotulo mb-2.5">
            minhas matérias · {escolhidas.length}{" "}
            {escolhidas.length === 1 ? "escolhida" : "escolhidas"}
          </p>

          {escolhidas.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line-stronger px-4 py-6 text-center text-[13.5px] text-muted">
              Nenhuma ainda. Escolha abaixo as matérias do seu concurso.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {escolhidas.map((d) => (
                <li
                  key={d}
                  className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-2.5"
                >
                  <span className="min-w-0 flex-1 truncate text-[14px]">{d}</span>
                  {/* Dizer AGORA que esta não vai gerar questão, na linha dela.
                      Descobrir depois, com a fila vazia, é o defeito que a 017
                      documenta. */}
                  {semMaterial.includes(d) && (
                    <span
                      className="shrink-0 rounded-md border border-warning-line bg-warning-soft px-1.5 py-0.5 text-[10.5px] text-warning"
                      title="O acervo ainda não tem material desta matéria, então ela não entra no seu alvo. Suba material dela em Meus materiais."
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
              material no acervo {semMaterial.length === 1 ? "fica" : "ficam"} de fora do alvo.{" "}
              <Link href="/materiais" className="underline underline-offset-2">
                subir material delas
              </Link>
            </p>
          )}

          {/* As do acervo viram CHIP e não campo de texto: clicar é mais rápido
              que digitar e, principalmente, não erra a grafia — e grafia errada
              aqui é recusada pelo servidor (017). */}
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
            /* Empty state com saída, não beco: acervo vazio (ou tudo já
               escolhido) tem exatamente um próximo passo, e ele é um link. */
            <div className="rounded-xl border border-dashed border-line-stronger px-4 py-5 text-center">
              <p className="text-[13.5px] text-muted">
                {acervo && acervo.length > 0
                  ? "Você já escolheu tudo que o acervo tem."
                  : "O acervo ainda não tem matéria nenhuma pra escolher."}
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

          {/* ------------------------------------------------ confirmar */}
          <div className="mt-8 border-t border-line pt-6">
            {/* Substituir o edital é destrutivo e irreversível pelo servidor, e
                por isso não acontece no primeiro clique. O painel diz o que sai
                e o que fica, com números reais — "tem certeza?" sem conteúdo é
                só um clique a mais. */}
            {confirmando && edital ? (
              <div className="callout-warning !p-4">
                <p className="flex items-center gap-2 text-[14px] font-medium">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  Isto remove o edital desta mesa
                </p>
                <ul className="mt-2.5 flex flex-col gap-1 text-[13px]">
                  <li>
                    sai <strong>{edital.titulo}</strong>
                    {edital.data_prova && <> · prova em {edital.data_prova}</>}
                    {edital.cargo && <> · cargo {edital.cargo}</>}
                  </li>
                  <li>
                    a meta perde o prazo até você informar uma data ou anexar outro edital
                  </li>
                  <li>
                    o PDF não fica guardado no servidor — para voltar, é subir o arquivo de novo
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
                  <button
                    onClick={() => setConfirmando(false)}
                    disabled={salvando}
                    className="link"
                  >
                    cancelar
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => (edital ? setConfirmando(true) : salvar())}
                    disabled={salvando || salvaveis.length === 0}
                    className="btn-primary"
                  >
                    <Check className="h-4 w-4" />
                    {salvando
                      ? "Salvando…"
                      : edital
                        ? "Substituir o edital por estudo avulso"
                        : "Confirmar minhas matérias"}
                  </button>
                  <button onClick={() => router.push("/")} className="link">
                    deixar pra depois
                  </button>
                </div>
                <p className="mt-2 text-[12.5px] text-subtle">
                  {salvaveis.length === 0
                    ? "Escolha ao menos uma matéria que o acervo tenha."
                    : edital
                      ? "Esta mesa tem edital, e o edital manda no recorte — sua lista só passa a valer se ele sair."
                      : "Só agora isso vira o alvo da mesa e passa a contar na meta e na fila."}
                </p>
                {/* Caminho ALTERNATIVO dito na tela: quem só quer consertar uma
                    matéria do edital não deveria descobrir sozinho que existe
                    outro lugar pra isso. */}
                {edital && (
                  <p className="mt-2 text-[12.5px] text-subtle">
                    Só quer corrigir uma matéria do edital, sem removê-lo?{" "}
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
