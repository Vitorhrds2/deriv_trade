"""
D23 — Crypto Volatility Risk Premium (VRP) Scan

Hypothesis: Implied Volatility (IV) on Deribit BTC/ETH options is systematically
higher than Realized Volatility (RV) of the underlying. If IV > RV consistently,
selling options (delta-hedged or naked) captures the premium.

This is a well-documented edge in traditional finance (equity index options).
The question is whether it exists in crypto, and if so, how large it is after
fees (trading fees + bid-ask spread + funding for hedging).

Data sources (all free, no auth required):
- Deribit public API: https://www.deribit.com/api/v2/public/get_book_summary_by_currency
  Returns IV for each option, plus mark price, underlying price, etc.
- Binance public API: historical klines for realized vol calculation

Methodology:
1. Fetch current IV from Deribit for BTC and ETH options (various expiries/deltas)
2. Calculate RV from Binance historical klines (1h candles, 30-day window)
3. Compare IV vs RV with bootstrap CI
4. Account for costs: Deribit taker fee 0.03% + bid-ask spread (~0.5 IV points)
5. Report VRP = IV - RV in annualized vol points, with IC95%

Usage:
  python3 volatility_risk_premium_scan.py
  python3 volatility_risk_premium_scan.py --asset ETH --days 30
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
    def bootstrap_ci(values, n_boot=2000, ci=0.95, seed=42):
        if not values:
            return (0.0, 0.0, 0.0)
        import random
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


DERIBIT_API = "https://www.deribit.com/api/v2/public"
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_deribit_iv(asset="BTC"):
    """Fetch IV for all options on Deribit for given asset.
    Returns list of dicts: {expiry, type, strike, iv, mark_price, underlying, delta}
    """
    currency = asset.lower()
    url = f"{DERIBIT_API}/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    result = data.get("result", [])
    if not result:
        print(f"  ERRO: sem dados do Deribit para {asset}")
        return []

    options = []
    for item in result:
        iv = item.get("mark_iv")
        if iv is None or iv <= 0:
            continue
        instrument = item.get("instrument_name", "")
        # Parse instrument name: BTC-28JUN25-65000-C
        parts = instrument.split("-")
        if len(parts) < 4:
            continue
        expiry_str = parts[1]
        strike = float(parts[2]) if parts[2].replace(".", "").isdigit() else 0
        opt_type = parts[3].upper()  # C or P

        options.append({
            "instrument": instrument,
            "expiry": expiry_str,
            "type": opt_type,
            "strike": strike,
            "iv": float(iv),
            "mark_price": float(item.get("mark_price", 0)),
            "underlying_price": float(item.get("underlying_price", 0)),
            "volume": float(item.get("volume", 0)),
            "open_interest": float(item.get("open_interest", 0)),
        })
    return options


def fetch_binance_klines(symbol="BTCUSDT", interval="1h", limit=720):
    """Fetch historical klines from Binance Futures for RV calculation.
    Default: 720 x 1h candles = 30 days.
    """
    url = f"{BINANCE_FAPI}/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = fetch_json(url)
    candles = []
    for k in data:
        # [open_time, open, high, low, close, volume, close_time, ...]
        candles.append({
            "time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return candles


def calc_realized_vol(candles, interval_minutes=60):
    """Calculate annualized realized volatility from log returns.
    Uses close-to-close returns (standard method).
    Annualization factor: 365 * 24 * 60 / interval_minutes (crypto trades 24/7)
    """
    if len(candles) < 10:
        return 0.0, []
    log_returns = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["close"]
        curr_close = candles[i]["close"]
        if prev_close > 0:
            lr = math.log(curr_close / prev_close)
            log_returns.append(lr)

    if not log_returns:
        return 0.0, []

    # Daily RV from intraday returns: RV_daily = sum(r^2) * (365 / N_days)
    # But more standard: std of log returns * sqrt(annualization_factor)
    n = len(log_returns)
    mean_lr = sum(log_returns) / n
    variance = sum((r - mean_lr) ** 2 for r in log_returns) / (n - 1)
    std = math.sqrt(variance)

    # Annualize: crypto = 365 days * 24h * (60 / interval_minutes) periods per year
    periods_per_year = 365 * 24 * 60 / interval_minutes
    rv_annual = std * math.sqrt(periods_per_year) * 100  # in % annualized

    return rv_annual, log_returns


def calc_rv_rolling(log_returns, window=24, interval_minutes=60):
    """Rolling 24h realized vol (annualized) for each period.
    Returns list of RV values for bootstrap CI.
    """
    periods_per_year = 365 * 24 * 60 / interval_minutes
    rvs = []
    for i in range(window, len(log_returns)):
        chunk = log_returns[i - window:i]
        n = len(chunk)
        mean_c = sum(chunk) / n
        var = sum((r - mean_c) ** 2 for r in chunk) / (n - 1)
        rv = math.sqrt(var) * math.sqrt(periods_per_year) * 100
        rvs.append(rv)
    return rvs


def analyze_vrp(asset, days, interval="1h"):
    print(f"\n{'='*80}")
    print(f"D23 — Crypto Volatility Risk Premium Scan | {asset} | {days}d RV window")
    print(f"{'='*80}")

    # 1. Fetch Deribit IV
    print(f"\n[1/4] Fetching {asset} options IV from Deribit...")
    options = fetch_deribit_iv(asset)
    if not options:
        print("  FALHA: sem dados do Deribit. Abortando.")
        return None
    print(f"  OK: {len(options)} opções com IV válido")

    # Group by expiry and type
    by_expiry = {}
    for opt in options:
        key = opt["expiry"]
        by_expiry.setdefault(key, []).append(opt)

    # Filter to liquid options (volume > 0 or OI > 10)
    liquid = [o for o in options if o["volume"] > 0 or o["open_interest"] > 10]
    print(f"  Líquidas (vol>0 ou OI>10): {len(liquid)}")

    # ATM options (strike closest to underlying)
    underlying = options[0]["underlying_price"] if options else 0
    print(f"  Underlying ({asset}): ${underlying:,.2f}")

    atm_options = []
    for expiry, opts in sorted(by_expiry.items()):
        calls = [o for o in opts if o["type"] == "C"]
        puts = [o for o in opts if o["type"] == "P"]
        # Find ATM call and put
        if calls:
            atm_call = min(calls, key=lambda o: abs(o["strike"] - underlying))
            atm_options.append(atm_call)
        if puts:
            atm_put = min(puts, key=lambda o: abs(o["strike"] - underlying))
            atm_options.append(atm_put)

    print(f"  ATM options (por expiry): {len(atm_options)}")

    # All IVs summary
    all_ivs = [o["iv"] for o in liquid]
    atm_ivs = [o["iv"] for o in atm_options]

    if all_ivs:
        avg_iv_all = sum(all_ivs) / len(all_ivs)
        avg_iv_atm = sum(atm_ivs) / len(atm_ivs) if atm_ivs else 0
        print(f"  IV médio (todas): {avg_iv_all:.2f}%")
        print(f"  IV médio (ATM): {avg_iv_atm:.2f}%")

    # 2. Fetch Binance klines for RV
    symbol = f"{asset}USDT"
    limit = min(days * 24 if interval == "1h" else days * 24 * 4, 1500)
    print(f"\n[2/4] Fetching {symbol} klines from Binance ({limit} x {interval})...")
    candles = fetch_binance_klines(symbol, interval, limit)
    if not candles:
        print("  FALHA: sem dados do Binance. Abortando.")
        return None
    print(f"  OK: {len(candles)} velas | {datetime.fromtimestamp(candles[0]['time']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} -> {datetime.fromtimestamp(candles[-1]['time']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}")

    # 3. Calculate RV
    print(f"\n[3/4] Calculating realized volatility...")
    interval_min = 60 if interval == "1h" else 15
    rv_full, log_returns = calc_realized_vol(candles, interval_min)
    print(f"  RV (full {len(candles)} candles): {rv_full:.2f}% annualized")

    # Rolling 24h RV for bootstrap CI
    rvs_24h = calc_rv_rolling(log_returns, window=24, interval_minutes=interval_min)
    if rvs_24h:
        rv_lo, rv_mean, rv_hi = bootstrap_ci(rvs_24h, n_boot=3000)
        print(f"  RV (rolling 24h, {len(rvs_24h)} windows): {rv_mean:.2f}% IC95%[{rv_lo:.2f}%, {rv_hi:.2f}%]")
    else:
        rv_lo, rv_mean, rv_hi = rv_full, rv_full, rv_full

    # 4. VRP Analysis
    print(f"\n[4/4] Volatility Risk Premium (IV - RV) analysis...")
    print(f"\n  {'Expiry':<12} {'Type':<5} {'Strike':>10} {'IV%':>8} {'VRP%':>8} {'VRP_net%':>10} {'OI':>8} {'Vol':>8}")
    print(f"  {'-'*80}")

    # Deribit costs: taker fee 0.03% of underlying, bid-ask spread ~0.5 vol points
    DERIBIT_TAKER_FEE_PCT = 0.03  # % of notional
    BID_ASK_SPREAD_VOL = 0.5  # vol points (conservative)
    # For delta-hedged: also funding cost for perp hedge (~0.01% per 8h = 0.03%/day)
    HEDGE_COST_VOL_PER_DAY = 0.1  # approx 0.1 vol points per day of holding

    vrp_results = []
    for opt in sorted(atm_options, key=lambda o: (o["expiry"], o["type"])):
        vrp = opt["iv"] - rv_mean
        # Net VRP: subtract bid-ask spread (you sell at bid, buy at ask)
        vrp_net = vrp - BID_ASK_SPREAD_VOL
        vrp_results.append({
            "expiry": opt["expiry"],
            "type": opt["type"],
            "strike": opt["strike"],
            "iv": opt["iv"],
            "vrp": vrp,
            "vrp_net": vrp_net,
            "oi": opt["open_interest"],
            "vol": opt["volume"],
        })
        print(f"  {opt['expiry']:<12} {opt['type']:<5} {opt['strike']:>10.0f} {opt['iv']:>8.2f} {vrp:>8.2f} {vrp_net:>10.2f} {opt['open_interest']:>8.0f} {opt['volume']:>8.0f}")

    # Summary stats
    if vrp_results:
        vrp_values = [v["vrp"] for v in vrp_results]
        vrp_net_values = [v["vrp_net"] for v in vrp_results]
        vrp_lo, vrp_mean, vrp_hi = bootstrap_ci(vrp_values, n_boot=3000)
        vrp_net_lo, vrp_net_mean, vrp_net_hi = bootstrap_ci(vrp_net_values, n_boot=3000)

        print(f"\n{'='*80}")
        print(f"VEREDITO — D23 VRP {asset}")
        print(f"{'='*80}")
        print(f"  IV ATM médio: {sum(atm_ivs)/len(atm_ivs):.2f}%")
        print(f"  RV 30d: {rv_mean:.2f}% IC95%[{rv_lo:.2f}%, {rv_hi:.2f}%]")
        print(f"  VRP bruto (IV - RV): {vrp_mean:.2f} vol pts IC95%[{vrp_lo:.2f}, {vrp_hi:.2f}]")
        print(f"  VRP net (após bid-ask 0.5vp): {vrp_net_mean:.2f} vol pts IC95%[{vrp_net_lo:.2f}, {vrp_net_hi:.2f}]")
        print(f"  Custos: Deribit taker 0.03% + bid-ask ~0.5 vol pts")

        if vrp_net_lo > 0:
            print(f"\n  >>> EDGE DETECTADO: VRP net > 0 com IC95% inteiro positivo.")
            print(f"  >>> Selling {asset} ATM options captura ~{vrp_net_mean:.1f} vol pts de premium.")
            print(f"  >>> Próximo: backtest histórico de short straddle delta-hedged.")
        elif vrp_net_mean > 0:
            print(f"\n  >>> SINAL FRACO: VRP net médio positivo ({vrp_net_mean:.2f}) mas IC cruza zero.")
            print(f"  >>> Pode haver edge mas não é estatisticamente significante com esta amostra.")
        else:
            print(f"\n  >>> SEM EDGE: VRP net <= 0. IV não supera RV + custos.")

        print(f"\n  Dataset: {len(candles)} velas {interval} Binance + {len(options)} opções Deribit")
        print(f"  Nota: VRP varia ao longo do tempo. Este é um snapshot point-in-time.")
        print(f"  Para validação: coletar série histórica de IV (Deribit) vs RV e testar persistência.")

        return {
            "asset": asset,
            "iv_atm": sum(atm_ivs) / len(atm_ivs),
            "rv": rv_mean,
            "rv_ci": (rv_lo, rv_hi),
            "vrp": vrp_mean,
            "vrp_ci": (vrp_lo, vrp_hi),
            "vrp_net": vrp_net_mean,
            "vrp_net_ci": (vrp_net_lo, vrp_net_hi),
            "n_options": len(options),
            "n_candles": len(candles),
        }
    return None


def main():
    ap = argparse.ArgumentParser(description="D23 — Crypto Volatility Risk Premium Scan")
    ap.add_argument("--asset", default="BTC", choices=["BTC", "ETH"], help="Asset to analyze")
    ap.add_argument("--days", type=int, default=30, help="Days of historical data for RV")
    ap.add_argument("--interval", default="1h", choices=["1h", "15m"], help="Kline interval for RV")
    args = ap.parse_args()

    print("D23 — Crypto Volatility Risk Premium Scan")
    print(f"Asset: {args.asset} | RV window: {args.days}d | Interval: {args.interval}")
    print()

    results = []
    for asset in (["BTC", "ETH"] if args.asset == "BTC" else [args.asset]):
        r = analyze_vrp(asset, args.days, args.interval)
        if r:
            results.append(r)

    if results:
        print(f"\n{'='*80}")
        print("RESUMO GERAL")
        print(f"{'='*80}")
        for r in results:
            print(f"  {r['asset']}: IV={r['iv_atm']:.1f}% RV={r['rv']:.1f}% VRP={r['vrp']:.1f}vp net={r['vrp_net']:.1f}vp")


if __name__ == "__main__":
    main()
