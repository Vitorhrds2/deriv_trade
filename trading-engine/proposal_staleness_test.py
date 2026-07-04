"""Teste de Proposal Staleness: a Deriv honra uma cotacao (proposal) stale quando o
spot ja se moveu, ou reprecifica/rejeita?

Hipotese: se a Deriv honra o ask_price de uma proposal mesmo apos o spot se mover
favoravelmente, pode haver edge em:
  1. Pedir proposal CALL quando spot esta num ponto qualquer
  2. Esperar o spot subir (favoravel para CALL)
  3. Comprar a cotacao stale (preco antigo, mais barato)
  4. Se entry_spot = T+1 e o spot ja subiu, maior chance de win

Fluxo de teste (diferente do entry_spot_lag_test que usava buy_direct):
  - Usa proposal -> buy(proposal_id) flow, que e onde staleness poderia existir
  - basis="payout" (fixa payout, deixa ask_price/custo variar com spot) pra detectar
    se o custo cobrado difere do ask_price original
  - Mede: ask_price original vs buy_price efetivo vs spot no momento da proposal vs
    spot no momento do buy

Usa conta DEMO (mesmo padrao de validate_demo dos outros testes).
"""
import argparse
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
]:
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
    print(f"  Conta conectada: {connected} | demo={demo_ids} | real={real_ids} -> "
          f"{'OK DEMO' if ok else 'NAO CONFIRMADA COMO DEMO!'}")
    return ok


async def run_trial(client, symbol, payout_amount, idx):
    """Um trial: pede proposal, espera spot mover, tenta comprar com proposal_id stale."""
    t0 = state["last_tick"]
    if t0 is None:
        print(f"  [{idx}] sem tick disponivel -- pulando")
        return None

    # 1. Pedir proposal (CALL, 1 tick, basis=payout -> ask_price varia com spot)
    prop_res = await client.send_request({
        "proposal": 1,
        "amount": payout_amount,
        "basis": "payout",
        "contract_type": "CALL",
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": 1,
        "duration_unit": "t",
    })
    if "error" in prop_res:
        print(f"  [{idx}] proposal erro: {prop_res['error'].get('message')}")
        return None

    prop = prop_res["proposal"]
    proposal_id = prop["id"]
    ask_price = float(prop["ask_price"])
    prop_spot = float(prop.get("spot", 0))
    prop_date_expiry = int(prop.get("date_expiry", 0))
    prop_local_t = time.time()

    # 2. Esperar o proximo tick (spot se move)
    tick_before = t0["value"]
    waited = 0
    while True:
        await asyncio.sleep(0.05)
        cur = state["last_tick"]
        if cur and cur["epoch"] != t0["epoch"]:
            break
        waited += 0.05
        if waited > 5:
            break

    spot_at_buy = state["last_tick"]
    spot_moved = spot_at_buy["value"] - tick_before if spot_at_buy else 0
    spot_direction = "UP" if spot_moved > 0 else "DOWN" if spot_moved < 0 else "FLAT"

    # 3. Tentar comprar com o proposal_id e ask_price originais
    buy_res = await client.send_request({
        "buy": proposal_id,
        "price": ask_price,
    })

    if "error" in buy_res:
        err_msg = buy_res["error"].get("message", "")
        print(f"  [{idx}] spot {spot_direction} ({tick_before:.5f}->{spot_at_buy['value']:.5f}) | "
              f"ask=${ask_price:.4f} | BUY REJEITADO: {err_msg}")
        return {
            "accepted": False, "rejection": err_msg,
            "ask_price": ask_price, "spot_moved": spot_moved,
            "spot_direction": spot_direction,
        }

    b = buy_res["buy"]
    buy_price = float(b.get("buy_price", 0))
    buy_spot = float(b.get("current_spot", 0))
    cid = b["contract_id"]

    # 4. Esperar settlement
    final = None
    for _ in range(75):
        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        c = poc.get("proposal_open_contract", {})
        if c.get("is_sold"):
            final = c
            break
        await asyncio.sleep(0.2)

    profit = float(final.get("profit", 0)) if final else None
    price_diff = buy_price - ask_price
    stale_honored = abs(price_diff) < 1e-9

    # Favoravel: spot subiu (CALL fica mais propenso a win) e compramos ao preco antigo
    favorable = spot_moved > 0

    flag = ""
    if stale_honored and favorable:
        flag = "*** STALE HONORED + FAVORAVEL ***"
    elif stale_honored:
        flag = "stale honored (spot moveu contra, nao favoravel)"
    else:
        flag = f"REPRECIFICADO (buy=${buy_price:.4f} vs ask=${ask_price:.4f}, diff=${price_diff:+.4f})"

    print(f"  [{idx}] spot {spot_direction} ({tick_before:.5f}->{spot_at_buy['value']:.5f}, "
          f"diff={spot_moved:+.5f}) | ask=${ask_price:.4f} buy=${buy_price:.4f} | {flag} | "
          f"profit={f'${profit:+.4f}' if profit is not None else 'N/A'}")

    return {
        "accepted": True, "stale_honored": stale_honored,
        "favorable": favorable, "spot_moved": spot_moved,
        "spot_direction": spot_direction,
        "ask_price": ask_price, "buy_price": buy_price, "price_diff": price_diff,
        "profit": profit,
    }


async def main():
    ap = argparse.ArgumentParser(description="Teste de Proposal Staleness na Deriv")
    ap.add_argument("--symbol", default="1HZ10V")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--payout", type=float, default=2.0,
                    help="Payout fixo (basis=payout); ask_price/custo varia com spot")
    ap.add_argument("--cooldown-s", type=float, default=1.0)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados (.env).")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    print("=" * 90)
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao confirmada como DEMO. ABORTANDO.")
        await client.disconnect()
        return

    # Subscrever ticks
    await client.subscribe_ticks(args.symbol, on_tick)
    await asyncio.sleep(2)  # esperar primeiro tick

    print(f">>> Symbol={args.symbol} | trials={args.trials} | payout=${args.payout} | "
          f"duration=1 tick (CALL) | fluxo: proposal -> buy(proposal_id)")
    print("=" * 90)

    results = []
    try:
        for i in range(args.trials):
            rec = await run_trial(client, args.symbol, args.payout, i)
            if rec:
                results.append(rec)
            await asyncio.sleep(args.cooldown_s)
    finally:
        await client.disconnect()

    print("\n" + "=" * 90)
    n = len(results)
    if n == 0:
        print("Nenhum trial valido.")
        return

    accepted = [r for r in results if r.get("accepted")]
    rejected = [r for r in results if not r.get("accepted")]
    stale = [r for r in accepted if r.get("stale_honored")]
    reprice = [r for r in accepted if not r.get("stale_honored")]
    stale_fav = [r for r in stale if r.get("favorable")]
    stale_unfav = [r for r in stale if not r.get("favorable")]

    print(f"RESULTADO: {n} trials | aceitos={len(accepted)} | rejeitados={len(rejected)}")
    print(f"  Dos aceitos: stale honored={len(stale)} | reprecificados={len(reprice)}")
    print(f"  Stale honored: favoravel={len(stale_fav)} | nao-favoravel={len(stale_unfav)}")

    if rejected:
        rej_msgs = {}
        for r in rejected:
            m = r.get("rejection", "unknown")
            rej_msgs[m] = rej_msgs.get(m, 0) + 1
        print(f"  Rejeicoes: {rej_msgs}")

    if stale_fav:
        profits_fav = [r["profit"] for r in stale_fav if r.get("profit") is not None]
        if profits_fav:
            wins = sum(1 for p in profits_fav if p > 0)
            print(f"\n  STALE + FAVORAVEL: {len(profits_fav)} trades | WR={wins}/{len(profits_fav)} "
                  f"({wins/len(profits_fav)*100:.1f}%) | "
                  f"EV=${sum(profits_fav)/len(profits_fav):.4f}")
            if wins / len(profits_fav) > 0.55:
                print(">>> !!! WR elevado em stale+favoravel -- possivel edge!")
            else:
                print(">>> WR nao elevado o suficiente para indicar edge.")
    else:
        print("\n>>> Nenhum caso stale+favoravel para avaliar edge.")

    if reprice:
        diffs = [r["price_diff"] for r in reprice]
        print(f"\n  REPRECIFICACOES: diff medio ask->buy = ${sum(diffs)/len(diffs):.4f} "
              f"(min=${min(diffs):.4f}, max=${max(diffs):.4f})")

    # Veredito
    print("\n" + "-" * 90)
    if len(stale) > 0 and len(stale_fav) > 0:
        fav_rate = len(stale_fav) / len(stale) if stale else 0
        print(f"Stale honored em {len(stale)}/{len(accepted)} compras aceitas.")
        print(f"Taxa de stale+favoravel: {len(stale_fav)}/{len(stale)} = {fav_rate*100:.1f}%")
        if fav_rate > 0.5:
            print(">>> MAIS da metade dos stale cases sao favoraveis -- investigar EV positivo.")
        else:
            print(">>> Menos da metade favoravel -- spot se move contra tao frequentemente quanto a favor.")
    elif len(reprice) == len(accepted) and len(accepted) > 0:
        print(">>> Deriv SEMPRE reprecifica no buy -- proposal staleness nao existe (cotacao e so um quote).")
    elif len(rejected) == n:
        print(">>> Todos os buys com proposal_id foram rejeitados -- proposta expira muito rapido.")
    else:
        print(">>> Resultado misto -- ver detalhes acima.")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
