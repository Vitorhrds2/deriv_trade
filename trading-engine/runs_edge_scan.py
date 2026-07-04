"""
Scan de mispricing em Only Ups/Only Downs (RUNHIGH/RUNLOW) -- produto nunca testado neste
ecossistema. Paga se os proximos N ticks (N=2..5, unico range permitido) subirem (RUNHIGH) ou
descerem (RUNLOW) sucessivamente em relacao ao tick anterior.

A proposal real inclui um campo "barrier" (ex.: "+0.17") cujo papel exato na condicao de vitoria
nao e documentado publicamente. Em vez de assumir uma formula (0.5^N), medimos a probabilidade
EMPIRICA direto na sequencia real de ticks (replay, sem bootstrap -- preserva qualquer dependencia
serial real que exista) usando o criterio literal do longcode ("tick seguinte estritamente maior/
menor que o anterior"). Se houver um limiar minimo de movimento nao capturado aqui, esta medicao
e uma estimativa levemente OTIMISTA da prob. real (o que so reforca a conclusao se mesmo assim
o EV vier negativo).

Metodo: particiona os 15000 ticks reais em janelas NAO sobrepostas de tamanho N+1 (amostras
independentes, evita o problema de autocorrelacao de janelas deslizantes) e conta quantas sao
monotonas crescentes/decrescentes. Wilson CI na proporcao. Compara contra o payout real cotado.
"""
import asyncio
import os
import statistics
import sys

from dotenv import load_dotenv
from deriv_client import DerivClient
from stats_utils import wilson_ci

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ100V"
N_HISTORY_TICKS = 15000
DURATIONS = [2, 3, 4, 5]  # min_contract_duration=2t, max=5t
STAKE = 10.0


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


def empirical_run_prob(prices, n):
    """Fracao de janelas NAO sobrepostas de tamanho n+1 que sao estritamente monotonas."""
    window = n + 1
    n_windows = len(prices) // window
    ups = downs = 0
    for w in range(n_windows):
        seg = prices[w * window:(w + 1) * window]
        is_up = all(seg[i] > seg[i - 1] for i in range(1, window))
        is_down = all(seg[i] < seg[i - 1] for i in range(1, window))
        ups += is_up
        downs += is_down
    return ups, downs, n_windows


async def get_payout(client, contract_type, duration):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": contract_type,
        "currency": "USD", "underlying_symbol": SYMBOL, "duration": duration,
        "duration_unit": "t",
    })
    if "error" in res:
        return None
    return float(res.get("proposal", {}).get("payout", 0))


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"Baixando {N_HISTORY_TICKS} ticks reais de {SYMBOL}...")
    prices = await fetch_ticks(client, SYMBOL, N_HISTORY_TICKS)
    print(f"{len(prices)} ticks baixados.\n")

    all_results = []
    print(f"{'N':>3} {'contrato':10} {'N_amostra':>10} {'P_emp':>8} {'P_lo(IC95%)':>12} "
          f"{'payout':>9} {'EV':>10} {'EV_lo':>10}")
    for n in DURATIONS:
        ups, downs, n_windows = empirical_run_prob(prices, n)
        for contract_type, wins in [("RUNHIGH", ups), ("RUNLOW", downs)]:
            payout = await get_payout(client, contract_type, n)
            await asyncio.sleep(0.4)
            if not payout:
                continue
            p_hat = wins / n_windows
            p_lo, p_hi = wilson_ci(wins, n_windows)
            ev = p_hat * payout - STAKE
            ev_lo = p_lo * payout - STAKE
            flag = " <<< CANDIDATO A EDGE (EV_lo > 0)" if ev_lo > 0 else ""
            print(f"{n:>3} {contract_type:10} {n_windows:>10} {p_hat*100:>7.3f}% {p_lo*100:>11.3f}% "
                  f"{payout:>9.2f} {ev:>+10.4f} {ev_lo:>+10.4f}{flag}")
            all_results.append({"n": n, "contract_type": contract_type, "payout": payout,
                                 "p_hat": p_hat, "ev": ev, "ev_lo": ev_lo})

    await client.disconnect()
    return all_results


def print_verdict(all_results):
    print("\n" + "=" * 70)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (RUNHIGH/RUNLOW x N)")
    print("=" * 70)
    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge:")
        for c in candidates:
            print(f"    {c['contract_type']} N={c['n']}: EV_lo={c['ev_lo']:+.4f} (payout=${c['payout']:.2f})")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0 em nenhum N/contrato testado.")
        evs = [r["ev"] for r in all_results]
        if evs:
            print(f"    EV medio: {statistics.mean(evs):+.4f} (min={min(evs):+.4f}, max={max(evs):+.4f})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    all_results = []
    for attempt in range(10):
        try:
            all_results = asyncio.run(main())
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry {attempt+1}/10] Conexao caiu ({e}), tentando de novo do zero...\n")
            continue

    print_verdict(all_results)
