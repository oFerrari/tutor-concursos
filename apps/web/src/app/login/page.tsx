"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Marca } from "@/components/Marca";
import { ErroApi, login, setToken } from "@/lib/api";

/**
 * Tela dividida do protótipo: marca + promessa à esquerda, formulário à
 * direita. Abaixo de `lg` o painel da marca some — em coluna estreita ele
 * empurraria o formulário pra baixo da dobra, que é o oposto do que uma
 * tela de acesso precisa fazer.
 *
 * O protótipo tem ainda "Continuar com Google". NÃO ESTÁ AQUI de
 * propósito: o `api.py` só expõe `/auth/login` e `/auth/registrar`
 * (e-mail + senha, JWT), sem OAuth. Volta no dia em que existir.
 *
 * "Esqueceu a senha?" está aqui só como link visual (pedido explícito,
 * decisão registrada) — `api.py`/`core/auth.py` ainda NÃO têm rota de
 * reset de senha, então o clique não faz nada. Antes disso o argumento
 * era o oposto (link morto derruba confiança na tela); implementar de
 * verdade (token por e-mail + página de reset) segue em aberto.
 */
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
      // Entrar é escolher a missão do dia: a mesa decide o recorte de tudo o
      // que vem depois. Ir direto ao painel usava a mesa que sobrou do último
      // acesso sem perguntar — e numa conta nova, uma mesa que ninguém criou.
      router.push("/mesas");
    } catch (e) {
      // ErroApi.message já vem do "detail" do FastAPI — mesma mensagem
      // que auth.py devolve pra email/senha errados ou conta inexistente.
      setErro(e instanceof ErroApi ? e.message : "Não deu pra conectar com a API");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="grid min-h-full flex-1 grid-cols-1 lg:grid-cols-2">
      {/* ------------------------------------------------------- marca */}
      <div className="brilho-canto relative hidden flex-col justify-between overflow-hidden border-r border-line-soft px-11 py-10 lg:flex">
        <div className="grade-fundo" />

        <div className="relative z-[1] flex items-center gap-2.5">
          <Marca />
        </div>

        <div className="relative z-[1] max-w-[440px]">
          <h1 className="text-[34px] leading-tight tracking-[-0.6px]">
            Sua aprovação guiada por <span className="text-accent-text">Inteligência Artificial</span>.
          </h1>
          <p className="mt-4 text-[15px] leading-[1.7] text-muted">
            O único tutor socrático que domina o seu edital, mapeia a sua memória e planeja a sua rota de
            estudos até a posse.
          </p>
        </div>

        <div className="relative z-[1] flex flex-wrap gap-[18px] font-mono text-[11px] uppercase tracking-[1.5px] text-[#45454d]">
          <span>Algoritmo SM-2</span>
          <span>Método socrático</span>
          <span>Edital vetorizado</span>
        </div>
      </div>

      {/* --------------------------------------------------- formulário */}
      <div className="flex items-center justify-center overflow-y-auto px-7 py-10">
        <form onSubmit={aoEnviar} className="w-full max-w-[360px]">
          <div className="mb-7 flex items-center gap-2.5 lg:hidden">
            <Marca />
          </div>

          <h2 className="text-[23px] tracking-[-0.3px]">Acesse sua conta</h2>
          <p className="mt-1.5 text-sm text-muted">Bem-vindo de volta, futuro aprovado.</p>

          <div className="mt-6 flex flex-col gap-3.5">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-[12.5px] text-muted">
                E-mail
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="field"
                placeholder="voce@email.com"
              />
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor="senha" className="block text-[12.5px] text-muted">
                  Senha
                </label>
                {/* Visual só — sem rota de reset ainda, ver comentário no topo do arquivo. */}
                <span className="cursor-not-allowed text-[12.5px] text-accent-text" title="Ainda não implementado">
                  Esqueceu a senha?
                </span>
              </div>
              <input
                id="senha"
                type="password"
                required
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                className="field"
                placeholder="••••••••"
              />
            </div>

            {erro && <p className="callout-danger !p-3 text-[13px]">{erro}</p>}

            <button type="submit" disabled={enviando} className="btn-primary mt-1 w-full rounded-xl py-3.5 text-[14.5px]">
              {enviando ? "Entrando…" : "Entrar na plataforma"}
            </button>
          </div>

          <p className="mt-6 text-center text-[13.5px] text-muted">
            Ainda não tem uma conta?{" "}
            <Link href="/cadastro" className="text-accent-text">
              Crie sua mesa de estudo.
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
