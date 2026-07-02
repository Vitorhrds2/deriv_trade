"""T3 v2 - Scanner de VALOR-RELATIVO em contratos EXOTICOS/BARREIRA (Deriv sinteticos).

O v1 (relative_value_scan.py) cobriu Rise/Fall por duracao (payoff so depende do ponto
final). Os exoticos tem payoff PATH-DEPENDENT (tocar/ficar dentro), entao a prob teorica
nao tem forma fechada simples -> usamos o MESMO DGP validado no v1 (GBM auto-calibrado
mu,sigma dos log-retornos do proprio feed) e medimos a prob por MONTE CARLO.

Por que MC e FIEL aqui: o indice sintetico so existe nos TICKS; a Deriv avalia a barreira
em cada tick. Logo um GBM discreto por tick (nao um difusao continua) e o modelo correto,
nao uma aproximacao.

3 medidas independentes por celula (igual ao v1):
  1. P_emp : prob de vitoria MEDIDA em janelas NAO-SOBREPOSTAS do historico (model-free).
             Janela deslizando de 1 tick infla a amostra (replicacao pseudo): N janelas de
             600 ticks em 100k ticks dao so ~166 INDEPENDENTES -> Wilson com N=100k seria
             ~15x estreito demais (falso EV_lo>0). Usamos step=n para IC honesto.
  2. P_mc  : prob TEORICA por Monte Carlo no GBM DRIFTLESS (mu=0). Os indices sinteticos
             sao MARTINGALES por construcao; o drift medido na amostra e ruido ~N(0,sd/sqrt N)
             e, se injetado no MC, cria 'edges' direcionais falsos (ex.: ONETOUCH pra cima
             'ganha' so porque a amostra subiu). Por padrao mu=0; --use-drift testa o oposto.
  3. payout: gross_return REAL ao vivo (API proposal) = payout/ask.
edge = P_emp - 1/gross_return ; EV/$1 = P_emp*gross_return - 1.
Pessimista: so crava EDGE se o PISO de Wilson de P_emp ainda der EV>0.

Contratos cobertos: ONETOUCH, NOTOUCH (toca/nao toca), EXPIRYRANGE, EXPIRYMISS (termina
dentro/fora), RANGE, UPORDOWN (fica dentro / sai), HIGHER, LOWER (CALL/PUT com barreira).

Barreira: offset = k * sigma_horizonte (k em multiplos do desvio esperado ate a expiracao),
sigma_horizonte = sd * sqrt(n_ticks), n_ticks = duracao_s / tick_dt (tick_dt medido do feed).

Uso:
  python exotic_value_scan.py --symbols R_100,1HZ100V --chunks 20 \
      --durations-s 30,120,300 --k 1.0,1.5 --mc 20000
"""
import argparse
import asyncio
import math
import os
import sys
from statistics import mean, pstdev

import numpy as np
from dotenv import load_dotenv
from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
STAKE = 10.0
Z = 1.96  # IC95%

# Cada probe: payoff -> funcao vetorizada de vitoria sobre 'path' (preco normalizado ao
# inicio=1.0, SEM o ponto inicial), com barreiras ub=1+r_up, db=1-r_dn (None se nao usa).
# 'use': quais barreiras pedir a API ('up', 'dn' ou 'both').
PROBES = [
    {"name": "ONETOUCH_up", "ct": "ONETOUCH", "use": "up",
     "win": lambda path, ub, db: (path >= ub).any(axis=-1)},
    {"name": "NOTOUCH_up", "ct": "NOTOUCH", "use": "up",
     "win": lambda path, ub, db: ~(path >= ub).any(axis=-1)},
    {"name": "EXPIRYRANGE", "ct": "EXPIRYRANGE", "use": "both",
     "win": lambda path, ub, db: (path[..., -1] >= db) & (path[..., -1] <= ub)},
    {"name": "EXPIRYMISS", "ct": "EXPIRYMISS", "use": "both",
     "win": lambda path, ub, db: (path[..., -1] < db) | (path[..., -1] > ub)},
    {"name": "RANGE_stays", "ct": "RANGE", "use": "both",
     "win": lambda path, ub, db: ((path > db) & (path < ub)).all(axis=-1)},
    {"name": "UPORDOWN_out", "ct": "UPORDOWN", "use": "both",
     "win": lambda path, ub, db: ((path >= ub) | (path <= db)).any(axis=-1)},
    {"name": "HIGHER", "ct": "CALL", "use": "up",
     "win": lambda path, ub, db: path[..., -1] > ub},
    {"name": "LOWER", "ct": "PUT", "use": "dn",
     "win": lambda path, ub, db: path[..., -1] < db},
]


def wilson(successes, n, z=Z):
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


async def fetch_prices(client, symbol, chunks, delay=0.7):
    """Retorna (prices, times) historicos ordenados (times em segundos)."""
    current_end, prices, times = "latest", [], []
    for _ in range(chunks):
        res = None
        for attempt in range(4):
            res = await client.send_request({
                "ticks_history": symbol, "adjust_start_time": 1,
                "count": 5000, "end": current_end, "style": "ticks",
            })
            if "error" not in res:
                break
            await asyncio.sleep(2 ** (attempt + 1))
        if res is None or "error" in res:
            break
        hist = res.get("history", {})
        t, pr = hist.get("times", []), hist.get("prices", [])
        if not pr or not t:
            break
        prices = list(pr) + prices
        times = list(t) + times
        current_end = t[0] - 1
        await asyncio.sleep(delay)
    return [float(p) for p in prices], [float(t) for t in times]


def build_request(symbol, ct, dur_s, use, r, spot):
    req = {"proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": ct,
           "currency": "USD", "underlying_symbol": symbol,
           "duration": int(dur_s), "duration_unit": "s"}
    off = r * spot
    if use == "up":
        req["barrier"] = f"+{off:.2f}"
    elif use == "dn":
        req["barrier"] = f"-{off:.2f}"
    else:  # both
        req["barrier"] = f"+{off:.2f}"
        req["barrier2"] = f"-{off:.2f}"
    return req


async def get_gross_return(client, req):
    res = await client.send_request(req)
    if "error" in res:
        return None, res["error"].get("message", "erro")
    p = res.get("proposal", {})
    payout, ask = p.get("payout"), p.get("ask_price")
    if not payout or not ask:
        return None, "sem payout"
    return payout / ask, None


def emp_win_prob(prices_np, n, use, r, win_fn):
    """Janelas NAO-SOBREPOSTAS de n+1 ticks (step=n) -> amostras independentes e IC honesto.
    Barreira relativa ao inicio de cada janela."""
    if len(prices_np) < n + 2:
        return 0, 0
    W = np.lib.stride_tricks.sliding_window_view(prices_np, n + 1)
    W = W[::n]                   # step=n: janelas independentes (sem replicacao pseudo)
    rel = W / W[:, :1]            # normaliza cada janela ao seu inicio
    path = rel[:, 1:]            # (M, n) sem o ponto inicial
    ub = 1.0 + r if use in ("up", "both") else None
    db = 1.0 - r if use in ("dn", "both") else None
    wins = win_fn(path, ub, db)
    return int(wins.sum()), int(wins.size)


def mc_win_prob(mu, sd, n, use, r, win_fn, iters, rng):
    steps = rng.normal(mu, sd, size=(iters, n))
    path = np.exp(np.cumsum(steps, axis=1))   # normalizado ao inicio=1.0
    ub = 1.0 + r if use in ("up", "both") else None
    db = 1.0 - r if use in ("dn", "both") else None
    wins = win_fn(path, ub, db)
    p = float(wins.mean())
    se = math.sqrt(p * (1 - p) / iters) if iters else 0.0
    return p, se


async def scan_symbol(symbol, chunks, durations_s, ks, iters, use_drift=False):
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    rows = []
    try:
        print(f"\n>>> {symbol}: baixando ~{chunks} blocos...")
        prices, times = await fetch_prices(client, symbol, chunks)
        if len(prices) < 5000:
            print(f"  ! ticks insuficientes ({len(prices)}). Pulando.")
            return rows
        rets = [math.log(prices[i + 1] / prices[i]) for i in range(len(prices) - 1)
                if prices[i] > 0 and prices[i + 1] > 0]
        mu, sd = mean(rets), pstdev(rets)
        t_drift = mu / (sd / math.sqrt(len(rets))) if sd > 0 else 0.0
        mu_fair = mu if use_drift else 0.0   # martingale por construcao: mu=0 (default)
        dts = np.diff(np.array(times))
        tick_dt = float(np.median(dts[dts > 0])) if len(dts) else 1.0
        prices_np = np.array(prices, dtype=np.float64)
        spot = prices[-1]
        rng = np.random.default_rng(7)
        print(f"  {len(prices):,} ticks | dt~{tick_dt:.1f}s | log-ret mu={mu:.2e} sd={sd:.2e} "
              f"| drift t-stat={t_drift:+.2f} ({'signif' if abs(t_drift) > 2 else 'ruido ~0'}) "
              f"| MC mu={'calibrado' if use_drift else '0 (driftless)'} | spot={spot:.4f}")

        for dur_s in durations_s:
            n = max(1, round(dur_s / tick_dt))
            if len(prices) < n + 2:
                print(f"  dur={dur_s}s (n={n} ticks): historico curto, pulando.")
                continue
            sigma_h = sd * math.sqrt(n)
            for k in ks:
                r = k * sigma_h               # offset relativo da barreira
                for pb in PROBES:
                    req = build_request(symbol, pb["ct"], dur_s, pb["use"], r, spot)
                    gr, err = await get_gross_return(client, req)
                    await asyncio.sleep(0.25)
                    if gr is None:
                        print(f"  {pb['name']:13} dur={dur_s}s k={k}: sem cotacao ({err})")
                        continue
                    we, ne = emp_win_prob(prices_np, n, pb["use"], r, pb["win"])
                    if ne == 0:
                        continue
                    p_emp = we / ne
                    p_lo, _ = wilson(we, ne)
                    p_mc, se_mc = mc_win_prob(mu_fair, sd, n, pb["use"], r, pb["win"], iters, rng)
                    ev = p_emp * gr - 1.0
                    ev_lo = p_lo * gr - 1.0
                    rows.append((symbol, pb["name"], dur_s, k, n, p_emp, p_mc,
                                 gr, ev, ev_lo, ne))
    finally:
        await client.disconnect()
    return rows


def print_table(rows):
    if not rows:
        print("Nenhum dado coletado.")
        return
    rows.sort(key=lambda r: r[8], reverse=True)
    print("\n" + "=" * 108)
    print(f"  {'SIMBOLO':8} {'CONTRATO':13} {'DUR':>5} {'k':>4} {'n':>4} {'P_emp':>7} "
          f"{'P_mc':>7} {'IMPLIC':>7} {'PAYOUT':>7} {'EV/$1':>8} {'EV_lo':>8}")
    print("=" * 108)
    for sym, name, dur, k, n, pe, pm, gr, ev, evlo, ne in rows:
        implied = 1.0 / gr
        flag = "  <== EDGE+" if evlo > 0 else (" <- EV+ (s/ margem)" if ev > 0 else "")
        print(f"  {sym:8} {name:13} {dur:4d}s {k:4.1f} {n:4d} {pe*100:6.2f}% {pm*100:6.2f}% "
              f"{implied*100:6.2f}% {(gr-1)*100:6.2f}% {ev:+8.4f} {evlo:+8.4f}{flag}")
    print("=" * 108)
    # Gate de credibilidade (mesma filosofia do auto-vet do monitor): EV_lo>0 sozinho nao
    # basta. Exige (a) DGP consistente |P_emp-P_mc|<3pp e (b) >=100 janelas independentes,
    # senao e fluke de N baixo (ex.: P_emp=100% em ~33 janelas) e/ou drift de amostra.
    MIN_N, MAX_DIV = 100, 0.03
    raw_pos = [r for r in rows if r[9] > 0]
    qualified = [r for r in raw_pos if abs(r[5] - r[6]) < MAX_DIV and r[10] >= MIN_N]
    best = max(rows, key=lambda r: r[9])
    if qualified:
        b = max(qualified, key=lambda r: r[9])
        print(f"\n>>> CANDIDATO A EDGE (passou o gate): {b[0]} {b[1]} dur={b[2]}s k={b[3]} -> "
              f"EV_lo {b[9]:+.4f}/$1, P_emp={b[5]*100:.1f}%~P_mc={b[6]*100:.1f}%, N={b[10]}. "
              f"CONFIRMAR ao vivo (payout muda).")
    else:
        rej = len(raw_pos)
        why = []
        for r in raw_pos:
            if r[10] < MIN_N:
                why.append("N baixo")
            elif abs(r[5] - r[6]) >= MAX_DIV:
                why.append("P_emp diverge do DGP")
        print(f"\n>>> SEM EDGE. {rej} celula(s) com EV_lo>0, mas TODAS reprovadas no gate "
              f"(N>=100 e |P_emp-P_mc|<3pp): "
              + (", ".join(sorted(set(why))) if why else "-") + ".")
        print(">>> Pelo MC driftless (DGP verdadeiro), P_mc < implied em toda celula -> margem "
              "da casa nos exoticos tambem. Os 'edges' eram drift de amostra + N baixo.")
    div = max(abs(r[5] - r[6]) for r in rows)
    print(f"    cross-check DGP: max|P_emp - P_mc| = {div*100:.2f}pp "
          + ("(GBM driftless bate -> exotico so reprecifica a mesma margem)"
             if div < 0.05 else "(DIVERGE: dominado por celulas de N baixo; ver gate acima)"))


async def main():
    ap = argparse.ArgumentParser(description="Scanner de valor-relativo em exoticos Deriv (T3 v2)")
    ap.add_argument("--symbols", default="R_100,1HZ100V")
    ap.add_argument("--chunks", type=int, default=20)
    ap.add_argument("--durations-s", default="120,300,600", dest="durations_s")
    ap.add_argument("--k", default="1.0,1.5")
    ap.add_argument("--mc", type=int, default=20000, help="iteracoes Monte Carlo")
    ap.add_argument("--use-drift", action="store_true", dest="use_drift",
                    help="injeta o drift medido no MC (default: mu=0, martingale). So p/ diagnostico.")
    args = ap.parse_args()
    durations_s = [int(x) for x in args.durations_s.split(",") if x.strip()]
    ks = [float(x) for x in args.k.split(",") if x.strip()]
    all_rows = []
    for sym in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        all_rows += await scan_symbol(sym, args.chunks, durations_s, ks, args.mc, args.use_drift)
    print_table(all_rows)


if __name__ == "__main__":
    asyncio.run(main())
