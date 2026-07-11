"""
D76 — Early-Sell + Directional Signal Combo
=============================================
D72 refutou early-sell com direcao aleatoria (CALL/PUT alternados).
Mas e se combinar early-sell com um sinal direcional?

Sinais testados:
  1. Momentum: ultimos 3 ticks UP -> comprar CALL, ultimos 3 DOWN -> comprar PUT
  2. Mean reversion (D46): 2 ticks iguais seguidos de direcional -> reverter
  3. Tick direction: ultimo tick UP -> CALL, DOWN -> PUT

Metodologia A/B pareada:
  - Grupo A (signal+sell): comprar com sinal direcional, vender a threshold
  - Grupo B (signal+hold): comprar com sinal direcional, segurar ate expiry
  - Comparar EV_A vs EV_B

Se o sinal melhorar WR o suficiente, early-sell pode virar EV positivo
porque mais contratos atingem o threshold antes de reverter.

Thresholds: 1.30 e 1.50
Simbolo: 1HZ10V (baixa volatilidade, onde D71 encontrou edge)
Duracao: 5m (onde sell funciona per D69)
"""
import argparse
import asyncio
import json
import os
import sys
import time
import random
import statistics
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
STAKE = 1.00
DURATION = 5
DURATION_UNIT = "m"
POLL_INTERVAL = 1.5
N_TICKS_HISTORY = 10

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "early_sell_signal_combo_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "early_sell_signal_combo_stats.json")


async def get_recent_ticks(client, symbol, count=N_TICKS_HISTORY):
    """Get recent ticks for signal generation."""
    res = await client.send_request({
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "start": 1,
        "style": "ticks",
    })
    if "error" in res:
        return []
    prices = res.get("history", {}).get("prices", [])
    return [float(p) for p in prices]


def momentum_signal(ticks):
    """3 ticks UP -> CALL, 3 ticks DOWN -> PUT."""
    if len(ticks) < 4:
        return None
    recent = ticks[-3:]
    diffs = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
    if all(d > 0 for d in diffs):
        return "CALL"
    elif all(d < 0 for d in diffs):
        return "PUT"
    return None


def mean_reversion_signal(ticks):
    """D46: 2 ticks iguais seguidos de direcional -> reverter.
    ==D -> UP -> next = DOWN (buy PUT)
    ==U -> DOWN -> next = UP (buy CALL)
    """
    if len(ticks) < 4:
        return None
    t1, t2, t3 = ticks[-3], ticks[-2], ticks[-1]
    if t1 == t2 and t3 > t2:
        return "PUT"  # revert
    elif t1 == t2 and t3 < t2:
        return "CALL"  # revert
    return None


def tick_direction_signal(ticks):
    """Last tick UP -> CALL, DOWN -> PUT."""
    if len(ticks) < 2:
        return None
    if ticks[-1] > ticks[-2]:
        return "CALL"
    elif ticks[-1] < ticks[-2]:
        return "PUT"
    return None


async def buy_contract(client, contract_type):
    try:
        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in prop:
            return {"error": f"proposal: {prop['error'].get('message')}"}

        buy = await client.buy_contract(prop["proposal"]["id"], price=STAKE)
        if "error" in buy:
            return {"error": f"buy: {buy['error'].get('message')}"}

        return {
            "contract_id": buy["buy"]["contract_id"],
            "buy_price": float(buy["buy"]["buy_price"]),
        }
    except Exception as e:
        return {"error": str(e)}


async def get_poc(client, contract_id):
    try:
        poc = await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
        })
        return poc.get("proposal_open_contract", {})
    except:
        return {}


async def run_sell_trial(client, trial_num, contract_type, signal_name, threshold):
    """Grupo A: buy com sinal, monitorar bid, vender a threshold."""
    rec = {
        "trial": trial_num,
        "group": "sell",
        "signal": signal_name,
        "contract_type": contract_type,
        "threshold": threshold,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    buy = await buy_contract(client, contract_type)
    if "error" in buy:
        rec["error"] = buy["error"]
        print(f"  [#{trial_num} SELL {signal_name} {contract_type}] buy erro: {rec['error']}")
        return rec

    contract_id = buy["contract_id"]
    buy_price = buy["buy_price"]
    rec["contract_id"] = contract_id
    rec["buy_price"] = buy_price

    t0 = time.time()
    max_wait = DURATION * 60 + 30
    sold = False

    while time.time() - t0 < max_wait:
        poc_data = await get_poc(client, contract_id)
        bid = poc_data.get("bid_price")
        is_sold = poc_data.get("is_sold", 0)

        if bid is not None:
            try:
                bid_val = float(bid)
                bid_ratio = bid_val / buy_price if buy_price > 0 else 0

                if not sold and bid_ratio >= threshold:
                    sell_resp = await client.sell_contract(contract_id, price=0)
                    if "error" not in sell_resp:
                        sold_for = float(sell_resp["sell"].get("sold_for", 0))
                        rec["sold"] = True
                        rec["sell_price"] = sold_for
                        rec["sell_profit"] = sold_for - buy_price
                        rec["sell_time"] = round(time.time() - t0, 1)
                        rec["sell_bid_ratio"] = round(bid_ratio, 4)
                        print(f"  [#{trial_num} SELL {signal_name} {contract_type}] "
                              f"SOLD at bid_ratio={bid_ratio:.3f} "
                              f"profit=${rec['sell_profit']:+.4f} t={rec['sell_time']:.0f}s")
                        return rec
            except:
                pass

        if is_sold:
            profit = float(poc_data.get("profit", 0))
            rec["sold"] = False
            rec["expired"] = True
            rec["hold_profit"] = profit
            print(f"  [#{trial_num} SELL {signal_name} {contract_type}] "
                  f"EXPIRED hold_profit=${profit:+.4f}")
            return rec

        await asyncio.sleep(POLL_INTERVAL)

    rec["sold"] = False
    rec["timeout"] = True
    print(f"  [#{trial_num} SELL {signal_name} {contract_type}] TIMEOUT")
    return rec


async def run_hold_trial(client, trial_num, contract_type, signal_name):
    """Grupo B: buy com sinal, NAO vender, segurar ate expiry."""
    rec = {
        "trial": trial_num,
        "group": "hold",
        "signal": signal_name,
        "contract_type": contract_type,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    buy = await buy_contract(client, contract_type)
    if "error" in buy:
        rec["error"] = buy["error"]
        print(f"  [#{trial_num} HOLD {signal_name} {contract_type}] buy erro: {rec['error']}")
        return rec

    contract_id = buy["contract_id"]
    buy_price = buy["buy_price"]
    rec["contract_id"] = contract_id
    rec["buy_price"] = buy_price

    t0 = time.time()
    max_wait = DURATION * 60 + 60

    while time.time() - t0 < max_wait:
        poc_data = await get_poc(client, contract_id)
        if poc_data.get("is_sold", 0):
            profit = float(poc_data.get("profit", 0))
            is_won = poc_data.get("is_won")
            if is_won is None:
                is_won = 1 if profit > 0 else 0
            rec["hold_profit"] = profit
            rec["is_won"] = int(is_won)
            won_str = "WON" if is_won else "LOST"
            print(f"  [#{trial_num} HOLD {signal_name} {contract_type}] "
                  f"{won_str} hold_profit=${profit:+.4f}")
            return rec
        await asyncio.sleep(POLL_INTERVAL)

    rec["timeout"] = True
    print(f"  [#{trial_num} HOLD {signal_name} {contract_type}] TIMEOUT")
    return rec


def bootstrap_ci(data, n_boot=5000, confidence=0.95):
    if len(data) < 2:
        return 0, 0, 0
    means = []
    for _ in range(n_boot):
        sample = [random.choice(data) for _ in range(len(data))]
        means.append(statistics.mean(sample))
    means.sort()
    alpha = (1 - confidence) / 2
    lo = means[int(n_boot * alpha)]
    hi = means[int(n_boot * (1 - alpha))]
    return statistics.mean(data), lo, hi


SIGNALS = {
    "momentum": momentum_signal,
    "mean_reversion": mean_reversion_signal,
    "tick_direction": tick_direction_signal,
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30, help="Trials per signal per group")
    parser.add_argument("--threshold", type=float, default=1.30)
    args = parser.parse_args()

    print("=" * 90)
    print("D76 — Early-Sell + Directional Signal Combo")
    print(f"  Symbol: {SYMBOL} | Duration: {DURATION}{DURATION_UNIT} | Stake: ${STAKE}")
    print(f"  Threshold: {args.threshold} | Trials per signal: {args.n} (A/B pareado)")
    print(f"  Signals: {', '.join(SIGNALS.keys())}")
    print(f"  Runtime: {args.n * len(SIGNALS) * 2 * DURATION}min = "
          f"{args.n * len(SIGNALS) * 2 * DURATION / 60:.1f}h")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    trial_num = 0

    for signal_name, signal_fn in SIGNALS.items():
        print(f"\n{'='*60}")
        print(f"  SIGNAL: {signal_name}")
        print(f"{'='*60}")

        i = 0
        while i < args.n * 2:
            # Get recent ticks for signal
            ticks = await get_recent_ticks(client, SYMBOL)
            if len(ticks) < 4:
                await asyncio.sleep(1)
                continue

            signal = signal_fn(ticks)
            if signal is None:
                await asyncio.sleep(1)
                continue

            # Alternate A/B
            if i % 2 == 0:
                rec = await run_sell_trial(client, trial_num, signal, signal_name, args.threshold)
            else:
                rec = await run_hold_trial(client, trial_num, signal, signal_name)

            all_results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")

            trial_num += 1
            i += 1
            await asyncio.sleep(1)

    # Analysis
    print(f"\n{'='*90}")
    print("  ANALISE FINAL — EARLY-SELL + SIGNAL COMBO")
    print(f"{'='*90}")

    for signal_name in SIGNALS:
        print(f"\n  --- Signal: {signal_name} ---")
        sell_results = [r for r in all_results if r.get("signal") == signal_name
                        and r.get("group") == "sell" and "error" not in r]
        hold_results = [r for r in all_results if r.get("signal") == signal_name
                        and r.get("group") == "hold" and "error" not in r]

        sell_valid = []
        for r in sell_results:
            if r.get("sold"):
                sell_valid.append(r["sell_profit"])
            elif r.get("hold_profit") is not None:
                sell_valid.append(r["hold_profit"])

        hold_valid = [r["hold_profit"] for r in hold_results if r.get("hold_profit") is not None]

        if len(sell_valid) < 3 or len(hold_valid) < 3:
            print(f"    Dados insuficientes (sell={len(sell_valid)}, hold={len(hold_valid)})")
            continue

        sell_ev = statistics.mean(sell_valid)
        hold_ev = statistics.mean(hold_valid)
        sell_wr = sum(1 for p in sell_valid if p > 0) / len(sell_valid)
        hold_wr = sum(1 for p in hold_valid if p > 0) / len(hold_valid)

        sold_count = sum(1 for r in sell_results if r.get("sold"))
        expired_count = sum(1 for r in sell_results if r.get("expired"))

        print(f"    Sell: EV=${sell_ev:+.4f} WR={sell_wr*100:.0f}% "
              f"({sold_count} sold, {expired_count} expired, N={len(sell_valid)})")
        print(f"    Hold: EV=${hold_ev:+.4f} WR={hold_wr*100:.0f}% (N={len(hold_valid)})")

        diffs = []
        min_n = min(len(sell_valid), len(hold_valid))
        for j in range(min_n):
            diffs.append(sell_valid[j] - hold_valid[j])

        mean_diff, ci_lo, ci_hi = bootstrap_ci(diffs)
        print(f"    Diff (sell - hold): ${mean_diff:+.4f} CI95%[${ci_lo:+.4f},${ci_hi:+.4f}]")

        if ci_lo > 0:
            print(f"    *** EDGE CONFIRMADO com signal {signal_name}!")
        elif ci_hi < 0:
            print(f"    REFUTADO — sell pior que hold mesmo com signal {signal_name}")
        else:
            print(f"    INCONCLUSIVO — CI cruza zero")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_total": len(all_results),
        "threshold": args.threshold,
        "signals": list(SIGNALS.keys()),
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
