"""H3 - Sonda de latencia cross-venue: Deriv cryBTCUSD vs Binance BTCUSDT.

Pergunta decisiva: o feed da Deriv ATRASA a Binance? Se sim, da pra operar na
Deriv um movimento que JA aconteceu na Binance (arbitragem de latencia - edge
estrutural grande, nao previsao de mercado).

Metodo: captura os dois streams ao vivo com timestamp LOCAL (o que importa e
qual feed EU recebo primeiro), reamostra num grid fino, e mede a correlacao
cruzada de retornos em varios lags. O lag de correlacao maxima = quanto a Deriv
atrasa a Binance.

Caveat: isto mede o lag do FEED. Se houver lag, o passo 2 (separado) e testar se
da pra EXECUTAR uma ordem na Deriv ao preco defasado (ordem demo ao vivo).

So leitura de streams - nenhuma ordem e enviada.

Uso:
  python latency_probe.py --seconds 60
  python latency_probe.py --seconds 900 --grid-ms 100
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

# .env mora no repo principal (gitignored, nao copiado pro worktree)
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

binance_ticks = []   # (local_ts, price)
deriv_ticks = []     # (local_ts, price)


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


def analyze(grid_ms, max_lag_ms):
    if len(binance_ticks) < 50 or len(deriv_ticks) < 10:
        print(f"Dados insuficientes (binance={len(binance_ticks)}, deriv={len(deriv_ticks)}).")
        return
    bt = np.array([x[0] for x in binance_ticks]); bp = np.array([x[1] for x in binance_ticks])
    dt = np.array([x[0] for x in deriv_ticks]); dp = np.array([x[1] for x in deriv_ticks])
    print("\n" + "=" * 80)
    print(f"Binance: {len(bt)} ticks | {len(bt)/(bt[-1]-bt[0]):.1f}/s | preco medio {bp.mean():.2f}")
    print(f"Deriv:   {len(dt)} ticks | {len(dt)/(dt[-1]-dt[0]):.2f}/s | preco medio {dp.mean():.2f}")
    print("=" * 80)

    t0, t1 = max(bt[0], dt[0]), min(bt[-1], dt[-1])
    if t1 - t0 < 10:
        print("Janela sobreposta curta demais."); return
    step = grid_ms / 1000.0
    grid = np.arange(t0, t1, step)
    bg = bp[np.clip(np.searchsorted(bt, grid, side="right") - 1, 0, len(bp) - 1)]
    dg = dp[np.clip(np.searchsorted(dt, grid, side="right") - 1, 0, len(dp) - 1)]
    br = np.diff(np.log(bg)); dr = np.diff(np.log(dg))

    maxlag = int(max_lag_ms / grid_ms)
    profile = []
    for lag in range(-maxlag, maxlag + 1):
        if lag >= 0:
            a, b = br[:len(br) - lag] if lag else br, dr[lag:]
        else:
            a, b = br[-lag:], dr[:len(dr) + lag]
        n = min(len(a), len(b))
        if n < 30:
            continue
        a, b = a[:n], b[:n]
        c = 0.0 if a.std() == 0 or b.std() == 0 else float(np.corrcoef(a, b)[0, 1])
        profile.append((lag * grid_ms, c))

    if not profile:
        print("Sem sobreposicao suficiente para correlacao."); return
    best_lag, best_c = max(profile, key=lambda x: x[1])
    zero_c = next((c for l, c in profile if l == 0), 0.0)

    print(f"\n  {'LAG(ms)':>8} {'CORR':>7}")
    print("  " + "-" * 18)
    for l, c in profile:
        mark = "  <== max" if (l, c) == (best_lag, best_c) else (" (lag0)" if l == 0 else "")
        if abs(l) <= 600 or (l, c) == (best_lag, best_c):
            print(f"  {l:>8.0f} {c:>7.3f}{mark}")
    print("  " + "-" * 18)
    print(f"\nCorrelacao em lag 0: {zero_c:.3f} | maxima: {best_c:.3f} em lag {best_lag:+.0f}ms")
    print("(lag>0 = Deriv reflete o movimento DEPOIS da Binance, ou seja, ATRASA)\n")

    if best_lag > grid_ms and best_c > 0.15:
        print(f">>> SINAL: Deriv ATRASA a Binance ~{best_lag:.0f}ms (corr {best_c:.2f}). "
              "Passo 2: testar execucao ao vivo (ordem demo no preco defasado).")
    elif best_c <= 0.1:
        print(">>> Correlacao fraca: pouca co-movimentacao na janela (mercado calmo?). "
              "Rodar mais tempo / em horario volatil.")
    else:
        print(">>> SEM atraso exploravel: feeds praticamente sincronizados (lag ~0). "
              "Arb de latencia improvavel nesta rota.")


async def main():
    ap = argparse.ArgumentParser(description="Sonda de latencia Deriv x Binance")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--grid-ms", type=int, default=100)
    ap.add_argument("--max-lag-ms", type=int, default=2000)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados (.env).")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    await client.subscribe_ticks(DERIV_SYMBOL, on_deriv_tick)
    stop = asyncio.Event()
    btask = asyncio.create_task(capture_binance(stop))
    print(f"Capturando {args.seconds}s ao vivo (Binance BTCUSDT + Deriv {DERIV_SYMBOL})...")
    try:
        await asyncio.sleep(args.seconds)
    finally:
        stop.set()
        await asyncio.gather(btask, return_exceptions=True)
        try:
            await client.disconnect()
        except Exception:
            pass
    analyze(args.grid_ms, args.max_lag_ms)


if __name__ == "__main__":
    asyncio.run(main())
