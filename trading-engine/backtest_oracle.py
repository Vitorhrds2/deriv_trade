"""Backtest do EDGE do Oraculo Dinamico (oracle_diff_bot_6).

Replica FIELMENTE a logica do bot:
  - extract_last_digit = int(round(price*100)) % 10
  - rolling window (recalcula anomalias a cada tick)
  - anomalia: por digito c, o proximo digito OBSERVADO mais raro; vira gatilho se <=6%
  - VL (Sniper Duplo): ao ver o gatilho c, arma alvo = anomalies[c]; se o alvo repetir
    TARGET_VL vezes seguidas, dispara DIGITDIFF contra o alvo (vence se proximo != alvo)
  - apos disparar, o tick seguinte (settlement) e ignorado (is_trading), igual ao bot

Mede: win rate pos-sinal + IC95% (Wilson), P[alvo aparecer] vs 10%, controle de
barreira aleatoria, EV/break-even por payout, e um baseline SINTETICO (RNG uniforme)
que prova que o algoritmo nao extrai edge de dados memoryless.

Uso:
  python backtest_oracle.py --synthetic 500000          # so prova offline (sem rede)
  python backtest_oracle.py --symbols 1HZ10V,R_10 --chunks 15   # ticks reais (rede)
"""
import argparse
import asyncio
import math
import os
import random
import sys
from collections import deque
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")


def extract_last_digit(price):
    return int(round(float(price) * 100)) % 10


def run_oracle_replay(digits, window_size, target_vl):
    """Replay fiel do on_tick + recalculate_anomalies + maquina de estados VL.
    Retorna lista de (alvo, digito_seguinte) para cada disparo.
    Usa matriz de transicao incremental 10x10 para rodar rapido em amostras grandes.
    """
    window = deque(maxlen=window_size)
    T = [[0] * 10 for _ in range(10)]
    rowtot = [0] * 10

    def add_digit(nd):
        # adiciona o par (anterior -> nd)
        if window:
            prev = window[-1]
            T[prev][nd] += 1
            rowtot[prev] += 1
        # se cheia, o append vai expulsar window[0]; remove o par (window[0] -> window[1])
        if len(window) == window_size and window_size >= 2:
            a, b = window[0], window[1]
            T[a][b] -= 1
            rowtot[a] -= 1
        window.append(nd)

    def get_anomalies():
        # Fiel ao bot: min sobre proximos digitos OBSERVADOS (count > 0)
        anomalies = {}
        best_pct = 101.0
        best_c = best_n = None
        for c in range(10):
            tot = rowtot[c]
            if tot == 0:
                continue
            row = T[c]
            worst_d = None
            worst_cnt = None
            for d in range(10):
                cnt = row[d]
                if cnt <= 0:
                    continue
                if worst_cnt is None or cnt < worst_cnt:
                    worst_cnt = cnt
                    worst_d = d
            if worst_d is None:
                continue
            pct = (worst_cnt / tot) * 100.0
            if pct <= 6.0:
                anomalies[c] = worst_d
            if pct < best_pct:
                best_pct = pct
                best_c, best_n = c, worst_d
        if not anomalies and best_c is not None:
            anomalies[best_c] = best_n
        return anomalies

    signals = []
    armed_target = None
    vl_count = 0
    skip_until = -1
    n = len(digits)
    for i in range(n):
        d = digits[i]
        add_digit(d)
        if len(window) < window_size:
            continue
        if i <= skip_until:           # tick de settlement (is_trading) -> bot ignora
            continue
        if armed_target is not None:
            if d == armed_target:
                vl_count += 1
                if vl_count == target_vl:
                    if i + 1 < n:     # aposta no proximo tick (duracao 1 tick)
                        signals.append((armed_target, digits[i + 1]))
                    armed_target = None
                    vl_count = 0
                    skip_until = i + 1
            else:
                armed_target = None
                vl_count = 0
            continue
        anomalies = get_anomalies()
        if d in anomalies:
            armed_target = anomalies[d]
            vl_count = 0
    return signals


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (center - half, center + half)


def chi_square_uniform(digits):
    counts = [0] * 10
    for d in digits:
        counts[d] += 1
    n = len(digits)
    exp = n / 10.0
    chi = sum((c - exp) ** 2 / exp for c in counts) if exp > 0 else 0.0
    return chi, counts


def max_consec_losses(signals):
    mx = cur = 0
    for t, o in signals:
        if o == t:  # loss = proximo digito == barreira
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


def analyze(label, digits, window, vl, payouts, seed=42):
    print("\n" + "=" * 72)
    print(f"  {label}  | ticks={len(digits):,} window={window} vl={vl}")
    print("=" * 72)

    chi, counts = chi_square_uniform(digits)
    print(f"Distribuicao de digitos : {counts}")
    print(f"Chi-quadrado vs uniforme (df=9): {chi:.2f}  (critico 0.05 = 16.92)  -> "
          + ("UNIFORME (sem estrutura exploravel)" if chi < 16.92 else "NAO uniforme"))

    signals = run_oracle_replay(digits, window, vl)
    n = len(signals)
    if n == 0:
        print("Nenhum disparo gerado (amostra pequena demais).")
        return signals
    losses = sum(1 for t, o in signals if o == t)
    wins = n - losses
    wr = wins / n
    lo, hi = wilson(wins, n)
    target_hit = losses / n

    print(f"\nDisparos do Oraculo     : {n:,}")
    print(f"WIN / LOSS              : {wins:,} / {losses:,}")
    print(f"WIN RATE pos-sinal      : {wr*100:.2f}%   IC95% Wilson: [{lo*100:.2f}%, {hi*100:.2f}%]")
    print(f"P[alvo aparecer]        : {target_hit*100:.2f}%   (aleatorio = 10.00%)")
    print(f"Max perdas consecutivas : {max_consec_losses(signals)}")

    rnd = random.Random(seed)
    rwins = sum(1 for t, o in signals if o != rnd.randint(0, 9))
    print(f"Controle barreira aleat.: WR {rwins/n*100:.2f}%  (mesmos pontos, alvo sorteado)")

    print("EV por $1 e break-even (varios payouts do DIGITDIFF):")
    for p in payouts:
        ev = wr * p - (1 - wr)
        be = 1.0 / (1.0 + p)
        print(f"  payout {p*100:5.1f}%  EV/$1 = {ev:+.4f}  | break-even WR = {be*100:.2f}%  -> "
              + ("LUCRA" if wr > be else "PERDE"))
    return signals


async def fetch_ticks(symbol, chunks, delay=0.8):
    from deriv_client import DerivClient
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    prices = []
    try:
        current_end = "latest"
        for i in range(chunks):
            res = None
            for attempt in range(4):
                res = await client.send_request({
                    "ticks_history": symbol,
                    "adjust_start_time": 1,
                    "count": 5000,
                    "end": current_end,
                    "style": "ticks",
                })
                if "error" not in res:
                    break
                wait = 2 ** (attempt + 1)
                print(f"  ! {symbol}: erro {res['error'].get('code')} - retry em {wait}s")
                await asyncio.sleep(wait)
            if res is None or "error" in res:
                print(f"  ! {symbol}: desistindo apos retries (parou em {len(prices):,} ticks)")
                break
            hist = res.get("history", {})
            times = hist.get("times", [])
            pr = hist.get("prices", [])
            if not pr or not times:
                print(f"  ! {symbol}: sem mais historico (parou em {len(prices):,} ticks)")
                break
            prices = list(pr) + prices
            current_end = times[0] - 1
            if (i + 1) % 10 == 0 or i == chunks - 1:
                print(f"  {symbol}: {i+1}/{chunks} -> {len(prices):,} ticks")
            await asyncio.sleep(delay)
    finally:
        await client.disconnect()
    return prices


def gen_synthetic(n, seed=7):
    rnd = random.Random(seed)
    return [rnd.randint(0, 9) for _ in range(n)]


def combined_verdict(label, signals, payouts):
    n = len(signals)
    if n == 0:
        print(f"\n{label}: sem disparos.")
        return
    losses = sum(1 for t, o in signals if o == t)
    wins = n - losses
    wr = wins / n
    lo, hi = wilson(wins, n)
    print("\n" + "#" * 72)
    print(f"  {label}")
    print("#" * 72)
    print(f"Disparos: {n:,} | WIN {wins:,} | LOSS {losses:,}")
    print(f"WIN RATE: {wr*100:.2f}%  IC95% Wilson: [{lo*100:.2f}%, {hi*100:.2f}%]")
    print(f"P[alvo aparece]: {losses/n*100:.2f}% (aleatorio 10.00%)  | max perdas seguidas: {max_consec_losses(signals)}")
    for p in payouts:
        be = 1.0 / (1.0 + p)
        if lo > be:
            v = "LUCRA (IC todo acima do break-even)"
        elif hi < be:
            v = "PERDE (IC todo abaixo do break-even)"
        else:
            v = "INCONCLUSIVO (IC cruza o break-even)"
        print(f"  break-even @ payout {p*100:.1f}% = {be*100:.2f}%  -> {v}")


async def main():
    ap = argparse.ArgumentParser(description="Backtest do edge do Oraculo (DIGITDIFF)")
    ap.add_argument("--symbols", type=str, default="1HZ10V,R_10,1HZ25V")
    ap.add_argument("--chunks", type=int, default=15, help="blocos de 5000 ticks por simbolo")
    ap.add_argument("--window", type=int, default=1000)
    ap.add_argument("--vl", type=int, default=2)
    ap.add_argument("--synthetic", type=int, default=0, help="se >0, roda so em N digitos uniformes (sem rede)")
    ap.add_argument("--delay", type=float, default=0.8, help="intervalo entre requests (anti rate-limit)")
    args = ap.parse_args()

    payouts = [0.087, 0.093, 0.10]

    if args.synthetic > 0:
        digits = gen_synthetic(args.synthetic)
        analyze("SINTETICO (RNG uniforme)", digits, args.window, args.vl, payouts)
        print("\nLeitura: se em dados PROVADAMENTE aleatorios o WR ~= 90% e P[alvo] ~= 10%,")
        print("entao o algoritmo do Oraculo nao cria edge nenhum - ele apenas re-descobre o acaso.")
        return

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    combined = []
    for sym in symbols:
        print(f"\n>>> Baixando {sym} ({args.chunks} x 5000 ticks)...")
        prices = await fetch_ticks(sym, args.chunks, args.delay)
        if len(prices) < args.window + 100:
            print(f"  ! {sym}: ticks insuficientes ({len(prices)}). Pulando.")
            continue
        digits = [extract_last_digit(p) for p in prices]
        combined += analyze(f"REAL {sym}", digits, args.window, args.vl, payouts)

    combined_verdict("RESULTADO COMBINADO (todos os simbolos reais)", combined, payouts)

    print("\n>>> Baseline sintetico (RNG uniforme, 400k) para comparacao direta:")
    analyze("SINTETICO (RNG uniforme)", gen_synthetic(400000), args.window, args.vl, payouts)


if __name__ == "__main__":
    asyncio.run(main())
