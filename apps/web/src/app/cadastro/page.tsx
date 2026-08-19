"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Marca } from "@/components/Marca";
import { ErroApi, registrar, setToken } from "@/lib/api";

/**
 * Mesmo esqueleto visual de /login (marca + formulário) — a tela existia
 * há tempos no cliente de API (`registrar()`, POST /auth/registrar) sem
 * NENHUMA tela chamando ela; só dava pra criar conta via curl. Essa é a
 * lacuna #1 do diagnóstico (ver "Do protótipo ao sistema").
 *
 * Validação de senha (mín. 8 caracteres) é só feedback antecipado — quem
 * decide de verdade é `core/auth.registrar()`; se a regra mudar lá, o
 * pior que acontece aqui é a mensagem de erro do servidor aparecer sem o
 * aviso local ter pego antes. Duplicidade de e-mail também é resolvida
 * 100% pelo servidor (ErroAuth -> 400), não checada aqui.
 */
export default function PaginaCadastro() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function aoEnviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);

    if (senha.length < 8) {
      setErro("A senha precisa de pelo menos 8 caracteres");
      return;
    }
    if (senha !== confirmarSenha) {
      setErro("As senhas não coincidem");
      return;
    }

    setEnviando(true);
    try {
      const { token } = await registrar(email, senha);
      setToken(token);
      // Pro LOBBY, não pro onboarding: a conta nova ainda não tem mesa
      // nenhuma, e o onboarding pede "o PDF do SEU edital" sem que exista
      // um concurso-alvo pra receber ele — o edital acabava caindo numa
      // "Mesa principal" que o servidor cria por baixo (`mesa.padrao`) e
      // que a pessoa nunca escolheu nem nomeou. Perguntar "de qual
      // concurso é este edital?" ANTES de pedir o PDF é a ordem que a
      // própria criação de mesa já usa (`/mesas` -> criar -> /onboarding
      // com a mesa ativa definida); o cadastro era o único caminho que
      // pulava esse passo e entrava no fluxo pelo meio.
      router.push("/mesas");
    } catch (e) {
      // ErroApi.message já vem do "detail" do FastAPI — mesma mensagem
      // que auth.py devolve pra e-mail duplicado ou senha curta.
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

          <h2 className="text-[23px] tracking-[-0.3px]">Crie sua mesa de estudo</h2>
          <p className="mt-1.5 text-sm text-muted">Leva menos de um minuto.</p>

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
              <label htmlFor="senha" className="mb-1.5 block text-[12.5px] text-muted">
                Senha
              </label>
              <input
                id="senha"
                type="password"
                required
                minLength={8}
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                className="field"
                placeholder="Mínimo 8 caracteres"
              />
            </div>

            <div>
              <label htmlFor="confirmar-senha" className="mb-1.5 block text-[12.5px] text-muted">
                Confirmar senha
              </label>
              <input
                id="confirmar-senha"
                type="password"
                required
                minLength={8}
                value={confirmarSenha}
                onChange={(e) => setConfirmarSenha(e.target.value)}
                className="field"
                placeholder="••••••••"
              />
            </div>

            {erro && <p className="callout-danger !p-3 text-[13px]">{erro}</p>}

            <button type="submit" disabled={enviando} className="btn-primary mt-1 w-full rounded-xl py-3.5 text-[14.5px]">
              {enviando ? "Criando conta…" : "Criar minha conta"}
            </button>
          </div>

          <p className="mt-6 text-center text-[13.5px] text-muted">
            Já tem uma conta?{" "}
            <Link href="/login" className="text-accent-text">
              Entrar na plataforma.
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
