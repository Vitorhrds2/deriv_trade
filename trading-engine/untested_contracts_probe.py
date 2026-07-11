"""
D77-D79 — Untested Contract Types Mispricing Scan
===================================================
35 contract types disponiveis na Deriv, mas varios nunca foram testados:
  - CALLE/PUTE (European-style calls/puts)
  - RESETCALL/RESETPUT (Reset options com barrier)
  - TURBOSLONG/TURBOSSHORT (Turbos / leveraged warrants)
  - UPORDOWN (Up or Down)

Metodologia:
  1. Descobrir estrutura de cada contract type via contracts_for + proposal
  2. Baixar 5000 ticks reais
  3. Monte Carlo: simular payoff para cada tipo
  4. Comparar fair value com ask_price
  5. Se EV = P(win) * payout - stake > 0, ha edge

Para CALLE/PUTE: mesma logica CALL/PUT mas settlement pode ser diferente.
Para RESET: barrier reseta em ponto especifico — payoff mais complexo.
Para TURBOS: warrant alavancado — payoff depende de multiplier e barrier.
Para UPORDOWN: paga se tick final > OU < entry (nao importa direcao escolhida?).
"""
import asyncio
import json
import os
import sys
import random
import statistics
import math
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
STAKE = 1.00
UNTESTED_TYPES = ["CALLE", "PUTE", "RESETCALL", "RESETPUT",
                  "TURBOSLONG", "TURBOSSHORT", "UPORDOWN"]
DURATIONS = [(5, "t"), (10, "t"), (15, "t"), (1, "m"), (5, "m")]
N_TICKS = 5000
N_MC = 10000

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "untested_contracts_results.json")


async def download_ticks(client, symbol, count=N_TICKS):
    all_prices = []
    remaining = count
    while remaining > 0:
        batch = min(remaining, 5000)
        res = await client.send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": batch,
            "end": "latest" if not all_prices else "latest",
            "start": 1,
            "style": "ticks",
        })
        if "error" in res:
            break
        prices = res.get("history", {}).get("prices", [])
        if not prices:
            break
        all_prices.extend([float(p) for p in prices])
        remaining -= len(prices)
        if len(prices) < batch:
            break
        await asyncio.sleep(0.3)
    return all_prices[:count]


def mc_call_put(prices, n_window, contract_type, payout):
    """Monte Carlo for CALL/PUT/CALLE/PUTE — paga se ultimo > (CALL) ou < (PUT) entry."""
    if len(prices) < n_window + 1:
        return None
    wins = 0
    for _ in range(N_MC):
        idx = random.randint(0, len(prices) - n_window - 1)
        entry = prices[idx]
        final = prices[idx + n_window]
        if contract_type in ("CALL", "CALLE"):
            if final > entry:
                wins += 1
        else:
            if final < entry:
                wins += 1
    p_win = wins / N_MC
    ev = p_win * payout - STAKE
    return {"p_win": p_win, "ev": ev, "payout": payout}


def mc_reset(prices, n_window, contract_type, payout):
    """Monte Carlo for RESETCALL/RESETPUT.
    Reset options: barrier reseta em ponto especifico.
    Assumimos: paga se (final - reset_point) > 0 (CALL) ou < 0 (PUT).
    Reset point = tick no meio da janela.
    """
    if len(prices) < n_window + 1:
        return None
    wins = 0
    for _ in range(N_MC):
        idx = random.randint(0, len(prices) - n_window - 1)
        window = prices[idx:idx + n_window + 1]
        entry = window[0]
        reset = window[len(window) // 2]  # midpoint
        final = window[-1]
        if contract_type == "RESETCALL":
            if final > reset:
                wins += 1
        else:
            if final < reset:
                wins += 1
    p_win = wins / N_MC
    ev = p_win * payout - STAKE
    return {"p_win": p_win, "ev": ev, "payout": payout}


def mc_turbos(prices, n_window, contract_type, payout, barrier):
    """Monte Carlo for TURBOSLONG/TURBOSSHORT.
    Turbos: leveraged warrant com barrier (knock-out).
    Paga payout se nao tocar barrier durante a janela E final > (LONG) ou < (SHORT) entry.
    """
    if len(prices) < n_window + 1:
        return None
    wins = 0
    knocked = 0
    for _ in range(N_MC):
        idx = random.randint(0, len(prices) - n_window - 1)
        window = prices[idx:idx + n_window + 1]
        entry = window[0]
        final = window[-1]

        # Check barrier (simplified — barrier is distance from entry)
        barrier_val = float(barrier) if barrier else 0
        if contract_type == "TURBOSLONG":
            knock_level = entry - barrier_val
            if min(window) <= knock_level:
                knocked += 1
                continue
            if final > entry:
                wins += 1
        else:
            knock_level = entry + barrier_val
            if max(window) >= knock_level:
                knocked += 1
                continue
            if final < entry:
                wins += 1
    p_win = wins / N_MC
    p_knock = knocked / N_MC
    ev = p_win * payout - STAKE
    return {"p_win": p_win, "ev": ev, "payout": payout, "knockout_rate": p_knock}


def mc_upordown(prices, n_window, payout):
    """Monte Carlo for UPORDOWN.
    UPORDOWN: paga se tick final != entry (qualquer direcao).
    Fair value: P(final != entry) * payout.
    Para random walk continuo: P(final != entry) ~ 1.0 (quase sempre).
    """
    if len(prices) < n_window + 1:
        return None
    wins = 0
    for _ in range(N_MC):
        idx = random.randint(0, len(prices) - n_window - 1)
        entry = prices[idx]
        final = prices[idx + n_window]
        if final != entry:
            wins += 1
    p_win = wins / N_MC
    ev = p_win * payout - STAKE
    return {"p_win": p_win, "ev": ev, "payout": payout}


async def main():
    print("=" * 90)
    print("D77-D79 — Untested Contract Types Mispricing Scan")
    print(f"  Symbol: {SYMBOL} | Stake: ${STAKE}")
    print(f"  Types: {', '.join(UNTESTED_TYPES)}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    # Download ticks once
    print(f"\n  Baixando {N_TICKS} ticks de {SYMBOL}...")
    prices = await download_ticks(client, SYMBOL)
    print(f"  Ticks: {len(prices)}")

    all_results = []

    for ct in UNTESTED_TYPES:
        print(f"\n{'='*60}")
        print(f"  {ct}")
        print(f"{'='*60}")

        for dur, unit in DURATIONS:
            payload = {
                "proposal": 1,
                "amount": STAKE,
                "basis": "stake",
                "contract_type": ct,
                "currency": "USD",
                "underlying_symbol": SYMBOL,
                "duration": dur,
                "duration_unit": unit,
            }

            res = await client.send_request(payload)
            if "error" in res:
                print(f"  {ct} {dur}{unit}: ERRO {res['error'].get('message', '')[:80]}")
                continue

            p = res["proposal"]
            ask_price = float(p.get("ask_price", 0))
            payout = float(p.get("payout", 0))
            spot = float(p.get("spot", 0))
            barrier = p.get("barrier")
            cd = p.get("contract_details", {})

            if payout <= 0:
                print(f"  {ct} {dur}{unit}: payout=0, pulando")
                continue

            payout_ratio = payout / STAKE
            print(f"  {ct} {dur}{unit}: ask=${ask_price:.4f} payout=${payout:.4f} "
                  f"ratio={payout_ratio:.4f} barrier={barrier}")
            if cd:
                print(f"    details: {json.dumps(cd, indent=2, ensure_ascii=False)[:300]}")

            # Monte Carlo
            n_window = dur if unit == "t" else dur * 60
            mc = None

            if ct in ("CALLE", "PUTE"):
                mc = mc_call_put(prices, n_window, ct, payout)
            elif ct in ("RESETCALL", "RESETPUT"):
                mc = mc_reset(prices, n_window, ct, payout)
            elif ct in ("TURBOSLONG", "TURBOSSHORT"):
                mc = mc_turbos(prices, n_window, ct, payout, barrier)
            elif ct == "UPORDOWN":
                mc = mc_upordown(prices, n_window, payout)

            if mc:
                ev = mc["ev"]
                p_win = mc["p_win"]
                be_p = STAKE / payout if payout > 0 else 999
                print(f"    MC: P(win)={p_win:.4f} (break-even={be_p:.4f}) "
                      f"EV=${ev:+.4f} {'*** EV>0 ***' if ev > 0 else ''}")
                if "knockout_rate" in mc:
                    print(f"    Knockout rate: {mc['knockout_rate']:.4f}")

                all_results.append({
                    "contract_type": ct,
                    "duration": dur,
                    "duration_unit": unit,
                    "ask_price": ask_price,
                    "payout": payout,
                    "payout_ratio": payout_ratio,
                    "barrier": barrier,
                    "mc_p_win": p_win,
                    "mc_ev": ev,
                    "break_even_p": be_p,
                    "contract_details": cd,
                    **mc,
                })

            await asyncio.sleep(0.4)

    # Verdict
    print(f"\n{'='*90}")
    print("  VEREDITO FINAL — UNTESTED CONTRACT TYPES")
    print(f"{'='*90}")

    candidates = [r for r in all_results if r["mc_ev"] > 0]
    print(f"\n  {len(all_results)} celulas testadas, {len(candidates)} com EV>0")

    if candidates:
        print("\n  *** CANDIDATOS A EDGE ***")
        for r in candidates:
            print(f"    {r['contract_type']} {r['duration']}{r['duration_unit']}: "
                  f"EV=${r['mc_ev']:+.4f} P(win)={r['mc_p_win']:.4f} "
                  f"payout_ratio={r['payout_ratio']:.4f}")
    else:
        print("\n  Nenhuma celula com EV>0. Todos os tipos refutados (house margin).")

    # Summary by type
    print(f"\n  Resumo por tipo:")
    for ct in UNTESTED_TYPES:
        ct_results = [r for r in all_results if r["contract_type"] == ct]
        if ct_results:
            best_ev = max(r["mc_ev"] for r in ct_results)
            worst_ev = min(r["mc_ev"] for r in ct_results)
            avg_p_win = statistics.mean(r["mc_p_win"] for r in ct_results)
            print(f"    {ct}: N={len(ct_results)} best_EV=${best_ev:+.4f} "
                  f"worst_EV=${worst_ev:+.4f} avg_P(win)={avg_p_win:.4f}")

    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Resultados salvos em {RESULTS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
