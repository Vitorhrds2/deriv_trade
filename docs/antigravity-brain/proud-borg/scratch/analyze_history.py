import pandas as pd
import sys
import numpy as np
from datetime import datetime

file_path = "/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/historico_trades_maio.csv"

try:
    df = pd.read_csv(file_path)
except Exception as e:
    print(f"Error reading file: {e}")
    sys.exit(1)

# Inspect columns
print("=== COLUNAS DO ARQUIVO ===")
print(df.columns.tolist())

# Basic cleaning
df['buy_price'] = df['buy_price'].astype(float)
df['sell_price'] = df['sell_price'].astype(float)
df['pnl'] = df['sell_price'] - df['buy_price']
df['purchase_time'] = pd.to_datetime(df['purchase_time'])
df['sell_time'] = pd.to_datetime(df['sell_time'])
df['duration_seconds'] = (df['sell_time'] - df['purchase_time']).dt.total_seconds()

wins = df[df['pnl'] > 0]
losses = df[df['pnl'] < 0]

print("\n=== RESUMO GERAL ===")
print(f"Total Trades: {len(df)}")
print(f"Win Rate: {len(wins)/len(df)*100:.2f}%")
print(f"Gross PnL: ${df['pnl'].sum():.2f}")
print(f"Average Win: ${wins['pnl'].mean():.2f}")
print(f"Average Loss: ${losses['pnl'].mean():.2f}")
print(f"Max Win: ${wins['pnl'].max():.2f}")
print(f"Max Loss: ${losses['pnl'].min():.2f}")

print("\n=== STAKES & MULTIPLIERS ===")
if 'shortcode' in df.columns:
    # Example shortcode: MULTUP_1HZ10V_10.00_1000_...
    # Extracts info from shortcode if present
    print("Amostra de shortcodes:")
    print(df['shortcode'].head(5).tolist())

print("\n=== CONTRATOS (Tipos) ===")
if 'contract_type' in df.columns:
    print(df['contract_type'].value_counts())
elif 'shortcode' in df.columns:
    # extract contract type from shortcode
    df['type'] = df['shortcode'].apply(lambda x: x.split('_')[0] if isinstance(x, str) else 'UNKNOWN')
    print(df['type'].value_counts())

print("\n=== DURAÇÃO DOS TRADES ===")
print(f"Tempo Médio: {df['duration_seconds'].mean():.1f}s")
print(f"Mediana: {df['duration_seconds'].median():.1f}s")
print(f"Menor Duração: {df['duration_seconds'].min()}s")
print(f"Maior Duração: {df['duration_seconds'].max()}s")

print("\n=== TIER SYSTEM (Stakes Used) ===")
print(df['buy_price'].value_counts().head(10))

print("\n=== LUCROS E PERDAS FREQUENTES ===")
print("Top 5 PnL Ganhos (Frequência):")
print(wins['pnl'].round(2).value_counts().head(5))
print("Top 5 PnL Perdas (Frequência):")
print(losses['pnl'].round(2).value_counts().head(5))

print("\n=== FREQUÊNCIA DE TRADING ===")
df['date'] = df['purchase_time'].dt.date
print(df.groupby('date').size())
