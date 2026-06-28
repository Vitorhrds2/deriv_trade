"""H3 passo 2 - Teste de EXECUCAO: o preco TRANSACIONAVEL da Deriv esta defasado?

A captura de feed mostrou os TICKS da Deriv ~400ms atras da Binance, mas a Deriv
so tica 1/s -> pode ser artefato de amostragem (nao arbitravel). O que decide a
explorabilidade e o preco que a Deriv da num PROPOSAL (o preco em que a ordem
seria precificada).

Metodo: stream Binance ao vivo + dispara proposals cryBTCUSD em alta frequencia,
coletando o `spot` de cada proposal com timestamp local. Mede o lead-lag de:
  (a) spot do PROPOSAL  vs Binance  <- preco transacionavel (DECISIVO)
  (b) tick da Deriv     vs Binance  <- so display (confirma o ~400ms anterior)

Veredito:
  - proposal lag ~0  e  tick lag ~400ms  -> preco tradeable e FRESCO; o lag do
    tick era so amostragem -> SEM arb.
  - proposal lag ~tick lag (~400ms)      -> preco tradeable e DEFASADO -> ARB real.

So cotacao (proposal) - nenhuma ordem e enviada.

Uso:
  python exec_lag_probe.py --seconds 180 --interval-ms 250
"""
import argparse
import asyncio
import json
import os
import sys
import time

import numpy as np
import websockets
from dotenv import load_dotenv

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    r"C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env",
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
DERIV_SYMBOL = "cryBTCUSD"

binance_ticks = []    # (local_ts, price)
deriv_ticks = []      # (local_ts, price)  - display feed
proposal_spots = []   # (local_ts, spot)   - preco transacionavel


async def capture_binance(stop):
    try:
        async with websockets.connect(BINANCE_WS, ping_interval=20) as ws:
            while not stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(msg)
                if "p" in d:
                    binance_ticks.append((time.time(), float(d["p"])))
    except Exception as e:
        print(f"  ! binance ws: {e}")


def on_deriv_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        deriv_ticks.append((time.time(), float(t["quote"])))


async def poll_proposals(client, stop, interval_ms, mult):
    ok = err = 0
    payload = {
        "proposal": 1, "amount": 10.0, "basis": "stake", "contract_type": "MULTUP",
        "currency": "USD", "underlying_symbol": DERIV_SYMBOL, "multiplier": mult,
    }
    while not stop.is_set():
        try:
            res = await client.send_request(dict(payload))
            if "error" in res:
                err += 1
                await asyncio.sleep(1.0)
            else:
                spot = res.get("proposal", {}).get("spot")
                if spot:
                    proposal_spots.append((time.time(), float(spot)))
                    ok += 1
        except Exception:
            err += 1
        await asyncio.sleep(interval_ms / 1000.0)
    print(f"  proposals: {ok} ok / {err} erros")


def lead_lag(ref_t, ref_p, test_t, test_p, grid_ms, max_lag_ms, label):
    """corr(ref_ret[t], test_ret[t+lag]); lag>0 = 'test' atrasa o 'ref' (Binance)."""
    if len(ref_t) < 30 or len(test_t) < 10:
        print(f"  [{label}] dados insuficientes (ref={len(ref_t)}, test={len(test_t)})")
        return None
    ref_t, ref_p = np.array(ref_t), np.array(ref_p)
    test_t, test_p = np.array(test_t), np.array(test_p)
    t0, t1 = max(ref_t[0], test_t[0]), min(ref_t[-1], test_t[-1])
    if t1 - t0 < 10:
        print(f"  [{label}] janela curta")
        return None
    step = grid_ms / 1000.0
    grid = np.arange(t0, t1, step)
    rg = ref_p[np.clip(np.searchsorted(ref_t, grid, side="right") - 1, 0, len(ref_p) - 1)]
    tg = test_p[np.clip(np.searchsorted(test_t, grid, side="right") - 1, 0, len(test_p) - 1)]
    rr, tr = np.diff(np.log(rg)), np.diff(np.log(tg))
    maxlag = int(max_lag_ms / grid_ms)
    prof = []
    for lag in range(-maxlag, maxlag + 1):
        if lag >= 0:
            a, b = (rr[:len(rr) - lag] if lag else rr), tr[lag:]
        else:
            a, b = rr[-lag:], tr[:len(tr) + lag]
        n = min(len(a), len(b))
        if n < 30:
            continue
        a, b = a[:n], b[:n]
        c = 0.0 if a.std() == 0 or b.std() == 0 else float(np.corrcoef(a, b)[0, 1])
        prof.append((lag * grid_ms, c))
    if not prof:
        print(f"  [{label}] sem sobreposicao")
        return None
    best_lag, best_c = max(prof, key=lambda x: x[1])
    zero_c = next((c for l, c in prof if l == 0), 0.0)
    print(f"  [{label}] lag0 corr={zero_c:.3f} | MAX corr={best_c:.3f} em lag {best_lag:+.0f}ms")
    return best_lag, best_c


async def main():
    ap = argparse.ArgumentParser(description="Teste de execucao (proposal lag) Deriv x Binance")
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--interval-ms", type=int, default=250)
    ap.add_argument("--grid-ms", type=int, default=200)
    ap.add_argument("--max-lag-ms", type=int, default=2000)
    ap.add_argument("--mult", type=int, default=100)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados (.env).")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    await client.subscribe_ticks(DERIV_SYMBOL, on_deriv_tick)
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(capture_binance(stop)),
        asyncio.create_task(poll_proposals(client, stop, args.interval_ms, args.mult)),
    ]
    print(f"Capturando {args.seconds}s: Binance + proposals Deriv (~{1000/args.interval_ms:.1f}/s)...")
    try:
        await asyncio.sleep(args.seconds)
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await client.disconnect()
        except Exception:
            pass

    print("\n" + "=" * 84)
    print(f"Binance: {len(binance_ticks)} | Deriv ticks: {len(deriv_ticks)} | proposals: {len(proposal_spots)}")
    print("=" * 84)
    prop = lead_lag([x[0] for x in binance_ticks], [x[1] for x in binance_ticks],
                    [x[0] for x in proposal_spots], [x[1] for x in proposal_spots],
                    args.grid_ms, args.max_lag_ms, "PROPOSAL spot vs Binance (DECISIVO)")
    tick = lead_lag([x[0] for x in binance_ticks], [x[1] for x in binance_ticks],
                    [x[0] for x in deriv_ticks], [x[1] for x in deriv_ticks],
                    args.grid_ms, args.max_lag_ms, "TICK Deriv vs Binance (display)")

    print("\n" + "-" * 84)
    if prop and prop[1] > 0.15:
        plag = prop[0]
        if plag <= args.grid_ms:
            print(f">>> SEM ARB: preco TRANSACIONAVEL e FRESCO (proposal lag {plag:+.0f}ms ~ 0). "
                  "O ~400ms do tick era so amostragem do display. H3 morre.")
        else:
            print(f">>> ARB POSSIVEL: preco TRANSACIONAVEL atrasa ~{plag:.0f}ms (corr {prop[1]:.2f}). "
                  "Passo 3: teste de ordem demo cronometrada para confirmar o fill no preco defasado.")
    else:
        print(">>> INCONCLUSIVO: correlacao do proposal fraca (mercado calmo ou poucos proposals). "
              "Rodar mais tempo / horario volatil.")
    print("-" * 84)


if __name__ == "__main__":
    asyncio.run(main())
