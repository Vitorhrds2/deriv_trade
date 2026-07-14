"""Scan de mispricing na feature "Deal Cancellation" dos Multipliers -- nunca testada
neste ecossistema. Mecanica real (confirmada via `contracts_for`/`proposal` ao vivo):
um MULTUP/MULTDOWN comprado com `cancellation=<5m|10m|15m|30m|60m>` garante que, a
qualquer momento dentro dessa janela, o titular pode cancelar o contrato e receber o
STAKE INTEGRAL de volta (P&L=$0) -- floor MELHOR que o stop-out padrao (que so garante
P&L=-$stake). Ao expirar a janela, a garantia desaparece e o contrato volta a operar
como um multiplier comum. A Deriv cobra por isso via `proposal.cancellation.ask_price`
(fee fixo, somado ao stake no ask_price total).

Isso e uma opcao de venda (PUT) europeia embutida: strike=entry_spot, notional=
stake*multiplier, vencimento=duracao da janela. (American vs European: sem dividendos
e com taxa de juros ~0 no horizonte de minutos, o premio de exercicio antecipado e
desprezivel -- aproximar por European e razoavel, nao so um lower bound de conveniencia.)

  fair_value(MULTUP)   = E[max(0, stake*multiplier*(1 - S_T/S_0))]
  fair_value(MULTDOWN) = E[max(0, stake*multiplier*(S_T/S_0 - 1))]

S_T simulado via bootstrap em bloco de retornos tick-a-tick reais (demeaned, martingale,
mesma metodologia do higher_lower_edge_scan.py / vanilla_edge_scan.py).

Uso: python3 deal_cancellation_edge_scan.py
"""
import asyncio
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "R_100"
STAKE = 10.0
N_HISTORY_TICKS = 60000
N_SIMULATIONS = 120000
CANCELLATION_DURATIONS = ["5m", "10m", "15m", "30m", "60m"]
MULTIPLIERS = [40, 100, 200, 300, 400]
CONTRACT_TYPES = ["MULTUP", "MULTDOWN"]

DUR_TO_MIN = {"5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60}


async def fetch_ticks(client, symbol, count):
    all_prices, all_times = [], []
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
        all_times = times + all_times
        remaining -= len(prices)
        end = times[0] - 1
        await asyncio.sleep(0.12)
    return all_prices, all_times


async def get_cancellation_quote(client, contract_type, multiplier, cancellation):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": SYMBOL, "multiplier": multiplier,
        "cancellation": cancellation,
    })
    if "error" in res:
        return None, res["error"].get("message", "")
    p = res.get("proposal", {})
    canc = p.get("cancellation", {})
    return {
        "ask_price_total": float(p.get("ask_price", STAKE)),
        "cancellation_fee": float(canc.get("ask_price", 0)),
        "spot": float(p.get("spot", 0)),
    }, None


SUBBLOCK = 60  # ticks (~1min) -- preserva autocorrelacao/clustering de curto prazo


def monte_carlo_fair_value(prefix_sums, n_ticks, stake, multiplier, is_up, n_sims, rng):
    """Bootstrap em SUB-blocos concatenados (nao um unico bloco contiguo de n_ticks).
    Um bloco unico de ate 3600 ticks (60min) tirado de so 20k ticks de historico tem
    <6 comprimentos-de-bloco de "espaco" -> as amostras ficam quase todas sobrepostas
    e dominadas por 1-2 trechos de tendencia real que por acaso ocorreram na amostra,
    inflando artificialmente um lado (MULTUP vs MULTDOWN) de forma espuria -- exatamente
    o padrao de falso-positivo de N pequeno ja visto em D46/Accumulators/JD50. Para
    corrigir: cada caminho simulado e a soma de varios SUB-blocos de tamanho fixo
    (SUBBLOCK ticks), cada um reamostrado de forma independente -> uma janela de 60min
    vira 60 sorteios independentes de 1min, dando mixing estatistico adequado (CLT)
    mesmo com historico limitado. Prefix sums -> soma de cada sub-bloco em O(1)."""
    pool_n = len(prefix_sums) - 1
    payoffs = []
    max_start = pool_n - SUBBLOCK
    n_full = n_ticks // SUBBLOCK
    remainder = n_ticks - n_full * SUBBLOCK
    for _ in range(n_sims):
        delta = 0.0
        for _ in range(n_full):
            start = rng.randrange(max_start)
            delta += prefix_sums[start + SUBBLOCK] - prefix_sums[start]
        if remainder:
            max_start_r = pool_n - remainder
            start = rng.randrange(max_start_r)
            delta += prefix_sums[start + remainder] - prefix_sums[start]
        # retorno percentual aproximado (delta e em pontos de preco, nao %; para
        # sinteticos com spot ~ mesma ordem de grandeza ao longo da amostra, usamos
        # o spot medio da amostra como referencia de entry_spot para a razao %).
        pct_move = delta / REF_SPOT
        if is_up:
            payoff = min(stake, max(0.0, -pct_move) * stake * multiplier)  # protege MULTUP de queda, limitado ao stake
        else:
            payoff = min(stake, max(0.0, pct_move) * stake * multiplier)   # protege MULTDOWN de alta, limitado ao stake
        payoffs.append(payoff)
    mean = statistics.mean(payoffs)
    sem = statistics.pstdev(payoffs) / (n_sims ** 0.5)
    return mean, mean - 1.96 * sem, mean + 1.96 * sem


REF_SPOT = None


async def fetch_return_pool():
    global REF_SPOT
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"Baixando {N_HISTORY_TICKS} ticks reais de {SYMBOL}...")
    prices, times = await fetch_ticks(client, SYMBOL, N_HISTORY_TICKS)
    await client.disconnect()
    raw_returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    mean_r = statistics.mean(raw_returns)
    demeaned = [r - mean_r for r in raw_returns]
    REF_SPOT = statistics.mean(prices)
    dts = [times[i] - times[i - 1] for i in range(1, len(times)) if times[i] > times[i - 1]]
    median_dt = statistics.median(dts) if dts else 1.0
    print(f"{len(prices)} ticks | drift bruto={mean_r:+.6f} (removido) | "
          f"desvio/tick={statistics.pstdev(raw_returns):.5f} | spot_ref={REF_SPOT:.2f} | "
          f"intervalo mediano entre ticks={median_dt:.2f}s\n")
    prefix_sums = [0.0] * (len(demeaned) + 1)
    for i, r in enumerate(demeaned):
        prefix_sums[i + 1] = prefix_sums[i] + r
    return prefix_sums, median_dt


async def main(prefix_sums, median_dt):
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    rng = random.Random(7)

    all_results = []
    for multiplier in MULTIPLIERS:
        print(f"\n{'='*100}\nMultiplier={multiplier}x  stake=${STAKE}\n{'='*100}")
        for contract_type in CONTRACT_TYPES:
            is_up = contract_type == "MULTUP"
            print(f"\n  {contract_type}")
            for canc in CANCELLATION_DURATIONS:
                n_ticks = max(2, round((DUR_TO_MIN[canc] * 60) / median_dt))
                q, err = await get_cancellation_quote(client, contract_type, multiplier, canc)
                await asyncio.sleep(0.3)
                if not q:
                    print(f"    cancellation={canc:>4} | ERRO {err}")
                    continue

                fv, fv_lo, fv_hi = monte_carlo_fair_value(
                    prefix_sums, n_ticks, STAKE, multiplier, is_up, N_SIMULATIONS, rng)

                fee = q["cancellation_fee"]
                edge = fv - fee          # >0 => taxa cobrada abaixo do valor justo (client-favoravel)
                edge_lo = fv_lo - fee
                flag = " <<< CANDIDATO A EDGE (fee < fair value, IC95%)" if edge_lo > 0 else ""
                print(f"    cancellation={canc:>4} ({n_ticks:>4} ticks) | fee_cobrado=${fee:.4f} | "
                      f"fair_value_MC=${fv:.4f} (IC95%[${fv_lo:.4f},${fv_hi:.4f}]) | "
                      f"edge=${edge:+.4f} (edge_lo=${edge_lo:+.4f}){flag}")

                all_results.append({
                    "multiplier": multiplier, "contract_type": contract_type,
                    "cancellation": canc, "n_ticks": n_ticks, "fee": fee,
                    "fair_value": fv, "fv_lo": fv_lo, "fv_hi": fv_hi,
                    "edge": edge, "edge_lo": edge_lo,
                })

    await client.disconnect()
    return all_results


def print_verdict(all_results):
    print("\n" + "=" * 100)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (multiplier x contract_type x cancellation)")
    print("=" * 100)
    candidates = [r for r in all_results if r["edge_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge (fee cobrado < fair value, IC95%):")
        for c in candidates:
            print(f"    {c['contract_type']} {c['multiplier']}x cancellation={c['cancellation']}: "
                  f"fee=${c['fee']:.4f} fair=${c['fair_value']:.4f} edge_lo=${c['edge_lo']:+.4f}")
    else:
        print(">>> SEM EDGE. 0 celulas com edge_lo>0 (fee sempre >= valor justo estimado).")
        ratios = [(r["fee"] / r["fair_value"]) if r["fair_value"] > 0 else float("inf") for r in all_results]
        print(f"    Razao fee/fair_value: media={statistics.mean(ratios):.2f}x "
              f"(min={min(ratios):.2f}x, max={max(ratios):.2f}x)")
        print("\n    Detalhe por celula (ordenado por razao fee/fair, menor primeiro):")
        for r in sorted(all_results, key=lambda x: (x["fee"] / x["fair_value"]) if x["fair_value"] > 0 else 1e9):
            ratio = r["fee"] / r["fair_value"] if r["fair_value"] > 0 else float("inf")
            print(f"    {r['contract_type']:>9} {r['multiplier']:>5}x {r['cancellation']:>4}: "
                  f"fee=${r['fee']:.4f} fair=${r['fair_value']:.4f} ratio={ratio:.2f}x")


if __name__ == "__main__":
    prefix_sums, median_dt = None, 1.0
    for attempt in range(4):
        try:
            prefix_sums, median_dt = asyncio.run(fetch_return_pool())
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry fetch {attempt+1}/4] {e}\n")

    results = []
    for attempt in range(5):
        try:
            results = asyncio.run(main(prefix_sums, median_dt))
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry scan {attempt+1}/5] {e}...\n")
            continue

    print_verdict(results)
