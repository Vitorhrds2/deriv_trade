"""PA1-PA4 Polymarket arbitrage scan — read-only, no credentials, no capital.

Four hypotheses, all testable with public Gamma + CLOB APIs:

PA1 — New market sniping: freshly opened markets may have mispriced books before
      bots converge prices. Scan: monitor newly created markets, measure how fast
      ask prices converge to "reasonable" levels (vs Binance for BTC markets).

PA2 — Cross-market consistency: logically related markets (same underlying BTC,
      different window durations) should have consistent implied probabilities.
      If 5m "Up" costs 60¢ and the 15m "Up" (containing the same 5m) costs 30¢,
      there's an inconsistency. Scan: compare implied probs across overlapping windows.

PA3 — Multi-outcome arbitrage: markets with N mutually-exclusive outcomes where
      sum of best asks < $1.00 = free money (buy all outcomes, guaranteed profit).
      Scan: fetch all active multi-outcome markets, sum best asks, check < $1.00.

PA4 — Near-resolution convergence: as a market approaches settlement, the winning
      side should converge to ~$1.00 and losing to ~$0.00. If the book lags behind
      the realized outcome (Binance price vs window open), there's a stale-book
      window. This is PA5's cousin but tests a different mechanism: not "stale book
      in last 30s" but "slow convergence in last minutes" — a wider window.

Usage:
    python polymarket_arb_scan.py --duration-min 30 --interval-s 10
    python polymarket_arb_scan.py --pa3-only          # just multi-outcome scan
    python polymarket_arb_scan.py --pa4 --substr btc-updown-5m --final-min 5
"""
import argparse
import asyncio
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BINANCE = "https://api.binance.com"
UA = {"User-Agent": "polymarket-arb-scan/1.0 (research; read-only)"}


def _get(url: str, timeout: int = 10) -> dict | list:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# PA3: Multi-outcome arbitrage
# ---------------------------------------------------------------------------

@dataclass
class MultiOutcomeResult:
    condition_id: str
    question: str
    slug: str
    n_outcomes: int
    best_asks: list = field(default_factory=list)
    sum_asks: float = 0.0
    arb_bps: float = 0.0  # (1.0 - sum_asks) * 10000
    outcomes: list = field(default_factory=list)
    error: Optional[str] = None


def fetch_clob_book(token_id: str, timeout: int = 10) -> dict:
    return _get(f"{CLOB}/book?token_id={urllib.parse.quote(token_id)}", timeout=timeout)


def best_ask_price(token_id: str) -> Optional[float]:
    """Returns best (lowest) ask price for a token, or None if no asks."""
    book = fetch_clob_book(token_id)
    asks = book.get("asks", [])
    if not asks:
        return None
    return min(float(level["price"]) for level in asks)


def best_bid_price(token_id: str) -> Optional[float]:
    """Returns best (highest) bid price for a token, or None if no bids."""
    book = fetch_clob_book(token_id)
    bids = book.get("bids", [])
    if not bids:
        return None
    return max(float(level["price"]) for level in bids)


def scan_pa3_multi_outcome(max_markets: int = 100) -> list:
    """Scan all active multi-outcome markets for sum(asks) < $1.00."""
    results = []

    # Fetch active markets from Gamma
    params = {"limit": str(max_markets), "active": "true", "closed": "false"}
    url = f"{GAMMA}/markets?{urllib.parse.urlencode(params)}"
    try:
        markets = _get(url, timeout=15)
    except Exception as e:
        print(f"  [PA3] Erro buscando mercados: {e}")
        return results

    if isinstance(markets, dict):
        markets = markets.get("data", [])

    for m in markets:
        raw_tokens = m.get("clobTokenIds") or "[]"
        tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
        if not tokens or len(tokens) < 2:
            continue

        raw_outcomes = m.get("outcomes") or "[]"
        outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes

        condition_id = m.get("conditionId", m.get("id", "?"))
        question = m.get("question", "?")[:80]
        slug = m.get("slug", "?")

        result = MultiOutcomeResult(
            condition_id=condition_id,
            question=question,
            slug=slug,
            n_outcomes=len(tokens),
            outcomes=outcomes,
        )

        try:
            asks = []
            for token_id in tokens:
                ask = best_ask_price(token_id)
                if ask is not None:
                    asks.append(ask)
                else:
                    asks.append(None)

            result.best_asks = asks
            valid_asks = [a for a in asks if a is not None]

            if len(valid_asks) == len(tokens) and len(valid_asks) >= 2:
                result.sum_asks = sum(valid_asks)
                result.arb_bps = (1.0 - result.sum_asks) * 10000
            else:
                result.error = "incomplete book"
        except Exception as e:
            result.error = str(e)[:150]

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# PA2: Cross-market consistency (overlapping BTC windows)
# ---------------------------------------------------------------------------

@dataclass
class CrossMarketResult:
    slug_5m: str
    slug_15m: str
    up_5m: Optional[float]
    up_15m: Optional[float]
    diff_bps: float = 0.0
    error: Optional[str] = None


def find_btc_windows(substr: str = "btc-updown") -> list:
    """Find active BTC Up/Down markets from Gamma.

    Uses the same query pattern as polymarket_lag_probe.py: limit=500,
    order by startDate descending — the default query only returns
    general markets, not short-term crypto windows.
    """
    params = {"closed": "false", "limit": "500", "order": "startDate", "ascending": "false"}
    url = f"{GAMMA}/markets?{urllib.parse.urlencode(params)}"
    try:
        markets = _get(url, timeout=15)
    except Exception as e:
        print(f"  [find_btc_windows] Erro buscando mercados: {e}")
        return []

    if isinstance(markets, dict):
        markets = markets.get("data", [])

    btc_markets = []
    for m in markets:
        slug = m.get("slug", "")
        if substr.lower() in slug.lower():
            raw_tokens = m.get("clobTokenIds") or "[]"
            tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
            if len(tokens) >= 2:
                end_date = m.get("endDate", "")
                start_date = m.get("startDate", m.get("createdAt", ""))
                btc_markets.append({
                    "slug": slug,
                    "tokens": tokens,
                    "endDate": end_date,
                    "startDate": start_date,
                    "question": m.get("question", ""),
                })
    return btc_markets


def parse_horizon_min(slug: str) -> int:
    for part in slug.split("-"):
        if part.endswith("m") and part[:-1].isdigit():
            return int(part[:-1])
    return 0


def scan_pa2_cross_market(substr: str = "btc-updown") -> list:
    """Compare implied probabilities across overlapping BTC windows."""
    markets = find_btc_windows(substr)
    if not markets:
        return []

    # Group by horizon
    by_horizon = {}
    for m in markets:
        h = parse_horizon_min(m["slug"])
        if h > 0:
            by_horizon.setdefault(h, []).append(m)

    results = []
    # Compare 5m vs 15m if both exist
    if 5 in by_horizon and 15 in by_horizon:
        for m5 in by_horizon[5]:
            for m15 in by_horizon[15]:
                try:
                    up5 = best_ask_price(m5["tokens"][0])
                    up15 = best_ask_price(m15["tokens"][0])
                    diff = 0.0
                    if up5 is not None and up15 is not None:
                        diff = (up5 - up15) * 10000  # bps
                    results.append(CrossMarketResult(
                        slug_5m=m5["slug"],
                        slug_15m=m15["slug"],
                        up_5m=up5,
                        up_15m=up15,
                        diff_bps=diff,
                    ))
                except Exception as e:
                    results.append(CrossMarketResult(
                        slug_5m=m5["slug"],
                        slug_15m=m15["slug"],
                        up_5m=None,
                        up_15m=None,
                        error=str(e)[:150],
                    ))
    return results


# ---------------------------------------------------------------------------
# PA4: Near-resolution convergence
# ---------------------------------------------------------------------------

@dataclass
class NearResolutionResult:
    slug: str
    end_date: str
    minutes_to_close: float
    up_ask: Optional[float]
    down_ask: Optional[float]
    binance_price: Optional[float]
    window_open_price: Optional[float]
    binance_move: float = 0.0  # % move from open
    implied_up_prob: float = 0.0
    convergence_bps: float = 0.0  # how far from "correct" price
    error: Optional[str] = None


def get_binance_price(symbol: str = "BTCUSDT") -> Optional[float]:
    try:
        data = _get(f"{BINANCE}/api/v3/ticker/price?symbol={symbol}", timeout=5)
        return float(data["price"])
    except Exception:
        return None


def parse_end_date(end_str: str) -> Optional[datetime]:
    if not end_str:
        return None
    try:
        return datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    except Exception:
        return None


def scan_pa4_near_resolution(substr: str = "btc-updown", final_min: float = 10.0) -> list:
    """Find BTC Up/Down markets closing within final_min minutes, check convergence."""
    markets = find_btc_windows(substr)
    if not markets:
        return []

    now = datetime.now(timezone.utc)
    binance_price = get_binance_price()

    results = []
    for m in markets:
        end_dt = parse_end_date(m.get("endDate", ""))
        if not end_dt:
            continue

        minutes_to_close = (end_dt - now).total_seconds() / 60.0
        if minutes_to_close < 0 or minutes_to_close > final_min:
            continue

        result = NearResolutionResult(
            slug=m["slug"],
            end_date=m.get("endDate", ""),
            minutes_to_close=minutes_to_close,
            binance_price=binance_price,
            window_open_price=None,
        )

        try:
            up_ask = best_ask_price(m["tokens"][0])
            down_ask = best_ask_price(m["tokens"][1]) if len(m["tokens"]) > 1 else None
            result.up_ask = up_ask
            result.down_ask = down_ask

            if up_ask is not None:
                result.implied_up_prob = up_ask

            # We don't know the exact window open price from Gamma API,
            # but we can infer from the question or just measure if
            # the winning side is converging to 1.0
            if up_ask is not None and down_ask is not None:
                # If both asks sum to ~1.0, market is "fair"
                # If winning side ask < 0.90 when close to resolution, book is slow
                total = up_ask + down_ask
                # Convergence: as minutes_to_close -> 0, max(ask) should -> 1.0
                max_ask = max(up_ask, down_ask)
                expected = 1.0 - (minutes_to_close / final_min) * 0.5  # rough expected convergence
                result.convergence_bps = (max_ask - expected) * 10000

        except Exception as e:
            result.error = str(e)[:150]

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# PA1: New market sniping (monitoring)
# ---------------------------------------------------------------------------

@dataclass
class NewMarketResult:
    slug: str
    question: str
    created_at: str
    first_seen_age_s: float
    up_ask: Optional[float]
    down_ask: Optional[float]
    spread_bps: float = 0.0
    error: Optional[str] = None


def scan_pa1_new_markets(substr: str = "btc-updown", max_age_min: float = 10.0) -> list:
    """Find markets created within the last max_age_min minutes."""
    markets = find_btc_windows(substr)
    if not markets:
        return []

    now = datetime.now(timezone.utc)
    results = []

    for m in markets:
        # Gamma doesn't always expose createdAt; use startDate as proxy
        created_str = m.get("startDate", m.get("createdAt", ""))
        created_dt = parse_end_date(created_str)
        if not created_dt:
            continue

        age_s = (now - created_dt).total_seconds()
        if age_s < 0 or age_s > max_age_min * 60:
            continue

        result = NewMarketResult(
            slug=m["slug"],
            question=m.get("question", "")[:80],
            created_at=created_str,
            first_seen_age_s=age_s,
            up_ask=None,
            down_ask=None,
        )

        try:
            up_ask = best_ask_price(m["tokens"][0])
            down_ask = best_ask_price(m["tokens"][1]) if len(m["tokens"]) > 1 else None
            result.up_ask = up_ask
            result.down_ask = down_ask
            if up_ask is not None and down_ask is not None:
                result.spread_bps = abs(up_ask - (1.0 - down_ask)) * 10000
        except Exception as e:
            result.error = str(e)[:150]

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Main scan loop
# ---------------------------------------------------------------------------

async def run_scan(duration_min: float, interval_s: float, pa3_only: bool,
                   pa4_substr: str, pa4_final_min: float):
    duration_s = int(duration_min * 60)
    end_time = time.time() + duration_s
    cycle = 0

    print(f"\n{'='*100}")
    print(f"Polymarket PA1-PA4 Arbitrage Scan — {duration_min:.0f}min, intervalo {interval_s}s")
    print(f"{'='*100}")

    all_pa3 = []
    all_pa2 = []
    all_pa4 = []
    all_pa1 = []

    while time.time() < end_time:
        cycle += 1
        ts = datetime.now(timezone.utc).isoformat()
        print(f"\n--- Ciclo {cycle} @ {ts} ---")

        # PA3: Multi-outcome arb (always run — most likely to find something)
        print("  [PA3] Escaneando multi-outcome markets...")
        pa3_results = await asyncio.get_event_loop().run_in_executor(None, scan_pa3_multi_outcome, 100)
        arb_found = [r for r in pa3_results if r.arb_bps > 0 and not r.error]
        all_pa3.extend(pa3_results)

        if arb_found:
            print(f"  [PA3] {len(arb_found)} mercados com sum(asks) < $1.00!")
            for r in arb_found:
                print(f"    ARB: {r.question[:60]} | sum={r.sum_asks:.4f} | "
                      f"arb={r.arb_bps:.1f}bps | outcomes={r.outcomes}")
        else:
            n_valid = len([r for r in pa3_results if not r.error])
            n_err = len([r for r in pa3_results if r.error])
            if n_valid > 0:
                min_sum = min(r.sum_asks for r in pa3_results if not r.error and r.sum_asks > 0)
                print(f"  [PA3] {n_valid} mercados validos, {n_err} erros. "
                      f"Min sum(asks)={min_sum:.4f} (need <1.0000 for arb)")
            else:
                print(f"  [PA3] {n_err} erros, 0 mercados validos")

        if not pa3_only:
            # PA2: Cross-market consistency
            print("  [PA2] Comparando janelas BTC 5m vs 15m...")
            pa2_results = await asyncio.get_event_loop().run_in_executor(None, scan_pa2_cross_market, "btc-updown")
            all_pa2.extend(pa2_results)
            if pa2_results:
                for r in pa2_results:
                    if r.error:
                        print(f"    [PA2] ERR: {r.slug_5m} vs {r.slug_15m}: {r.error}")
                    else:
                        print(f"    [PA2] {r.slug_5m} up={r.up_5m} vs {r.slug_15m} up={r.up_15m} "
                              f"diff={r.diff_bps:+.1f}bps")
            else:
                print("    [PA2] Nenhum par 5m/15m encontrado")

            # PA4: Near-resolution convergence
            print(f"  [PA4] Buscando mercados BTC fechando em <{pa4_final_min}min...")
            pa4_results = await asyncio.get_event_loop().run_in_executor(
                None, scan_pa4_near_resolution, pa4_substr, pa4_final_min
            )
            all_pa4.extend(pa4_results)
            if pa4_results:
                for r in pa4_results:
                    if r.error:
                        print(f"    [PA4] ERR: {r.slug}: {r.error}")
                    else:
                        print(f"    [PA4] {r.slug} | {r.minutes_to_close:.1f}min to close | "
                              f"up={r.up_ask} down={r.down_ask} | "
                              f"max_ask={max(r.up_ask or 0, r.down_ask or 0):.4f} | "
                              f"BTC=${r.binance_price}")
            else:
                print("    [PA4] Nenhum mercado proximo de resolucao agora")

            # PA1: New market sniping
            print("  [PA1] Buscando mercados criados nos ultimos 10min...")
            pa1_results = await asyncio.get_event_loop().run_in_executor(
                None, scan_pa1_new_markets, "btc-updown", 10.0
            )
            all_pa1.extend(pa1_results)
            if pa1_results:
                for r in pa1_results:
                    if r.error:
                        print(f"    [PA1] ERR: {r.slug}: {r.error}")
                    else:
                        print(f"    [PA1] {r.slug} | age={r.first_seen_age_s:.0f}s | "
                              f"up={r.up_ask} down={r.down_ask} | spread={r.spread_bps:.1f}bps")
            else:
                print("    [PA1] Nenhum mercado novo detectado")

        await asyncio.sleep(interval_s)

    # --- Analysis ---
    print(f"\n{'='*100}")
    print(f"ANALISE — {cycle} ciclos")
    print(f"{'='*100}")

    # PA3 analysis
    valid_pa3 = [r for r in all_pa3 if not r.error and r.sum_asks > 0]
    if valid_pa3:
        arb_count = len([r for r in valid_pa3 if r.arb_bps > 0])
        min_sum = min(r.sum_asks for r in valid_pa3)
        max_sum = max(r.sum_asks for r in valid_pa3)
        mean_sum = sum(r.sum_asks for r in valid_pa3) / len(valid_pa3)
        # Cost threshold: Polymarket taker fee is ~2% (200 bps) on the notional
        # For arb: need sum(asks) < 1.0 - 2 * fee = 1.0 - 0.04 = 0.96
        profitable = len([r for r in valid_pa3 if r.arb_bps > 200])
        print(f"\nPA3 — Multi-outcome arbitrage:")
        print(f"  N={len(valid_pa3)} mercados validos")
        print(f"  sum(asks): min={min_sum:.4f} mean={mean_sum:.4f} max={max_sum:.4f}")
        print(f"  Arb bruto (sum<1.0): {arb_count}/{len(valid_pa3)}")
        print(f"  Arb lucrativo (sum<0.96, pos-fee): {profitable}/{len(valid_pa3)}")
        if arb_count == 0:
            print(f"  >>> SEM EDGE. Nenhum mercado com sum(asks) < $1.00.")
        elif profitable == 0:
            print(f"  >>> SEM EDGE pos-fee. {arb_count} mercados com arb bruto, mas nenhum supera ~200bps de fee.")
        else:
            print(f"  >>> EDGE CANDIDATO! {profitable} mercados com arb lucrativo.")
    else:
        print(f"\nPA3 — Multi-outcome arbitrage: sem dados validos")

    # PA2 analysis
    valid_pa2 = [r for r in all_pa2 if not r.error and r.up_5m is not None and r.up_15m is not None]
    if valid_pa2:
        diffs = [r.diff_bps for r in valid_pa2]
        max_diff = max(abs(d) for d in diffs)
        mean_diff = sum(diffs) / len(diffs)
        print(f"\nPA2 — Cross-market consistency (5m vs 15m):")
        print(f"  N={len(valid_pa2)} pares comparados")
        print(f"  diff: mean={mean_diff:+.1f}bps max|diff|={max_diff:.1f}bps")
        # For PA2: a 5m window inside a 15m window should have Up prob ~ 50% if random walk
        # But they're different windows (not nested), so we expect some divergence
        # The question is whether the divergence is exploitable
        big_diff = len([d for d in diffs if abs(d) > 500])  # >500 bps = 5%
        print(f"  Divergencias > 500bps: {big_diff}/{len(valid_pa2)}")
        if max_diff < 200:
            print(f"  >>> SEM EDGE. Mercados 5m e 15m sao consistentes (diff < 200bps).")
        else:
            print(f"  >>> Divergencias grandes detectadas, mas sem mecanismo claro de exploracao (janelas nao-ninhadas).")
    else:
        print(f"\nPA2 — Cross-market consistency: sem dados validos")

    # PA4 analysis
    valid_pa4 = [r for r in all_pa4 if not r.error and r.up_ask is not None]
    if valid_pa4:
        print(f"\nPA4 — Near-resolution convergence:")
        print(f"  N={len(valid_pa4)} mercados proximos de resolucao")
        for r in valid_pa4:
            max_ask = max(r.up_ask or 0, r.down_ask or 0)
            print(f"    {r.slug} | {r.minutes_to_close:.1f}min | "
                  f"up={r.up_ask} down={r.down_ask} max={max_ask:.4f}")
        # Check if any market has winning side < 0.90 when < 2 min to close
        slow = [r for r in valid_pa4 if r.minutes_to_close < 2.0 and
                max(r.up_ask or 0, r.down_ask or 0) < 0.90]
        if slow:
            print(f"  >>> {len(slow)} mercados com lado vencedor < 0.90 a <2min do close (possivel lentidao)")
        else:
            print(f"  >>> SEM EDGE. Mercados convergem normalmente proximo da resolucao.")
    else:
        print(f"\nPA4 — Near-resolution convergence: sem dados (nenhum mercado proximo ao close)")

    # PA1 analysis
    valid_pa1 = [r for r in all_pa1 if not r.error]
    if valid_pa1:
        print(f"\nPA1 — New market sniping:")
        print(f"  N={len(valid_pa1)} mercados novos detectados")
        for r in valid_pa1:
            print(f"    {r.slug} | age={r.first_seen_age_s:.0f}s | "
                  f"up={r.up_ask} down={r.down_ask} | spread={r.spread_bps:.1f}bps")
        # Check for wide spreads in very young markets
        wide = [r for r in valid_pa1 if r.first_seen_age_s < 60 and r.spread_bps > 500]
        if wide:
            print(f"  >>> {len(wide)} mercados com spread > 500bps nos primeiros 60s (possivel snipe)")
        else:
            print(f"  >>> SEM EDGE. Spreads convergem rapidamente nos novos mercados.")
    else:
        print(f"\nPA1 — New market sniping: sem dados (nenhum mercado novo detectado)")

    # Overall verdict
    print(f"\n{'='*100}")
    print("VEREDITO PRELIMINAR")
    print(f"{'='*100}")

    has_edge = False
    if valid_pa3:
        profitable = len([r for r in valid_pa3 if r.arb_bps > 200])
        if profitable > 0:
            print(f"  PA3: POSSIVEL EDGE — {profitable} mercados com arb lucrativo pos-fee")
            has_edge = True
        else:
            print(f"  PA3: SEM EDGE — nenhum mercado com sum(asks) < $0.96 (pos-fee)")

    if valid_pa2:
        if max(abs(r.diff_bps) for r in valid_pa2) > 500:
            print(f"  PA2: DIVERGENCIA DETECTADA mas sem mecanismo de exploracao claro")
        else:
            print(f"  PA2: SEM EDGE — mercados 5m/15m sao consistentes")

    if valid_pa4:
        slow = [r for r in valid_pa4 if r.minutes_to_close < 2.0 and
                max(r.up_ask or 0, r.down_ask or 0) < 0.90]
        if slow:
            print(f"  PA4: POSSIVEL EDGE — {len(slow)} mercados com convergencia lenta")
            has_edge = True
        else:
            print(f"  PA4: SEM EDGE — mercados convergem normalmente")

    if valid_pa1:
        wide = [r for r in valid_pa1 if r.first_seen_age_s < 60 and r.spread_bps > 500]
        if wide:
            print(f"  PA1: POSSIVEL EDGE — {len(wide)} mercados novos com spread largo")
            has_edge = True
        else:
            print(f"  PA1: SEM EDGE — spreads convergem rapidamente")

    if not has_edge:
        print(f"\n  >>> SEM EDGE em PA1-PA4. Nenhuma hipotese mostra edge exploravel.")

    # Save results
    out = {
        "pa3": [{"question": r.question, "slug": r.slug, "n_outcomes": r.n_outcomes,
                 "sum_asks": r.sum_asks, "arb_bps": r.arb_bps, "error": r.error}
                for r in all_pa3],
        "pa2": [{"slug_5m": r.slug_5m, "slug_15m": r.slug_15m,
                 "up_5m": r.up_5m, "up_15m": r.up_15m, "diff_bps": r.diff_bps, "error": r.error}
                for r in all_pa2],
        "pa4": [{"slug": r.slug, "minutes_to_close": r.minutes_to_close,
                 "up_ask": r.up_ask, "down_ask": r.down_ask, "error": r.error}
                for r in all_pa4],
        "pa1": [{"slug": r.slug, "age_s": r.first_seen_age_s,
                 "up_ask": r.up_ask, "down_ask": r.down_ask, "error": r.error}
                for r in all_pa1],
    }
    with open("polymarket_arb_samples.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nAmostras salvas em polymarket_arb_samples.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-min", type=float, default=30.0)
    parser.add_argument("--interval-s", type=float, default=10.0)
    parser.add_argument("--pa3-only", action="store_true", help="So multi-outcome arb scan")
    parser.add_argument("--pa4-substr", default="btc-updown", help="Substring para PA4")
    parser.add_argument("--pa4-final-min", type=float, default=10.0, help="Janela de close para PA4")
    args = parser.parse_args()

    asyncio.run(run_scan(
        duration_min=args.duration_min,
        interval_s=args.interval_s,
        pa3_only=args.pa3_only,
        pa4_substr=args.pa4_substr,
        pa4_final_min=args.pa4_final_min,
    ))


if __name__ == "__main__":
    main()
