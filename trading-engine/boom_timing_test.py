"""T2 - Teste RIGOROSO de memoria no timing de spikes Boom/Crash.

Pergunta de decisao: o gap (ticks entre spikes) tem MEMORIA (hazard sobe com a
idade -> "spike atrasado" fica mais provavel -> possivel edge de timing) ou e
MEMORYLESS (geometrico/exponencial -> falacia do apostador, sem edge)?

Por que este modulo (e nao o boom_memory_test.py "de olho"):
  - Detector de spike CALIBRADO por magnitude: |retorno| > mult x mediana(|retorno|)
    NA DIRECAO do indice. O coletor antigo usava "qualquer tick positivo" (delta>0),
    que conta ruido de drift como spike e contamina os gaps curtos.
  - Coleta com paginacao + DEDUP por epoch. A paginacao antiga (end=times[0]-1 sem
    dedup) reusava a mesma janela: 500k "ticks" viravam ~100k reais repetidos, dando
    so ~177 spikes. Aqui paramos quando o historico real acaba (sem progresso).
  - POOL de gaps NORMALIZADOS (gap/N) entre varios simbolos. Sob o nulo (memoryless,
    taxa 1/N) cada gap/N ~ Exp(1); entao pooling multiplica o poder estatistico.
  - Veredito com IC: shape k de Weibull (k=1 memoryless; k>1 hazard CRESCENTE; k<1
    clustering) via MLE + IC bootstrap; KS vs exponencial; sobrevivencia condicional.

Uso:
  python boom_timing_test.py                     # coleta fresca multi-simbolo + veredito
  python boom_timing_test.py --offline gaps.txt  # so analisa um arquivo de gaps (1/linha, ja em ticks)
  python boom_timing_test.py --symbols BOOM500,CRASH500 --chunks 40
"""
import argparse
import asyncio
import math
import os
import re
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_SYMBOLS = ["BOOM300N", "BOOM500", "BOOM600", "BOOM900", "BOOM1000",
                   "CRASH300N", "CRASH500", "CRASH600", "CRASH900", "CRASH1000"]


def spec_n(sym):
    m = re.search(r"(\d+)", sym or "")
    return int(m.group(1)) if m else 0


def spike_dir(sym):
    s = (sym or "").upper()
    return 1 if s.startswith("BOOM") else (-1 if s.startswith("CRASH") else 0)


# --------------------------------------------------------------------------- #
# Coleta (paginacao para tras com DEDUP por epoch)
# --------------------------------------------------------------------------- #
async def fetch_prices(client, symbol, chunks):
    seen = set()
    pairs = []
    end = "latest"
    for i in range(chunks):
        try:
            res = await client.send_request({
                "ticks_history": symbol, "end": end, "count": 5000,
                "style": "ticks", "adjust_start_time": 1,
            })
        except Exception as e:
            print(f"  AVISO {symbol}: request falhou ({e}); parando")
            break
        hist = res.get("history") or {}
        ts, ps = hist.get("times") or [], hist.get("prices") or []
        if not ts:
            break
        new = [(int(t), float(p)) for t, p in zip(ts, ps) if int(t) not in seen]
        if not new:  # sem progresso -> fim do historico disponivel
            break
        for t, _ in new:
            seen.add(t)
        pairs.extend(new)
        end = min(t for t, _ in new) - 1
        await asyncio.sleep(0.5)
    if not pairs:
        return []
    pairs.sort()
    return [p for _, p in pairs]


def detect_gaps(prices, direction, mult):
    """Spike = |retorno| > mult x mediana(|retorno|) na direcao do indice.
    Retorna gaps (ticks entre spikes consecutivos), descartando o 1o."""
    p = np.asarray(prices, float)
    if len(p) < 200:
        return []
    r = np.diff(p)
    scale = float(np.median(np.abs(r)))
    if scale <= 0:
        return []
    is_spike = (np.abs(r) > mult * scale) & (np.sign(r) == direction)
    idx = np.flatnonzero(is_spike)
    if len(idx) < 4:
        return []
    gaps = np.diff(idx)
    return gaps[1:].tolist()  # descarta o 1o gap (inicio arbitrario)


# --------------------------------------------------------------------------- #
# Estatistica
# --------------------------------------------------------------------------- #
def weibull_shape_mle(x):
    """MLE do shape k de Weibull por bisseccao. k=1 <=> exponencial (memoryless)."""
    x = np.asarray(x, float)
    x = x[x > 0]
    if len(x) < 5:
        return float("nan")
    lnx = np.log(x)
    mean_lnx = float(np.mean(lnx))

    def g(k):
        xk = np.power(x, k)
        return float(np.sum(xk * lnx) / np.sum(xk) - 1.0 / k - mean_lnx)

    lo, hi = 0.1, 12.0
    glo, ghi = g(lo), g(hi)
    if glo == 0:
        return lo
    if glo * ghi > 0:
        return float("nan")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        gm = g(mid)
        if abs(gm) < 1e-9:
            return mid
        if glo * gm < 0:
            hi = mid
        else:
            lo, glo = mid, gm
    return 0.5 * (lo + hi)


def bootstrap_ci(x, stat, B=2000, seed=7):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    n = len(x)
    vals = []
    for _ in range(B):
        v = stat(x[rng.integers(0, n, n)])
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def ks_vs_exp(x):
    """KS entre a empirica e Exp(mean=mean(x)). crit ~ 1.36/sqrt(n) (alpha=0.05)."""
    x = np.sort(np.asarray(x, float))
    n = len(x)
    mu = float(x.mean())
    if mu <= 0 or n < 5:
        return float("nan"), float("nan")
    Fn = np.arange(1, n + 1) / n
    Fexp = 1.0 - np.exp(-x / mu)
    D = float(np.max(np.abs(Fn - Fexp)))
    return D, 1.36 / math.sqrt(n)


def cond_survival(x, m):
    x = np.asarray(x, float)
    past = x[x > m]
    if len(past) == 0:
        return float("nan")
    return float(np.mean(past > 2 * m))


def hazard_by_age(x, nbins=10):
    x = np.asarray(x, float)
    hi = float(np.percentile(x, 95))
    edges = np.linspace(0, hi, nbins + 1)
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        at_risk = int(np.sum(x >= a))
        ev = int(np.sum((x >= a) & (x < b)))
        if at_risk >= 15:
            rows.append((a, b, at_risk, ev, ev / at_risk))
    return rows


def analyze(gaps_norm, label):
    x = np.asarray([g for g in gaps_norm if g > 0], float)
    n = len(x)
    print("=" * 74)
    print(f"T2 VEREDITO RIGOROSO - {label}  (n={n} gaps normalizados)")
    print("=" * 74)
    if n < 30:
        print(f"  amostra insuficiente (n={n}). Colete mais antes de concluir.")
        return None
    mean, med, sd = float(x.mean()), float(np.median(x)), float(x.std(ddof=1))
    cv = sd / mean if mean else float("nan")
    print(f"  media={mean:.3f}  mediana={med:.3f}  sd={sd:.3f}  CV={cv:.3f}  "
          f"(memoryless: CV~1.00, mediana/media~0.69)")
    print(f"  mediana/media = {med/mean:.3f}")

    k = weibull_shape_mle(x)
    klo, khi = bootstrap_ci(x, weibull_shape_mle, B=2000)
    print(f"\n  Weibull shape k = {k:.3f}  IC95% bootstrap [{klo:.3f}, {khi:.3f}]")
    print(f"     k=1 memoryless | k>1 hazard CRESCE (spike 'atrasado' + provavel) | k<1 clustering")

    D, crit = ks_vs_exp(x)
    print(f"  KS vs exponencial: D={D:.4f}  crit(0.05)~{crit:.4f}  -> "
          f"{'REJEITA exp' if D > crit else 'NAO rejeita exp'} (aprox; Lilliefors seria + rigoroso)")

    cs = cond_survival(x, med)
    cslo, cshi = bootstrap_ci(x, lambda s: cond_survival(s, np.median(s)), B=2000)
    print(f"  P(gap>2*mediana | gap>mediana) = {cs*100:.1f}%  IC95% [{cslo*100:.1f}%, {cshi*100:.1f}%]  "
          f"(memoryless ~50%)")

    rows = hazard_by_age(x)
    if rows:
        print("\n  hazard por idade (normalizada):")
        for a, b, ar, ev, h in rows:
            print(f"    [{a:4.2f},{b:4.2f}) risco={ar:5d} ev={ev:4d} h={h*100:5.2f}%  {'#'*int(round(h*50))}")

    print("\n  " + "-" * 70)
    if not math.isnan(klo) and klo > 1.0:
        verdict = ("MEMORIA: hazard CRESCENTE significativo (IC de k todo > 1). 'Spike "
                   "atrasado' e real -> vale medir EV (entrada overdue vs drift+margem+stop-out).")
    elif not math.isnan(khi) and khi < 1.0:
        verdict = ("CLUSTERING (IC de k todo < 1): spikes se AGRUPAM; 'overdue' fica MENOS "
                   "provavel. Anti-tese de timing.")
    else:
        verdict = ("MEMORYLESS nao rejeitado (k=1 dentro do IC). Sem edge de timing: "
                   "P(spike) ~ taxa base independ. da idade. => T2 REFUTADA.")
    print(f"  VEREDITO: {verdict}")
    print("=" * 74)
    return {"n": n, "k": k, "k_ci": (klo, khi), "cv": cv, "cond_surv": cs}


# --------------------------------------------------------------------------- #
async def collect_and_analyze(symbols, chunks, mult):
    from dotenv import load_dotenv
    from deriv_client import DerivClient
    load_dotenv()
    client = DerivClient(app_id=os.getenv("DERIV_APP_ID", "1089") or "1089",
                         api_token=os.getenv("DERIV_API_TOKEN", ""), use_demo=True)
    await client.connect()
    pooled = []
    per_symbol = []
    try:
        for sym in symbols:
            N = spec_n(sym)
            d = spike_dir(sym)
            if not N or not d:
                print(f"  pulando {sym} (N/direcao invalidos)")
                continue
            prices = await fetch_prices(client, sym, chunks)
            gaps = detect_gaps(prices, d, mult)
            norm = [g / N for g in gaps]
            pooled.extend(norm)
            mg = float(np.mean(gaps)) if gaps else 0.0
            per_symbol.append((sym, N, len(prices), len(gaps), mg))
            print(f"  {sym:10s} N={N:5d} ticks={len(prices):7d} spikes={len(gaps):5d} "
                  f"gap_medio={mg:7.1f} (spec {N})")
    finally:
        await client.disconnect()
    print()
    return pooled, per_symbol


def main():
    ap = argparse.ArgumentParser(description="T2: teste rigoroso de memoria no timing de spikes Boom/Crash")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--chunks", type=int, default=60, help="max chunks (5000 ticks) por simbolo; para no fim do historico")
    ap.add_argument("--mult", type=float, default=8.0, help="limiar de spike = mult x mediana(|retorno|)")
    ap.add_argument("--offline", default="", help="arquivo de gaps (1/linha, em ticks) p/ so analisar")
    ap.add_argument("--offline-n", type=int, default=500, help="N do simbolo do arquivo offline (p/ normalizar)")
    ap.add_argument("--out", default="boom_gaps_pooled.txt")
    args = ap.parse_args()

    if args.offline:
        with open(args.offline) as f:
            gaps = [int(float(x)) for x in f if x.strip()]
        analyze([g / args.offline_n for g in gaps], f"offline {os.path.basename(args.offline)} (N={args.offline_n})")
        return

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    pooled, per_symbol = asyncio.run(collect_and_analyze(symbols, args.chunks, args.mult))
    if pooled:
        with open(args.out, "w") as f:
            for g in pooled:
                f.write(f"{g:.6f}\n")
        print(f"  pool salvo -> {args.out} ({len(pooled)} gaps normalizados de {len(per_symbol)} simbolos)\n")
        analyze(pooled, f"POOL {len(per_symbol)} simbolos Boom/Crash")
    else:
        print("  nenhum gap coletado.")


if __name__ == "__main__":
    main()
