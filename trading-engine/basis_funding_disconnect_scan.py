"""
D29 — Binance Futures Basis-Funding Disconnect (Carry Trade)

When the futures price > spot (contango) AND funding rate is NEGATIVE (shorts pay longs),
holding long futures is a FREE carry trade: you earn the funding + the basis converges to 0.

When futures < spot (backwardation) AND funding is POSITIVE (longs pay shorts),
holding short futures is a FREE carry trade.

The disconnect: funding rate should theoretically align with basis. When they diverge,
there's a structural arbitrage: lock in basis + collect funding.

Scan: fetch Binance futures mark price, spot price, and current funding rate for top pairs.
Calculate: annualized carry = (basis% + funding_8h_annualized) for long-futures carry
           or (-basis% - funding_8h_annualized) for short-futures carry

Usage:
  python3 basis_funding_disconnect_scan.py
  python3 basis_funding_disconnect_scan.py --symbols BTCUSDT,ETHUSDT,SOLUSDT
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone

try:
    from stats_utils import bootstrap_ci
except ImportError:
    import random
    def bootstrap_ci(values, n_boot=2000, ci=0.95, seed=42):
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
        return (means[lo_idx], sum(values) / n, means[hi_idx])


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_binance_spot_prices():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = fetch_json(url)
    return {d["symbol"]: float(d["price"]) for d in data}


def fetch_binance_futures_data():
    """Fetch mark price + funding rate for all USDT perpetuals."""
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    data = fetch_json(url)
    return data


def fetch_top_futures_symbols(limit=30):
    """Get top USDT perpetuals by volume."""
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    data = fetch_json(url)
    usdt_perps = [d for d in data if d["symbol"].endswith("USDT") and "USDC" not in d["symbol"]]
    usdt_perps.sort(key=lambda d: float(d["quoteVolume"]), reverse=True)
    return [d["symbol"] for d in usdt_perps[:limit]]


def scan_basis_funding(symbols=None, top_n=30):
    print(f"\n{'='*80}")
    print(f"D29 — Basis-Funding Disconnect Scan (Carry Trade)")
    print(f"{'='*80}")

    if symbols is None:
        symbols = fetch_top_futures_symbols(top_n)
    print(f"  Symbols: {len(symbols)}")

    # Fetch all data
    print("  Fetching spot prices...")
    spot_prices = fetch_binance_spot_prices()
    print("  Fetching futures mark prices + funding rates...")
    futures_data = fetch_binance_futures_data()

    # Binance taker fees: spot 0.1%, futures 0.04%
    # Need: buy spot + sell futures (or vice versa), 2 entry legs + 2 exit legs at expiry
    SPOT_TAKER = 0.001
    FUT_TAKER = 0.0004
    TOTAL_ROUNDTRIP = SPOT_TAKER + FUT_TAKER  # entry both legs (exit at delivery is free if held to settlement)

    results = []
    now = datetime.now(timezone.utc)

    for sym in symbols:
        spot_sym = sym  # BTCUSDT
        if spot_sym not in spot_prices:
            continue

        spot_price = spot_prices[spot_sym]
        fut = None
        for f in futures_data:
            if f.get("symbol") == sym:
                fut = f
                break
        if not fut:
            continue

        mark_price = float(fut.get("markPrice", 0))
        funding_rate = float(fut.get("lastFundingRate", 0))
        next_funding_ts = int(fut.get("nextFundingTime", 0))

        if mark_price <= 0 or spot_price <= 0:
            continue

        # Basis = (futures - spot) / spot
        basis_pct = (mark_price - spot_price) / spot_price * 100

        # Funding is per 8h. Annualized = funding * 3 * 365
        funding_annual = funding_rate * 3 * 365 * 100  # in %

        # Time to next funding
        if next_funding_ts > 0:
            next_funding = datetime.fromtimestamp(next_funding_ts / 1000, tz=timezone.utc)
            hours_to_funding = (next_funding - now).total_seconds() / 3600
        else:
            hours_to_funding = 8

        # Carry trade analysis:
        # LONG FUTURES carry (when contango + negative funding):
        #   Buy futures at mark, pay funding every 8h (if negative, you RECEIVE)
        #   At delivery, basis converges to 0 → gain basis%
        #   Net carry = basis% + (funding_8h * number_of_periods)
        #   But we need basis to be POSITIVE (futures > spot) and funding NEGATIVE
        #   → you collect basis convergence + receive funding = double profit

        # SHORT FUTURES carry (when backwardation + positive funding):
        #   Sell futures at mark, receive funding every 8h (if positive, shorts receive)
        #   At delivery, basis converges to 0 → gain -basis%
        #   Net carry = -basis% + (funding_8h * number_of_periods)
        #   Need basis NEGATIVE (futures < spot) and funding POSITIVE

        # Per-8h carry (one funding period):
        long_carry_8h = basis_pct + funding_rate * 100  # basis converges over time, funding per period
        short_carry_8h = -basis_pct + funding_rate * 100  # short gets +funding if positive

        # The "disconnect" is when carry is positive in both components:
        # Long: basis > 0 AND funding < 0 → both favor long futures
        # Short: basis < 0 AND funding > 0 → both favor short futures
        long_disconnect = basis_pct > 0 and funding_rate < 0
        short_disconnect = basis_pct < 0 and funding_rate > 0

        # Net profit if held to convergence (assume 1 funding period for conservative est):
        # Long: profit = basis% + funding% - roundtrip fees
        long_profit = basis_pct + funding_rate * 100 - TOTAL_ROUNDTRIP * 100
        # Short: profit = -basis% + funding% - roundtrip fees
        short_profit = -basis_pct + funding_rate * 100 - TOTAL_ROUNDTRIP * 100

        best_profit = max(long_profit, short_profit)
        best_side = "LONG" if long_profit > short_profit else "SHORT"

        results.append({
            "symbol": sym,
            "spot": spot_price,
            "mark": mark_price,
            "basis_pct": basis_pct,
            "funding_8h": funding_rate * 100,
            "funding_annual": funding_annual,
            "long_disconnect": long_disconnect,
            "short_disconnect": short_disconnect,
            "long_profit_8h": long_profit,
            "short_profit_8h": short_profit,
            "best_profit_8h": best_profit,
            "best_side": best_side,
            "hours_to_funding": hours_to_funding,
        })

    # Sort by profit
    results.sort(key=lambda r: r["best_profit_8h"], reverse=True)

    print(f"\n  Pairs analyzed: {len(results)}")
    print(f"  Roundtrip fees: {TOTAL_ROUNDTRIP*100:.2f}% (spot 0.1% + futures 0.04%)")

    # Disconnects
    long_disc = [r for r in results if r["long_disconnect"]]
    short_disc = [r for r in results if r["short_disconnect"]]
    print(f"\n  LONG disconnects (contango + neg funding): {len(long_disc)}")
    print(f"  SHORT disconnects (backwardation + pos funding): {len(short_disc)}")

    # Profitable after fees
    profitable = [r for r in results if r["best_profit_8h"] > 0]
    print(f"  Profitable after fees (1 funding period): {len(profitable)}")

    if results:
        print(f"\n  Top 20 by carry profit (per 8h):")
        print(f"  {'Symbol':>12} {'Basis%':>8} {'Fund8h%':>9} {'FundAnn%':>9} {'Side':>6} {'Profit8h%':>11} {'Disconnect':>11} {'h2fund':>7}")
        for r in results[:20]:
            disc = "LONG" if r["long_disconnect"] else ("SHORT" if r["short_disconnect"] else "-")
            print(f"  {r['symbol']:>12} {r['basis_pct']:>+7.3f} {r['funding_8h']:>+8.4f} {r['funding_annual']:>+8.2f} "
                  f"{r['best_side']:>6} {r['best_profit_8h']:>+10.4f} {disc:>11} {r['hours_to_funding']:>6.1f}h")

    # Verdict
    print(f"\n{'='*80}")
    print(f"VEREDITO — D29 Basis-Funding Disconnect")
    print(f"{'='*80}")

    if profitable:
        disconnects_profitable = [r for r in profitable if r["long_disconnect"] or r["short_disconnect"]]
        if disconnects_profitable:
            print(f"  >>> {len(disconnects_profitable)} disconnects profitable after fees")
            print(f"  >>> EDGE POTENCIAL: basis + funding ambos favoráveis")
            profits = [r["best_profit_8h"] for r in disconnects_profitable]
            print(f"  >>> Profit médio per 8h: {sum(profits)/len(profits):+.4f}%")
            print(f"  >>> CUIDADO: funding rate muda a cada período, não é garantido")
            print(f"  >>> Recomendado: monitorar continuamente, entrar apenas em disconnects grandes")
        else:
            print(f"  >>> {len(profitable)} profitable mas SEM disconnect (funding e basis alinhados)")
            print(f"  >>> Profit vem apenas de um componente (não é carry trade livre)")
    else:
        print(f"  >>> SEM EDGE. Nenhum par com carry positivo após fees em 1 período.")
        print(f"  >>> Basis e funding rate estão alinhados (sem disconnect).")

    # Annualized stats
    if results:
        annual_carries = [r["best_profit_8h"] * 3 * 365 for r in results]
        lo, mean, hi = bootstrap_ci(annual_carries)
        print(f"\n  Annualized carry (best side, all pairs):")
        print(f"    Mean: {mean:+.1f}% | IC95%: [{lo:+.1f}%, {hi:+.1f}%]")

    return results


def main():
    ap = argparse.ArgumentParser(description="D29 — Basis-Funding Disconnect Scan")
    ap.add_argument("--symbols", default=None, help="Comma-separated symbols (e.g., BTCUSDT,ETHUSDT)")
    ap.add_argument("--top", type=int, default=30, help="Top N futures by volume")
    args = ap.parse_args()

    symbols = args.symbols.split(",") if args.symbols else None
    scan_basis_funding(symbols=symbols, top_n=args.top)


if __name__ == "__main__":
    main()
