"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Check, Plus, X } from "lucide-react";
import { Voltar } from "@/components/Voltar";
import {
  DisciplinaEdital,
  ErroApi,
  Rascunho,
  confirmarRascunho,
  getRascunho,
  getToken,
} from "@/lib/api";

/**
 * Curadoria do edital — a tela entre "a IA leu o PDF" e "o sistema passou
 * a me cobrar isso todo dia".
 *
 * Por que ela existe: um edital tem vários cargos, e cada cargo tem
 * conteúdo próprio. O edital da Dataprev tem TREZE perfis; ingerir tudo
 * junto punha Advocacia, Contabilidade e Engenharia dentro do plano de
 * quem vai prestar Desenvolvimento de Software — 1015 tópicos em 52
 * disciplinas. Somar cargo é pior que não ler: vira revisão espaçada de
 * matéria que nunca vai cair na prova da pessoa.
 *
 * A tela também assume que o extrator erra. Por isso tudo aqui é
 * editável: dá pra tirar matéria que você não vai estudar e acrescentar a
 * que ele engoliu. O que vira edital é a lista DESTA tela, não o que o
 * parser achou — o rascunho é insumo, a decisão é do aluno.
 */
export default function PaginaCuradoria() {
  const router = useRouter();
  const params = useParams<{ rascunho: string }>();
  const id = Number(params.rascunho);

  const [draft, setDraft] = useState<Rascunho | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [cargo, setCargo] = useState<string | null>(null);
  const [disciplinas, setDisciplinas] = useState<DisciplinaEdital[]>([]);
  const [nova, setNova] = useState("");
  const [titulo, setTitulo] = useState("");
  const [orgao, setOrgao] = useState("");
  const [banca, setBanca] = useState("");
  const [salvando, setSalvando] = useState(false);

  /** comuns + as do cargo escolhido. Trocar de cargo remonta a lista —
   *  edição manual do cargo anterior não sobrevive, e não deveria. */
  const montar = useCallback((d: Rascunho, nome: string | null) => {
    const doCargo = d.estrutura.cargos.find((c) => c.nome === nome)?.disciplinas ?? [];
    setDisciplinas([...d.estrutura.comuns, ...doCargo]);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    getRascunho(id)
      .then((d) => {
        setDraft(d);
        setTitulo(d.titulo);
        // Cargo único (ou edital que não separa por cargo) não é escolha —
        // é só um clique a mais antes de fazer a única coisa possível.
        const auto = d.estrutura.cargos.length === 1 ? d.estrutura.cargos[0].nome : null;
        setCargo(auto);
        if (d.estrutura.cargos.length <= 1) montar(d, auto);
      })
      .catch((e) =>
        setErro(
          e instanceof ErroApi && e.status === 404
            ? "esse rascunho expirou ou não existe — suba o PDF de novo"
            : "não deu pra carregar o rascunho"
        )
      );
  }, [id, router, montar]);

  function escolherCargo(nome: string) {
    setCargo(nome);
    if (draft) montar(draft, nome);
  }

  async function confirmar() {
    if (!draft || disciplinas.length === 0 || salvando) return;
    setSalvando(true);
    setErro(null);
    try {
      await confirmarRascunho(draft.id, {
        disciplinas,
        titulo: titulo.trim() || undefined,
        orgao: orgao.trim() || undefined,
        banca: banca.trim() || undefined,
      });
      router.push("/meta");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra confirmar o edital");
      setSalvando(false);
    }
  }

  if (erro && !draft) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="callout-danger">{erro}</p>
      </div>
    );
  }
  if (!draft) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <p className="text-sm text-muted">carregando o rascunho…</p>
      </div>
    );
  }

  const precisaEscolher = draft.estrutura.cargos.length > 1 && !cargo;
  const totalTopicos = disciplinas.reduce((n, d) => n + d.topicos.length, 0);

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <Voltar />
      <p className="rotulo mb-2">conferir antes de valer</p>
      <h1 className="text-2xl font-semibold tracking-tight">{draft.titulo}</h1>
      <p className="mt-1.5 text-sm text-muted">
        {draft.data_prova ? `prova em ${draft.data_prova}` : "sem data de prova reconhecida"}
        {" · "}
        {draft.origem === "parser"
          ? "lido pela estrutura do edital"
          : "lido pela IA — confira com atenção, modelo pode omitir matéria"}
      </p>

      {erro && <p className="callout-danger mt-4">{erro}</p>}

      {/* ------------------------------------------------------ cargo */}
      {draft.estrutura.cargos.length > 1 && (
        <div className="mt-6">
          <h2 className="mb-1 text-sm font-medium">
            Este edital tem {draft.estrutura.cargos.length} cargos. Qual é o seu?
          </h2>
          <p className="mb-3 text-[13px] text-muted">
            Só o conteúdo do cargo escolhido entra na sua mesa. O que é comum a todos (Português,
            RLM, Informática…) vem junto de qualquer jeito. O número é quantas matérias
            <em> só daquele cargo</em> entram — por isso cargos diferentes repetem o mesmo número.
          </p>
          <div className="flex flex-wrap gap-2">
            {draft.estrutura.cargos.map((c) => (
              <button
                key={c.nome}
                onClick={() => escolherCargo(c.nome)}
                className={c.nome === cargo ? "chip-ativo" : "chip"}
              >
                {c.nome === cargo && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                {c.nome}
                <span className="opacity-60">
                  · {c.disciplinas.length} {c.disciplinas.length === 1 ? "matéria" : "matérias"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ------------------------------------------------ disciplinas */}
      {!precisaEscolher && (
        <div className="mt-7">
          <h2 className="mb-1 text-sm font-medium">
            {disciplinas.length} disciplinas · {totalTopicos} tópicos
          </h2>
          <p className="mb-3 text-[13px] text-muted">
            Tire o que você não vai estudar e acrescente o que faltou. Vale a lista desta tela,
            não o que a leitura achou.
          </p>

          <ul className="space-y-1.5">
            {disciplinas.map((d, i) => (
              <li
                key={`${d.disciplina}-${i}`}
                className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-2.5"
              >
                <span className="min-w-0 flex-1 truncate text-[14px]">{d.disciplina}</span>
                <span className="mono-num shrink-0 text-[12px] text-subtle">
                  {d.topicos.length || "—"}
                </span>
                <button
                  onClick={() => setDisciplinas(disciplinas.filter((_, j) => j !== i))}
                  aria-label={`tirar ${d.disciplina}`}
                  className="shrink-0 rounded-lg p-1 text-subtle transition-colors hover:bg-surface-hover hover:text-danger"
                >
                  <X className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              const nome = nova.trim();
              if (!nome) return;
              // topicos vazio é legítimo: a pessoa quer a matéria mesmo sem
              // o edital detalhar. O backend cria a linha de tópico com o
              // próprio nome, senão a escolha não entraria no recorte.
              setDisciplinas([...disciplinas, { disciplina: nome, topicos: [] }]);
              setNova("");
            }}
            className="mt-3 flex gap-2"
          >
            <input
              value={nova}
              onChange={(e) => setNova(e.target.value)}
              placeholder="acrescentar disciplina que faltou"
              className="field flex-1"
            />
            <button type="submit" disabled={!nova.trim()} className="btn-ghost shrink-0">
              <Plus className="h-4 w-4" />
              adicionar
            </button>
          </form>
        </div>
      )}

      {/* ---------------------------------------------------- confirmar */}
      {!precisaEscolher && (
        <div className="mt-8 border-t border-line pt-6">
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
            <input value={titulo} onChange={(e) => setTitulo(e.target.value)}
                   placeholder="nome do edital" className="field md:col-span-3" />
            <input value={orgao} onChange={(e) => setOrgao(e.target.value)}
                   placeholder="órgão (opcional)" className="field" />
            <input value={banca} onChange={(e) => setBanca(e.target.value)}
                   placeholder="banca (opcional)" className="field" />
          </div>
          <button
            onClick={confirmar}
            disabled={disciplinas.length === 0 || salvando}
            className="btn-primary mt-4"
          >
            {salvando ? "gravando…" : "confirmar meu edital"}
          </button>
          <p className="mt-2.5 text-[12px] text-subtle">
            só agora isso vira edital da mesa e passa a contar na meta e na fila.
          </p>
        </div>
      )}
    </div>
  );
}
