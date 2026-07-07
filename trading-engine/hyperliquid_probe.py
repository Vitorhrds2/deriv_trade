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
RESULTS_FILE_WALKFORWARD = "hyperliquid_walkforward_results.json"

WALKFORWARD_CANDIDATES = ["ETH", "SOL", "OP", "LINK"]  # sobreviventes do split IS/OOS inicial


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


def _compute_diffs_with_ts(sym, start_ms):
    """Retorna lista de (timestamp_ms, diff_bps) -- mesma logica de alinhamento HL(hourly)
    vs Binance(8h) usada no screening, mas preservando o timestamp pra permitir bucketing
    em folds temporais (walk-forward)."""
    binance_sym = f"{sym}USDT"
    hl_hist = hl_funding_history(sym, start_ms)
    bn_hist = binance_funding_history(binance_sym, start_ms)
    if len(hl_hist) < 10 or len(bn_hist) < 10:
        return []
    out = []
    for bn in bn_hist:
        window_start = bn["time"] - 8 * 3600 * 1000
        hl_in_window = [h["rate"] for h in hl_hist if window_start < h["time"] <= bn["time"]]
        if not hl_in_window:
            continue
        hl_accum_bps = sum(hl_in_window) * 10000
        bn_bps = bn["rate"] * 10000
        out.append((bn["time"], hl_accum_bps - bn_bps))
    return out


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
        try:
            diffs_bps = [d for _, d in _compute_diffs_with_ts(sym, start_ms)]
        except Exception as e:
            print(f"  {sym}: erro ao buscar historico ({e})")
            continue

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


def run_walkforward_validation(days=90, fold_days=7, symbols=None):
    """Walk-forward multi-janela (mesma unidade de 7d que o D9 usou pra validar: "0% das
    janelas 7d lucrativas"). 1 unico split IS/OOS (run_funding_scan) e fraco -- aqui a
    direcao e decidida usando SOMENTE o fold anterior (k), aplicada de verdade no fold
    seguinte (k+1), deslizando por todo o periodo -- sem look-ahead.

    Custo: modelado como posicao MANTIDA (nao fechada/reaberta toda semana) -- so paga
    round-trip (19bps) na entrada inicial, EXIT final, e quando a direcao realmente VIRA
    (flip = fechar+abrir de novo). Cobrar 19bps TODA semana (mesmo sem trocar de lado)
    seria uma simulacao de estrategia errada (puniria um sinal estavel tipo LINK, que na
    pratica nunca flipa de sinal em 13 semanas, tanto quanto um sinal ruidoso tipo OP)."""
    symbols = symbols or WALKFORWARD_CANDIDATES
    print("=" * 90)
    print(f"D55a walk-forward -- folds de {fold_days}d, direcao decidida no fold anterior, "
          f"testada no seguinte (sem look-ahead). Custo so na entrada/saida/flip de direcao.")
    print("=" * 90)

    start_ms = int((time.time() - days * 86400) * 1000)
    fold_ms = fold_days * 86400 * 1000
    results = []

    for sym in symbols:
        try:
            pairs = _compute_diffs_with_ts(sym, start_ms)
        except Exception as e:
            print(f"  {sym}: erro ao buscar historico ({e})")
            continue
        if len(pairs) < 20:
            print(f"  {sym}: historico insuficiente (N={len(pairs)})")
            continue

        first_ts = pairs[0][0]
        folds = {}
        for ts, diff in pairs:
            idx = (ts - first_ts) // fold_ms
            folds.setdefault(idx, []).append(diff)
        fold_idxs = sorted(i for i in folds if len(folds[i]) >= 5)

        if len(fold_idxs) < 4:
            print(f"  {sym}: poucos folds validos (N={len(fold_idxs)})")
            continue

        # Fold 0 so forma o sinal inicial (nao ha posicao pra render P&L nele ainda).
        position = 1 if sum(folds[fold_idxs[0]]) > 0 else -1
        weekly_pnl = []  # P&L bruto (sem custo) de cada fold, ja com sinal da posicao vigente
        n_flips = 0
        for prev_idx, cur_idx in zip(fold_idxs, fold_idxs[1:]):
            weekly_pnl.append(sum(folds[cur_idx]) * position)
            new_position = 1 if sum(folds[cur_idx]) > 0 else -1
            if new_position != position:
                n_flips += 1
                position = new_position

        total_cost = FUNDING_ARB_ROUNDTRIP_BPS * (1 + n_flips)  # entrada+saida (=1 RT) + 1 RT por flip
        gross_total = sum(weekly_pnl)
        net_total = gross_total - total_cost
        # bootstrap no P&L semanal BRUTO, custo total debitado uma vez do agregado (custo
        # nao e i.i.d. por semana, e concentrado nos eventos de flip)
        lo_gross, mean_gross, hi_gross = bootstrap_ci(weekly_pnl)
        lo_net, hi_net = lo_gross * len(weekly_pnl) - total_cost, hi_gross * len(weekly_pnl) - total_cost
        n_win = sum(1 for p in weekly_pnl if p > 0)
        win_rate = n_win / len(weekly_pnl) * 100
        confirms = net_total > 0 and lo_net > 0

        results.append({
            "symbol": sym, "n_folds": len(fold_idxs), "n_weeks_held": len(weekly_pnl),
            "n_flips": n_flips, "win_rate_pct": win_rate, "gross_total_bps": gross_total,
            "total_cost_bps": total_cost, "net_total_bps": net_total,
            "net_ci95": [lo_net, hi_net], "confirms": confirms,
        })
        tag = "CONFIRMA (net>0, IC95% nao cruza zero)" if confirms else "NAO confirma"
        print(f"  {sym:6s} folds={len(fold_idxs):2d} semanas_seguradas={len(weekly_pnl):2d} "
              f"flips={n_flips} win_rate={win_rate:5.1f}% ({n_win}/{len(weekly_pnl)}) "
              f"gross={gross_total:+7.2f}bps custo={total_cost:5.1f}bps "
              f"net={net_total:+7.2f}bps CI95=[{lo_net:+.2f},{hi_net:+.2f}] -> {tag}")

    with open(RESULTS_FILE_WALKFORWARD, "w") as f:
        json.dump(results, f, indent=2)

    confirmed = [r for r in results if r["confirms"]]
    print("\n" + "=" * 90)
    print(f"RESUMO walk-forward: {len(confirmed)}/{len(results)} confirmam com folds de {fold_days}d "
          f"(vs {len(symbols)} candidatos testados), custo so em entrada/saida/flip")
    if confirmed:
        print("Confirmados:", ", ".join(f"{r['symbol']}(net={r['net_total_bps']:+.1f}bps, "
                                         f"{r['n_flips']} flips)" for r in confirmed))
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
    ap.add_argument("--mode", choices=["funding", "walkforward", "divergence", "both"], default="both")
    ap.add_argument("--funding-days", type=int, default=30)
    ap.add_argument("--fold-days", type=int, default=7)
    ap.add_argument("--symbols", nargs="*", default=None,
                     help="Restringe walkforward a esses simbolos (default: candidatos D55a)")
    ap.add_argument("--divergence-duration-s", type=int, default=600)
    ap.add_argument("--divergence-interval-s", type=float, default=3.0)
    args = ap.parse_args()

    if args.mode in ("funding", "both"):
        run_funding_scan(days=args.funding_days)
    if args.mode == "walkforward":
        run_walkforward_validation(days=args.funding_days, fold_days=args.fold_days, symbols=args.symbols)
    if args.mode in ("divergence", "both"):
        print()
        run_divergence_scan(duration_s=args.divergence_duration_s,
                             interval_s=args.divergence_interval_s)


if __name__ == "__main__":
    main()
