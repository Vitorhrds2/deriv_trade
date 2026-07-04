"""
Scan de mispricing em High/Low Ticks (TICKHIGH/TICKLOW) -- produto nunca testado neste
ecossistema. Aposta em qual dos 5 ticks seguintes sera o maior (TICKHIGH) ou menor (TICKLOW).

Descoberta via probe_new_proposals.py: o payout cotado pela Deriv NAO e uniforme por posicao
(o que a hipotese ingenua de "5 ticks intercambiaveis => 1/5 cada" preveria) -- e simetrico em
formato de U:
    posicao 1: $35.09   posicao 2: $59.52   posicao 3: $65.36   posicao 4: $59.52   posicao 5: $35.09
Isso bate com a "lei do arcsine" de passeios aleatorios: o EXTREMO (maximo ou minimo) de um
random walk tende a ocorrer perto das BORDAS da janela, nao no meio -- entao a posicao 3 (meio)
e de fato a MENOS provavel de ser o extremo, e a Deriv parece precificar isso corretamente (nao
ingenuamente). A unica forma de saber se ha edge de verdade e medir a distribuicao EMPIRICA real
via bootstrap de retornos reais (nao assumir nem 1/5 nem a formula teorica do arcsine) e comparar
contra o payout cotado.

Metodo: Monte Carlo driftless via bootstrap de retornos reais (mesma filosofia do
vanilla_edge_scan.py), vetorizado com numpy pois cada "path" tem so 5 ticks (barato).
Para cada simulacao, sorteia 5 retornos com reposicao, soma cumulativa, acha a posicao do
maximo (TICKHIGH) e do minimo (TICKLOW). Wilson CI na proporcao empirica de cada posicao.
"""
import asyncio
import os
import statistics
import sys

import numpy as np
from dotenv import load_dotenv
from deriv_client import DerivClient
from stats_utils import wilson_ci

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ100V"
N_HISTORY_TICKS = 15000
N_TICKS_PATH = 5
N_SIMULATIONS = 200_000
STAKE = 10.0


async def fetch_ticks(client, symbol, count):
    all_prices = []
    end = "latest"
    remaining = count
    while remaining > 0:
        batch = min(remaining, 1000)
        res = await client.get_ticks_history(symbol, count=batch, end=end)
        hist = res.get("history", {})
        prices = hist.get("prices", [])
        times = hist.get("times", [])
        if not prices:
            break
        all_prices = prices + all_prices
        remaining -= len(prices)
        end = times[0] - 1
        await asyncio.sleep(0.12)
    return all_prices


async def fetch_return_pool():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"Baixando {N_HISTORY_TICKS} ticks reais de {SYMBOL} para calibrar o Monte Carlo...")
    prices = await fetch_ticks(client, SYMBOL, N_HISTORY_TICKS)
    await client.disconnect()
    raw_returns = np.diff(np.array(prices, dtype=np.float64))
    demeaned = raw_returns - raw_returns.mean()
    print(f"{len(prices)} ticks | drift bruto medio/tick={raw_returns.mean():+.6f} (removido p/ driftless) | "
          f"desvio/tick={raw_returns.std():.5f}\n")
    return demeaned


def simulate_extreme_positions(returns_pool, n_ticks, n_sims, seed=7):
    """Retorna (contagem_argmax, contagem_argmin) por posicao (1..n_ticks), vetorizado."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(returns_pool), size=(n_sims, n_ticks))
    draws = returns_pool[idx]
    paths = np.cumsum(draws, axis=1)  # preco relativo ao spot em cada uma das 5 ticks
    argmax_pos = np.argmax(paths, axis=1)  # 0-indexed
    argmin_pos = np.argmin(paths, axis=1)
    count_max = np.bincount(argmax_pos, minlength=n_ticks)
    count_min = np.bincount(argmin_pos, minlength=n_ticks)
    return count_max, count_min


async def get_payout(client, contract_type, selected_tick):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": contract_type,
        "currency": "USD", "underlying_symbol": SYMBOL, "duration": N_TICKS_PATH,
        "duration_unit": "t", "selected_tick": selected_tick,
    })
    if "error" in res:
        return None
    return float(res.get("proposal", {}).get("payout", 0))


async def main(returns_pool, all_results):
    count_max, count_min = simulate_extreme_positions(returns_pool, N_TICKS_PATH, N_SIMULATIONS)
    n = N_SIMULATIONS

    print(f"Distribuicao empirica (N={n:,} simulacoes bootstrap, {N_TICKS_PATH} ticks/path):")
    print(f"  {'posicao':>7}  {'P(argmax=pos)':>22}  {'P(argmin=pos)':>22}")
    for pos in range(N_TICKS_PATH):
        pmax_lo, pmax_hi = wilson_ci(int(count_max[pos]), n)
        pmin_lo, pmin_hi = wilson_ci(int(count_min[pos]), n)
        print(f"  {pos+1:>7}  {count_max[pos]/n*100:6.2f}% [{pmax_lo*100:5.2f},{pmax_hi*100:5.2f}]      "
              f"{count_min[pos]/n*100:6.2f}% [{pmin_lo*100:5.2f},{pmin_hi*100:5.2f}]")
    theoretical = [_sparre_andersen(k, N_TICKS_PATH) for k in range(N_TICKS_PATH)]
    print(f"\n  (referencia teorica teoria arcsine/Sparre-Andersen p/ posicao do max, driftless puro: "
          f"{[f'{t*100:.2f}%' for t in theoretical]})")

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"\n{'contrato':10} {'pos':>3} {'payout':>10} {'P_emp':>8} {'P_lo(IC95%)':>12} {'EV':>10} {'EV_lo':>10}")
    for contract_type, counts in [("TICKHIGH", count_max), ("TICKLOW", count_min)]:
        for pos in range(1, N_TICKS_PATH + 1):
            key = (contract_type, pos)
            if key in {r["key"] for r in all_results}:
                continue
            payout = await get_payout(client, contract_type, pos)
            await asyncio.sleep(0.4)
            if not payout:
                continue
            wins = int(counts[pos - 1])
            p_hat = wins / n
            p_lo, p_hi = wilson_ci(wins, n)
            ev = p_hat * payout - STAKE
            ev_lo = p_lo * payout - STAKE
            flag = " <<< CANDIDATO A EDGE (EV_lo > 0)" if ev_lo > 0 else ""
            print(f"{contract_type:10} {pos:>3} {payout:>10.2f} {p_hat*100:>7.2f}% {p_lo*100:>11.2f}% "
                  f"{ev:>+10.4f} {ev_lo:>+10.4f}{flag}")
            all_results.append({"key": key, "contract_type": contract_type, "pos": pos,
                                 "payout": payout, "p_hat": p_hat, "ev": ev, "ev_lo": ev_lo})
    await client.disconnect()


def _sparre_andersen(k, n):
    """P(argmax = k) [0-indexed] para um passeio aleatorio simetrico de n passos S_1..S_n
    (excluindo S_0), via formula combinatoria u_j = C(2j,j)/4^j."""
    from math import comb
    def u(j):
        return comb(2 * j, j) / 4 ** j if j >= 0 else 1.0
    # aproximacao: trata como posicao do max entre n pontos indexados 0..n-1 (S_1..S_n)
    return u(k) * u(n - 1 - k)


def print_verdict(all_results):
    print("\n" + "=" * 70)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (TICKHIGH/TICKLOW x posicao)")
    print("=" * 70)
    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge:")
        for c in candidates:
            print(f"    {c['contract_type']} pos={c['pos']}: EV_lo={c['ev_lo']:+.4f} (payout=${c['payout']:.2f})")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0 em nenhuma posicao/contrato testado.")
        evs = [r["ev"] for r in all_results]
        if evs:
            print(f"    EV medio: {statistics.mean(evs):+.4f} (min={min(evs):+.4f}, max={max(evs):+.4f})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    returns_pool = None
    for attempt in range(4):
        try:
            returns_pool = asyncio.run(fetch_return_pool())
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry fetch {attempt+1}/4] Conexao caiu ({e}), tentando de novo...\n")

    all_results = []
    for attempt in range(10):
        try:
            asyncio.run(main(returns_pool, all_results))
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry scan {attempt+1}/10] Conexao caiu ({e}), retomando de onde parou "
                  f"({len(all_results)} celulas ja feitas)...\n")
            continue

    print_verdict(all_results)
