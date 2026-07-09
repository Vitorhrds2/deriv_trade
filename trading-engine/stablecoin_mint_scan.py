"""
D40 — Stablecoin Mint Signal (capital inflow detection)

Tese: Quando Tether (USDT) ou Circle (USDC) emitem (mint) grandes quantidades
de stablecoins, esse capital novo entra no ecossistema crypto → pressão
compradora → preço sobe. Se detectarmos mints grandes em tempo real,
podemos comprar BTC/ETH antes do influxo de capital precificar.

Método:
  1. Monitorar Ethereum blockchain para Transfer events no contrato USDT
  2. Mints grandes (> $10M) são eventos de supply increase
  3. Sinal: mint > $50M USDT/USDC em 1h → LONG BTC
  4. Backtest: após mints grandes, preço subiu em 1h/4h/24h?

APIs:
  - Etherscan API (free): ERC-20 token transfers
  - Stablecoin supply APIs: DefiLlama, CoinGecko
  - Binance: preço BTC/ETH em tempo real

Aggressiveness: mints de stablecoins são informação pública mas o mercado
demora a precificar. Janela de oportunidade pode ser 30min-4h.
"""
import json
import time
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import forward_return_tracker as frt

ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "YourApiKeyToken")

# Achado estrutural do audit 2026-07-08: este script sempre logou um signal_score
# por ciclo mas nunca conferiu o que o preço fez depois -- então nunca poderia
# produzir um veredito de EV/WR, não importa quanto tempo rodasse (nem quantas
# vezes o regime mudasse de STRONG LONG pra STRONG SHORT). Ver
# forward_return_tracker.py e docs/aggressive_hypotheses_report.md UPDATE 2026-07-08.
SIGNAL_HISTORY_FILE = "d40_signal_history.json"
HORIZONS_S = [3600, 4 * 3600, 24 * 3600]  # 1h / 4h / 24h, conforme a tese original

# USDT contract on Ethereum: 0xdac17f958d2ee523a2206206994597c13d831ec7
# USDC contract on Ethereum: 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48
USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
USDC_CONTRACT = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"

# DefiLlama API for stablecoin supply
DEFILLAMA_STABLECOINS = "https://stablecoins.llama.fi/stablecoins"
DEFILLAMA_CHAINS = "https://stablecoins.llama.fi/stablecoincharts/all"

# Binance price API
BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price"


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_stablecoin_supply():
    """Fetch current stablecoin supply from DefiLlama."""
    try:
        data = fetch_json(DEFILLAMA_STABLECOINS, timeout=15)
        stablecoins = data.get("data", [])
        
        usdt = None
        usdc = None
        
        for sc in stablecoins:
            if sc.get("symbol") == "USDT":
                usdt = sc
            elif sc.get("symbol") == "USDC":
                usdc = sc
        
        result = {}
        if usdt:
            result["USDT"] = {
                "name": usdt.get("name"),
                "supply": usdt.get("circulating", {}).get("current", 0),
                "pegged_to": usdt.get("peggedUSD"),
                "price": usdt.get("price", 1.0),
            }
        if usdc:
            result["USDC"] = {
                "name": usdc.get("name"),
                "supply": usdc.get("circulating", {}).get("current", 0),
                "pegged_to": usdc.get("peggedUSD"),
                "price": usdc.get("price", 1.0),
            }
        
        return result
    except Exception as e:
        print(f"  DefiLlama fetch failed: {e}")
        return None


def fetch_stablecoin_supply_history():
    """Fetch stablecoin supply history from DefiLlama for trend analysis."""
    try:
        data = fetch_json(DEFILLAMA_CHAINS, timeout=15)
        # Returns daily supply data
        if isinstance(data, list) and len(data) > 7:
            # Last 7 days
            recent = data[-7:]
            supply_changes = []
            for i in range(1, len(recent)):
                prev = recent[i-1].get("totalCirculating", {}).get("peggedUSD", 0)
                curr = recent[i].get("totalCirculating", {}).get("peggedUSD", 0)
                change = curr - prev
                date = recent[i].get("date", "")
                supply_changes.append({
                    "date": date,
                    "supply": curr,
                    "change": change,
                    "change_pct": change / prev * 100 if prev > 0 else 0,
                })
            return supply_changes
        return []
    except Exception as e:
        print(f"  DefiLlama history fetch failed: {e}")
        return []


def fetch_etherscan_token_transfers(contract, limit=20):
    """Fetch recent large token transfers from Etherscan.
    Uses token transfer events for the USDT/USDC contract.
    """
    # Query recent token transfers FROM the Tether/Circle treasury address
    # USDT treasury: 0x5754284f345afc66a98fbb0a0afe71e0f007b949
    # USDC treasury: 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 (also the token contract)
    # Use tokentx with the treasury address to get mint events
    treasury = "0x5754284f345afc66a98fbb0a0afe71e0f007b949" if contract == USDT_CONTRACT else contract
    url = (f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx"
           f"&address={treasury}&contractaddress={contract}"
           f"&page=1&offset={limit}&sort=desc&apikey={ETHERSCAN_API_KEY}")
    try:
        data = fetch_json(url, timeout=15)
        result = data.get("result", [])
        # Etherscan returns error message as string in result field
        if isinstance(result, str):
            print(f"  Etherscan API error: {result}")
            return None
        transfers = result
        large_transfers = []
        for tx in transfers:
            value = int(tx.get("value", 0))
            # USDT has 6 decimals, USDC has 6 decimals
            value_usd = value / 1e6
            if value_usd > 1_000_000:  # > $1M
                large_transfers.append({
                    "from": tx.get("from", ""),
                    "to": tx.get("to", ""),
                    "value_usd": value_usd,
                    "timestamp": int(tx.get("timeStamp", 0)),
                    "hash": tx.get("hash", ""),
                })
        return large_transfers
    except Exception as e:
        print(f"  Etherscan fetch failed (need API key): {e}")
        return None


def fetch_binance_price(symbol="BTCUSDT"):
    try:
        url = f"{BINANCE_PRICE}?symbol={symbol}"
        data = fetch_json(url, timeout=5)
        return float(data["price"])
    except:
        return None


def run_scan():
    print("=" * 80)
    print("D40 — Stablecoin Mint Signal Scanner")
    print("=" * 80)
    print("  Tese: Large USDT/USDC mints = capital inflow → BTC price up")
    print("  Method: DefiLlama supply data + Etherscan transfers + Binance price")
    print("  Signal: Supply increase > $100M in 24h → LONG BTC")
    print()

    # Step 1: Current stablecoin supply
    print("[1/3] Fetching stablecoin supply from DefiLlama...")
    supply = fetch_stablecoin_supply()
    if supply:
        for symbol, data in supply.items():
            supply_b = data["supply"] / 1e9
            print(f"  {symbol}: ${supply_b:.2f}B supply | pegged: ${data['pegged_to']:,.0f}")
    else:
        print("  Could not fetch supply data")
    
    # Step 2: Supply history (7-day trend)
    print("\n[2/3] Fetching 7-day supply history...")
    history = fetch_stablecoin_supply_history()
    if history:
        print(f"  {'Date':>12s} {'Supply':>15s} {'Change':>15s} {'Change%':>10s}")
        print(f"  {'-'*12} {'-'*15} {'-'*15} {'-'*10}")
        for h in history:
            supply_b = h["supply"] / 1e9
            change_m = h["change"] / 1e6
            print(f"  {h['date']:>12s} ${supply_b:>12.2f}B ${change_m:>+12.2f}M {h['change_pct']:>+9.3f}%")
        
        # Signal: recent supply changes
        recent_changes = [h["change"] for h in history[-3:]]
        total_3d_change = sum(recent_changes)
        avg_daily = total_3d_change / 3 if recent_changes else 0
        
        print(f"\n  3-day total supply change: ${total_3d_change/1e6:+.2f}M")
        print(f"  Average daily change: ${avg_daily/1e6:+.2f}M")
        
        if total_3d_change > 500_000_000:
            print(f"  *** LARGE SUPPLY INCREASE — BULLISH SIGNAL ***")
            print(f"  ${total_3d_change/1e6:+.0f}M new stablecoins in 3 days")
        elif total_3d_change > 100_000_000:
            print(f"  Moderate supply increase — mildly bullish")
        elif total_3d_change < -500_000_000:
            print(f"  *** LARGE SUPPLY DECREASE — BEARISH SIGNAL ***")
            print(f"  ${total_3d_change/1e6:+.0f}M stablecoins redeemed in 3 days")
    else:
        print("  Could not fetch supply history")

    # Step 3: Current prices
    print("\n[3/3] Fetching current crypto prices...")
    btc = fetch_binance_price("BTCUSDT")
    eth = fetch_binance_price("ETHUSDT")
    if btc:
        print(f"  BTC: ${btc:,.2f} | ETH: ${eth:,.2f}")

    # Step 4: Try Etherscan for real-time large transfers
    print("\n[4/4] Checking recent large USDT transfers (Etherscan)...")
    usdt_transfers = fetch_etherscan_token_transfers(USDT_CONTRACT, 20)
    if usdt_transfers:
        print(f"  Found {len(usdt_transfers)} large USDT transfers (>$1M)")
        for tx in usdt_transfers[:5]:
            ts = datetime.fromtimestamp(tx["timestamp"], tz=timezone.utc)
            print(f"    ${tx['value_usd']:,.0f} | {ts.isoformat()[:19]} | from={tx['from'][:10]}... to={tx['to'][:10]}...")
    else:
        print("  Etherscan API requires key — using DefiLlama supply data only")

    # Signal assessment
    print(f"\n{'='*80}")
    print("SIGNAL ASSESSMENT")
    print(f"{'='*80}")

    signal_score = 0
    reasons = []

    if history:
        recent_change = sum(h["change"] for h in history[-3:])
        if recent_change > 500_000_000:
            signal_score += 2
            reasons.append(f"3d supply +${recent_change/1e6:.0f}M (>$500M threshold)")
        elif recent_change > 100_000_000:
            signal_score += 1
            reasons.append(f"3d supply +${recent_change/1e6:.0f}M (moderate)")
        elif recent_change < -500_000_000:
            signal_score -= 2
            reasons.append(f"3d supply ${recent_change/1e6:.0f}M (large redemption)")

    if signal_score >= 2:
        signal = "STRONG LONG"
    elif signal_score >= 1:
        signal = "MODERATE LONG"
    elif signal_score <= -2:
        signal = "STRONG SHORT"
    elif signal_score <= -1:
        signal = "MODERATE SHORT"
    else:
        signal = "NEUTRAL"

    print(f"  Signal: {signal} (score={signal_score})")
    for r in reasons:
        print(f"    - {r}")
    if not reasons:
        print("    - No significant supply changes detected")

    print(f"\n  NOTE: Stablecoin mint signals are macro (days/weeks), not micro (seconds).")
    print(f"  For real-time detection, need Etherscan API key + WebSocket monitoring")
    print(f"  of USDT/USDC Transfer events from minting addresses.")

    # Loga esta leitura pro forward-return tracker (SEMPRE, mesmo NEUTRAL --
    # precisamos do grupo de controle).
    direction = 1 if "LONG" in signal else (-1 if "SHORT" in signal else 0)
    frt.record(SIGNAL_HISTORY_FILE, btc, direction, HORIZONS_S, meta={"signal": signal, "signal_score": signal_score})

    # Save
    with open("stablecoin_mint_scan_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "supply": supply,
            "history": history,
            "btc_price": btc,
            "eth_price": eth,
            "signal": signal,
            "signal_score": signal_score,
            "reasons": reasons,
        }, f, indent=2, default=str)

    return signal


if __name__ == "__main__":
    import sys
    continuous = "--continuous" in sys.argv
    if continuous:
        POLL_INTERVAL_S = 3600  # 1h between scans
        LOG_FILE = "d40_stablecoin_monitor.log"
        print(f"CONTINUOUS MODE — polling every {POLL_INTERVAL_S}s, logging to {LOG_FILE}")
        while True:
            try:
                signal = run_scan()
                with open(LOG_FILE, "a") as f:
                    ts = datetime.now(timezone.utc).isoformat()
                    f.write(f"[{ts}] signal={signal}\n")
                frt.resolve_due(SIGNAL_HISTORY_FILE, lambda: fetch_binance_price("BTCUSDT"))
                frt.report(SIGNAL_HISTORY_FILE, HORIZONS_S, label_prefix="D40 stablecoin")
            except Exception as e:
                print(f"  Scan error: {e}")
            time.sleep(POLL_INTERVAL_S)
    else:
        run_scan()
