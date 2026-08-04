#!/usr/bin/env python3
"""
Simulador de carga e progresso — SEM banco, SEM LLM, SEM cota.

    python simular.py
    python simular.py --questoes 428 --dias 90 --limite 25

Responde perguntas que só apareceriam depois de meses de uso real:
  · a fila estabiliza ou vira dívida impagável?
  · com teto diário de N, quanto do acervo fica dominado em 90 dias?
  · 1 dia de intervalo para erro é curto demais?

Usa as MESMAS funções de core/scheduler_regras.py que rodam em produção.
Simulador que reimplementa a regra testa a cópia, não o sistema.
"""
import argparse
import random
from core import scheduler_regras as R


def simular(questoes, dias, limite, p_correta, p_parcial, semente=7,
            novas_por_dia=None, ganho=0.16, regra=None):
    """
    novas_por_dia=None  -> estrategia ANTIGA: caixa mais baixa primeiro.
    novas_por_dia=N     -> estrategia ANKI: revisao pendente primeiro (sempre),
                           material novo com cota separada de N.

    A estrategia antiga sofre INANICAO: com 400 questoes de caixa 0 na fila,
    uma questao promovida volta em 3 dias e fica atras de todas elas. Nunca e
    revisada, nada consolida. O teto diario expoe o problema; sem teto ele
    fica escondido porque tudo e respondido todo dia.
    """
    rnd = random.Random(semente)
    # cada questão: [caixa, dia_da_proxima_revisao, tentativas]
    estado = [[0, 0, 0] for _ in range(questoes)]
    hist = []
    for dia in range(dias):
        vencidas = [i for i in range(questoes) if estado[i][1] <= dia]
        if novas_por_dia is None:
            fila = sorted(vencidas, key=lambda i: (estado[i][0], estado[i][1]))
            escolhidas = fila[:limite]
        else:
            revisoes = sorted((i for i in vencidas if estado[i][2] > 0),
                              key=lambda i: estado[i][1])
            novas = [i for i in vencidas if estado[i][2] == 0]
            escolhidas = revisoes[:limite]
            sobra = min(limite - len(escolhidas), novas_por_dia)
            escolhidas += novas[:max(0, sobra)]
            fila = vencidas
        atraso = max(0, len(fila) - len(escolhidas))
        for i in escolhidas:
            caixa = estado[i][0]
            # CURVA DE APRENDIZADO. A versao anterior usava acerto fixo, isto e,
            # um aluno que nunca aprende — premissa que faz qualquer regra de
            # promocao parecer ruim. Reencontrar a mesma questao aumenta a
            # chance de acerto; e para isso que a repeticao espacada existe.
            vistas_i = estado[i][2]
            pc = min(0.92, p_correta + ganho * vistas_i)
            r = rnd.random()
            if r < pc:
                veredito, dicas = "correta", (0 if rnd.random() < 0.6 else rnd.randint(1, 3))
            elif r < pc + p_parcial * 0.7:
                veredito, dicas = "parcial", rnd.randint(0, 3)
            else:
                veredito, dicas = "incorreta", 3
            nova = (regra or R.proxima_caixa)(caixa, veredito, dicas)
            estado[i] = [nova, dia + R.dias_ate_revisao(nova), estado[i][2] + 1]
        dominadas = sum(1 for c, _, _ in estado if c >= 3)
        vistas = sum(1 for _, _, t in estado if t > 0)
        hist.append({"dia": dia + 1, "venceram": len(fila),
                     "respondidas": len(escolhidas), "atraso": atraso,
                     "dominadas": dominadas, "vistas": vistas})
    return hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questoes", type=int, default=428)
    ap.add_argument("--dias", type=int, default=90)
    ap.add_argument("--limite", type=int, default=0, help="0 = compara vários")
    ap.add_argument("--acerto", type=float, default=0.45)
    ap.add_argument("--parcial", type=float, default=0.20)
    a = ap.parse_args()

    print(f"{a.questoes} questoes · {a.dias} dias · "
          f"acerto {a.acerto:.0%} · parcial {a.parcial:.0%}\n")

    print("ESTRATEGIA ATUAL (caixa mais baixa primeiro)")
    print(f"{'teto/dia':>9} {'vistas':>7} {'dominadas':>10} {'%':>5} {'atraso final':>13}")
    for lim in ([a.limite] if a.limite else [15, 25, 40, 60]):
        f = simular(a.questoes, a.dias, lim, a.acerto, a.parcial)[-1]
        print(f"{lim:>9} {f['vistas']:>7} {f['dominadas']:>10} "
              f"{100*f['dominadas']/a.questoes:>4.0f}% {f['atraso']:>13}")

    print("\nESTRATEGIA ANKI (revisao primeiro, cota de novas)")
    print(f"{'teto/dia':>9} {'novas/dia':>10} {'vistas':>7} {'dominadas':>10} {'%':>5} {'atraso final':>13}")
    for lim, nv in [(15, 5), (25, 8), (25, 15), (40, 12), (40, 25)]:
        if a.limite and lim != a.limite:
            continue
        f = simular(a.questoes, a.dias, lim, a.acerto, a.parcial, novas_por_dia=nv)[-1]
        print(f"{lim:>9} {nv:>10} {f['vistas']:>7} {f['dominadas']:>10} "
              f"{100*f['dominadas']/a.questoes:>4.0f}% {f['atraso']:>13}")

    lim = a.limite or 25
    h = simular(a.questoes, a.dias, lim, a.acerto, a.parcial, novas_por_dia=8)
    print(f"\nevolucao ANKI, teto {lim}/dia com 8 novas/dia:")
    print(f"{'dia':>5} {'venceram':>9} {'respond.':>9} {'vistas':>7} {'dominadas':>10}")
    for x in h:
        if x["dia"] in (1, 2, 3, 5, 7, 14, 21, 30, 45, 60, 90) or x["dia"] == a.dias:
            print(f"{x['dia']:>5} {x['venceram']:>9} {x['respondidas']:>9} "
                  f"{x['vistas']:>7} {x['dominadas']:>10}")


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------
# Variantes da regra, para decidir o peso do "parcial" com numero e nao palpite
def regra_parcial_desce(caixa, veredito, dicas):      # proposta atual
    if veredito == "correta":
        return min(caixa + 1, 5) if dicas == 0 else caixa
    return max(caixa - 1, 0) if veredito == "parcial" else 0


def regra_parcial_zera(caixa, veredito, dicas):        # parcial == erro
    if veredito == "correta":
        return min(caixa + 1, 5) if dicas == 0 else caixa
    return 0


def regra_parcial_mantem(caixa, veredito, dicas):      # parcial nao pune caixa
    if veredito == "correta":
        return min(caixa + 1, 5) if dicas == 0 else caixa
    return caixa if veredito == "parcial" else 0


def regra_dica_promove(caixa, veredito, dicas):        # acerto com dica promove
    if veredito == "correta":
        return min(caixa + 1, 5)
    return max(caixa - 1, 0) if veredito == "parcial" else 0
