/**
 * A prosa do tutor, formatada.
 *
 * O modelo escreve em Markdown por hábito — `**LIMPE**`, listas numeradas,
 * parágrafos separados por linha em branco. A tela mostrava o texto cru, então
 * o aluno lia literalmente `**Princípios Expressos (Constitucionais):**`. Pedir
 * ao prompt que não use asterisco seria lutar contra o modelo em todo turno, e
 * é o tipo de instrução que ele obedece por três respostas e esquece.
 *
 * POR QUE NÃO UMA BIBLIOTECA DE MARKDOWN. O tutor emite um subconjunto pequeno
 * e conhecido: negrito, listas, parágrafos, subtítulos e — desde 28/09/2026,
 * quando o aluno pediu a conta "igual o ChatGPT faz" — fórmula em LaTeX
 * (`Formula.tsx`), bloco de código para o mapa mental em árvore e tabela
 * Markdown. É o vocabulário de `socratic.SISTEMA_FORMATO`; mudou um, mude o
 * outro. Um renderizador completo
 * traria dependência, peso e uma superfície de HTML arbitrário para texto que
 * vem de um modelo; aqui nada é interpretado como HTML, porque a formatação é
 * montada em JSX. Sem `dangerouslySetInnerHTML` em nenhum ponto.
 *
 * A CITAÇÃO GANHA DESTAQUE PRÓPRIO, e não é enfeite: `[CF, art. 37]` é a única
 * coisa na resposta que o aluno pode CONFERIR, e `socratic.limpar_citacoes`
 * existe pra garantir que toda citação tenha trecho por trás. Destacá-la é
 * mostrar onde olhar quando desconfiar — no meio da prosa ela se perdia.
 */

import { Formula } from "@/components/Formula";

/** `**negrito**`, `*itálico*` e `[Citação, art. N]`. O resto passa intacto.
 *
 *  O negrito vem PRIMEIRO na alternância de propósito: `*` casaria a primeira
 *  metade de `**` e transformaria "**LIMPE**" em itálico com asterisco sobrando.
 *
 *  O itálico entrou porque o socratic-v44 o usa pra uma coisa importante — o
 *  aviso de que o conteúdo é doutrina e não veio do material do aluno. Ele
 *  fechava a resposta com "*Vale lembrar: isto é doutrina...*" e a tela mostrava
 *  os asteriscos, justamente na frase que existe pra ser lida. */
//
// A FÓRMULA VEM ANTES de tudo (`$$...$$`, `$...$`): dentro dela `*` e `[` são
// matemática. O cifrão de abertura não pode vir colado a letra nem seguido de
// espaço, e o de fechamento não pode vir depois de espaço — é o que separa
// `$x + 1$` de "multa de R$ 1.000 a R$ 5.000", que o material de lei traz toda hora.
const PEDACOS =
  /(\$\$[^$]+?\$\$|(?<![A-Za-z0-9\\])\$(?!\s)[^$\n]+?(?<!\s)\$|`[^`\n]+`|\*\*[^*\n]+\*\*|\*(?!\s)[^*\n]+?(?<!\s)\*|\[[^\]\n]{1,160}\])/g;

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
    if (p.length > 4 && p.startsWith("$$") && p.endsWith("$$")) {
      return <Formula key={k} tex={p.slice(2, -2)} bloco />;
    }
    if (p.length > 2 && p.startsWith("$") && p.endsWith("$")) {
      return <Formula key={k} tex={p.slice(1, -1)} />;
    }
    if (p.length > 2 && p.startsWith("`") && p.endsWith("`")) {
      return (
        <code key={k} className="rounded bg-surface-hover px-1 font-mono text-[13px]">
          {p.slice(1, -1)}
        </code>
      );
    }
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
    // ASTERISCO SEM PAR não é texto: é Markdown que o modelo fechou errado
    // ("pergunta?"* Não é proposição…*") e aparecia cru na tela (conversa real,
    // 01/10/2026). Entre letras/números ("2*3") ele fica.
    return <span key={k}>{p.replace(/(?<![\p{L}\p{N}])\*+|\*+(?![\p{L}\p{N}])/gu, "")}</span>;
  });
}

/** Linha de lista: "1. ", "- ", "· ". O recuo pendente é o que faz a segunda
 *  linha do item alinhar com a primeira em vez de voltar à margem. */
const ITEM = /^\s*(\d{1,2}[.)]|[-–•·*])\s+/;

/** Título de seção: "### Perícias" (1 a 4 cerquilhas). A leitura em sequência
 *  (`core/leitura.py`) organiza a aula por subtítulos, e a tela mostrava os
 *  "###" crus no meio do texto. */
const TITULO = /^\s*#{1,4}\s+(.+?)\s*#*\s*$/;

/** Linha de tabela Markdown: começa com "|". A linha de separação (|---|:--:|)
 *  diz que a de cima é o cabeçalho, e não vira linha da tabela. */
// Tolera o lixo que o modelo às vezes cola no fim da linha: "|---|---|---|>" veio
// assim na bateria de 29/09/2026, e a tabela inteira aparecia crua.
const LINHA_DE_TABELA = /^\s*\|.*\|\s*[>.]?\s*$/;
const SEPARADOR_DE_TABELA = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*[>.]?\s*$/;

function celulas(linha: string) {
  return linha.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

function tabela(cheias: string[], chave: string) {
  const temCabecalho = cheias.length > 1 && SEPARADOR_DE_TABELA.test(cheias[1]);
  const cabecalho = temCabecalho ? celulas(cheias[0]) : null;
  const corpo = cheias.slice(temCabecalho ? 2 : 0).filter((l) => !SEPARADOR_DE_TABELA.test(l));
  return (
    <div key={chave} className="overflow-x-auto">
      <table className="w-full border-collapse text-[14px]">
        {cabecalho && (
          <thead>
            <tr>
              {cabecalho.map((c, ci) => (
                <th key={ci} className="border-b border-line-stronger px-2.5 py-1.5 text-left font-semibold text-foreground">
                  {formatar(c, `${chave}-h${ci}`)}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {corpo.map((l, li) => (
            <tr key={li} className="border-b border-line-soft">
              {celulas(l).map((c, ci) => (
                <td key={ci} className="px-2.5 py-1.5 align-top">
                  {formatar(c, `${chave}-${li}-${ci}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function bloco(linhas: string[], chave: string) {
  const cheias = linhas.filter((l) => l.trim());
  if (!cheias.length) return null;
  if (cheias.length === 1 && /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(cheias[0])) {
    return <hr key={chave} className="border-line-soft" />;
  }
  if (cheias.length > 1 && cheias.every((l) => LINHA_DE_TABELA.test(l) || SEPARADOR_DE_TABELA.test(l))) {
    return tabela(cheias, chave);
  }
  // Tabela do PDF chega separada por TABULAÇÃO ("PESSOA\tPRESENTE\tFUTURO"): a
  // leitura da apostila de verbos mostrou a conjugação crua (29/09/2026). Duas
  // linhas ou mais, todas com tabulação: vira tabela, a primeira é o cabeçalho.
  if (cheias.length > 1 && cheias.every((l) => l.includes("\t"))) {
    const linhas = cheias.map((l) => `| ${l.split("\t").map((c) => c.trim()).join(" | ")} |`);
    const colunas = cheias[0].split("\t").length;
    return tabela([linhas[0], `|${" --- |".repeat(colunas)}`, ...linhas.slice(1)], chave);
  }
  // Fórmula sozinha no parágrafo: centralizada, como no caderno.
  const junto = cheias.join(" ").trim();
  if (/^\$\$[^$]+\$\$$/.test(junto)) {
    return (
      <div key={chave}>
        <Formula tex={junto.slice(2, -2)} bloco />
      </div>
    );
  }
  const lista = cheias.length > 1 && cheias.every((l) => ITEM.test(l));
  if (lista) {
    return (
      <ul key={chave} className="space-y-1.5">
        {cheias.map((l, li) => {
          const marca = ITEM.exec(l);
          return (
            <li key={li} className="flex gap-2">
              <span className="shrink-0 select-none text-muted tabular-nums">
                {marca ? marca[1].replace(/[-–•*]/, "·") : "·"}
              </span>
              <span className="min-w-0">{formatar(l.replace(ITEM, ""), `${chave}-${li}`)}</span>
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <p key={chave} className="whitespace-pre-wrap">
      {formatar(linhas.join("\n").trim(), chave)}
    </p>
  );
}

/** Fórmula escrita SEM cifrão. Medido na bateria de 28/09/2026: o resultado
 *  veio como `\boxed{\frac{1}{2}}` solto na linha, e a tela mostrava a barra.
 *  Fora de `$...$`, um comando de fórmula com seus `{}` vira fórmula. */
const MATEMATICA = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/;
// Com chaves (\boxed{..}, \frac{..}{..}) ou símbolo sozinho (\cap, \times):
// "n(A \cup B)" escrito em prosa, sem cifrão, aparecia com a barra na tela.
const COMANDO_SOLTO =
  /\\(?:(?:boxed|d?frac|sqrt|text)\{|(?:cap|cup|times|cdot|div|pm|leq?|geq?|neq?|approx|Rightarrow|rightarrow|Leftrightarrow|to|land|lor|neg|in|notin|subseteq?|emptyset|infty|Delta|alpha|beta|pi|sigma|theta|lambda|mu|circ|therefore)(?![A-Za-z]))/g;

function envolverSolto(texto: string) {
  return texto
    .split(MATEMATICA)
    .map((pedaco, i) => {
      if (i % 2 === 1) return pedaco; // já é fórmula
      let saida = "";
      let ultimo = 0;
      for (const m of pedaco.matchAll(COMANDO_SOLTO)) {
        if (m.index < ultimo) continue;
        let j = m[0].endsWith("{") ? m.index + m[0].length - 1 : m.index + m[0].length;
        while (pedaco[j] === "{") {
          let nivel = 0;
          for (; j < pedaco.length; j++) {
            if (pedaco[j] === "{") nivel++;
            else if (pedaco[j] === "}" && --nivel === 0) break;
          }
          j++;
        }
        saida += pedaco.slice(ultimo, m.index) + "$" + pedaco.slice(m.index, j) + "$";
        ultimo = j;
      }
      return saida + pedaco.slice(ultimo);
    })
    .join("");
}

/** Bloco de código: o mapa mental em árvore (├── └──). Separado ANTES dos
 *  parágrafos, porque a árvore tem linha em branco e o espaçamento é o desenho.
 *  Cerca sem fechamento (resposta ainda chegando) vale até o fim. */
const CERCA = /```[^\n]*\n?([\s\S]*?)(?:```|$)/g;

export function TextoDoTutor({ texto: bruto }: { texto: string }) {
  // `\( \)` e `\[ \]` são a outra grafia do LaTeX; o modelo alterna entre elas.
  const texto = bruto
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, f) => `$$${f}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, f) => `$${f}$`);
  const partes: { codigo: boolean; texto: string }[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(CERCA)) {
    if (m.index > ultimo) partes.push({ codigo: false, texto: texto.slice(ultimo, m.index) });
    partes.push({ codigo: true, texto: m[1].replace(/\s+$/, "") });
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) partes.push({ codigo: false, texto: texto.slice(ultimo) });
  return (
    <div className="space-y-2.5 text-[15px] leading-[1.65]">
      {partes.map((parte, bi) =>
        parte.codigo ? (
          parte.texto.trim() && (
            <pre
              key={`c${bi}`}
              className="overflow-x-auto rounded-lg border border-line bg-surface-hover px-3.5 py-3 font-mono text-[13px] leading-[1.55] text-foreground"
            >
              {parte.texto}
            </pre>
          )
        ) : (
          <Prosa key={`p${bi}`} texto={parte.texto} />
        )
      )}
    </div>
  );
}

/** Fórmula de exibição com o fecho errado: "$$30 + 15 = 45$" ou "$$\boxed{105}$|"
 *  (bateria de 29/09/2026 — o modelo erra o fecho, e a tela mostrava o cifrão).
 *  Só em linha com número ÍMPAR de "$$": a última abre, o primeiro "$" solto depois
 *  dela fecha, e um "|" colado ao fecho sai. Linha balanceada passa intacta. */
function repararCifrao(linha: string) {
  if (((linha.match(/\$\$/g) || []).length) % 2 === 0) return linha;
  const i = linha.lastIndexOf("$$");
  const resto = linha.slice(i + 2);
  const j = resto.indexOf("$");
  if (j < 1) return linha;
  return linha.slice(0, i + 2) + resto.slice(0, j) + "$$" + resto.slice(j + 1).replace(/^\|/, "");
}

function Prosa({ texto: bruto }: { texto: string }) {
  if (!bruto.trim()) return null;
  const texto = envolverSolto(bruto.split("\n").map(repararCifrao).join("\n"));
  // Parágrafo é linha em branco; dentro dele, cada linha é uma linha. Isso
  // preserva as listas que o modelo escreve uma por linha sem transformá-las
  // em prosa corrida. Um título pode vir colado ao parágrafo que abre ("###
  // Peritos\nO perito oficial…"): vira título e o resto segue como bloco.
  // Linha divisória é parágrafo próprio, ainda que o modelo a cole no texto.
  const paragrafos = texto
    .replace(/^[ \t]*(-{3,}|\*{3,}|_{3,})[ \t]*$/gm, "\n\n$1\n\n")
    .trim()
    .split(/\n{2,}/);
  return (
    <div className="space-y-2.5">
      {paragrafos.flatMap((par, pi) => {
        const linhas = par.split("\n");
        const titulo = TITULO.exec(linhas[0] ?? "");
        if (!titulo) return [bloco(linhas, String(pi))];
        return [
          <h3 key={`${pi}-t`} className="pt-1.5 text-[15.5px] font-semibold text-foreground">
            {formatar(titulo[1].replace(/^\*\*(.+)\*\*$/, "$1"), `${pi}-t`)}
          </h3>,
          bloco(linhas.slice(1), `${pi}-c`),
        ];
      })}
    </div>
  );
}
