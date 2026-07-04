"""
D24 — Perpetual Basis Arbitrage Scan

Hypothesis: When perpetual futures trade at a premium/discount to spot,
there's a market-neutral arbitrage opportunity:
  - If perp > spot (positive basis): short perp + long spot, collect funding
  - If perp < spot (negative basis): long perp + short spot, pay funding but capture basis

The key insight is that funding rates on perps are designed to pull price toward spot.
When basis is large, funding payments in the favorable direction can exceed the
cost of carrying the position.

Data sources (all free, no auth):
- Binance: spot price (api.binance.com) + perp price (fapi.binance.com) + funding rate
- Bybit: spot + perp + funding (api.bybit.com)
- OKX: spot + perp + funding (www.okx.com)

Methodology:
1. Fetch current spot and perp prices across venues
2. Calculate basis = (perp - spot) / spot * 100
3. Fetch current funding rates (8h cycle)
4. Calculate net carry: basis + expected funding over holding period
5. Compare against costs (trading fees + slippage)
6. Report opportunities with IC95% via historical funding rate distribution

Usage:
  python3 perp_basis_arb_scan.py
  python3 perp_basis_arb_scan.py --asset BTC --days 30
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

def binance_spot_price(symbol="BTCUSDT"):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data = fetch_json(url)
    return float(data.get("price", 0))


def binance_perp_price(symbol="BTCUSDT"):
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    data = fetch_json(url)
    return float(data.get("price", 0))


def binance_funding_rate(symbol="BTCUSDT"):
    """Current funding rate (most recent)."""
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    data = fetch_json(url)
    return {
        "funding_rate": float(data.get("lastFundingRate", 0)),
        "mark_price": float(data.get("markPrice", 0)),
        "index_price": float(data.get("indexPrice", 0)),
    }


def binance_funding_history(symbol="BTCUSDT", limit=90):
    """Historical funding rates (each is 8h, so 90 = 30 days)."""
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

def bybit_spot_price(symbol="BTCUSDT"):
    url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}"
    data = fetch_json(url)
    result = data.get("result", {}).get("list", [])
    if result:
        return float(result[0].get("lastPrice", 0))
    return 0.0


def bybit_perp_price(symbol="BTCUSDT"):
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    data = fetch_json(url)
    result = data.get("result", {}).get("list", [])
    if result:
        return float(result[0].get("lastPrice", 0))
    return 0.0


def bybit_funding_rate(symbol="BTCUSDT"):
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    data = fetch_json(url)
    result = data.get("result", {}).get("list", [])
    if result:
        return float(result[0].get("fundingRate", 0))
    return 0.0


# ============ OKX ============

def okx_spot_price(symbol="BTC-USDT"):
    url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
    data = fetch_json(url)
    result = data.get("data", [])
    if result:
        return float(result[0].get("last", 0))
    return 0.0


def okx_perp_price(symbol="BTC-USDT-SWAP"):
    url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
    data = fetch_json(url)
    result = data.get("data", [])
    if result:
        return float(result[0].get("last", 0))
    return 0.0


def okx_funding_rate(symbol="BTC-USDT-SWAP"):
    url = f"https://www.okx.com/api/v5/public/funding-rate?instId={symbol}"
    data = fetch_json(url)
    result = data.get("data", [])
    if result:
        return float(result[0].get("fundingRate", 0))
    return 0.0


def analyze_venue(venue_name, spot_price, perp_price, funding_rate, funding_history=None):
    """Analyze basis arb opportunity for a single venue."""
    if spot_price <= 0 or perp_price <= 0:
        print(f"  {venue_name}: dados insuficientes (spot={spot_price}, perp={perp_price})")
        return None

    basis_pct = (perp_price - spot_price) / spot_price * 100
    basis_bps = basis_pct * 100  # in basis points

    # Funding rate is per 8h. Annualized = rate * 3 * 365
    funding_8h = funding_rate
    funding_annual = funding_rate * 3 * 365 * 100  # in %

    # If basis > 0 (perp premium): short perp, long spot
    #   -> you RECEIVE funding when funding > 0 (longs pay shorts)
    #   -> net carry = funding received - basis cost (you short perp above spot)
    # If basis < 0 (perp discount): long perp, short spot
    #   -> you PAY funding when funding > 0
    #   -> net carry = basis discount - funding paid

    # Trading costs (taker fees, both legs):
    # Binance: spot 0.1% + perp 0.04% = 0.14% round-trip entry, same exit = 0.28% total
    # Bybit: spot 0.1% + perp 0.055% = 0.155% entry, same exit = 0.31% total
    # OKX: spot 0.1% + perp 0.05% = 0.15% entry, same exit = 0.30% total
    COST_ENTRY_BPS = {
        "Binance": 14,
        "Bybit": 15.5,
        "OKX": 15,
    }.get(venue_name, 15)
    COST_TOTAL_BPS = COST_ENTRY_BPS * 2  # entry + exit

    # Net opportunity (basis points):
    # If basis > 0: short perp at premium, collect funding
    # Gross = basis_bps + (funding_8h * 10000) per 8h period
    # Net = gross - total costs
    funding_bps_8h = funding_8h * 10000

    if basis_bps > 0:
        # Short perp, long spot
        direction = "SHORT perp / LONG spot"
        gross_carry_per_8h = basis_bps + funding_bps_8h  # collect basis + receive funding
    else:
        # Long perp, short spot
        direction = "LONG perp / SHORT spot"
        gross_carry_per_8h = abs(basis_bps) - funding_bps_8h  # capture discount but pay funding

    # Net after costs (assume hold 3 funding periods = 24h)
    hold_periods = 3  # 24h
    gross_24h = gross_carry_per_8h * hold_periods  # simplified: same funding each period
    net_24h = gross_24h - COST_TOTAL_BPS

    # Historical funding analysis
    funding_stats = {}
    if funding_history and len(funding_history) > 5:
        rates_bps = [f["rate"] * 10000 for f in funding_history]
        funding_stats = {
            "mean_bps": sum(rates_bps) / len(rates_bps),
            "median_bps": sorted(rates_bps)[len(rates_bps) // 2],
            "positive_pct": sum(1 for r in rates_bps if r > 0) / len(rates_bps) * 100,
            "n": len(rates_bps),
        }

    print(f"  {venue_name}:")
    print(f"    Spot: ${spot_price:,.2f} | Perp: ${perp_price:,.2f}")
    print(f"    Basis: {basis_bps:+.2f} bps ({basis_pct:+.4f}%)")
    print(f"    Funding (8h): {funding_8h*100:.4f}% ({funding_bps_8h:+.2f} bps)")
    print(f"    Funding annualized: {funding_annual:.2f}%")
    print(f"    Direction: {direction}")
    print(f"    Gross carry/8h: {gross_carry_per_8h:+.2f} bps")
    print(f"    Gross 24h (3 periods): {gross_24h:+.2f} bps")
    print(f"    Costs (round-trip): {COST_TOTAL_BPS:.1f} bps")
    print(f"    NET 24h: {net_24h:+.2f} bps")
    if funding_stats:
        print(f"    Funding history ({funding_stats['n']} periods): "
              f"mean={funding_stats['mean_bps']:+.2f} bps, "
              f"positive {funding_stats['positive_pct']:.0f}% of time")

    return {
        "venue": venue_name,
        "spot": spot_price,
        "perp": perp_price,
        "basis_bps": basis_bps,
        "funding_8h": funding_8h,
        "funding_bps_8h": funding_bps_8h,
        "direction": direction,
        "gross_24h": gross_24h,
        "net_24h": net_24h,
        "cost_bps": COST_TOTAL_BPS,
        "funding_stats": funding_stats,
    }


def main():
    ap = argparse.ArgumentParser(description="D24 — Perpetual Basis Arbitrage Scan")
    ap.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL"], help="Asset to scan")
    ap.add_argument("--days", type=int, default=30, help="Days of funding history")
    args = ap.parse_args()

    asset = args.asset
    binance_sym = f"{asset}USDT"
    bybit_sym = f"{asset}USDT"
    okx_spot_sym = f"{asset}-USDT"
    okx_perp_sym = f"{asset}-USDT-SWAP"

    print(f"{'='*80}")
    print(f"D24 — Perpetual Basis Arbitrage Scan | {asset} | {args.days}d funding history")
    print(f"{'='*80}")

    # Fetch all data
    print(f"\n[1/3] Fetching prices and funding rates...")

    results = []

    # Binance
    try:
        bn_spot = binance_spot_price(binance_sym)
        bn_perp = binance_perp_price(binance_sym)
        bn_fund = binance_funding_rate(binance_sym)
        bn_fund_hist = binance_funding_history(binance_sym, limit=args.days * 3)
        r = analyze_venue("Binance", bn_spot, bn_perp, bn_fund["funding_rate"], bn_fund_hist)
        if r:
            results.append(r)
    except Exception as e:
        print(f"  Binance: ERRO ({e})")

    # Bybit
    try:
        bb_spot = bybit_spot_price(bybit_sym)
        bb_perp = bybit_perp_price(bybit_sym)
        bb_fund = bybit_funding_rate(bybit_sym)
        r = analyze_venue("Bybit", bb_spot, bb_perp, bb_fund, None)
        if r:
            results.append(r)
    except Exception as e:
        print(f"  Bybit: ERRO ({e})")

    # OKX
    try:
        ok_spot = okx_spot_price(okx_spot_sym)
        ok_perp = okx_perp_price(okx_perp_sym)
        ok_fund = okx_funding_rate(okx_perp_sym)
        r = analyze_venue("OKX", ok_spot, ok_perp, ok_fund, None)
        if r:
            results.append(r)
    except Exception as e:
        print(f"  OKX: ERRO ({e})")

    # Cross-venue comparison
    print(f"\n[2/3] Cross-venue basis comparison...")
    if len(results) >= 2:
        for r in results:
            print(f"  {r['venue']:>8}: basis={r['basis_bps']:+.2f} bps | net 24h={r['net_24h']:+.2f} bps | funding={r['funding_bps_8h']:+.2f} bps/8h")

        # Best opportunity
        best = max(results, key=lambda r: r["net_24h"])
        print(f"\n  Melhor oportunidade: {best['venue']} (net 24h = {best['net_24h']:+.2f} bps)")
    else:
        print("  Dados insuficientes para comparação cross-venue")

    # Verdict
    print(f"\n[3/3] Verdict...")
    print(f"\n{'='*80}")
    print(f"VEREDITO — D24 Perp Basis Arb {asset}")
    print(f"{'='*80}")

    if not results:
        print("  FALHA: não foi possível obter dados de nenhuma venue.")
        return

    profitable = [r for r in results if r["net_24h"] > 0]
    if profitable:
        print(f"  {len(profitable)} venue(s) com net 24h positivo:")
        for r in profitable:
            print(f"    {r['venue']}: {r['net_24h']:+.2f} bps/24h | {r['direction']}")
            if r["funding_stats"]:
                fs = r["funding_stats"]
                print(f"      Funding histórico: mean={fs['mean_bps']:+.2f} bps, positivo {fs['positive_pct']:.0f}% do tempo")

        best = max(profitable, key=lambda r: r["net_24h"])
        print(f"\n  >>> EDGE DETECTADO em {best['venue']}: {best['net_24h']:+.2f} bps/24h")
        print(f"  >>> Direção: {best['direction']}")
        print(f"  >>> CUIDADO: este é um snapshot point-in-time.")
        print(f"  >>> Para validação: coletar série histórica de basis+funding,")
        print(f"  >>> simular P&L diário, e verificar se net > 0 consistentemente.")
    else:
        print(f"  SEM EDGE: nenhuma venue mostra net 24h positivo após custos.")
        print(f"  Custos round-trip: ~{results[0]['cost_bps']:.0f} bps (taker fees both legs)")
        print(f"  Basis atual muito pequeno para superar custos de entrada+saída.")
        print(f"\n  Para ser profitável precisaria:")
        print(f"    - Basis > {results[0]['cost_bps']:.0f} bps (raro em condições normais)")
        print(f"    - Ou maker fees (reduz custo para ~{results[0]['cost_bps']*0.3:.0f} bps)")
        print(f"    - Ou segurar por múltiplos períodos de funding (3+ dias)")
        print(f"    - Ou capturar basis durante eventos de stress (liquidation cascades)")

    print(f"\n  Dataset: {len(results)} venues | {asset}")
    print(f"  Nota: Basis arb é mais viável durante alta volatilidade/stress.")
    print(f"  Este scan mede condições normais — edge pode aparecer em momentos específicos.")


if __name__ == "__main__":
    main()
