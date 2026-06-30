"""PA5 - Sonda de latencia/staleness: Polymarket BTC Up/Down (5m/15m) vs Binance.

Pergunta decisiva (a H3 INVERTIDA)
----------------------------------
A H3 morreu porque a Deriv reprecifica o fill FRESCO. Aqui a pergunta e outra: o LIVRO
CLOB da Polymarket fica STALE perto do settlement de um evento que a Binance ja praticamente
decidiu? Se nos ultimos segundos der pra comprar o lado correto (direcao ja realizada na
Binance) por um preco que ainda nao convergiu para ~1, ha edge estrutural.

Caveat central (risco da tese): a Polymarket resolve por **Chainlink**, nao pela Binance.
Binance e so o sinal GRATIS. A divergencia Binance x Chainlink (H5 da literatura) e basis/
oraculo e entra como ruido/risco — esta sonda usa Binance como proxy e marca isso.

ESTE SCRIPT NAO OPERA. E read-only + PAPER (a Polymarket exige assinatura EIP-712, fora
de escopo por decisao de projeto). Ele mede o edge que SERIA capturado, liquido de custo,
com o metodo A/B aligned-vs-anti da H3 (a diferenca cancela custo/basis comuns).

Uso
---
    python polymarket_lag_probe.py --selftest
    python polymarket_lag_probe.py --discover btc-updown-5m
    # lead-lag do feed (Binance x preco do token Up), read-only:
    python polymarket_lag_probe.py --slug <btc-updown-5m-...> --seconds 120 --grid-ms 500
    # A/B PAPER nos ultimos 30s da janela (settla contra Binance begin/close):
    python polymarket_lag_probe.py --slug <btc-updown-5m-...> --paper-ab --final-s 30 --sample-s 2
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from polymarket_arb_stats import (
    best_lag,
    boot_diff_ci,
    cross_corr_profile,
    updown_paper_pnl,
    wilson_interval,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BINANCE = "https://api.binance.com"
UA = {"User-Agent": "poly-lag-probe/1.0 (research; read-only)"}


def _get(url, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_horizon_min(slug):
    """Extrai o horizonte em minutos do slug (...-5m-... / ...-15m-...)."""
    for part in slug.split("-"):
        if part.endswith("m") and part[:-1].isdigit():
            return int(part[:-1])
    return 0


def resolve_market(slug, timeout=10):
    data = _get(f"{GAMMA}/markets?slug={urllib.parse.quote(slug)}", timeout=timeout)
    rows = data if isinstance(data, list) else data.get("data", [])
    if not rows:
        raise RuntimeError(f"mercado nao encontrado: {slug}")
    m = rows[0]
    raw = m.get("clobTokenIds") or "[]"
    tokens = json.loads(raw) if isinstance(raw, str) else raw
    out_raw = m.get("outcomes") or '["Up","Down"]'
    outcomes = json.loads(out_raw) if isinstance(out_raw, str) else out_raw
    end = datetime.fromisoformat(m["endDate"].replace("Z", "+00:00"))
    return {
        "question": m.get("question"),
        "outcomes": outcomes,        # ["Up","Down"]
        "tokens": tokens,            # [up_token, down_token]
        "end": end,
        "horizon_min": parse_horizon_min(slug),
        "neg": bool(m.get("negRisk", False)),
    }


def best_ask(token_id, timeout=10):
    d = _get(f"{CLOB}/book?token_id={urllib.parse.quote(str(token_id))}", timeout=timeout)
    asks = [(float(l["price"]), float(l["size"])) for l in d.get("asks", [])]
    bids = [(float(l["price"]), float(l["size"])) for l in d.get("bids", [])]
    a = min((p for p, _ in asks), default=None)
    b = max((p for p, _ in bids), default=None)
    mid = (a + b) / 2.0 if (a is not None and b is not None) else (a or b)
    return a, b, mid


def binance_price(timeout=10):
    return float(_get(f"{BINANCE}/api/v3/ticker/price?symbol=BTCUSDT", timeout=timeout)["price"])


def binance_open_at(epoch_s, timeout=10):
    """Preco de abertura do candle de 1m que contem `epoch_s` (referencia 'begin')."""
    ms = int(epoch_s // 60 * 60 * 1000)
    k = _get(f"{BINANCE}/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={ms}&limit=1", timeout=timeout)
    return float(k[0][1]) if k else None


def discover(substr, timeout=15):
    q = urllib.parse.urlencode({"closed": "false", "limit": 200, "order": "startDate", "ascending": "false"})
    data = _get(f"{GAMMA}/markets?{q}", timeout=timeout)
    rows = data if isinstance(data, list) else data.get("data", [])
    hits = [m for m in rows if substr.lower() in (m.get("slug") or "").lower()]
    print(f"{len(hits)} mercados ativos casando '{substr}':")
    for m in hits[:25]:
        print(f"  {m.get('slug'):42}  end={m.get('endDate')}")
    return 0


def run_leadlag(slug, seconds, grid_ms, max_lag_ms):
    mk = resolve_market(slug)
    up_token = mk["tokens"][0]
    print(f"[{slug}] {mk['question']} | horizonte={mk['horizon_min']}m | fim={mk['end'].isoformat()}")
    print(f"Capturando {seconds}s (Binance BTCUSDT vs preco token Up)...")
    bs, ps = [], []   # (ts, price)
    t0 = time.time()
    while time.time() - t0 < seconds:
        now = time.time()
        try:
            bp = binance_price()
            _, _, mid = best_ask(up_token)
            if mid is not None:
                bs.append((now, bp)); ps.append((now, mid))
        except Exception as e:
            print(f"  ! poll: {e}")
        time.sleep(grid_ms / 1000.0)

    if len(bs) < 10:
        print("Dados insuficientes."); return 1
    # reamostra no grid comum por retorno log
    def returns(series):
        return [series[i][1] / series[i - 1][1] - 1.0 for i in range(1, len(series))]
    br, pr = returns(bs), returns(ps)
    n = min(len(br), len(pr))
    prof = cross_corr_profile(br[:n], pr[:n], max_lag=max(1, max_lag_ms // grid_ms))
    lag, corr = best_lag(prof)
    lag_ms = lag * grid_ms
    print(f"\nAmostras: binance={len(bs)} poly={len(ps)} | grid={grid_ms}ms")
    print(f"Correlacao maxima {corr:.3f} em lag {lag_ms:+d}ms (lag>0 = Polymarket ATRASA a Binance)")
    if lag_ms > grid_ms and corr > 0.15:
        print(">>> SINAL: livro da Polymarket reflete a Binance com atraso. Rodar o A/B paper "
              "(--paper-ab) nos ultimos segundos da janela para medir se o atraso e EXPLORAVEL.")
    elif corr <= 0.1:
        print(">>> Correlacao fraca (mercado calmo / poll lento). Rodar em janela volatil ou com grid menor.")
    else:
        print(">>> Sem atraso claro: livro acompanha a Binance. Edge de latencia improvavel nesta rota.")
    return 0


def run_paper_ab(args):
    import random
    mk = resolve_market(args.slug)
    up_token, down_token = mk["tokens"][0], mk["tokens"][1]
    end = mk["end"]
    begin_epoch = end.timestamp() - mk["horizon_min"] * 60
    begin_ref = binance_open_at(begin_epoch)
    print(f"[{args.slug}] {mk['question']}")
    print(f"  fim={end.isoformat()} | begin~={datetime.fromtimestamp(begin_epoch, timezone.utc).isoformat()} "
          f"| begin_ref(Binance)={begin_ref}")
    print(f"  PAPER A/B nos ultimos {args.final_s}s | taker={args.taker_rate} fixed=${args.fixed_cost}")
    print("  (resolver real = Chainlink; usamos Binance como proxy -> basis/oraculo e risco)")
    if begin_ref is None:
        print("  ! sem referencia de begin (klines). Abortando."); return 1

    rng = random.Random(args.seed)
    trades = []
    last = 0.0
    while True:
        now = time.time()
        secs_left = end.timestamp() - now
        if secs_left <= args.guard_s:
            break
        if secs_left > args.final_s:
            time.sleep(min(1.0, secs_left - args.final_s)); continue
        if now - last < args.sample_s:
            time.sleep(0.1); continue
        try:
            bp = binance_price()
            d = bp - begin_ref
            if abs(d) < args.min_move:
                last = now; continue
            move_dir = 1 if d > 0 else -1
            if rng.random() < 0.5:
                chosen, tag = move_dir, "aligned"
            else:
                chosen, tag = -move_dir, "anti"
            side = "Up" if chosen > 0 else "Down"
            token = up_token if chosen > 0 else down_token
            ask, _, _ = best_ask(token)
            if ask is None:
                last = now; continue
            trades.append({"tag": tag, "side": side, "ask": ask, "binance": bp, "move": d})
            print(f"  [{tag:7}] {side:4} ask={ask:.3f} | binance={bp:.1f} (move {d:+.1f}) | left={secs_left:.0f}s")
            last = now
        except Exception as e:
            print(f"  ! sample: {e}"); time.sleep(0.5)

    # settla contra o close (Binance como proxy do Chainlink)
    try:
        close_px = binance_price()
    except Exception:
        close_px = begin_ref
    outcome_up = close_px >= begin_ref
    print(f"\n  close(Binance)={close_px:.1f} vs begin={begin_ref:.1f} -> resultado={'Up' if outcome_up else 'Down'}")
    for t in trades:
        won = (t["side"] == "Up") == outcome_up
        t["won"] = won
        t["pnl"] = updown_paper_pnl(t["ask"], won, args.taker_rate, args.fixed_cost)

    print("=" * 78)
    print(f"Paper trades: {len(trades)}")
    for grp in ("aligned", "anti"):
        g = [t for t in trades if t["tag"] == grp]
        if not g:
            continue
        pnl = [t["pnl"] for t in g]
        wins = sum(1 for t in g if t["won"])
        lo, hi = wilson_interval(wins, len(g))
        mean = sum(pnl) / len(g)
        print(f"  {grp:8}: n={len(g):3d} | WR={wins/len(g)*100:5.1f}% [{lo*100:.0f},{hi*100:.0f}] "
              f"| P&L medio=${mean:+.4f} | total=${sum(pnl):+.4f}")
    al = [t["pnl"] for t in trades if t["tag"] == "aligned"]
    an = [t["pnl"] for t in trades if t["tag"] == "anti"]
    if al and an:
        ma, mn = sum(al) / len(al), sum(an) / len(an)
        print(f">>> aligned={ma:+.4f} | anti={mn:+.4f} | aligned-anti=${ma-mn:+.4f}/trade")
        if len(al) >= 5 and len(an) >= 5:
            lo, hi = boot_diff_ci(al, an)
            verdict = ("edge direcional comprovado" if lo > 0 else
                       "aligned PIOR" if hi < 0 else "cruza zero (sem edge comprovado)")
            print(f"    IC95% (aligned-anti): [{lo:+.4f}, {hi:+.4f}] -> {verdict}")
        if ma > 0:
            print("    >>> LUCRATIVO no paper: aligned liquido > 0. Validar amostra maior + divergencia "
                  "Chainlink antes de QUALQUER capital (e exige executor EIP-712, fora deste script).")
        else:
            print("    >>> NAO LUCRATIVO: aligned liquido <= 0 -> mesmo padrao H1/H3 (sinal real, sub-custo).")
    else:
        print("(amostra insuficiente para A/B — rode em janela ativa com mais samples)")
    print("=" * 78)
    return 0


def selftest():
    print("== SELFTEST PA5 (offline) ==")
    n = 0
    # 1) cross-corr acha o atraso
    ref = [0.0, 1.0, -1.0, 0.5, -0.5, 1.0, -1.0, 0.2, -0.2, 0.8, -0.8, 0.3]
    tgt = [0.0, 0.0] + ref[:-2]
    lag, corr = best_lag(cross_corr_profile(ref, tgt, 4))
    assert lag == 2 and corr > 0.9, (lag, corr)
    print(f"  ok  lead-lag detecta atraso de 2 passos (corr {corr:.2f})"); n += 1
    # 2) paper pnl
    assert abs(updown_paper_pnl(0.4, True) - 0.6) < 1e-9
    assert abs(updown_paper_pnl(0.4, False) + 0.4) < 1e-9
    print("  ok  P&L paper Up/Down (win/loss)"); n += 1
    # 3) A/B: aligned ganha quando o livro esta stale (ask < 1 do lado certo)
    aligned = [updown_paper_pnl(0.55, True) for _ in range(18)] + [updown_paper_pnl(0.55, False) for _ in range(2)]
    anti = [updown_paper_pnl(0.45, False) for _ in range(18)] + [updown_paper_pnl(0.45, True) for _ in range(2)]
    lo, hi = boot_diff_ci(aligned, anti, n_boot=3000, seed=7)
    assert lo > 0, (lo, hi)
    print(f"  ok  A/B isola edge (IC95% aligned-anti lo={lo:+.3f} > 0)"); n += 1
    # 4) horizon parse
    assert parse_horizon_min("btc-updown-5m-1782865800") == 5
    assert parse_horizon_min("eth-updown-15m-1782865800") == 15
    print("  ok  parse de horizonte do slug"); n += 1
    print(f"\n{n}/4 checagens passaram.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="PA5: sonda read-only de latencia/staleness Polymarket Up/Down x Binance (paper).")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--discover", default="", help="lista mercados ativos cujo slug casa o substring")
    p.add_argument("--slug", default="", help="slug do mercado (ex.: btc-updown-5m-<epoch>)")
    p.add_argument("--seconds", type=int, default=120, help="modo lead-lag: duracao da captura")
    p.add_argument("--grid-ms", type=int, default=500, help="modo lead-lag: intervalo de poll")
    p.add_argument("--max-lag-ms", type=int, default=3000, help="modo lead-lag: lag maximo testado")
    p.add_argument("--paper-ab", action="store_true", help="roda o A/B paper nos ultimos segundos da janela")
    p.add_argument("--final-s", type=float, default=30.0, help="A/B: janela final (s) para amostrar trades")
    p.add_argument("--sample-s", type=float, default=2.0, help="A/B: intervalo entre amostras")
    p.add_argument("--guard-s", type=float, default=1.0, help="A/B: para de amostrar X s antes do fim")
    p.add_argument("--min-move", type=float, default=5.0, help="A/B: |move| minimo na Binance (USD) p/ amostrar")
    p.add_argument("--taker-rate", type=float, default=0.0)
    p.add_argument("--fixed-cost", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=42)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.discover:
        return discover(args.discover)
    if not args.slug:
        print("informe --slug (ou --discover / --selftest)."); return 2
    if args.paper_ab:
        return run_paper_ab(args)
    return run_leadlag(args.slug, args.seconds, args.grid_ms, args.max_lag_ms)


if __name__ == "__main__":
    raise SystemExit(main())
