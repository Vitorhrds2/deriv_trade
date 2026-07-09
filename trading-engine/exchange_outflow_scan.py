"""
D37 — Exchange Outflow Signal (on-chain alpha)

Tese: Saídas grandes de BTC/ETH de exchanges = holders movendo para cold storage
= redução de supply vendável = bullish. Se detectarmos outflows grandes em tempo real,
podemos comprar ANTES do mercado precificar a redução de supply.

Método:
  1. Poll Glassnode/CryptoQuant free API para exchange net flows
  2. Fallback: poll blockchain explorers (blockchain.com, etherscan) para large transfers
     TO known exchange wallets (Binance, Coinbase, OKX cold wallets)
  3. Sinal: net outflow > 2x média 7d → LONG
  4. Testar: após outflow grande, preço sobe em 1h/4h/24h?

APIs usadas:
  - Glassnode: free tier, exchange net flow (BTC)
  - Binance: preço em tempo real
  - Blockchain.com: large transactions API (fallback)

Aggressiveness: tentar detectar outflows em tempo quase real e medir
se há edge preditivo antes do mercado reagir.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from pathlib import Path
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import forward_return_tracker as frt

WHALE_ALERT_API_KEY = os.environ.get("WHALE_ALERT_API_KEY", "demo")

# Achado estrutural do audit 2026-07-08: este script sempre logou um signal_score
# por ciclo mas nunca conferiu o que o preço fez depois -- então nunca poderia
# produzir um veredito de EV/WR, não importa quanto tempo rodasse. Ver
# forward_return_tracker.py e docs/aggressive_hypotheses_report.md UPDATE 2026-07-08.
SIGNAL_HISTORY_FILE = "d37_signal_history.json"
HORIZONS_S = [3600, 4 * 3600, 24 * 3600]  # 1h / 4h / 24h, conforme a tese original

# Known exchange hot wallet addresses (subset)
EXCHANGE_WALLETS_BTC = {
    "Binance": ["34xp4vRoCGJym3xR7yCXYF1QfM4W8YQ3Xc", "1NDyJtNTjmwk5xPNhj3amCT4L2WQ8s5K3"],
    "Coinbase": ["37XuVSEpTT4WtHighdDZDpJ8q5ZJYw4Xmo"],
    "OKX": ["3Dq8Kkmz5oYxraB4vz3P8hQ8Yx5Z8w9X2"],
}

# Glassnode free tier endpoints
GLASSNODE_BASE = "https://api.glassnode.com/v1/metrics"


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_binance_price(symbol="BTCUSDT"):
    """Fetch current price from Binance."""
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data = fetch_json(url)
    return float(data["price"])


def fetch_exchange_netflow_cryptoquant():
    """Try CryptoQuant free API for exchange net flow.
    Returns net flow in BTC (positive = inflow to exchange, negative = outflow).
    """
    # CryptoQuant public endpoint (may need API key)
    # Fallback: use Whale Alert API (free tier)
    url = f"https://api.whale-alert.io/v1/transactions?api_key={WHALE_ALERT_API_KEY}&min=500000&start=0&currency=btc"
    try:
        data = fetch_json(url, timeout=10)
        return data
    except Exception as e:
        print(f"  CryptoQuant/WhaleAlert fetch failed: {e}")
        return None


def fetch_glassnode_exchanges_balance():
    """Fetch exchange balance from Glassnode (free tier, may need key).
    Without API key, returns None.
    """
    url = f"{GLASSNODE_BASE}/distribution/balance_exchanges?a=BTC"
    try:
        data = fetch_json(url, timeout=10)
        return data
    except Exception as e:
        print(f"  Glassnode fetch failed (need API key?): {e}")
        return None


def fetch_large_btc_transactions():
    """Fetch large BTC transactions from blockchain.com API.
    This is a proxy for whale movements.
    """
    # blockchain.com unconfirmed transactions API
    url = "https://blockchain.info/unconfirmed-transactions?format=json&cors=true"
    try:
        data = fetch_json(url, timeout=15)
        txs = data.get("txs", [])
        large_txs = []
        for tx in txs[:50]:  # check recent unconfirmed
            total_out = sum(o.get("value", 0) for o in tx.get("out", []))
            if total_out > 10 * 1e8:  # > 10 BTC
                large_txs.append({
                    "hash": tx.get("hash", ""),
                    "value_btc": total_out / 1e8,
                    "time": tx.get("time", 0),
                    "n_outs": len(tx.get("out", [])),
                })
        return large_txs
    except Exception as e:
        print(f"  blockchain.com fetch failed: {e}")
        return None


def fetch_binance_withdrawal_history():
    """Binance doesn't expose withdrawal history publicly.
    Use Whale Alert as proxy for large exchange outflows.
    """
    # Whale Alert with real API key
    now_ts = int(time.time())
    url = f"https://api.whale-alert.io/v1/transactions?api_key={WHALE_ALERT_API_KEY}&min=1000000&start={now_ts - 3600}&currency=btc"
    try:
        data = fetch_json(url, timeout=15)
        transactions = data.get("transactions", [])
        outflows = []
        for tx in transactions:
            if tx.get("from", {}).get("type") == "exchange":
                outflows.append({
                    "from": tx["from"].get("owner", "unknown"),
                    "to": tx.get("to", {}).get("owner", "unknown"),
                    "to_type": tx.get("to", {}).get("type", "unknown"),
                    "amount_usd": tx.get("amount_usd", 0),
                    "amount_btc": tx.get("amount", 0),
                    "timestamp": tx.get("timestamp", 0),
                    "hash": tx.get("id", ""),
                })
        return outflows
    except Exception as e:
        print(f"  Whale Alert fetch failed: {e}")
        return None


def analyze_outflow_signal():
    """Main analysis: fetch outflows, compute signal, predict price direction."""
    print("=" * 80)
    print("D37 — Exchange Outflow Signal Scan")
    print("=" * 80)
    print("  Tese: Large exchange outflows → bullish (supply reduction)")
    print("  Method: Whale Alert API + Binance price")
    print("  Signal: Net outflow > $1M in 1h → LONG BTC")
    print("  Test: Price change 1h/4h/24h after signal")
    print()

    # Step 1: Fetch current large transactions
    print("[1/3] Fetching large BTC transactions (last 1h)...")
    outflows = fetch_binance_withdrawal_history()

    if outflows is None:
        print("  Fallback: blockchain.com unconfirmed txs")
        large_txs = fetch_large_btc_transactions()
        if large_txs:
            print(f"  Found {len(large_txs)} large unconfirmed BTC txs (>10 BTC)")
            for tx in large_txs[:10]:
                print(f"    {tx['value_btc']:.1f} BTC | outs={tx['n_outs']} | hash={tx['hash'][:16]}...")
        else:
            print("  No large transactions data available")
    else:
        print(f"  Found {len(outflows)} large exchange outflows (>$1M) in last 1h")
        total_usd = sum(o["amount_usd"] for o in outflows)
        total_btc = sum(o["amount_btc"] for o in outflows)
        print(f"  Total: ${total_usd:,.0f} | {total_btc:.1f} BTC")
        for o in outflows[:10]:
            direction = "EXCHANGE OUTFLOW" if o["to_type"] != "exchange" else "EXCHANGE TRANSFER"
            print(f"    {direction}: {o['from']} → {o['to']} | ${o['amount_usd']:,.0f} | {o['amount_btc']:.1f} BTC")

    # Step 2: Fetch blockchain.com large txs as additional signal
    print("\n[2/3] Fetching blockchain.com large unconfirmed txs...")
    large_txs = fetch_large_btc_transactions()
    if large_txs:
        print(f"  {len(large_txs)} large unconfirmed txs (>10 BTC)")
        total_btc = sum(tx["value_btc"] for tx in large_txs)
        print(f"  Total: {total_btc:.1f} BTC in unconfirmed pool")
    else:
        print("  No large unconfirmed txs or API unavailable")

    # Step 3: Current price for baseline
    print("\n[3/3] Fetching current BTC price...")
    try:
        btc_price = fetch_binance_price("BTCUSDT")
        eth_price = fetch_binance_price("ETHUSDT")
        print(f"  BTC: ${btc_price:,.2f} | ETH: ${eth_price:,.2f}")
    except Exception as e:
        print(f"  Price fetch failed: {e}")
        btc_price = 0
        eth_price = 0

    # Signal assessment
    print(f"\n{'='*80}")
    print("SIGNAL ASSESSMENT")
    print(f"{'='*80}")

    signal_score = 0
    signal_reasons = []

    if outflows:
        total_outflow_usd = sum(o["amount_usd"] for o in outflows if o["to_type"] != "exchange")
        if total_outflow_usd > 5_000_000:
            signal_score += 2
            signal_reasons.append(f"Large net outflow: ${total_outflow_usd:,.0f} (> $5M threshold)")
        elif total_outflow_usd > 1_000_000:
            signal_score += 1
            signal_reasons.append(f"Moderate net outflow: ${total_outflow_usd:,.0f}")

    if large_txs:
        total_large_btc = sum(tx["value_btc"] for tx in large_txs)
        if total_large_btc > 100:
            signal_score += 1
            signal_reasons.append(f"Large unconfirmed txs: {total_large_btc:.1f} BTC")

    if signal_score >= 3:
        signal = "STRONG LONG"
    elif signal_score >= 2:
        signal = "MODERATE LONG"
    elif signal_score >= 1:
        signal = "WEAK LONG"
    else:
        signal = "NO SIGNAL"

    print(f"  Signal: {signal} (score={signal_score})")
    for r in signal_reasons:
        print(f"    - {r}")

    if not signal_reasons:
        print("    - No large outflows detected in last hour")
        print("    - Need to monitor continuously for whale movements")

    # Save results
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "btc_price": btc_price,
        "eth_price": eth_price,
        "outflows": outflows or [],
        "large_txs": large_txs or [],
        "signal": signal,
        "signal_score": signal_score,
        "signal_reasons": signal_reasons,
    }

    with open("exchange_outflow_scan_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n  Results saved to exchange_outflow_scan_results.json")
    print(f"\n  NOTE: This is a point-in-time snapshot. For proper backtest,")
    print(f"  need to run continuously and track price after signals.")

    # Loga esta leitura pro forward-return tracker (SEMPRE, mesmo sem sinal --
    # precisamos do grupo de controle). direction=+1 pq a tese é LONG-only.
    direction = 1 if signal_score > 0 else 0
    frt.record(SIGNAL_HISTORY_FILE, btc_price, direction, HORIZONS_S, meta={"signal": signal})

    return results


if __name__ == "__main__":
    import sys
    continuous = "--continuous" in sys.argv
    if continuous:
        POLL_INTERVAL_S = 600  # 10 min between scans
        LOG_FILE = "d37_outflow_monitor.log"
        print(f"CONTINUOUS MODE — polling every {POLL_INTERVAL_S}s, logging to {LOG_FILE}")
        cycle = 0
        while True:
            try:
                results = analyze_outflow_signal()
                if results.get("signal_score", 0) > 0:
                    with open(LOG_FILE, "a") as f:
                        f.write(f"[{results['timestamp']}] SIGNAL: {results['signal']} score={results['signal_score']} | BTC=${results['btc_price']:,.0f}\n")
                        for r in results.get("signal_reasons", []):
                            f.write(f"  - {r}\n")
                frt.resolve_due(SIGNAL_HISTORY_FILE, lambda: fetch_binance_price("BTCUSDT"))
                cycle += 1
                if cycle % 6 == 0:  # ~1h (6 x 10min)
                    frt.report(SIGNAL_HISTORY_FILE, HORIZONS_S, label_prefix="D37 outflow")
            except Exception as e:
                print(f"  Scan error: {e}")
            time.sleep(POLL_INTERVAL_S)
    else:
        analyze_outflow_signal()
