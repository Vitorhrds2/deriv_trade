"""
Scan de mispricing em Turbos (TURBOSLONG/TURBOSSHORT) -- produto nunca testado neste
ecossistema. Mecanica confirmada via probe_turbos.py (longcode real): "You will receive a
payout at expiry if the spot price never breaches the barrier. The payout is equal to the
payout per point multiplied by the distance between the final price and the barrier."

Ou seja: e um barreira/knockout -- se o preco TOCAR a barreira a qualquer momento do contrato,
paga zero (perde o stake). Se sobreviver ate o expiry, payout = payout_per_point * distancia
entre preco final e a barreira. TURBOSLONG usa barreira NEGATIVA (abaixo do spot, knockout se
cair demais); TURBOSSHORT usa barreira POSITIVA (acima do spot, knockout se subir demais).
Confirmado tambem que duracoes curtas (5m) SAO aceitas, apesar de contracts_for sugerir
min_contract_duration=1d -- torna o teste tratavel em escala de ticks (nao precisa de paths de
dezenas de milhares de ticks).

Metodo: Monte Carlo driftless via bootstrap de retornos reais, vetorizado com numpy. Para cada
simulacao, gera o path completo (cumsum), verifica se algum ponto tocou a barreira (knockout)
e, se sobreviveu, calcula o payout final. Bootstrap CI na media do payout simulado.
"""
import asyncio
import os
import statistics
import sys

import numpy as np
from dotenv import load_dotenv
from deriv_client import DerivClient
from stats_utils import bootstrap_ci

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ100V"
TICKS_PER_SECOND = 1.0
N_HISTORY_TICKS = 15000
DURATIONS = [(15, "m", 15 * 60), (60, "m", 60 * 60)]
N_SIMULATIONS = 10_000
STAKE = 25.0  # min_stake observado ~$0.40, mas $25 evita erro de "stake minimo" visto no probe


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


async def fetch_return_pool():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"Baixando {N_HISTORY_TICKS} ticks reais de {SYMBOL} para calibrar o Monte Carlo...")
    prices = await fetch_ticks(client, SYMBOL, N_HISTORY_TICKS)
    await client.disconnect()
    raw_returns = np.diff(np.array(prices, dtype=np.float64))
    demeaned = raw_returns - raw_returns.mean()
    print(f"{len(prices)} ticks | drift bruto medio/tick={raw_returns.mean():+.6f} (removido p/ driftless) | "
          f"desvio/tick={raw_returns.std():.5f}\n")
    return demeaned


def monte_carlo_turbo(returns_pool, n_ticks, barrier_rel, payout_per_point, is_long, n_sims, seed=7):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(returns_pool), size=(n_sims, n_ticks))
    paths = np.cumsum(returns_pool[idx], axis=1)  # relativo ao spot (0 = entry)
    final = paths[:, -1]
    if is_long:
        survived = np.min(paths, axis=1) > barrier_rel
        payoff = np.where(survived, payout_per_point * (final - barrier_rel), 0.0)
    else:
        survived = np.max(paths, axis=1) < barrier_rel
        payoff = np.where(survived, payout_per_point * (barrier_rel - final), 0.0)
    return payoff, float(np.mean(survived))


async def get_quote(client, contract_type, duration_val, duration_unit, barrier):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": contract_type,
        "currency": "USD", "underlying_symbol": SYMBOL, "duration": duration_val,
        "duration_unit": duration_unit, "barrier": barrier,
    })
    if "error" in res:
        # barreira ficou obsoleta (spot mexeu) -- API devolve a lista atual em error.details
        # (so quando o subcode e InvalidBarrierPredefined; um placeholder longe demais ou perto
        # demais do spot pode disparar validacao de stake min/max em vez da lista de barreiras)
        choices = res.get("error", {}).get("details", {}).get("barrier_choices", [])
        return None, choices
    p = res.get("proposal", {})
    return {
        "payout_per_point": float(p.get("display_number_of_contracts", 0)),
        "barrier_choices": p.get("barrier_choices", [barrier]),
    }, None


async def get_quote_by_index(client, contract_type, duration_val, duration_unit, idx, sign, tries=5):
    """Pede a barreira no indice idx do ranking atual de barrier_choices, com retry pois a
    lista inteira dá 'drift' a cada segundo (spot se move). Usa um placeholder deliberadamente
    IMPOSSIVEL (nunca sera um barrier_choice valido) para SEMPRE forcar a API a devolver a
    lista atual completa no erro -- se o placeholder fosse um valor real (ex.: a propria tier
    idx=0), a chamada poderia "suceder" sem querer para qualquer idx quando o grid nao tiver
    dado drift ainda, casando o payout_per_point do tier ERRADO com o barrier_rel do tier CERTO."""
    barrier = f"{sign}50.00"  # valor moderado: invalido (nao bate exato c/ nenhum tier) mas nao
    # extremo o bastante p/ disparar validacao de stake min/max em vez da lista de barreiras
    for _ in range(tries):
        q, fresh_choices = await get_quote(client, contract_type, duration_val, duration_unit, barrier)
        if q is not None:
            # so aceita se o barrier devolvido bate com o indice pedido (evita reuso indevido)
            if q["barrier_choices"][idx if idx < len(q["barrier_choices"]) else -1] == barrier:
                return q
            return None
        if not fresh_choices or idx >= len(fresh_choices):
            return None
        barrier = fresh_choices[idx]
    return None


async def main(returns_pool, all_results, done_keys):
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    print(f"{'duracao':>8} {'contrato':13} {'barreira':>10} {'P(sobrevive)':>13} "
          f"{'payout_medio':>13} {'EV':>10} {'EV_lo':>10}")
    for duration_val, duration_unit, duration_secs in DURATIONS:
        n_ticks = int(duration_secs * TICKS_PER_SECOND)
        for contract_type, is_long, sign in [
            ("TURBOSSHORT", False, "+"), ("TURBOSLONG", True, "-"),
        ]:
            for idx in range(10):  # 10 tiers de distancia (barrier_choices tem 10 entradas)
                key = (f"{duration_val}{duration_unit}", contract_type, idx)
                if key in done_keys:
                    continue
                q = await get_quote_by_index(client, contract_type, duration_val, duration_unit,
                                              idx, sign)
                await asyncio.sleep(0.4)
                if not q or q["payout_per_point"] <= 0:
                    done_keys.add(key)
                    continue
                barrier_str = q["barrier_choices"][idx]
                barrier_rel = float(barrier_str)
                payoff, p_survive = monte_carlo_turbo(returns_pool, n_ticks, barrier_rel,
                                                        q["payout_per_point"], is_long, N_SIMULATIONS)
                boot_lo, mean_payout, boot_hi = bootstrap_ci(payoff.tolist(), n_boot=2000)
                ev = mean_payout / STAKE - 1
                ev_lo = boot_lo / STAKE - 1
                ev_hi = boot_hi / STAKE - 1
                flag = " <<< CANDIDATO A EDGE (EV_lo > 0)" if ev_lo > 0 else ""
                label = f"{duration_val}{duration_unit}"
                print(f"{label:>8} {contract_type:13} {barrier_str:>10} {p_survive*100:>12.2f}% "
                      f"{mean_payout:>13.4f} {ev:>+10.4f} {ev_lo:>+10.4f}{flag}")
                all_results.append({"duration": label, "contract_type": contract_type,
                                     "barrier": barrier_str, "ev": ev, "ev_lo": ev_lo, "ev_hi": ev_hi})
                done_keys.add(key)

    await client.disconnect()


def print_verdict(all_results):
    print("\n" + "=" * 70)
    print(f"VEREDITO FINAL — {len(all_results)} celulas testadas (TURBOSLONG/SHORT x barreira x duracao)")
    print("=" * 70)
    candidates = [r for r in all_results if r["ev_lo"] > 0]
    if candidates:
        print(f">>> {len(candidates)} candidato(s) a edge:")
        for c in candidates:
            print(f"    {c['contract_type']} {c['barrier']} @ {c['duration']}: EV_lo={c['ev_lo']:+.4f}")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0 em nenhuma combinacao testada.")
        evs = [r["ev"] for r in all_results]
        if evs:
            print(f"    EV medio: {statistics.mean(evs):+.4f} (min={min(evs):+.4f}, max={max(evs):+.4f})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    returns_pool = None
    for attempt in range(4):
        try:
            returns_pool = asyncio.run(fetch_return_pool())
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry fetch {attempt+1}/4] Conexao caiu ({e}), tentando de novo...\n")

    all_results, done_keys = [], set()
    for attempt in range(20):
        try:
            asyncio.run(main(returns_pool, all_results, done_keys))
            break
        except (SystemExit, ConnectionError, Exception) as e:
            print(f"\n[retry scan {attempt+1}/20] Conexao caiu ({e}), retomando de onde parou "
                  f"({len(done_keys)} celulas ja feitas)...\n")
            continue

    print_verdict(all_results)
