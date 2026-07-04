"""
D26 — Cross-Venue Funding Rate Arbitrage

HYPOTHESIS: When funding rates diverge between exchanges (Binance vs Bybit vs OKX),
going long perp on the exchange with LOWER funding and short perp on the exchange
with HIGHER funding captures the funding rate differential. This is MARKET-NEUTRAL
(no price exposure) and generates carry from the funding spread.

Unlike D9 (single-venue carry trade) and D24 (perp vs spot basis), this is:
- Long perp on Venue A + Short perp on Venue B (same underlying, same size)
- Profit = funding_diff * position_size (per 8h period)
- No spot leg needed, no basis risk

METHODOLOGY:
1. Fetch current funding rates from Binance, Bybit, OKX for BTC/ETH/SOL
2. Fetch historical funding rates (30 days) from Binance (most accessible)
3. Calculate funding spread between venue pairs
4. Simulate P&L: for each 8h period, P&L = (funding_long - funding_short) * notional
5. Calculate net P&L after fees (taker fees on both venues, entry + exit)
6. Bootstrap CI on daily P&L
7. Test persistence: is the spread consistent or does it flip?

Data sources (all free, no auth):
- Binance: https://fapi.binance.com/fapi/v1/fundingRate
- Bybit: https://api.bybit.com/v5/market/tickers?category=linear
- OKX: https://www.okx.com/api/v5/public/funding-rate

Usage:
  python3 cross_venue_funding_arb_scan.py
  python3 cross_venue_funding_arb_scan.py --asset BTC --days 30
"""
import argparse
import json
import math
import sys
import urllib.request
import urllib.error
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
        mean_val = sum(values) / n
        return (means[lo_idx], mean_val, means[hi_idx])


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ============ BINANCE ============

def binance_funding_current(symbol="BTCUSDT"):
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    data = fetch_json(url)
    return float(data.get("lastFundingRate", 0))


def binance_funding_history(symbol="BTCUSDT", limit=270):
    """270 = 90 days (3 per day)."""
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
    data = fetch_json(url)
    rates = []
    for item in data:
        rates.append({
            "time": item.get("fundingTime", 0),
            "rate": float(item.get("fundingRate", 0)),
        })
    return rates


# ============ BYBIT ============

def bybit_funding_current(symbol="BTCUSDT"):
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    data = fetch_json(url)
    result = data.get("result", {}).get("list", [])
    if result:
        return float(result[0].get("fundingRate", 0))
    return 0.0


# ============ OKX ============

def okx_funding_current(symbol="BTC-USDT-SWAP"):
    url = f"https://www.okx.com/api/v5/public/funding-rate?instId={symbol}"
    data = fetch_json(url)
    result = data.get("data", [])
    if result:
        return float(result[0].get("fundingRate", 0))
    return 0.0


def okx_funding_history(symbol="BTC-USDT-SWAP", limit=90):
    """OKX funding history (each is 8h)."""
    url = f"https://www.okx.com/api/v5/public/funding-rate-history?instId={symbol}&limit={limit}"
    data = fetch_json(url)
    rates = []
    for item in data.get("data", []):
        rates.append({
            "time": item.get("fundingTime", 0),
            "rate": float(item.get("fundingRate", 0)),
        })
    return rates


def analyze_funding_arb(asset="BTC", days=30):
    """Analyze cross-venue funding rate arbitrage."""
    binance_sym = f"{asset}USDT"
    bybit_sym = f"{asset}USDT"
    okx_sym = f"{asset}-USDT-SWAP"

    print(f"\n{'='*80}")
    print(f"D26 — Cross-Venue Funding Rate Arb | {asset}")
    print(f"{'='*80}")

    # Step 1: Fetch current funding rates
    print(f"\n[1/3] Fetching current funding rates...")
    venues = {}
    try:
        venues["Binance"] = binance_funding_current(binance_sym)
        print(f"  Binance: {venues['Binance']*100:.4f}% ({venues['Binance']*10000:+.2f} bps)")
    except Exception as e:
        print(f"  Binance: ERRO ({e})")

    try:
        venues["Bybit"] = bybit_funding_current(bybit_sym)
        print(f"  Bybit:   {venues['Bybit']*100:.4f}% ({venues['Bybit']*10000:+.2f} bps)")
    except Exception as e:
        print(f"  Bybit:   ERRO ({e})")

    try:
        venues["OKX"] = okx_funding_current(okx_sym)
        print(f"  OKX:     {venues['OKX']*100:.4f}% ({venues['OKX']*10000:+.2f} bps)")
    except Exception as e:
        print(f"  OKX:     ERRO ({e})")

    if len(venues) < 2:
        print("  Dados insuficientes.")
        return None

    # Current spread
    venue_names = list(venues.keys())
    print(f"\n  Spreads atuais (bps/8h):")
    for i in range(len(venue_names)):
        for j in range(i+1, len(venue_names)):
            v1, v2 = venue_names[i], venue_names[j]
            spread = (venues[v1] - venues[v2]) * 10000
            print(f"    {v1} - {v2}: {spread:+.2f} bps/8h")

    # Step 2: Fetch historical funding for simulation
    print(f"\n[2/3] Fetching historical funding rates ({days}d)...")
    binance_hist = []
    okx_hist = []
    try:
        binance_hist = binance_funding_history(binance_sym, limit=days * 3)
        print(f"  Binance: {len(binance_hist)} periods")
    except Exception as e:
        print(f"  Binance history: ERRO ({e})")

    try:
        okx_hist = okx_funding_history(okx_sym, limit=days * 3)
        print(f"  OKX:     {len(okx_hist)} periods")
    except Exception as e:
        print(f"  OKX history: ERRO ({e})")

    # Step 3: Simulate P&L
    print(f"\n[3/3] Simulating cross-venue funding arb P&L...")

    # Trading costs (taker fees, both venues, entry + exit)
    # Binance perp taker: 0.04%, Bybit: 0.055%, OKX: 0.05%
    # Round trip = 2 * (entry + exit) = 4 * taker_fee
    COST_BPS = {
        "Binance": 4 * 0.4,   # 1.6 bps round-trip
        "Bybit": 4 * 0.55,    # 2.2 bps round-trip
        "OKX": 4 * 0.5,       # 2.0 bps round-trip
    }

    results = []

    # Binance vs OKX historical simulation
    if binance_hist and okx_hist:
        # Align by time (both are 8h, but timestamps may differ slightly)
        # Simple approach: pair by index (both should be ~3 per day)
        n = min(len(binance_hist), len(okx_hist))
        binance_rates = [binance_hist[i]["rate"] for i in range(n)]
        okx_rates = [okx_hist[i]["rate"] for i in range(n)]

        # Strategy: long perp on venue with lower funding, short on higher
        # P&L per 8h = |funding_diff| * notional (you always collect the spread)
        pnl_per_period_bps = []
        for i in range(n):
            spread_bps = abs(binance_rates[i] - okx_rates[i]) * 10000
            pnl_per_period_bps.append(spread_bps)

        # Net after costs (one round-trip per rebalance, assume daily rebalance = 3 periods)
        total_cost_bps = COST_BPS["Binance"] + COST_BPS["OKX"]
        periods_per_rebalance = 3  # 24h
        n_rebalances = n // periods_per_rebalance

        # Group P&L by rebalance periods
        daily_pnl_bps = []
        for i in range(0, n - periods_per_rebalance, periods_per_rebalance):
            period_pnl = sum(pnl_per_period_bps[i:i+periods_per_rebalance])
            net_pnl = period_pnl - total_cost_bps
            daily_pnl_bps.append(net_pnl)

        if daily_pnl_bps:
            lo, mean, hi = bootstrap_ci(daily_pnl_bps)
            wins = sum(1 for p in daily_pnl_bps if p > 0)
            win_rate = wins / len(daily_pnl_bps) * 100

            # Annualized return (365 rebalances)
            annual_bps = mean * 365
            annual_pct = annual_bps / 100

            print(f"\n  Binance vs OKX ({len(daily_pnl_bps)} rebalances):")
            print(f"    P&L médio/dia: {mean:+.2f} bps (IC95%: {lo:+.2f} - {hi:+.2f})")
            print(f"    Win rate: {win_rate:.1f}%")
            print(f"    Custo round-trip: {total_cost_bps:.1f} bps")
            print(f"    P&L anualizado: {annual_bps:+.0f} bps ({annual_pct:+.2f}%)")

            # Also compute static strategy: always long Binance, short OKX
            static_pnl_bps = []
            for i in range(n):
                spread_bps = (binance_rates[i] - okx_rates[i]) * 10000
                # If Binance funding > OKX: short Binance (receive), long OKX (pay) => collect diff
                # If Binance funding < OKX: long Binance (receive from short side), short OKX
                # Actually: long perp pays funding when rate > 0, receives when rate < 0
                # Short perp receives funding when rate > 0, pays when rate < 0
                # Strategy: short venue with higher funding, long venue with lower funding
                # P&L = -(higher_rate) + (lower_rate) = -(higher - lower) = lower - higher
                # Wait, let me think again:
                # If venue A has funding_rate_A, venue B has funding_rate_B
                # Long on A pays rate_A, short on B receives rate_B
                # P&L = -rate_A + rate_B = rate_B - rate_A
                # We want to long the venue with lower rate, short the one with higher rate
                # If rate_A > rate_B: short A (receive rate_A), long B (pay rate_B) => P&L = rate_A - rate_B > 0
                # If rate_A < rate_B: long A (pay rate_A), short B (receive rate_B) => P&L = rate_B - rate_A > 0
                # So P&L = |rate_A - rate_B| always positive (before costs)
                pass  # Already handled above

            results.append({
                "pair": "Binance vs OKX",
                "mean_daily_bps": mean,
                "ci_lo": lo,
                "ci_hi": hi,
                "win_rate": win_rate,
                "annual_bps": annual_bps,
                "n": len(daily_pnl_bps),
                "cost_bps": total_cost_bps,
            })

    # Current spread analysis (all venue pairs)
    print(f"\n  Spreads atuais (o que capturaria agora):")
    for i in range(len(venue_names)):
        for j in range(i+1, len(venue_names)):
            v1, v2 = venue_names[i], venue_names[j]
            spread_bps = abs(venues[v1] - venues[v2]) * 10000
            cost = COST_BPS.get(v1, 2.0) + COST_BPS.get(v2, 2.0)
            net_per_8h = spread_bps - cost
            daily_net = net_per_8h * 3  # 3 periods per day
            annual = daily_net * 365
            print(f"    {v1} vs {v2}: spread={spread_bps:.2f} bps/8h, "
                  f"cost={cost:.1f} bps, net/8h={net_per_8h:+.2f}, "
                  f"net/day={daily_net:+.2f}, annual={annual:+.0f} bps")
            results.append({
                "pair": f"{v1} vs {v2}",
                "current_spread_bps": spread_bps,
                "cost_bps": cost,
                "net_per_8h_bps": net_per_8h,
                "daily_net_bps": daily_net,
                "annual_bps": annual,
            })

    # Verdict
    print(f"\n{'='*80}")
    print(f"VEREDITO — D26 Cross-Venue Funding Arb {asset}")
    print(f"{'='*80}")

    historical = [r for r in results if "mean_daily_bps" in r]
    current = [r for r in results if "current_spread_bps" in r]

    if historical:
        h = historical[0]
        if h["mean_daily_bps"] > 0 and h["win_rate"] > 60:
            print(f"  EDGE HISTÓRICO: {h['pair']}")
            print(f"    P&L médio: {h['mean_daily_bps']:+.2f} bps/dia (IC95%: {h['ci_lo']:+.2f} - {h['ci_hi']:+.2f})")
            print(f"    Win rate: {h['win_rate']:.1f}% | N={h['n']} rebalances")
            print(f"    Anualizado: {h['annual_bps']:+.0f} bps ({h['annual_bps']/100:+.2f}%)")
            print(f"    >>> EDGE DETECTADO (histórico). Validar com execução real.")
        else:
            print(f"  SEM EDGE HISTÓRICO: {h['pair']}")
            print(f"    P&L médio: {h['mean_daily_bps']:+.2f} bps/dia (IC95%: {h['ci_lo']:+.2f} - {h['ci_hi']:+.2f})")
            print(f"    Win rate: {h['win_rate']:.1f}%")
            if h["mean_daily_bps"] <= 0:
                print(f"    Spread de funding não supera custos consistentemente.")
            else:
                print(f"    Spread positivo mas win rate baixo ({h['win_rate']:.0f}%) — inconsistente.")

    if current:
        profitable_current = [r for r in current if r.get("net_per_8h_bps", 0) > 0]
        if profitable_current:
            print(f"\n  Spreads atuais profitáveis:")
            for r in profitable_current:
                print(f"    {r['pair']}: {r['net_per_8h_bps']:+.2f} bps/8h, "
                      f"annual={r['annual_bps']:+.0f} bps")
        else:
            print(f"\n  Nenhum spread atual supera custos ({sum(r.get('cost_bps',0) for r in current)/len(current):.1f} bps).")

    print(f"\n  Nota: Funding arb requer rebalanceamento quando spread inverte.")
    print(f"  Custo de rebalanceamento: ~{COST_BPS['Binance'] + COST_BPS['OKX']:.1f} bps por ciclo.")
    print(f"  Edge real depende da frequência de rebalanceamento necessária.")

    return results


def main():
    ap = argparse.ArgumentParser(description="D26 — Cross-Venue Funding Rate Arb")
    ap.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL"], help="Asset to scan")
    ap.add_argument("--days", type=int, default=30, help="Days of funding history")
    args = ap.parse_args()

    print(f"D26 — Cross-Venue Funding Rate Arbitrage")
    print(f"Asset: {args.asset} | History: {args.days}d")

    for asset in [args.asset] if args.asset != "BTC" else ["BTC", "ETH", "SOL"]:
        analyze_funding_arb(asset, args.days)


if __name__ == "__main__":
    main()
