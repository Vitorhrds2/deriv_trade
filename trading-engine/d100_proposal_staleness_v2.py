"""D100 — Proposal Staleness Exploit v2 (Race between proposal and buy).

Hipotese
--------
D47 testou stale proposal com delay de 20s e encontrou que barriers sao sempre
recalculados. D54 testou proposal subscribe:1 e descobriu que nunca reenvia.
Mas nenhum testou a janela CRITICA entre proposal request e buy execution em
alta frequencia.

Se o spot se move FAVORAVELMENTE entre o momento do proposal e o buy (mesmo que
~100ms), o ask_price pode estar desatualizado e podemos comprar abaixo do fair
value. D47 esperou 20s (tempo demais para o servidor recalcular). Este teste
mede o race em escala de milissegundos.

Testa:
  1. Para cada trial: pede proposal, imediatamente compra (sem delay)
  2. Compara entry_spot (spot real no momento da compra) vs spot no proposal
  3. Se entry_spot > proposal_spot para CALL (ou < para PUT), capturamos favor
  4. Mede lag entre proposal e buy em ms
  5. Compara com CONTROL: espera 2s entre proposal e buy

Uso
---
    python d100_proposal_staleness_v2.py --trials 100
    python d100_proposal_staleness_v2.py --trials 50 --symbol 1HZ10V --duration 10
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


async def trial_race(client, symbol, contract_type, duration, stake, delay_ms=0):
    """Single trial: proposal -> wait delay_ms -> buy -> check entry vs proposal spot."""
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

    t0 = time.monotonic()
    try:
        prop_res = await client.send_request(payload)
    except Exception as e:
        return {"error": f"proposal_failed: {e}"}
    t_prop = time.monotonic()

    if "error" in prop_res:
        return {"error": f"proposal_error: {prop_res['error'].get('message', '')}"}

    proposal = prop_res.get("proposal", {})
    proposal_id = proposal.get("id")
    ask_price = proposal.get("ask_price")
    payout = proposal.get("payout")
    proposal_spot = proposal.get("spot")
    proposal_spot_time = proposal.get("spot_time")

    if not proposal_id or not ask_price:
        return {"error": "no proposal id/ask"}

    # Wait the specified delay
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)

    t_buy_start = time.monotonic()
    try:
        buy_res = await client.send_request({"buy": proposal_id, "price": ask_price})
    except Exception as e:
        return {"error": f"buy_failed: {e}"}
    t_buy_end = time.monotonic()

    if "error" in buy_res:
        return {"error": f"buy_error: {buy_res['error'].get('message', '')}"}

    buy = buy_res.get("buy", {})
    contract_id = buy.get("contract_id")
    buy_price = buy.get("buy_price")
    entry_spot = buy.get("start_time")  # timestamp of entry
    transaction_time = buy.get("purchase_time")

    # Poll for contract details to get entry_spot price
    await asyncio.sleep(1)
    entry_price = None
    for attempt in range(5):
        try:
            res = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            contract = res.get("proposal_open_contract", {})
            entry_price = contract.get("entry_spot")
            if entry_price is not None:
                break
        except Exception:
            pass
        await asyncio.sleep(1)

    # Wait for settlement
    wait_time = max(duration * 3 + 10, 15)
    await asyncio.sleep(wait_time)

    # Get result
    won = None
    profit = None
    for attempt in range(10):
        try:
            res = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            contract = res.get("proposal_open_contract", {})
            if contract.get("is_sold"):
                profit = float(contract.get("profit", 0))
                won = profit > 0
                break
        except Exception:
            pass
        await asyncio.sleep(2)

    # Sell if not settled
    if won is None:
        try:
            await client.send_request({"sell": contract_id, "price": 0})
        except Exception:
            pass

    prop_to_buy_ms = (t_buy_end - t_prop) * 1000

    # Calculate if we captured favorable movement
    spot_diff = None
    captured_favor = None
    if proposal_spot and entry_price:
        try:
            spot_diff = float(entry_price) - float(proposal_spot)
            if contract_type in ("CALL", "CALLE", "HIGHER"):
                captured_favor = spot_diff < 0  # entry lower than proposal = favorable for CALL
            elif contract_type in ("PUT", "PUTE", "LOWER"):
                captured_favor = spot_diff > 0  # entry higher than proposal = favorable for PUT
        except (ValueError, TypeError):
            pass

    return {
        "contract_id": contract_id,
        "proposal_spot": proposal_spot,
        "entry_price": entry_price,
        "spot_diff": round(spot_diff, 8) if spot_diff is not None else None,
        "captured_favor": captured_favor,
        "ask_price": ask_price,
        "buy_price": buy_price,
        "payout": payout,
        "won": won,
        "profit": profit,
        "prop_to_buy_ms": round(prop_to_buy_ms, 1),
        "delay_ms": delay_ms,
    }


async def main():
    parser = argparse.ArgumentParser(description="D100 Proposal Staleness v2")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--symbol", default="1HZ10V")
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--output", default="d100_proposal_staleness_v2_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    print(f"D100 — Proposal Staleness Exploit v2", flush=True)
    print(f"Symbol: {args.symbol} | Duration: {args.duration}t | Stake: ${args.stake}", flush=True)
    print(f"Trials: {args.trials} (50% RACE=0ms, 50% CONTROL=2000ms)", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    results = []
    for i in range(args.trials):
        # Alternate CALL and PUT, RACE (0ms) and CONTROL (2000ms)
        ct = "CALL" if i % 2 == 0 else "PUT"
        delay = 0 if i % 4 < 2 else 2000  # 50% race, 50% control
        label = "RACE" if delay == 0 else "CONTROL"

        r = await trial_race(client, args.symbol, ct, args.duration, args.stake, delay)
        r["trial"] = i + 1
        r["contract_type"] = ct
        r["group"] = label
        results.append(r)

        if "error" in r:
            print(f"  [{i+1}/{args.trials}] {label} {ct} ERROR: {r['error']}", flush=True)
        else:
            favor_str = "FAVOR" if r.get("captured_favor") else "AGAINST" if r.get("captured_favor") is False else "?"
            won_str = "WIN" if r.get("won") else "LOSS" if r.get("won") is False else "?"
            print(f"  [{i+1}/{args.trials}] {label} {ct} {won_str} "
                  f"spot_diff={r.get('spot_diff','?')} {favor_str} "
                  f"lag={r.get('prop_to_buy_ms','?')}ms profit=${r.get('profit','?')}", flush=True)

        await asyncio.sleep(0.5)

    await client.disconnect()

    # Analysis
    race_results = [r for r in results if r.get("group") == "RACE" and "error" not in r]
    control_results = [r for r in results if r.get("group") == "CONTROL" and "error" not in r]

    def summarize(rs, label):
        if not rs:
            return {"label": label, "n": 0}
        n = len(rs)
        wins = sum(1 for r in rs if r.get("won"))
        losses = sum(1 for r in rs if r.get("won") is False)
        total_profit = sum(r.get("profit", 0) for r in rs if r.get("profit") is not None)
        favors = sum(1 for r in rs if r.get("captured_favor") is True)
        against = sum(1 for r in rs if r.get("captured_favor") is False)
        avg_lag = sum(r.get("prop_to_buy_ms", 0) for r in rs) / n

        wr = wins / n if n > 0 else 0
        wr_lo, wr_hi = wilson_interval(wins, n)

        return {
            "label": label,
            "n": n,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wr, 4),
            "win_rate_ci95": [round(wr_lo, 4), round(wr_hi, 4)],
            "total_profit": round(total_profit, 4),
            "ev_per_trade": round(total_profit / n, 4) if n > 0 else 0,
            "favors": favors,
            "against": against,
            "favor_rate": round(favors / n, 4) if n > 0 else 0,
            "avg_lag_ms": round(avg_lag, 1),
        }

    race_summary = summarize(race_results, "RACE")
    control_summary = summarize(control_results, "CONTROL")

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D100",
        "description": "Proposal staleness exploit v2 — race between proposal and buy",
        "symbol": args.symbol,
        "duration": args.duration,
        "stake": args.stake,
        "trials": args.trials,
        "race_summary": race_summary,
        "control_summary": control_summary,
        "results": results,
    }

    print(f"\n=== RACE (0ms delay) ===", flush=True)
    print(f"  N={race_summary['n']} WR={race_summary.get('win_rate',0)*100:.1f}% "
          f"EV=${race_summary.get('ev_per_trade',0):.4f} "
          f"Favors={race_summary.get('favors',0)}/{race_summary.get('n',0)} "
          f"AvgLag={race_summary.get('avg_lag_ms',0):.1f}ms", flush=True)

    print(f"\n=== CONTROL (2000ms delay) ===", flush=True)
    print(f"  N={control_summary['n']} WR={control_summary.get('win_rate',0)*100:.1f}% "
          f"EV=${control_summary.get('ev_per_trade',0):.4f} "
          f"Favors={control_summary.get('favors',0)}/{control_summary.get('n',0)}", flush=True)

    # Verdict
    if race_summary["n"] > 10 and control_summary["n"] > 10:
        race_wr = race_summary["win_rate"]
        ctrl_wr = control_summary["win_rate"]
        if race_wr - ctrl_wr > 0.05:
            verdict = "EDGE: RACE WR > CONTROL WR by >5%"
        elif race_wr - ctrl_wr < -0.05:
            verdict = "REFUTED: RACE WR < CONTROL WR (staleness hurts)"
        else:
            verdict = "INCONCLUSIVE: No significant WR difference"
        output["verdict"] = verdict
        print(f"\nVerdict: {verdict}", flush=True)

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
