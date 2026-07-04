"""DEX arbitrage scan — Jupiter (Solana) vs Binance CEX + triangular arb.

Read-only scan (no capital, no wallet, no transactions). Two independent tests:

1. CEX-DEX divergence: Poll Jupiter Swap API quote for SOL→USDC and compare
   with Binance bookTicker (best bid/ask) in real-time. If Jupiter's effective
   price (outAmount/inAmount) diverges from Binance mid by more than the
   swap fee + slippage, there's a potential edge.

2. Triangular arbitrage: SOL→USDC→SOL roundtrip via Jupiter. If the product
   of the two quotes > 1.0 after accounting for fees, there's a circular arb.

Both tests are analogous to H1/H3 (latency arb) but in a fundamentally different
market structure: DEX prices are on-chain AMM pool states that update on Solana
slots (~400ms), while Binance updates in real-time via WebSocket. The question
is whether the slower on-chain update creates exploitable stale pricing.

Usage:
    python dex_arb_scan.py --duration-min 30 --interval-s 2
    python dex_arb_scan.py --duration-min 60 --interval-s 1 --pairs sol-usdc,usdc-sol
"""
import argparse
import asyncio
import json
import os
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import websockets

# --- Token mints (Solana) ---
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP_API_KEY = os.getenv("JUPITER_API_KEY", "")
JUP_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
BINANCE_WS = "wss://stream.binance.com:9443/ws/solusdt@bookTicker"

# Lamports per SOL
LAMPORTS_PER_SOL = 1_000_000_000
# Microcents per USDC (USDC has 6 decimals)
MICRO_PER_USDC = 1_000_000


@dataclass
class BinanceState:
    best_bid: float = 0.0
    best_ask: float = 0.0
    last_update: float = 0.0

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2 if self.best_bid and self.best_ask else 0.0

    @property
    def spread_bps(self) -> float:
        if not self.best_bid or not self.best_ask:
            return 0.0
        return (self.best_ask - self.best_bid) / self.mid * 10000


@dataclass
class QuoteResult:
    input_mint: str
    output_mint: str
    in_amount: int        # raw (lamports or micro-USDC)
    out_amount: int       # raw
    effective_price: float  # USDC per SOL (or SOL per USDC * 1e-6)
    price_impact_pct: float
    route_labels: list = field(default_factory=list)
    time_taken_ms: float = 0.0
    timestamp: float = 0.0
    error: Optional[str] = None


def get_jupiter_quote(input_mint: str, output_mint: str, amount_raw: int,
                      slippage_bps: int = 50, timeout: int = 10) -> QuoteResult:
    """Fetch a quote from Jupiter Swap API (read-only, no wallet needed)."""
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_raw),
        "slippageBps": str(slippage_bps),
        "restrictIntermediateTokens": "true",
    }
    url = JUP_QUOTE_URL + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; hypothesis-research-bot/1.0)"}
    if JUP_API_KEY:
        headers["x-api-key"] = JUP_API_KEY

    req = urllib.request.Request(url, headers=headers)
    ts = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return QuoteResult(
            input_mint=input_mint, output_mint=output_mint,
            in_amount=amount_raw, out_amount=0, effective_price=0.0,
            price_impact_pct=0.0, timestamp=ts, error=str(e)[:200],
        )

    out_amount = int(data.get("outAmount", 0))
    in_amount = int(data.get("inAmount", amount_raw))
    price_impact = float(data.get("priceImpactPct", "0"))
    time_taken = float(data.get("timeTaken", 0)) * 1000  # to ms

    # Effective price: for SOL→USDC, price = out_amount (micro-USDC) / in_amount (lamports) * 1e9
    # → USDC per SOL
    if input_mint == SOL_MINT and output_mint == USDC_MINT:
        eff_price = (out_amount / MICRO_PER_USDC) / (in_amount / LAMPORTS_PER_SOL)
    elif input_mint == USDC_MINT and output_mint == SOL_MINT:
        # SOL per USDC → convert to USDC per SOL for consistency
        sol_received = out_amount / LAMPORTS_PER_SOL
        usdc_spent = in_amount / MICRO_PER_USDC
        eff_price = usdc_spent / sol_received if sol_received else 0.0
    else:
        eff_price = out_amount / in_amount if in_amount else 0.0

    route_labels = [step.get("swapInfo", {}).get("label", "?") for step in data.get("routePlan", [])]

    return QuoteResult(
        input_mint=input_mint, output_mint=output_mint,
        in_amount=in_amount, out_amount=out_amount,
        effective_price=eff_price, price_impact_pct=price_impact,
        route_labels=route_labels, time_taken_ms=time_taken,
        timestamp=ts,
    )


async def binance_book_ticker_loop(state: BinanceState, running: asyncio.Event):
    """Continuously update best bid/ask from Binance WebSocket."""
    uri = BINANCE_WS
    while running.is_set():
        try:
            async with websockets.connect(uri, ping_interval=15) as ws:
                async for msg in ws:
                    if not running.is_set():
                        break
                    data = json.loads(msg)
                    bid = float(data.get("b", 0))
                    ask = float(data.get("a", 0))
                    if bid and ask:
                        state.best_bid = bid
                        state.best_ask = ask
                        state.last_update = time.time()
        except Exception as e:
            print(f"  [binance_ws] reconectando apos erro: {e}")
            await asyncio.sleep(2)


async def scan_loop(duration_s: int, interval_s: float, sol_amount: float):
    """Main scan loop: poll Jupiter quotes + compare with Binance price."""
    binance = BinanceState()
    running = asyncio.Event()
    running.set()

    # Start Binance WS in background
    ws_task = asyncio.create_task(binance_book_ticker_loop(binance, running))

    # Wait for Binance to connect
    print("Aguardando Binance WS conectar...", flush=True)
    for _ in range(20):
        if binance.last_update > 0:
            break
        await asyncio.sleep(0.5)

    if binance.last_update == 0:
        print("ERRO: Binance WS nao conectou em 10s. Abortando.")
        running.clear()
        ws_task.cancel()
        return

    print(f"Binance conectado: bid={binance.best_bid} ask={binance.best_ask} "
          f"mid={binance.mid:.4f} spread={binance.spread_bps:.2f}bps", flush=True)

    sol_raw = int(sol_amount * LAMPORTS_PER_SOL)
    # usdc_raw for the standalone USDC→SOL quote (fixed size for CEX-DEX comparison)
    usdc_raw = int(sol_amount * binance.mid * MICRO_PER_USDC)

    end_time = time.time() + duration_s
    samples = []

    print(f"\n{'='*100}")
    print(f"DEX Arb Scan — {duration_s/60:.1f}min, intervalo {interval_s}s, "
          f"size={sol_amount} SOL (~${sol_amount*binance.mid:.2f})")
    print(f"{'='*100}")
    print(f"{'ts':>6} | {'Binance_mid':>12} {'Binance_spd':>10} | "
          f"{'Jup_SOL→USDC':>14} {'div_bps':>8} | "
          f"{'Jup_USDC→SOL':>14} {'div_bps':>8} | "
          f"{'Tri_chained':>14} {'net_bps':>8} | routes")
    print("-" * 130)

    while time.time() < end_time:
        ts = time.time()
        binance_mid = binance.mid
        binance_spread = binance.spread_bps

        # 1. SOL→USDC quote (first leg of triangular + standalone CEX-DEX sell)
        q_sol_usdc = await asyncio.get_event_loop().run_in_executor(
            None, get_jupiter_quote, SOL_MINT, USDC_MINT, sol_raw
        )
        await asyncio.sleep(0.5)  # stagger to avoid 429

        # 2. USDC→SOL standalone (fixed size for CEX-DEX buy comparison)
        q_usdc_sol = await asyncio.get_event_loop().run_in_executor(
            None, get_jupiter_quote, USDC_MINT, SOL_MINT, usdc_raw
        )
        await asyncio.sleep(0.5)  # stagger to avoid 429

        # 3. Chained triangular: use actual outAmount from leg 1 as input to leg 2
        if q_sol_usdc.out_amount and not q_sol_usdc.error:
            q_tri_back = await asyncio.get_event_loop().run_in_executor(
                None, get_jupiter_quote, USDC_MINT, SOL_MINT, q_sol_usdc.out_amount
            )
        else:
            q_tri_back = QuoteResult(
                input_mint=USDC_MINT, output_mint=SOL_MINT,
                in_amount=0, out_amount=0, effective_price=0.0,
                price_impact_pct=0.0, timestamp=ts, error="no leg1 output",
            )

        # CEX-DEX divergence (SOL→USDC: sell SOL on Jupiter vs sell at Binance mid)
        if q_sol_usdc.effective_price and binance_mid:
            div_sell_bps = (q_sol_usdc.effective_price - binance_mid) / binance_mid * 10000
        else:
            div_sell_bps = None

        # CEX-DEX divergence (USDC→SOL: buy SOL on Jupiter vs buy at Binance mid)
        if q_usdc_sol.effective_price and binance_mid:
            div_buy_bps = (q_usdc_sol.effective_price - binance_mid) / binance_mid * 10000
        else:
            div_buy_bps = None

        # Triangular arb: SOL→USDC→SOL chained roundtrip
        # Uses actual outAmount from leg 1 as input to leg 2 (real arb, not inflated)
        if q_sol_usdc.out_amount and q_tri_back.out_amount:
            roundtrip_ratio = q_tri_back.out_amount / sol_raw
            tri_bps = (roundtrip_ratio - 1.0) * 10000
        else:
            roundtrip_ratio = None
            tri_bps = None

        # Error handling
        errors = []
        if q_sol_usdc.error:
            errors.append(f"SOL→USDC: {q_sol_usdc.error}")
        if q_usdc_sol.error:
            errors.append(f"USDC→SOL: {q_usdc_sol.error}")
        if q_tri_back.error:
            errors.append(f"TRI_back: {q_tri_back.error}")

        sample = {
            "ts": ts,
            "binance_mid": binance_mid,
            "binance_spread_bps": binance_spread,
            "jup_sell_price": q_sol_usdc.effective_price,
            "jup_sell_div_bps": div_sell_bps,
            "jup_buy_price": q_usdc_sol.effective_price,
            "jup_buy_div_bps": div_buy_bps,
            "tri_ratio": roundtrip_ratio,
            "tri_bps": tri_bps,
            "sell_routes": q_sol_usdc.route_labels,
            "buy_routes": q_usdc_sol.route_labels,
            "tri_back_routes": q_tri_back.route_labels,
            "sell_impact_pct": q_sol_usdc.price_impact_pct,
            "buy_impact_pct": q_usdc_sol.price_impact_pct,
            "tri_back_impact_pct": q_tri_back.price_impact_pct,
            "errors": errors,
        }
        samples.append(sample)

        # Print line
        div_s = f"{div_sell_bps:+.1f}" if div_sell_bps is not None else "  ERR"
        div_b = f"{div_buy_bps:+.1f}" if div_buy_bps is not None else "  ERR"
        tri_s = f"{tri_bps:+.1f}" if tri_bps is not None else "  ERR"
        rt_s = f"{roundtrip_ratio:.6f}" if roundtrip_ratio is not None else "  ERR"
        sell_p = f"${q_sol_usdc.effective_price:.4f}" if q_sol_usdc.effective_price else "ERR"
        buy_p = f"${q_usdc_sol.effective_price:.4f}" if q_usdc_sol.effective_price else "ERR"

        print(
            f"{ts - samples[0]['ts']:>6.1f} | "
            f"${binance_mid:>11.4f} {binance_spread:>8.1f}bps | "
            f"{sell_p:>14} {div_s:>8} | "
            f"{buy_p:>14} {div_b:>8} | "
            f"{rt_s:>14} {tri_s:>8} | "
            f"{'+'.join(q_sol_usdc.route_labels[:2])}"
            + (f" → {'+'.join(q_tri_back.route_labels[:2])}" if q_tri_back.route_labels else ""),
            flush=True,
        )

        if errors:
            for e in errors:
                print(f"  ERROR: {e}", flush=True)

        await asyncio.sleep(interval_s)

    running.clear()
    ws_task.cancel()
    try:
        await ws_task
    except asyncio.CancelledError:
        pass

    # --- Analysis ---
    print(f"\n{'='*100}")
    print(f"ANALISE — {len(samples)} amostras")
    print(f"{'='*100}")

    valid = [s for s in samples if not s["errors"]]

    if not valid:
        print("Nenhuma amostra valida. Abortando.")
        return

    # CEX-DEX divergence stats
    sell_divs = [s["jup_sell_div_bps"] for s in valid if s["jup_sell_div_bps"] is not None]
    buy_divs = [s["jup_buy_div_bps"] for s in valid if s["jup_buy_div_bps"] is not None]
    tri_bps_list = [s["tri_bps"] for s in valid if s["tri_bps"] is not None]

    def stats(vals, label):
        if not vals:
            print(f"  {label}: sem dados")
            return
        n = len(vals)
        mean = sum(vals) / n
        sorted_v = sorted(vals)
        median = sorted_v[n // 2]
        p5 = sorted_v[int(n * 0.05)]
        p95 = sorted_v[int(n * 0.95)]
        mx = max(vals)
        mn = min(vals)
        pos = sum(1 for v in vals if v > 0)
        print(f"  {label}: N={n} mean={mean:+.2f}bps median={median:+.2f}bps "
              f"P5={p5:+.2f} P95={p95:+.2f} min={mn:+.2f} max={mx:+.2f} "
              f"pos={pos}/{n} ({100*pos/n:.1f}%)")

    print("\nCEX-DEX Divergence (Jupiter vs Binance):")
    stats(sell_divs, "SOL→USDC (sell SOL on DEX vs CEX mid)")
    stats(buy_divs, "USDC→SOL (buy SOL on DEX vs CEX mid)")

    print("\nTriangular Arbitrage (SOL→USDC→SOL roundtrip):")
    stats(tri_bps_list, "Roundtrip net")

    # Key question: does the divergence ever exceed the Binance spread + Jupiter fee?
    # Jupiter fee is implicit in the quote (AMM pool fee ~0.25% = 25bps per swap)
    # For triangular: 2 swaps = ~50bps total fee
    # For CEX-DEX: need to beat Binance spread + 1 swap fee (~25bps)
    if sell_divs:
        sell_exceeds = [v for v in sell_divs if v > 25 + binance.spread_bps / 2]
        print(f"\n  SOL→USDC: {len(sell_exceeds)}/{len(sell_divs)} amostras com div > fee+spread "
              f"({25 + binance.spread_bps / 2:.1f}bps)")
    if buy_divs:
        buy_exceeds = [v for v in buy_divs if v < -(25 + binance.spread_bps / 2)]
        print(f"  USDC→SOL: {len(buy_exceeds)}/{len(buy_divs)} amostras com div < -(fee+spread) "
              f"({25 + binance.spread_bps / 2:.1f}bps)")
    if tri_bps_list:
        tri_exceeds = [v for v in tri_bps_list if v > 0]
        print(f"  Triangular: {len(tri_exceeds)}/{len(tri_bps_list)} amostras com roundtrip > 0 "
              f"(antes de gas/tx fee)")

    # Verdict
    print(f"\n{'='*100}")
    print("VEREDITO PRELIMINAR")
    print(f"{'='*100}")

    has_edge = False
    if tri_bps_list:
        mean_tri = sum(tri_bps_list) / len(tri_bps_list)
        max_tri = max(tri_bps_list)
        # Need to beat: 2x AMM fee (~50bps) + Solana tx fee (~0.000005 SOL * 2) + priority fee
        # For ~$20 size, Solana fees are negligible (~$0.001)
        if max_tri > 50:  # 50bps = approximate double AMM fee
            print(f"  Triangular: POSSIVEL EDGE — max roundtrip {max_tri:+.2f}bps > 50bps fee threshold")
            has_edge = True
        else:
            print(f"  Triangular: SEM EDGE — max roundtrip {max_tri:+.2f}bps < 50bps fee threshold")

    if sell_divs and buy_divs:
        max_sell = max(sell_divs)
        min_buy = min(buy_divs)
        # For CEX-DEX: sell on DEX at Jupiter price, simultaneously buy on Binance at ask
        # Profit = jup_sell_price - binance_ask, in bps relative to mid
        # Or: buy on DEX at Jupiter price, sell on Binance at bid
        # Profit = binance_bid - jup_buy_price
        if max_sell > 25:
            print(f"  CEX-DEX sell: POSSIVEL EDGE — max div {max_sell:+.2f}bps > 25bps AMM fee")
            has_edge = True
        else:
            print(f"  CEX-DEX sell: SEM EDGE — max div {max_sell:+.2f}bps < 25bps AMM fee")

        if -min_buy > 25:
            print(f"  CEX-DEX buy: POSSIVEL EDGE — max div {min_buy:+.2f}bps > 25bps AMM fee")
            has_edge = True
        else:
            print(f"  CEX-DEX buy: SEM EDGE — max div {min_buy:+.2f}bps < 25bps AMM fee")

    if not has_edge:
        print("\n  >>> SEM EDGE. Divergencias CEX-DEX e triangular nao superam fees+spread.")
    else:
        print("\n  >>> EDGE CANDIDATO DETECTADO. Necessita validacao com execucacao real.")

    # Save samples to JSON
    out_file = "dex_arb_samples.json"
    with open(out_file, "w") as f:
        json.dump(samples, f, indent=2, default=str)
    print(f"\nAmostras salvas em {out_file}")

    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-min", type=float, default=30.0,
                        help="Duracao do scan em minutos (default: 30)")
    parser.add_argument("--interval-s", type=float, default=2.0,
                        help="Intervalo entre amostras em segundos (default: 2)")
    parser.add_argument("--sol-amount", type=float, default=1.0,
                        help="Tamanho do swap em SOL (default: 1.0)")
    args = parser.parse_args()

    asyncio.run(scan_loop(
        duration_s=int(args.duration_min * 60),
        interval_s=args.interval_s,
        sol_amount=args.sol_amount,
    ))


if __name__ == "__main__":
    main()
