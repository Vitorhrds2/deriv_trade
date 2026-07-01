import pandas as pd

file_path = "/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/historico_trades_maio.csv"
df = pd.read_csv(file_path)

df['buy_price'] = df['buy_price'].astype(float)
df['sell_price'] = df['sell_price'].astype(float)
df['pnl'] = df['sell_price'] - df['buy_price']

# Group by purchase_time and check if both are wins
pairs = df.groupby('purchase_time')
dual_wins = 0
for time, group in pairs:
    if len(group) == 2:
        if (group['pnl'] > 0).all():
            dual_wins += 1

print(f"Total de pares onde AMBOS deram lucro: {dual_wins}")
