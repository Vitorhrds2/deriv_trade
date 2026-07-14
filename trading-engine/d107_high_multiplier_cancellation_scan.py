"""D107 — High-Multiplier Deal Cancellation Scan (600x-800x, 30m-60m).

PDF "Arbitragem de Opcionalidade Exótica" claims:
  - 1HZ50V 800x/60m: fee=$7.52, fair_value=$17.15, edge=+$5.10
  - 1HZ50V 600x/60m: similar edge

D52 refutou cancellation mispricing com N=120 live trades (até 400x).
D95 mostrou 400x/60m negativo em todos os símbolos.
Mas 600x-800x NUNCA foi testado — é um regime não explorado.

Este script faz scan READ-ONLY (sem trades, só proposals):
  1. Baixa 60k ticks reais de 1HZ50V e 1HZ100V
  2. Para cada célula (multiplier × cancellation × direction):
     - Pega o fee real cobrado pela API (proposal.cancellation.ask_price)
     - Calcula fair value via Monte Carlo (bootstrap em sub-blocos)
     - Compara: edge = fair_value - fee
  3. Reporta se alguma célula tem edge_lo > 0 (fee < fair value, IC95%)

Também calcula o custo do STRADDLE (MULTUP + MULTDOWN simultâneo):
  - Total fee = fee_up + fee_down
  - Total fair value = fv_up + fv_down
  - Straddle edge = total_fv - total_fee
  (O PDF propõe straddle para eliminar risco direcional)

Uso: python3 d107_high_multiplier_cancellation_scan.py
"""
import asyncio
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOLS = ["1HZ50V", "1HZ100V"]
STAKE = 10.0
N_HISTORY_TICKS = 60000
N_SIMULATIONS = 120000

# Focus on the PDF's claim: high multipliers, long cancellations
MULTIPLIERS = [200, 400, 600, 800, 1000]
CANCELLATION_DURATIONS = ["15m", "30m", "60m"]
CONTRACT_TYPES = ["MULTUP", "MULTDOWN"]

DUR_TO_MIN = {"5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60}
SUBBLOCK = 60  # ticks (~1min) — preserva autocorrelacao de curto prazo


async def fetch_ticks(client, symbol, count):
    all_prices, all_times = [], []
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
        all_times = times + all_times
        remaining -= len(prices)
        end = times[0] - 1
        await asyncio.sleep(0.12)
    return all_prices, all_times


async def get_cancellation_quote(client, symbol, contract_type, multiplier, cancellation):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": symbol, "multiplier": multiplier,
        "cancellation": cancellation,
    })
    if "error" in res:
        return None, res["error"].get("message", "")
    p = res.get("proposal", {})
    canc = p.get("cancellation", {})
    return {
        "ask_price_total": float(p.get("ask_price", STAKE)),
        "cancellation_fee": float(canc.get("ask_price", 0)),
        "spot": float(p.get("spot", 0)),
    }, None


def monte_carlo_fair_value(prefix_sums, n_ticks, stake, multiplier, is_up, n_sims, rng, ref_spot):
    """Bootstrap em SUB-blocos concatenados — mesmo método do D95 corrigido."""
    pool_n = len(prefix_sums) - 1
    payoffs = []
    max_start = pool_n - SUBBLOCK
    if max_start <= 0:
        return 0.0, 0.0, 0.0
    n_full = n_ticks // SUBBLOCK
    remainder = n_ticks - n_full * SUBBLOCK
    for _ in range(n_sims):
        delta = 0.0
        for _ in range(n_full):
            start = rng.randrange(max_start)
            delta += prefix_sums[start + SUBBLOCK] - prefix_sums[start]
        if remainder and pool_n > remainder:
            max_start_r = pool_n - remainder
            start = rng.randrange(max_start_r)
            delta += prefix_sums[start + remainder] - prefix_sums[start]
        pct_move = delta / ref_spot
        if is_up:
            payoff = min(stake, max(0.0, -pct_move) * stake * multiplier)
        else:
            payoff = min(stake, max(0.0, pct_move) * stake * multiplier)
        payoffs.append(payoff)
    mean = statistics.mean(payoffs)
    sem = statistics.pstdev(payoffs) / (n_sims ** 0.5)
    return mean, mean - 1.96 * sem, mean + 1.96 * sem


async def scan_symbol(symbol, prefix_sums, median_dt, ref_spot):
    """Run scan for one symbol."""
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    rng = random.Random(42)

    results = []
    print(f"\n{'='*110}")
    print(f"SYMBOL={symbol}  stake=${STAKE}  ticks_pool={len(prefix_sums)-1}  ref_spot={ref_spot:.4f}")
    print(f"{'='*110}")

    for multiplier in MULTIPLIERS:
        print(f"\n--- Multiplier={multiplier}x ---")
        row_data = {}
        for contract_type in CONTRACT_TYPES:
            is_up = contract_type == "MULTUP"
            for canc in CANCELLATION_DURATIONS:
                n_ticks = max(2, round((DUR_TO_MIN[canc] * 60) / median_dt))
                q, err = await get_cancellation_quote(client, symbol, contract_type, multiplier, canc)
                await asyncio.sleep(0.3)
                if not q:
                    print(f"  {contract_type:>9} {canc:>4} | ERRO: {err}")
                    continue

                fv, fv_lo, fv_hi = monte_carlo_fair_value(
                    prefix_sums, n_ticks, STAKE, multiplier, is_up, N_SIMULATIONS, rng, ref_spot)

                fee = q["cancellation_fee"]
                edge = fv - fee
                edge_lo = fv_lo - fee
                flag = " *** EDGE ***" if edge_lo > 0 else ""
                print(f"  {contract_type:>9} {canc:>4} ({n_ticks:>4}t) | "
                      f"fee=${fee:.4f} | fair=${fv:.4f} [{fv_lo:.4f},{fv_hi:.4f}] | "
                      f"edge=${edge:+.4f} (lo={edge_lo:+.4f}){flag}")

                key = f"{contract_type}_{canc}"
                row_data[key] = {
                    "multiplier": multiplier, "contract_type": contract_type,
                    "cancellation": canc, "n_ticks": n_ticks, "fee": fee,
                    "fair_value": fv, "fv_lo": fv_lo, "fv_hi": fv_hi,
                    "edge": edge, "edge_lo": edge_lo,
                    "spot": q["spot"],
                }
                results.append(row_data[key])

        # Straddle analysis: MULTUP + MULTDOWN same cancellation
        for canc in CANCELLATION_DURATIONS:
            up_key = f"MULTUP_{canc}"
            down_key = f"MULTDOWN_{canc}"
            if up_key not in row_data or down_key not in row_data:
                continue
            up = row_data[up_key]
            down = row_data[down_key]
            total_fee = up["fee"] + down["fee"]
            total_fv = up["fair_value"] + down["fair_value"]
            total_fv_lo = up["fv_lo"] + down["fv_lo"]
            straddle_edge = total_fv - total_fee
            straddle_edge_lo = total_fv_lo - total_fee
            flag = " *** STRADDLE EDGE ***" if straddle_edge_lo > 0 else ""
            print(f"  [STRADDLE] {canc:>4} | total_fee=${total_fee:.4f} | "
                  f"total_fair=${total_fv:.4f} | straddle_edge=${straddle_edge:+.4f} "
                  f"(lo={straddle_edge_lo:+.4f}){flag}")

    await client.disconnect()
    return results


async def main():
    print(f">>> D107 — High-Multiplier Deal Cancellation Scan (600x-800x, 30m-60m)")
    print(f"    Symbols: {SYMBOLS}")
    print(f"    Multipliers: {MULTIPLIERS}")
    print(f"    Cancellations: {CANCELLATION_DURATIONS}")
    print(f"    Stake: ${STAKE}")
    print(f"    MC simulations: {N_SIMULATIONS}/cell")
    print(f"    READ-ONLY (no trades, just proposals)")
    print()

    all_results = {}
    for symbol in SYMBOLS:
        # Fetch history
        client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
        await client.connect()
        print(f"Baixando {N_HISTORY_TICKS} ticks reais de {symbol}...")
        prices, times = await fetch_ticks(client, symbol, N_HISTORY_TICKS)
        await client.disconnect()

        if len(prices) < 1000:
            print(f"  ERRO: só {len(prices)} ticks obtidos para {symbol}, pulando")
            continue

        raw_returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        mean_r = statistics.mean(raw_returns)
        demeaned = [r - mean_r for r in raw_returns]
        ref_spot = statistics.mean(prices)
        dts = [times[i] - times[i - 1] for i in range(1, len(times)) if times[i] > times[i - 1]]
        median_dt = statistics.median(dts) if dts else 1.0
        print(f"  {len(prices)} ticks | drift={mean_r:+.6f} (removido) | "
              f"desvio/tick={statistics.pstdev(raw_returns):.5f} | "
              f"spot_ref={ref_spot:.4f} | dt_mediano={median_dt:.2f}s")

        prefix_sums = [0.0] * (len(demeaned) + 1)
        for i, r in enumerate(demeaned):
            prefix_sums[i + 1] = prefix_sums[i] + r

        # Run scan
        results = await scan_symbol(symbol, prefix_sums, median_dt, ref_spot)
        all_results[symbol] = results

    # Final verdict
    print("\n" + "=" * 110)
    print("VEREDITO FINAL — D107 High-Multiplier Deal Cancellation Scan")
    print("=" * 110)

    all_cells = []
    for symbol, results in all_results.items():
        for r in results:
            r["symbol"] = symbol
            all_cells.append(r)

    candidates = [r for r in all_cells if r["edge_lo"] > 0]
    if candidates:
        print(f"\n>>> {len(candidates)} célula(s) com edge_lo > 0 (fee < fair value, IC95%):")
        for c in sorted(candidates, key=lambda x: -x["edge_lo"]):
            print(f"  {c['symbol']} {c['contract_type']:>9} {c['multiplier']:>5}x {c['cancellation']:>4}: "
                  f"fee=${c['fee']:.4f} fair=${c['fair_value']:.4f} edge_lo=${c['edge_lo']:+.4f}")
    else:
        print("\n>>> SEM EDGE. 0 células com edge_lo > 0.")
        print("\n  Detalhe fee vs fair_value (ordenado por razão fee/fair, menor primeiro):")
        for r in sorted(all_cells, key=lambda x: (x["fee"] / x["fair_value"]) if x["fair_value"] > 0 else 1e9):
            ratio = r["fee"] / r["fair_value"] if r["fair_value"] > 0 else float("inf")
            print(f"  {r['symbol']} {r['contract_type']:>9} {r['multiplier']:>5}x {r['cancellation']:>4}: "
                  f"fee=${r['fee']:.4f} fair=${r['fair_value']:.4f} ratio={ratio:.2f}x edge=${r['edge']:+.4f}")

    # Straddle summary
    print("\n--- STRADDLE SUMMARY (MULTUP + MULTDOWN same cancellation) ---")
    for symbol in SYMBOLS:
        sym_results = all_results.get(symbol, [])
        for mult in MULTIPLIERS:
            for canc in CANCELLATION_DURATIONS:
                up = next((r for r in sym_results if r["multiplier"] == mult and r["contract_type"] == "MULTUP" and r["cancellation"] == canc), None)
                down = next((r for r in sym_results if r["multiplier"] == mult and r["contract_type"] == "MULTDOWN" and r["cancellation"] == canc), None)
                if not up or not down:
                    continue
                total_fee = up["fee"] + down["fee"]
                total_fv = up["fair_value"] + down["fair_value"]
                total_fv_lo = up["fv_lo"] + down["fv_lo"]
                s_edge = total_fv - total_fee
                s_edge_lo = total_fv_lo - total_fee
                flag = " *** EDGE ***" if s_edge_lo > 0 else ""
                print(f"  {symbol} {mult:>5}x {canc:>4}: fee_total=${total_fee:.4f} "
                      f"fv_total=${total_fv:.4f} straddle_edge=${s_edge:+.4f} "
                      f"(lo={s_edge_lo:+.4f}){flag}")

    # Save JSON
    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D107",
        "description": "High-Multiplier Deal Cancellation Scan (600x-800x, 30m-60m)",
        "symbols": SYMBOLS,
        "multipliers": MULTIPLIERS,
        "cancellations": CANCELLATION_DURATIONS,
        "stake": STAKE,
        "n_simulations": N_SIMULATIONS,
        "n_candidates": len(candidates),
        "results": all_results,
    }
    fname = "d107_high_multiplier_cancellation_results.json"
    with open(fname, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResultados salvos em {fname}")


if __name__ == "__main__":
    asyncio.run(main())
