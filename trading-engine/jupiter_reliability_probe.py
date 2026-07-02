"""Soak test de confiabilidade da Jupiter Prediction API.

Contexto: teste ao vivo em 2026-07-02 (amostra pequena, ~15 requests) achou falha
intermitente real (timeout sem resposta) em /events e /markets/{id}, pior nesta ultima
(~40% em 7 tentativas). Este script roda uma amostra bem maior, por um periodo mais longo,
pra medir a taxa de falha de verdade e o quanto o retry+fallback ja implementados em
venues/jupiter_prediction.py ajudam na pratica. Ver docs/phantom_ecosystem_findings.md.

Mede 3 coisas por ciclo, no mesmo market_id fixo:
  1. events_ok        -- list_events() (GET /events)
  2. market_direct_ok -- _get() cru em /markets/{id}, SEM o fallback (mede a rota isolada)
  3. market_fallback_ok -- get_market() COM o fallback (mede o que o resto do sistema veria)

Uso:
    PYTHONPATH=. .venv/bin/python3 -u jupiter_reliability_probe.py --hours 2 --interval-s 30
"""
import argparse
import json
import time
from datetime import datetime, timezone

from venues.jupiter_prediction import JupiterPredictionVenue

TEST_MARKET_ID = "POLY-2758341"  # BTC "hit price in July" -- confirmado existir em teste ao vivo
TEST_CATEGORY = "crypto"
TEST_PROVIDER = "polymarket"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_once(venue: JupiterPredictionVenue) -> dict:
    result = {"ts": now_iso()}

    t0 = time.time()
    try:
        events = venue.list_events(category=TEST_CATEGORY, provider=TEST_PROVIDER)
        result["events_ok"] = True
        result["events_latency_s"] = round(time.time() - t0, 3)
        result["events_count"] = len(events) if isinstance(events, list) else None
    except Exception as e:
        result["events_ok"] = False
        result["events_latency_s"] = round(time.time() - t0, 3)
        result["events_error"] = str(e)[:200]

    t0 = time.time()
    try:
        venue._get(f"/markets/{TEST_MARKET_ID}")
        result["market_direct_ok"] = True
        result["market_direct_latency_s"] = round(time.time() - t0, 3)
    except Exception as e:
        result["market_direct_ok"] = False
        result["market_direct_latency_s"] = round(time.time() - t0, 3)
        result["market_direct_error"] = str(e)[:200]

    t0 = time.time()
    try:
        venue.get_market(TEST_MARKET_ID)
        result["market_fallback_ok"] = True
        result["market_fallback_latency_s"] = round(time.time() - t0, 3)
    except Exception as e:
        result["market_fallback_ok"] = False
        result["market_fallback_latency_s"] = round(time.time() - t0, 3)
        result["market_fallback_error"] = str(e)[:200]

    return result


def summarize(results: list) -> dict:
    def rate(key):
        vals = [1.0 if r[key] else 0.0 for r in results if key in r]
        return round(sum(vals) / len(vals), 4) if vals else None

    def avg_latency(key):
        vals = [r[key] for r in results if key in r]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "n_cycles": len(results),
        "events_success_rate": rate("events_ok"),
        "events_avg_latency_s": avg_latency("events_latency_s"),
        "market_direct_success_rate": rate("market_direct_ok"),
        "market_direct_avg_latency_s": avg_latency("market_direct_latency_s"),
        "market_fallback_success_rate": rate("market_fallback_ok"),
        "market_fallback_avg_latency_s": avg_latency("market_fallback_latency_s"),
        "updated_at": now_iso(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--interval-s", type=float, default=30.0)
    parser.add_argument("--out", default="jupiter_reliability_log.jsonl")
    parser.add_argument("--summary", default="jupiter_reliability_summary.json")
    args = parser.parse_args()

    venue = JupiterPredictionVenue()
    if not venue.api_key:
        print("SEM JUPITER_API_KEY carregada -- abortando", flush=True)
        return

    end_time = time.time() + args.hours * 3600
    results = []
    print(
        f"Iniciando soak test: {args.hours}h, intervalo {args.interval_s}s, "
        f"log={args.out}, summary={args.summary}",
        flush=True,
    )

    with open(args.out, "a") as f:
        while time.time() < end_time:
            r = probe_once(venue)
            results.append(r)
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(
                f"[{r['ts']}] events={r.get('events_ok')} "
                f"market_direct={r.get('market_direct_ok')} "
                f"market_fallback={r.get('market_fallback_ok')}",
                flush=True,
            )

            summary = summarize(results)
            with open(args.summary, "w") as sf:
                json.dump(summary, sf, indent=2)

            time.sleep(args.interval_s)

    print("Soak test concluido.", flush=True)
    print(json.dumps(summarize(results), indent=2), flush=True)


if __name__ == "__main__":
    main()
