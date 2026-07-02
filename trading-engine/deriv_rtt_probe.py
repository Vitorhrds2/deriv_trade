"""H3 - sonda de latencia do leg de ORDEM na Deriv (round-trip real).

Mede o RTT de requests a Deriv (atras de Cloudflare) a partir desta maquina.
Como a borda Cloudflare fica proxima tanto daqui quanto de Toquio, o RTT do
'proposal' aqui e um bom PROXY para o leg de ordem a partir de uma VM em Toquio.

  - ping/time : round-trip ~puro (rede + borda CF -> origem -> borda).
  - proposal  : rede + computacao de preco no servidor (o que importa pra arb).

Sem ordens. Apenas leitura. Decide se uma VM em Toquio poderia caber dentro
de uma eventual janela 'stale' da Deriv (sinal Binance de Toquio ~1ms + este RTT).
"""
import asyncio
import os
import statistics
import sys
import time

from dotenv import load_dotenv

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    r"C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env",
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
DERIV_SYMBOL = "cryBTCUSD"
N = 25


def stats(xs):
    if not xs:
        return "sem dados"
    xs = sorted(xs)
    p95 = xs[min(len(xs) - 1, int(0.95 * len(xs)))]
    return f"min {min(xs):6.1f} | mediana {statistics.median(xs):6.1f} | p95 {p95:6.1f} | n={len(xs)}"


async def timed(client, payload, n=N, gap=0.15):
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            res = await client.send_request(payload)
            dt = (time.perf_counter() - t0) * 1000.0
            if "error" not in res:
                out.append(dt)
        except Exception:
            pass
        await asyncio.sleep(gap)
    return out


async def main():
    if not API_TOKEN or not APP_ID:
        print("ERRO: token/app_id ausentes (.env)")
        return
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    print("=" * 72)
    print(f"Latencia do leg de ORDEM Deriv (atras de Cloudflare) - {N}x cada (ms)")
    print("=" * 72)

    ping = await timed(client, {"ping": 1})
    print(f"  ping     : {stats(ping)}")
    tm = await timed(client, {"time": 1})
    print(f"  time     : {stats(tm)}")
    prop_payload = {
        "proposal": 1, "amount": 1, "basis": "stake", "contract_type": "MULTUP",
        "currency": "USD", "underlying_symbol": DERIV_SYMBOL, "multiplier": 100,
    }
    prop = await timed(client, prop_payload)
    print(f"  proposal : {stats(prop)}")
    print("=" * 72)
    if ping and prop:
        net = min(ping)
        srv = max(min(prop) - net, 0.0)
        print(f"  rede+CF (min ping) ~{net:.1f} ms | compute Deriv (proposal-ping) ~{srv:.1f} ms")
        print(f"  => leg de ordem ~{min(prop):.0f}-{statistics.median(prop):.0f} ms (proxy p/ Toquio)")
        print(f"  Reacao Toquio estimada ~ sinal 1ms + {min(prop):.0f} ms = ~{min(prop)+1:.0f} ms.")
        print("  Arb so existe se a janela 'stale' da Deriv for MAIOR que isso.")
    print("=" * 72)
    try:
        await client.disconnect()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
