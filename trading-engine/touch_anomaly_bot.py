#!/usr/bin/env python3
"""
================================================================================
  DERIV TOUCH ANOMALY AUTONOMOUS TRADING BOT
  Exploits structural barrier pricing mispricing on Daily Reset Indices:
  - RDBULL ONETOUCH (counter-trend negative barrier, e.g. -2.0)
  - RDBEAR ONETOUCH (counter-trend positive barrier, e.g. +2.0)
================================================================================
"""

import asyncio
import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

class TouchAnomalyBot:
    def __init__(self, app_id, token, stake=1.0, barrier_offset=2.0, duration_m=2, 
                 mode='alternate', target_symbol='RDBULL', max_trades=20,
                 take_profit=50.0, stop_loss=-20.0, delay=5.0, log_file='touch_anomaly_trades.jsonl',
                 min_ratio=None):
        self.app_id = app_id
        self.token = token
        self.stake = float(stake)
        self.barrier_offset = float(barrier_offset)
        self.duration_m = int(duration_m)
        self.mode = mode  # 'alternate', 'parallel', 'single'
        self.target_symbol = target_symbol
        self.max_trades = int(max_trades)
        self.take_profit = float(take_profit)
        self.stop_loss = float(stop_loss)
        self.delay = float(delay)
        self.log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_file)
        
        # Dynamic minimum payout ratio threshold based on contract duration
        if min_ratio is not None:
            self.min_ratio = float(min_ratio)
        elif self.duration_m <= 2:
            self.min_ratio = 1.85
        elif self.duration_m == 3:
            self.min_ratio = 1.55
        elif self.duration_m <= 5:
            self.min_ratio = 1.35
        else:
            self.min_ratio = 1.20
        
        self.client = None
        self.running = False
        
        # Performance Tracking
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0
        self.history = []

    def log_trade(self, trade_data):
        self.history.append(trade_data)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(trade_data) + '\n')

    def print_status_banner(self):
        wr = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0.0
        roi = (self.total_pnl / (self.total_trades * self.stake) * 100) if self.total_trades > 0 else 0.0
        print("\n" + "=" * 70)
        print(f"  PERFORMANCE DASHBOARD | Trades: {self.total_trades} | Wins: {self.wins} | Losses: {self.losses}")
        print(f"  Win Rate: {wr:5.1f}% | Total PnL: ${self.total_pnl:+7.2f} | ROI: {roi:+6.1f}% | Max DD: ${self.max_drawdown:5.2f}")
        print("=" * 70 + "\n")

    async def get_proposal(self, symbol, barrier_str):
        prop_req = {
            'proposal': 1,
            'amount': self.stake,
            'basis': 'stake',
            'contract_type': 'ONETOUCH',
            'currency': 'USD',
            'underlying_symbol': symbol,
            'duration': self.duration_m,
            'duration_unit': 'm',
            'barrier': barrier_str
        }
        res = await self.client.send_request(prop_req)
        if 'error' in res:
            return None, res['error'].get('message', 'Unknown error')
        return res.get('proposal'), None

    async def execute_trade(self, symbol, barrier_str, trial_idx):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Trial #{trial_idx}: Requesting proposal for {symbol} ONETOUCH {barrier_str} (${self.stake})...")
        
        proposal, err = await self.get_proposal(symbol, barrier_str)
        if err or not proposal:
            print(f"  ❌ Proposal failed for {symbol}: {err}")
            return None

        ask_price = float(proposal['ask_price'])
        payout = float(proposal['payout'])
        ratio = payout / ask_price
        be_wr = (100.0 / ratio) if ratio > 0 else 0.0
        
        # Mispricing filter: payout ratio must meet threshold
        if ratio < self.min_ratio:
            print(f"  ⚠️ Payout ratio too low ({ratio:.2f}x < {self.min_ratio:.2f}x). Deriv may have adjusted pricing. Skipping trade.")
            return None

        print(f"  ⚡ Quote: Ask=${ask_price:.2f} | Payout=${payout:.2f} | Multiplier={ratio:.3f}x | Breakeven WR={be_wr:.1f}%")
        
        # Buy contract
        buy_res = await self.client.buy_contract(proposal['id'], ask_price)
        if 'error' in buy_res:
            print(f"  ❌ Buy order failed: {buy_res['error'].get('message')}")
            return None

        contract_id = buy_res['buy']['contract_id']
        t_start = time.time()
        print(f"  🎯 Position OPEN! Contract ID: {contract_id} | Monitoring settlement...")

        # Monitor settlement
        timeout = self.duration_m * 60 + 20
        while time.time() - t_start < timeout:
            poc_res = await self.client.send_request({
                'proposal_open_contract': 1,
                'contract_id': contract_id
            })
            poc = poc_res.get('proposal_open_contract', {})
            status = poc.get('status')
            is_sold = bool(poc.get('is_sold'))
            profit = float(poc.get('profit', 0) or 0)
            spot = poc.get('current_spot')
            entry = poc.get('entry_spot')
            barrier = poc.get('barrier')
            elapsed = time.time() - t_start
            
            if is_sold:
                won = (status == 'won')
                result_str = "WIN ✅" if won else "LOSS ❌"
                print(f"  🏁 RESULT: {result_str} | PnL=${profit:+.2f} | Time={elapsed:.1f}s | Entry={entry} | Barrier={barrier} | Exit={spot}")
                
                trade_record = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'trial': trial_idx,
                    'symbol': symbol,
                    'barrier': barrier_str,
                    'stake': self.stake,
                    'payout': payout,
                    'ratio': ratio,
                    'result': 'won' if won else 'lost',
                    'profit': profit,
                    'duration_sec': elapsed,
                    'entry_spot': entry,
                    'barrier_spot': barrier,
                    'exit_spot': spot
                }
                
                # Update metrics
                self.total_trades += 1
                if won:
                    self.wins += 1
                else:
                    self.losses += 1
                self.total_pnl += profit
                if self.total_pnl > self.peak_pnl:
                    self.peak_pnl = self.total_pnl
                dd = self.peak_pnl - self.total_pnl
                if dd > self.max_drawdown:
                    self.max_drawdown = dd
                
                self.log_trade(trade_record)
                return trade_record
                
            await asyncio.sleep(2.0)

        print(f"  ⚠️ Timeout waiting for contract {contract_id} resolution.")
        return None

    async def execute_parallel_pair(self, trial_idx):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Trial #{trial_idx}-PARALLEL: Requesting proposals for RDBULL (-{self.barrier_offset}) & RDBEAR (+{self.barrier_offset})...")
        b_bull_str = f"-{self.barrier_offset:.1f}"
        b_bear_str = f"+{self.barrier_offset:.1f}"
        
        prop_bull, err1 = await self.get_proposal('RDBULL', b_bull_str)
        prop_bear, err2 = await self.get_proposal('RDBEAR', b_bear_str)
        
        if err1 or err2 or not prop_bull or not prop_bear:
            print(f"  ❌ Proposal failed (Bull: {err1}, Bear: {err2})")
            return
            
        ratio_bull = float(prop_bull['payout']) / float(prop_bull['ask_price'])
        ratio_bear = float(prop_bear['payout']) / float(prop_bear['ask_price'])
        
        print(f"  ⚡ Quotes: Bull={ratio_bull:.3f}x (Ask=${prop_bull['ask_price']}) | Bear={ratio_bear:.3f}x (Ask=${prop_bear['ask_price']})")
        if ratio_bull < self.min_ratio or ratio_bear < self.min_ratio:
            print(f"  ⚠️ Payout ratio below threshold (Bull: {ratio_bull:.2f}x, Bear: {ratio_bear:.2f}x < {self.min_ratio:.2f}x). Skipping.")
            return

        buy_bull = await self.client.buy_contract(prop_bull['id'], float(prop_bull['ask_price']))
        buy_bear = await self.client.buy_contract(prop_bear['id'], float(prop_bear['ask_price']))
        
        id_bull = buy_bull.get('buy', {}).get('contract_id')
        id_bear = buy_bear.get('buy', {}).get('contract_id')
        print(f"  🎯 Parallel Bought! Bull ID: {id_bull} | Bear ID: {id_bear}")
        
        t_start = time.time()
        cids = {'RDBULL': id_bull, 'RDBEAR': id_bear}
        props = {'RDBULL': prop_bull, 'RDBEAR': prop_bear}
        done = {'RDBULL': False, 'RDBEAR': False}
        
        while time.time() - t_start < (self.duration_m * 60 + 20) and not all(done.values()):
            for sym, cid in cids.items():
                if done[sym] or not cid:
                    continue
                poc_res = await self.client.send_request({'proposal_open_contract': 1, 'contract_id': cid})
                poc = poc_res.get('proposal_open_contract', {})
                if poc.get('is_sold'):
                    won = (poc.get('status') == 'won')
                    profit = float(poc.get('profit', 0) or 0)
                    elapsed = time.time() - t_start
                    entry = poc.get('entry_spot')
                    barrier = poc.get('barrier')
                    exit_spot = poc.get('current_spot')
                    res_str = "WIN ✅" if won else "LOSS ❌"
                    print(f"  🏁 [{sym}] {res_str} | PnL=${profit:+.2f} | Time={elapsed:.1f}s | Entry={entry} | Barrier={barrier} | Exit={exit_spot}")
                    
                    self.total_trades += 1
                    if won:
                        self.wins += 1
                    else:
                        self.losses += 1
                    self.total_pnl += profit
                    if self.total_pnl > self.peak_pnl:
                        self.peak_pnl = self.total_pnl
                    dd = self.peak_pnl - self.total_pnl
                    if dd > self.max_drawdown:
                        self.max_drawdown = dd
                        
                    self.log_trade({
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'trial': f"{trial_idx}-{sym}",
                        'symbol': sym,
                        'barrier': b_bull_str if sym == 'RDBULL' else b_bear_str,
                        'stake': self.stake,
                        'payout': float(poc.get('payout', 0) or 0),
                        'ratio': ratio_bull if sym == 'RDBULL' else ratio_bear,
                        'result': 'won' if won else 'lost',
                        'profit': profit,
                        'duration_sec': elapsed,
                        'entry_spot': entry,
                        'barrier_spot': barrier,
                        'exit_spot': exit_spot
                    })
                    done[sym] = True
            await asyncio.sleep(2.0)

    async def run(self):
        self.running = True
        self.client = DerivClient(app_id=self.app_id, api_token=self.token, use_demo=True)
        await self.client.connect()
        print(f"Connected to Deriv! Account: {self.client.account_id}")
        
        # Check balance
        bal_res = await self.client.send_request({'balance': 1})
        bal = bal_res.get('balance', {}).get('balance', 0.0)
        print(f"Starting Demo Balance: ${bal:,.2f}")
        print(f"Configuration: Mode={self.mode} | Stake=${self.stake} | Barrier=±{self.barrier_offset} | Duration={self.duration_m}m")
        print(f"Risk Limits: Stop Loss=${self.stop_loss} | Take Profit=${self.take_profit} | Max Trades={self.max_trades or 'Unlimited'}\n")

        trial = 1
        symbols_cycle = ['RDBULL', 'RDBEAR']
        
        try:
            while self.running:
                # Check stop loss / take profit
                if self.total_pnl <= self.stop_loss:
                    print(f"\n🛑 STOP LOSS TRIGGERED! PnL (${self.total_pnl:.2f}) <= Stop Loss (${self.stop_loss:.2f}). Halting bot.")
                    break
                if self.total_pnl >= self.take_profit:
                    print(f"\n🎉 TAKE PROFIT REACHED! PnL (${self.total_pnl:.2f}) >= Target (${self.take_profit:.2f}). Halting bot.")
                    break
                if self.max_trades > 0 and self.total_trades >= self.max_trades:
                    print(f"\n🎯 Max trades ({self.max_trades}) reached. Stopping run.")
                    break

                if self.mode == 'parallel':
                    await self.execute_parallel_pair(trial)
                elif self.mode == 'alternate':
                    sym = symbols_cycle[(trial - 1) % len(symbols_cycle)]
                    barrier_str = f"-{self.barrier_offset:.1f}" if sym == 'RDBULL' else f"+{self.barrier_offset:.1f}"
                    await self.execute_trade(sym, barrier_str, trial)
                elif self.mode == 'single':
                    sym = self.target_symbol
                    barrier_str = f"-{self.barrier_offset:.1f}" if sym == 'RDBULL' else f"+{self.barrier_offset:.1f}"
                    await self.execute_trade(sym, barrier_str, trial)

                self.print_status_banner()
                trial += 1
                
                if self.max_trades > 0 and self.total_trades >= self.max_trades:
                    break
                    
                print(f"Waiting {self.delay}s cooldown before next cycle...")
                await asyncio.sleep(self.delay)

        except asyncio.CancelledError:
            print("\nBot execution cancelled.")
        except Exception as e:
            print(f"\n⚠️ Unexpected error: {e}")
        finally:
            print("\n=======================================================")
            print("  SESSION SUMMARY REPORT")
            print("=======================================================")
            self.print_status_banner()
            if self.client and self.client.ws:
                await self.client.ws.close()

def main():
    parser = argparse.ArgumentParser(description="Deriv Touch Anomaly Autonomous Bot")
    parser.add_argument('--stake', type=float, default=1.0, help='Stake per trade ($)')
    parser.add_argument('--barrier', type=float, default=2.0, help='Barrier offset absolute value (e.g. 2.0)')
    parser.add_argument('--duration', type=int, default=2, help='Contract duration in minutes (default: 2)')
    parser.add_argument('--mode', type=str, choices=['alternate', 'parallel', 'single'], default='alternate', 
                        help='Trading mode: alternate (RDBULL/RDBEAR), parallel (both concurrently), single')
    parser.add_argument('--symbol', type=str, choices=['RDBULL', 'RDBEAR'], default='RDBULL', help='Symbol for single mode')
    parser.add_argument('--max-trades', type=int, default=20, help='Maximum trades to execute (0 for unlimited)')
    parser.add_argument('--take-profit', type=float, default=50.0, help='Take profit in $')
    parser.add_argument('--stop-loss', type=float, default=-20.0, help='Stop loss in $')
    parser.add_argument('--delay', type=float, default=5.0, help='Delay in seconds between trades')
    parser.add_argument('--min-ratio', type=float, default=None, help='Minimum required payout ratio')
    
    args = parser.parse_args()
    
    token = os.getenv('DERIV_API_TOKEN')
    app_id = os.getenv('DERIV_APP_ID')
    
    bot = TouchAnomalyBot(
        app_id=app_id,
        token=token,
        stake=args.stake,
        barrier_offset=args.barrier,
        duration_m=args.duration,
        mode=args.mode,
        target_symbol=args.symbol,
        max_trades=args.max_trades,
        take_profit=args.take_profit,
        stop_loss=args.stop_loss,
        delay=args.delay,
        min_ratio=args.min_ratio
    )
    
    asyncio.run(bot.run())

if __name__ == '__main__':
    main()
