"use client";

import { useState } from "react";
import { ENTREVISTA } from "@/lib/perfil";

/**
 * As três perguntas do perfil (horas/nível/turno) como chips clicáveis —
 * extraído do onboarding porque a tela `/perfil` (editar depois) precisa
 * do MESMO editor, e duas cópias de uma lógica com estado (o chip
 * "personalizado" de horas) é como elas divergem — foi exatamente aqui que
 * um bug morou: a flag de "estou digitando horas personalizadas" apagava
 * o anel ativo de NÍVEL e TURNO também, porque a condição não checava qual
 * pergunta era qual. Ter isso escrito uma vez só é o que impede o mesmo
 * bug de voltar pela metade que ninguém está olhando.
 */
export function EditorPerfil({
  respostas,
  onEscolher,
}: {
  respostas: Record<string, string>;
  onEscolher: (chave: string, valor: string) => void;
}) {
  // Chip "personalizado" só faz sentido em "horas" — as outras duas
  // perguntas (nível, turno) são categóricas, um número não responde
  // nenhuma delas. `core/auth._valor_valido` aceita "Nh" ou "N.Nh" de 1 a 16.
  const [personalizandoHoras, setPersonalizandoHoras] = useState(false);
  const [horasPersonalizadas, setHorasPersonalizadas] = useState("");

  // "3,5h" foi o primeiro valor que uma pessoa de verdade digitou aqui —
  // rotina real tem fração, não só hora cheia. `formatarHoras` normaliza
  // pro formato que o backend aceita (ponto, não vírgula; no máx. 1 casa
  // decimal — `core/auth._RE_HORAS_PERSONALIZADA`) e tira o ".0" de um
  // valor inteiro, pra não gravar "3.0h" quando "3h" já é o formato dos
  // presets.
  function formatarHoras(n: number): string {
    const arredondado = Math.round(n * 10) / 10;
    return `${Number.isInteger(arredondado) ? arredondado : arredondado.toFixed(1)}h`;
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      {ENTREVISTA.map((p) => (
        <div
          key={p.chave}
          // A linha de HORAS é a mais cheia do formulário: 4 presets + o chip
          // do valor personalizado + o botão "personalizado". Com rótulo de
          // 190px o último caía numa segunda linha, e "personalizado" sozinho
          // embaixo parece outra pergunta, não a última opção da mesma. 120px
          // + gap menor deixam ~460px pros chips, que precisam de ~375 — folga
          // suficiente pra sobrar mesmo com o valor personalizado presente.
          // O rótulo mais longo ("Melhor horário") cabe em 120px.
          className="grid grid-cols-1 items-center gap-3 border-b border-line-soft px-5 py-4 last:border-b-0 md:grid-cols-[120px_1fr]"
        >
          <p className="text-sm text-body">{p.rotulo}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {p.opcoes.map((o) => (
              <button
                key={o}
                onClick={() => {
                  if (p.chave === "horas") setPersonalizandoHoras(false);
                  onEscolher(p.chave, o);
                }}
                // Sem exceção nenhuma aqui: o chip aceso é sempre o valor
                // que está VALENDO. Abrir o campo de digitação não muda
                // nada até apertar "ok", então apagar o anel do preset
                // durante a digitação (como fazia antes) dizia "nada
                // escolhido" sobre um valor que continuava salvo — e era
                // a fonte da flag global que apagava nível e turno junto.
                className={respostas[p.chave] === o ? "chip-ativo" : "chip"}
              >
                {o}
              </button>
            ))}

            {p.chave === "horas" &&
              (personalizandoHoras ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    // Vírgula normaliza pra ponto ANTES do `Number()` —
                    // `type="number"` nativo já deixou passar "3,5" que o
                    // JS não lê como 3.5 (o widget aceita a tecla, o valor
                    // debaixo não bate com nenhuma sintaxe numérica válida
                    // em todo browser/locale). Texto + normalização manual
                    // tira essa ambiguidade da mão do browser.
                    const n = Number(horasPersonalizadas.replace(",", "."));
                    if (Number.isFinite(n) && n >= 1 && n <= 16) {
                      onEscolher("horas", formatarHoras(n));
                      // Fecha ao confirmar: o campo aberto depois de salvar
                      // não dá sinal nenhum de que gravou — some justamente
                      // o chip aceso que É o retorno visual. Valor inválido
                      // (fora de 1-16, ou vazio) NÃO fecha: sumir com o
                      // campo sem gravar nada seria engolir o que a pessoa
                      // digitou sem dizer por quê.
                      setPersonalizandoHoras(false);
                    }
                  }}
                  className="flex items-center gap-1.5"
                >
                  <input
                    type="text"
                    inputMode="decimal"
                    autoFocus
                    value={horasPersonalizadas}
                    onChange={(e) => {
                      // Só dígito, vírgula e ponto — não é abrir campo
                      // livre, é aceitar as duas grafias de fração que
                      // existem em pt-BR antes de normalizar pra uma só
                      // no submit (mesmo espírito do regex fechado do
                      // backend, aplicado já na digitação).
                      setHorasPersonalizadas(e.target.value.replace(/[^0-9.,]/g, ""));
                    }}
                    placeholder="h/dia"
                    className="field w-[70px] !py-1.5 text-center text-[13px]"
                  />
                  <button type="submit" className="chip-ativo">
                    ok
                  </button>
                </form>
              ) : (
                <>
                  {/* O valor personalizado salvo é um chip A MAIS, do lado
                      dos presets — não um substituto do botão. Sem ele,
                      "3.5h" salvo não acendia em lugar nenhum e parecia
                      perdido; ocupando o LUGAR do "personalizado", sumia a
                      porta de entrada pra trocar por outro valor. As duas
                      versões anteriores erraram uma dessas metades: o chip
                      MOSTRA o que vale, o botão ABRE o campo, e são coisas
                      diferentes. Clicar nele reabre já preenchido (corrigir
                      3.5 pra 3.6 não deveria exigir digitar do zero). */}
                  {!(p.opcoes as readonly string[]).includes(respostas.horas) &&
                    respostas.horas && (
                      <button
                        onClick={() => {
                          setHorasPersonalizadas(respostas.horas.replace(/h$/, ""));
                          setPersonalizandoHoras(true);
                        }}
                        className="chip-ativo"
                      >
                        {respostas.horas}
                      </button>
                    )}

                  {/* SEMPRE presente, com valor personalizado salvo ou não:
                      é a porta pra digitar qualquer valor, e porta que some
                      depois de usada uma vez não é porta. Abre em BRANCO
                      (não com o valor atual) porque quem clica aqui quer
                      outro número — corrigir o atual é o chip acima. */}
                  <button
                    onClick={() => {
                      setHorasPersonalizadas("");
                      setPersonalizandoHoras(true);
                    }}
                    className="chip"
                  >
                    personalizado
                  </button>
                </>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
