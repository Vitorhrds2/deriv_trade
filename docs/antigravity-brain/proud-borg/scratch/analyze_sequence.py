import pandas as pd
import sys

file_path = "/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/historico_trades_maio.csv"
df = pd.read_csv(file_path)

df['buy_price'] = df['buy_price'].astype(float)
df['sell_price'] = df['sell_price'].astype(float)
df['pnl'] = df['sell_price'] - df['buy_price']
df['purchase_time'] = pd.to_datetime(df['purchase_time'])
df = df.sort_values(by=['purchase_time', 'transaction_id'])

print("Primeiros 30 trades (cronológico):")
for idx, row in df.head(30).iterrows():
    print(f"{row['purchase_time']} | {row['contract_type']} | Stake: {row['buy_price']} | PnL: {row['pnl']:.2f}")

print("\nVerificando sobreposição de trades:")
counts = df.groupby('purchase_time').size()
print(counts.value_counts())
