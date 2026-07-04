"""Scan de mispricing em HIGHER/LOWER (barrier contracts) -- produto nunca testado neste
ecossistema. Mecanica: contrato HIGHER ganha se spot_final > entry_spot + barrier (barrier
relativo ao entry spot). Payout e fixo (binario), nao convexo como Vanilla.

Hipotese: se a Deriv mispricinga a probabilidade de cruzar a barreira em alguma combinacao
de barrier/duration, o payout oferecido sera > fair value, gerando edge.

Metodo (mesma filosofia do vanilla_edge_scan/tickhigh_edge_scan):
  1. Baixar N ticks reais de 1HZ100V
  2. Bootstrap de retornos demeaned (driftless martingale)
  3. Para cada (barrier, duration): simular 20k caminhos, medir P(win) * payout vs stake
  4. IC95% via bootstrap para descartar ruido
"""
import asyncio
import os
import random
import statistics
import sys

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import bootstrap_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
N_HISTORY_TICKS = 10000
DURATIONS = [5, 10]  # ticks (min/max para tick contracts)
N_SIMULATIONS = 20000
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


async def get_higher_lower_quote(client, contract_type, symbol, duration, barrier):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": symbol, "duration": duration, "duration_unit": "t",
        "barrier": barrier,
    })
    if "error" in res:
        return None, res["error"].get("message", "")
    p = res.get("proposal", {})
    return {
        "ask_price": float(p.get("ask_price", STAKE)),
        "payout": float(p.get("payout", 0)),
        "spot": float(p.get("spot", 0)),
        "barrier": float(p.get("barrier", barrier)),
    }, None


async def get_barrier_choices(client, contract_type, symbol, duration):
    """Descobrir barriers validos forando erro com barrier absurdo."""
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": symbol, "duration": duration, "duration_unit": "t",
        "barrier": "+999.99",
    })
    # Tentar pegar barrier_choices do proposal (alguns contratos retornam)
    if "proposal" in res:
        return res["proposal"].get("barrier_choices", [])
    # Tentar do error details
    err = res.get("error", {})
    details = err.get("details", {})
    if "barrier_choices" in details:
        return details["barrier_choices"]
    # Fallback: barreiras comuns descobertas no probe
    return ["+0.01", "+0.10", "+0.20", "+0.33", "+0.50", "+1.00"]


def monte_carlo_win_prob(returns_pool, n_ticks, barrier_value, is_higher, n_sims, rng):
    """Simula n_sims caminhos de n_ticks a partir de spot=0 (barrier relativo).
    Retorna fracao de caminhos que cruzam a barreira no sentido certo no tick final."""
    pool_n = len(returns_pool)
    wins = 0
    for _ in range(n_sims):
        total = sum(returns_pool[rng.randrange(pool_n)] for _ in range(n_ticks))
        if is_higher:
            if total > barrier_value:   # HIGHER: win if final > entry + barrier
                wins += 1
        else:
            if total < barrier_value:   # LOWER: win if final < entry + barrier
                wins += 1
    return wins / n_sims


async def fetch_return_pool():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"Baixando {N_HISTORY_TICKS} ticks reais de {SYMBOL}...")
    prices = await fetch_ticks(client, SYMBOL, N_HISTORY_TICKS)
    await client.disconnect()
    raw_returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    mean_r = statistics.mean(raw_returns)
    demeaned = [r - mean_r for r in raw_returns]
    print(f"{len(prices)} ticks | drift bruto={mean_r:+.6f} (removido) | "
          f"desvio/tick={statistics.pstdev(raw_returns):.5f}\n")
    return demeaned


async def main(demeaned_returns, all_results, done_keys):
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    rng = random.Random(42)

    for duration in DURATIONS:
        print(f"\n{'='*80}\nDuracao={duration} ticks\n{'='*80}")
        for contract_type, is_higher in [("HIGHER", True), ("LOWER", False)]:
            barriers = await get_barrier_choices(client, contract_type, SYMBOL, duration)
            if not barriers:
                barriers = ["+0.01", "+0.10", "+0.20", "+0.33", "+0.50", "+1.00"]
            # Para LOWER, tambem testar barriers negativos (lado hard: spot precisa cair)
            if contract_type == "LOWER":
                barriers = barriers + ["-0.10", "-0.20", "-0.33", "-0.50"]
            print(f"\n  {contract_type} barriers: {barriers}")

            for barrier_str in barriers:
                key = (duration, contract_type, barrier_str)
                if key in done_keys:
                    continue
                q, err = await get_higher_lower_quote(client, contract_type, SYMBOL,
                                                       duration, barrier_str)
                await asyncio.sleep(0.3)
                if not q:
                    print(f"    {contract_type} barrier={barrier_str}: ERRO {err}")
                    done_keys.add(key)
                    continue

                barrier_val = float(barrier_str)
                win_prob = monte_carlo_win_prob(demeaned_returns, duration, barrier_val,
                                                 is_higher, N_SIMULATIONS, rng)

                # EV = win_prob * payout - stake
                fair_payout = STAKE / win_prob if win_prob > 0 else float('inf')
                ev = win_prob * q["payout"] - STAKE
                ev_pct = ev / STAKE

                # Bootstrap CI para win_prob
                # Simulacao rapida: re-amostrar os resultados individuais
                sim_results = []
                pool_n = len(demeaned_returns)
                for _ in range(300):
                    w = 0
                    for _ in range(N_SIMULATIONS // 10):  # sub-amostra pra velocidade
                        total = sum(demeaned_returns[rng.randrange(pool_n)]
                                    for _ in range(duration))
                        if is_higher and total > barrier_val:
                            w += 1
                        elif not is_higher and total < barrier_val:
                            w += 1
                    sim_results.append(w / (N_SIMULATIONS // 10))

                from stats_utils import bootstrap_ci as _bc
                wp_lo, wp_mean, wp_hi = _bc(sim_results, n_boot=500)
                ev_lo = wp_lo * q["payout"] - STAKE
                ev_hi = wp_hi * q["payout"] - STAKE

                flag = " <<< CANDIDATO A EDGE" if ev_lo > 0 else ""
                print(f"    {contract_type} barrier={barrier_str:>7} | payout=${q['payout']:.2f} | "
                      f"P(win)_MC={win_prob*100:.2f}% [IC95% {wp_lo*100:.2f}%, {wp_hi*100:.2f}%] | "
                      f"fair_payout=${fair_payout:.2f} | "
                      f"EV=${ev:+.4f} (IC95%[${ev_lo:+.4f},${ev_hi:+.4f}]){flag}")

                all_results.append({
                    "duration": duration, "type": contract_type, "barrier": barrier_str,
                    "payout": q["payout"], "win_prob": win_prob,
                    "wp_lo": wp_lo, "wp_hi": wp_hi,
                    "ev": ev, "ev_lo": ev_lo, "ev_hi": ev_hi,
                })
                done_keys.add(key)

    await client.disconnect()


def print_verdict(all_results):
    print("\n" + "=" * 80)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (HIGHER/LOWER x barrier x duration)")
    print("=" * 80)
    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge:")
        for c in candidates:
            print(f"    {c['type']} barrier={c['barrier']} dur={c['duration']}t: "
                  f"P(win)={c['win_prob']*100:.2f}% payout=${c['payout']:.2f} "
                  f"EV=${c['ev']:+.4f} (EV_lo=${c['ev_lo']:+.4f})")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0.")
        evs = [r["ev"] for r in all_results]
        if evs:
            print(f"    EV medio: ${statistics.mean(evs):+.4f} "
                  f"(min=${min(evs):+.4f}, max=${max(evs):+.4f})")
            # Analisar padrao: payout vs fair_payout
            print("\n    Detalhe por celula:")
            for r in sorted(all_results, key=lambda x: x["ev"], reverse=True):
                fair = STAKE / r["win_prob"] if r["win_prob"] > 0 else 0
                ratio = r["payout"] / fair if fair > 0 else 0
                print(f"    {r['type']} {r['barrier']:>7} dur={r['duration']}t: "
                      f"payout/justo={r['payout']:.2f}/{fair:.2f} (ratio={ratio:.4f}) "
                      f"EV=${r['ev']:+.4f}")


if __name__ == "__main__":
    demeaned_returns = None
    for attempt in range(4):
        try:
            demeaned_returns = asyncio.run(fetch_return_pool())
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry fetch {attempt+1}/4] {e}\n")

    all_results, done_keys = [], set()
    for attempt in range(10):
        try:
            asyncio.run(main(demeaned_returns, all_results, done_keys))
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry scan {attempt+1}/10] {e} ({len(done_keys)} celulas feitas)...\n")
            continue

    print_verdict(all_results)
