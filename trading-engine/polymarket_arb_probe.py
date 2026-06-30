"""Cacador de arbitragem de REBALANCEAMENTO na Polymarket (read-only, NAO opera).

Por que existe
--------------
O `docs/polymarket_arb_report.md` delimita as teses de arbitragem na Polymarket. A tese
PA1/PA2 (Market Rebalancing: Sigma "YES" != 1) e a unica risk-free POR DESENHO — mas a
literatura mostra que os gaps exibidos sao sniped em 2-7s e quase sempre SUB-CUSTO depois
da taxa/spread/profundidade. Este modulo aplica a MESMA disciplina que matou o Oraculo e
refutou a H3: mede o edge com PROFUNDIDADE EXECUTAVEL (anda o livro, nao usa midpoint),
desconta a BARRA DE CUSTO e so confirma o que PERSISTE. Ele caca e REGISTRA; armar capital
e um passo separado (e exige assinatura EIP-712, que este script nao faz de proposito).

Uso
---
    # Offline (sem rede) — prova que a matematica e os gates funcionam:
    python polymarket_arb_probe.py --selftest

    # Ao vivo (dados PUBLICOS, sem auth): conjunto completo de "YES" de um mercado.
    # Para um binario simples passe os 2 clobTokenIds [YES, NO]:
    python polymarket_arb_probe.py --token-ids <YES_ID>,<NO_ID> --complete-set --taker-rate 0.0

    # Resolve os token ids de um mercado pela Gamma API (por slug):
    python polymarket_arb_probe.py --market-slug <slug> --taker-rate 0.0

Evidencia bruta: logs/polymarket_arb/opportunities.jsonl  (gitignored)
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from polymarket_arb_stats import (
    max_fillable_set,
    net_edge_bps,
    rebalancing_long_edge,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = {"User-Agent": "poly-arb-probe/1.0 (research; read-only)"}


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_book(token_id, timeout=10):
    """Livro de ofertas publico da CLOB. Retorna (asks_asc, bids_desc) como (price, size)."""
    data = _get(f"{CLOB}/book?token_id={urllib.parse.quote(str(token_id))}", timeout=timeout)
    asks = [(float(l["price"]), float(l["size"])) for l in data.get("asks", [])]
    bids = [(float(l["price"]), float(l["size"])) for l in data.get("bids", [])]
    asks.sort(key=lambda x: x[0])           # comprar: menor preco primeiro
    bids.sort(key=lambda x: x[0], reverse=True)  # vender: maior preco primeiro
    return asks, bids


def resolve_market_tokens(slug, timeout=10):
    """Resolve clobTokenIds de um mercado pela Gamma API (por slug)."""
    data = _get(f"{GAMMA}/markets?slug={urllib.parse.quote(slug)}", timeout=timeout)
    if isinstance(data, dict):
        data = data.get("data", []) or [data]
    if not data:
        raise RuntimeError(f"mercado nao encontrado para slug={slug}")
    m = data[0]
    raw = m.get("clobTokenIds") or "[]"
    token_ids = json.loads(raw) if isinstance(raw, str) else raw
    return {
        "question": m.get("question"),
        "negRisk": bool(m.get("negRisk", False)),
        "token_ids": token_ids,
    }


def evidence_path(cfg_path):
    if cfg_path:
        return cfg_path
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "polymarket_arb")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "opportunities.jsonl")


def log_evidence(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def evaluate_set(books_asks, taker_rate, fixed_cost, max_notional):
    """Mede o edge LONG executavel de um conjunto completo de "YES"."""
    cap = max_fillable_set(books_asks)
    if cap <= 0:
        return None
    qty = cap if max_notional <= 0 else min(cap, max_notional)
    r = rebalancing_long_edge(books_asks, qty=qty, taker_rate=taker_rate, fixed_cost=fixed_cost)
    if r["net"] is None:
        return None
    notional = r["qty"] * (r["sum_ask"] or 0.0)
    r["bps"] = net_edge_bps(r["net"], notional) if notional else 0.0
    r["depth_qty"] = cap
    return r


class Episode:
    """Gate anti-variancia: confirma so apos `persistence` polls net-positivos seguidos;
    emite 1x por episodio (igual ao monitor de anomalias)."""

    def __init__(self, persistence):
        self.persistence = persistence
        self.streak = 0
        self.emitted = False

    def update(self, net_positive):
        if net_positive:
            self.streak += 1
        else:
            self.streak = 0
            self.emitted = False
        return self.streak >= self.persistence and not self.emitted

    def mark_emitted(self):
        self.emitted = True


def run_live(args):
    ev_path = evidence_path(args.evidence)
    if args.market_slug:
        info = resolve_market_tokens(args.market_slug)
        token_ids = info["token_ids"]
        label = info["question"] or args.market_slug
        print(f"[gamma] {label} | negRisk={info['negRisk']} | {len(token_ids)} legs")
    else:
        token_ids = [t.strip() for t in args.token_ids.split(",") if t.strip()]
        label = args.label or f"set:{len(token_ids)}legs"

    if not token_ids:
        print("nada para vigiar: passe --token-ids ou --market-slug")
        return 2

    print(f"vigiando {len(token_ids)} pernas | taker={args.taker_rate} fixed=${args.fixed_cost} "
          f"persistence={args.persistence} | evidencia: {ev_path}")
    ep = Episode(args.persistence)
    t0 = time.time()
    polls = 0
    while True:
        try:
            books_asks = []
            for tid in token_ids:
                asks, _ = fetch_book(tid, timeout=args.timeout)
                books_asks.append(asks)
            r = evaluate_set(books_asks, args.taker_rate, args.fixed_cost, args.max_notional)
        except Exception as e:
            print(f"[warn] poll falhou: {e}")
            time.sleep(args.cycle)
            continue

        polls += 1
        if r is None:
            print(f"[{polls}] profundidade insuficiente em alguma perna (sem veredito)")
            ep.update(False)
        else:
            net_pos = r["net"] > 0
            tag = "+EV" if net_pos else "sub-custo"
            print(f"[{polls}] Sigma_ask={r['sum_ask']:.4f} net=${r['net']:.4f} "
                  f"({r['bps']:.1f}bps) depth={r['depth_qty']:.0f} streak={ep.streak} [{tag}]")
            if ep.update(net_pos):
                rec = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "label": label,
                    "legs": len(token_ids),
                    "sum_ask": r["sum_ask"],
                    "net": r["net"],
                    "bps": r["bps"],
                    "qty": r["qty"],
                    "depth_qty": r["depth_qty"],
                    "taker_rate": args.taker_rate,
                    "fixed_cost": args.fixed_cost,
                    "persistence": args.persistence,
                }
                log_evidence(ev_path, rec)
                ep.mark_emitted()
                print(f"  >>> CONFIRMADO (persistiu {args.persistence}x): net=${r['net']:.4f} -> evidencia gravada")

        if args.max_runtime and (time.time() - t0) >= args.max_runtime:
            print(f"max-runtime atingido ({polls} polls).")
            return 0
        time.sleep(args.cycle)


def selftest():
    """Prova offline: a matematica + os gates funcionam sem rede."""
    print("== SELFTEST (offline) ==")
    n = 0

    # 1) arb long real (soma 0.97), profundidade 100, sem taxa
    books = [[(0.42, 100)], [(0.55, 100)]]
    r = evaluate_set(books, taker_rate=0.0, fixed_cost=0.0, max_notional=0)
    assert r and r["net"] > 0 and abs(r["sum_ask"] - 0.97) < 1e-9, r
    print(f"  ok  arb long detectado: net=${r['net']:.2f} ({r['bps']:.0f}bps)"); n += 1

    # 2) mesmo gap morto pela barra de custo (taker 1.5%)
    books2 = [[(0.50, 100)], [(0.495, 100)]]
    r2 = evaluate_set(books2, taker_rate=0.015, fixed_cost=0.0, max_notional=0)
    assert r2 and r2["net"] < 0, r2
    print(f"  ok  gap sub-custo refutado: net=${r2['net']:.2f}"); n += 1

    # 3) profundidade insuficiente -> sem veredito
    books3 = [[(0.42, 5)], [(0.55, 100)]]
    r3 = evaluate_set(books3, 0.0, 0.0, max_notional=10)
    assert r3 is None or r3["net"] is None or r3["depth_qty"] == 5
    print("  ok  profundidade rasa tratada"); n += 1

    # 4) gate anti-variancia: so emite apos persistencia, 1x por episodio
    ep = Episode(persistence=3)
    seq = [True, True, True, True, False, True, True, True]
    emits = [ep.update(x) and (ep.mark_emitted() or True) for x in seq]
    assert emits == [False, False, True, False, False, False, False, True], emits
    print("  ok  gate de persistencia (emite 1x/episodio)"); n += 1

    print(f"\n{n}/4 checagens passaram.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="Cacador read-only de arbitragem de rebalanceamento na Polymarket.")
    p.add_argument("--selftest", action="store_true", help="roda checagens offline e sai")
    p.add_argument("--token-ids", default="", help="clobTokenIds separados por virgula (conjunto completo de YES, ou [YES,NO])")
    p.add_argument("--market-slug", default="", help="resolve token ids pela Gamma API")
    p.add_argument("--complete-set", action="store_true", help="(doc) os ids formam um conjunto mutuamente exclusivo e exaustivo")
    p.add_argument("--label", default="", help="rotulo para a evidencia")
    p.add_argument("--taker-rate", type=float, default=0.0, help="taxa de taker (fracao do notional). Polymarket historicamente ~0; configure se mudar")
    p.add_argument("--fixed-cost", type=float, default=0.0, help="custo fixo por rodada (gas/bridge USDC)")
    p.add_argument("--max-notional", type=float, default=0.0, help="teto de unidades por perna (0 = usa profundidade disponivel)")
    p.add_argument("--persistence", type=int, default=3, help="polls net-positivos seguidos antes de confirmar")
    p.add_argument("--cycle", type=float, default=3.0, help="segundos entre polls")
    p.add_argument("--timeout", type=float, default=10.0, help="timeout HTTP")
    p.add_argument("--max-runtime", type=float, default=0.0, help="segundos totais (0 = infinito)")
    p.add_argument("--evidence", default="", help="caminho do JSONL de evidencia")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    return run_live(args)


if __name__ == "__main__":
    raise SystemExit(main())
