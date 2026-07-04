#!/usr/bin/env python3
"""
D7+D8: CEX-CEX arbitrage + Triangular CEX arbitrage scan.

D7 — Cross-exchange spread: Compare best bid/ask for the same pair across
Binance, Bybit, and OKX. If bid on exchange A > ask on exchange B (after fees),
there's a cross-exchange arb opportunity.

D8 — Triangular arbitrage on Binance: Check if BTC→ETH→USDT→BTC roundtrip
yields > 1.0 (after trading fees). Tests 6 triangular paths.

All data via free public REST APIs (no keys, no auth, read-only).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

UA = {"User-Agent": "cex-arb-scan/1.0 (research; read-only)"}

# Trading fees (taker) per exchange
FEES = {
    "binance": 0.0010,   # 0.10% spot taker (VIP0)
    "bybit": 0.0010,     # 0.10% spot taker (VIP0)
    "okx": 0.0010,       # 0.10% spot taker (Tier 1)
}

# Withdrawal fees (approximate, USD)
WITHDRAWAL_FEES = {
    "BTC": {"binance": 0.00002, "bybit": 0.00002, "okx": 0.00002},  # ~$2
    "ETH": {"binance": 0.00008, "bybit": 0.00008, "okx": 0.00008},  # ~$0.30
    "SOL": {"binance": 0.001, "bybit": 0.001, "okx": 0.001},        # ~$0.15
    "USDT": {"binance": 1.0, "bybit": 1.0, "okx": 1.0},            # ~$1 (TRC20)
}

# Pairs to scan for D7
CEX_PAIRS = [
    ("BTC", "USDT"),
    ("ETH", "USDT"),
    ("SOL", "USDT"),
    ("XRP", "USDT"),
    ("DOGE", "USDT"),
    ("ADA", "USDT"),
    ("AVAX", "USDT"),
    ("LINK", "USDT"),
]

# Triangular paths for D8 (on Binance)
# Each path: [(base, quote), (base, quote), (base, quote)] forming a cycle
TRIANGULAR_PATHS = [
    # BTC → ETH → USDT → BTC
    [("BTC", "ETH"), ("ETH", "USDT"), ("BTC", "USDT")],
    # BTC → SOL → USDT → BTC
    [("BTC", "SOL"), ("SOL", "USDT"), ("BTC", "USDT")],
    # ETH → SOL → USDT → ETH
    [("ETH", "SOL"), ("SOL", "USDT"), ("ETH", "USDT")],
    # BTC → XRP → USDT → BTC
    [("BTC", "XRP"), ("XRP", "USDT"), ("BTC", "USDT")],
    # ETH → XRP → USDT → ETH
    [("ETH", "XRP"), ("XRP", "USDT"), ("ETH", "USDT")],
    # BTC → DOGE → USDT → BTC
    [("BTC", "DOGE"), ("DOGE", "USDT"), ("BTC", "USDT")],
]


# ─── API clients ─────────────────────────────────────────────────────────────

def _get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def binance_book_ticker(base: str, quote: str) -> Optional[dict]:
    """Binance bookTicker: best bid/ask."""
    symbol = f"{base}{quote}"
    url = f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
    try:
        d = _get(url)
        return {"bid": float(d["bidPrice"]), "ask": float(d["askPrice"]),
                "bid_qty": float(d["bidQty"]), "ask_qty": float(d["askQty"])}
    except Exception:
        return None


def bybit_ticker(base: str, quote: str) -> Optional[dict]:
    """Bybit v5 tickers for spot."""
    symbol = f"{base}{quote}"
    url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}"
    try:
        d = _get(url)
        if d.get("retCode") == 0 and d.get("result", {}).get("list"):
            t = d["result"]["list"][0]
            return {"bid": float(t["bid1Price"]), "ask": float(t["ask1Price"]),
                    "bid_qty": float(t["bid1Size"]), "ask_qty": float(t["ask1Size"])}
    except Exception:
        pass
    return None


def okx_ticker(base: str, quote: str) -> Optional[dict]:
    """OKX v5 ticker."""
    inst_id = f"{base}-{quote}"
    url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
    try:
        d = _get(url)
        if d.get("code") == "0" and d.get("data"):
            t = d["data"][0]
            return {"bid": float(t["bidPx"]), "ask": float(t["askPx"]),
                    "bid_qty": float(t["bidSz"]), "ask_qty": float(t["askSz"])}
    except Exception:
        pass
    return None


def get_all_tickers(base: str, quote: str) -> dict:
    """Get best bid/ask from all exchanges for a pair."""
    return {
        "binance": binance_book_ticker(base, quote),
        "bybit": bybit_ticker(base, quote),
        "okx": okx_ticker(base, quote),
    }


# ─── D7: Cross-exchange arbitrage ────────────────────────────────────────────

@dataclass
class CEXSpread:
    pair: str
    exchanges: dict  # {exchange: {bid, ask, bid_qty, ask_qty}}
    best_buy_exchange: str = ""  # cheapest ask
    best_sell_exchange: str = ""  # highest bid
    buy_price: float = 0.0
    sell_price: float = 0.0
    gross_spread_bps: float = 0.0  # (sell - buy) / buy * 10000
    net_spread_bps: float = 0.0   # after fees
    max_trade_size: float = 0.0   # min of ask_qty at buy, bid_qty at sell
    timestamp: str = ""


def scan_cex_spread(base: str, quote: str) -> CEXSpread:
    """Find the best cross-exchange arb for a pair."""
    tickers = get_all_tickers(base, quote)
    result = CEXSpread(
        pair=f"{base}/{quote}",
        exchanges={k: v for k, v in tickers.items() if v is not None},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    valid = {k: v for k, v in tickers.items() if v is not None and v["ask"] > 0 and v["bid"] > 0}
    if len(valid) < 2:
        return result

    # Best place to buy = lowest ask
    buy_exch, buy_ticker = min(valid.items(), key=lambda x: x[1]["ask"])
    # Best place to sell = highest bid
    sell_exch, sell_ticker = max(valid.items(), key=lambda x: x[1]["bid"])

    result.best_buy_exchange = buy_exch
    result.best_sell_exchange = sell_exch
    result.buy_price = buy_ticker["ask"]
    result.sell_price = sell_ticker["bid"]

    if result.buy_price > 0:
        result.gross_spread_bps = (result.sell_price - result.buy_price) / result.buy_price * 10000
        # Net: subtract taker fees on both sides
        total_fee_bps = (FEES.get(buy_exch, 0.001) + FEES.get(sell_exch, 0.001)) * 10000
        result.net_spread_bps = result.gross_spread_bps - total_fee_bps

        # Max trade size (in base currency) = min(ask_qty at buy, bid_qty at sell)
        result.max_trade_size = min(buy_ticker["ask_qty"], sell_ticker["bid_qty"])

    return result


# ─── D8: Triangular arbitrage on Binance ─────────────────────────────────────

@dataclass
class TriangularResult:
    path: str
    legs: list  # [{base, quote, side, price, qty}]
    gross_roundtrip_bps: float = 0.0
    net_roundtrip_bps: float = 0.0
    timestamp: str = ""


def binance_book_ticker_pair(ccy_a: str, ccy_b: str) -> Optional[tuple]:
    """Try both orderings to find a valid Binance pair between two currencies.
    Returns (ticker_dict, actual_base, actual_quote) or None."""
    for base, quote in [(ccy_a, ccy_b), (ccy_b, ccy_a)]:
        t = binance_book_ticker(base, quote)
        if t is not None:
            return t, base, quote
    return None


def scan_triangular(path: list, trade_size_usd: float = 100.0) -> TriangularResult:
    """Check a triangular path on Binance.

    Path is a list of (ccy_a, ccy_b) pairs forming a cycle.
    We start with 1 unit of the first currency and go around the cycle.
    For each leg, we try both symbol orderings on Binance.
    """
    start_ccy = path[0][0]

    # Build the sequence of currencies
    sequence = [start_ccy]
    for ccy_a, ccy_b in path:
        if sequence[-1] == ccy_a:
            sequence.append(ccy_b)
        elif sequence[-1] == ccy_b:
            sequence.append(ccy_a)
        else:
            return TriangularResult(path=str(path), legs=[], timestamp=datetime.now(timezone.utc).isoformat())

    if sequence[-1] != start_ccy:
        return TriangularResult(path=str(path), legs=[], timestamp=datetime.now(timezone.utc).isoformat())

    # Execute the cycle
    legs = []
    current_amount = 1.0
    current_ccy = start_ccy

    for ccy_a, ccy_b in path:
        result = binance_book_ticker_pair(ccy_a, ccy_b)
        if result is None:
            return TriangularResult(path=str(path), legs=[], timestamp=datetime.now(timezone.utc).isoformat())

        ticker, actual_base, actual_quote = result

        if current_ccy == actual_base:
            # We have base, want quote → SELL base (use bid price)
            side = "sell"
            price = ticker["bid"]
            current_amount = current_amount * price
            current_ccy = actual_quote
        elif current_ccy == actual_quote:
            # We have quote, want base → BUY base (use ask price)
            side = "buy"
            price = ticker["ask"]
            current_amount = current_amount / price
            current_ccy = actual_base
        else:
            return TriangularResult(path=str(path), legs=[], timestamp=datetime.now(timezone.utc).isoformat())

        legs.append({"pair": f"{actual_base}/{actual_quote}", "side": side,
                     "price": price, "amount_after": current_amount})

    gross_bps = (current_amount - 1.0) * 10000
    net_bps = gross_bps - FEES["binance"] * 10000 * 3

    path_str = "→".join([f"{a}/{b}" for a, b in path])
    return TriangularResult(
        path=f"{path_str} (start={start_ccy})",
        legs=legs,
        gross_roundtrip_bps=gross_bps,
        net_roundtrip_bps=net_bps,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ─── Main scan loop ──────────────────────────────────────────────────────────

def run_scan(duration_min: int, interval_s: int, output_file: str):
    end_time = time.time() + duration_min * 60
    cycle = 0
    all_results = []

    print(f"D7+D8: CEX-CEX Arb + Triangular CEX Arb Scan")
    print(f"Duration: {duration_min}min, Interval: {interval_s}s")
    print(f"Exchanges: Binance, Bybit, OKX")
    print(f"D7 pairs: {len(CEX_PAIRS)}, D8 paths: {len(TRIANGULAR_PATHS)}")
    print(f"Fees: Binance/Bybit/OKX = 0.10% taker (10 bps/side)")
    print(f"Output: {output_file}")
    print(f"{'='*80}\n")

    while time.time() < end_time:
        cycle += 1
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"\n--- Cycle {cycle} @ {ts} UTC ---")

        # D7: Cross-exchange spreads
        print(f"\n  D7 — Cross-exchange spreads:")
        for base, quote in CEX_PAIRS:
            r = scan_cex_spread(base, quote)
            all_results.append({"type": "cex_spread", **asdict(r)})
            if r.gross_spread_bps > 0:
                fee_note = "NET+" if r.net_spread_bps > 0 else "net-"
                print(f"    {r.pair:10s} gross={r.gross_spread_bps:6.1f}bps "
                      f"net={r.net_spread_bps:6.1f}bps ({fee_note}) "
                      f"buy={r.best_buy_exchange}@{r.buy_price:.6f} "
                      f"sell={r.best_sell_exchange}@{r.sell_price:.6f} "
                      f"max_size={r.max_trade_size:.4f}")
            else:
                n_exch = len(r.exchanges)
                print(f"    {r.pair:10s} {n_exch} exchanges, no positive spread")

        # D8: Triangular arb on Binance
        print(f"\n  D8 — Triangular arb (Binance):")
        for path in TRIANGULAR_PATHS:
            r = scan_triangular(path)
            all_results.append({"type": "triangular", **asdict(r)})
            status = "ARB!" if r.net_roundtrip_bps > 0 else "loss"
            print(f"    {r.path:50s} gross={r.gross_roundtrip_bps:7.1f}bps "
                  f"net={r.net_roundtrip_bps:7.1f}bps ({status})")

        # Save incrementally
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2, default=str)

        if time.time() < end_time:
            print(f"\n  Waiting {interval_s}s...")
            time.sleep(interval_s)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — {cycle} cycles, {len(all_results)} observations\n")

    # D7 summary
    spreads = [r for r in all_results if r["type"] == "cex_spread" and r["gross_spread_bps"] != 0]
    if spreads:
        gross_vals = [r["gross_spread_bps"] for r in spreads]
        net_vals = [r["net_spread_bps"] for r in spreads]
        positive_net = [r for r in spreads if r["net_spread_bps"] > 0]
        print(f"D7 — Cross-exchange spreads:")
        print(f"  N = {len(spreads)} observations")
        print(f"  Gross: mean={sum(gross_vals)/len(gross_vals):.1f}bps, "
              f"max={max(gross_vals):.1f}bps, min={min(gross_vals):.1f}bps")
        print(f"  Net:   mean={sum(net_vals)/len(net_vals):.1f}bps, "
              f"max={max(net_vals):.1f}bps, min={min(net_vals):.1f}bps")
        print(f"  Positive net (after fees): {len(positive_net)}/{len(spreads)}")
        if positive_net:
            for r in positive_net[:5]:
                print(f"    {r['pair']:10s} net={r['net_spread_bps']:.1f}bps "
                      f"buy={r['best_buy_exchange']} sell={r['best_sell_exchange']} "
                      f"max_size={r['max_trade_size']:.4f}")

    # D8 summary
    tris = [r for r in all_results if r["type"] == "triangular" and r["gross_roundtrip_bps"] != 0]
    if tris:
        gross_rt = [r["gross_roundtrip_bps"] for r in tris]
        net_rt = [r["net_roundtrip_bps"] for r in tris]
        positive_net_rt = [r for r in tris if r["net_roundtrip_bps"] > 0]
        print(f"\nD8 — Triangular arb (Binance):")
        print(f"  N = {len(tris)} observations")
        print(f"  Gross: mean={sum(gross_rt)/len(gross_rt):.1f}bps, "
              f"max={max(gross_rt):.1f}bps, min={min(gross_rt):.1f}bps")
        print(f"  Net:   mean={sum(net_rt)/len(net_rt):.1f}bps, "
              f"max={max(net_rt):.1f}bps, min={min(net_rt):.1f}bps")
        print(f"  Positive net (after 30bps fees): {len(positive_net_rt)}/{len(tris)}")
        if positive_net_rt:
            for r in positive_net_rt[:5]:
                print(f"    {r['path']:50s} net={r['net_roundtrip_bps']:.1f}bps")


def main():
    parser = argparse.ArgumentParser(description="D7+D8 CEX Arbitrage Scan")
    parser.add_argument("--duration-min", type=int, default=10, help="Scan duration in minutes")
    parser.add_argument("--interval-s", type=int, default=15, help="Seconds between cycles")
    parser.add_argument("--output", type=str, default="cex_arb_samples.json",
                        help="Output JSON file")
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(args.duration_min, args.interval_s, output_path)


if __name__ == "__main__":
    main()
