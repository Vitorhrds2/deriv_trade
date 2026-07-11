"""
D59 — POC Subscription vs Poll Timing Gap Probe
=================================================
Hipotese: Assinar proposal_open_contract com subscribe:1 vs poll manual.
Se a subscription notificar settle DEPOIS do poll, ha janela onde o poll
sabe algo que a subscription nao sabe (ou vice-versa). Se o poll detecta
settle/is_sold antes da subscription, podemos agir antes do stream.

Metodo:
  1. Comprar CALL de 5 ticks em 1HZ10V (demo)
  2. Assinar POC com subscribe:1 para esse contract_id
  3. Simultaneamente, poll POC manualmente a cada 200ms
  4. Registrar timestamps precisos de cada evento:
     - subscription update recebida (ts_sub)
     - poll response recebida (ts_poll)
     - campos: is_sold, bid_price, sold_for
  5. Comparar: quem detecta is_sold=1 primeiro?
  6. Repetir N trials

Uso: python3 poc_subscription_vs_poll_probe.py [--n=30]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import wilson_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
CONTRACT_TYPE = "CALL"
STAKE = 1.00
DURATION = 5
DURATION_UNIT = "t"
POLL_INTERVAL_MS = 200

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc_sub_vs_poll_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc_sub_vs_poll_stats.json")


async def run_trial(client, trial_num):
    rec = {
        "trial": trial_num,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": CONTRACT_TYPE,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in prop:
            rec["error"] = f"proposal: {prop['error'].get('message')}"
            print(f"  [#{trial_num}] proposal erro: {rec['error']}")
            return rec

        buy = await client.buy_contract(prop["proposal"]["id"], price=STAKE)
        if "error" in buy:
            rec["error"] = f"buy: {buy['error'].get('message')}"
            print(f"  [#{trial_num}] buy erro: {rec['error']}")
            return rec

        contract_id = buy["buy"]["contract_id"]
        buy_price = float(buy["buy"]["buy_price"])
        rec["contract_id"] = contract_id
        rec["buy_price"] = buy_price

        sub_events = []
        poll_events = []
        sub_detected_sold = None
        poll_detected_sold = None
        sub_first_bid = None
        poll_first_bid = None

        sub_ready = asyncio.Event()

        async def on_poc_update(data):
            ts = time.time()
            poc = data.get("proposal_open_contract", {})
            is_sold = poc.get("is_sold", 0)
            bid_price = float(poc.get("bid_price", 0))
            sold_for = float(poc.get("sold_for", 0)) if is_sold else None
            sub_events.append({
                "ts": ts,
                "is_sold": is_sold,
                "bid_price": bid_price,
                "sold_for": sold_for,
            })
            nonlocal sub_detected_sold, sub_first_bid
            if sub_first_bid is None and bid_price > 0:
                sub_first_bid = (ts, bid_price)
            if is_sold and sub_detected_sold is None:
                sub_detected_sold = ts
            sub_ready.set()

        await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
            "subscribe": 1,
        })

        client.callbacks["poc_sub"] = on_poc_update

        async def poll_loop():
            while True:
                t0 = time.time()
                try:
                    resp = await client.send_request({
                        "proposal_open_contract": 1,
                        "contract_id": contract_id,
                    })
                    ts = time.time()
                    poc = resp.get("proposal_open_contract", {})
                    is_sold = poc.get("is_sold", 0)
                    bid_price = float(poc.get("bid_price", 0))
                    sold_for = float(poc.get("sold_for", 0)) if is_sold else None
                    poll_events.append({
                        "ts": ts,
                        "rtt_ms": round((ts - t0) * 1000, 1),
                        "is_sold": is_sold,
                        "bid_price": bid_price,
                        "sold_for": sold_for,
                    })
                    nonlocal poll_detected_sold
                    if is_sold and poll_detected_sold is None:
                        poll_detected_sold = ts
                    if is_sold:
                        return
                except Exception as e:
                    poll_events.append({"ts": time.time(), "error": str(e)})
                await asyncio.sleep(POLL_INTERVAL_MS / 1000)

        poll_task = asyncio.create_task(poll_loop())

        try:
            await asyncio.wait_for(poll_task, timeout=60)
        except asyncio.TimeoutError:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

        try:
            await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
                "subscribe": 0,
            })
        except Exception:
            pass

        if "poc_sub" in client.callbacks:
            del client.callbacks["poc_sub"]

        rec["sub_events"] = len(sub_events)
        rec["poll_events"] = len(poll_events)
        rec["sub_detected_sold_ts"] = sub_detected_sold
        rec["poll_detected_sold_ts"] = poll_detected_sold
        rec["sub_first_bid"] = sub_first_bid
        rec["poll_first_bid"] = poll_events[0] if poll_events else None

        if sub_detected_sold and poll_detected_sold:
            gap_ms = (poll_detected_sold - sub_detected_sold) * 1000
            rec["gap_ms_poll_minus_sub"] = round(gap_ms, 1)
            winner = "POLL" if gap_ms < 0 else "SUB"
            print(f"  [#{trial_num}] sub_events={len(sub_events)} poll_events={len(poll_events)} "
                  f"gap={gap_ms:+.0f}ms ({winner} detectou settle primeiro)")
        elif poll_detected_sold and not sub_detected_sold:
            rec["gap_ms_poll_minus_sub"] = None
            print(f"  [#{trial_num}] POLL detectou settle, SUB NUNCA notificou! "
                  f"sub_events={len(sub_events)} poll_events={len(poll_events)}")
        elif sub_detected_sold and not poll_detected_sold:
            rec["gap_ms_poll_minus_sub"] = None
            print(f"  [#{trial_num}] SUB detectou settle, POLL nao (timeout?)")
        else:
            rec["gap_ms_poll_minus_sub"] = None
            print(f"  [#{trial_num}] Nenhum detectou settle. sub={len(sub_events)} poll={len(poll_events)}")

        if poll_events:
            last_poll = poll_events[-1]
            if last_poll.get("is_sold"):
                rec["sold_for"] = last_poll.get("sold_for")
                rec["profit"] = float(last_poll.get("sold_for", 0)) - buy_price

        return rec

    except Exception as e:
        rec["error"] = f"exception: {e}"
        print(f"  [#{trial_num}] EXC: {e}")
        return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D59 — POC Subscription vs Poll Timing Gap Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE} | Duration: {DURATION} {DURATION_UNIT}")
    print(f"  Stake: ${STAKE} | Poll interval: {POLL_INTERVAL_MS}ms | Trials: {args.n}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    gaps = []

    for i in range(args.n):
        rec = await run_trial(client, i)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        if rec.get("gap_ms_poll_minus_sub") is not None:
            gaps.append(rec["gap_ms_poll_minus_sub"])
        await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r]
    sub_only = sum(1 for r in valid if r.get("sub_detected_sold_ts") and not r.get("poll_detected_sold_ts"))
    poll_only = sum(1 for r in valid if r.get("poll_detected_sold_ts") and not r.get("sub_detected_sold_ts"))
    both = sum(1 for r in valid if r.get("sub_detected_sold_ts") and r.get("poll_detected_sold_ts"))
    neither = sum(1 for r in valid if not r.get("sub_detected_sold_ts") and not r.get("poll_detected_sold_ts"))

    print(f"  Trials validos: {len(valid)}")
    print(f"  Ambos detectaram: {both}")
    print(f"  Apenas SUB: {sub_only}")
    print(f"  Apenas POLL: {poll_only}")
    print(f"  Nenhum: {neither}")

    if gaps:
        import statistics
        mean_gap = statistics.mean(gaps)
        median_gap = statistics.median(gaps)
        min_gap = min(gaps)
        max_gap = max(gaps)
        poll_first = sum(1 for g in gaps if g < 0)
        sub_first = sum(1 for g in gaps if g > 0)
        simultaneous = sum(1 for g in gaps if abs(g) < 50)

        print(f"\n  Gap (poll_ts - sub_ts) em ms quando ambos detectaram:")
        print(f"    Mean: {mean_gap:+.1f}ms | Median: {median_gap:+.1f}ms")
        print(f"    Min: {min_gap:+.1f}ms | Max: {max_gap:+.1f}ms")
        print(f"    POLL primeiro: {poll_first}/{len(gaps)}")
        print(f"    SUB primeiro: {sub_first}/{len(gaps)}")
        print(f"    Simultaneo (<50ms): {simultaneous}/{len(gaps)}")

        if poll_first > sub_first and mean_gap < -100:
            print(f"\n  *** EDGE POTENCIAL: POLL detecta settle consistentemente antes da SUB!")
        elif sub_first > poll_first and mean_gap > 100:
            print(f"\n  *** EDGE POTENCIAL: SUB detecta settle consistentemente antes do POLL!")
        else:
            print(f"\n  Sem gap significativo — SUB e POLL notificam ao mesmo tempo.")
    else:
        print(f"\n  Sem dados de gap para analisar.")

    sub_event_counts = [r.get("sub_events", 0) for r in valid]
    poll_event_counts = [r.get("poll_events", 0) for r in valid]
    print(f"\n  Eventos SUB/trial: mean={statistics.mean(sub_event_counts):.1f} (esperado: ~{DURATION}+1)")
    print(f"  Eventos POLL/trial: mean={statistics.mean(poll_event_counts):.1f}")

    if sub_event_counts and all(c == 0 for c in sub_event_counts):
        print(f"\n  *** ACHADO: subscribe:1 para POC NUNCA enviou atualizacoes!")
        print(f"      Confirmado padrao do D54 — subscription POC nao realimenta.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "both_detected": both,
        "sub_only": sub_only,
        "poll_only": poll_only,
        "neither": neither,
        "gaps_ms": gaps,
        "sub_event_counts": sub_event_counts,
        "poll_event_counts": poll_event_counts,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
