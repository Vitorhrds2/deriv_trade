"""Extensao do Early Sell Optionality (early_sell_test.py) para multiplos simbolos e
contract types, rodando concorrentemente sobre uma unica conexao WS.

Baseline ja confirmado (N=50, early_sell_test.py): 1HZ10V CALL 15m -- SELL (melhor bid)
WR 86% (IC95%[73.8%,93.1%]) vs HOLD WR 52% (IC95%[38.5%,65.2%]); diff EV=+$5.23/trade,
IC95%[$3.22,$7.17] nao cruza zero. Regra non-hindsight (vender no 1o bid>=threshold)
confirmada em todos os thresholds $11-18 (stake=$10).

Esta extensao testa se o edge GENERALIZA (pergunta de escala/robustez, nao so existencia):
  - Atraves de toda a familia de indices de volatilidade (1HZ25V..100V, R_10..100)
  - Contract type simetrico (PUT no simbolo ja confirmado)

Roda continuamente (mesmo padrao dos outros bots do ecossistema: tmux + loop infinito),
1 trial de cada vez por stream (symbol, contract_type), todos os streams em PARALELO via
asyncio, compartilhando UMA UNICA conexao DerivClient (multiplexada por req_id -- ver
deriv_client.py: send_request usa Futures indexadas por req_id, entao chamadas concorrentes
sobre a mesma conexao sao seguras). Isso mantem o footprint de memoria de 1 processo so,
em vez de 10 processos separados (relevante dado o historico de OOM da instancia AWS).

Resultados persistidos incrementalmente em early_sell_multi_results.jsonl (1 linha por
trial concluido, idempotente/append-only, sobrevive a crashes) + snapshot agregado em
early_sell_multi_stats.json a cada --summary-interval-s (default 10min).

Regra threshold generalizada (nao-hindsight, comparavel entre stakes/simbolos): vender no
primeiro bid tal que bid_price/buy_price >= ratio, testado para ratio em [1.10..1.80]
(equivalente aos thresholds $11-18 do teste original com stake=$10).

Contratos sobrevivem no lado do servidor Deriv independente da nossa conexao WS -- por
isso poll_open_contract apenas re-tenta a mesma proposal_open_contract em vez de abortar
o trial inteiro quando a conexao cai (mesmo espirito do checkpointing usado em D46/D41).
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import bootstrap_ci, wilson_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_multi_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_multi_stats.json")

# Ratios equivalentes aos thresholds $11-18 testados em early_sell_test.py com stake=$10.
RATIO_THRESHOLDS = [1.10, 1.20, 1.30, 1.40, 1.50, 1.60, 1.70, 1.80]

# 1HZ10V CALL ja confirmado (N=50) em early_sell_test.py -- nao repetido aqui.
DEFAULT_MATRIX = [
    ("1HZ10V", "PUT"),     # checagem simetrica do simbolo ja confirmado
    ("1HZ25V", "CALL"),
    ("1HZ50V", "CALL"),
    ("1HZ75V", "CALL"),
    ("1HZ100V", "CALL"),
    ("R_10", "CALL"),
    ("R_25", "CALL"),
    ("R_50", "CALL"),
    ("R_75", "CALL"),
    ("R_100", "CALL"),
]

tick_state = {}  # symbol -> {"value", "epoch", "local_t"}


def on_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        sym = t.get("symbol")
        if sym:
            tick_state[sym] = {
                "value": float(t["quote"]),
                "epoch": int(t.get("epoch", 0)),
                "local_t": time.time(),
            }


async def validate_demo(client):
    import urllib.request as _u

    def _fetch():
        req = _u.Request("https://api.derivws.com/trading/v1/options/accounts")
        req.add_header("Authorization", f"Bearer {API_TOKEN}")
        req.add_header("Deriv-App-ID", str(APP_ID))
        with _u.urlopen(req) as r:
            return json.loads(r.read().decode())

    accs = (await asyncio.get_running_loop().run_in_executor(None, _fetch)).get("data", [])
    demo_ids = [a["account_id"] for a in accs if a.get("account_type") == "demo"]
    real_ids = [a["account_id"] for a in accs if a.get("account_type") != "demo"]
    connected = client.account_id
    ok = bool(client.use_demo and connected in demo_ids and connected not in real_ids)
    print(f"Conta: {connected} | demo={demo_ids} | real={real_ids} -> "
          f"{'OK DEMO' if ok else 'NAO DEMO!'}", flush=True)
    return ok


async def poll_open_contract(client, cid, retries=6):
    """proposal_open_contract com retry em WS drop. O contrato sobrevive no servidor Deriv
    independente da nossa conexao -- so precisamos re-tentar ate a reconexao (automatica no
    DerivClient) se completar."""
    for attempt in range(retries):
        try:
            poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
            if isinstance(poc, dict) and "error" in poc:
                await asyncio.sleep(2)
                continue
            return poc.get("proposal_open_contract", {})
        except Exception:
            await asyncio.sleep(min(2 * (attempt + 1), 10))
    return {}


async def run_trial(client, symbol, contract_type, stake, duration, duration_unit, tag):
    buy_res = None
    for attempt in range(5):
        try:
            buy_res = await client.send_request({
                "buy": 1, "price": stake,
                "parameters": {
                    "amount": stake, "basis": "stake", "contract_type": contract_type,
                    "currency": "USD", "underlying_symbol": symbol,
                    "duration": duration, "duration_unit": duration_unit,
                }
            })
            break
        except Exception as e:
            print(f"  [{tag}] BUY exception (tentativa {attempt + 1}): {e}", flush=True)
            await asyncio.sleep(3)

    if not buy_res or "error" in buy_res:
        msg = buy_res["error"].get("message", "") if buy_res and "error" in buy_res else "sem resposta"
        print(f"  [{tag}] BUY erro: {msg}", flush=True)
        return None

    b = buy_res["buy"]
    cid = b["contract_id"]
    buy_price = float(b.get("buy_price", 0))
    entry_spot = float(b.get("current_spot", 0))
    payout = float(b.get("payout", 0))

    total_secs = duration * 60 if duration_unit == "m" else duration
    sample_interval = max(5, total_secs // 60)
    n_samples = total_secs // sample_interval + 5

    bids = []
    final = None
    for sample_i in range(n_samples):
        c = await poll_open_contract(client, cid)
        if c.get("is_sold"):
            final = c
            break

        bid_price = float(c.get("bid_price", 0) or 0)
        is_valid_sell = bool(c.get("is_valid_to_sell", False))
        live = tick_state.get(symbol)
        live_spot = live["value"] if live else 0
        spot_diff = live_spot - entry_spot if live_spot and entry_spot else 0

        bids.append({
            "sample": sample_i, "bid_price": bid_price,
            "is_valid_to_sell": is_valid_sell,
            "live_spot": live_spot, "spot_diff": spot_diff,
        })
        await asyncio.sleep(sample_interval)

    if not final:
        final = await poll_open_contract(client, cid)

    profit = float(final.get("profit", 0) or 0)
    won = profit > 0

    valid_bids = [x for x in bids if x["is_valid_to_sell"] and x["bid_price"] > 0]
    best_bid = max(valid_bids, key=lambda x: x["bid_price"]) if valid_bids else None
    sell_profit = (best_bid["bid_price"] - buy_price) if best_bid else None

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "contract_type": contract_type, "stake": stake,
        "duration": duration, "duration_unit": duration_unit,
        "contract_id": cid,
        "buy_price": buy_price, "payout": payout, "entry_spot": entry_spot,
        "profit_hold": profit, "won": won,
        "best_bid": best_bid["bid_price"] if best_bid else None,
        "best_bid_sample": best_bid["sample"] if best_bid else None,
        "sell_profit": sell_profit,
        "n_valid_bids": len(valid_bids),
        "bids": bids,
    }


async def stream_loop(client, symbol, contract_type, stake, duration, duration_unit,
                       cooldown_s, max_trials, lock):
    tag = f"{symbol}:{contract_type}"
    i = 0
    while max_trials is None or i < max_trials:
        try:
            rec = await run_trial(client, symbol, contract_type, stake, duration, duration_unit, tag)
        except Exception as e:
            print(f"  [{tag}] trial exception: {e} -- retry em 5s", flush=True)
            await asyncio.sleep(5)
            continue
        if rec:
            sell_str = f"${rec['sell_profit']:+.4f}" if rec["sell_profit"] is not None else "N/A"
            print(f"  [{tag}] #{i} hold=${rec['profit_hold']:+.4f} sell={sell_str} "
                  f"n_bids={rec['n_valid_bids']}", flush=True)
            async with lock:
                with open(RESULTS_FILE, "a") as out_fh:
                    out_fh.write(json.dumps(rec) + "\n")
            i += 1
        await asyncio.sleep(cooldown_s)


def load_all_results():
    if not os.path.exists(RESULTS_FILE):
        return []
    out = []
    with open(RESULTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def compute_stream_stats(records):
    """ATENCAO -- correcao de 2026-07-07 (ver docs/state_of_research.md item 14):

    Os campos `sell_profit`/`sell_wr`/`sell_ev`/`diff_ev` abaixo usam `best_bid` = MAX
    do bid_price observado em TODAS as amostras do contrato (hindsight). Isso e um
    LIMITE SUPERIOR nao-acionavel (max(caminho) >= qualquer ponto fixo, incl. o valor
    terminal, e trivialmente positivo para qualquer processo de preco com ruido -- nao e
    evidencia de mispricing da Deriv). Mantidos so por compatibilidade/contexto historico.

    A regra `rule_by_ratio` (vender no 1o bid tal que bid/buy_price >= ratio) E
    non-hindsight, mas o EV "ev_sell" ali tambem e enganoso sozinho: e a media
    CONDICIONAL A TER DISPARADO, que e quase tautologicamente positiva (so dispara
    quando bid > buy_price). A pergunta certa e se a regra (vender se disparar, senao
    segurar) bate o EV de simplesmente segurar SEMPRE -- isso e o novo campo
    `diff_ev_vs_hold`/`diff_ci95_vs_hold` (pareado por trial, bootstrap na diferenca,
    nao-triggered = mesmo valor que hold em ambos os lados => diff=0 nesses casos).
    Resultado ao rodar isso pela 1a vez em N=550 (10 simbolos): cruza zero em 7/8
    ratios, e SIGNIFICATIVAMENTE NEGATIVO no ratio=1.8 -- sem edge confirmado."""
    sellable = [r for r in records if r["n_valid_bids"] > 0]
    hold_profits = [r["profit_hold"] for r in sellable]
    sell_profits = [r["sell_profit"] for r in sellable if r["sell_profit"] is not None]
    out = {"n_trials": len(records), "n_sellable": len(sellable)}

    if hold_profits:
        wins_hold = sum(1 for p in hold_profits if p > 0)
        out["hold_wr"] = wins_hold / len(hold_profits)
        out["hold_wr_ci95"] = list(wilson_ci(wins_hold, len(hold_profits)))
        out["hold_ev"] = statistics.mean(hold_profits)
    if sell_profits:
        wins_sell = sum(1 for p in sell_profits if p > 0)
        out["sell_wr_HINDSIGHT"] = wins_sell / len(sell_profits)
        out["sell_wr_ci95_HINDSIGHT"] = list(wilson_ci(wins_sell, len(sell_profits)))
        out["sell_ev_HINDSIGHT"] = statistics.mean(sell_profits)
    if sell_profits and hold_profits and len(sell_profits) == len(hold_profits):
        diffs = [s - h for s, h in zip(sell_profits, hold_profits)]
        lo, mean_d, hi = bootstrap_ci(diffs)
        out["diff_ev_HINDSIGHT_not_actionable"] = mean_d
        out["diff_ci95_HINDSIGHT_not_actionable"] = [lo, hi]

    rule_stats = {}
    for ratio in RATIO_THRESHOLDS:
        sp = []
        paired_diffs = []
        for r in sellable:
            if r["buy_price"] <= 0:
                continue
            triggered_profit = None
            for bd in r["bids"]:
                if bd["is_valid_to_sell"] and (bd["bid_price"] / r["buy_price"]) >= ratio:
                    triggered_profit = bd["bid_price"] - r["buy_price"]
                    break
            if triggered_profit is not None:
                sp.append(triggered_profit)
                paired_diffs.append(triggered_profit - r["profit_hold"])
            else:
                paired_diffs.append(0.0)  # regra nao disparou -> segura, diff=0 vs baseline hold
        if sp:
            lo_r, mean_r, hi_r = bootstrap_ci(paired_diffs)
            rule_stats[str(ratio)] = {
                "n_triggered": len(sp), "ev_sell_CONDITIONAL_on_trigger": statistics.mean(sp),
                "diff_ev_vs_hold": mean_r, "diff_ci95_vs_hold": [lo_r, hi_r],
            }
    out["rule_by_ratio"] = rule_stats
    return out


def write_summary():
    all_records = load_all_results()
    by_key = {}
    for r in all_records:
        key = f"{r['symbol']}:{r['contract_type']}"
        by_key.setdefault(key, []).append(r)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_trials": len(all_records),
        "streams": {k: compute_stream_stats(v) for k, v in by_key.items()},
    }
    with open(STATS_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


async def periodic_summary(interval_s):
    while True:
        await asyncio.sleep(interval_s)
        try:
            summary = write_summary()
            print("\n" + "=" * 90, flush=True)
            print(f"[SUMMARY @ {summary['generated_at']}] total_trials={summary['total_trials']}", flush=True)
            print("  (diff_ev_HINDSIGHT usa melhor bid observado -- limite superior nao-acionavel, ver docstring)", flush=True)
            for k, s in summary["streams"].items():
                print(f"  {k}: n={s['n_trials']} sellable={s['n_sellable']} "
                      f"hold_wr={s.get('hold_wr', 0) * 100:.1f}% sell_wr_HINDSIGHT={s.get('sell_wr_HINDSIGHT', 0) * 100:.1f}% "
                      f"diff_ev_HINDSIGHT={s.get('diff_ev_HINDSIGHT_not_actionable', 0):+.4f}", flush=True)
                rb = s.get("rule_by_ratio", {})
                if "1.3" in rb:
                    r13 = rb["1.3"]
                    print(f"      regra REAL (ratio=1.3, non-hindsight vs hold): "
                          f"diff_ev={r13['diff_ev_vs_hold']:+.4f} ci95={r13['diff_ci95_vs_hold']}", flush=True)
            print("=" * 90 + "\n", flush=True)
        except Exception as e:
            print(f"[SUMMARY erro] {e}", flush=True)


async def main():
    ap = argparse.ArgumentParser(description="Early Sell Optionality -- extensao multi-simbolo")
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--duration", type=int, default=15)
    ap.add_argument("--duration-unit", default="m")
    ap.add_argument("--cooldown-s", type=float, default=3.0)
    ap.add_argument("--max-trials-per-stream", type=int, default=None,
                     help="None = roda indefinidamente (mesmo padrao dos outros bots)")
    ap.add_argument("--summary-interval-s", type=int, default=600)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    print("=" * 90, flush=True)
    print(f"Early Sell Optionality -- EXTENSAO MULTI-SIMBOLO ({len(DEFAULT_MATRIX)} streams concorrentes)", flush=True)
    print("Baseline confirmado: 1HZ10V CALL 15m, N=50, EDGE CONFIRMADO (early_sell_test.py)", flush=True)
    for sym, ct in DEFAULT_MATRIX:
        print(f"  - {sym} {ct}", flush=True)
    print("=" * 90, flush=True)

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao DEMO. ABORTANDO.", flush=True)
        await client.disconnect()
        return

    unique_symbols = sorted(set(s for s, _ in DEFAULT_MATRIX))
    for sym in unique_symbols:
        await client.subscribe_ticks(sym, on_tick)
    await asyncio.sleep(2)
    print(f">>> Subscrito a ticks de {len(unique_symbols)} simbolos: {unique_symbols}", flush=True)

    lock = asyncio.Lock()
    tasks = [
        asyncio.create_task(stream_loop(
            client, sym, ct, args.stake, args.duration, args.duration_unit,
            args.cooldown_s, args.max_trials_per_stream, lock))
        for sym, ct in DEFAULT_MATRIX
    ]
    tasks.append(asyncio.create_task(periodic_summary(args.summary_interval_s)))
    await asyncio.gather(*tasks)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
