"""D98 — Instant Resale Flip Scanner.

Hipotese
--------
O preco de resale de um contrato imediatamente apos compra pode exceder o preco de
compra para certos tipos de contrato ou condicoes de mercado. Se resale > buy para
qualquer combinacao, e flip instantâneo (dinheiro gratis).

Nunca testado sistematicamente. D90 testa early-sell vs hold para duracoes longas,
mas nao testa flip instantâneo (resale imediatamente apos buy).

Testa:
  - 10 contract types x 5 durations x 5 symbols = 250 cells
  - Para cada cell: buy DEMO contract, checar resale price imediatamente
  - Se resale_price > buy_price => EDGE (flip instantâneo)
  - Se resale_price / buy_price > 0.99 => quase-break-even (potential edge apos fees)

Uso
---
    python d98_resale_flip_scan.py
    python d98_resale_flip_scan.py --symbols 1HZ10V,R_10 --trades-per-cell 3

Output: d98_resale_flip_results.json
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

SYMBOLS_DEFAULT = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_100"]

CONTRACT_TYPES = [
    ("CALL", None),
    ("PUT", None),
    ("CALLE", None),
    ("PUTE", None),
    ("DIGITEVEN", None),
    ("DIGITODD", None),
    ("DIGITOVER", "5"),
    ("DIGITUNDER", "4"),
    ("EXPIRYMISS", None),
    ("EXPIRYRANGE", None),
]

DURATIONS = [5, 10, 25, 50, 100]
STAKE = 1.0


async def get_proposal_and_buy(client, symbol, contract_type, duration, barrier=None):
    """Obtem proposta e compra o contrato. Retorna (contract_id, buy_price) ou None.
    Tenta proposal->buy primeiro, fallback para buy_direct se proposal expirar.
    """
    payload = {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": "t",
    }
    if barrier is not None:
        payload["barrier"] = str(barrier)

    try:
        prop_res = await client.send_request(payload)
    except Exception:
        return None
    if "error" in prop_res:
        return None
    proposal = prop_res.get("proposal", {})
    proposal_id = proposal.get("id")
    ask_price = proposal.get("ask_price")
    payout = proposal.get("payout")
    if not proposal_id or not ask_price:
        return None

    # Try proposal-based buy first
    try:
        buy_res = await client.send_request({"buy": proposal_id, "price": ask_price})
    except Exception:
        # Fallback: buy_direct (no proposal_id needed)
        try:
            buy_res = await client.buy_direct(
                contract_type, STAKE, symbol=symbol,
                duration=duration, duration_unit="t", barrier=barrier
            )
        except Exception:
            return None
    if "error" in buy_res:
        # Fallback: buy_direct
        try:
            buy_res = await client.buy_direct(
                contract_type, STAKE, symbol=symbol,
                duration=duration, duration_unit="t", barrier=barrier
            )
        except Exception:
            return None
    if "error" in buy_res:
        return None
    buy = buy_res.get("buy", {})
    contract_id = buy.get("contract_id")
    buy_price = buy.get("buy_price")
    if not contract_id:
        return None

    return {
        "contract_id": contract_id,
        "buy_price": buy_price,
        "ask_price": ask_price,
        "payout": payout,
    }


async def check_resale_price(client, contract_id, max_retries=5):
    """Checa o preco de resale do contrato. Retorna resale_price ou None.
    Uses bid_price (the price at which you can sell back the contract).
    Falls back to ask_price if bid_price is not available.
    """
    for attempt in range(max_retries):
        try:
            res = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
        except Exception:
            await asyncio.sleep(1)
            continue
        contract = res.get("proposal_open_contract", {})
        if not contract:
            await asyncio.sleep(1)
            continue
        is_sold = contract.get("is_sold", False)
        if is_sold:
            return {"resale_price": 0, "is_sold": True, "status": contract.get("status")}
        # bid_price is the resale (sell-back) price
        resale_price = contract.get("bid_price")
        if resale_price is None:
            # Fallback: some contracts use ask_price as current market price
            resale_price = contract.get("ask_price")
        if resale_price is not None:
            return {"resale_price": float(resale_price), "is_sold": False}
        await asyncio.sleep(1)
    return None


async def sell_contract(client, contract_id):
    """Vende o contrato para fechar a posicao."""
    try:
        res = await client.send_request({"sell": contract_id, "price": 0})
        return res
    except Exception:
        return None


async def scan_cell(client, symbol, contract_type, duration, barrier, trades_per_cell):
    """Testa flip instantâneo para uma celula especifica."""
    results = []
    for trade_idx in range(trades_per_cell):
        buy_info = await get_proposal_and_buy(client, symbol, contract_type, duration, barrier)
        if not buy_info:
            results.append({"error": "buy_failed"})
            await asyncio.sleep(1)
            continue

        # Checa resale imediatamente
        await asyncio.sleep(1.5)  # Delay para o contrato processar no servidor
        resale = await check_resale_price(client, buy_info["contract_id"])

        if not resale:
            results.append({
                "contract_id": buy_info["contract_id"],
                "buy_price": buy_info["buy_price"],
                "error": "resale_check_failed",
            })
        elif resale.get("is_sold"):
            results.append({
                "contract_id": buy_info["contract_id"],
                "buy_price": buy_info["buy_price"],
                "error": "already_sold",
                "status": resale.get("status"),
            })
        else:
            resale_price = resale["resale_price"]
            buy_price = buy_info["buy_price"]
            flip_profit = resale_price - buy_price
            flip_ratio = resale_price / buy_price if buy_price > 0 else 0

            results.append({
                "contract_id": buy_info["contract_id"],
                "buy_price": buy_price,
                "resale_price": resale_price,
                "flip_profit": round(flip_profit, 6),
                "flip_ratio": round(flip_ratio, 6),
                "is_flip": flip_profit > 0,
                "payout": buy_info.get("payout"),
            })

        # Vende o contrato para limpar a posicao
        await sell_contract(client, buy_info["contract_id"])
        await asyncio.sleep(1)

    return results


async def main():
    parser = argparse.ArgumentParser(description="D98 Instant Resale Flip Scanner")
    parser.add_argument("--symbols", default=",".join(SYMBOLS_DEFAULT))
    parser.add_argument("--trades-per-cell", type=int, default=3)
    parser.add_argument("--output", default="d98_resale_flip_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"D98 — Instant Resale Flip Scanner", flush=True)
    print(f"Symbols: {symbols}", flush=True)
    print(f"Contract types: {[ct for ct, _ in CONTRACT_TYPES]}", flush=True)
    print(f"Durations: {DURATIONS}", flush=True)
    print(f"Trades per cell: {args.trades_per_cell}", flush=True)
    print(f"Stake: ${STAKE}", flush=True)

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required for DEMO trades", flush=True)
        return

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    all_results = []
    flip_edges = []

    for sym in symbols:
        for ct, barrier in CONTRACT_TYPES:
            for dur in DURATIONS:
                cell_key = f"{sym}_{ct}_{dur}t"
                print(f"  Testing {cell_key}...", flush=True)
                cell_results = await scan_cell(
                    client, sym, ct, dur, barrier, args.trades_per_cell
                )

                valid = [r for r in cell_results if "error" not in r]
                flips = [r for r in valid if r.get("is_flip")]

                cell_summary = {
                    "symbol": sym,
                    "contract_type": ct,
                    "duration": dur,
                    "barrier": barrier,
                    "trades": len(cell_results),
                    "valid": len(valid),
                    "flips": len(flips),
                    "avg_flip_profit": round(
                        sum(r["flip_profit"] for r in valid) / len(valid), 6
                    ) if valid else 0,
                    "avg_flip_ratio": round(
                        sum(r["flip_ratio"] for r in valid) / len(valid), 6
                    ) if valid else 0,
                    "details": cell_results,
                }
                all_results.append(cell_summary)

                if flips:
                    flip_edges.append(cell_summary)
                    print(f"    !!! FLIP EDGE: {len(flips)}/{len(valid)} trades profitable!", flush=True)
                elif valid:
                    avg_ratio = sum(r["flip_ratio"] for r in valid) / len(valid)
                    if avg_ratio > 0.99:
                        print(f"    ~ Near break-even: avg_ratio={avg_ratio:.4f}", flush=True)

                await asyncio.sleep(0.5)

    await client.disconnect()

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D98",
        "description": "Instant resale flip scanner",
        "symbols_tested": len(symbols),
        "cells_tested": len(all_results),
        "trades_per_cell": args.trades_per_cell,
        "stake": STAKE,
        "flip_edges_found": len(flip_edges),
        "flip_edges": [
            {
                "symbol": e["symbol"],
                "contract_type": e["contract_type"],
                "duration": e["duration"],
                "flips": e["flips"],
                "valid": e["valid"],
                "avg_flip_profit": e["avg_flip_profit"],
                "avg_flip_ratio": e["avg_flip_ratio"],
            }
            for e in flip_edges
        ],
        "all_cells": all_results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n=== SUMMARY ===", flush=True)
    print(f"Cells tested: {len(all_results)}", flush=True)
    print(f"Flip edges found: {len(flip_edges)}", flush=True)
    if flip_edges:
        print(f"\nEDGE CELLS:", flush=True)
        for e in flip_edges:
            print(f"  {e['symbol']} {e['contract_type']} dur={e['duration']}t "
                  f"flips={e['flips']}/{e['valid']} avg_profit=${e['avg_flip_profit']:.4f}", flush=True)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
