"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { SimuladoRunner } from "@/components/SimuladoRunner";
import { RelatorioProva, RelatorioSimulado } from "@/components/RelatorioProva";
import {
  ErroApi,
  EstadoSimulado,
  HistoricoSimulado,
  apagarSimulado,
  getEstadoSimulado,
  getRelatorioSimulado,
  getSimulados,
  getToken,
  iniciarSimulado,
} from "@/lib/api";
import { sair } from "@/lib/cache";

export default function PaginaSimulado() {
  const router = useRouter();
  const [erro, setErro] = useState<string | null>(null);
  const [historico, setHistorico] = useState<HistoricoSimulado[] | null>(null);

  const [n, setN] = useState(10);
  const [minutos, setMinutos] = useState<number | "">("");
  const [nome, setNome] = useState("");

  const [sessao, setSessao] = useState<EstadoSimulado | null>(null);
  const [finalizado, setFinalizado] = useState(false);
  const [apagando, setApagando] = useState<number | null>(null);
  const [confirmando, setConfirmando] = useState<number | null>(null);
  // Revisão de uma prova já FECHADA, aberta a partir do histórico — sem
  // isso, o relatório só existia no instante em que a prova terminava; sair
  // da tela perdia pra sempre a chance de ver de novo qual foi a resposta
  // dada e qual era o gabarito.
  const [revisao, setRevisao] = useState<RelatorioSimulado | null>(null);

  function recarregarHistorico() {
    getSimulados().then(setHistorico).catch(() => {});
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    recarregarHistorico();
  }, [router]);

  async function comecar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const r = await iniciarSimulado(n, minutos === "" ? undefined : minutos, undefined, nome);
      if (r.questoes.length === 0) {
        setErro("Nenhuma questão no acervo ainda.");
        return;
      }
      setSessao({
        id: r.simulado_id,
        questoes: r.questoes.map((q) => ({ ...q, respondida: false, resposta_dada: null })),
        minutos_alvo: minutos === "" ? null : minutos,
        segundos_acumulados: 0,
        finalizado: false,
      });
      setFinalizado(false);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        sair();
        router.push("/login");
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
    }
  }

  /** Puxa o estado completo (questões + relógio) e só então abre o runner
   *  — o histórico só tem o resumo, não dá pra retomar sem isso. */
  async function continuar(id: number) {
    try {
      setSessao(await getEstadoSimulado(id));
      setFinalizado(false);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra retomar esse simulado");
    }
  }

  async function verRevisao(id: number) {
    try {
      setRevisao(await getRelatorioSimulado(id));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra abrir essa revisão");
    }
  }

  /** Dois cliques em vez de `window.confirm`: a mesma linha vira "tem
   *  certeza?" por um instante — menos intrusivo que um modal do navegador
   *  pra uma ação que já é fácil de desfazer o efeito (a prova não some
   *  de verdade, só a etiqueta — ver core/simulado.apagar). */
  async function apagar(id: number) {
    if (confirmando !== id) {
      setConfirmando(id);
      return;
    }
    setApagando(id);
    try {
      await apagarSimulado(id);
      setHistorico((h) => (h ? h.filter((s) => s.id !== id) : h));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não deu pra apagar");
    } finally {
      setApagando(null);
      setConfirmando(null);
    }
  }

  if (sessao && !finalizado) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <SimuladoRunner
          estado={sessao}
          rotuloContinuar="Novo simulado"
          onFinalizado={() => {
            setFinalizado(true);
            setSessao(null);
            recarregarHistorico();
          }}
          // Sair sem finalizar não perde nada — tudo que já foi respondido
          // já está salvo (migração 018). A prova só volta pra lista como
          // "em andamento", pronta pra continuar depois.
          onSair={() => {
            setSessao(null);
            recarregarHistorico();
          }}
        />
      </div>
    );
  }

  if (revisao) {
    return (
      <div className="mx-auto max-w-2xl p-6 md:p-10">
        <RelatorioProva relatorio={revisao} rotuloAcao="Fechar" onAcao={() => setRevisao(null)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Simulado</h1>
        <p className="mt-1 text-sm text-muted">Sem dica, sem correção durante a prova — gabarito só no final.</p>
      </div>

      <form onSubmit={comecar} className="card max-w-xs space-y-3">
        <div className="space-y-1">
          <label className="text-sm text-muted">Nome (opcional)</label>
          <input
            type="text"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="ex.: revisão de Penal"
            className="field"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm text-muted">Quantas questões</label>
          <input
            type="number"
            min={1}
            value={n}
            onChange={(e) => setN(Number(e.target.value))}
            className="field"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm text-muted">Meta de minutos (opcional)</label>
          <input
            type="number"
            min={1}
            value={minutos}
            onChange={(e) => setMinutos(e.target.value === "" ? "" : Number(e.target.value))}
            className="field"
          />
        </div>
        {erro && <p className="text-sm text-danger">{erro}</p>}
        <button type="submit" className="btn-primary">
          começar
        </button>
      </form>

      {historico && historico.length > 0 && (
        <div className="relative mt-10">
          {/* Clicar fora cancela a confirmação de exclusão — mesmo padrão
              de MenuConta.tsx: um overlay invisível abaixo (z-index) dos
              botões da própria linha, que ainda respondem ao clique normal. */}
          {confirmando !== null && (
            <div onClick={() => setConfirmando(null)} className="fixed inset-0 z-[40]" />
          )}
          <h2 className="mb-2 text-sm font-medium text-muted">Histórico</h2>
          <ul className="space-y-1 text-sm">
            {historico.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 border-b border-line py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{h.nome || h.criado_em.slice(0, 10)}</p>
                  <p className="text-[12px] text-muted">
                    {h.nome ? h.criado_em.slice(0, 10) + " · " : ""}
                    {h.respondidas}/{h.n_questoes}
                    {!h.em_andamento && ` · ${h.nota_pct ?? 0}%`}
                  </p>
                </div>
                <div className="relative z-[41] flex shrink-0 items-center gap-2">
                  {/* "Continuar"/"Ver revisão" ficam NA LINHA da prova, não
                      num aviso à parte — é a mesma prova, é só um estado
                      dela. Revisão fica disponível pra SEMPRE (não some
                      quando a tela de resultado fecha) — POST/GET
                      /simulados/{"{id}"}/relatorio só lê, nunca refinaliza.
                      Some e vira "Cancelar" durante a confirmação de
                      exclusão — as duas ações juntas (retomar/revisar E
                      apagar) ao mesmo tempo é ambíguo demais pra uma
                      decisão que já é irreversível o bastante sozinha. */}
                  {confirmando === h.id ? (
                    <button onClick={() => setConfirmando(null)} className="chip text-[12.5px]">
                      Cancelar
                    </button>
                  ) : h.em_andamento ? (
                    <button onClick={() => continuar(h.id)} className="chip-ativo text-[12.5px]">
                      Continuar
                    </button>
                  ) : (
                    <button onClick={() => verRevisao(h.id)} className="chip text-[12.5px]">
                      Ver revisão
                    </button>
                  )}
                  <button
                    onClick={() => apagar(h.id)}
                    disabled={apagando === h.id}
                    aria-label={confirmando === h.id ? "confirmar exclusão" : "apagar simulado"}
                    className={
                      confirmando === h.id
                        ? "chip !border-danger !text-danger text-[12px]"
                        : "btn-icone text-muted hover:text-danger"
                    }
                  >
                    {confirmando === h.id ? "apagar mesmo?" : <Trash2 className="h-4 w-4" />}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
