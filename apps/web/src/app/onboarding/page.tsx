"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { MarcaGlifo } from "@/components/Marca";
import { EditorPerfil } from "@/components/EditorPerfil";
import {
  ErroApi,
  MesaNaLista,
  criarRascunho,
  getMesaAtiva,
  getMesas,
  salvarPerfil,
} from "@/lib/api";
import { ENTREVISTA } from "@/lib/perfil";

/**
 * "Primeiro contato" — o onboarding do protótipo: o PDF do edital mais
 * três respostas.
 *
 * Metade desta tela é REAL e metade é vitrine, e a divisão importa:
 *
 *  - O upload do edital é REAL, mas não grava nada ainda: cria um
 *    RASCUNHO (`POST /editais/rascunho`) e leva pra tela de curadoria, onde
 *    a pessoa escolhe o cargo e revisa as disciplinas. Um edital tem vários
 *    cargos, e ingerir todos junto punha matéria de Advocacia no plano de
 *    quem vai prestar TI.
 *  - As três perguntas (horas/nível/turno) são REAIS desde a migração 015:
 *    `usuario.perfil` (JSONB) grava a cada clique via `salvarPerfil()`,
 *    sem botão de "salvar" — ver o comentário no `onClick` mais abaixo pro
 *    porquê. "Horas" também aceita um valor personalizado (`core/auth.py`,
 *    `_valor_valido`): a lista fechada continua existindo pros presets,
 *    mas um número dentro de um padrão fixo (`Nh`, 1 a 16) passa — não é
 *    abrir campo livre, é um padrão fechado maior que 4 valores.
 *
 * Sobre a extração: `core/edital.py` é MELHOR ESFORÇO, não contrato —
 * layout de edital varia por banca. É exatamente por isso que existe a
 * curadoria: o extrator pode errar sem consequência, porque o erro morre
 * na tela antes de virar agendamento de revisão.
 */
export default function PaginaOnboarding() {
  const router = useRouter();
  const inputArquivo = useRef<HTMLInputElement>(null);

  const [respostas, setRespostas] = useState<Record<string, string>>(
    Object.fromEntries(ENTREVISTA.map((p) => [p.chave, p.padrao]))
  );
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function escolherResposta(chave: string, valor: string) {
    const novas = { ...respostas, [chave]: valor };
    setRespostas(novas);
    // Grava a cada clique, não num "salvar" no fim: são três escolhas de
    // um toque e a pessoa costuma sair da tela pelo upload do PDF, não por
    // um botão de confirmar — um "salvar" que ela nunca aperta é
    // preferência perdida. Falhar aqui não pode travar o onboarding.
    salvarPerfil(novas).catch(() => {});
  }

  // Esta tela é o destino de DOIS caminhos: a conta nova (que nunca viu o
  // produto) e a criação da segunda, terceira, quarta mesa — porque mesa
  // nova nunca tem edital e é aqui que ele entra. Chamar de "primeiro
  // contato" e se apresentar ("Sou a FerrarIA") na quarta vez é a tela
  // fingindo que não conhece quem já usa o produto há semanas.
  //
  // O sinal de primeira vez: nenhuma mesa com edital ainda. `getMesas()`
  // custa uma consulta por mesa, e uma conta tem unidades delas — barato
  // numa tela que não é quente, e não vale inventar um endpoint pra isso.
  const [mesas, setMesas] = useState<MesaNaLista[] | null>(null);
  useEffect(() => {
    getMesas().then(setMesas).catch(() => setMesas([]));
  }, []);
  const primeiraVez = mesas !== null && !mesas.some((m) => m.edital_id !== null);
  // A mesa ATIVA, não "a primeira sem edital": com duas mesas incompletas,
  // a segunda condição nomearia a errada — e a tela estaria dizendo pra
  // qual mesa o PDF vai enquanto a API grava noutra (o header manda).
  const alvo = mesas?.find((m) => m.id === getMesaAtiva()) ?? null;

  async function enviarEdital(arquivo: File) {
    setErro(null);
    setEnviando(true);
    try {
      // Sobe pra RASCUNHO e leva pra curadoria: nada vira edital antes de
      // a pessoa escolher o cargo. Um edital tem vários cargos, e ingerir
      // todos põe matéria de outro concurso dentro do plano dela.
      const d = await criarRascunho(arquivo, arquivo.name.replace(/\.pdf$/i, ""));
      router.push(`/edital/${d.id}`);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra ler o edital");
      setEnviando(false);
    }
  }

  const status = ENTREVISTA.map((p) => respostas[p.chave]).join(" · ");

  return (
    <div className="mx-auto w-full max-w-[680px] px-6 pb-10 pt-7">
      {/* ---------------------------------------------------- abertura */}
      <div className="mb-5 flex items-start gap-3">
        <span className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-accent text-accent-foreground">
          <MarcaGlifo className="h-[18px] w-[18px]" />
        </span>
        {/* Nada de texto antes de saber QUAL dos dois é o caso: um quadro
            piscando "primeiro contato" pra quem tem quatro mesas (ou o
            contrário) é pior que meio segundo de espaço vazio. */}
        <div className={mesas === null ? "opacity-0" : ""}>
          <p className="rotulo mb-2">
            {primeiraVez ? "FerrarIA · primeiro contato" : "FerrarIA · edital da mesa"}
          </p>
          {primeiraVez ? (
            <>
              <h1 className="text-[26px] leading-tight tracking-[-0.3px]">
                Sou a FerrarIA. Vou te <span className="text-accent-text">ferrar</span> de estudar até
                você passar.
              </h1>
              <p className="mt-2.5 text-[15px] leading-[1.65] text-muted">
                Me dê o PDF do seu edital e três respostas. Com isso eu monto sua árvore de tópicos,
                calculo o ritmo necessário e começo a te cobrar todos os dias.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-[26px] leading-tight tracking-[-0.3px]">
                Falta o edital{" "}
                {alvo && <>de <span className="text-accent-text">{alvo.nome}</span></>}.
              </h1>
              <p className="mt-2.5 text-[15px] leading-[1.65] text-muted">
                Sem ele esta mesa não recorta nada — mostra o acervo inteiro e a meta fica sem prazo.
                Suba o PDF e eu extraio as matérias e os tópicos; você confere antes de valer.
              </p>
            </>
          )}
        </div>
      </div>

      {/* ------------------------------------------------ PDF do edital */}
      <input
        ref={inputArquivo}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          // Zerar o value é o que permite escolher o MESMO arquivo de novo:
          // `change` só dispara quando o valor MUDA, então reenviar o mesmo
          // PDF (depois de um erro, ou pra conferir) não fazia nada — a tela
          // ficava parada até um F5. Tem que ser antes do await.
          e.target.value = "";
          if (f) enviarEdital(f);
        }}
      />

      <button
        type="button"
        disabled={enviando}
        onClick={() => inputArquivo.current?.click()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) enviarEdital(f);
        }}
        onDragOver={(e) => e.preventDefault()}
        className="drop mb-4 w-full"
      >
        <span className="mx-auto mb-3 flex h-[42px] w-[42px] items-center justify-center rounded-xl bg-accent-soft text-accent-text">
          <Upload className="h-5 w-5" strokeWidth={2.2} />
        </span>
        <span className="mb-1.5 block text-[15.5px] font-medium">
          {enviando ? "Lendo o edital…" : "Arraste o PDF do edital aqui"}
        </span>
        <span className="block text-[13.5px] text-muted">
          Extraio data da prova, banca, matérias, pesos e tópicos em segundos
        </span>
        <span className="mt-3 block font-mono text-[11.5px] text-label">PDF até 20 MB</span>
      </button>

      {erro && <p className="callout-danger mb-4 !p-3 text-[13px]">{erro}</p>}

      {/* ------------------------------------------------- entrevista
          Só no primeiro contato. Perguntar "quantas horas por dia?" de novo
          a cada mesa nova é ruído: a resposta é da PESSOA, não do concurso,
          e ela não muda por ter aberto um segundo edital. (Continua sem
          gravar em lugar nenhum — ver o aviso logo abaixo do bloco.) */}
      {primeiraVez && (
        <div className="mb-4">
          <EditorPerfil respostas={respostas} onEscolher={escolherResposta} />
        </div>
      )}

      {primeiraVez && (
        <p className="mb-4 text-[12px] text-subtle">
          Salvo a cada escolha. O tutor usa isso pra calibrar o tamanho do que sugere — não
          adianta propor três horas de estudo a quem tem uma.
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <p className="font-mono text-[11.5px] text-subtle">{primeiraVez ? status : ""}</p>
        <div className="flex gap-2">
          {/* Sem edital, "montar meu plano" não monta plano nenhum — a mesa
              segue sem recorte. Duas saídas com o mesmo destino e nomes
              diferentes prometiam coisas diferentes; ficou uma, honesta.

              A TERCEIRA saída é a que faltava: quem não tem o PDF (edital não
              publicado é metade do tempo de preparação de verdade) ficava só
              com "depois" — e "depois" deixa a mesa sem recorte nenhum,
              mostrando o acervo inteiro. O alvo manual existe desde a
              migração 017 e já estava ligado no editor de /mesas; o que não
              existia era o caminho ATÉ ele a partir daqui. */}
          <button onClick={() => router.push("/mesas")} className="btn-ghost">
            Voltar pras mesas
          </button>
          <button
            onClick={() => router.push("/alvo")}
            className="btn-ghost"
            title="Escolher as matérias do que existe no acervo, sem o PDF"
          >
            Não tenho o edital — escolher matérias
          </button>
          <button onClick={() => router.push("/")} className="btn-primary">
            Configuro o edital depois
          </button>
        </div>
      </div>
    </div>
  );
}
