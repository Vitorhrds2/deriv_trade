"""Teste DEDICADO e rigoroso da observacao lateral encontrada em entry_spot_lag_test.py:
WR agregado de 64% (48/75) em compras de CALL fixo (1 tick, 1HZ10V), IC95% Wilson
[52.7%,73.9%] mal acima do breakeven de 92% payout (52.08%) -- suspeito de ser ruido
pos-hoc (direcao nao randomizada, N pequeno, amostra unica), mas nao descartado sem um
teste proprio, pre-registrado, com controle.

Hipotese: existe um vies direcional real (CALL > PUT, ou WR agregado > breakeven) em
contratos de 1 tick no 1HZ10V, ou o achado anterior foi so drift de curto prazo de uma
amostra pequena e nao-randomizada (o teste anterior SEMPRE comprava CALL, entao nao
consegue distinguir "CALL e favorecido" de "o mercado subiu por acaso nesses minutos")?

Metodo (mesmo rigor de arb_order_test.py / hft_arbitrage_bot.py SHADOW_AB_TESTING):
  - Pra cada trial, sorteia CALL ou PUT 50/50 -- SEM gatilho/sinal, e um teste as cegas
    que controla exatamente o confound "drift de curto prazo no periodo testado" que o
    teste anterior nao controlava (CALL e PUT ficam expostos ao MESMO caminho de preco,
    so a direcao da aposta e sorteada).
  - N grande (default 200) pra ter poder estatistico de sobra.
  - Compara: WR(CALL) vs WR(PUT) via bootstrap_diff_ci (deveria cruzar zero se simetrico)
    e WR combinado vs o breakeven implicito do payout real (Wilson CI).

Usa conta DEMO (trava explicita, mesmo padrao de arb_order_test.py/entry_spot_lag_test.py)
e stake minimo.

Uso:
  python tick_direction_bias_test.py --symbol 1HZ10V --trials 200 --stake 1
"""
import argparse
import asyncio
import json
import os
import random
import sys

from dotenv import load_dotenv

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    r"C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env",
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import wilson_ci, bootstrap_diff_ci, summarize

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")


async def validate_demo(client):
    # Autoritativo: confirma pela API que a conta conectada e account_type=demo (mesmo
    # padrao de arb_order_test.py/entry_spot_lag_test.py). Nunca envia ordem sem isso.
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


async def run_trial(client, symbol, stake, idx, rng):
    direction = rng.choice(["CALL", "PUT"])
    buy = await client.buy_direct(contract_type=direction, stake=stake, symbol=symbol,
                                   duration=1, duration_unit="t")
    if "error" in buy:
        print(f"  [{idx}] buy erro: {buy['error'].get('message')}")
        return None
    b = buy["buy"]
    if idx == 0:
        print(f"  [debug trial 0] campos do buy: {sorted(b.keys())}")
    cid = b["contract_id"]
    payout = float(b.get("payout", 0) or 0)
    buy_price = float(b.get("buy_price", stake) or stake)

    final = None
    for _ in range(75):  # ate ~15s (1 tick ~1-2s p/ entry + ~1-2s p/ exit + overhead)
        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        c = poc.get("proposal_open_contract", {})
        if c.get("is_sold"):
            final = c
            break
        await asyncio.sleep(0.2)

    if final is None:
        print(f"  [{idx}] timeout esperando settlement (contrato {cid}).")
        return None

    profit = float(final.get("profit", 0))
    won = profit > 0
    if idx < 3 or (idx + 1) % 25 == 0:
        print(f"  [{idx}] {direction} | profit=${profit:+.4f} | {'WIN' if won else 'loss'}")

    return {"direction": direction, "profit": profit, "won": won,
            "payout": payout, "buy_price": buy_price}


async def main():
    ap = argparse.ArgumentParser(description="Teste dedicado de vies direcional (CALL/PUT randomizado, 1 tick)")
    ap.add_argument("--symbol", default="1HZ10V")
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--cooldown-s", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados (.env).")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    print("=" * 84)
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao confirmada como DEMO/virtual. ABORTANDO (nenhuma ordem enviada).")
        await client.disconnect()
        return
    print(f">>> Symbol={args.symbol} | trials={args.trials} | stake=${args.stake} | "
          f"duration=1 tick | direcao RANDOMIZADA 50/50 (sem gatilho, blind)")
    print("=" * 84)

    rng = random.Random(args.seed)
    results = []
    try:
        for i in range(args.trials):
            rec = await run_trial(client, args.symbol, args.stake, i, rng)
            if rec:
                results.append(rec)
            if (i + 1) % 25 == 0:
                print(f"    ... {i + 1}/{args.trials} trials completos")
            await asyncio.sleep(args.cooldown_s)
    finally:
        await client.disconnect()

    print("\n" + "=" * 84)
    n = len(results)
    if n == 0:
        print("Nenhum trial valido.")
        return

    payout = results[0]["payout"]
    buy_price = results[0]["buy_price"]
    breakeven_wr = (buy_price / payout) if payout else 0.5
    print(f"Payout=${payout:.2f} | Stake=${buy_price:.2f} | Breakeven WR implicito={breakeven_wr * 100:.2f}%")

    all_profits = [r["profit"] for r in results]
    call_profits = [r["profit"] for r in results if r["direction"] == "CALL"]
    put_profits = [r["profit"] for r in results if r["direction"] == "PUT"]

    summarize(f"COMBINADO ({args.symbol}, 1 tick, CALL+PUT randomizado)", all_profits)
    if call_profits:
        summarize("  Apenas CALL", call_profits)
    if put_profits:
        summarize("  Apenas PUT", put_profits)

    print("\n" + "-" * 84)
    wins = sum(1 for p in all_profits if p > 0)
    wr_lo, wr_hi = wilson_ci(wins, n)
    print(f"WR combinado IC95%: [{wr_lo * 100:.2f}%, {wr_hi * 100:.2f}%] vs breakeven {breakeven_wr * 100:.2f}%")
    if wr_lo > breakeven_wr:
        print(">>> !!! WR combinado bate o breakeven com IC95% inteiro acima -- EDGE REAL candidato!")
    elif wr_hi < breakeven_wr:
        print(">>> WR combinado fica ABAIXO do breakeven (IC95% inteiro) -- consistente com house edge normal.")
    else:
        print(">>> IC95% cruza o breakeven -- SEM edge estatisticamente distinguivel (ruido).")

    if call_profits and put_profits and len(call_profits) >= 5 and len(put_profits) >= 5:
        lo, point, hi = bootstrap_diff_ci(call_profits, put_profits)
        print(f"\nCALL - PUT (EV/trade): {point:+.4f} | IC95% [{lo:+.4f}, {hi:+.4f}]")
        if lo > 0:
            print(">>> CALL bate PUT com IC95% inteiro acima de zero -- vies direcional real (CALL favorecido).")
        elif hi < 0:
            print(">>> PUT bate CALL com IC95% inteiro acima de zero -- vies direcional real (PUT favorecido).")
        else:
            print(">>> IC95% cruza zero -- SEM vies direcional detectavel entre CALL e PUT (esperado p/ RNG simetrico).")
    print("=" * 84)


if __name__ == "__main__":
    asyncio.run(main())
