import pandas as pd
import numpy as np
import os
import zipfile
import urllib.request
from datetime import datetime, timedelta

def download_binance_data(symbol, date_str):
    zip_name = f"{symbol}-aggTrades-{date_str}.zip"
    csv_name = f"{symbol}-aggTrades-{date_str}.csv"
    
    if os.path.exists(csv_name):
        return csv_name
        
    url = f"https://data.binance.vision/data/spot/daily/aggTrades/{symbol}/{zip_name}"
    print(f"Baixando {url}...")
    try:
        urllib.request.urlretrieve(url, zip_name)
        with zipfile.ZipFile(zip_name, 'r') as zip_ref:
            zip_ref.extractall(".")
        os.remove(zip_name)
        return csv_name
    except Exception as e:
        print(f"Erro ao baixar {date_str}: {e}")
        return None

def analyze_day(csv_path):
    print(f"Analisando {csv_path}...")
    df = pd.read_csv(csv_path, header=None, names=['id', 'price', 'qty', 'f_id', 'l_id', 'time', 'is_bm', 'is_best'])
    prices = df['price'].values
    times = df['time'].values # em milissegundos ou microsegundos? Em aggTrades costuma ser ms
    
    # Binance daily aggTrades 'time' column is in UNIX milliseconds.
    # Mas verificando o formato do script anterior, parece que usou micros ou millis, no último eu dividi por 1000 se fosse micro.
    # aggTrades padrão é milissegundos (timestamp 13 digitos).
    if times[0] > 1e14:
        # Microseconds
        times = times / 1000.0
        
    THRESHOLD = 50.00
    WAIT_MS = 2000 # 2 segundos completos
    
    MULTIPLIER = 800
    STAKE = 10.0
    COMMISSION = 0.24 # $2.40 de taxa
    
    left = 0
    last_trigger_time = 0
    
    wins = 0
    losses = 0
    total_profit = 0.0
    
    for right in range(1, len(times)):
        # janela de 500ms
        while (times[right] - times[left]) > 500:
            left += 1
            
        if left == right:
            continue
            
        diff = prices[right] - prices[left]
        
        if abs(diff) >= THRESHOLD and (times[right] - last_trigger_time > 5000):
            t0 = times[right]
            
            # Buscar o preço exato em t0 + 2000ms
            idx_wait = right
            while idx_wait < len(times) and (times[idx_wait] - t0) < WAIT_MS:
                idx_wait += 1
                
            if idx_wait >= len(times): break
            
            price_at_2s = prices[idx_wait]
            sustained_diff = price_at_2s - prices[left]
            
            # Avalia o trade supondo que saímos em 2s
            trade_diff = sustained_diff if diff > 0 else -sustained_diff
            
            pct_move = trade_diff / prices[left]
            gross_profit = pct_move * MULTIPLIER * STAKE
            net_profit = gross_profit - (STAKE * COMMISSION)
            
            if trade_diff > 0 and net_profit > 0:
                wins += 1
            else:
                losses += 1
                
            total_profit += net_profit
            last_trigger_time = times[right]
            
    return wins, losses, total_profit

if __name__ == "__main__":
    start_date = datetime(2026, 6, 19)
    days = 7
    symbol = "BTCUSDT"
    
    results = []
    
    print("Iniciando backtest semanal de rompimentos estruturais > 2 segundos...")
    for i in range(days):
        d = start_date + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        
        csv_path = download_binance_data(symbol, d_str)
        if csv_path:
            w, l, p = analyze_day(csv_path)
            total_trades = w + l
            win_rate = (w / total_trades * 100) if total_trades > 0 else 0
            results.append({
                'Data': d_str,
                'Rompimentos >$50': total_trades,
                'Sucesso (Sustentou 2s+) (%)': f"{win_rate:.1f}%",
                'Lucro Líquido ($)': p
            })
            print(f"Data: {d_str} | Trades: {total_trades} | Lucro: ${p:.2f}")
            
    res_df = pd.DataFrame(results)
    print("\n" + "="*50)
    print("RELATÓRIO SEMANAL: SUSTENTAÇÃO DE 2 SEGUNDOS ($50)")
    print("="*50)
    print(res_df.to_markdown(index=False))
    
    with open('weekly_sustained_report.md', 'w') as f:
        f.write("# Relatório de Rupturas Estruturais (Janela de 2 Segundos)\n\n")
        f.write("Backtest para responder à pergunta: 'Quantas vezes na última semana a Binance manteve um pulo de $50 no topo por mais de 2 segundos inteiros sem reverter?'\n\n")
        f.write(res_df.to_markdown(index=False))
