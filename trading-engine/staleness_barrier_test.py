"""Teste de Proposal Staleness com HIGHER/LOWER (barrier contracts) -- onde o spot level
no momento do buy AFETA a probabilidade de win, diferente de CALL/PUT onde entry = T+1.

Hipotese: se a Deriv honra uma proposal stale para HIGHER/LOWER, e o spot se moveu
FAVORAVELMENTE (mais perto da barreira), compramos a cotacao antiga (mais barata) num
contrato que agora tem maior probabilidade de win.

Mecanica:
  - HIGHER +0.33: ganha se spot_final > spot_inicial + 0.33 (barreira relativa ao spot na compra)
  - Se pedimos proposal quando spot=S, spot sobe para S+0.20, e compramos ao preco stale:
    a barreira ainda e S+0.33, mas agora so precisamos de +0.13 mais (vs +0.33 original)
  - Preco stale reflete probabilidade de +0.33, mas realidade e +0.13 -> edge!

Controle: tambem medimos casos onde spot se moveu DESFAVORAVELMENTE (mais longe da barreira).
Se a Deriv honra nesses casos tambem, o edge teorico se cancela (voce tambem compra caro
quando o spot foi contra). A questao e se podemos FILTRAR so comprar quando favoravel.

Fluxo:
  1. Pedir proposal HIGHER +0.33 (5 ticks)
  2. Esperar 1 tick (spot se move)
  3. Se spot subiu (favoravel): comprar com proposal_id stale
  4. Se spot desceu (desfavoravel): NAO comprar (descartar proposal)
  5. Medir WR e EV dos trades favoraveis vs controle (comprar sempre, independente de direcao)
"""
import argparse
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import wilson_ci, summarize

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


async def run_trial(client, symbol, stake, barrier, duration, idx, mode):
    """mode: 'filter' = so compra se favoravel; 'always' = compra sempre (controle)"""
    t0 = state["last_tick"]
    if t0 is None:
        return None

    # 1. Pedir proposal HIGHER com barrier relativo
    prop_res = await client.send_request({
        "proposal": 1, "amount": stake, "basis": "stake",
        "contract_type": "HIGHER", "currency": "USD", "underlying_symbol": symbol,
        "duration": duration, "duration_unit": "t", "barrier": barrier,
    })
    if "error" in prop_res:
        return None
    prop = prop_res["proposal"]
    proposal_id = prop["id"]
    ask_price = float(prop["ask_price"])
    payout = float(prop["payout"])
    prop_spot = float(prop.get("spot", 0))

    # 2. Esperar proximo tick
    t0_epoch = t0["epoch"]
    waited = 0
    while True:
        await asyncio.sleep(0.05)
        cur = state["last_tick"]
        if cur and cur["epoch"] != t0_epoch:
            break
        waited += 0.05
        if waited > 5:
            break

    spot_at_buy = state["last_tick"]
    spot_moved = spot_at_buy["value"] - prop_spot if spot_at_buy else 0
    favorable = spot_moved > 0  # HIGHER: spot subiu = mais perto da barreira = favoravel

    # 3. Decidir se compra
    if mode == "filter" and not favorable:
        print(f"  [{idx}] spot {'UP' if spot_moved > 0 else 'DOWN'} "
              f"({prop_spot:.5f}->{spot_at_buy['value']:.5f}, diff={spot_moved:+.5f}) | "
              f"SKIP (desfavoravel, filtro)")
        return {"skipped": True, "favorable": False, "spot_moved": spot_moved}

    # 4. Comprar com proposal_id stale
    buy_res = await client.send_request({"buy": proposal_id, "price": ask_price})
    if "error" in buy_res:
        print(f"  [{idx}] BUY REJEITADO: {buy_res['error'].get('message','')}")
        return {"skipped": True, "rejected": True}

    b = buy_res["buy"]
    buy_price = float(b.get("buy_price", 0))
    cid = b["contract_id"]
    stale_honored = abs(buy_price - ask_price) < 1e-9

    # 5. Esperar settlement
    final = None
    for _ in range(100):
        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        c = poc.get("proposal_open_contract", {})
        if c.get("is_sold"):
            final = c
            break
        await asyncio.sleep(0.2)

    profit = float(final.get("profit", 0)) if final else None
    won = profit is not None and profit > 0

    flag = "STALE+FAV" if (stale_honored and favorable) else \
           "STALE+UNFAV" if stale_honored else \
           f"REPRICE (${buy_price:.4f} vs ${ask_price:.4f})"

    print(f"  [{idx}] spot {'UP' if spot_moved > 0 else 'DOWN'} "
          f"({prop_spot:.5f}->{spot_at_buy['value']:.5f}, diff={spot_moved:+.5f}) | "
          f"ask=${ask_price:.4f} buy=${buy_price:.4f} payout=${payout:.2f} | {flag} | "
          f"profit={f'${profit:+.4f}' if profit is not None else 'N/A'}")

    return {
        "skipped": False, "stale_honored": stale_honored,
        "favorable": favorable, "spot_moved": spot_moved,
        "ask_price": ask_price, "buy_price": buy_price, "payout": payout,
        "profit": profit, "won": won,
    }


async def main():
    ap = argparse.ArgumentParser(description="Staleness + HIGHER/LOWER barrier exploit test")
    ap.add_argument("--symbol", default="1HZ10V")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--barrier", default="+0.33")
    ap.add_argument("--duration", type=int, default=5)
    ap.add_argument("--cooldown-s", type=float, default=1.0)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    print("=" * 90)
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao DEMO. ABORTANDO.")
        await client.disconnect()
        return

    await client.subscribe_ticks(args.symbol, on_tick)
    await asyncio.sleep(2)

    print(f">>> {args.symbol} | HIGHER barrier={args.barrier} | dur={args.duration}t | "
          f"stake=${args.stake} | trials={args.trials}")
    print(f">>> Modo: FILTER (so compra se spot subiu favoravelmente)")
    print("=" * 90)

    results = []
    try:
        for i in range(args.trials):
            rec = await run_trial(client, args.symbol, args.stake, args.barrier,
                                  args.duration, i, "filter")
            if rec:
                results.append(rec)
            await asyncio.sleep(args.cooldown_s)
    finally:
        await client.disconnect()

    print("\n" + "=" * 90)
    n = len(results)
    bought = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    fav = [r for r in bought if r.get("favorable")]
    unfav = [r for r in bought if not r.get("favorable")]

    print(f"Total: {n} trials | comprados={len(bought)} | skipped={len(skipped)}")
    print(f"Comprados: favoravel={len(fav)} | desfavoravel={len(unfav)}")

    if bought:
        stale_count = sum(1 for r in bought if r.get("stale_honored"))
        print(f"Stale honored: {stale_count}/{len(bought)}")

        profits_all = [r["profit"] for r in bought if r.get("profit") is not None]
        profits_fav = [r["profit"] for r in fav if r.get("profit") is not None]

        if profits_all:
            summarize("TODOS trades comprados", profits_all)
        if profits_fav:
            summarize("APENAS favoraveis (filtro)", profits_fav)
            wins = sum(1 for p in profits_fav if p > 0)
            wr_lo, wr_hi = wilson_ci(wins, len(profits_fav))
            # Breakeven WR = stake / payout
            payout = fav[0]["payout"] if fav else args.stake * 2
            breakeven = args.stake / payout if payout else 0.5
            print(f"\n  WR favoraveis: {wins}/{len(profits_fav)} = {wins/len(profits_fav)*100:.1f}% "
                  f"IC95% [{wr_lo*100:.1f}%, {wr_hi*100:.1f}%] vs breakeven {breakeven*100:.1f}%")
            if wr_lo > breakeven:
                print(">>> !!! EDGE DETECTADO: WR favoravel bate breakeven com IC95% inteiro acima!")
            else:
                print(">>> IC95% cruza ou abaixo do breakeven -- sem edge confirmado.")

    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
