"""
D22 — CEX liquidation cascade scan (historical, multi-day validation).

Hipotese: grandes movimentos de preco em curto prazo (proxy para liquidation cascades)
predizem reversoes. Quando BTC cai >X% em 1-5 minutos, tende a reverter (bounce).
Quando sobe >X% rapidamente, tende a cair (pullback).

Mecanismo:
- Liquidation cascade: preco cai -> longs liquidados -> selling pressure -> mais queda
- Apos cascade exaustivo, preco tende a reverter (oversold)
- Simetrico para short squeeze

Data source (gratuito, publico, sem API key):
- Binance Futures REST API: BTCUSDT 1m klines (velas de 1 minuto)
- Paginacao via startTime/endTime (1500 por request, ~7 dias = ~29 requests)

Teste:
1. Fetch N dias de velas 1m (paginado)
2. Split IS/OOS (70/30 temporal)
3. Detectar velas com |retorno| > threshold (1σ, 2σ, 3σ acima da media)
4. Medir retorno nos 1m, 5m, 15m, 30m, 60m seguintes
5. Veredito: IC95% no retorno medio, IS vs OOS, fee-adjusted
"""
import argparse
import json
import sys
import math
import time as _time
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from stats_utils import bootstrap_ci, wilson_ci
except ImportError:
    print("ERRO: stats_utils.py nao encontrado. Execute do diretorio trading-engine/")
    sys.exit(1)

TAKER_FEE_PCT = 0.04  # Binance Futures taker fee per side (%), 0.08% round trip


def fetch_klines_page(symbol="BTCUSDT", interval="1m", limit=1500, start_time_ms=None, end_time_ms=None):
    """Fetch one page of kline data from Binance Futures REST API (free, no auth)."""
    params = f"symbol={symbol}&interval={interval}&limit={limit}"
    if start_time_ms:
        params += f"&startTime={start_time_ms}"
    if end_time_ms:
        params += f"&endTime={end_time_ms}"
    url = f"https://fapi.binance.com/fapi/v1/klines?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    candles = []
    for k in data:
        candles.append({
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": k[6],
            "time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
        })
    return candles


def fetch_klines_multi(symbol="BTCUSDT", interval="1m", days=7, page_limit=1500):
    """Fetch multiple days of 1m candles via pagination."""
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ms = now_ms - days * 24 * 60 * 60 * 1000
    all_candles = []
    cursor = start_ms
    requests_made = 0

    while cursor < now_ms:
        batch = fetch_klines_page(symbol, interval, page_limit, start_time_ms=cursor)
        requests_made += 1
        if not batch:
            break
        all_candles.extend(batch)
        last_open = batch[-1]["open_time"]
        cursor = last_open + 60_000  # +1 minute
        if requests_made % 10 == 0:
            elapsed_days = (cursor - start_ms) / (24 * 60 * 60 * 1000)
            print(f"    ... {len(all_candles)} velas, ~{elapsed_days:.1f} dias coletados ({requests_made} requests)")
        if len(batch) < page_limit:
            break
        _time.sleep(0.3)  # rate limit courtesy

    # Deduplicate by open_time
    seen = set()
    unique = []
    for c in all_candles:
        if c["open_time"] not in seen:
            seen.add(c["open_time"])
            unique.append(c)
    unique.sort(key=lambda c: c["open_time"])
    return unique


def compute_returns(candles):
    """Compute 1-minute returns for each candle."""
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["close"]
        cur_close = candles[i]["close"]
        if prev_close > 0:
            candles[i]["return_1m"] = (cur_close - prev_close) / prev_close * 100
        else:
            candles[i]["return_1m"] = 0.0
    candles[0]["return_1m"] = 0.0
    return candles


def compute_forward_returns(candles, horizons=(1, 5, 15, 30, 60)):
    """Compute forward returns for each candle at given horizons (in minutes)."""
    for i, c in enumerate(candles):
        for h in horizons:
            if i + h < len(candles):
                fwd_close = candles[i + h]["close"]
                cur_close = c["close"]
                if cur_close > 0:
                    c[f"fwd_{h}m"] = (fwd_close - cur_close) / cur_close * 100
                else:
                    c[f"fwd_{h}m"] = None
            else:
                c[f"fwd_{h}m"] = None
    return candles


def detect_large_moves(candles, threshold_std=2.0):
    """Detect candles with returns > threshold_std standard deviations."""
    returns = [c["return_1m"] for c in candles if c.get("return_1m") is not None]
    if len(returns) < 10:
        return [], [], 0, 0

    mean_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / len(returns))

    threshold = mean_ret + threshold_std * std_ret
    threshold_neg = mean_ret - threshold_std * std_ret

    large_up = [c for c in candles if c.get("return_1m") is not None and c["return_1m"] > threshold]
    large_down = [c for c in candles if c.get("return_1m") is not None and c["return_1m"] < threshold_neg]

    return large_up, large_down, mean_ret, std_ret


def analyze_moves(events, label, horizons=(1, 5, 15, 30, 60)):
    """Analyze forward returns after large move events."""
    if not events:
        return

    print(f"\n  {label} | N={len(events)}")
    print(f"    {'Horizon':<10} {'N':<6} {'Retorno%':<12} {'IC95%':<30} {'WR%':<10} {'WR IC95%':<20}")
    print("    " + "-" * 88)

    for h in horizons:
        returns = [c[f"fwd_{h}m"] for c in events if c.get(f"fwd_{h}m") is not None]
        if len(returns) < 3:
            print(f"    {h}m{'':<7} {'insufficient data'}")
            continue

        lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
        wins = sum(1 for r in returns if r > 0)
        wr = wins / len(returns) if returns else 0
        wr_lo, wr_hi = wilson_ci(wins, len(returns))

        ci_str = f"[{lo:.4f}%, {hi:.4f}%]"
        wr_ci_str = f"[{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]"
        print(f"    {h}m{'':<7} {len(returns):<6} {avg:<12.4f} {ci_str:<30} {wr*100:<10.1f} {wr_ci_str:<20}")


def analyze_dataset(candles, label, horizons=(1, 5, 15, 30, 60), thresholds=(1.0, 1.5, 2.0, 2.5, 3.0)):
    """Run full large-move analysis on a dataset. Returns list of significant edges."""
    if not candles:
        return []

    candles = compute_returns(candles)
    candles = compute_forward_returns(candles, horizons=horizons)

    returns = [c["return_1m"] for c in candles if c.get("return_1m") is not None]
    if len(returns) < 10:
        print(f"  [{label}] Dados insuficientes ({len(returns)} velas)")
        return []

    mean_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / len(returns))

    print(f"\n  [{label}] {len(candles)} velas | mean={mean_ret:.6f}% std={std_ret:.4f}%")

    edges = []
    for thresh in thresholds:
        large_up, large_down, _, _ = detect_large_moves(candles, thresh)

        for h in horizons:
            # Bounce after large down (long signal)
            if large_down:
                rets = [c[f"fwd_{h}m"] for c in large_down if c.get(f"fwd_{h}m") is not None]
                if len(rets) >= 5:
                    lo, avg, hi = bootstrap_ci(rets, n_boot=5000)
                    net = avg - 2 * TAKER_FEE_PCT  # round-trip fee
                    net_lo = lo - 2 * TAKER_FEE_PCT
                    net_hi = hi - 2 * TAKER_FEE_PCT
                    sig = lo > 0
                    fee_sig = net_lo > 0
                    if sig or fee_sig:
                        edges.append({
                            "signal": f"DOWN {thresh}σ -> bounce {h}m",
                            "n": len(rets), "avg": avg, "lo": lo, "hi": hi,
                            "net": net, "net_lo": net_lo, "net_hi": net_hi,
                            "fee_significant": fee_sig, "direction": "long",
                        })

            # Pullback after large up (short signal)
            if large_up:
                rets = [c[f"fwd_{h}m"] for c in large_up if c.get(f"fwd_{h}m") is not None]
                if len(rets) >= 5:
                    lo, avg, hi = bootstrap_ci(rets, n_boot=5000)
                    # For short: return is negative = profit. Fee reduces profit.
                    net = avg + 2 * TAKER_FEE_PCT  # short profit = -|return| - fee
                    net_lo = lo + 2 * TAKER_FEE_PCT
                    net_hi = hi + 2 * TAKER_FEE_PCT
                    sig = hi < 0
                    fee_sig = net_hi < 0
                    if sig or fee_sig:
                        edges.append({
                            "signal": f"UP {thresh}σ -> pullback {h}m",
                            "n": len(rets), "avg": avg, "lo": lo, "hi": hi,
                            "net": net, "net_lo": net_lo, "net_hi": net_hi,
                            "fee_significant": fee_sig, "direction": "short",
                        })

    # Print detailed table for this dataset
    for thresh in thresholds:
        large_up, large_down, _, _ = detect_large_moves(candles, thresh)
        print(f"\n    Threshold {thresh}σ: UP={len(large_up)} DOWN={len(large_down)} events")
        if large_up:
            analyze_moves(large_up, f"  UP (>{thresh}σ) -> pullback", horizons=horizons)
        if large_down:
            analyze_moves(large_down, f"  DOWN (<-{thresh}σ) -> bounce", horizons=horizons)

    return edges


def main():
    parser = argparse.ArgumentParser(description="D22 — CEX liquidation cascade scan (multi-day validation)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance Futures symbol")
    parser.add_argument("--days", type=int, default=7, help="Days of 1m data to fetch")
    parser.add_argument("--oos-ratio", type=float, default=0.3, help="Fraction of data for OOS (0.3 = last 30%)")
    args = parser.parse_args()

    print("=" * 100)
    print(f"D22 — CEX Liquidation Cascade Scan (Multi-Day) | {args.symbol} | {args.days} dias | OOS={args.oos_ratio*100:.0f}%")
    print("=" * 100)

    # 1. Fetch klines (paginated)
    print(f"\n[1/4] Fetching {args.days} days of 1m candles from Binance Futures...")
    try:
        candles = fetch_klines_multi(args.symbol, "1m", args.days)
        if len(candles) < 100:
            print(f"  ERRO: apenas {len(candles)} velas obtidas")
            sys.exit(1)
        print(f"  OK: {len(candles)} velas | {candles[0]['time']} -> {candles[-1]['time']}")
        print(f"  Price: ${candles[0]['close']:.2f} -> ${candles[-1]['close']:.2f}")
        print(f"  ~{len(candles) / 60 / 24:.1f} dias de dados")
    except Exception as e:
        print(f"  ERRO: {e}")
        sys.exit(1)

    # 2. Split IS / OOS
    print(f"\n[2/4] Splitting IS/OOS ({1-args.oos_ratio:.0%}/{args.oos_ratio:.0%})...")
    split_idx = int(len(candles) * (1 - args.oos_ratio))
    is_candles = candles[:split_idx]
    oos_candles = candles[split_idx:]
    print(f"  IS:  {len(is_candles)} velas | {is_candles[0]['time']} -> {is_candles[-1]['time']}")
    print(f"  OOS: {len(oos_candles)} velas | {oos_candles[0]['time']} -> {oos_candles[-1]['time']}")

    # 3. Analyze Full + IS + OOS
    print(f"\n[3/4] Analyzing large moves...")
    print(f"  Fee model: Binance taker {TAKER_FEE_PCT}%/side = {2*TAKER_FEE_PCT}% round-trip")

    print("\n" + "=" * 100)
    print("FULL DATASET ANALYSIS")
    print("=" * 100)
    full_edges = analyze_dataset(candles, "FULL")

    print("\n" + "=" * 100)
    print("IN-SAMPLE (IS) ANALYSIS")
    print("=" * 100)
    is_edges = analyze_dataset(is_candles, "IS")

    print("\n" + "=" * 100)
    print("OUT-OF-SAMPLE (OOS) ANALYSIS")
    print("=" * 100)
    oos_edges = analyze_dataset(oos_candles, "OOS")

    # 4. Volume-weighted analysis on full dataset
    print("\n" + "=" * 100)
    print("VOLUME-WEIGHTED ANALYSIS (Full dataset)")
    print("=" * 100)

    all_candles = compute_returns(compute_forward_returns(candles))
    volumes = [c["volume"] for c in all_candles]
    vol_median = sorted(volumes)[len(volumes) // 2]
    vol_q80 = sorted(volumes)[int(len(volumes) * 0.8)]

    for thresh in [1.5, 2.0, 2.5]:
        _, large_down, _, _ = detect_large_moves(all_candles, thresh)
        if not large_down:
            continue
        high_vol = [c for c in large_down if c["volume"] > vol_q80]
        if high_vol:
            analyze_moves(high_vol, f"  DOWN {thresh}σ + HIGH VOL (>Q80) -> bounce")

        large_up, _, _, _ = detect_large_moves(all_candles, thresh)
        if large_up:
            high_vol_up = [c for c in large_up if c["volume"] > vol_q80]
            if high_vol_up:
                analyze_moves(high_vol_up, f"  UP {thresh}σ + HIGH VOL (>Q80) -> pullback")

    # Save samples (only significant events, >1.5σ)
    all_returns = [c["return_1m"] for c in all_candles if c.get("return_1m") is not None]
    all_mean = sum(all_returns) / len(all_returns) if all_returns else 0
    all_std = math.sqrt(sum((r - all_mean) ** 2 for r in all_returns) / len(all_returns)) if all_returns else 1
    threshold_15 = all_mean + 1.5 * all_std
    threshold_15_neg = all_mean - 1.5 * all_std

    samples = []
    for c in all_candles:
        r = c.get("return_1m")
        if r is not None and (r > threshold_15 or r < threshold_15_neg):
            samples.append({
                "time": c["time"], "close": c["close"],
                "return_1m": r, "volume": c["volume"],
                "fwd_5m": c.get("fwd_5m"), "fwd_15m": c.get("fwd_15m"),
                "fwd_30m": c.get("fwd_30m"), "fwd_60m": c.get("fwd_60m"),
            })
    with open("cex_liquidation_samples.json", "w") as f:
        json.dump(samples, f, indent=2)
    print(f"\n  {len(samples)} eventos significativos salvos em cex_liquidation_samples.json")

    # 5. Verdict
    print("\n" + "=" * 100)
    print("VEREDITO — D22 CEX LIQUIDATION CASCADE")
    print("=" * 100)

    # Cross-reference IS and OOS edges
    is_signals = {e["signal"]: e for e in is_edges}
    oos_signals = {e["signal"]: e for e in oos_edges}
    full_signals = {e["signal"]: e for e in full_edges}

    all_signals = set(list(is_signals.keys()) + list(oos_signals.keys()) + list(full_signals.keys()))

    if not all_signals:
        print("  SEM EDGE: nenhum signal significativo encontrado em nenhum dataset")
        print(f"  ({len(candles)} velas, {args.days} dias, threshold ate 3σ)")
        sys.exit(0)

    print(f"\n  Signals significativos encontrados:")
    print(f"  {'Signal':<35} {'IS?':<5} {'OOS?':<5} {'Fee-sig?':<10} {'N (full)':<10} {'Avg%':<10} {'Net%':<10}")
    print("  " + "-" * 85)

    validated = []
    for sig in sorted(all_signals):
        in_is = sig in is_signals
        in_oos = sig in oos_signals
        in_full = sig in full_signals
        full_e = full_signals.get(sig, {})
        fee_sig = full_e.get("fee_significant", False)
        n_full = full_e.get("n", "?")
        avg = full_e.get("avg", 0)
        net = full_e.get("net", 0)

        is_str = "YES" if in_is else "no"
        oos_str = "YES" if in_oos else "no"
        fee_str = "YES" if fee_sig else "no"

        print(f"  {sig:<35} {is_str:<5} {oos_str:<5} {fee_str:<10} {n_full:<10} {avg:<10.4f} {net:<10.4f}")

        if in_is and in_oos:
            validated.append((sig, full_e))

    # Final verdict
    print("\n  " + "=" * 80)
    if validated:
        print(f"  EDGE VALIDADO IS+OOS ({len(validated)} signals):")
        for sig, e in validated:
            fee_note = " (supera fees)" if e.get("fee_significant") else " (NAO supera fees)"
            print(f"    {sig}: avg={e['avg']:.4f}% IC95%[{e['lo']:.4f}%, {e['hi']:.4f}%] net={e['net']:.4f}%{fee_note}")
        print(f"\n  PROXIMO PASSO: Se net > 0 apos fees, implementar paper trading para validacao ao vivo")
    else:
        # Check if at least significant in full dataset
        full_sig = [s for s, e in full_signals.items()]
        if full_sig:
            print(f"  SINAL PARCIAL: {len(full_sig)} signals significativos no dataset completo")
            print(f"  MAS nao replicam em IS e OOS simultaneamente -> possivel overfitting/ruído")
        else:
            print(f"  SEM EDGE: nenhum signal significativo")

    print(f"\n  Dataset: {len(candles)} velas 1m ({args.days} dias)")
    print(f"  Fees: {TAKER_FEE_PCT}%/side = {2*TAKER_FEE_PCT}% round-trip (Binance taker)")
    print(f"  IS: {len(is_candles)} velas | OOS: {len(oos_candles)} velas")
    print(f"  Para validacao adicional: coletar mais dias, testar em outros simbolos (ETHUSDT),")
    print(f"  e distinguir liquidations reais (WS forceOrder) de grandes moves normais.")


if __name__ == "__main__":
    main()
