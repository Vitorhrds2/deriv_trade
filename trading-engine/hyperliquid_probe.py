#!/usr/bin/env python3
"""
D55 -- Hyperliquid cross-venue mispricing (funding rate arb + oracle/mark/mid divergence
vs Binance). Primeira hipotese em plataforma GENUINAMENTE NOVA (nem Deriv, nem Polymarket,
nem CEX-CEX -- ver docs/state_of_research.md, todos ja fechados).

Por que Hyperliquid e diferente do que ja foi refutado:
  - D9 (funding CEX-CEX Binance/Bybit/OKX, REFUTADO): usava construcao spot+perp
    (precisa da perna spot pra hedgear), round-trip 40bps (4 taker fills a 10bps).
    Hyperliquid x Binance permite construcao PERP-PERP (ambos os venues tem perp do
    mesmo ativo) -- so 4 fills tambem, mas custo menor: HL taker tier0=4.5bps +
    Binance taker~5bps, round-trip = 2*(4.5+5) = 19bps. Barreira de custo BEM menor.
  - D32 (latencia CEX-CEX Binance/Bybit/OKX, REFUTADO): testou se um CEX "lidera" o
    outro. Hyperliquid tem um mecanismo que NENHUM CEX tem -- publica simultaneamente
    oraclePx (referencia externa/cesto de CEX), markPx (proprio, com EMA de premium)
    e midPx (livro de ordens realmente tradeable) no mesmo endpoint. Testa-se se midPx
    (o preco que voce realmente compra/vende) atrasa em relacao ao oraclePx/Binance.

Dois testes independentes:
  D55a (run_funding_scan) -- Funding rate Hyperliquid vs Binance, mesmo ativo,
       construcao perp-perp. Mesma metodologia de soma de diffs assinados no periodo
       que D9/D26 (rastreio de historico, screening inicial -- viés de retrospecto
       reconhecido, precisa confirmacao OOS se algo aparecer, igual foi feito em D17).
  D55b (run_divergence_scan) -- Polling continuo de oraclePx/markPx/midPx (HL) vs
       Binance mid. Mede se |basis| excede o custo de round-trip (1 taker de cada lado,
       9.5bps) com frequencia e se reverte (tradeable) ou e estrutural.

Dados via API publica (sem key, sem custo, read-only): https://api.hyperliquid.xyz/info
"""
import argparse
import json
import statistics
import time
import urllib.request
from datetime import datetime, timezone

try:
    from stats_utils import bootstrap_ci
except ImportError:
    import random

    def bootstrap_ci(values, n_boot=2000, ci=0.95, seed=42):
        if not values:
            return (0.0, 0.0, 0.0)
        rng = random.Random(seed)
        n = len(values)
        means = []
        for _ in range(n_boot):
            sample = [values[rng.randrange(n)] for _ in range(n)]
            means.append(sum(sample) / n)
        means.sort()
        lo = means[int((1 - ci) / 2 * n_boot)]
        hi = means[int((1 + ci) / 2 * n_boot) - 1]
        return (lo, sum(values) / n, hi)

UA = {"User-Agent": "hyperliquid-probe/1.0 (research; read-only)"}
HL_INFO_URL = "https://api.hyperliquid.xyz/info"

HL_TAKER_BPS = 4.5        # tier 0 (0.045%), sem volume/staking discount
BINANCE_TAKER_BPS = 5.0   # USDT-M futures, retail (VIP0)
FUNDING_ARB_ROUNDTRIP_BPS = 2 * (HL_TAKER_BPS + BINANCE_TAKER_BPS)   # abre+fecha, perp-perp
DIVERGENCE_ROUNDTRIP_BPS = HL_TAKER_BPS + BINANCE_TAKER_BPS          # 1 leg cada lado

SYMBOLS = ["BTC", "ETH", "SOL", "ARB", "OP", "AVAX", "LINK", "DOGE", "SUI", "APT"]

RESULTS_FILE_FUNDING = "hyperliquid_funding_arb_results.json"
RESULTS_FILE_DIVERGENCE = "hyperliquid_divergence_results.jsonl"


def _post(body, timeout=10):
    req = urllib.request.Request(
        HL_INFO_URL, data=json.dumps(body).encode(),
        headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def hl_meta_and_ctxs():
    """1 chamada retorna oraclePx/markPx/midPx/funding/premium pra TODOS os ativos."""
    meta, ctxs = _post({"type": "metaAndAssetCtxs"})
    universe = meta["universe"]
    out = {}
    for u, c in zip(universe, ctxs):
        mid = c.get("midPx")
        out[u["name"]] = {
            "funding": float(c.get("funding", 0) or 0),
            "oraclePx": float(c.get("oraclePx", 0) or 0),
            "markPx": float(c.get("markPx", 0) or 0),
            "midPx": float(mid) if mid not in (None, "") else None,
            "premium": float(c.get("premium", 0) or 0) if c.get("premium") not in (None, "") else 0.0,
            "openInterest": float(c.get("openInterest", 0) or 0),
        }
    return out


def hl_funding_history(coin, start_ms, end_ms=None):
    """Endpoint retorna no MAXIMO 500 registros a partir de startTime PRA FRENTE (nao
    e "ultimos N ate agora") -- pagina explicitamente ate alcancar end_ms (default: now)."""
    if end_ms is None:
        end_ms = int(time.time() * 1000)
    out = []
    cursor = start_ms
    while cursor < end_ms:
        data = _post({"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms})
        if not data:
            break
        batch = [{"time": int(d["time"]), "rate": float(d["fundingRate"])} for d in data]
        out.extend(batch)
        last_t = batch[-1]["time"]
        if last_t <= cursor:
            break
        cursor = last_t + 1
        if len(data) < 500:
            break
    return out


def binance_funding_history(symbol, start_ms):
    url = (f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}"
           f"&startTime={start_ms}&limit=1000")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
    return [{"time": int(d["fundingTime"]), "rate": float(d["fundingRate"])} for d in data]


def binance_book_ticker(symbol):
    url = f"https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={symbol}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=5) as r:
        d = json.loads(r.read().decode())
    return (float(d["bidPrice"]) + float(d["askPrice"])) / 2


def run_funding_scan(days=30):
    print("=" * 90)
    print("D55a -- Hyperliquid vs Binance funding rate arb (perp-perp, sem perna spot)")
    print(f"Round-trip assumido: {FUNDING_ARB_ROUNDTRIP_BPS:.1f}bps "
          f"(HL {HL_TAKER_BPS}bps + Binance {BINANCE_TAKER_BPS}bps, abre+fecha)")
    print("AVISO: screening inicial com viés de retrospecto (soma sinal no periodo inteiro,")
    print("mesma limitacao reconhecida de D9/D26). Sinal aqui exige confirmacao OOS depois.")
    print("=" * 90)

    start_ms = int((time.time() - days * 86400) * 1000)
    try:
        hl_ctxs = hl_meta_and_ctxs()
    except Exception as e:
        print(f"ERRO fatal ao buscar metaAndAssetCtxs da Hyperliquid: {e}")
        return []

    results = []
    for sym in SYMBOLS:
        if sym not in hl_ctxs:
            print(f"  {sym}: nao listado na Hyperliquid, pulando")
            continue
        binance_sym = f"{sym}USDT"
        try:
            hl_hist = hl_funding_history(sym, start_ms)
        except Exception as e:
            print(f"  {sym}: erro historico HL ({e})")
            continue
        try:
            bn_hist = binance_funding_history(binance_sym, start_ms)
        except Exception as e:
            print(f"  {sym}: erro historico Binance ({e})")
            continue

        if len(hl_hist) < 10 or len(bn_hist) < 10:
            print(f"  {sym}: historico insuficiente (HL={len(hl_hist)}, Binance={len(bn_hist)})")
            continue

        # Funding HL e mais frequente que o da Binance (8h) -- soma o acumulado HL
        # dentro de cada janela de 8h que termina no timestamp do funding Binance.
        diffs_bps = []
        for bn in bn_hist:
            window_start = bn["time"] - 8 * 3600 * 1000
            hl_in_window = [h["rate"] for h in hl_hist if window_start < h["time"] <= bn["time"]]
            if not hl_in_window:
                continue
            hl_accum_bps = sum(hl_in_window) * 10000
            bn_bps = bn["rate"] * 10000
            diffs_bps.append(hl_accum_bps - bn_bps)

        if len(diffs_bps) < 20:
            print(f"  {sym}: poucas janelas alinhadas (N={len(diffs_bps)})")
            continue

        total_diff = sum(diffs_bps)
        avg_diff = statistics.mean(diffs_bps)
        lo, mean_d, hi = bootstrap_ci(diffs_bps)
        net_after_costs = abs(total_diff) - FUNDING_ARB_ROUNDTRIP_BPS
        ci_crosses_zero = lo < 0 < hi

        # Validacao IS/OOS (mesma disciplina de D17/D9-validacao): direcao decidida na
        # metade IS (cronologicamente mais antiga), testada de verdade so na OOS (mais
        # recente) -- sem isso, "net_after_costs" acima tem viés de retrospecto puro.
        mid = len(diffs_bps) // 2
        is_part, oos_part = diffs_bps[:mid], diffs_bps[mid:]
        is_sign = 1 if sum(is_part) > 0 else -1
        oos_signed_total = sum(oos_part) * is_sign  # rendimento de manter a direcao decidida na IS
        oos_lo, oos_mean, oos_hi = bootstrap_ci([x * is_sign for x in oos_part])
        oos_net = oos_signed_total - FUNDING_ARB_ROUNDTRIP_BPS
        oos_confirms = oos_net > 0 and oos_lo > 0

        results.append({
            "symbol": sym, "n_windows": len(diffs_bps),
            "total_diff_bps": total_diff, "avg_diff_bps_per_8h": avg_diff,
            "ci95": [lo, hi], "net_after_costs_bps": net_after_costs,
            "direction": "long_HL_short_BN" if total_diff < 0 else "long_BN_short_HL",
            "oos_net_after_costs_bps": oos_net, "oos_ci95": [oos_lo, oos_hi],
            "oos_confirms": oos_confirms,
        })
        if net_after_costs > 0 and not ci_crosses_zero:
            verdict = "SINAL (net>0, IC95% nao cruza zero)"
        elif net_after_costs > 0:
            verdict = "net>0 mas IC95% cruza zero"
        else:
            verdict = "negativo apos custos"
        oos_tag = "OOS CONFIRMA" if oos_confirms else "OOS NAO CONFIRMA"
        print(f"  {sym:6s} N={len(diffs_bps):3d} total_diff={total_diff:+8.2f}bps "
              f"avg={avg_diff:+6.3f}bps/8h CI95=[{lo:+.2f},{hi:+.2f}] "
              f"net_apos_custos={net_after_costs:+7.2f}bps -> {verdict} | "
              f"OOS(2a metade, mesma direcao): net={oos_net:+7.2f}bps CI95=[{oos_lo:+.2f},{oos_hi:+.2f}] -> {oos_tag}")

    with open(RESULTS_FILE_FUNDING, "w") as f:
        json.dump(results, f, indent=2)

    profitable = [r for r in results if r["net_after_costs_bps"] > 0 and not (r["ci95"][0] < 0 < r["ci95"][1])]
    oos_confirmed = [r for r in results if r["oos_confirms"]]
    print("\n" + "=" * 90)
    print(f"RESUMO D55a: {len(profitable)}/{len(results)} pares com sinal (periodo inteiro, viés retrospecto) | "
          f"{len(oos_confirmed)}/{len(results)} CONFIRMADOS na metade OOS (direcao fixada na IS)")
    if oos_confirmed:
        print("Confirmados OOS:", ", ".join(f"{r['symbol']}({r['direction']})" for r in oos_confirmed))
    print("=" * 90)
    return results


def run_divergence_scan(duration_s=600, interval_s=3.0, symbols=("BTC", "ETH", "SOL")):
    print("=" * 90)
    print("D55b -- Hyperliquid (oraclePx/markPx/midPx) vs Binance mid -- divergencia")
    print(f"Polling a cada {interval_s}s por {duration_s}s | simbolos={symbols}")
    print(f"Custo round-trip (1 leg cada lado): {DIVERGENCE_ROUNDTRIP_BPS:.1f}bps")
    print("=" * 90)

    samples = []
    n_polls = int(duration_s / interval_s)
    for i in range(n_polls):
        t0 = time.time()
        row = {"ts": datetime.now(timezone.utc).isoformat()}
        try:
            ctxs = hl_meta_and_ctxs()
        except Exception as e:
            print(f"  [{i}] erro HL: {e}")
            time.sleep(interval_s)
            continue

        for sym in symbols:
            c = ctxs.get(sym)
            if not c:
                continue
            try:
                bn_mid = binance_book_ticker(f"{sym}USDT")
            except Exception:
                bn_mid = None
            hl_mid = c["midPx"]
            row[sym] = {
                "hl_oracle": c["oraclePx"], "hl_mark": c["markPx"], "hl_mid": hl_mid,
                "binance_mid": bn_mid,
                "basis_mid_bps": ((hl_mid - bn_mid) / bn_mid * 10000
                                  if hl_mid and bn_mid else None),
                "basis_oracle_bps": ((c["oraclePx"] - bn_mid) / bn_mid * 10000
                                     if c["oraclePx"] and bn_mid else None),
            }

        samples.append(row)
        with open(RESULTS_FILE_DIVERGENCE, "a") as f:
            f.write(json.dumps(row) + "\n")

        if i % 20 == 0:
            btc = row.get("BTC", {})
            print(f"  [{i}/{n_polls}] BTC hl_mid={btc.get('hl_mid')} binance={btc.get('binance_mid')} "
                  f"basis_mid={btc.get('basis_mid_bps')}bps basis_oracle={btc.get('basis_oracle_bps')}bps")

        elapsed = time.time() - t0
        time.sleep(max(0, interval_s - elapsed))

    print("\n" + "=" * 90)
    print("ANALISE D55b")
    print("=" * 90)
    verdicts = []
    for sym in symbols:
        mid_basis = [s[sym]["basis_mid_bps"] for s in samples
                     if sym in s and s[sym].get("basis_mid_bps") is not None]
        oracle_basis = [s[sym]["basis_oracle_bps"] for s in samples
                        if sym in s and s[sym].get("basis_oracle_bps") is not None]
        if len(mid_basis) < 10:
            print(f"  {sym}: dados insuficientes (N={len(mid_basis)})")
            continue
        abs_mid = [abs(x) for x in mid_basis]
        lo, mean_d, hi = bootstrap_ci(mid_basis)
        n_exceed = sum(1 for x in abs_mid if x > DIVERGENCE_ROUNDTRIP_BPS)
        pct_exceed = n_exceed / len(abs_mid) * 100
        verdict = "POTENCIAL EDGE (>10% das amostras excede custo)" if pct_exceed > 10 else "sem edge (custo domina)"
        verdicts.append({"symbol": sym, "n": len(mid_basis), "pct_exceed": pct_exceed, "verdict": verdict})
        print(f"  {sym:5s} N={len(mid_basis):4d} basis_mid: mean={mean_d:+.3f}bps CI95=[{lo:+.3f},{hi:+.3f}] "
              f"max_abs={max(abs_mid):.3f}bps | basis_oracle_mean={statistics.mean(oracle_basis):+.3f}bps | "
              f"%>custo({DIVERGENCE_ROUNDTRIP_BPS:.1f}bps)={pct_exceed:.1f}% -> {verdict}")

    return samples, verdicts


def main():
    ap = argparse.ArgumentParser(description="D55 -- Hyperliquid cross-venue mispricing probe")
    ap.add_argument("--mode", choices=["funding", "divergence", "both"], default="both")
    ap.add_argument("--funding-days", type=int, default=30)
    ap.add_argument("--divergence-duration-s", type=int, default=600)
    ap.add_argument("--divergence-interval-s", type=float, default=3.0)
    args = ap.parse_args()

    if args.mode in ("funding", "both"):
        run_funding_scan(days=args.funding_days)
    if args.mode in ("divergence", "both"):
        print()
        run_divergence_scan(duration_s=args.divergence_duration_s,
                             interval_s=args.divergence_interval_s)


if __name__ == "__main__":
    main()
