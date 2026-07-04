"""
D38 — Binance Announcement Front-Run Scanner

Tese: Binance posta anúncios (new listings, delistings, maintenance) em
https://www.binance.com/en/support/announcement. Se detectarmos o anúncio
em segundos e tradearmos antes do mercado precificar, capturamos o pump
ou evitamos o dump.

Método:
  1. Scrape Binance announcement page a cada 3s
  2. Detectar novos anúncios (hash change)
  3. Classificar: listing (bullish), delisting (bearish), maintenance (neutral)
  4. Se listing detectado: comprar o token na Binance Spot imediatamente
  5. Medir tempo de reação vs movimento de preço

Aggressiveness: polling a cada 3s, tentar ser mais rápido que o mercado.
Binance announcements são a fonte #1 de pumps instantâneos.
"""
import json
import time
import hashlib
import urllib.request
import re
from datetime import datetime, timezone

ANNOUNCEMENT_URLS = [
    "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&pageNo=1&pageSize=10",
    "https://www.binance.com/bapi/composite/v1/public/content/article/list/query?type=1&pageNo=1&pageSize=10",
    "https://www.binance.com/en/support/announcement/api/v1/list?type=1&pageNo=1&pageSize=10",
]
POLL_INTERVAL = 3  # seconds
RUN_DURATION = 120  # 2 minutes
PRICE_API = "https://api.binance.com/api/v3/ticker/price"

# Keywords for classification
LISTING_KEYWORDS = ["list", "listing", "new trading pair", "opens trading", "will list"]
DELISTING_KEYWORDS = ["delist", "remove", "cease trading", "trading halt"]
MAINTENANCE_KEYWORDS = ["maintenance", "suspend", "resume", "network upgrade"]


def fetch_json(url, timeout=10, headers=None):
    hdrs = {"User-Agent": "Mozilla/5.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_announcements():
    """Fetch latest Binance announcements via their internal API.
    Response format: data.catalogs[].articles[]
    """
    for url in ANNOUNCEMENT_URLS:
        try:
            data = fetch_json(url, timeout=10, headers={
                "Accept": "application/json",
                "Referer": "https://www.binance.com/en/support/announcement",
            })
            # New format: data.catalogs[].articles[]
            catalogs = data.get("data", {}).get("catalogs", [])
            if catalogs:
                articles = []
                for cat in catalogs:
                    for art in cat.get("articles", []):
                        art["catalog"] = cat.get("catalogName", "")
                        articles.append(art)
                if articles:
                    return articles
            # Fallback: data.articles or data.list
            articles = data.get("data", {}).get("articles", [])
            if not articles:
                articles = data.get("data", {}).get("list", [])
            if articles:
                return articles
        except Exception as e:
            continue
    return None


def classify_announcement(title, content=""):
    """Classify announcement as bullish/bearish/neutral."""
    text = (title + " " + content).lower()
    
    for kw in LISTING_KEYWORDS:
        if kw in text:
            return "LISTING", "bullish"
    
    for kw in DELISTING_KEYWORDS:
        if kw in text:
            return "DELISTING", "bearish"
    
    for kw in MAINTENANCE_KEYWORDS:
        if kw in text:
            return "MAINTENANCE", "neutral"
    
    return "OTHER", "neutral"


def extract_token_symbol(title):
    """Try to extract token symbol from announcement title."""
    # Common patterns: "Binance Will List XXX" or "New Trading Pair: XXXUSDT"
    patterns = [
        r"list\s+(\w+)\s",
        r"list\s+(\w+)$",
        r"(\w+)/USDT",
        r"(\w+)/BTC",
        r"trading pair.*?(\w+)",
    ]
    for p in patterns:
        m = re.search(p, title, re.IGNORECASE)
        if m:
            sym = m.group(1).upper()
            if len(sym) <= 10 and sym.isalpha():
                return sym
    return None


def fetch_price(symbol):
    """Fetch current price for a symbol."""
    try:
        url = f"{PRICE_API}?symbol={symbol}"
        data = fetch_json(url, timeout=5)
        return float(data["price"])
    except:
        return None


def run_scan():
    print("=" * 80)
    print("D38 — Binance Announcement Front-Run Scanner")
    print("=" * 80)
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print(f"  Duration: {RUN_DURATION}s ({RUN_DURATION//60}min)")
    print(f"  Target: detect new announcements within {POLL_INTERVAL}s")
    print()

    # Fetch initial state
    print("[INIT] Fetching current announcements as baseline...")
    initial = fetch_announcements()
    if not initial:
        print("  ERROR: Could not fetch announcements. API may have changed.")
        return

    known_ids = set()
    known_titles = set()
    for article in initial:
        known_ids.add(article.get("id", ""))
        known_titles.add(article.get("title", ""))
    
    print(f"  Baseline: {len(known_ids)} known announcements")
    print(f"  Latest: {initial[0].get('title', 'N/A')[:80]}")
    print()

    # Track price reactions
    price_reactions = []
    new_announcements = []

    start_time = time.time()
    poll_count = 0

    print(f"[SCAN] Monitoring for new announcements...\n")

    while RUN_DURATION == 0 or time.time() - start_time < RUN_DURATION:
        poll_count += 1
        now = datetime.now(timezone.utc)
        elapsed = time.time() - start_time

        articles = fetch_announcements()
        if not articles:
            time.sleep(POLL_INTERVAL)
            continue

        for article in articles:
            art_id = article.get("id", "")
            title = article.get("title", "")
            
            if art_id in known_ids or title in known_titles:
                continue

            # NEW ANNOUNCEMENT DETECTED!
            known_ids.add(art_id)
            known_titles.add(title)

            category, sentiment = classify_announcement(title)
            token = extract_token_symbol(title)
            
            # Fetch price immediately
            price_data = {}
            if token:
                symbol = f"{token}USDT"
                price = fetch_price(symbol)
                if price:
                    price_data = {"symbol": symbol, "price_t0": price, "t0_time": now.isoformat()}
                    print(f"  *** NEW ANNOUNCEMENT ***")
                    print(f"  [{now.isoformat()}] Poll #{poll_count} ({elapsed:.1f}s elapsed)")
                    print(f"  Title: {title[:100]}")
                    print(f"  Category: {category} | Sentiment: {sentiment}")
                    print(f"  Token: {token} | Price: ${price}")
                    
                    # Track price for next 60s
                    price_reactions.append({
                        "title": title,
                        "category": category,
                        "sentiment": sentiment,
                        "token": token,
                        **price_data,
                        "prices_after": [],
                    })
                else:
                    print(f"  *** NEW ANNOUNCEMENT (no price) ***")
                    print(f"  [{now.isoformat()}] {title[:100]}")
                    print(f"  Category: {category} | Token: {token} (price not available)")
            else:
                print(f"  *** NEW ANNOUNCEMENT ***")
                print(f"  [{now.isoformat()}] {title[:100]}")
                print(f"  Category: {category} | Sentiment: {sentiment}")
                print(f"  Token: N/A")

            new_announcements.append({
                "id": art_id,
                "title": title,
                "category": category,
                "sentiment": sentiment,
                "token": token,
                "timestamp": now.isoformat(),
                "poll_number": poll_count,
                "elapsed_s": elapsed,
            })

        # Check price reactions for tracked tokens
        for reaction in price_reactions:
            if "price_t0" not in reaction:
                continue
            symbol = reaction["symbol"]
            current_price = fetch_price(symbol)
            if current_price:
                price_change_pct = (current_price - reaction["price_t0"]) / reaction["price_t0"] * 100
                reaction["prices_after"].append({
                    "time": now.isoformat(),
                    "price": current_price,
                    "change_pct": price_change_pct,
                })

        time.sleep(POLL_INTERVAL)

    # Summary
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Duration: {RUN_DURATION}s | Polls: {poll_count} | Interval: {POLL_INTERVAL}s")
    print(f"  New announcements detected: {len(new_announcements)}")
    print(f"  Price reactions tracked: {len(price_reactions)}")

    if new_announcements:
        print(f"\n  Detected announcements:")
        for ann in new_announcements:
            print(f"    [{ann['timestamp']}] {ann['category']:>12s} | {ann['sentiment']:>8s} | {ann['title'][:60]}")
    else:
        print(f"\n  No new announcements in {RUN_DURATION}s window")
        print(f"  (Binance typically posts 0-5 announcements/hour)")

    if price_reactions:
        print(f"\n  Price reactions:")
        for r in price_reactions:
            if r["prices_after"]:
                last = r["prices_after"][-1]
                print(f"    {r['symbol']}: ${r['price_t0']:.4f} → ${last['price']:.4f} ({last['change_pct']:+.2f}%)")
            else:
                print(f"    {r['symbol']}: ${r['price_t0']:.4f} (no subsequent price data)")

    # Verdict
    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")
    
    if not new_announcements:
        print(f"  INCONCLUSIVO — No announcements in {RUN_DURATION}s window")
        print(f"  Need longer monitoring (hours) to capture listing events")
        print(f"  Binance posts ~3-10 announcements/day, listings ~1-2/week")
    else:
        listings = [a for a in new_announcements if a["category"] == "LISTING"]
        if listings:
            print(f"  {len(listings)} LISTING announcement(s) detected!")
            print(f"  Check if price moved > 1% within 60s of detection")
            print(f"  If yes, edge depends on: detection speed + execution speed + slippage")
        else:
            print(f"  {len(new_announcements)} announcement(s) but no listings")
            print(f"  Non-listing announcements typically don't move price significantly")

    # Save
    with open("announcement_scan_results.json", "w") as f:
        json.dump({
            "duration_s": RUN_DURATION,
            "poll_interval_s": POLL_INTERVAL,
            "polls": poll_count,
            "new_announcements": new_announcements,
            "price_reactions": price_reactions,
        }, f, indent=2, default=str)

    return new_announcements


if __name__ == "__main__":
    import sys
    if "--continuous" in sys.argv:
        RUN_DURATION = 0
        print("CONTINUOUS MODE — infinite polling")
    run_scan()
