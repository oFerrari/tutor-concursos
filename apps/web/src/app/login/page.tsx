"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ErroApi, login, setToken } from "@/lib/api";

export default function PaginaLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function aoEnviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      const { token } = await login(email, senha);
      setToken(token);
      router.push("/fila");
    } catch (e) {
      // ErroApi.message já vem do "detail" do FastAPI — mesma mensagem
      // que auth.py devolve pra email/senha errados ou conta inexistente.
      setErro(e instanceof ErroApi ? e.message : "não deu pra conectar com a API");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <form onSubmit={aoEnviar} className="w-full max-w-sm space-y-4">
        <h1 className="text-xl font-semibold">Tutor de concursos</h1>

        <div className="space-y-1">
          <label htmlFor="email" className="text-sm">e-mail</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded border border-black/20 px-3 py-2"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="senha" className="text-sm">senha</label>
          <input
            id="senha"
            type="password"
            required
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="w-full rounded border border-black/20 px-3 py-2"
          />
        </div>

        {erro && <p className="text-sm text-red-600">{erro}</p>}

        <button
          type="submit"
          disabled={enviando}
          className="w-full rounded bg-black py-2 text-white disabled:opacity-50"
        >
          {enviando ? "entrando…" : "entrar"}
        </button>
      </form>
    </main>
  );
}
