"""Scan de mispricing em Multipliers (MULTUP/MULTDOWN) -- unico produto Deriv ativo nunca testado.

Mecanica (confirmada via probe_multiplier.py e compra real):
- Sem payout fixo, sem expiry. Payoff = (spot_final - entry) * multiplier / spot_entry (aprox).
- Custo = ask_price - stake (comissão cobrada pela Deriv).
- ask_price varia por multiplier e cancellation duration.
- Spot e driftless (martingale), entao EV do payoff bruto = 0.
- EV total = 0 - comissao = -comissao (sempre negativo se comissao > 0).

Mas ha uma sutileza: o SL/TP e o cancellation criam optionality.
- Cancellation: apos N minutos, o contrato e cancelado (fechado) ao preco de mercado.
- Se houver stop_loss automatico, isso e uma option vendida pela Deriv (limita perda maxima).
- Se o stop_loss for "gratis" (sem custo extra), pode haver edge.

Teste:
1. Medir comissao (ask_price - stake) para cada (multiplier, cancellation, direction).
2. Comprar contratos reais, medir profit final vs comissao paga.
3. Monte Carlo: simular payoff com e sem stop_loss para ver se o optionality compensa a comissao.
"""
import argparse
import asyncio
import json
import os
import random
import statistics
import sys

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import summarize, bootstrap_ci, wilson_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

SYMBOLS = ["1HZ10V", "1HZ100V"]
MULTIPLIERS = [400, 1000, 2000, 3000, 4000]
CANCELLATIONS = ["5m", "15m", "60m"]
N_HISTORY_TICKS = 10000
N_SIMULATIONS = 20000


async def fetch_ticks(client, symbol, count):
    all_prices = []
    end = "latest"
    remaining = count
    while remaining > 0:
        batch = min(remaining, 1000)
        res = await client.get_ticks_history(symbol, count=batch, end=end)
        hist = res.get("history", {})
        prices = hist.get("prices", [])
        times = hist.get("times", [])
        if not prices:
            break
        all_prices = prices + all_prices
        remaining -= len(prices)
        end = times[0] - 1
        await asyncio.sleep(0.12)
    return all_prices


async def get_multiplier_quote(client, contract_type, symbol, multiplier, cancellation):
    res = await client.send_request({
        "proposal": 1, "amount": 10, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": symbol,
        "multiplier": multiplier, "cancellation": cancellation,
    })
    if "error" in res:
        return None
    p = res.get("proposal", {})
    return {
        "ask_price": float(p.get("ask_price", 0)),
        "spot": float(p.get("spot", 0)),
        "payout": float(p.get("payout", 0)),
        "limit_order": p.get("limit_order", {}),
        "contract_details": p.get("contract_details", {}),
    }


async def get_multiplier_quote_retry(client_factory, contract_type, symbol, multiplier, cancellation, max_retries=3):
    """Get quote with WS reconnect retry."""
    for attempt in range(max_retries):
        try:
            client = await client_factory.get()
            return await get_multiplier_quote(client, contract_type, symbol, multiplier, cancellation)
        except Exception as e:
            print(f"  [retry {attempt+1}/{max_retries}] {e}")
            await client_factory.reset()
            await asyncio.sleep(2)
    return None


def monte_carlo_multiplier(returns_pool, n_ticks, spot, multiplier, is_up,
                           n_sims, rng, stop_loss_pct=None):
    """Simula payoff de um Multiplier contract.

    Payoff = (spot_final - entry) * multiplier / entry  [MULTUP]
           = (entry - spot_final) * multiplier / entry  [MULTDOWN]

    Com stop_loss: se a perda exceder stop_loss_pct do stake, fecha no SL.
    """
    pool_n = len(returns_pool)
    payoffs = []  # em dolares, sobre stake de $10
    stake = 10.0

    for _ in range(n_sims):
        total_return = sum(returns_pool[rng.randrange(pool_n)] for _ in range(n_ticks))
        terminal = spot + total_return

        if is_up:
            raw_payout = (terminal - spot) * multiplier / spot * stake
        else:
            raw_payout = (spot - terminal) * multiplier / spot * stake

        # Stop loss: limita perda maxima
        if stop_loss_pct is not None:
            sl_amount = -stake * stop_loss_pct
            if raw_payout < sl_amount:
                raw_payout = sl_amount

        payoffs.append(raw_payout)

    return payoffs


class ClientFactory:
    """Lazy WS client with reconnect."""
    def __init__(self):
        self.client = None

    async def get(self):
        if self.client is None:
            self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
            await self.client.connect()
        return self.client

    async def reset(self):
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None


async def main():
    ap = argparse.ArgumentParser(description="Multiplier edge scan")
    ap.add_argument("--symbol", default="1HZ10V")
    ap.add_argument("--live-trials", type=int, default=0,
                    help="Buy real contracts and measure actual profit vs commission")
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    factory = ClientFactory()

    # 1. Baixar ticks reais para calibrar Monte Carlo
    for attempt in range(3):
        try:
            client = await factory.get()
            print(f"Baixando {N_HISTORY_TICKS} ticks reais de {args.symbol}...")
            prices = await fetch_ticks(client, args.symbol, N_HISTORY_TICKS)
            break
        except Exception as e:
            print(f"  [fetch_ticks retry {attempt+1}] {e}")
            await factory.reset()
            await asyncio.sleep(2)
    else:
        print("ERRO: nao conseguiu baixar ticks apos 3 tentativas.")
        return

    raw_returns = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    mean_r = statistics.mean(raw_returns)
    demeaned = [r - mean_r for r in raw_returns]
    print(f"{len(prices)} ticks | drift={mean_r:+.6f} (removido) | "
          f"std/tick={statistics.pstdev(raw_returns):.5f}")

    rng = random.Random(42)

    # 2. Scan de comissao para cada (multiplier, cancellation, direction)
    print(f"\n{'='*90}")
    print(f"Scan de comissao: {args.symbol}")
    print(f"{'='*90}")
    print(f"{'Type':<10} {'Mult':>6} {'Cancel':>7} {'Ask':>8} {'Comm':>8} {'Comm%':>7}")
    print("-" * 50)

    all_results = []

    for mult in MULTIPLIERS:
        for cancel in CANCELLATIONS:
            for ct, is_up in [("MULTUP", True), ("MULTDOWN", False)]:
                q = await get_multiplier_quote_retry(factory, ct, args.symbol, mult, cancel)
                if not q:
                    continue
                commission = q["ask_price"] - 10.0
                comm_pct = commission / 10.0 * 100

                # Ticks aproximados para a cancellation duration
                # 1HZ10V = ~1 tick/s
                cancel_secs = int(cancel[:-1]) * 60
                n_ticks = cancel_secs  # ~1 tick/s

                # Monte Carlo: payoff bruto (sem comissao)
                payoffs = monte_carlo_multiplier(
                    demeaned, n_ticks, q["spot"], mult, is_up,
                    N_SIMULATIONS, rng, stop_loss_pct=None
                )
                mc_mean = statistics.mean(payoffs)
                mc_lo, mc_mean_ci, mc_hi = bootstrap_ci(payoffs, n_boot=3000)

                # EV = payoff bruto - comissao
                ev = mc_mean - commission
                ev_lo = mc_lo - commission
                ev_hi = mc_hi - commission

                flag = " <<< CANDIDATO" if ev_lo > 0 else ""
                print(f"{ct:<10} {mult:>6} {cancel:>7} ${q['ask_price']:>7.2f} "
                      f"${commission:>7.2f} {comm_pct:>6.2f}% | "
                      f"MC_payoff=${mc_mean:+.4f} EV=${ev:+.4f} "
                      f"IC95%[${ev_lo:+.4f},{ev_hi:+.4f}]{flag}")

                all_results.append({
                    "type": ct, "multiplier": mult, "cancellation": cancel,
                    "ask_price": q["ask_price"], "commission": commission,
                    "mc_payoff": mc_mean, "ev": ev, "ev_lo": ev_lo, "ev_hi": ev_hi,
                })
                await asyncio.sleep(0.2)

    # 3. Veredito
    print(f"\n{'='*90}")
    print(f"VEREDITO -- {len(all_results)} celulas testadas")
    print(f"{'='*90}")

    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge (EV_lo > 0):")
        for c in candidates:
            print(f"    {c['type']} mult={c['multiplier']} cancel={c['cancellation']}: "
                  f"EV_lo=${c['ev_lo']:+.4f}")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo > 0.")
        comms = [r["commission"] for r in all_results]
        evs = [r["ev"] for r in all_results]
        if comms:
            print(f"    Comissao: min=${min(comms):.4f} max=${max(comms):.4f} "
                  f"media=${statistics.mean(comms):.4f}")
            print(f"    EV: min=${min(evs):+.4f} max=${max(evs):+.4f} "
                  f"media=${statistics.mean(evs):+.4f}")
            print(f"    Padrao: payoff bruto MC ~0 (martingale), EV = -comissao.")

    # 4. Análise: comissão varia com multiplier e cancellation?
    print(f"\n{'='*90}")
    print("Analise: comissao por multiplier x cancellation (MULTUP = MULTDOWN)")
    print(f"{'='*90}")
    print(f"{'Mult':>6} |", end="")
    for cancel in CANCELLATIONS:
        print(f" {cancel:>10}", end="")
    print()
    for mult in MULTIPLIERS:
        print(f"{mult:>6} |", end="")
        for cancel in CANCELLATIONS:
            comms = [r["commission"] for r in all_results
                     if r["multiplier"] == mult and r["cancellation"] == cancel]
            if comms:
                print(f" ${comms[0]:>8.2f}", end="")
            else:
                print(f" {'N/A':>10}", end="")
        print()

    # 5. Live trials (opcional)
    if args.live_trials > 0:
        print(f"\n{'='*90}")
        print(f"Live trials: {args.live_trials} contratos reais MULTUP mult=1000 cancel=5m")
        print(f"{'='*90}")

        state = {"last_tick": None}

        def on_tick(data):
            t = data.get("tick")
            if t and "quote" in t:
                state["last_tick"] = float(t["quote"])

        client = await factory.get()
        await client.subscribe_ticks(args.symbol, on_tick)
        await asyncio.sleep(2)

        live_profits = []
        for i in range(args.live_trials):
            try:
                client = await factory.get()
                buy_res = await client.send_request({
                "buy": 1, "price": 15.0,
                "parameters": {
                    "amount": 10, "basis": "stake", "contract_type": "MULTUP",
                    "currency": "USD", "underlying_symbol": args.symbol,
                    "multiplier": 1000, "cancellation": "5m",
                }
            })
            except Exception as e:
                print(f"  [{i}] WS erro: {e} -- reset")
                await factory.reset()
                continue
            if "error" in buy_res:
                print(f"  [{i}] BUY erro: {buy_res['error'].get('message','')}")
                continue
            b = buy_res["buy"]
            cid = b["contract_id"]
            buy_price = float(b.get("buy_price", 0))
            print(f"  [{i}] bought @ ${buy_price:.2f}, monitoring 30s...")

            # Monitorar 30s depois vender
            await asyncio.sleep(30)
            try:
                client = await factory.get()
                sell_res = await client.send_request({"sell": cid, "price": 0})
                if "error" in sell_res:
                    poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
                    c = poc.get("proposal_open_contract", {})
                    profit = float(c.get("profit", 0))
                    print(f"  [{i}] sell erro, POC profit=${profit:+.4f}")
                    live_profits.append(profit)
                else:
                    poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
                    c = poc.get("proposal_open_contract", {})
                    profit = float(c.get("profit", 0))
                    print(f"  [{i}] sold, profit=${profit:+.4f}")
                    live_profits.append(profit)
            except Exception as e:
                print(f"  [{i}] WS erro no sell: {e} -- reset")
                await factory.reset()
            await asyncio.sleep(1)

        if live_profits:
            summarize("Live MULTUP mult=1000 30s hold", live_profits)
            comm = next((r["commission"] for r in all_results
                        if r["multiplier"] == 1000 and r["cancellation"] == "5m"), 0)
            print(f"  Comissao teorica: ${comm:.4f}")
            print(f"  EV esperado: ~${-comm:.4f} (payoff bruto ~0)")

    c = await factory.get()
    try:
        await c.disconnect()
    except Exception:
        pass
    print("\n" + "=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
