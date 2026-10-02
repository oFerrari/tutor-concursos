import type { ReactNode } from "react";

/**
 * Fórmula em LaTeX, desenhada em JSX — o subconjunto que o prompt ensina
 * (`socratic.SISTEMA_FORMATO`): \frac, ^, _, \sqrt, \boxed, \text e símbolos.
 *
 * POR QUE NÃO KaTeX. A decisão do `TextoDoTutor` vale aqui: texto de modelo não
 * vira HTML, e uma questão de concurso usa fração, potência, raiz, grau e o
 * resultado em caixa — nada que peça um motor tipográfico inteiro. Comando que
 * não está na lista aparece pelo nome, sem barra: legível, nunca quebrado.
 * Mudou a lista do prompt, mude esta.
 */
const SIMBOLOS: Record<string, string> = {
  times: "×", cdot: "·", div: "÷", pm: "±", mp: "∓", le: "≤", leq: "≤", ge: "≥", geq: "≥",
  neq: "≠", ne: "≠", approx: "≈", equiv: "≡", cup: "∪", cap: "∩", bigcup: "∪", bigcap: "∩", setminus: "∖", complement: "∁", subset: "⊂", subseteq: "⊆",
  supset: "⊃", in: "∈", notin: "∉", emptyset: "∅", varnothing: "∅", infty: "∞",
  Rightarrow: "⇒", Leftarrow: "⇐", Leftrightarrow: "⇔", rightarrow: "→", to: "→",
  leftarrow: "←", leftrightarrow: "↔", implies: "⇒", iff: "⇔", therefore: "∴",
  because: "∵", circ: "°", degree: "°", ldots: "…", cdots: "⋯", dots: "…",
  forall: "∀", exists: "∃", neg: "¬", lnot: "¬", land: "∧", wedge: "∧", lor: "∨", vee: "∨",
  oplus: "⊕", sum: "∑", prod: "∏", int: "∫", partial: "∂", angle: "∠", perp: "⊥",
  parallel: "∥", overline: "", quad: "  ", qquad: "    ",
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", varepsilon: "ε", theta: "θ",
  lambda: "λ", mu: "μ", pi: "π", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", varphi: "φ",
  omega: "ω", Delta: "Δ", Sigma: "Σ", Omega: "Ω", Pi: "Π", Gamma: "Γ", Theta: "Θ",
  "%": "%", "$": "$", "&": "&", "#": "#", "_": "_", "{": "{", "}": "}", ",": " ", ";": " ",
  ":": " ", "!": "", " ": " ", "\\": " ",
};
// Comandos que só mudam o estilo, ou que nada acrescentam na tela.
const TRANSPARENTES = new Set(["left", "right", "displaystyle", "big", "Big", "bigg", "limits"]);
const TEXTO = new Set(["text", "mathrm", "textrm", "mbox", "operatorname", "mathit", "textit"]);

type Leitor = { s: string; i: number };

/** Um argumento: `{...}` inteiro ou o próximo caractere/comando. */
function argumento(l: Leitor, chave: string): ReactNode {
  while (l.s[l.i] === " ") l.i++;
  if (l.s[l.i] === "{") {
    l.i++;
    return sequencia(l, chave, "}");
  }
  if (l.s[l.i] === "\\") return comando(l, chave);
  return l.s[l.i++] ?? "";
}

/** O conteúdo cru de `{...}`, para \text: ali o espaço é texto, não é ignorado. */
function cru(l: Leitor): string {
  while (l.s[l.i] === " ") l.i++;
  if (l.s[l.i] !== "{") return l.s[l.i++] ?? "";
  let nivel = 0;
  const ini = ++l.i;
  while (l.i < l.s.length) {
    const c = l.s[l.i];
    if (c === "{") nivel++;
    else if (c === "}") {
      if (nivel === 0) break;
      nivel--;
    }
    l.i++;
  }
  const texto = l.s.slice(ini, l.i);
  l.i++;
  return texto.replace(/\\([%$&#_ ])/g, "$1");
}

function comando(l: Leitor, chave: string): ReactNode {
  l.i++; // a barra
  const m = /^[A-Za-z]+/.exec(l.s.slice(l.i));
  const nome = m ? m[0] : l.s[l.i] ?? "";
  l.i += nome.length || 1;
  if (TRANSPARENTES.has(nome)) return null;
  if (nome === "frac" || nome === "dfrac" || nome === "tfrac") {
    const cima = argumento(l, `${chave}n`);
    const baixo = argumento(l, `${chave}d`);
    return (
      <span key={chave} className="mx-0.5 inline-flex flex-col items-center align-middle text-[0.9em] leading-tight">
        <span className="px-0.5">{cima}</span>
        {/* Invisível na tela, lido por leitor de tela e pela extração de texto da
            bateria de descoberta: sem ele, "2/5" virava "25". */}
        <span className="sr-only"> / </span>
        <span className="w-full border-t border-current px-0.5">{baixo}</span>
      </span>
    );
  }
  if (nome === "sqrt") {
    const dentro = argumento(l, `${chave}r`);
    return (
      <span key={chave} className="inline-flex items-baseline">
        √<span className="border-t border-current pl-0.5">{dentro}</span>
      </span>
    );
  }
  if (nome === "boxed") {
    const dentro = argumento(l, `${chave}b`);
    return (
      <span key={chave} className="mx-0.5 inline-block rounded-md border-2 border-accent px-2 py-0.5 font-semibold">
        {dentro}
      </span>
    );
  }
  if (nome === "textbf" || nome === "mathbf") {
    return <strong key={chave}>{cru(l)}</strong>;
  }
  if (TEXTO.has(nome)) return <span key={chave} className="not-italic">{cru(l)}</span>;
  if (nome in SIMBOLOS) return SIMBOLOS[nome];
  return nome;
}

/** Sequência até `fim` (ou até o fim da string): grupos, comandos, ^ e _. */
function sequencia(l: Leitor, chave: string, fim?: string): ReactNode[] {
  const saida: ReactNode[] = [];
  let n = 0;
  while (l.i < l.s.length) {
    const c = l.s[l.i];
    const k = `${chave}.${n++}`;
    if (fim && c === fim) {
      l.i++;
      break;
    }
    if (c === "{") {
      l.i++;
      saida.push(<span key={k}>{sequencia(l, k, "}")}</span>);
    } else if (c === "\\") {
      saida.push(comando(l, k));
    } else if (c === "^" || c === "_") {
      l.i++;
      // "^\circ" é o grau: sobrescrito de um círculo é só o símbolo de grau.
      const arg = argumento(l, k);
      const Tag = c === "^" ? "sup" : "sub";
      saida.push(
        arg === "°" ? (
          "°"
        ) : (
          <span key={k}>
            <span className="sr-only">{c}</span>
            <Tag className="text-[0.75em]">{arg}</Tag>
          </span>
        )
      );
    } else {
      saida.push(c);
      l.i++;
    }
  }
  return saida;
}

export function Formula({ tex, bloco = false }: { tex: string; bloco?: boolean }) {
  const corpo = sequencia({ s: tex.trim(), i: 0 }, "f");
  if (bloco) {
    return (
      <span className="my-1.5 block overflow-x-auto text-center font-serif text-[16.5px]">
        {corpo}
      </span>
    );
  }
  return <span className="whitespace-nowrap font-serif text-[15.5px]">{corpo}</span>;
}
