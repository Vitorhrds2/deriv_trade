"""D101 — Barrier Proximity Edge (DIGITOVER/DIGITUNDER near barrier).

Hipotese
--------
Para DIGITOVER/DIGITUNDER, o contrato ganha se o último dígito do preço está
acima/abaixo de uma barreira. A Deriv usa a precisão decimal do símbolo para
determinar o "dígito". Se o preço está muito próximo da barreira (último dígito
próximo do limiar), a probabilidade de cruzar pode não ser 50/50 devido ao
tamanho do tick.

Exemplo: DIGITOVER barrier=5 em 1HZ10V (2 casas decimais). Se o preço está em
X.XX5, o próximo tick pode arredondar para X.XX4 ou X.XX6. Se o tick size é
assimétrico em relação ao dígito, pode haver edge.

Adicionalmente, testa se a Deriv precifica DIGITOVER/DIGITUNDER corretamente
para todas as barreiras (0-9). Se alguma barreira tiver payout anômalo, é
mispricing.

Testa:
  1. Scan payout ratios para DIGITOVER/DIGITUNDER com barreiras 0-9
  2. Compara payout ratio entre barreiras (deveria ser ~constante)
  3. Se alguma barreira tiver payout ratio significativamente diferente, flag
  4. Live DEMO: compra DIGITOVER/DIGITUNDER para barreiras extremas (0 e 9)
     e mede win rate real vs teórico (50%)

Uso
---
    python d101_barrier_proximity_edge.py --trials 50
    python d101_barrier_proximity_edge.py --trials 30 --symbol 1HZ10V
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections import defaultdict
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


async def scan_barrier_payouts(client, symbol, duration, stake):
    """Scan payout ratios for DIGITOVER/DIGITUNDER with barriers 0-9."""
    results = []
    for barrier in range(10):
        for ct in ["DIGITOVER", "DIGITUNDER"]:
            payload = {
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": ct,
                "currency": "USD",
                "underlying_symbol": symbol,
                "duration": duration,
                "duration_unit": "t",
                "barrier": str(barrier),
            }
            try:
                res = await client.send_request(payload)
            except Exception:
                continue
            if "error" in res:
                continue
            p = res.get("proposal", {})
            ask = p.get("ask_price")
            payout = p.get("payout")
            if ask and payout:
                results.append({
                    "contract_type": ct,
                    "barrier": barrier,
                    "ask_price": ask,
                    "payout": payout,
                    "payout_ratio": payout / ask,
                    "longcode": p.get("longcode", ""),
                })
            await asyncio.sleep(0.2)
    return results


async def buy_and_wait(client, symbol, contract_type, duration, stake, barrier):
    """Buy contract and wait for settlement."""
    payload = {
        "proposal": 1,
        "amount": stake,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": "t",
        "barrier": str(barrier),
    }
    try:
        prop_res = await client.send_request(payload)
    except Exception as e:
        return {"error": f"proposal_failed: {e}"}
    if "error" in prop_res:
        return {"error": f"proposal_error: {prop_res['error'].get('message', '')}"}

    proposal = prop_res.get("proposal", {})
    proposal_id = proposal.get("id")
    ask_price = proposal.get("ask_price")
    payout = proposal.get("payout")
    longcode = proposal.get("longcode", "")

    if not proposal_id:
        return {"error": "no proposal id"}

    try:
        buy_res = await client.send_request({"buy": proposal_id, "price": ask_price})
    except Exception as e:
        return {"error": f"buy_failed: {e}"}
    if "error" in buy_res:
        return {"error": f"buy_error: {buy_res['error'].get('message', '')}"}

    buy = buy_res.get("buy", {})
    contract_id = buy.get("contract_id")
    buy_price = buy.get("buy_price")

    # Wait for settlement
    wait_time = max(duration * 3 + 10, 15)
    await asyncio.sleep(wait_time)

    for attempt in range(15):
        try:
            res = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            contract = res.get("proposal_open_contract", {})
            if contract.get("is_sold"):
                profit = float(contract.get("profit", 0))
                exit_tick = contract.get("exit_tick")
                entry_spot = contract.get("entry_spot")
                return {
                    "contract_id": contract_id,
                    "won": profit > 0,
                    "profit": profit,
                    "payout": payout,
                    "buy_price": buy_price,
                    "ask_price": ask_price,
                    "barrier": barrier,
                    "entry_spot": entry_spot,
                    "exit_tick": exit_tick,
                    "longcode": longcode,
                }
        except Exception:
            pass
        await asyncio.sleep(2)

    return {"error": "timeout", "contract_id": contract_id}


async def main():
    parser = argparse.ArgumentParser(description="D101 Barrier Proximity Edge")
    parser.add_argument("--trials", type=int, default=50, help="Trades per barrier")
    parser.add_argument("--symbol", default="1HZ10V")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--output", default="d101_barrier_proximity_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    print(f"D101 — Barrier Proximity Edge (DIGITOVER/DIGITUNDER)", flush=True)
    print(f"Symbol: {args.symbol} | Duration: {args.duration}t | Stake: ${args.stake}", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    # Phase 1: Scan payout ratios for all barriers
    print(f"\n--- Phase 1: Payout ratio scan ---", flush=True)
    scan_results = await scan_barrier_payouts(client, args.symbol, args.duration, args.stake)

    print(f"\nBarrier payout ratios:", flush=True)
    over_ratios = {}
    under_ratios = {}
    for r in scan_results:
        print(f"  {r['contract_type']:12s} barrier={r['barrier']} "
              f"ask=${r['ask_price']:.2f} payout=${r['payout']:.2f} "
              f"ratio={r['payout_ratio']:.4f}", flush=True)
        if r["contract_type"] == "DIGITOVER":
            over_ratios[r["barrier"]] = r
        else:
            under_ratios[r["barrier"]] = r

    # Check for anomalies
    all_ratios = [r["payout_ratio"] for r in scan_results]
    if all_ratios:
        mean_r = sum(all_ratios) / len(all_ratios)
        std_r = math.sqrt(sum((x - mean_r) ** 2 for x in all_ratios) / len(all_ratios))
        print(f"\nMean ratio: {mean_r:.4f} | Std: {std_r:.4f}", flush=True)
        anomalies = [r for r in scan_results if abs(r["payout_ratio"] - mean_r) > 2 * std_r]
        if anomalies:
            print(f"ANOMALIES (>2std from mean):", flush=True)
            for a in anomalies:
                print(f"  {a['contract_type']} barrier={a['barrier']} ratio={a['payout_ratio']:.4f}", flush=True)
        else:
            print(f"No anomalies — payout ratio consistent across barriers", flush=True)

    # Phase 2: Live trades for extreme barriers (0 and 9)
    # DIGITOVER barrier=0: wins if digit > 0 (90% theoretical)
    # DIGITOVER barrier=9: wins if digit > 9 (0% theoretical — should never win)
    # DIGITUNDER barrier=0: wins if digit < 0 (0% theoretical — should never win)
    # DIGITUNDER barrier=9: wins if digit < 9 (90% theoretical)
    # Interesting barriers: 4, 5, 6 (near 50/50)
    test_barriers = [
        ("DIGITOVER", 0),   # 90% theoretical
        ("DIGITUNDER", 9),  # 90% theoretical
        ("DIGITOVER", 4),   # 60% theoretical
        ("DIGITUNDER", 5),  # 50% theoretical
        ("DIGITOVER", 5),   # 50% theoretical
        ("DIGITUNDER", 4),  # 50% theoretical
    ]

    print(f"\n--- Phase 2: Live DEMO trades ---", flush=True)
    live_results = {}
    for ct, barrier in test_barriers:
        key = f"{ct}_{barrier}"
        print(f"\n  Testing {key} ({args.trials} trades)...", flush=True)
        live_results[key] = []
        wins = 0
        total_profit = 0.0

        for i in range(args.trials):
            r = await buy_and_wait(client, args.symbol, ct, args.duration, args.stake, barrier)
            if "error" in r:
                live_results[key].append(r)
                print(f"    [{i+1}/{args.trials}] ERROR: {r['error']}", flush=True)
            else:
                live_results[key].append(r)
                if r["won"]:
                    wins += 1
                    total_profit += r["profit"]
                    print(f"    [{i+1}/{args.trials}] WIN +${r['profit']:.2f} exit={r.get('exit_tick')}", flush=True)
                else:
                    total_profit += r["profit"]
                    print(f"    [{i+1}/{args.trials}] LOSS ${r['profit']:.2f} exit={r.get('exit_tick')}", flush=True)

                settled = wins + (i + 1 - wins - sum(1 for x in live_results[key] if "error" in x))
                if settled > 0:
                    wr = wins / settled
                    print(f"      Running WR={wr*100:.1f}% PnL=${total_profit:.2f} (n={settled})", flush=True)

            await asyncio.sleep(0.5)

    await client.disconnect()

    # Analysis
    barrier_analysis = {}
    for ct, barrier in test_barriers:
        key = f"{ct}_{barrier}"
        valid = [r for r in live_results[key] if "error" not in r]
        n = len(valid)
        wins = sum(1 for r in valid if r.get("won"))
        total_profit = sum(r.get("profit", 0) for r in valid)

        # Theoretical P(win)
        if ct == "DIGITOVER":
            p_theoretical = (9 - barrier) / 10  # digits barrier+1 to 9
        else:
            p_theoretical = barrier / 10  # digits 0 to barrier-1

        wr = wins / n if n > 0 else 0
        wr_lo, wr_hi = wilson_interval(wins, n)

        # Get payout ratio from scan
        scan_data = over_ratios.get(barrier) if ct == "DIGITOVER" else under_ratios.get(barrier)
        payout = scan_data["payout"] if scan_data else 0
        ask = scan_data["ask_price"] if scan_data else 0
        breakeven_p = ask / payout if payout > 0 else 0
        ev = wr * payout - ask if payout > 0 else 0

        barrier_analysis[key] = {
            "contract_type": ct,
            "barrier": barrier,
            "n_valid": n,
            "wins": wins,
            "win_rate": round(wr, 4),
            "win_rate_ci95": [round(wr_lo, 4), round(wr_hi, 4)],
            "theoretical_p_win": round(p_theoretical, 4),
            "breakeven_p_win": round(breakeven_p, 4),
            "payout": payout,
            "ask_price": ask,
            "ev_per_trade": round(ev, 4),
            "total_profit": round(total_profit, 4),
            "verdict": "EDGE" if wr_lo > breakeven_p else ("INCONCLUSIVE" if wr_hi > breakeven_p else "REFUTED"),
        }

        print(f"\n=== {key} FINAL ===", flush=True)
        print(f"  N={n} Wins={wins} WR={wr*100:.1f}% CI=[{wr_lo*100:.1f}%,{wr_hi*100:.1f}%]", flush=True)
        print(f"  Theoretical={p_theoretical*100:.1f}% Breakeven={breakeven_p*100:.2f}%", flush=True)
        print(f"  EV=${ev:.4f} PnL=${total_profit:.2f} Verdict={barrier_analysis[key]['verdict']}", flush=True)

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D101",
        "description": "Barrier proximity edge — DIGITOVER/DIGITUNDER payout and win rate by barrier",
        "symbol": args.symbol,
        "duration": args.duration,
        "stake": args.stake,
        "scan_results": scan_results,
        "barrier_analysis": barrier_analysis,
        "live_results": live_results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
