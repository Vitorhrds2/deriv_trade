"""
Validacao independente do sinal achado em accumulator_edge_scan.py (1HZ100V, growth_rate
0.02-0.04): mede a probabilidade de sobrevivencia TICK-A-TICK diretamente do historico real
(ticks_history), em vez de confiar so no "ticks_stayed_in" (amostra retrospectiva da propria
Deriv). Se as duas fontes independentes concordarem, o sinal fica muito mais dificil de
descartar como fluke -- exatamente a logica que o T3 usou (P_emp por janela empirica x P_mc
por Monte Carlo) para separar edge real de artefato de amostra pequena.
"""
import asyncio
import os
from dotenv import load_dotenv
from deriv_client import DerivClient
from stats_utils import wilson_ci

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ100V"
GROWTH_RATES = [0.01, 0.02, 0.03, 0.04, 0.05]
N_TICKS_HISTORY = 5000
TARGET_N = [5, 8, 10, 15, 20, 30, 50]


async def fetch_barrier_pct(client, symbol, gr):
    res = await client.get_proposal("ACCU", stake=10.0, symbol=symbol, growth_rate=gr)
    cd = res.get("proposal", {}).get("contract_details", {})
    return cd.get("tick_size_barrier")  # fracao, ex: 0.000379665263


async def fetch_ticks(client, symbol, count):
    all_prices = []
    end = "latest"
    remaining = count
    while remaining > 0:
        batch = min(remaining, 5000)
        res = await client.get_ticks_history(symbol, count=batch, end=end)
        hist = res.get("history", {})
        prices = hist.get("prices", [])
        times = hist.get("times", [])
        if not prices:
            break
        all_prices = prices + all_prices
        remaining -= len(prices)
        end = times[0] - 1
        await asyncio.sleep(0.3)
    return all_prices


def empirical_single_tick_survival(prices, barrier_pct):
    """Fracao de passos tick-a-tick onde |retorno| <= barrier_pct (barreira recalculada a cada tick)."""
    survivals = 0
    total = 0
    for i in range(1, len(prices)):
        ret = abs(prices[i] - prices[i - 1]) / prices[i - 1]
        total += 1
        if ret <= barrier_pct:
            survivals += 1
    return survivals, total


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    print(f"Baixando {N_TICKS_HISTORY} ticks reais de {SYMBOL}...")
    prices = await fetch_ticks(client, SYMBOL, N_TICKS_HISTORY)
    print(f"Total de ticks obtidos: {len(prices)}\n")

    for gr in GROWTH_RATES:
        barrier_pct = await fetch_barrier_pct(client, SYMBOL, gr)
        if barrier_pct is None:
            continue
        survivals, total = empirical_single_tick_survival(prices, barrier_pct)
        p1_emp = survivals / total
        p1_fair = 1 / (1 + gr)  # probabilidade de sobrevivencia por tick exigida p/ EV=0 (sem margem)
        wr_lo, wr_hi = wilson_ci(survivals, total)

        print(f"growth_rate={gr} | barreira/tick={barrier_pct*100:.5f}%")
        print(f"  P(sobreviver 1 tick) EMPIRICO (historico real, N={total}): {p1_emp*100:.3f}% "
              f"(IC95%[{wr_lo*100:.3f}%,{wr_hi*100:.3f}%])")
        print(f"  P(sobreviver 1 tick) NECESSARIO p/ EV=0 (fair, sem margem): {p1_fair*100:.3f}%")
        edge_per_tick = p1_emp - p1_fair
        edge_lo = wr_lo - p1_fair
        flag = " <<< barreira parece GENEROSA (favoravel ao comprador)" if edge_lo > 0 else (
            "" if edge_per_tick <= 0 else " (positivo mas IC nao confirma)")
        print(f"  Diferenca (emp - fair): {edge_per_tick*100:+.4f}pp | IC_lo: {edge_lo*100:+.4f}pp{flag}")

        for n in TARGET_N:
            p_survive_n_fair = p1_fair ** n
            p_survive_n_emp = p1_emp ** n
            p_survive_n_emp_lo = wr_lo ** n
            payout_mult = (1 + gr) ** n
            ev_emp = p_survive_n_emp * payout_mult - 1
            ev_lo = p_survive_n_emp_lo * payout_mult - 1
            print(f"    N={n:>3}: P_sobrevive(fair)={p_survive_n_fair*100:5.1f}% | "
                  f"P_sobrevive(emp, extrapolado i.i.d.)={p_survive_n_emp*100:5.1f}% | "
                  f"EV=${ev_emp:+.4f} | EV_lo=${ev_lo:+.4f}")
        print()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
