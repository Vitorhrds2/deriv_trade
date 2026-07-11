"""
D73 — Lookback Contract Fair Value Mispricing
==============================================
LOOKBACKHIGH/LOOKBACKLOW sao contratos path-dependent: payout baseado no
tick mais alto (LOOKBACKHIGH) ou mais baixo (LOOKBACKLOW) durante o periodo.
Fair value teorico de uma lookback e significativamente maior que vanilla
call/put porque captura o melhor preco em todo o caminho.

Metodologia:
  1. Descobrir contract types LOOKBACK via contracts_for
  2. Baixar 5000 ticks reais via ticks_history
  3. Para cada janela de N ticks, calcular max/min (lookback payoff)
  4. Comparar com payout oferecido pela Deriv
  5. Se EV = P(win) * payout > stake, ha edge

Fair value teorico para driftless random walk:
  LOOKBACKHIGH: P(max > entry) ~ 1 - 1/N (probabilidade do ultimo tick ser o max)
  Mas o payoff e max - entry, nao apenas win/lose. Precisa Monte Carlo.

  Na verdade, LOOKBACKHIGH provavelmente paga se o ULTIMO tick > entry
  (como CALL), mas o payout e baseado em quanto o maximo superou o entry.
  Precisamos descobrir a estrutura exata do contrato.

Fase 1: descobrir estrutura do contrato (proposal, contract_details)
Fase 2: Monte Carlo com ticks reais para calcular fair value
Fase 3: Comparar fair value com ask_price
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

SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_100"]
DURATIONS = [(5, "t"), (10, "t"), (15, "t"), (1, "m"), (5, "m"), (15, "m")]
STAKE = 1.00
N_TICKS_DOWNLOAD = 5000
N_MC_SIMS = 10000

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lookback_edge_results.json")


async def discover_lookback_contracts(client):
    """Descobrir contract types LOOKBACK disponiveis."""
    all_contracts = {}
    for sym in SYMBOLS:
        res = await client.send_request({"contracts_for": sym})
        if "error" in res:
            print(f"  {sym}: erro {res['error'].get('message', '')[:60]}")
            continue
        avail = res.get("contracts_for", {}).get("available", [])
        lookbacks = [c for c in avail if "LOOKBACK" in c.get("contract_type", "")]
        if lookbacks:
            all_contracts[sym] = lookbacks
            print(f"  {sym}: {len(lookbacks)} contratos LOOKBACK encontrados")
            for c in lookbacks:
                ct = c.get("contract_type")
                print(f"    {ct}: {json.dumps(c, indent=2, ensure_ascii=False)[:300]}")
        else:
            print(f"  {sym}: nenhum LOOKBACK encontrado")
        await asyncio.sleep(0.3)
    return all_contracts


async def get_lookback_proposal(client, contract_type, symbol, duration, duration_unit):
    """Solicitar proposal para contrato lookback."""
    payload = {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": duration_unit,
    }
    res = await client.send_request(payload)
    return res


async def download_ticks(client, symbol, count=N_TICKS_DOWNLOAD):
    """Baixar ticks reais para Monte Carlo."""
    res = await client.send_request({
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "start": 1,
        "style": "ticks",
    })
    if "error" in res:
        print(f"  Erro baixando ticks {symbol}: {res['error'].get('message', '')}")
        return []
    history = res.get("history", {})
    prices = history.get("prices", [])
    return [float(p) for p in prices]


def monte_carlo_lookback(prices, n_window, contract_type, n_sims=N_MC_SIMS):
    """
    Monte Carlo: amostrar janelas de n_window ticks dos dados reais.
    Para cada janela, simular o payoff do contrato lookback.

    LOOKBACKHIGH: paga baseado em (max_da_janela - entry) / entry
    LOOKBACKLOW: paga baseado em (entry - min_da_janela) / entry

    Mas precisamos descobrir a estrutura exata do payoff.
    Assumimos inicialmente: paga se ultimo_tick > entry (LOOKBACKHIGH),
    com payout proporcional a (max - entry) / (max - min) ou similar.
    Na pratica, vamos medir P(ultimo > entry) e comparar com payout/stake.
    """
    if len(prices) < n_window + 1:
        return None

    wins = 0
    max_excesses = []
    min_excesses = []
    final_excesses = []

    for _ in range(n_sims):
        start_idx = random.randint(0, len(prices) - n_window - 1)
        window = prices[start_idx:start_idx + n_window + 1]
        entry = window[0]
        window_ticks = window[1:]
        max_tick = max(window_ticks)
        min_tick = min(window_ticks)
        final_tick = window_ticks[-1]

        if contract_type == "LOOKBACKHIGH":
            win = final_tick > entry
            max_excess = (max_tick - entry) / entry if entry > 0 else 0
            final_excess = (final_tick - entry) / entry if entry > 0 else 0
        else:  # LOOKBACKLOW
            win = final_tick < entry
            max_excess = (entry - min_tick) / entry if entry > 0 else 0
            final_excess = (entry - final_tick) / entry if entry > 0 else 0

        if win:
            wins += 1
        max_excesses.append(max_excess)
        final_excesses.append(final_excess)

    p_win = wins / n_sims
    avg_max_excess = statistics.mean(max_excesses)
    avg_final_excess = statistics.mean(final_excesses)

    return {
        "p_win": p_win,
        "avg_max_excess": avg_max_excess,
        "avg_final_excess": avg_final_excess,
        "n_sims": n_sims,
        "n_window": n_window,
    }


def bootstrap_ci(data, n_boot=5000, confidence=0.95):
    if len(data) < 2:
        return 0, 0, 0
    means = []
    for _ in range(n_boot):
        sample = [random.choice(data) for _ in range(len(data))]
        means.append(statistics.mean(sample))
    means.sort()
    alpha = (1 - confidence) / 2
    lo = means[int(n_boot * alpha)]
    hi = means[int(n_boot * (1 - alpha))]
    return statistics.mean(data), lo, hi


async def main():
    print("=" * 90)
    print("D73 — Lookback Contract Fair Value Mispricing")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    # Fase 1: Descobrir contratos LOOKBACK
    print(f"\n{'='*60}")
    print("  FASE 1: Descoberta de contratos LOOKBACK")
    print(f"{'='*60}")
    lookback_contracts = await discover_lookback_contracts(client)

    if not lookback_contracts:
        print("\n  Nenhum contrato LOOKBACK encontrado em nenhum simbolo.")
        print("  Verificando todos os contract_types disponiveis em 1HZ10V...")
        res = await client.send_request({"contracts_for": "1HZ10V"})
        avail = res.get("contracts_for", {}).get("available", [])
        all_types = sorted(set(c.get("contract_type", "") for c in avail))
        print(f"  Tipos disponiveis: {', '.join(all_types)}")
        await client.disconnect()
        return

    # Fase 2: Solicitar proposals e analisar estrutura
    print(f"\n{'='*60}")
    print("  FASE 2: Proposals e estrutura de pricing")
    print(f"{'='*60}")
    all_results = []

    for sym, contracts in lookback_contracts.items():
        for c in contracts:
            ct = c.get("contract_type")
            for dur, unit in DURATIONS:
                prop = await get_lookback_proposal(client, ct, sym, dur, unit)
                if "error" in prop:
                    print(f"  {sym} {ct} {dur}{unit}: ERRO {prop['error'].get('message', '')[:60]}")
                    continue

                p = prop["proposal"]
                ask_price = float(p.get("ask_price", 0))
                payout = float(p.get("payout", 0))
                spot = float(p.get("spot", 0))
                barrier = p.get("barrier")
                cd = p.get("contract_details", {})

                payout_ratio = payout / STAKE if STAKE > 0 else 0
                ev_break_even = STAKE / payout if payout > 0 else 999

                print(f"\n  {sym} {ct} {dur}{unit}:")
                print(f"    ask_price=${ask_price:.4f} payout=${payout:.4f} payout_ratio={payout_ratio:.4f}")
                print(f"    spot={spot} barrier={barrier}")
                print(f"    contract_details: {json.dumps(cd, indent=2, ensure_ascii=False)[:400]}")

                # Fase 3: Monte Carlo com ticks reais
                ticks = await download_ticks(client, sym)
                if len(ticks) < 50:
                    print(f"    Ticks insuficientes ({len(ticks)}), pulando MC")
                    continue

                n_window = dur if unit == "t" else dur * 60 if unit == "s" else dur * 60
                mc = monte_carlo_lookback(ticks, n_window, ct)

                if mc:
                    p_win = mc["p_win"]
                    ev = p_win * payout - STAKE
                    ev_lo = max(0, p_win - 0.02) * payout - STAKE  # conservador

                    print(f"    MC: P(win)={p_win:.4f} EV=${ev:.4f} "
                          f"avg_max_excess={mc['avg_max_excess']:.6f} "
                          f"avg_final_excess={mc['avg_final_excess']:.6f}")

                    result = {
                        "symbol": sym,
                        "contract_type": ct,
                        "duration": dur,
                        "duration_unit": unit,
                        "ask_price": ask_price,
                        "payout": payout,
                        "payout_ratio": payout_ratio,
                        "spot": spot,
                        "barrier": barrier,
                        "mc_p_win": p_win,
                        "mc_ev": ev,
                        "mc_avg_max_excess": mc["avg_max_excess"],
                        "mc_avg_final_excess": mc["avg_final_excess"],
                        "n_ticks": len(ticks),
                        "n_mc_sims": mc["n_sims"],
                        "contract_details": cd,
                    }
                    all_results.append(result)

                await asyncio.sleep(0.5)

    # Fase 4: Veredito
    print(f"\n{'='*90}")
    print("  VEREDITO FINAL — LOOKBACK EDGE SCAN")
    print(f"{'='*90}")

    if not all_results:
        print("  Nenhum resultado valido. LOOKBACK pode nao estar disponivel.")
        await client.disconnect()
        return

    candidates = [r for r in all_results if r["mc_ev"] > 0]
    print(f"\n  {len(all_results)} celulas testadas, {len(candidates)} com EV>0")

    if candidates:
        print("\n  *** CANDIDATOS A EDGE ***")
        for r in candidates:
            print(f"    {r['symbol']} {r['contract_type']} {r['duration']}{r['duration_unit']}: "
                  f"EV=${r['mc_ev']:.4f} P(win)={r['mc_p_win']:.4f} payout_ratio={r['payout_ratio']:.4f}")
        print("\n  PROXIMO PASSO: validacao independente com mais ticks e teste ao vivo.")
    else:
        print("\n  Nenhuma celula com EV>0. LOOKBACK refutado (house margin presente).")

    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Resultados salvos em {RESULTS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
