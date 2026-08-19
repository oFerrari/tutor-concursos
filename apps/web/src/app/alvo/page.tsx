"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Plus, X } from "lucide-react";
import {
  ErroApi,
  Mesa,
  atualizarMesa,
  getDisciplinasDoAcervo,
  getMesaAtual,
  getToken,
} from "@/lib/api";
import { limparCache } from "@/lib/cache";

/**
 * "Ainda não tenho o edital" — declarar as matérias na mão (migração 017).
 *
 * Antes este caminho ia para `/mesas?editar=alvo`, e isso pedia a coisa errada:
 * quem acabou de dizer "não tenho o edital" não quer administrar mesas, quer
 * montar o plano. A tela de mesas abria o editor de UMA mesa entre várias, com
 * criar/renomear/apagar em volta — trabalho de organização, não de conteúdo.
 *
 * Aqui a tela é a MESMA da curadoria de edital (011), com a mesma sequência:
 * uma lista de matérias que se tira e se acrescenta, e um botão que só no fim
 * faz aquilo valer. É o mesmo produto pelos dois caminhos — o PDF só poupa a
 * digitação.
 *
 * O que ela NÃO copia é o contador de tópicos e os cargos: alvo manual não tem
 * nem um nem outro. Mostrar "—" onde o edital mostra número seria prometer um
 * detalhamento que não existe; o edital vence o manual justamente por trazer o
 * tópico (ver `mesa.disciplinas`).
 *
 * A lista de origem é o ACERVO (`GET /disciplinas`), não texto livre, e o
 * motivo está na 017: nome que não casa com o acervo vira filtro que não acha
 * nada, e o sintoma seria fila vazia sem explicação — o aluno acharia que o app
 * quebrou, não que escolheu matéria inexistente.
 */
export default function PaginaAlvo() {
  const router = useRouter();
  const [mesa, setMesa] = useState<Mesa | null>(null);
  const [acervo, setAcervo] = useState<string[]>([]);
  const [escolhidas, setEscolhidas] = useState<string[]>([]);
  const [nova, setNova] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    Promise.all([getMesaAtual(), getDisciplinasDoAcervo()])
      .then(([m, d]) => {
        setMesa(m);
        setAcervo(d.disciplinas);
        // Semeia com o que a mesa já declarou à mão. Se o alvo veio de PDF,
        // NÃO semeia: o edital tem precedência (017), e trazer as matérias
        // dele pra cá convidaria a "editar o edital" por um caminho que não
        // mexe no edital — a correção do PDF se faz na curadoria.
        setEscolhidas(m.origem_alvo === "manual" ? m.disciplinas ?? [] : []);
      })
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 401) router.push("/login");
        else setErro(e instanceof ErroApi ? e.message : "Não deu pra carregar as matérias");
      });
  }, [router]);

  /** O que sobrou do acervo pra oferecer — o que já está na lista sai daqui. */
  const disponiveis = useMemo(
    () => acervo.filter((d) => !escolhidas.includes(d)),
    [acervo, escolhidas]
  );

  const temEdital = mesa?.origem_alvo === "edital";

  async function confirmar() {
    if (!mesa) return;
    setErro(null);
    setSalvando(true);
    try {
      await atualizarMesa(mesa.id, { disciplinas: escolhidas });
      // O recorte mudou, então fila/caderno/desempenho em cache mentem: são
      // exatamente os números que dependem das matérias da mesa.
      limparCache();
      router.push("/");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra salvar suas matérias");
      setSalvando(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 pb-10 pt-6">
      <h1 className="text-[27px] tracking-[-0.3px]">Quais matérias você vai estudar?</h1>
      <p className="mb-6 mt-1.5 text-[14.5px] text-muted">
        Sem edital publicado ainda, você mesmo diz o alvo. É isso que recorta a fila, o desempenho
        e o simulado — dá pra trocar depois, e quando o edital sair ele assume.
      </p>

      {erro && <p className="callout-danger mb-4 !p-3 text-[13px]">{erro}</p>}

      {/* Mesa com edital: avisar ANTES de a pessoa montar uma lista que não vai
          valer. O edital tem precedência (017) — deixar salvar em silêncio faria
          a tela aceitar um trabalho que o servidor ignora. */}
      {temEdital && (
        <p className="callout-warning mb-5 !p-3.5 text-[13px]">
          Esta mesa já tem edital anexado, e o edital manda no recorte. O que você escolher aqui
          fica guardado, mas só passa a valer se o edital for removido — para corrigir uma matéria
          do edital, use a tela do edital.
        </p>
      )}

      {mesa === null && !erro && <p className="text-[13.5px] text-muted">Carregando…</p>}

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

          {/* As do acervo viram CHIP e não campo de texto: clicar é mais rápido
              que digitar e, principalmente, não erra a grafia — e grafia errada
              aqui é filtro que não casa nada. */}
          {disponiveis.length > 0 && (
            <>
              <p className="rotulo mb-2.5 mt-7">o que o acervo tem</p>
              <div className="flex flex-wrap gap-2">
                {disponiveis.map((d) => (
                  <button
                    key={d}
                    onClick={() => setEscolhidas([...escolhidas, d])}
                    className="chip"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    {d}
                  </button>
                ))}
              </div>
            </>
          )}

          {/* Digitar continua permitido — o acervo cresce, e recusar uma matéria
              que o aluno sabe que vai cair seria decidir por ele. O preço está
              dito na linha de baixo, não escondido. */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const nome = nova.trim();
              if (!nome || escolhidas.includes(nome)) return;
              setEscolhidas([...escolhidas, nome]);
              setNova("");
            }}
            className="mt-5 flex gap-2"
          >
            <input
              value={nova}
              onChange={(e) => setNova(e.target.value)}
              placeholder="Outra matéria que vai cair na sua prova"
              className="field flex-1"
            />
            <button type="submit" disabled={!nova.trim()} className="btn-ghost shrink-0">
              <Plus className="h-4 w-4" />
              adicionar
            </button>
          </form>
          <p className="mt-1.5 text-[12px] text-subtle">
            Matéria que o acervo ainda não tem entra no seu plano e aparece no raio-x, mas não gera
            questão até existir material dela.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-line pt-6">
            <button
              onClick={confirmar}
              disabled={salvando || escolhidas.length === 0}
              className="btn-primary"
            >
              <Check className="h-4 w-4" />
              {salvando ? "Salvando…" : "Confirmar minhas matérias"}
            </button>
            <button onClick={() => router.push("/")} className="link">
              deixar pra depois
            </button>
          </div>
          <p className="mt-2 text-[12.5px] text-subtle">
            Só agora isso vira o alvo da mesa e passa a contar na meta e na fila.
          </p>
        </>
      )}
    </div>
  );
}
