"""
Scan de mispricing em Vanilla Options (VANILLALONGCALL/PUT) -- produto nunca testado neste
ecossistema, e o unico com payoff CONVEXO real (nao binario/fixo) testado ate agora.

Mecanica confirmada via probe_vanilla.py: stake=ask_price sempre fixo (ex.: $10); o que varia
por strike/duracao e o "payout_per_point" (display_number_of_contracts), calibrado pela Deriv
para precificar a opcao. Payout = payout_per_point * max(0, final - strike) [CALL] ou
max(0, strike - final) [PUT].

Metodo (mesma filosofia do T3): Monte Carlo DRIFTLESS via bootstrap de retornos REAIS (nao GBM
continuo assumido -- usamos a distribuicao empirica de verdade, ja demeaned p/ garantir
driftless, o que e a premissa correta pois os sinteticos sao martingales por construcao,
comprovado em T3). Compara payout medio simulado (e seu IC95% via bootstrap) contra o stake.
"""
import asyncio
import os
import random
import statistics
from dotenv import load_dotenv
from deriv_client import DerivClient
from stats_utils import bootstrap_ci

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ100V"
TICKS_PER_SECOND = 1.0  # 1HZ100V = ~1 tick/s
N_HISTORY_TICKS = 15000
DURATIONS = [(15, "m", 15 * 60), (60, "m", 60 * 60)]  # (valor, unidade, segundos)
N_SIMULATIONS = 20000
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


async def get_vanilla_quote(client, contract_type, symbol, duration_val, duration_unit, barrier):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": symbol, "duration": duration_val, "duration_unit": duration_unit,
        "barrier": barrier,
    })
    p = res.get("proposal", {})
    if "error" in res:
        return None
    return {
        "payout_per_point": float(p.get("display_number_of_contracts", 0)),
        "spot": float(p.get("spot", 0)),
        "strike": float(p.get("contract_details", {}).get("barrier", 0)),
        "ask_price": float(p.get("ask_price", STAKE)),
    }


def monte_carlo_payout(returns_pool, n_ticks, spot, strike, is_call, n_sims, rng):
    """Bootstrap de retornos reais (log-returns demeaned) para simular o preco terminal."""
    payoffs = []
    pool_n = len(returns_pool)
    for _ in range(n_sims):
        # soma de n_ticks retornos amostrados com reposicao (ja demeaned = driftless)
        total_return = sum(returns_pool[rng.randrange(pool_n)] for _ in range(n_ticks))
        terminal = spot + total_return
        if is_call:
            payoff = max(0.0, terminal - strike)
        else:
            payoff = max(0.0, strike - terminal)
        payoffs.append(payoff)
    return payoffs


async def fetch_return_pool():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"Baixando {N_HISTORY_TICKS} ticks reais de {SYMBOL} para calibrar o Monte Carlo...")
    prices = await fetch_ticks(client, SYMBOL, N_HISTORY_TICKS)
    await client.disconnect()
    raw_returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    mean_r = statistics.mean(raw_returns)
    demeaned_returns = [r - mean_r for r in raw_returns]  # forca driftless (martingale)
    print(f"{len(prices)} ticks | drift bruto medio/tick={mean_r:+.6f} (removido p/ driftless) | "
          f"desvio/tick={statistics.pstdev(raw_returns):.5f}\n")
    return demeaned_returns


async def main(demeaned_returns, all_results, done_keys):
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    rng = random.Random(7)

    for duration_val, duration_unit, duration_secs in DURATIONS:
        n_ticks = int(duration_secs * TICKS_PER_SECOND)
        print(f"\n{'='*70}\nDuracao={duration_val}{duration_unit} (~{n_ticks} ticks)\n{'='*70}")

        cf = await get_vanilla_quote(client, "VANILLALONGCALL", SYMBOL, duration_val, duration_unit, "+0.00")
        if not cf:
            continue
        barriers = None
        # pega os barrier_choices reais junto com a 1a chamada (reaproveita contracts_for)
        res_full = await client.send_request({
            "proposal": 1, "amount": STAKE, "basis": "stake",
            "contract_type": "VANILLALONGCALL", "currency": "USD",
            "underlying_symbol": SYMBOL, "duration": duration_val, "duration_unit": duration_unit,
            "barrier": "+0.00",
        })
        barrier_choices = res_full.get("proposal", {}).get("barrier_choices", ["+0.00"])

        for contract_type, is_call in [("VANILLALONGCALL", True), ("VANILLALONGPUT", False)]:
            for barrier_str in barrier_choices:
                key = (f"{duration_val}{duration_unit}", contract_type, barrier_str)
                if key in done_keys:
                    continue
                q = await get_vanilla_quote(client, contract_type, SYMBOL, duration_val, duration_unit, barrier_str)
                await asyncio.sleep(0.5)
                if not q or q["payout_per_point"] <= 0:
                    done_keys.add(key)
                    continue
                payoffs = monte_carlo_payout(demeaned_returns, n_ticks, q["spot"], q["strike"],
                                              is_call, N_SIMULATIONS, rng)
                payout_values = [p * q["payout_per_point"] for p in payoffs]
                boot_lo, mean_payout, boot_hi = bootstrap_ci(payout_values, n_boot=3000)
                ev = mean_payout / STAKE - 1
                ev_lo = boot_lo / STAKE - 1
                ev_hi = boot_hi / STAKE - 1
                flag = " <<< CANDIDATO A EDGE (EV_lo > 0)" if ev_lo > 0 else ""
                print(f"  {contract_type} barrier={barrier_str:>7} (strike={q['strike']:.2f}, spot={q['spot']:.2f}, "
                      f"payout/pt={q['payout_per_point']:.4f}): payout_medio_MC=${mean_payout:.4f} | "
                      f"EV={ev:+.4f} (IC95%[{ev_lo:+.4f},{ev_hi:+.4f}]){flag}")
                all_results.append({
                    "duration": f"{duration_val}{duration_unit}", "type": contract_type,
                    "barrier": barrier_str, "ev": ev, "ev_lo": ev_lo, "ev_hi": ev_hi,
                })
                done_keys.add(key)

    await client.disconnect()


def print_verdict(all_results):
    print("\n" + "=" * 70)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (CALL/PUT x barreira x duracao)")
    print("=" * 70)
    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge:")
        for c in candidates:
            print(f"    {c['type']} {c['barrier']} @ {c['duration']}: EV_lo={c['ev_lo']:+.4f}")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0 em nenhuma combinacao testada.")
        evs = [r["ev"] for r in all_results]
        if evs:
            print(f"    EV medio em todas as celulas: {statistics.mean(evs):+.4f} "
                  f"(min={min(evs):+.4f}, max={max(evs):+.4f})")


if __name__ == "__main__":
    # O WS de demo da Deriv cai de forma sistematica apos ~18-20 requests na mesma conexao
    # (nao e flakiness aleatoria -- parece rate-limit por sessao). Retry com estado preservado
    # (pool de retornos + resultados ja computados) em vez de reiniciar do zero a cada queda,
    # e sem mudar o sys.exit(1) do DerivClient (usado de proposito pelos bots ao vivo p/ restart).
    demeaned_returns = None
    for attempt in range(4):
        try:
            demeaned_returns = asyncio.run(fetch_return_pool())
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry fetch {attempt+1}/4] Conexao caiu ({e}), tentando de novo...\n")

    all_results, done_keys = [], set()
    for attempt in range(20):
        try:
            asyncio.run(main(demeaned_returns, all_results, done_keys))
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry scan {attempt+1}/8] Conexao caiu ({e}), retomando de onde parou "
                  f"({len(done_keys)} celulas ja feitas)...\n")
            continue

    print_verdict(all_results)
