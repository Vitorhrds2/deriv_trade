#!/usr/bin/env python3
import json
import os
import glob

files = [
    'd107_results_r100_trade1.jsonl',
    'd107_results_r100_session2_16trades.jsonl',
    'd107_results_r100_session3.jsonl',
    'd107_rate_limit_winner_holding_results.jsonl',
]

r100_trades = []

for fpath in files:
    if not os.path.exists(fpath):
        continue
    with open(fpath) as f:
        trades_map = {}
        for line in f:
            line = line.strip()
            if not line:
                continue
            evt = json.loads(line)
            cid = evt.get('contract_id')
            ev_type = evt.get('event')
            if ev_type == 'buy_confirmed':
                trades_map[cid] = {
                    'cid': cid,
                    'file': fpath,
                    'buy_price': evt.get('buy_price', 1.10),
                    'stake': evt.get('stake', 1.00),
                    'fee': evt.get('cancellation_fee', 0.10),
                    'direction': evt.get('direction'),
                    'outcome': None,
                    'sold_for': None,
                    'pnl': None,
                }
            elif ev_type == 'sell_confirmed':
                if cid in trades_map:
                    t = trades_map[cid]
                    t['outcome'] = 'WINNER_SOLD'
                    t['sold_for'] = evt.get('sold_for', 0.0)
                    t['pnl'] = evt.get('realized_pnl', t['sold_for'] - t['buy_price'])
            elif ev_type == 'cancel_confirmed':
                if cid in trades_map:
                    t = trades_map[cid]
                    t['outcome'] = 'LOSER_CANCELLED'
                    t['sold_for'] = evt.get('sold_for', t['stake'])
                    t['pnl'] = (t['sold_for'] or t['stake']) - t['buy_price']
            elif ev_type == 'unresolved_contract_exit':
                if cid in trades_map:
                    t = trades_map[cid]
                    t['outcome'] = 'UNRESOLVED'
                    t['sold_for'] = evt.get('sold_for', 0.0)
                    t['pnl'] = (t['sold_for'] or 0.0) - t['buy_price']
        for t in trades_map.values():
            if t['outcome'] is not None:
                r100_trades.append(t)

print("=" * 60)
print(f"AUDITORIA FORENSE E QUANTITATIVA: D107 NO ATIVO R_100")
print("=" * 60)
print(f"Total de Trades Concluídos Analisados: {len(r100_trades)}")

winners = [t for t in r100_trades if t['outcome'] == 'WINNER_SOLD']
cancelled = [t for t in r100_trades if t['outcome'] == 'LOSER_CANCELLED']
unresolved = [t for t in r100_trades if t['outcome'] == 'UNRESOLVED']

win_pnl = [t['pnl'] for t in winners]
loss_pnl = [t['pnl'] for t in cancelled]
unres_pnl = [t['pnl'] for t in unresolved]

winners_profitable = [p for p in win_pnl if p > 0]
winners_scratch = [p for p in win_pnl if p <= 0]

gross_profit = sum(p for p in win_pnl if p > 0)
gross_loss = abs(sum(p for p in (win_pnl + loss_pnl + unres_pnl) if p < 0))
net_pnl = sum(t['pnl'] for t in r100_trades)

win_rate = (len(winners_profitable) / len(r100_trades)) * 100 if r100_trades else 0
cancel_rate = (len(cancelled) / len(r100_trades)) * 100 if r100_trades else 0
unresolved_rate = (len(unresolved) / len(r100_trades)) * 100 if r100_trades else 0

pf = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
ev = net_pnl / len(r100_trades) if r100_trades else 0.0
avg_win = sum(winners_profitable) / len(winners_profitable) if winners_profitable else 0.0
avg_loss = sum(loss_pnl) / len(loss_pnl) if loss_pnl else 0.0

print(f"Trades com Lucro Efetivo (Net Profit > 0): {len(winners_profitable)} ({win_rate:.1f}%)")
print(f"Trades Vendidos com Lucro Marginal/Scratch (Net PnL <= 0): {len(winners_scratch)}")
print(f"Trades Perdedores Cancelados (Reembolso integral): {len(cancelled)} ({cancel_rate:.1f}%)")
print(f"Trades Não-Resolvidos / Erros de Rede: {len(unresolved)} ({unresolved_rate:.1f}%)")
print("-" * 60)
print(f"Lucro Bruto Realizado (Ganhos): +${gross_profit:.2f} USD")
print(f"Custos de Cancelamento e Perdas Brutas: -${gross_loss:.2f} USD")
print(f"LUCRO LÍQUIDO REALIZADO TOTAL: +${net_pnl:.2f} USD")
print(f"Profit Factor (Gross Profit / Gross Loss): {pf:.2f}")
print(f"Expected Value (EV Líquido por Trade): +${ev:.4f} USD (+{ev*100:.2f}% por trade de $1.00)")
print(f"Ganho Médio nos Trades Vencedores: +${avg_win:.4f} USD (+{avg_win*100:.1f}%)")
print(f"Custo Médio por Cancelamento Defensivo: -${abs(avg_loss):.4f} USD (-{abs(avg_loss)*100:.1f}%)")
print(f"Payoff Ratio (Ganho Médio / Custo Médio): {avg_win / abs(avg_loss):.2f}x")
print("=" * 60)
