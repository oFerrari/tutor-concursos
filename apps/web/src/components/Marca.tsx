/**
 * A marca. O ícone é o mesmo SVG do protótipo — dois colchetes e uma barra
 * (`</>`), o símbolo de código — desenhado à mão em vez de puxado de uma
 * biblioteca de ícones: o traço (2.6) e o recorte do protótipo não batem
 * com nenhum ícone pronto, e uma marca "quase igual" é justamente o tipo
 * de detalhe que faz a tela inteira parecer outra coisa.
 *
 * O quadrado rubro com glow vem de `.marca-icone` (globals.css).
 */
/** Só o glifo — pra quando o quadrado rubro tem outro tamanho ou raio
 *  (o avatar do tutor na conversa, por exemplo, é 9px e sem glow). */
export function MarcaGlifo({ className = "h-[17px] w-[17px]" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="m18 16 4-4-4-4" />
      <path d="m6 8-4 4 4 4" />
      <path d="m14.5 4-5 16" />
    </svg>
  );
}

export function MarcaIcone({ className = "h-[30px] w-[30px]" }: { className?: string }) {
  return (
    <span className={`marca-icone ${className}`}>
      <MarcaGlifo />
    </span>
  );
}

export function Marca({ compacta = false }: { compacta?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <MarcaIcone />
      {!compacta && (
        <span className="marca-texto">
          Ferrar<span className="text-accent-text">IA</span>
        </span>
      )}
    </span>
  );
}
