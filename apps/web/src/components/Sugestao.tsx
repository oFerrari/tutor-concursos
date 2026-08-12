"use client";

import { useEffect, useState } from "react";
import { getSugestao } from "@/lib/api";

/**
 * Intervenção proativa (módulo "conversa natural") — no máximo UMA
 * sugestão, igual `chat._mostrar_sugestao()`: reincidência > disciplina
 * fraca > sequência de acertos. A regra que decide QUAL mostrar já é
 * `core/ritmo_regras.py`; aqui é só exibição, sem lógica nova.
 */
export function Sugestao() {
  const [texto, setTexto] = useState<string | null>(null);

  useEffect(() => {
    getSugestao()
      .then((r) => setTexto(r.sugestao))
      .catch(() => {}); // sugestão é um extra — falhar aqui não deve travar a página
  }, []);

  if (!texto) return null;

  return <div className="callout-info mb-6">💡 {texto}</div>;
}
