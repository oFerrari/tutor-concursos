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
      <form onSubmit={aoEnviar} className="card w-full max-w-sm space-y-4">
        <div>
          <p className="text-sm font-bold tracking-tight text-accent">tutor</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">entrar</h1>
        </div>

        <div className="space-y-1">
          <label htmlFor="email" className="text-sm text-muted">e-mail</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="senha" className="text-sm text-muted">senha</label>
          <input
            id="senha"
            type="password"
            required
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="field"
          />
        </div>

        {erro && <p className="text-sm text-danger">{erro}</p>}

        <button type="submit" disabled={enviando} className="btn-primary w-full">
          {enviando ? "entrando…" : "entrar"}
        </button>
      </form>
    </main>
  );
}
