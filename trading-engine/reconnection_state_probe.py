"""
D61 — Reconnection State Inconsistency Probe
==============================================
Hipotese: Reconectar WS no meio de um contrato ativo. O estado do contrato
(barriers, bid_price) e consistente entre a sessao antiga e nova? Pode haver
janela onde informacoes obsoletas sao servidas.

Se apos reconexao o bid_price ou barrier for diferente do pre-reconexao,
ha inconsistencia de estado — potencialmente exploravel se o servidor
servir dados obsoletos por alguma janela.

Metodo:
  1. Comprar CALL de 10 ticks em 1HZ10V (demo) — duracao maior para dar
     tempo de reconectar
  2. Poll POC para obter estado baseline (bid_price, barrier, spot)
  3. Forcar reconexao WS (disconnect + reconnect)
  4. Imediatamente apos reconexao, poll POC novamente
  5. Comparar: bid_price, barrier, spot, is_sold
  6. Verificar se ha janela de dados obsoletos
  7. Repetir N trials

Uso: python3 reconnection_state_probe.py [--n=20]
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
CONTRACT_TYPE = "CALL"
STAKE = 1.00
DURATION = 10
DURATION_UNIT = "t"
WAIT_BEFORE_RECONNECT_S = 2

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconnect_state_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconnect_state_stats.json")


async def get_poc(client, contract_id, label=""):
    t0 = time.time()
    try:
        resp = await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
        })
        latency = (time.time() - t0) * 1000
        poc = resp.get("proposal_open_contract", {})
        result = {
            "label": label,
            "ts": time.time(),
            "latency_ms": round(latency, 1),
            "bid_price": float(poc.get("bid_price", 0)),
            "entry_spot": float(poc.get("entry_spot", 0) or 0),
            "exit_tick": float(poc.get("exit_tick", 0) or 0),
            "barrier": poc.get("barrier"),
            "is_sold": poc.get("is_sold", 0),
            "is_expired": poc.get("is_expired", 0),
            "sold_for": float(poc.get("sold_for", 0)) if poc.get("is_sold") else None,
            "spot": float(poc.get("spot", 0) or 0),
            "current_spot": float(poc.get("current_spot", 0) or 0),
            "status": poc.get("status", ""),
            "underlying": poc.get("underlying", ""),
            "contract_type": poc.get("contract_type", ""),
            "purchase_time": poc.get("purchase_time"),
            "date_expiry": poc.get("date_expiry"),
            "error": resp.get("error", {}).get("message") if "error" in resp else None,
        }
        return result
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return {
            "label": label,
            "ts": time.time(),
            "latency_ms": round(latency, 1),
            "error": str(e),
        }


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

        await asyncio.sleep(WAIT_BEFORE_RECONNECT_S)

        poc_before = await get_poc(client, contract_id, "before_reconnect")
        rec["poc_before"] = poc_before
        print(f"  [#{trial_num}] BEFORE: bid={poc_before.get('bid_price', 0):.4f} "
              f"spot={poc_before.get('spot', 0):.4f} sold={poc_before.get('is_sold', 0)} "
              f"({poc_before.get('latency_ms', 0):.0f}ms)")

        t_disconnect = time.time()
        await client.disconnect()
        print(f"  [#{trial_num}] Desconectado, reconectando...")
        await asyncio.sleep(0.5)
        await client.connect()
        t_reconnect_done = time.time()
        reconnect_time = t_reconnect_done - t_disconnect
        rec["reconnect_time_s"] = round(reconnect_time, 2)

        poc_after = await get_poc(client, contract_id, "after_reconnect")
        rec["poc_after"] = poc_after
        print(f"  [#{trial_num}] AFTER:  bid={poc_after.get('bid_price', 0):.4f} "
              f"spot={poc_after.get('spot', 0):.4f} sold={poc_after.get('is_sold', 0)} "
              f"({poc_after.get('latency_ms', 0):.0f}ms)")

        if poc_before.get("error") or poc_after.get("error"):
            rec["poc_error"] = True
            print(f"  [#{trial_num}] Erro POC: before={poc_before.get('error')} after={poc_after.get('error')}")
            return rec

        bid_diff = poc_after.get("bid_price", 0) - poc_before.get("bid_price", 0)
        spot_diff = poc_after.get("spot", 0) - poc_before.get("spot", 0)
        rec["bid_diff"] = round(bid_diff, 6)
        rec["spot_diff"] = round(spot_diff, 6)

        barrier_before = poc_before.get("barrier")
        barrier_after = poc_after.get("barrier")
        rec["barrier_match"] = (barrier_before == barrier_after)
        rec["barrier_before"] = barrier_before
        rec["barrier_after"] = barrier_after

        sold_before = poc_before.get("is_sold", 0)
        sold_after = poc_after.get("is_sold", 0)
        rec["sold_changed"] = (sold_before != sold_after)

        if not rec["barrier_match"]:
            print(f"  [#{trial_num}] *** BARRIER MISMATCH: before={barrier_before} after={barrier_after}")
        if rec["sold_changed"]:
            print(f"  [#{trial_num}] *** SOLD STATE CHANGED: before={sold_before} after={sold_after}")
        if abs(bid_diff) > 0.001 and sold_before == sold_after:
            print(f"  [#{trial_num}] Bid mudou: {bid_diff:+.4f} (esperado: tick moveu)")

        await asyncio.sleep(max(0, DURATION - WAIT_BEFORE_RECONNECT_S - reconnect_time - 1))

        poc_final = await get_poc(client, contract_id, "final")
        rec["poc_final"] = poc_final
        if poc_final.get("is_sold"):
            sold_for = float(poc_final.get("sold_for", 0))
            rec["sold_for"] = sold_for
            rec["profit"] = sold_for - buy_price
            print(f"  [#{trial_num}] Final: sold_for=${sold_for:.4f} profit=${sold_for - buy_price:+.4f}")

        return rec

    except Exception as e:
        rec["error"] = f"exception: {e}"
        print(f"  [#{trial_num}] EXC: {e}")
        return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D61 — Reconnection State Inconsistency Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE} | Duration: {DURATION} {DURATION_UNIT}")
    print(f"  Stake: ${STAKE} | Wait before reconnect: {WAIT_BEFORE_RECONNECT_S}s | Trials: {args.n}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    barrier_mismatches = 0
    sold_changes = 0
    errors = 0

    for i in range(args.n):
        rec = await run_trial(client, i)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        if rec.get("barrier_match") is False:
            barrier_mismatches += 1
        if rec.get("sold_changed"):
            sold_changes += 1
        if "error" in rec:
            errors += 1
        await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r and not r.get("poc_error")]
    print(f"  Trials: {len(all_results)} | Validos: {len(valid)} | Erros: {errors}")
    print(f"  Barrier mismatches: {barrier_mismatches}/{len(valid)}")
    print(f"  Sold state changes: {sold_changes}/{len(valid)}")

    reconnect_times = [r.get("reconnect_time_s", 0) for r in valid if r.get("reconnect_time_s")]
    if reconnect_times:
        import statistics
        print(f"  Reconnect time: mean={statistics.mean(reconnect_times):.2f}s "
              f"median={statistics.median(reconnect_times):.2f}s")

    bid_diffs = [r.get("bid_diff", 0) for r in valid if r.get("bid_diff") is not None]
    if bid_diffs:
        print(f"  Bid diff (after-before): mean={statistics.mean(bid_diffs):+.4f} "
              f"median={statistics.median(bid_diffs):+.4f}")

    if barrier_mismatches > 0:
        print(f"\n  *** INCONSISTENCIA DE BARRIER em {barrier_mismatches} trials!")
        print(f"      Estado do contrato muda apos reconexao — possivel janela de dados obsoletos.")
    elif sold_changes > 0:
        print(f"\n  *** SOLD STATE MUDOU em {sold_changes} trials apos reconexao!")
        print(f"      Pode ser settle natural durante reconnect, nao inconsistencia.")
    else:
        print(f"\n  Estado do contrato CONSISTENTE apos reconexao.")
        print(f"  Barrier, bid_price e is_sold iguais antes e depois do reconnect.")
        print(f"  Nao ha janela de dados obsoletos exploravel.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "errors": errors,
        "barrier_mismatches": barrier_mismatches,
        "sold_changes": sold_changes,
        "reconnect_times": reconnect_times,
        "bid_diffs": bid_diffs,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
