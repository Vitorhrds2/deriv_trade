"""
Hipotese nova do Mega Brain 2.0: SPIKE_TIMING em Jump Indices (JD10/25/50/75/100).

Mecanica (confirmada por doc publica da Deriv): cada Jump Index "pula" em media a cada
~20 minutos, direcao 50/50, salto ~30x o movimento normal de vela. A pergunta testavel:
o processo de saltos e realmente MEMORYLESS (geometrico/exponencial, como um dado sendo
jogado a cada tick) ou existe uma estrutura de "temporizador" (hazard rate crescente com
o tempo desde o ultimo salto)? Se for temporizador, e uma vantagem estrutural real: da
pra saber que um salto esta "atrasado" e evitar (ou explorar) essa janela -- diferente de
tudo que ja foi testado neste ecossistema (que assume, corretamente, memorylessness nos
indices de volatilidade puros).

Tambem testa o viés de direção (a doc diz 50/50 "designed", mas vale confirmar empiricamente).
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

SYMBOLS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["JD10", "JD25", "JD50", "JD75", "JD100"]
N_TICKS = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
SPIKE_MULT = 10.0  # salto = retorno > SPIKE_MULT x a mediana do |retorno| normal


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
        await asyncio.sleep(0.15)
    return all_prices, all_times


def detect_jumps(prices, times, spike_mult):
    returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    abs_returns = [abs(r) for r in returns]
    median_move = statistics.median(abs_returns)
    jumps = []  # (tick_index, time, direction, magnitude)
    for i, r in enumerate(returns):
        if abs(r) > spike_mult * median_move:
            jumps.append({"tick_idx": i + 1, "time": times[i + 1], "dir": 1 if r > 0 else -1, "mag": abs(r)})
    return jumps, median_move


def analyze_symbol(symbol, prices, times):
    jumps, median_move = detect_jumps(prices, times, SPIKE_MULT)
    n_jumps = len(jumps)
    print(f"\n{'='*65}\n{symbol} — {len(prices)} ticks, mediana |retorno normal|={median_move:.5f}")
    print(f"Saltos detectados (>{SPIKE_MULT}x mediana): {n_jumps}")
    if n_jumps < 8:
        print("  Amostra insuficiente de saltos para analise de timing/direcao. Pulando.")
        return None

    # 1) Vies de direcao
    ups = sum(1 for j in jumps if j["dir"] > 0)
    wr_lo, wr_hi = wilson_ci(ups, n_jumps)
    print(f"  Direcao: {ups}/{n_jumps} UP ({ups/n_jumps*100:.1f}%, IC95%[{wr_lo*100:.1f}%,{wr_hi*100:.1f}%]) "
          f"| esperado 50% {'DENTRO' if wr_lo <= 0.5 <= wr_hi else '<<< FORA do IC (vies de direcao real)'}")

    # 2) Gaps entre saltos (em ticks e em segundos)
    gaps_ticks = [jumps[i]["tick_idx"] - jumps[i - 1]["tick_idx"] for i in range(1, n_jumps)]
    gaps_secs = [jumps[i]["time"] - jumps[i - 1]["time"] for i in range(1, n_jumps)]
    mean_gap_s = statistics.mean(gaps_secs)
    std_gap_s = statistics.pstdev(gaps_secs)
    cv = std_gap_s / mean_gap_s if mean_gap_s else 0
    print(f"  Gap medio entre saltos: {mean_gap_s:.0f}s ({mean_gap_s/60:.1f}min) | desvio={std_gap_s:.0f}s | "
          f"CV(desvio/media)={cv:.3f}")
    print(f"  -> Se memoryless (exponencial/geometrico puro), CV deveria ser ~1.0.")
    if cv < 0.6:
        print(f"  <<< CV BAIXO: timing mais REGULAR que aleatorio -- indicio de 'temporizador', nao dado puro.")
    elif cv > 1.4:
        print(f"  <<< CV ALTO: saltos em rajadas/clusters, mais irregular que memoryless.")
    else:
        print(f"  CV compativel com processo memoryless (Poisson/geometrico).")

    # 3) Hazard rate: P(salto no proximo tick | N ticks desde o ultimo salto) -- muda com N?
    #    Se memoryless, deve ser ~constante. Se cresce com N, e temporizador (edge real).
    buckets = {}  # bucket de "ticks desde ultimo salto" -> [sobreviveu_mais_1_tick?, ...]
    last_jump_tick = 0
    jump_ticks_set = set(j["tick_idx"] for j in jumps)
    BUCKET_SIZE = 100
    for t in range(1, len(prices) - 1):
        since_last = t - last_jump_tick
        bucket = min(since_last // BUCKET_SIZE, 9)  # cap em 9 (>=900 ticks desde o ultimo)
        happened = 1 if (t + 1) in jump_ticks_set else 0
        buckets.setdefault(bucket, [0, 0])
        buckets[bucket][0] += happened
        buckets[bucket][1] += 1
        if t in jump_ticks_set:
            last_jump_tick = t

    print(f"  Hazard rate (P[salto no proximo tick] por faixa de 'ticks desde o ultimo salto'):")
    hazards = []
    for b in sorted(buckets.keys()):
        events, total = buckets[b]
        if total < 30:
            continue
        rate = events / total
        lo, hi = wilson_ci(events, total)
        hazards.append((b, rate))
        print(f"    [{b*BUCKET_SIZE:>4}-{(b+1)*BUCKET_SIZE:>4} ticks desde ult. salto] N={total:>5} | "
              f"P(salto)={rate*100:.3f}% (IC95%[{lo*100:.3f}%,{hi*100:.3f}%])")

    return {
        "symbol": symbol, "n_jumps": n_jumps, "ups": ups, "wr_ci": (wr_lo, wr_hi),
        "mean_gap_s": mean_gap_s, "cv": cv, "hazards": hazards,
    }


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    results = []
    for symbol in SYMBOLS:
        print(f"\nBaixando {N_TICKS} ticks de {symbol}...")
        prices, times = await fetch_ticks(client, symbol, N_TICKS)
        print(f"  {len(prices)} ticks obtidos, de {times[0] if times else '?'} a {times[-1] if times else '?'} "
              f"({(times[-1]-times[0])/3600:.1f}h)" if times else "  sem dados")
        if len(prices) < 1000:
            continue
        r = analyze_symbol(symbol, prices, times)
        if r:
            results.append(r)

    await client.disconnect()

    print("\n" + "=" * 65)
    print("RESUMO FINAL — SPIKE_TIMING em Jump Indices")
    print("=" * 65)
    for r in results:
        hazard_range = f"{min(h[1] for h in r['hazards'])*100:.3f}%-{max(h[1] for h in r['hazards'])*100:.3f}%" if r["hazards"] else "N/A"
        print(f"{r['symbol']}: N_saltos={r['n_jumps']} | dir_up={r['ups']/r['n_jumps']*100:.1f}% | "
              f"gap_medio={r['mean_gap_s']/60:.1f}min | CV={r['cv']:.2f} | faixa_hazard={hazard_range}")


if __name__ == "__main__":
    asyncio.run(main())
