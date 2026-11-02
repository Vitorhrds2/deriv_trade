import json, os

print("=== 1. DERIV D107 STATE ===")
if os.path.exists("trading-engine/d107_rate_limit_winner_holding_state.json"):
    with open("trading-engine/d107_rate_limit_winner_holding_state.json") as f:
        s = json.load(f)
    print(f"Account: {s.get('account_id')} | Balance: {s.get('balance', 'N/A')} | Buys: {s.get('confirmed_buys')} | Open: {len(s.get('contracts', {}))} | Realized PnL: ${s.get('session_realized_pnl', 0):.2f} | Fees: ${s.get('cancellation_fees', 0):.2f}")
    for cid, c in s.get("contracts", {}).items():
        print(f"  Contract {cid} ({c.get('contract_type')}): Lifecycle={c.get('lifecycle')} | PnL={c.get('last_profit')} | Peak={c.get('peak_unrealized_pnl')} | Bid={c.get('bid_price')}")

print("\n=== 2. DERIV RESULTS HISTORY ===")
if os.path.exists("trading-engine/d107_rate_limit_winner_holding_results.jsonl"):
    actions = {}
    with open("trading-engine/d107_rate_limit_winner_holding_results.jsonl") as f:
        for line in f:
            if not line.strip(): continue
            ev = json.loads(line)
            act = ev.get("action")
            if act in ("cancelled_loser", "sold_winner_trailing_stop", "held_winner", "buy_confirmed"):
                actions[act] = actions.get(act, 0) + 1
    print("Action events count:", actions)

print("\n=== 3. AI REGIME POLICY ===")
if os.path.exists("trading-engine/market_regime_policy.json"):
    with open("trading-engine/market_regime_policy.json") as f:
        p = json.load(f)
    print(f"Timestamp: {p.get('timestamp')} | Primary: {p.get('deriv_primary_asset')} ({p.get('deriv_primary_strategy')})")
    print(f"Deriv Metrics:")
    for sym, m in p.get("deriv_metrics", {}).items():
        print(f"  {sym}: Hurst={m.get('hurst')} | Vol={m.get('volatility_5m_pct')}% | Strat={m.get('recommended_strategy')}")
    print(f"Top Squeeze: {[x['symbol'] for x in p.get('binance_funding_landscape', {}).get('top_squeeze_candidates', [])]}")

print("\n=== 4. BINANCE FUNDING SQUEEZE BOT ===")
if os.path.exists("trading-engine/binance_funding_squeeze_state.json"):
    with open("trading-engine/binance_funding_squeeze_state.json") as f:
        sq = json.load(f)
    print(f"Open Pos: {len(sq.get('open_positions', []))} | Realized PnL: ${sq.get('total_pnl', 0):.2f} | Realized Trades: {sq.get('realized_trades')}")
    for p in sq.get("open_positions", []):
        print(f"  {p['symbol']:10} | Entry: {p['entry_price']:.6f} | Mark: {p.get('current_price', 0):.6f} | PnL: ${p.get('unrealized_pnl_usd', 0):+.2f} ({p.get('unrealized_pnl_pct', 0):+.2f}%)")

print("\n=== 5. DERIBIT IV STATS ===")
if os.path.exists("trading-engine/iv_anomaly_paper_stats.json"):
    with open("trading-engine/iv_anomaly_paper_stats.json") as f:
        iv_s = json.load(f)
    print(f"Trades Settled: {iv_s.get('n')} | WR: {iv_s.get('wr')}% | Total PnL: ${iv_s.get('total_pnl', 0):.2f}")

print("\n=== 6. BINANCE SUI SHORT BOT ===")
if os.path.exists("trading-engine/unlock_short_state.json"):
    with open("trading-engine/unlock_short_state.json") as f:
        sui = json.load(f)
    for p in sui.get("open_positions", []):
        print(f"  {p['symbol']} SHORT @ ${p['entry_price']:.4f} | Stop: ${p.get('stop_loss_price', 0):.4f} | Unlock Date: {p.get('unlock_date')}")
