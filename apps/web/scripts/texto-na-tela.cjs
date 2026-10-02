/**
 * O que o aluno LÊ, e não o que o modelo escreveu: passa cada resposta pelo
 * `TextoDoTutor` de verdade (renderização estática) e devolve o texto visível.
 *
 * Existe para a bateria de descoberta (`apps/api/descobrir.py`): crase apagada
 * no caminho, `\text` comido pelo JSON e `\boxed` fora de cifrão só aparecem na
 * TELA — o texto da resposta continua "válido". Entrada: JSON (lista de
 * strings) no stdin. Saída: JSON (lista de strings) no stdout.
 *
 * Transpila os componentes com o `typescript` do monorepo, sem build do Next.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const Module = require("module");

const WEB = path.resolve(__dirname, "..");
const RAIZ = path.resolve(WEB, "..", "..");
const achar = (nome) => {
  for (const base of [WEB, RAIZ]) {
    try {
      return require.resolve(nome, { paths: [base] });
    } catch {}
  }
  throw new Error(`não achei ${nome}`);
};
const ts = require(achar("typescript"));

const pasta = fs.mkdtempSync(path.join(os.tmpdir(), "texto-na-tela-"));
for (const nome of ["Formula", "TextoDoTutor"]) {
  const fonte = fs
    .readFileSync(path.join(WEB, "src", "components", `${nome}.tsx`), "utf8")
    .replace(/@\/components\/(\w+)/g, "./$1.js");
  const js = ts.transpileModule(fonte, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  fs.writeFileSync(path.join(pasta, `${nome}.js`), js);
}
// Os componentes transpilados moram numa pasta temporária, onde `react` não se
// acha sozinho. Resolvidos UMA vez, antes de trocar a função: resolver dentro
// dela chamaria ela mesma de novo, sem fim.
const REACT = Object.fromEntries(
  ["react", "react/jsx-runtime", "react-dom/server"].map((n) => [n, achar(n)])
);
const original = Module._resolveFilename;
Module._resolveFilename = function (pedido, ...resto) {
  return REACT[pedido] ?? original.call(this, pedido, ...resto);
};
const React = require(REACT["react"]);
const { renderToStaticMarkup } = require(REACT["react-dom/server"]);
const { TextoDoTutor } = require(path.join(pasta, "TextoDoTutor.js"));

const visivel = (html) =>
  html
    .replace(/<\/(td|th)>/g, " | ")
    .replace(/<\/(p|h3|li|tr|pre|div|table)>/g, "\n")
    .replace(/<(br|hr)\s*\/?>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#x27;/g, "'")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

const entrada = JSON.parse(fs.readFileSync(0, "utf8"));
const saida = entrada.map((texto) => {
  try {
    return visivel(renderToStaticMarkup(React.createElement(TextoDoTutor, { texto })));
  } catch (e) {
    return `[[ERRO AO DESENHAR: ${e.message}]]`;
  }
});
fs.rmSync(pasta, { recursive: true, force: true });
process.stdout.write(JSON.stringify(saida));
