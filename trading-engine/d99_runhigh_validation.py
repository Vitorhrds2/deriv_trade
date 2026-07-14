"""D99 — RUNHIGH/RUNLOW Validation Probe.

D97 descobriu que RUNHIGH/RUNLOW tem payout ratios extremamente altos:
  - 2 ticks: 3.82x (breakeven P=26.18%, teorico P=50%)
  - 3 ticks: 7.63x (breakeven P=13.11%, teorico P=33.33%)
  - 5 ticks: 30.53x (breakeven P=3.28%, teorico P=20%)

Para random walk simetrico, P(ultimo tick = maximo) = 1/n por simetria.
Se confirmado, EV e massivamente positivo em todas as duracoes.

Este probe compra N contratos RUNHIGH + N contratos RUNLOW em DEMO,
mede a win rate real, e calcula EV com IC95% de Wilson.

Uso
---
    python d99_runhigh_validation.py --trades 50 --duration 5
    python d99_runhigh_validation.py --trades 100 --duration 3 --symbol 1HZ10V
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient


def wilson_interval(s, n, z=1.96):
    if n == 0:
        return 0, 0
    p = s / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0, center - margin), min(1, center + margin)


async def buy_and_wait(client, contract_type, symbol, duration, stake):
    """Compra contrato e aguarda settlement. Retorna (won, profit, payout, details)."""
    payload = {
        "proposal": 1,
        "amount": stake,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": "t",
    }
    try:
        prop_res = await client.send_request(payload)
    except Exception as e:
        return {"error": f"proposal_failed: {e}"}
    if "error" in prop_res:
        return {"error": f"proposal_error: {prop_res['error'].get('message','')}"}

    proposal = prop_res.get("proposal", {})
    proposal_id = proposal.get("id")
    ask_price = proposal.get("ask_price")
    payout = proposal.get("payout")
    longcode = proposal.get("longcode", "")

    if not proposal_id or not ask_price:
        return {"error": "no proposal id/ask"}

    try:
        buy_res = await client.send_request({"buy": proposal_id, "price": ask_price})
    except Exception as e:
        return {"error": f"buy_failed: {e}"}
    if "error" in buy_res:
        return {"error": f"buy_error: {buy_res['error'].get('message','')}"}

    buy = buy_res.get("buy", {})
    contract_id = buy.get("contract_id")
    buy_price = buy.get("buy_price")
    entry_spot = buy.get("start_time")

    # Aguarda settlement (duration ticks + buffer)
    # 1HZ ticks = 1s, R_ ticks = 2s. Buffer = duration * 3 + 10
    wait_time = max(duration * 3 + 10, 15)
    await asyncio.sleep(wait_time)

    # Poll para resultado
    for attempt in range(20):
        try:
            res = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
        except Exception:
            await asyncio.sleep(2)
            continue
        contract = res.get("proposal_open_contract", {})
        if not contract:
            await asyncio.sleep(2)
            continue
        if contract.get("is_sold") or contract.get("is_settled"):
            profit = float(contract.get("profit", 0))
            status = contract.get("status", "")
            exit_spot = contract.get("exit_tick")
            entry_spot_val = contract.get("entry_spot")
            return {
                "contract_id": contract_id,
                "won": profit > 0,
                "profit": profit,
                "payout": payout,
                "buy_price": buy_price,
                "ask_price": ask_price,
                "status": status,
                "longcode": longcode,
                "entry_spot": entry_spot_val,
                "exit_spot": exit_spot,
            }
        await asyncio.sleep(2)

    return {"error": "timeout", "contract_id": contract_id}


async def main():
    parser = argparse.ArgumentParser(description="D99 RUNHIGH/RUNLOW Validation")
    parser.add_argument("--trades", type=int, default=50, help="Trades per contract type")
    parser.add_argument("--duration", type=int, default=5, help="Duration in ticks")
    parser.add_argument("--symbol", default="1HZ10V")
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--output", default="d99_runhigh_validation_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    print(f"D99 — RUNHIGH/RUNLOW Validation Probe", flush=True)
    print(f"Symbol: {args.symbol} | Duration: {args.duration}t | Stake: ${args.stake}", flush=True)
    print(f"Trades per type: {args.trades} | Total: {args.trades * 2}", flush=True)

    # Theoretical values
    n_ticks = args.duration
    p_theoretical = 1.0 / n_ticks
    print(f"Theoretical P(win) = 1/{n_ticks} = {p_theoretical:.4f} ({p_theoretical*100:.2f}%)", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    # Get current payout ratio
    for ct in ["RUNHIGH", "RUNLOW"]:
        payload = {
            "proposal": 1,
            "amount": args.stake,
            "basis": "stake",
            "contract_type": ct,
            "currency": "USD",
            "underlying_symbol": args.symbol,
            "duration": args.duration,
            "duration_unit": "t",
        }
        try:
            res = await client.send_request(payload)
            if "proposal" in res:
                p = res["proposal"]
                print(f"  {ct}: ask=${p['ask_price']:.2f} payout=${p['payout']:.2f} "
                      f"ratio={p['payout']/p['ask_price']:.4f} breakeven={p['ask_price']/p['payout']*100:.2f}%", flush=True)
                print(f"    longcode: {p.get('longcode','')}", flush=True)
        except Exception:
            pass
        await asyncio.sleep(0.5)

    results = {"RUNHIGH": [], "RUNLOW": []}

    for ct in ["RUNHIGH", "RUNLOW"]:
        print(f"\n--- Trading {ct} ({args.trades} trades) ---", flush=True)
        wins = 0
        losses = 0
        errors = 0
        total_profit = 0.0

        for i in range(args.trades):
            r = await buy_and_wait(client, ct, args.symbol, args.duration, args.stake)
            if "error" in r:
                errors += 1
                results[ct].append(r)
                print(f"  [{i+1}/{args.trades}] ERROR: {r['error']}", flush=True)
            else:
                results[ct].append(r)
                if r["won"]:
                    wins += 1
                    total_profit += r["profit"]
                    print(f"  [{i+1}/{args.trades}] WIN +${r['profit']:.2f} (exit={r.get('exit_spot')})", flush=True)
                else:
                    losses += 1
                    total_profit += r["profit"]
                    print(f"  [{i+1}/{args.trades}] LOSS ${r['profit']:.2f} (exit={r.get('exit_spot')})", flush=True)

                settled = wins + losses
                if settled > 0:
                    wr = wins / settled
                    p_lo, p_hi = wilson_interval(wins, settled)
                    print(f"    Running: WR={wr*100:.1f}% CI=[{p_lo*100:.1f}%,{p_hi*100:.1f}%] "
                          f"PnL=${total_profit:.2f} (n={settled})", flush=True)

            await asyncio.sleep(1)

    await client.disconnect()

    # Final analysis
    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D99",
        "description": "RUNHIGH/RUNLOW validation with demo trades",
        "symbol": args.symbol,
        "duration": args.duration,
        "stake": args.stake,
        "trades_per_type": args.trades,
        "theoretical_p_win": p_theoretical,
        "results": {},
    }

    for ct in ["RUNHIGH", "RUNLOW"]:
        ct_results = [r for r in results[ct] if "error" not in r]
        errors_list = [r for r in results[ct] if "error" in r]
        wins = sum(1 for r in ct_results if r["won"])
        losses = len(ct_results) - wins
        n = len(ct_results)
        total_profit = sum(r["profit"] for r in ct_results)

        if n > 0:
            wr = wins / n
            p_lo, p_hi = wilson_interval(wins, n)
            avg_payout = ct_results[0]["payout"] if ct_results else 0
            avg_ask = ct_results[0]["ask_price"] if ct_results else 0
            breakeven_p = avg_ask / avg_payout if avg_payout > 0 else 0
            ev = wr * avg_payout - avg_ask
            ev_lo = p_lo * avg_payout - avg_ask
            ev_hi = p_hi * avg_payout - avg_ask
        else:
            wr = 0
            p_lo = p_hi = 0
            ev = ev_lo = ev_hi = 0
            breakeven_p = 0

        output["results"][ct] = {
            "n_valid": n,
            "n_errors": len(errors_list),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wr, 4),
            "win_rate_ci95": [round(p_lo, 4), round(p_hi, 4)],
            "theoretical_p_win": round(p_theoretical, 4),
            "breakeven_p_win": round(breakeven_p, 4),
            "total_profit": round(total_profit, 4),
            "ev_per_trade": round(ev, 4),
            "ev_ci95": [round(ev_lo, 4), round(ev_hi, 4)],
            "verdict": "EDGE" if p_lo > breakeven_p else ("INCONCLUSIVE" if p_hi > breakeven_p else "REFUTED"),
            "payout": avg_payout,
            "ask_price": avg_ask,
        }

        print(f"\n=== {ct} FINAL ===", flush=True)
        print(f"  Valid: {n} | Wins: {wins} | Losses: {losses}", flush=True)
        print(f"  WR: {wr*100:.1f}% CI=[{p_lo*100:.1f}%,{p_hi*100:.1f}%]", flush=True)
        print(f"  Theoretical: {p_theoretical*100:.1f}% | Breakeven: {breakeven_p*100:.2f}%", flush=True)
        print(f"  EV: ${ev:.4f} CI=[${ev_lo:.4f}, ${ev_hi:.4f}]", flush=True)
        print(f"  Total PnL: ${total_profit:.2f}", flush=True)
        print(f"  Verdict: {output['results'][ct]['verdict']}", flush=True)

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
