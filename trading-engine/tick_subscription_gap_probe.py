"""
D60 — Tick Subscription Gap Detection Probe
=============================================
Hipotese: O stream de ticks via WS tem gaps (ticks perdidos)? Se sim, os
ticks faltantes sao previsiveis? D54 notou que proposal subscribe:1 nunca
reenviou — mas o stream de TICKS em si nao foi auditado quanto a completude.

Se ticks sao perdidos no stream mas existem no historico, e se os gaps
seguem um padrao (ex: sempre apos N ticks, ou em intervalos regulares),
pode haver forma de prever e explorar.

Metodo:
  1. Assinar ticks de 1HZ10V com subscribe:1
  2. A cada 30s, buscar ticks_history (style=ticks) para o mesmo simbolo
     cobrindo o periodo desde a ultima verificacao
  3. Comparar: ticks do stream vs ticks do historico
  4. Registrar: total_stream, total_history, missing, extra
  5. Verificar padrao temporal dos gaps (intervalos regulares?)
  6. Rodar por N minutos

Uso: python3 tick_subscription_gap_probe.py [--minutes=30]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import deque
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
CHECK_INTERVAL_S = 30

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_gap_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_gap_stats.json")

stream_ticks = deque(maxlen=100000)
last_check_epoch = None


def on_tick(data):
    t = data.get("tick")
    if not t or "quote" not in t:
        return
    stream_ticks.append({
        "epoch": int(t.get("epoch", 0)),
        "quote": float(t["quote"]),
        "local_t": time.time(),
        "symbol": t.get("symbol", ""),
    })


async def run_check(client, check_num):
    global last_check_epoch

    if not stream_ticks:
        print(f"  [check #{check_num}] Sem ticks no stream ainda.")
        return None

    current_epoch = int(time.time())
    if last_check_epoch is None:
        start_epoch = stream_ticks[0]["epoch"] - 5
    else:
        start_epoch = last_check_epoch

    count_to_fetch = min(5000, (current_epoch - start_epoch) * 2 + 100)

    try:
        resp = await client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": count_to_fetch,
            "end": "latest",
            "start": start_epoch,
            "style": "ticks",
        })
    except Exception as e:
        print(f"  [check #{check_num}] Erro ao buscar historico: {e}")
        return None

    if "error" in resp:
        print(f"  [check #{check_num}] Erro API: {resp['error'].get('message')}")
        return None

    history_data = resp.get("history", {})
    history_prices = history_data.get("prices", [])
    history_epochs = history_data.get("times", [])

    hist_records = []
    for i in range(len(history_prices)):
        hist_records.append({
            "epoch": int(history_epochs[i]) if i < len(history_epochs) else 0,
            "quote": float(history_prices[i]),
        })

    stream_since_check = [t for t in stream_ticks if t["epoch"] >= start_epoch]

    stream_epochs = set(t["epoch"] for t in stream_since_check)
    hist_epochs_set = set(t["epoch"] for t in hist_records)

    missing_from_stream = hist_epochs_set - stream_epochs
    extra_in_stream = stream_epochs - hist_epochs_set
    matched = stream_epochs & hist_epochs_set

    stream_quotes = {t["epoch"]: t["quote"] for t in stream_since_check}
    hist_quotes = {t["epoch"]: t["quote"] for t in hist_records}

    quote_mismatches = []
    for ep in matched:
        sq = stream_quotes.get(ep, 0)
        hq = hist_quotes.get(ep, 0)
        if abs(sq - hq) > 1e-10:
            quote_mismatches.append({"epoch": ep, "stream": sq, "history": hq})

    result = {
        "check": check_num,
        "ts": datetime.now(timezone.utc).isoformat(),
        "start_epoch": start_epoch,
        "stream_count": len(stream_since_check),
        "history_count": len(hist_records),
        "matched": len(matched),
        "missing_from_stream": len(missing_from_stream),
        "extra_in_stream": len(extra_in_stream),
        "quote_mismatches": len(quote_mismatches),
        "missing_epochs": sorted(list(missing_from_stream))[:20],
        "mismatch_details": quote_mismatches[:5],
    }

    pct_missing = (len(missing_from_stream) / max(len(hist_records), 1)) * 100
    print(f"  [check #{check_num}] stream={len(stream_since_check)} hist={len(hist_records)} "
          f"matched={len(matched)} missing={len(missing_from_stream)} ({pct_missing:.1f}%) "
          f"extra={len(extra_in_stream)} mismatches={len(quote_mismatches)}")

    if missing_from_stream:
        missing_list = sorted(list(missing_from_stream))
        if len(missing_list) >= 2:
            gaps = [missing_list[i+1] - missing_list[i] for i in range(len(missing_list)-1)]
            print(f"    Missing epochs: {missing_list[:5]}...")
            print(f"    Gap intervals: {gaps[:5]}...")
    if quote_mismatches:
        print(f"    QUOTE MISMATCH! stream={quote_mismatches[0]['stream']} vs hist={quote_mismatches[0]['history']}")

    last_check_epoch = current_epoch
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(result) + "\n")

    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D60 — Tick Subscription Gap Detection Probe")
    print(f"  Symbol: {SYMBOL} | Check interval: {CHECK_INTERVAL_S}s | Duration: {args.minutes}min")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    await client.subscribe_ticks(SYMBOL, on_tick)
    print(f"  Subscrito a {SYMBOL}. Coletando ticks...")

    await asyncio.sleep(5)

    all_results = []
    end_time = time.time() + args.minutes * 60
    check_num = 0

    try:
        while time.time() < end_time:
            await asyncio.sleep(CHECK_INTERVAL_S)
            check_num += 1
            result = await run_check(client, check_num)
            if result:
                all_results.append(result)
    except KeyboardInterrupt:
        print("\n  Parando...")

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    if not all_results:
        print("  Sem dados para analisar.")
        await client.disconnect()
        return

    total_stream = sum(r["stream_count"] for r in all_results)
    total_hist = sum(r["history_count"] for r in all_results)
    total_missing = sum(r["missing_from_stream"] for r in all_results)
    total_extra = sum(r["extra_in_stream"] for r in all_results)
    total_mismatches = sum(r["quote_mismatches"] for r in all_results)
    checks_with_missing = sum(1 for r in all_results if r["missing_from_stream"] > 0)

    print(f"  Checks realizados: {len(all_results)}")
    print(f"  Total ticks stream: {total_stream}")
    print(f"  Total ticks historico: {total_hist}")
    print(f"  Total missing do stream: {total_missing}")
    print(f"  Total extra no stream: {total_extra}")
    print(f"  Total quote mismatches: {total_mismatches}")
    print(f"  Checks com gaps: {checks_with_missing}/{len(all_results)}")

    pct_missing_overall = (total_missing / max(total_hist, 1)) * 100
    print(f"  % missing overall: {pct_missing_overall:.2f}%")

    if total_missing > 0:
        all_missing_epochs = []
        for r in all_results:
            all_missing_epochs.extend(r.get("missing_epochs", []))
        if len(all_missing_epochs) >= 2:
            all_missing_epochs.sort()
            gaps = [all_missing_epochs[i+1] - all_missing_epochs[i] for i in range(len(all_missing_epochs)-1)]
            import statistics
            print(f"\n  Analise de padrao dos gaps:")
            print(f"    Total missing epochs: {len(all_missing_epochs)}")
            print(f"    Gap intervals: mean={statistics.mean(gaps):.1f}s median={statistics.median(gaps):.1f}s")
            print(f"    Min={min(gaps)}s Max={max(gaps)}s")
            unique_gaps = set(gaps)
            if len(unique_gaps) <= 3:
                print(f"    *** PADRAO REGULAR: apenas {len(unique_gaps)} intervalos unicos: {unique_gaps}")
            else:
                print(f"    {len(unique_gaps)} intervalos unicos — gaps irregulares")

    if total_mismatches > 0:
        print(f"\n  *** QUOTE MISMATCHES: stream e historico discordam em {total_mismatches} ticks!")
        for r in all_results:
            for m in r.get("mismatch_details", []):
                print(f"    epoch={m['epoch']}: stream={m['stream']} vs history={m['history']}")
    else:
        print(f"\n  Nenhum quote mismatch — quotes do stream batem com historico.")

    if total_missing == 0 and total_mismatches == 0:
        print(f"\n  Stream de ticks e COMPLETO e CONSISTENTE com historico.")
        print(f"  Nao ha gaps exploraveis no stream de ticks.")
    elif total_missing > 0 and pct_missing_overall < 1:
        print(f"\n  Gaps minoritarios ({pct_missing_overall:.2f}%) — pode ser latencia/reconnect.")
        print(f"  Nao parece exploravel (gaps nao sao previsiveis).")
    elif pct_missing_overall >= 5:
        print(f"\n  *** GAPS SIGNIFICATIVOS ({pct_missing_overall:.1f}%) — investigar padrao!")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "duration_minutes": args.minutes,
        "checks": len(all_results),
        "total_stream": total_stream,
        "total_hist": total_hist,
        "total_missing": total_missing,
        "total_extra": total_extra,
        "total_mismatches": total_mismatches,
        "pct_missing": pct_missing_overall,
        "checks_with_missing": checks_with_missing,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
