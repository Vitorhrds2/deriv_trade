import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

def analyze_periods(csv_path):
    print(f"Carregando CSV {csv_path} na memória...")
    df = pd.read_csv(csv_path, header=None, names=['id', 'price', 'qty', 'f_id', 'l_id', 'time', 'is_bm', 'is_best'])
    
    prices = df['price'].values
    times = df['time'].values # in microseconds
    
    THRESHOLD = 50.00
    WINDOW_MS = 500
    MULTIPLIER = 800
    STAKE = 10.0
    COMMISSION = 0.24 # 24% da Stake
    
    left = 0
    last_trigger_time = 0
    
    results = []
    
    print("Analisando microestrutura...")
    for right in range(1, len(times)):
        while (times[right] - times[left])/1000.0 > WINDOW_MS:
            left += 1
            
        if left == right:
            continue
            
        diff = prices[right] - prices[left]
        
        if abs(diff) >= THRESHOLD and ((times[right] - last_trigger_time)/1000.0 > 1000):
            last_trigger_time = times[right]
            
            pct_move = abs(diff) / prices[left]
            gross_profit = pct_move * MULTIPLIER * STAKE
            net_profit = gross_profit - (STAKE * COMMISSION)
            
            direction = "UP" if diff > 0 else "DOWN"
            dt = pd.to_datetime(times[right], unit='us')
            
            results.append({
                'timestamp': dt,
                'hour': dt.hour,
                'direction': direction,
                'jump': abs(diff),
                'net_profit': net_profit
            })
            
    res_df = pd.DataFrame(results)
    
    if res_df.empty:
        print("Nenhum trade encontrado.")
        return
        
    # Agrupar por hora
    hourly = res_df.groupby('hour').agg(
        trades=('net_profit', 'count'),
        total_profit=('net_profit', 'sum'),
        avg_profit=('net_profit', 'mean'),
        max_jump=('jump', 'max')
    ).reindex(range(24), fill_value=0)
    
    # Gerar Gráfico
    plt.figure(figsize=(12, 6))
    bars = plt.bar(hourly.index, hourly['total_profit'], color='skyblue', edgecolor='black')
    plt.title('Lucratividade Total por Hora do Dia (UTC) - Arbitragem HFT', fontsize=14)
    plt.xlabel('Hora do Dia (0-23 UTC)', fontsize=12)
    plt.ylabel('Lucro Líquido ($)', fontsize=12)
    plt.xticks(range(24))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Adicionar labels nas barras
    for bar in bars:
        yval = bar.get_height()
        if yval > 0:
            plt.text(bar.get_x() + bar.get_width()/2, yval + 1, f"${yval:.0f}", ha='center', va='bottom', fontsize=9)
            
    plt.savefig('profit_by_hour.png', dpi=300, bbox_inches='tight')
    print("Gráfico salvo como profit_by_hour.png")
    
    print("\n--- Relatório Estatístico por Hora ---")
    print(hourly)
    
    print("\n--- Separação por Turnos ---")
    turnos = {
        'Madrugada (00:00 - 05:59)': res_df[res_df['hour'].between(0, 5)],
        'Manhã (06:00 - 11:59)': res_df[res_df['hour'].between(6, 11)],
        'Tarde (12:00 - 17:59)': res_df[res_df['hour'].between(12, 17)],
        'Noite (18:00 - 23:59)': res_df[res_df['hour'].between(18, 23)]
    }
    
    for nome, t_df in turnos.items():
        t_trades = len(t_df)
        t_profit = t_df['net_profit'].sum() if t_trades > 0 else 0
        print(f"{nome}: {t_trades} trades | Lucro: ${t_profit:.2f}")

if __name__ == "__main__":
    analyze_periods("BTCUSDT-aggTrades-2026-06-25.csv")
