"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { MarcaGlifo } from "@/components/Marca";
import { ErroApi, ResultadoIngestaoEdital, ingerirEdital } from "@/lib/api";
import { ENTREVISTA } from "@/mock/prototipo";

/**
 * "Primeiro contato" — o onboarding do protótipo: o PDF do edital mais
 * três respostas.
 *
 * Metade desta tela é REAL e metade é vitrine, e a divisão importa:
 *
 *  - O upload do edital chama `POST /edital` de verdade (`ingerirEdital`),
 *    que roda `core/edital.py` e devolve data da prova, tópicos e
 *    disciplinas. Depois disso `/meta` e o Raio-X passam a ter número.
 *  - As três perguntas (horas/nível/turno) são vitrine — TODO(backend):
 *    não há onde gravar preferência de estudo; `usuario` tem só id, email
 *    e hash de senha. Enquanto não houver, a resposta some ao sair da tela,
 *    e a tela DIZ isso em vez de fingir que guardou.
 *
 * Sobre a extração: `core/edital.py` é MELHOR ESFORÇO, não contrato —
 * `candidatos_data_prova()` devolve todos os candidatos com pontuação
 * justamente porque layout de edital varia por banca. Por isso a tela
 * mostra os candidatos quando há mais de um, em vez de escolher calado.
 */
export default function PaginaOnboarding() {
  const router = useRouter();
  const inputArquivo = useRef<HTMLInputElement>(null);

  const [respostas, setRespostas] = useState<Record<string, string>>(
    Object.fromEntries(ENTREVISTA.map((p) => [p.chave, p.padrao]))
  );
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoIngestaoEdital | null>(null);

  async function enviarEdital(arquivo: File) {
    setErro(null);
    // Limpa o resultado ANTES de subir o próximo: sem isso o painel do
    // edital anterior fica na tela durante o upload novo, e quando os dois
    // dão o mesmo número a tela parece congelada (foi o que pareceu
    // "precisar de F5" ao trocar de edital).
    setResultado(null);
    setEnviando(true);
    try {
      setResultado(await ingerirEdital(arquivo, arquivo.name.replace(/\.pdf$/i, "")));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "não deu pra enviar o edital");
    } finally {
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
        <div>
          <p className="rotulo mb-2">FerrarIA · primeiro contato</p>
          <h1 className="text-[26px] leading-tight tracking-[-0.3px]">
            Sou a FerrarIA. Vou te <span className="text-accent-text">ferrar</span> de estudar até você
            passar.
          </h1>
          <p className="mt-2.5 text-[15px] leading-[1.65] text-muted">
            Me dê o PDF do seu edital e três respostas. Com isso eu monto sua árvore de tópicos, calculo o
            ritmo necessário e começo a te cobrar todos os dias.
          </p>
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
          {enviando ? "lendo o edital…" : "Arraste o PDF do edital aqui"}
        </span>
        <span className="block text-[13.5px] text-muted">
          Extraio data da prova, banca, matérias, pesos e tópicos em segundos
        </span>
        <span className="mt-3 block font-mono text-[11.5px] text-label">PDF até 20 MB</span>
      </button>

      {erro && <p className="callout-danger mb-4 !p-3 text-[13px]">{erro}</p>}

      {resultado && (
        <div className="callout-success mb-4">
          <p className="text-sm font-medium">
            {resultado.topicos} tópicos em {resultado.disciplinas.length} disciplinas.
          </p>
          <p className="mt-1 text-[13px] opacity-90">
            {resultado.data_prova
              ? `data da prova: ${resultado.data_prova}`
              : "não achei a data da prova — dá pra informar na tela do edital"}
          </p>
          {/* Reporta os candidatos em vez de decidir calado — mesma
              postura de `edital.py` na CLI. */}
          {resultado.candidatos_data.length > 1 && (
            <p className="mt-2 font-mono text-[11.5px] opacity-80">
              outros candidatos: {resultado.candidatos_data.slice(1, 4).map((c) => c.data).join(" · ")}
            </p>
          )}
        </div>
      )}

      {/* ------------------------------------------------- entrevista */}
      <div className="mb-4 overflow-hidden rounded-2xl border border-line bg-surface">
        {ENTREVISTA.map((p) => (
          <div
            key={p.chave}
            className="grid grid-cols-1 items-center gap-4 border-b border-line-soft px-5 py-4 last:border-b-0 md:grid-cols-[190px_1fr]"
          >
            <p className="text-sm text-body">{p.rotulo}</p>
            <div className="flex flex-wrap gap-2">
              {p.opcoes.map((o) => (
                <button
                  key={o}
                  onClick={() => setRespostas((r) => ({ ...r, [p.chave]: o }))}
                  className={respostas[p.chave] === o ? "chip-ativo" : "chip"}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="mb-4 text-[12px] text-subtle">
        as três respostas ainda não são gravadas — não há campo de preferência no schema. O edital, sim.
      </p>

      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <p className="font-mono text-[11.5px] text-subtle">{status}</p>
        <div className="flex gap-2">
          <button onClick={() => router.push("/")} className="btn-ghost">
            Configuro depois
          </button>
          <button onClick={() => router.push("/")} className="btn-primary">
            Montar meu plano
          </button>
        </div>
      </div>
    </div>
  );
}
