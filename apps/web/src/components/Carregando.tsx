/**
 * O estado de carregando, num lugar só.
 *
 * Sete telas escreviam `<p>Carregando…</p>` cada uma do seu jeito, e o problema
 * não era a repetição do texto: era o SALTO. Um parágrafo de uma linha some e
 * dá lugar a uma tabela de dez, então a tela pula na cara de quem está lendo.
 * Esqueleto com a forma aproximada do conteúdo resolve isso de graça, e é o que
 * interface moderna faz — mas só compensa se existir em um lugar, senão cada
 * tela inventa o seu.
 *
 * `linhas` e `altura` porque a forma do conteúdo é diferente em cada tela: uma
 * lista de matérias não tem a mesma silhueta que um cartão de meta. Aproximar é
 * suficiente; acertar ao pixel seria manter duas cópias do layout.
 */
export function Carregando({
  linhas = 3,
  altura = 44,
  titulo = false,
  rotulo = "Carregando",
}: {
  linhas?: number;
  /** px de cada barra. */
  altura?: number;
  /** Barra curta no topo, pro caso de haver um cabeçalho antes da lista. */
  titulo?: boolean;
  /** Lido por leitor de tela — o esqueleto é invisível pra quem não vê a tela. */
  rotulo?: string;
}) {
  return (
    <div className="animate-pulse" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{rotulo}…</span>
      {titulo && <div className="mb-3 h-3 w-40 rounded bg-surface-raised" />}
      {Array.from({ length: linhas }).map((_, i) => (
        <div
          key={i}
          style={{ height: altura }}
          // A última barra sai mais curta: bloco perfeitamente retangular parece
          // conteúdo carregado, não conteúdo chegando.
          className={`mb-2 rounded-xl bg-surface-raised last:mb-0 ${
            i === linhas - 1 ? "w-2/3" : "w-full"
          }`}
        />
      ))}
    </div>
  );
}
