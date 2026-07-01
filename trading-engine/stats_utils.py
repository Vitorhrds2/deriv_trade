"""
Utilitarios estatisticos compartilhados para o Mega Brain.

Todas as hipoteses rigorosas do ecossistema (H1, H3, T3, T4) usaram o mesmo
crivo: IC95% de Wilson no win rate + IC95% via bootstrap no EV/trade, sempre
comparado contra um controle nulo. Este modulo centraliza essas funcoes para
que toda nova hipotese (e a auditoria retroativa do hft_bot) use exatamente
o mesmo padrao, em vez de cada script reimplementar a sua propria versao.
"""
import math
import random


def wilson_ci(wins, n, z=1.96):
    """IC95% de Wilson para uma proporcao (win rate). Retorna (lo, hi) em [0,1]."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + (z ** 2) / n
    center = p + (z ** 2) / (2 * n)
    margin = z * math.sqrt((p * (1 - p) / n) + (z ** 2) / (4 * n ** 2))
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


def bootstrap_ci(values, n_boot=10000, ci=0.95, seed=42):
    """IC95% via bootstrap na media de uma lista de valores (ex.: profit/trade)."""
    if not values:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((1 - ci) / 2 * n_boot)
    hi_idx = int((1 + ci) / 2 * n_boot) - 1
    mean_val = sum(values) / n
    return (means[lo_idx], mean_val, means[hi_idx])


def mean(values):
    return sum(values) / len(values) if values else 0.0


def summarize(label, profits):
    """Imprime e retorna um resumo padrao (N, WR, IC95% Wilson, EV/trade, IC95% bootstrap)."""
    n = len(profits)
    wins = sum(1 for p in profits if p > 0)
    wr = wins / n if n else 0.0
    wr_lo, wr_hi = wilson_ci(wins, n)
    boot_lo, ev, boot_hi = bootstrap_ci(profits)
    total = sum(profits)
    print(f"\n--- {label} ---")
    print(f"N={n} | Wins={wins} | WR={wr*100:.2f}% (IC95% [{wr_lo*100:.2f}%, {wr_hi*100:.2f}%])")
    print(f"EV/trade=${ev:.4f} (IC95% [${boot_lo:.4f}, ${boot_hi:.4f}]) | PnL total=${total:.2f}")
    return {
        "label": label, "n": n, "wins": wins, "wr": wr,
        "wr_ci": (wr_lo, wr_hi), "ev": ev, "ev_ci": (boot_lo, boot_hi),
        "total_pnl": total,
    }
