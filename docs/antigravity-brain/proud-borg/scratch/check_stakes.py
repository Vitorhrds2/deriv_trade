import pandas as pd

file_path = "/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/historico_trades_maio.csv"
df = pd.read_csv(file_path)
df['buy_price'] = df['buy_price'].astype(float)
df['purchase_time'] = pd.to_datetime(df['purchase_time'])
df = df.sort_values(by=['purchase_time', 'transaction_id'])

# Group by time to get the pairs
pairs = []
for time, group in df.groupby('purchase_time'):
    if len(group) == 2:
        stake = group['buy_price'].iloc[0]
        pnl = group['sell_price'].sum() - group['buy_price'].sum()
        pairs.append({'time': time, 'stake': stake, 'pnl': pnl})

pair_df = pd.DataFrame(pairs)
print(pair_df.head(20))
