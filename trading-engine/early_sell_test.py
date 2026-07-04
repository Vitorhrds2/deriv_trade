"""Teste de Early Sell Optionality: contratos com is_valid_to_sell=true permitem venda
antes do expiry. O preco de venda (bid_price) e determinado pela Deriv em tempo real.

Hipotese: em algum momento durante o contrato, o bid_price pode ficar favoravel vs
segurar ate o final. Se a Deriv mispricinga o bid_price (ex: superestima a probabilidade
de win e oferece bid alto demais), pode haver edge em vender cedo.

Descoberta via probe_sellable.py: is_valid_to_sell=true apenas em durations >= 60s (15m ideal).
Tick contracts (5t, 10t) e durations < 60s NAO sao sellable.

Fluxo: comprar CALL 15m -> monitorar bid_price durante vida -> comparar sell vs hold.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import summarize, bootstrap_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

state = {"last_tick": None}


def on_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        state["last_tick"] = {
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
    print(f"  Conta: {connected} | demo={demo_ids} | real={real_ids} -> "
          f"{'OK DEMO' if ok else 'NAO DEMO!'}")
    return ok


async def run_trial(client, symbol, stake, duration, duration_unit, idx):
    """Compra CALL, monitora bid_price durante a vida do contrato, compara com resultado final."""
    buy_res = await client.send_request({
        "buy": 1, "price": stake,
        "parameters": {
            "amount": stake, "basis": "stake", "contract_type": "CALL",
            "currency": "USD", "underlying_symbol": symbol,
            "duration": duration, "duration_unit": duration_unit,
        }
    })
    if "error" in buy_res:
        print(f"  [{idx}] BUY erro: {buy_res['error'].get('message','')}")
        return None  # skip this trial, don't retry

    b = buy_res["buy"]
    cid = b["contract_id"]
    buy_price = float(b.get("buy_price", 0))
    entry_spot = float(b.get("current_spot", 0))
    payout = float(b.get("payout", 0))

    # Configurar amostragem baseada na duration
    if duration_unit == "m":
        total_secs = duration * 60
        sample_interval = max(5, total_secs // 60)
        n_samples = total_secs // sample_interval + 5
    elif duration_unit == "s":
        total_secs = duration
        sample_interval = max(1, total_secs // 30)
        n_samples = total_secs // sample_interval + 5
    else:
        sample_interval = 0.15
        n_samples = duration + 5

    # Use live tick from subscription for spot tracking
    live_spot = state["last_tick"]["value"] if state["last_tick"] else 0

    bids = []
    final = None
    for sample_i in range(n_samples):
        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        c = poc.get("proposal_open_contract", {})
        if c.get("is_sold"):
            final = c
            break

        bid_price = float(c.get("bid_price", 0))
        is_valid_sell = c.get("is_valid_to_sell", False)
        # Use live tick from subscription for real spot
        live_spot = state["last_tick"]["value"] if state["last_tick"] else 0
        spot_diff = live_spot - entry_spot if live_spot and entry_spot else 0

        bids.append({
            "sample": sample_i, "bid_price": bid_price,
            "is_valid_to_sell": is_valid_sell,
            "live_spot": live_spot, "spot_diff": spot_diff,
        })

        if sample_i == 0 or sample_i == n_samples // 2 or sample_i == n_samples - 3:
            print(f"  [{idx}] sample={sample_i} bid=${bid_price:.4f} sellable={is_valid_sell} "
                  f"spot={live_spot:.5f} diff={spot_diff:+.5f}")

        await asyncio.sleep(sample_interval)

    if not final:
        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        final = poc.get("proposal_open_contract", {})

    profit = float(final.get("profit", 0))
    won = profit > 0

    valid_bids = [b for b in bids if b["is_valid_to_sell"] and b["bid_price"] > 0]
    best_bid = max(valid_bids, key=lambda x: x["bid_price"]) if valid_bids else None

    sell_profit = None
    if best_bid:
        sell_profit = best_bid["bid_price"] - buy_price

    hold_better = sell_profit is not None and profit > sell_profit
    sell_better = sell_profit is not None and sell_profit > profit

    flag = ""
    if sell_better:
        flag = f"*** SELL BETTER (sell=${sell_profit:+.4f} vs hold=${profit:+.4f}) ***"
    elif hold_better:
        flag = f"hold better (hold=${profit:+.4f} vs sell=${sell_profit:+.4f})"
    elif not valid_bids:
        flag = f"no valid sell bids (n_bids={len(bids)}, all sellable=False)"

    best_bid_str = f"${best_bid['bid_price']:.4f} (sample {best_bid['sample']})" if best_bid else "N/A"
    sell_str = f"${sell_profit:+.4f}" if sell_profit is not None else "N/A"
    print(f"  [{idx}] profit_hold=${profit:+.4f} | best_bid={best_bid_str} | "
          f"sell_profit={sell_str} | {flag}")

    return {
        "buy_price": buy_price, "payout": payout, "entry_spot": entry_spot,
        "profit_hold": profit, "won": won,
        "best_bid": best_bid["bid_price"] if best_bid else None,
        "best_bid_sample": best_bid["sample"] if best_bid else None,
        "sell_profit": sell_profit,
        "sell_better": sell_better,
        "n_valid_bids": len(valid_bids),
        "bids": bids,
    }


async def run_with_retry(args):
    """Run all trials with WS reconnect logic. Preserves results across crashes."""
    results = []
    client = None
    i = 0
    while i < args.trials:
        try:
            if client is None:
                client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
                await client.connect()
                ok = await validate_demo(client)
                if not ok:
                    print(">>> TRAVA: conta nao DEMO. ABORTANDO.")
                    await client.disconnect()
                    return results
                await client.subscribe_ticks(args.symbol, on_tick)
                await asyncio.sleep(2)
                dur_label = f"{args.duration}{args.duration_unit}"
                if i == 0:
                    print(f">>> {args.symbol} | CALL dur={dur_label} | stake=${args.stake} | trials={args.trials}")
                    print(f">>> Monitorar bid_price durante vida do contrato, comparar sell vs hold")
                    print("=" * 90)
                else:
                    print(f"\n--- RECONECTADO no trial {i}/{args.trials} ({len(results)} results acumulados) ---\n")

            rec = await run_trial(client, args.symbol, args.stake, args.duration,
                                  args.duration_unit, i)
            if rec:
                results.append(rec)
            i += 1
            await asyncio.sleep(args.cooldown_s)
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[WS drop no trial {i}] {e} -- reconectando em 3s...\n")
            try:
                if client:
                    await client.disconnect()
            except Exception:
                pass
            client = None
            await asyncio.sleep(3)
            continue

    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    return results


async def main():
    ap = argparse.ArgumentParser(description="Early Sell Optionality test")
    ap.add_argument("--symbol", default="1HZ10V")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--duration", type=int, default=15, help="Duration value")
    ap.add_argument("--duration-unit", default="m", help="Duration unit (t/s/m/h/d)")
    ap.add_argument("--cooldown-s", type=float, default=2.0)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    print("=" * 90)
    results = await run_with_retry(args)

    print("\n" + "=" * 90)
    n = len(results)
    if n == 0:
        print("Nenhum trial valido.")
        return

    sellable = [r for r in results if r["n_valid_bids"] > 0]
    print(f"Total: {n} trials | com sell bids validos: {len(sellable)}")

    if not sellable:
        print(">>> Nenhum contrato tinha sell valido -- early sell nao disponivel.")
        print("=" * 90)
        return

    sell_better = [r for r in sellable if r.get("sell_better")]
    hold_better = [r for r in sellable if not r.get("sell_better") and r["sell_profit"] is not None]

    print(f"\nSell melhor que hold: {len(sell_better)}/{len(sellable)}")
    print(f"Hold melhor que sell: {len(hold_better)}/{len(sellable)}")

    hold_profits = [r["profit_hold"] for r in sellable]
    sell_profits = [r["sell_profit"] for r in sellable if r["sell_profit"] is not None]

    if hold_profits:
        summarize("HOLD (segurar ate expiry)", hold_profits)
    if sell_profits:
        summarize("SELL (vender no melhor bid)", sell_profits)

    if sell_profits and hold_profits:
        ev_sell = statistics.mean(sell_profits)
        ev_hold = statistics.mean(hold_profits)
        diff = ev_sell - ev_hold
        print(f"\n  EV Sell - EV Hold = ${diff:+.4f}/trade")
        if diff > 0:
            paired = [(s, h) for s, h in zip(sell_profits, hold_profits)]
            diffs = [s - h for s, h in paired]
            lo, mean, hi = bootstrap_ci(diffs, n_boot=3000)
            print(f"  IC95% da diferenca: [${lo:+.4f}, ${hi:+.4f}]")
            if lo > 0:
                print(">>> !!! EDGE: vender cedo e sistematicamente melhor que segurar!")
            else:
                print(">>> IC95% cruza zero -- diferenca nao significativa.")
        else:
            print(">>> Vender cedo nao e melhor que segurar.")

    print("\n  Padrao do bid_price por amostra (media sobre trials sellable):")
    max_samples = max(len(r["bids"]) for r in sellable) if sellable else 0
    for t in range(min(max_samples, 15)):
        bids_at_t = [r["bids"][t]["bid_price"] for r in sellable
                     if t < len(r["bids"]) and r["bids"][t]["is_valid_to_sell"]]
        if bids_at_t:
            print(f"    sample {t}: bid medio=${statistics.mean(bids_at_t):.4f} "
                  f"(min=${min(bids_at_t):.4f}, max=${max(bids_at_t):.4f}, n={len(bids_at_t)})")

    # Analise 6: regra non-hindsight -- vender no primeiro bid >= threshold
    print("\n  Regra non-hindsight: vender no 1o bid >= threshold")
    thresholds = [11, 12, 13, 14, 15, 16, 17, 18]
    for thresh in thresholds:
        sell_profits_rule = []
        hold_profits_rule = []
        for r in sellable:
            triggered = False
            for b in r["bids"]:
                if b["is_valid_to_sell"] and b["bid_price"] >= thresh:
                    sell_profits_rule.append(b["bid_price"] - r["buy_price"])
                    hold_profits_rule.append(r["profit_hold"])
                    triggered = True
                    break
            if not triggered:
                # Nao vendeu -- segurar ate expiry
                hold_profits_rule.append(r["profit_hold"])
        if sell_profits_rule:
            ev_rule = statistics.mean(sell_profits_rule)
            n_trig = len(sell_profits_rule)
            print(f"    thresh=${thresh}: n_vendidos={n_trig}/{len(sellable)} | "
                  f"EV_sell=${ev_rule:+.4f} | EV_hold_correspondente="
                  f"${statistics.mean(hold_profits_rule[:n_trig]):+.4f}")
        else:
            print(f"    thresh=${thresh}: 0 vendidos")

    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
