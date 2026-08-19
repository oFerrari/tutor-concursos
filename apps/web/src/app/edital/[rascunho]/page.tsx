"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Check } from "lucide-react";
import { Voltar } from "@/components/Voltar";
import {
  DisciplinaEdital,
  ErroApi,
  Rascunho,
  confirmarRascunho,
  getMesaAtual,
  getRascunho,
  getToken,
} from "@/lib/api";
import { ListaDisciplinas } from "@/components/ListaDisciplinas";

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
/** Sentinela do "meu cargo não está aqui". Não é nome de cargo nenhum e nunca
 *  vai casar com `estrutura.cargos[].nome` — é justamente por isso que serve:
 *  marca que a escolha foi FEITA (a tela destrava) sem escolher um dos cargos
 *  que a leitura ofereceu. */
const MEU_CARGO_NAO_ESTA_AQUI = "\u0000manual";

export default function PaginaCuradoria() {
  const router = useRouter();
  const params = useParams<{ rascunho: string }>();
  const id = Number(params.rascunho);

  const [draft, setDraft] = useState<Rascunho | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [cargo, setCargo] = useState<string | null>(null);
  const [disciplinas, setDisciplinas] = useState<DisciplinaEdital[]>([]);
  const [titulo, setTitulo] = useState("");
  const [orgao, setOrgao] = useState("");
  const [banca, setBanca] = useState("");
  /** Nome que o aluno dá ao próprio cargo quando a leitura não o achou. Vai
   *  pro TÍTULO do edital, que é o único lugar onde ele volta a aparecer —
   *  `topico` guarda disciplina, não cargo (ver a aproximação (1) declarada
   *  em core/edital.py). Melhor gravar num campo que existe do que prometer
   *  um vínculo que o schema não tem. */
  const [cargoManual, setCargoManual] = useState("");
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
            ? "Esse rascunho expirou ou não existe — suba o PDF de novo"
            : "Não deu pra carregar o rascunho"
        )
      );

    // Órgão e banca JÁ FORAM digitados: a criação da mesa pede os dois, e
    // esta tela é o passo seguinte do mesmo fluxo. Nascer em branco fazia a
    // pessoa redigitar o que acabou de informar — ou, pior, deixar vazio por
    // achar que já estava salvo, e aí `mesa.banca` some. É `mesa.banca` que
    // decide o FORMATO da questão gerada (`geracao.tipo_da_banca`: Cebraspe
    // gera item C/E), então perdê-la aqui muda o que o aluno treina.
    //
    // Preenche, não trava: os campos seguem editáveis, porque o edital pode
    // corrigir o que foi digitado na pressa ao criar a mesa.
    getMesaAtual()
      .then((m) => {
        if (m.orgao) setOrgao(m.orgao);
        if (m.banca) setBanca(m.banca);
      })
      .catch(() => {});
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
        // O cargo agora tem COLUNA (018) em vez de ser colado no título: é o
        // que a meta mostra pra dizer de quem é o plano. O sentinela do
        // "não está aqui" nunca vai pro banco — o que vale ali é o nome que
        // o aluno digitou, e vazio é ausência legítima.
        cargo: cargo === MEU_CARGO_NAO_ESTA_AQUI
          ? cargoManual.trim() || undefined
          : cargo ?? undefined,
        orgao: orgao.trim() || undefined,
        banca: banca.trim() || undefined,
      });
      router.push("/meta");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra confirmar o edital");
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
        <p className="text-sm text-muted">Carregando o rascunho…</p>
      </div>
    );
  }

  const precisaEscolher = draft.estrutura.cargos.length > 1 && !cargo;
  const totalTopicos = disciplinas.reduce((n, d) => n + d.topicos.length, 0);

  // Disciplina com contagem MUITO acima das outras costuma ser erro de
  // parsing: um cabeçalho que o extrator não reconheceu faz a matéria
  // seguinte engolir os tópicos da anterior. Esta tela existe justamente
  // pra o erro do extrator morrer aqui — então ela precisa APONTAR o
  // suspeito, não só permitir corrigi-lo. Mediana e não média: uma
  // disciplina inflada puxa a média e esconde a si mesma.
  const contagens = [...disciplinas.map((d) => d.topicos.length)].sort((a, b) => a - b);
  const mediana = contagens.length
    ? contagens[Math.floor(contagens.length / 2)]
    : 0;
  const suspeito = (n: number) => mediana > 0 && n >= mediana * 4 && n >= 20;

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <Voltar />
      <p className="rotulo mb-2">conferir antes de valer</p>
      <h1 className="text-2xl font-semibold tracking-tight">{draft.titulo}</h1>
      <p className="mt-1.5 text-sm text-muted">
        {draft.data_prova ? `Prova em ${draft.data_prova}` : "Sem data de prova reconhecida"}
        {" · "}
        {draft.origem === "parser"
          ? "lido pela estrutura do edital"
          : draft.origem === "parser_apos_falha"
            ? "a IA não conseguiu ler — isto é só a leitura mecânica"
            : "lido pela IA — confira com atenção, modelo pode omitir matéria"}
      </p>

      {/* Falhar caladamente entregando o resultado PIOR é o pior dos dois
          mundos: o aluno via "lido pela estrutura do edital" e ia embora com
          os cargos somados numa lista só, sem saber que dava pra tentar de
          novo. "Seguir em frente" e "tentar de novo" são reações opostas, e
          antes as duas telas eram idênticas. */}
      {draft.origem === "parser_apos_falha" && (
        <p className="callout-warning mt-4 text-[13px]">
          A leitura por IA falhou (cota diária do modelo ou edital muito longo). O que está
          abaixo veio só do reconhecimento de padrão, então os cargos podem aparecer
          somados numa lista só. Vale subir o PDF de novo mais tarde — ou seguir daqui,
          tirando na mão o que não é seu.
        </p>
      )}

      {erro && <p className="callout-danger mt-4">{erro}</p>}

      {/* ------------------------------------------------------ cargo */}
      {draft.estrutura.cargos.length > 1 && (
        <div className="mt-6">
          <h2 className="mb-1 text-sm font-medium">
            Este edital tem {draft.estrutura.cargos.length} cargos. Qual é o seu?
          </h2>
          <p className="mb-3 text-[13px] text-muted">
            Só o conteúdo do cargo escolhido entra na sua mesa. O que é comum a todos (Português,
            RLM, Informática…) vem junto de qualquer jeito, e o número no chip já inclui esses
            comuns — é quantas matérias a mesa vai ter se você escolher aquele cargo.
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
                {/* O TOTAL que vai entrar (comuns + próprias), não só as
                    próprias. O chip dizia "7 matérias" e a lista abaixo
                    abria com 14 — o número estava certo e respondia outra
                    pergunta. Quem escolhe cargo quer saber com quantas
                    matérias vai ficar. O detalhe do rateio fica no hover. */}
                <span
                  className="opacity-60"
                  title={`${draft.estrutura.comuns.length} comuns a todos os cargos + ` +
                         `${c.disciplinas.length} só deste cargo`}
                >
                  · {draft.estrutura.comuns.length + c.disciplinas.length} matérias
                </span>
              </button>
            ))}

            {/* SAÍDA MANUAL, e ela é obrigatória: toda etapa automatizada que
                pode falhar precisa de um caminho que não dependa dela ter
                acertado. A leitura já errou de tudo em edital real — cargo a
                menos, cargo a mais, nome truncado — e sem esta opção o aluno
                cujo cargo não apareceu ficava preso numa tela que só oferece
                cargos que não são dele. Começa da lista COMUM (o que vale pra
                todos costuma estar certo) e ele monta o resto na mão, que é o
                que a tela de disciplinas abaixo já sabe fazer. */}
            <button
              onClick={() => {
                setCargo(MEU_CARGO_NAO_ESTA_AQUI);
                if (draft) setDisciplinas([...draft.estrutura.comuns]);
              }}
              className={cargo === MEU_CARGO_NAO_ESTA_AQUI ? "chip-ativo" : "chip"}
            >
              {cargo === MEU_CARGO_NAO_ESTA_AQUI && (
                <Check className="h-3.5 w-3.5" strokeWidth={3} />
              )}
              Meu cargo não está aqui
            </button>
          </div>

          {/* Nomear o cargo importa mesmo quando a leitura não o achou: é ele
              que dá nome ao que o aluno está montando, e sem campo pra isso a
              opção manual ficava pela metade — dava pra escolher as matérias
              mas não dizia de quem elas são. Fica ao lado das matérias, não
              numa tela nova, porque é a mesma decisão. */}
          {cargo === MEU_CARGO_NAO_ESTA_AQUI && (
            <div className="callout-info mt-3 text-[13px]">
              <p className="mb-2.5">
                Sem problema — a lista abaixo começa só com o que é comum a todos os cargos.
                Acrescente as matérias do seu cargo no campo do fim da lista; o que vale é o
                que ficar nesta tela.
              </p>
              <label className="block">
                <span className="mb-1 block text-[12px] text-subtle">
                  Qual é o seu cargo? (opcional — só pra dar nome ao seu plano)
                </span>
                <input
                  value={cargoManual}
                  onChange={(e) => setCargoManual(e.target.value)}
                  placeholder="Perito Criminal Federal – Área 3"
                  className="field !py-2 text-[13px]"
                />
              </label>
            </div>
          )}
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

          <ListaDisciplinas
            linhas={disciplinas.map((d) => ({
              nome: d.disciplina,
              contagem: d.topicos.length,
              selo: suspeito(d.topicos.length)
                ? {
                    texto: "confira",
                    titulo:
                      "Muito mais tópicos que as outras matérias — pode ser um cabeçalho que a leitura não reconheceu, fazendo esta matéria engolir os tópicos da anterior. Vale conferir no PDF.",
                  }
                : undefined,
            }))}
            aoTirar={(i) => setDisciplinas(disciplinas.filter((_, j) => j !== i))}
            // topicos vazio é legítimo: a pessoa quer a matéria mesmo sem o
            // edital detalhar. O backend cria a linha de tópico com o próprio
            // nome, senão a escolha não entraria no recorte.
            aoAdicionar={(nome) =>
              setDisciplinas([...disciplinas, { disciplina: nome, topicos: [] }])
            }
            placeholderNovo="Acrescentar disciplina que faltou"
          />
        </div>
      )}

      {/* ---------------------------------------------------- confirmar */}
      {!precisaEscolher && (
        <div className="mt-8 border-t border-line pt-6">
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
            <input value={titulo} onChange={(e) => setTitulo(e.target.value)}
                   placeholder="Nome do edital" className="field md:col-span-3" />
            <input value={orgao} onChange={(e) => setOrgao(e.target.value)}
                   placeholder="Órgão (opcional)" className="field" />
            <input value={banca} onChange={(e) => setBanca(e.target.value)}
                   placeholder="Banca (opcional)" className="field" />
          </div>
          <button
            onClick={confirmar}
            disabled={disciplinas.length === 0 || salvando}
            className="btn-primary mt-4"
          >
            {salvando ? "Gravando…" : "Confirmar meu edital"}
          </button>
          <p className="mt-2.5 text-[12px] text-subtle">
            Só agora isso vira edital da mesa e passa a contar na meta e na fila.
          </p>
        </div>
      )}
    </div>
  );
}
