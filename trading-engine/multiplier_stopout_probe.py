"""Multiplier Stop-Out Slippage -- probe de exploracao (Item 2, candidato #3).

Mecanica: contratos MULTUP/MULTDOWN tem um `stop_out` (nivel de spot onde equity=0) dado
upfront pela Deriv (limit_order.stop_out.value, recalculado no entry_spot real da compra).
Quando o spot cruza esse nivel, a Deriv fecha o contrato a mercado automaticamente.

Hipotese: existe slippage sistematico entre o nivel TEORICO de stop_out e o spot de saida
REAL registrado no contrato fechado. Slippage negativo (saida pior que o nivel) e esperado/
normal (custo de execucao). O interessante seria: (a) quantificar o tamanho desse custo, e
(b) checar se ha alguma janela onde vender manualmente um instante antes do stop-out oficial
recupera mais valor que deixar o auto-close acontecer (mesma familia de pergunta do Early
Sell e do Accumulator Race, agora aplicada ao mecanismo de liquidacao forcada).

Metodo: compra MULTUP com multiplier MAXIMO (mais alavancagem = stop-out mais rapido/
frequente = mais trials por hora), stake pequeno, poll rapido ate o fechamento automatico.
Registra o `stop_out level` teorico (pos-entry) vs o spot de saida real (`exit_tick` /
`sell_spot`, o que a API retornar) e o `profit` final vs a perda teorica exata (-stake).
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multiplier_stopout_results.jsonl")

SYMBOL = "1HZ100V"
CONTRACT_TYPE = "MULTUP"
MULTIPLIER = 400
STAKE = 10.0
POLL_INTERVAL_S = 0.3
MAX_TRIAL_SECONDS = 240

tick_log = []


def on_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        tick_log.append({"t": time.time(), "epoch": t.get("epoch"), "quote": float(t["quote"])})
        if len(tick_log) > 5000:
            del tick_log[:1000]


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


async def poll_open_contract(client, cid, retries=6):
    for attempt in range(retries):
        try:
            poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
            if isinstance(poc, dict) and "error" in poc:
                await asyncio.sleep(1)
                continue
            return poc.get("proposal_open_contract", {})
        except Exception:
            await asyncio.sleep(min(2 * (attempt + 1), 8))
    return {}


async def run_trial(client, idx):
    proposal = await client.get_proposal(CONTRACT_TYPE, STAKE, symbol=SYMBOL, multiplier=MULTIPLIER)
    if "error" in proposal:
        print(f"  [{idx}] proposal erro: {proposal['error'].get('message')}", flush=True)
        return None
    p = proposal["proposal"]
    buy_res = await client.buy_contract(p["id"], float(p["ask_price"]))
    if "error" in buy_res:
        print(f"  [{idx}] buy erro: {buy_res['error'].get('message')}", flush=True)
        return None

    b = buy_res["buy"]
    cid = b["contract_id"]
    buy_price = float(b.get("buy_price", STAKE))

    entry_spot = 0.0
    stop_out_level = None
    for _ in range(10):
        first = await poll_open_contract(client, cid)
        if first.get("entry_spot") is not None:
            entry_spot = float(first["entry_spot"])
        lo = first.get("limit_order", {}).get("stop_out", {})
        if lo.get("value") is not None:
            stop_out_level = float(lo["value"])
        if entry_spot and stop_out_level is not None:
            break
        await asyncio.sleep(0.5)

    start = time.time()
    final = None
    n_polls = 0
    last_spot = entry_spot
    while time.time() - start < MAX_TRIAL_SECONDS:
        c = await poll_open_contract(client, cid)
        n_polls += 1
        if c.get("current_spot") is not None:
            last_spot = float(c["current_spot"])
        if c.get("is_sold"):
            final = c
            break
        await asyncio.sleep(POLL_INTERVAL_S)

    if not final:
        try:
            await client.sell_contract(cid, price=0)
        except Exception:
            pass
        await asyncio.sleep(1)
        final = await poll_open_contract(client, cid)

    exit_spot = None
    for k in ("exit_tick", "sell_spot", "current_spot"):
        if final.get(k) is not None:
            exit_spot = float(final[k])
            break

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "idx": idx, "contract_id": cid, "buy_price": buy_price,
        "multiplier": MULTIPLIER, "entry_spot": entry_spot,
        "stop_out_level": stop_out_level, "exit_spot": exit_spot,
        "last_polled_spot": last_spot, "n_polls": n_polls,
        "final_profit": float(final.get("profit", 0) or 0),
        "final_status": final.get("status"),
        "final_is_sold": final.get("is_sold"),
        "raw_final": {k: final.get(k) for k in
                      ("exit_tick", "exit_tick_time", "sell_spot", "sell_time", "current_spot",
                       "profit", "status", "bid_price")},
    }

    # Multiplier nao tem expiry fixo -- `status` fica "sold" tanto p/ stop-out real quanto
    # p/ fechamento manual (inclusive o nosso, por timeout). Identifica stop-out GENUINO
    # pelo profit ~= -stake (equity zerada), independente do label de status.
    rec["is_genuine_stopout"] = abs(rec["final_profit"] - (-buy_price)) < max(0.5, buy_price * 0.05)

    slippage = None
    if stop_out_level is not None and exit_spot is not None and rec["is_genuine_stopout"]:
        # MULTUP: stop-out e acionado quando spot cai ABAIXO do nivel. Slippage = quanto
        # mais ele caiu alem do gatilho teorico (positivo = pior p/ cliente).
        slippage = stop_out_level - exit_spot if CONTRACT_TYPE == "MULTUP" else exit_spot - stop_out_level
    rec["slippage_points"] = slippage

    print(f"  [{idx}] entry={entry_spot} stop_out_level={stop_out_level} exit_spot={exit_spot} "
          f"slippage_pts={slippage} profit=${rec['final_profit']:+.4f} status={rec['final_status']} "
          f"n_polls={n_polls}", flush=True)
    return rec


async def main():
    ap = argparse.ArgumentParser(description="Multiplier Stop-Out Slippage probe")
    ap.add_argument("--trials", type=int, default=15)
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

    print("=" * 90, flush=True)
    print(f"Multiplier Stop-Out Slippage -- {SYMBOL} {CONTRACT_TYPE} multiplier={MULTIPLIER}x "
          f"stake=${STAKE} poll={POLL_INTERVAL_S}s N={args.trials}", flush=True)
    print("=" * 90, flush=True)

    results = []
    with open(RESULTS_FILE, "a") as fh:
        for i in range(args.trials):
            try:
                rec = await run_trial(client, i)
            except Exception as e:
                print(f"  [{i}] trial exception: {e}", flush=True)
                rec = None
            if rec:
                results.append(rec)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            await asyncio.sleep(args.cooldown_s)

    print("\n" + "=" * 90, flush=True)
    stopped_out = [r for r in results if r.get("is_genuine_stopout") and r["slippage_points"] is not None]
    print(f"Total trials: {len(results)} | stop-outs genuinos (profit~=-stake) com slippage medido: {len(stopped_out)}", flush=True)
    if stopped_out:
        slips = [r["slippage_points"] for r in stopped_out]
        profits = [r["final_profit"] for r in stopped_out]
        print(f"Slippage (pontos, positivo=pior p/ cliente): media={statistics.mean(slips):+.4f} "
              f"min={min(slips):+.4f} max={max(slips):+.4f} stdev={statistics.pstdev(slips):.4f}", flush=True)
        print(f"Profit nos stop-outs: media=${statistics.mean(profits):+.4f} "
              f"(perda teorica exata seria -${STAKE:.2f})", flush=True)
    print("=" * 90, flush=True)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
