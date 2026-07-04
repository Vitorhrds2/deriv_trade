#!/usr/bin/env python3
"""
Cross-aggregator DEX arbitrage scan (D6).

Hypothesis D6: Different DEX aggregators on EVM chains may route through
different underlying DEXs, producing different quotes for the same token pair.
If the cross-aggregator spread exceeds gas + fees, there may be an exploitable
cross-DEX arbitrage opportunity.

Tests two sub-hypotheses:
  D6a — Cross-aggregator quote spread: measure the bps gap between best and
        worst aggregator quotes for the same pair. Large persistent spreads
        suggest routing inefficiency (aggregators don't all find the same price).
  D6b — Roundtrip arb: sell token A → B via best aggregator, then buy B → A
        via best aggregator. If roundtrip > 0 bps (after gas), arb exists.

Aggregators used (all free, no API keys):
  - OpenOcean v4  (30+ chains, 0.2% fee)
  - Paraswap/Velora (10+ EVM chains, 0.15% positive slippage)
  - LiFi (all chains, 0% fee, rate-limited without key)

Chains tested: BSC (56), Base (8453), Arbitrum (42161), Polygon (137)

Read-only, no wallet, no signing, no capital. Paper-trades only.
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
from pathlib import Path
from typing import Optional

UA = {"User-Agent": "dex-scan/1.0 (research; read-only)"}

# ─── Token registry ──────────────────────────────────────────────────────────

NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

TOKENS = {
    "bsc": {
        "chain_id": 56,
        "oo_chain": "bsc",
        "native_symbol": "BNB",
        "native_wrapped": "0xbb4CdB9CBd36B01bD1cBaEbF2De08d9173bc095c",  # WBNB
        "native_decimals": 18,
        "tokens": {
            "WBNB": ("0xbb4CdB9CBd36B01bD1cBaEbF2De08d9173bc095c", 18),
            "USDT": ("0x55d398326f99059fF775485246999027B3197955", 18),
            "USDC": ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
            "BUSD": ("0xe9e7CEA3DedcA5984780Bafc599bD69ACd087D56", 18),
            "CAKE": ("0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81c82C", 18),
            "ETH":  ("0x2170Ed0880ac9A755fd29B2688956BD959F933F8", 18),
        },
    },
    "base": {
        "chain_id": 8453,
        "oo_chain": "base",
        "native_symbol": "ETH",
        "native_wrapped": "0x4200000000000000000000000000000000000006",  # WETH
        "native_decimals": 18,
        "tokens": {
            "WETH":  ("0x4200000000000000000000000000000000000006", 18),
            "USDC":  ("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6),
            "CBETH": ("0x2Ae3F1Ec5F216B86E7c1012145D348d447c242C0", 18),
            "DEUS":  ("0xDe15F23c14c48612Bc11C95a8B981AaaDc44D7F1", 18),
        },
    },
    "arbitrum": {
        "chain_id": 42161,
        "oo_chain": "arbitrum",
        "native_symbol": "ETH",
        "native_wrapped": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
        "native_decimals": 18,
        "tokens": {
            "WETH":  ("0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", 18),
            "USDC":  ("0xaf88d065e77c8cC2239327C5EDb3A432268e5831", 6),
            "USDT":  ("0xFd086bC7CD5C481DCC9C85bE478A1C0b69FCbb9f", 6),
            "ARB":   ("0x912CE59144191C1204E64559FE8253a0e49E6548", 18),
        },
    },
    "polygon": {
        "chain_id": 137,
        "oo_chain": "polygon",
        "native_symbol": "MATIC",
        "native_wrapped": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
        "native_decimals": 18,
        "tokens": {
            "WMATIC": ("0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", 18),
            "USDC":   ("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", 6),
            "USDT":   ("0xc2132D05D31c914a87C6611C10748AEb04B8e2F5", 6),
            "WETH":   ("0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", 18),
        },
    },
}

# Trade sizes to test (in native token units)
TRADE_SIZES = [1.0, 5.0]  # 1 and 5 native tokens


# ─── Aggregator clients ──────────────────────────────────────────────────────

def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(url, body, timeout=15):
    headers = {**UA, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def quote_openocean(chain_oo: str, from_token: str, to_token: str, amount: float) -> Optional[int]:
    """OpenOcean v4 quote. Returns outAmount in smallest units, or None."""
    base = f"https://open-api.openocean.finance/v4/{chain_oo}/quote"
    params = {"inTokenAddress": from_token, "outTokenAddress": to_token,
              "amount": str(amount), "gasPrice": "3"}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        data = _get(url)
        if data.get("code") == 200:
            return int(data["data"]["outAmount"])
    except Exception:
        pass
    return None


def quote_paraswap(chain_id: int, from_token: str, to_token: str,
                   amount_wei: str, dec_in: int, dec_out: int) -> Optional[int]:
    """Paraswap/Velora quote. Returns destAmount in smallest units, or None."""
    base = "https://api.paraswap.io/prices"
    params = {"srcToken": from_token, "destToken": to_token, "amount": amount_wei,
              "srcDecimals": str(dec_in), "destDecimals": str(dec_out),
              "side": "SELL", "network": str(chain_id)}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        data = _get(url)
        pr = data.get("priceRoute", {})
        if pr.get("destAmount"):
            return int(pr["destAmount"])
    except Exception:
        pass
    return None


def quote_lifi(chain_id: int, from_token: str, to_token: str,
               amount_wei: str) -> Optional[int]:
    """LiFi quote. Returns toAmount in smallest units, or None."""
    base = "https://li.quest/v1/quote"
    params = {"fromChain": str(chain_id), "toChain": str(chain_id),
              "fromToken": from_token, "toToken": to_token,
              "fromAmount": amount_wei,
              "fromAddress": "0x0000000000000000000000000000000000000001"}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        data = _get(url)
        est = data.get("estimate", {})
        if est.get("toAmount"):
            return int(est["toAmount"])
    except Exception:
        pass
    return None


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class QuoteResult:
    aggregator: str
    out_amount: int  # smallest units
    success: bool


@dataclass
class PairScan:
    chain: str
    from_token: str
    to_token: str
    amount: float  # human-readable
    amount_wei: str
    quotes: list = field(default_factory=list)  # list of QuoteResult
    spread_bps: float = 0.0
    best_agg: str = ""
    worst_agg: str = ""
    timestamp: str = ""


@dataclass
class RoundtripResult:
    chain: str
    token_a: str
    token_b: str
    amount_a: float
    sell_agg: str
    sell_amount_b: int  # USDC/USDT units received
    buy_agg: str
    buy_amount_a: int  # token A units received back
    roundtrip_bps: float = 0.0
    timestamp: str = ""


# ─── Scan logic ──────────────────────────────────────────────────────────────

def to_wei(amount: float, decimals: int) -> str:
    return str(int(amount * 10**decimals))


def from_wei(amount: int, decimals: int) -> float:
    return amount / 10**decimals


def scan_pair(chain_key: str, from_sym: str, to_sym: str, amount: float) -> PairScan:
    """Get quotes from all aggregators for a single pair."""
    chain = TOKENS[chain_key]
    from_addr, from_dec = chain["tokens"][from_sym]
    to_addr, to_dec = chain["tokens"][to_sym]
    amount_wei = to_wei(amount, from_dec)

    result = PairScan(
        chain=chain_key, from_token=from_sym, to_token=to_sym,
        amount=amount, amount_wei=amount_wei,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # OpenOcean (uses human-readable amount)
    oo_out = quote_openocean(chain["oo_chain"], from_addr, to_addr, amount)
    result.quotes.append(QuoteResult("OpenOcean", oo_out or 0, oo_out is not None))

    # Paraswap (uses NATIVE sentinel for native and wrapped-native tokens)
    is_native = from_addr == chain["native_wrapped"] or from_sym == chain["native_symbol"]
    ps_from = NATIVE if is_native else from_addr
    ps_out = quote_paraswap(chain["chain_id"], ps_from, to_addr, amount_wei, from_dec, to_dec)
    result.quotes.append(QuoteResult("Paraswap", ps_out or 0, ps_out is not None))

    # LiFi (uses NATIVE sentinel for native and wrapped-native tokens)
    lf_from = NATIVE if is_native else from_addr
    lf_out = quote_lifi(chain["chain_id"], lf_from, to_addr, amount_wei)
    result.quotes.append(QuoteResult("LiFi", lf_out or 0, lf_out is not None))

    # Calculate spread
    valid = [(q.aggregator, q.out_amount) for q in result.quotes if q.success and q.out_amount > 0]
    if len(valid) >= 2:
        best_agg, best_amt = max(valid, key=lambda x: x[1])
        worst_agg, worst_amt = min(valid, key=lambda x: x[1])
        result.best_agg = best_agg
        result.worst_agg = worst_agg
        result.spread_bps = (best_amt - worst_amt) / worst_amt * 10000

    return result


def scan_roundtrip(chain_key: str, token_a: str, token_b: str, amount_a: float) -> RoundtripResult:
    """Sell A→B via best aggregator, then buy B→A via best aggregator."""
    chain = TOKENS[chain_key]
    a_addr, a_dec = chain["tokens"][token_a]
    b_addr, b_dec = chain["tokens"][token_b]

    ts = datetime.now(timezone.utc).isoformat()

    # Leg 1: A → B
    sell = scan_pair(chain_key, token_a, token_b, amount_a)
    valid_sells = [(q.aggregator, q.out_amount) for q in sell.quotes if q.success and q.out_amount > 0]
    if not valid_sells:
        return RoundtripResult(chain_key, token_a, token_b, amount_a, "", 0, "", 0, -9999, ts)

    best_sell_agg, best_sell_amount = max(valid_sells, key=lambda x: x[1])

    # Leg 2: B → A using exact amount from leg 1
    amount_b = from_wei(best_sell_amount, b_dec)
    buy = scan_pair(chain_key, token_b, token_a, amount_b)
    valid_buys = [(q.aggregator, q.out_amount) for q in buy.quotes if q.success and q.out_amount > 0]
    if not valid_buys:
        return RoundtripResult(chain_key, token_a, token_b, amount_a, best_sell_agg,
                               best_sell_amount, "", 0, -9999, ts)

    best_buy_agg, best_buy_amount = max(valid_buys, key=lambda x: x[1])

    # Roundtrip PnL
    started_with = to_wei(amount_a, a_dec)
    roundtrip_bps = (best_buy_amount - int(started_with)) / int(started_with) * 10000

    return RoundtripResult(
        chain_key, token_a, token_b, amount_a,
        best_sell_agg, best_sell_amount,
        best_buy_agg, best_buy_amount,
        roundtrip_bps, ts,
    )


# ─── Main loop ───────────────────────────────────────────────────────────────

def run_scan(duration_min: int, interval_s: int, output_file: str):
    """Run the scan loop."""
    end_time = time.time() + duration_min * 60
    cycle = 0
    all_results = []

    # Define pairs to scan per chain
    scan_pairs = {
        "bsc": [("WBNB", "USDT"), ("WBNB", "USDC"), ("WBNB", "BUSD"),
                ("CAKE", "USDT"), ("ETH", "USDT")],
        "base": [("WETH", "USDC"), ("WETH", "CBETH")],
        "arbitrum": [("WETH", "USDC"), ("WETH", "USDT"), ("ARB", "USDC")],
        "polygon": [("WMATIC", "USDC"), ("WMATIC", "USDT"), ("WETH", "USDC")],
    }

    # Roundtrip pairs (liquid pairs only)
    roundtrip_pairs = {
        "bsc": [("WBNB", "USDT"), ("WBNB", "USDC")],
        "base": [("WETH", "USDC")],
        "arbitrum": [("WETH", "USDC"), ("WETH", "USDT")],
        "polygon": [("WMATIC", "USDC")],
    }

    print(f"D6 Cross-Aggregator DEX Arb Scan")
    print(f"Duration: {duration_min}min, Interval: {interval_s}s")
    print(f"Chains: {list(scan_pairs.keys())}")
    print(f"Aggregators: OpenOcean, Paraswap, LiFi")
    print(f"Output: {output_file}")
    print(f"{'='*80}\n")

    while time.time() < end_time:
        cycle += 1
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"\n--- Cycle {cycle} @ {ts} UTC ---")

        # D6a: Cross-aggregator spread
        for chain_key, pairs in scan_pairs.items():
            for from_sym, to_sym in pairs:
                for size in TRADE_SIZES:
                    r = scan_pair(chain_key, from_sym, to_sym, size)
                    all_results.append({"type": "spread", **asdict(r)})
                    if r.spread_bps > 0:
                        print(f"  [{chain_key}] {from_sym}→{to_sym} x{size}: "
                              f"spread={r.spread_bps:.1f}bps "
                              f"(best={r.best_agg}, worst={r.worst_agg})")
                    else:
                        n_ok = sum(1 for q in r.quotes if q.success)
                        print(f"  [{chain_key}] {from_sym}→{to_sym} x{size}: "
                              f"{n_ok}/3 aggs OK, no spread")

        # D6b: Roundtrip arb
        for chain_key, pairs in roundtrip_pairs.items():
            for token_a, token_b in pairs:
                rt = scan_roundtrip(chain_key, token_a, token_b, 1.0)
                all_results.append({"type": "roundtrip", **asdict(rt)})
                status = "ARB!" if rt.roundtrip_bps > 0 else "loss"
                print(f"  [{chain_key}] RT {token_a}→{token_b}→{token_a}: "
                      f"{rt.roundtrip_bps:.1f}bps ({status}) "
                      f"sell={rt.sell_agg}, buy={rt.buy_agg}")

        # Save incrementally
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2, default=str)

        # Wait
        if time.time() < end_time:
            print(f"\n  Waiting {interval_s}s...")
            time.sleep(interval_s)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — {cycle} cycles, {len(all_results)} observations\n")

    spreads = [r for r in all_results if r["type"] == "spread" and r["spread_bps"] > 0]
    roundtrips = [r for r in all_results if r["type"] == "roundtrip" and r["roundtrip_bps"] > -9999]

    if spreads:
        bps_values = [r["spread_bps"] for r in spreads]
        print(f"D6a — Cross-aggregator spread:")
        print(f"  N = {len(spreads)} pairs with spread > 0")
        print(f"  Mean spread: {sum(bps_values)/len(bps_values):.1f} bps")
        print(f"  Max spread: {max(bps_values):.1f} bps")
        print(f"  Min spread: {min(bps_values):.1f} bps")
        # By chain
        for chain in scan_pairs:
            chain_spreads = [r["spread_bps"] for r in spreads if r["chain"] == chain]
            if chain_spreads:
                print(f"  {chain}: N={len(chain_spreads)}, "
                      f"mean={sum(chain_spreads)/len(chain_spreads):.1f}bps, "
                      f"max={max(chain_spreads):.1f}bps")
    else:
        print("D6a — No spreads detected (all aggregators returned same price)")

    if roundtrips:
        rt_values = [r["roundtrip_bps"] for r in roundtrips]
        positive = [r for r in roundtrips if r["roundtrip_bps"] > 0]
        print(f"\nD6b — Roundtrip arb:")
        print(f"  N = {len(roundtrips)} roundtrips")
        print(f"  Mean: {sum(rt_values)/len(rt_values):.1f} bps")
        print(f"  Max: {max(rt_values):.1f} bps")
        print(f"  Positive (arb): {len(positive)}/{len(roundtrips)}")
        if positive:
            print(f"  ⚠️  {len(positive)} roundtrips showed positive PnL — "
                  "likely stale quotes, not real arb")


def main():
    parser = argparse.ArgumentParser(description="D6 Cross-Aggregator DEX Arb Scan")
    parser.add_argument("--duration-min", type=int, default=10, help="Scan duration in minutes")
    parser.add_argument("--interval-s", type=int, default=30, help="Seconds between cycles")
    parser.add_argument("--output", type=str, default="dex_cross_agg_samples.json",
                        help="Output JSON file")
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(args.duration_min, args.interval_s, output_path)


if __name__ == "__main__":
    main()
