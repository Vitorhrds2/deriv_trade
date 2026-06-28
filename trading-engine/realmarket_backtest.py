"""H1 - Momentum pos-choque em mercado REAL (Binance BTC aggTrades).

Hipotese: apos um choque de >= THRESHOLD em <= WINDOW_MS, o preco CONTINUA na
direcao do choque por HOLD_MS o suficiente para lucrar liquido de custos.

Esta versao corrige os furos dos scripts antigos:
  - analyze_weekly_sustained.py media o lucro a partir de prices[left] (inicio
    da janela, ANTES do choque) -> embutia o proprio choque no "lucro" (o 90%+
    era artefato). AQUI a entrada e no GATILHO (prices[right]) + latencia.
  - binance_tick_backtest.py contava abs(move) como lucro, sem checar
    continuacao. AQUI ha entrada -> hold -> saida real.

Rigor (mesma regua que matou o Oraculo da Deriv):
  - Simulacao fiel: entrada no gatilho (+latencia), hold definido, saida real.
  - Custos: comissao + spread + slippage (round-trip).
  - Controle NULO: direcao aleatoria nos mesmos gatilhos. Se momentum nao bate
    o aleatorio, nao ha edge. Tambem testa FADE (mean-reversion).
  - Wilson CI no win rate + bootstrap CI no EV/trade (tem que excluir 0).
  - Multi-dia / out-of-sample.

Dados: https://data.binance.vision (aggTrades diarios; arquivos grandes; .csv
fica em cache local e e gitignored).

Uso:
  python realmarket_backtest.py --symbol BTCUSDT --start 2026-06-19 --days 3 \
      --threshold 50 --window-ms 500 --hold-ms 2000 --latency-ms 150 \
      --multiplier 800 --stake 10 --commission-frac 0.24 --slippage-bps 1.0
"""
import argparse
import math
import os
import sys
import zipfile
import urllib.request
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BINANCE_URL = ("https://data.binance.vision/data/spot/daily/aggTrades/"
               "{sym}/{sym}-aggTrades-{date}.zip")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "binance_cache")


def download_day(symbol, date_str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    csv_path = os.path.join(CACHE_DIR, f"{symbol}-aggTrades-{date_str}.csv")
    if os.path.exists(csv_path):
        return csv_path
    zip_path = os.path.join(CACHE_DIR, f"{symbol}-aggTrades-{date_str}.zip")
    url = BINANCE_URL.format(sym=symbol, date=date_str)
    print(f"  baixando {url} ...")
    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(CACHE_DIR)
        os.remove(zip_path)
        return csv_path if os.path.exists(csv_path) else None
    except Exception as e:
        print(f"  ! falha em {date_str}: {e}")
        return None


def load_day(csv_path):
    """Retorna (times_ms float64, prices float64), ordenados por tempo."""
    # aggTrades: agg_id, price, qty, first_id, last_id, time, is_buyer_maker, is_best
    cols = ["id", "price", "qty", "f_id", "l_id", "time", "is_bm", "is_best"]
    df = pd.read_csv(csv_path, header=None, names=cols, usecols=["price", "time"],
                     dtype={"price": np.float64, "time": np.float64})
    times = df["time"].to_numpy()
    prices = df["price"].to_numpy()
    # normaliza para ms (alguns dumps usam microssegundos)
    if len(times) and times[0] > 1e14:
        times = times / 1000.0
    order = np.argsort(times, kind="stable")
    return times[order], prices[order]


def find_triggers(times, prices, threshold, window_ms, cooldown_ms):
    """Two-pointer: detecta |price[r]-price[left]| >= threshold em <= window_ms.
    Retorna lista de (idx_gatilho, direcao +1/-1)."""
    triggers = []
    left = 0
    last_t = -1e18
    n = len(times)
    for r in range(1, n):
        while times[r] - times[left] > window_ms:
            left += 1
        if left == r:
            continue
        diff = prices[r] - prices[left]
        if abs(diff) >= threshold and (times[r] - last_t) > cooldown_ms:
            triggers.append((r, 1 if diff > 0 else -1))
            last_t = times[r]
    return triggers


def simulate(times, prices, triggers, hold_ms, latency_ms,
             multiplier, stake, commission_frac, slippage_bps, mode, rng):
    """Simulacao fiel. Retorna array de PnL liquido ($) por trade.
    mode: 'momentum' (segue choque), 'fade' (contra), 'random' (nulo)."""
    n = len(times)
    commission = stake * commission_frac           # $ por trade
    slip = slippage_bps / 10000.0                   # fracao por perna
    pnls = []
    for (r, d) in triggers:
        # entrada: primeiro tick em t[r] + latencia (voce reage DEPOIS do choque)
        e = np.searchsorted(times, times[r] + latency_ms, side="left")
        if e >= n:
            continue
        # saida: primeiro tick em t[entrada] + hold
        x = np.searchsorted(times, times[e] + hold_ms, side="left")
        if x >= n:
            continue
        entry, exit_ = prices[e], prices[x]
        if mode == "momentum":
            side = d
        elif mode == "fade":
            side = -d
        else:  # random (controle nulo)
            side = 1 if rng.random() < 0.5 else -1
        move_pct = side * (exit_ - entry) / entry
        move_pct -= 2.0 * slip                      # slippage round-trip contra voce
        gross = move_pct * multiplier * stake
        pnls.append(gross - commission)
    return np.array(pnls, dtype=np.float64)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def bootstrap_mean_ci(x, iters=2000, z=0.95, rng=None):
    if len(x) == 0:
        return (0.0, 0.0)
    rng = rng or np.random.default_rng(42)
    means = np.empty(iters)
    n = len(x)
    for i in range(iters):
        means[i] = x[rng.integers(0, n, n)].mean()
    lo = np.percentile(means, (1 - z) / 2 * 100)
    hi = np.percentile(means, (1 + z) / 2 * 100)
    return (lo, hi)


def summarize(name, pnls, breakeven_move, rng):
    n = len(pnls)
    if n == 0:
        print(f"  {name:9}: sem trades")
        return None
    wins = int((pnls > 0).sum())
    wr = wins / n
    wlo, whi = wilson(wins, n)
    ev = pnls.mean()
    elo, ehi = bootstrap_mean_ci(pnls, rng=np.random.default_rng(7))
    total = pnls.sum()
    print(f"  {name:9}: trades={n:5d}  WR={wr*100:5.2f}% [{wlo*100:5.2f},{whi*100:5.2f}]  "
          f"EV/trade=${ev:+.4f} [${elo:+.4f},${ehi:+.4f}]  total=${total:+.2f}")
    return {"n": n, "wr": wr, "ev": ev, "ev_lo": elo, "ev_hi": ehi, "total": total}


def run_sweep(days_data, args):
    """Varre uma grade de parametros nos dias ja carregados (sem novo download).
    Decide pela premissa PURA (EV bruto, sem custos): se nem a melhor config tem
    continuacao bruta positiva, H1 esta morto independente de custo."""
    thresholds = [20.0, 30.0, 50.0, 75.0, 100.0]
    windows = [500.0]
    holds = [500.0, 1000.0, 2000.0, 5000.0, 10000.0]
    latencies = [50.0, 150.0, 500.0]
    mult, stake = args.multiplier, args.stake
    cfrac, slip, cd = args.commission_frac, args.slippage_bps, args.cooldown_ms
    rng = np.random.default_rng(123)

    print("=" * 100)
    print(f"SWEEP H1 | {args.symbol} | {len(days_data)} dia(s) | mult x{mult:.0f} stake ${stake:.0f} "
          f"comissao=${stake*cfrac:.2f}/trade slippage={slip}bps")
    print(f"grade: thr={thresholds} hold(ms)={holds} lat(ms)={latencies} (win={windows[0]:.0f}ms)")
    print("=" * 100)

    rows = []
    for th in thresholds:
        for win in windows:
            trigs = [find_triggers(t, p, th, win, cd) for (_, t, p) in days_data]
            if sum(len(x) for x in trigs) < 30:
                continue
            for hold in holds:
                for lat in latencies:
                    mom, rnd, momg = [], [], []
                    for (_, t, p), trg in zip(days_data, trigs):
                        if not trg:
                            continue
                        mom.append(simulate(t, p, trg, hold, lat, mult, stake, cfrac, slip, "momentum", rng))
                        rnd.append(simulate(t, p, trg, hold, lat, mult, stake, cfrac, slip, "random", rng))
                        momg.append(simulate(t, p, trg, hold, lat, mult, stake, 0.0, 0.0, "momentum", rng))
                    mom, rnd, momg = np.concatenate(mom), np.concatenate(rnd), np.concatenate(momg)
                    rows.append({"th": th, "win": win, "hold": hold, "lat": lat, "n": len(mom),
                                 "gross": float(momg.mean()), "net": float(mom.mean()),
                                 "rnd": float(rnd.mean()), "wr": float((mom > 0).mean())})

    if not rows:
        print("Sem gatilhos suficientes na grade.")
        return
    rows.sort(key=lambda r: r["gross"], reverse=True)
    print(f"\n  {'THR':>4} {'HOLD':>6} {'LAT':>5} {'N':>5} {'EV_BRUTO':>9} {'EV_LIQ':>9} {'EV_RND':>9} {'WR':>6}")
    print("  " + "-" * 70)
    for r in rows[:25]:
        flag = ""
        if r["gross"] > 0:
            flag += " bruto+"
        if r["net"] > 0 and r["net"] > r["rnd"]:
            flag += " LIQ+>nulo"
        print(f"  {r['th']:4.0f} {r['hold']:6.0f} {r['lat']:5.0f} {r['n']:5d} "
              f"${r['gross']:+8.4f} ${r['net']:+8.4f} ${r['rnd']:+8.4f} {r['wr']*100:5.1f}%{flag}")
    print("  " + "-" * 70)

    best = rows[0]
    print()
    if best["gross"] <= 0:
        print(f">>> PREMISSA MORTA: a MELHOR de {len(rows)} configs (thr={best['th']:.0f} "
              f"hold={best['hold']:.0f} lat={best['lat']:.0f}) tem EV BRUTO ${best['gross']:+.4f} <= 0.")
        print(">>> Nenhuma combinacao tem continuacao positiva nem SEM custos. "
              "Otimizar custo nao salva -> H1 sem edge (como o Oraculo).")
    else:
        net_pos = [r for r in rows if r["net"] > 0 and r["net"] > r["rnd"]]
        print(f">>> Melhor EV BRUTO: thr={best['th']:.0f} hold={best['hold']:.0f} lat={best['lat']:.0f} "
              f"-> ${best['gross']:+.4f} (liq ${best['net']:+.4f} vs nulo ${best['rnd']:+.4f}).")
        if net_pos:
            print(f">>> {len(net_pos)}/{len(rows)} configs liquidas>0 acima do nulo. CUIDADO: vies de "
                  "multiplos testes -> OBRIGATORIO validar OOS em dias diferentes antes de crer.")
        else:
            print(">>> Nenhuma config fica liquida>0 acima do nulo: sinal bruto nao sobrevive custos.")
    print("=" * 100)


def main():
    ap = argparse.ArgumentParser(description="H1 momentum pos-choque (Binance BTC, sim fiel)")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--start", default="2026-06-19", help="data inicial YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=50.0, help="$ do choque")
    ap.add_argument("--window-ms", type=float, default=500.0)
    ap.add_argument("--hold-ms", type=float, default=2000.0)
    ap.add_argument("--latency-ms", type=float, default=150.0, help="atraso ate sua entrada")
    ap.add_argument("--cooldown-ms", type=float, default=5000.0)
    ap.add_argument("--multiplier", type=float, default=800.0)
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--commission-frac", type=float, default=0.24, help="comissao como fracao do stake")
    ap.add_argument("--slippage-bps", type=float, default=1.0, help="slippage por perna (bps)")
    ap.add_argument("--sweep", action="store_true", help="varre grade de parametros (usa cache)")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    days_data = []
    for i in range(args.days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        csv_path = download_day(args.symbol, d)
        if not csv_path:
            continue
        print(f"[{d}] carregando...")
        times, prices = load_day(csv_path)
        print(f"[{d}] ticks={len(times):,}")
        days_data.append((d, times, prices))

    if not days_data:
        print("\nNenhum dado processado.")
        return

    if args.sweep:
        run_sweep(days_data, args)
        return

    rng = np.random.default_rng(123)
    breakeven_move = (args.stake * args.commission_frac) / (args.multiplier * args.stake)
    print("=" * 92)
    print(f"H1 momentum | {args.symbol} | choque>=${args.threshold} em {args.window_ms:.0f}ms | "
          f"hold {args.hold_ms:.0f}ms | latencia {args.latency_ms:.0f}ms")
    print(f"mult x{args.multiplier:.0f} stake ${args.stake:.0f} comissao=${args.stake*args.commission_frac:.2f}/trade "
          f"slippage={args.slippage_bps}bps/perna")
    print(f">>> Break-even: o preco precisa CONTINUAR a favor >= {breakeven_move*100:.4f}% apos a entrada")
    print("=" * 92)

    agg = {"momentum": [], "fade": [], "random": []}
    for (d, times, prices) in days_data:
        triggers = find_triggers(times, prices, args.threshold, args.window_ms, args.cooldown_ms)
        print(f"[{d}] gatilhos>=${args.threshold}={len(triggers)}")
        if not triggers:
            continue
        for mode in ("momentum", "fade", "random"):
            p = simulate(times, prices, triggers, args.hold_ms, args.latency_ms,
                         args.multiplier, args.stake, args.commission_frac,
                         args.slippage_bps, mode, rng)
            agg[mode].append(p)
            summarize(mode, p, breakeven_move, rng)

    print("\n" + "=" * 92)
    print(f"AGREGADO ({len(days_data)} dias)")
    print("=" * 92)
    res = {}
    for mode in ("momentum", "fade", "random"):
        allp = np.concatenate(agg[mode]) if agg[mode] else np.array([])
        res[mode] = summarize(mode, allp, breakeven_move, rng)

    print("\n" + "-" * 92)
    m, rnd = res.get("momentum"), res.get("random")
    if m and rnd:
        beats_null = m["ev_lo"] > rnd["ev_hi"]
        ev_positive = m["ev_lo"] > 0
        if ev_positive and beats_null:
            print(f">>> POSSIVEL EDGE: momentum EV/trade ${m['ev']:+.4f} com IC>0 E batendo o controle nulo.")
            print(">>> Proximo: realismo cross-venue (Deriv cryBTCUSD vs Binance + latencia real) e OOS.")
        elif ev_positive and not beats_null:
            print(f">>> EV>0 mas NAO bate o controle nulo (random EV ${rnd['ev']:+.4f}). "
                  "Provavel variancia, nao edge direcional.")
        else:
            print(f">>> SEM EDGE: momentum EV/trade ${m['ev']:+.4f}, IC inclui/abaixo de 0. "
                  "Entrar DEPOIS do choque nao paga os custos.")
    print("-" * 92)


if __name__ == "__main__":
    main()
