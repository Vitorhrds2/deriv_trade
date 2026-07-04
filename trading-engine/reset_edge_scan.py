"""
Scan de mispricing em Reset Call/Put (RESETCALL/RESETPUT) -- produto nunca testado neste
ecossistema. Mecanica confirmada via probe_new_proposals.py (longcode real): "Win payout if
[symbol] after N is strictly higher [RESETCALL] than it was at EITHER entry or o meio do
contrato" -- ou seja, o strike "reseta" para o MENOR dos dois pontos de referencia (entrada,
meio), tornando o contrato mais favoravel ao comprador que uma call comum ATM:
    RESETCALL: paga se S_final > min(S_entrada, S_meio)
    RESETPUT : paga se S_final < max(S_entrada, S_meio)
Payout e FIXO (binario, sem "display_number_of_contracts" na proposal -- diferente da Vanilla).

Metodo: Monte Carlo driftless via bootstrap de retornos reais, vetorizado com numpy, em 2
checkpoints (primeira metade ate o meio, segunda metade ate o final) para nao precisar guardar
o path inteiro. Compara P(vitoria) simulado (Wilson CI) contra o payout fixo cotado.
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
TICKS_PER_SECOND = 1.0
N_HISTORY_TICKS = 15000
DURATIONS = [(5, "m", 5 * 60), (15, "m", 15 * 60), (30, "m", 30 * 60), (60, "m", 60 * 60)]
N_SIMULATIONS = 20_000
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


def simulate_reset_win_prob(returns_pool, n_ticks, n_sims, seed=7):
    """P(final > min(0,mid)) [CALL] e P(final < max(0,mid)) [PUT], via 2 checkpoints (sem
    guardar o path inteiro -- so a soma ate o meio e ate o final)."""
    rng = np.random.default_rng(seed)
    half = n_ticks // 2
    pool_n = len(returns_pool)

    idx1 = rng.integers(0, pool_n, size=(n_sims, half))
    s_mid = returns_pool[idx1].sum(axis=1)
    del idx1

    idx2 = rng.integers(0, pool_n, size=(n_sims, n_ticks - half))
    s_final = s_mid + returns_pool[idx2].sum(axis=1)
    del idx2

    call_wins = int(np.sum(s_final > np.minimum(0.0, s_mid)))
    put_wins = int(np.sum(s_final < np.maximum(0.0, s_mid)))
    return call_wins, put_wins


async def get_payout(client, contract_type, duration_val, duration_unit):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": contract_type,
        "currency": "USD", "underlying_symbol": SYMBOL, "duration": duration_val,
        "duration_unit": duration_unit,
    })
    if "error" in res:
        return None
    return float(res.get("proposal", {}).get("payout", 0))


async def main(returns_pool):
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    all_results = []
    print(f"{'duracao':>8} {'contrato':10} {'P_emp':>8} {'P_lo(IC95%)':>12} {'payout':>9} "
          f"{'EV':>10} {'EV_lo':>10}")
    for duration_val, duration_unit, duration_secs in DURATIONS:
        n_ticks = int(duration_secs * TICKS_PER_SECOND)
        call_wins, put_wins = simulate_reset_win_prob(returns_pool, n_ticks, N_SIMULATIONS)
        for contract_type, wins in [("RESETCALL", call_wins), ("RESETPUT", put_wins)]:
            payout = await get_payout(client, contract_type, duration_val, duration_unit)
            await asyncio.sleep(0.4)
            if not payout:
                continue
            p_hat = wins / N_SIMULATIONS
            p_lo, p_hi = wilson_ci(wins, N_SIMULATIONS)
            ev = p_hat * payout - STAKE
            ev_lo = p_lo * payout - STAKE
            flag = " <<< CANDIDATO A EDGE (EV_lo > 0)" if ev_lo > 0 else ""
            label = f"{duration_val}{duration_unit}"
            print(f"{label:>8} {contract_type:10} {p_hat*100:>7.3f}% {p_lo*100:>11.3f}% "
                  f"{payout:>9.2f} {ev:>+10.4f} {ev_lo:>+10.4f}{flag}")
            all_results.append({"duration": label, "contract_type": contract_type,
                                 "payout": payout, "p_hat": p_hat, "ev": ev, "ev_lo": ev_lo})

    await client.disconnect()
    return all_results


def print_verdict(all_results):
    print("\n" + "=" * 70)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (RESETCALL/RESETPUT x duracao)")
    print("=" * 70)
    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge:")
        for c in candidates:
            print(f"    {c['contract_type']} @ {c['duration']}: EV_lo={c['ev_lo']:+.4f} (payout=${c['payout']:.2f})")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0 em nenhuma duracao/contrato testado.")
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
            all_results = asyncio.run(main(returns_pool))
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry scan {attempt+1}/10] Conexao caiu ({e}), tentando de novo...\n")
            continue

    print_verdict(all_results)
