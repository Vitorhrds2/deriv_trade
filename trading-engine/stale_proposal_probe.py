"""Stale Proposal Buy Race -- probe de exploracao (Item 2: vulnerabilidades de logica de
negocio alem de mispricing estatico, distinta do Early Sell e ja-refutado Entry Spot Lag).

Hipotese: contratos HIGHER/LOWER usam um `barrier` RELATIVO (ex: "+1.00") resolvido para um
nivel ABSOLUTO no momento em que a `proposal` e gerada (`p["barrier"]`, `p["spot"]`). Se esse
nivel absoluto permanecer FIXO ate o `buy` ser efetivamente enviado -- mesmo que isso aconteca
varios segundos depois, com o spot ja tendo andado bastante em direcao a barreira -- entao o
preco/payout cotado (calculado sobre a distancia ANTIGA e menos favoravel) fica descolado da
probabilidade REAL de vitoria no momento da compra. Isso seria uma race condition de negocio
distinta de:
  - Early Sell Optionality (early_sell_test.py): sobre VENDER cedo, edge ja confirmado (N=50).
  - Entry Spot Lag (entry_spot_lag_test.py): sobre qual TICK vira entry_spot -- ja REFUTADO
    (75/75 trials, sempre T+1, nunca reusa T0).
Aqui o alvo e se o PRECO/BARREIRA cotado pode ficar obsoleto e MESMO ASSIM ser honrado pela
Deriv no momento do buy.

Metodo: 2 bracos alternados 50/50, MESMO barrier/duration/stake/symbol:
  - CONTROL (delay=0s): pede proposal, compra imediatamente. Deve refletir o house margin
    ja conhecido de HIGHER/LOWER (docs/edge_investigation_report.md item 7 -- sem edge estatico).
  - TREAT (delay=DELAY_S): pede proposal, ESPERA DELAY_S segundos monitorando o spot ao vivo,
    so entao compra usando o MESMO proposal_id/ask_price antigo (potencialmente obsoleto). Uma
    proposal FRESCA (mesmo barrier relativo) e buscada no momento da compra so para diagnostico
    (nao usada na compra) -- serve para comparar "preco pago" vs "preco justo agora".

Apos a compra (se aceita), confere-se o `barrier`/`entry_spot` REAIS do contrato via
`proposal_open_contract`:
  - Se baterem com o valor ANTIGO da proposal -> barreira NAO recalculada -> race estruturalmente
    real (o resto e so quantificar EV/WR do braco TREAT vs CONTROL).
  - Se baterem com um valor NOVO (re-ancorado no entry_spot do buy) -> Deriv se autocorrige,
    sem exploit nesta rota.
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
from stats_utils import wilson_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stale_proposal_probe_results.jsonl")

SYMBOL = "R_100"
CONTRACT_TYPE = "HIGHER"
DURATION_TICKS = 10  # tick contracts na Deriv exigem duration entre 5 e 10 ticks
STAKE = 1.0
BARRIER_FALLBACKS = ["+0.10", "+0.20", "+0.33", "+0.50", "+1.00"]

tick_state = {}


def on_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        sym = t.get("symbol")
        if sym:
            tick_state[sym] = {"value": float(t["quote"]), "epoch": int(t.get("epoch", 0)), "local_t": time.time()}


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
    print(f"Conta: {connected} | demo={demo_ids} | real={real_ids} -> {'OK DEMO' if ok else 'NAO DEMO!'}", flush=True)
    return ok


async def get_quote(client, barrier):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": CONTRACT_TYPE, "currency": "USD",
        "underlying_symbol": SYMBOL, "duration": DURATION_TICKS,
        "duration_unit": "t", "barrier": barrier,
    })
    if "error" in res:
        return None, res["error"].get("message", "")
    p = res.get("proposal", {})
    # Nota: na resposta de `proposal`, o barrier ABSOLUTO vem aninhado em contract_details
    # (nao no nivel superior) -- diferente de `proposal_open_contract`, que retorna "barrier"
    # direto no nivel superior. Descoberto empiricamente (ver stale_proposal_probe debug).
    barrier_abs = p.get("contract_details", {}).get("barrier")
    return {
        "id": p.get("id"),
        "ask_price": float(p.get("ask_price", STAKE)),
        "payout": float(p.get("payout", 0)),
        "spot": float(p["spot"]) if p.get("spot") is not None else None,
        "barrier": float(barrier_abs) if barrier_abs is not None else None,
    }, None


async def find_valid_barrier(client):
    for b in BARRIER_FALLBACKS:
        q, err = await get_quote(client, b)
        if q:
            return b
        print(f"  barrier={b} erro: {err}", flush=True)
        await asyncio.sleep(0.3)
    return None


async def poll_open_contract(client, cid, retries=6):
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


async def run_trial(client, barrier_rel, arm, delay_s, idx):
    old_quote, err = await get_quote(client, barrier_rel)
    if not old_quote or old_quote.get("id") is None:
        print(f"  [{idx}] {arm} quote erro: {err}", flush=True)
        return None

    spot_at_quote = tick_state.get(SYMBOL, {}).get("value")

    if delay_s > 0:
        await asyncio.sleep(delay_s)

    spot_at_buy = tick_state.get(SYMBOL, {}).get("value")
    fresh_quote, _ = await get_quote(client, barrier_rel)

    try:
        buy_res = await client.buy_contract(old_quote["id"], old_quote["ask_price"])
    except Exception as e:
        buy_res = {"error": {"message": str(e)}}

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "idx": idx, "arm": arm, "delay_s": delay_s,
        "barrier_rel": barrier_rel,
        "old_quote": old_quote, "fresh_quote": fresh_quote,
        "spot_at_quote": spot_at_quote, "spot_at_buy": spot_at_buy,
        "move_toward_barrier": None,
        "buy_ok": False, "buy_error": None,
    }
    if old_quote.get("barrier") is not None and spot_at_quote and spot_at_buy:
        denom = old_quote["barrier"] - spot_at_quote
        if denom:
            rec["move_toward_barrier"] = (spot_at_buy - spot_at_quote) / denom

    if not buy_res or "error" in buy_res:
        rec["buy_error"] = buy_res["error"].get("message", "") if buy_res else "sem resposta"
        print(f"  [{idx}] {arm} delay={delay_s}s BUY REJEITADO: {rec['buy_error']}", flush=True)
        return rec

    b = buy_res["buy"]
    cid = b["contract_id"]
    rec["buy_ok"] = True
    rec["contract_id"] = cid
    rec["buy_price_paid"] = float(b.get("buy_price", 0))

    final = None
    for _ in range(DURATION_TICKS + 15):
        c = await poll_open_contract(client, cid)
        if c.get("barrier") is not None:
            rec["actual_barrier"] = float(c["barrier"])
        if c.get("entry_spot") is not None:
            rec["actual_entry_spot"] = float(c["entry_spot"])
        if c.get("is_sold"):
            final = c
            break
        await asyncio.sleep(2)
    if not final:
        final = await poll_open_contract(client, cid)
        if final.get("barrier") is not None:
            rec["actual_barrier"] = float(final["barrier"])
        if final.get("entry_spot") is not None:
            rec["actual_entry_spot"] = float(final["entry_spot"])

    rec["profit"] = float(final.get("profit", 0) or 0)
    rec["won"] = rec["profit"] > 0

    barrier_match = "N/A"
    if rec.get("actual_barrier") is not None and old_quote.get("barrier") is not None:
        barrier_match = ("STALE(old)" if abs(rec["actual_barrier"] - old_quote["barrier"]) < 1e-9
                          else "RECALC(new)")

    print(f"  [{idx}] {arm} delay={delay_s}s move={rec['move_toward_barrier']} "
          f"barrier_old={old_quote.get('barrier')} barrier_actual={rec.get('actual_barrier')} ({barrier_match}) "
          f"profit=${rec['profit']:+.4f}", flush=True)
    return rec


async def main():
    ap = argparse.ArgumentParser(description="Stale Proposal Buy Race probe")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--delay-s", type=float, default=20.0)
    ap.add_argument("--cooldown-s", type=float, default=2.0)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao DEMO. ABORTANDO.", flush=True)
        await client.disconnect()
        return

    await client.subscribe_ticks(SYMBOL, on_tick)
    await asyncio.sleep(2)

    barrier_rel = await find_valid_barrier(client)
    if not barrier_rel:
        print(">>> Nenhum barrier valido encontrado. Abortando.", flush=True)
        await client.disconnect()
        return

    print("=" * 90, flush=True)
    print(f"Stale Proposal Buy Race -- {SYMBOL} {CONTRACT_TYPE} barrier={barrier_rel} "
          f"dur={DURATION_TICKS}t stake=${STAKE}", flush=True)
    print(f"Bracos: CONTROL (delay=0s) vs TREAT (delay={args.delay_s}s), alternados, N={args.trials}", flush=True)
    print("=" * 90, flush=True)

    results = []
    with open(RESULTS_FILE, "a") as fh:
        for i in range(args.trials):
            arm = "TREAT" if i % 2 == 0 else "CONTROL"
            delay = args.delay_s if arm == "TREAT" else 0.0
            try:
                rec = await run_trial(client, barrier_rel, arm, delay, i)
            except Exception as e:
                print(f"  [{i}] trial exception: {e}", flush=True)
                rec = None
            if rec:
                results.append(rec)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            await asyncio.sleep(args.cooldown_s)

    print("\n" + "=" * 90, flush=True)
    treat = [r for r in results if r["arm"] == "TREAT" and r.get("buy_ok")]
    control = [r for r in results if r["arm"] == "CONTROL" and r.get("buy_ok")]
    rejected = [r for r in results if not r.get("buy_ok")]
    print(f"Total: {len(results)} | TREAT ok={len(treat)} | CONTROL ok={len(control)} | REJEITADOS={len(rejected)}", flush=True)
    if rejected:
        print("Motivos de rejeicao (amostra ate 5):", flush=True)
        for r in rejected[:5]:
            print(f"    [{r['arm']}] {r['buy_error']}", flush=True)

    stale_honored = sum(1 for r in treat if r.get("actual_barrier") is not None
                         and r.get("old_quote", {}).get("barrier") is not None
                         and abs(r["actual_barrier"] - r["old_quote"]["barrier"]) < 1e-9)
    if treat:
        print(f"\nTREAT: barreira ANTIGA (obsoleta) honrada em {stale_honored}/{len(treat)} contratos aceitos", flush=True)

    if treat:
        profits_t = [r["profit"] for r in treat]
        wins_t = sum(1 for p in profits_t if p > 0)
        wr_t = wins_t / len(profits_t)
        lo_t, hi_t = wilson_ci(wins_t, len(profits_t))
        print(f"TREAT   N={len(profits_t)} WR={wr_t*100:.1f}% IC95%[{lo_t*100:.1f}%,{hi_t*100:.1f}%] "
              f"EV=${statistics.mean(profits_t):+.4f} total=${sum(profits_t):+.2f}", flush=True)
    if control:
        profits_c = [r["profit"] for r in control]
        wins_c = sum(1 for p in profits_c if p > 0)
        wr_c = wins_c / len(profits_c)
        lo_c, hi_c = wilson_ci(wins_c, len(profits_c))
        print(f"CONTROL N={len(profits_c)} WR={wr_c*100:.1f}% IC95%[{lo_c*100:.1f}%,{hi_c*100:.1f}%] "
              f"EV=${statistics.mean(profits_c):+.4f} total=${sum(profits_c):+.2f}", flush=True)
    print("=" * 90, flush=True)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
