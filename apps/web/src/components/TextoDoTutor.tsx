/**
 * A prosa do tutor, formatada.
 *
 * O modelo escreve em Markdown por hábito — `**LIMPE**`, listas numeradas,
 * parágrafos separados por linha em branco. A tela mostrava o texto cru, então
 * o aluno lia literalmente `**Princípios Expressos (Constitucionais):**`. Pedir
 * ao prompt que não use asterisco seria lutar contra o modelo em todo turno, e
 * é o tipo de instrução que ele obedece por três respostas e esquece.
 *
 * POR QUE NÃO UMA BIBLIOTECA DE MARKDOWN. O tutor emite um subconjunto minúsculo
 * e conhecido (negrito, listas, parágrafos) — o prompt proíbe explicitamente
 * tabela, bloco de código e alternativas a)/b)/c). Um renderizador completo
 * traria dependência, peso e uma superfície de HTML arbitrário para texto que
 * vem de um modelo; aqui nada é interpretado como HTML, porque a formatação é
 * montada em JSX. Sem `dangerouslySetInnerHTML` em nenhum ponto.
 *
 * A CITAÇÃO GANHA DESTAQUE PRÓPRIO, e não é enfeite: `[CF, art. 37]` é a única
 * coisa na resposta que o aluno pode CONFERIR, e `socratic.limpar_citacoes`
 * existe pra garantir que toda citação tenha trecho por trás. Destacá-la é
 * mostrar onde olhar quando desconfiar — no meio da prosa ela se perdia.
 */

/** `**negrito**`, `*itálico*` e `[Citação, art. N]`. O resto passa intacto.
 *
 *  O negrito vem PRIMEIRO na alternância de propósito: `*` casaria a primeira
 *  metade de `**` e transformaria "**LIMPE**" em itálico com asterisco sobrando.
 *
 *  O itálico entrou porque o socratic-v44 o usa pra uma coisa importante — o
 *  aviso de que o conteúdo é doutrina e não veio do material do aluno. Ele
 *  fechava a resposta com "*Vale lembrar: isto é doutrina...*" e a tela mostrava
 *  os asteriscos, justamente na frase que existe pra ser lida. */
const PEDACOS = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]{1,160}\])/g;

/**
 * O que dentro de `[...]` é de fato uma CITAÇÃO.
 *
 * A primeira versão chipava tudo entre colchetes, e a primeira conversa real
 * mostrou por que isso não serve: o tutor escreveu
 * `[Questão 1: ... a) Legalidade; b) Eficiência...]` — violando o prompt, que
 * proíbe alternativa no chat — e a tela o desenhou como se fosse fonte de lei.
 * Chip é promessa de conferibilidade; dar essa aparência a texto inventado é
 * pior que não formatar nada.
 *
 * O formato é o de `retrieval.referencia`: "cp, art. 312", "CF, art. 37 — …",
 * "Lei 8.112/1990, art. 40", "Prova pericial, p. 14". Ou seja, tem "art." ou
 * "p." com número, e é curto. O resto fica texto comum.
 */
const CITACAO = /^[^\]]{1,80}?,\s*(art\w*\.?\s*\d|p\.\s*\d)/i;

function formatar(linha: string, chave: string) {
  return linha.split(PEDACOS).map((p, i) => {
    if (!p) return null;
    const k = `${chave}-${i}`;
    if (p.startsWith("**") && p.endsWith("**")) {
      return (
        <strong key={k} className="font-semibold text-foreground">
          {p.slice(2, -2)}
        </strong>
      );
    }
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) {
      // Itálico é o aviso de "isto não veio do seu material". Cor de rótulo em
      // vez de itálico puro: a frase precisa se distinguir do conteúdo, e
      // itálico sozinho passa batido num parágrafo longo.
      return (
        <em key={k} className="text-[14px] not-italic text-label">
          {p.slice(1, -1)}
        </em>
      );
    }
    if (p.startsWith("[") && p.endsWith("]") && CITACAO.test(p.slice(1, -1))) {
      return (
        <span
          key={k}
          className="mx-0.5 whitespace-nowrap rounded-[4px] border border-line-stronger bg-surface-hover px-1.5 py-px font-mono text-[11.5px] text-muted"
        >
          {p.slice(1, -1)}
        </span>
      );
    }
    return <span key={k}>{p}</span>;
  });
}

/** Linha de lista: "1. ", "- ", "· ". O recuo pendente é o que faz a segunda
 *  linha do item alinhar com a primeira em vez de voltar à margem. */
const ITEM = /^\s*(\d{1,2}[.)]|[-–•·*])\s+/;

export function TextoDoTutor({ texto }: { texto: string }) {
  // Parágrafo é linha em branco; dentro dele, cada linha é uma linha. Isso
  // preserva as listas que o modelo escreve uma por linha sem transformá-las
  // em prosa corrida.
  const paragrafos = texto.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2.5 text-[15px] leading-[1.65]">
      {paragrafos.map((par, pi) => {
        const linhas = par.split("\n");
        const lista = linhas.length > 1 && linhas.every((l) => ITEM.test(l) || !l.trim());
        if (lista) {
          return (
            <ul key={pi} className="space-y-1.5">
              {linhas
                .filter((l) => l.trim())
                .map((l, li) => {
                  const marca = ITEM.exec(l);
                  return (
                    <li key={li} className="flex gap-2">
                      <span className="shrink-0 select-none text-muted tabular-nums">
                        {marca ? marca[1].replace(/[-–•*]/, "·") : "·"}
                      </span>
                      <span className="min-w-0">
                        {formatar(l.replace(ITEM, ""), `${pi}-${li}`)}
                      </span>
                    </li>
                  );
                })}
            </ul>
          );
        }
        return (
          <p key={pi} className="whitespace-pre-wrap">
            {formatar(par, String(pi))}
          </p>
        );
      })}
    </div>
  );
}
