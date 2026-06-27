import os
import zipfile
import requests
import pandas as pd
from datetime import datetime, timedelta

def download_data(date_str):
    url = f"https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{date_str}.zip"
    zip_path = f"BTCUSDT-aggTrades-{date_str}.zip"
    csv_path = f"BTCUSDT-aggTrades-{date_str}.csv"
    
    if not os.path.exists(csv_path):
        if not os.path.exists(zip_path):
            print(f"Baixando dados da Binance: {url}")
            response = requests.get(url)
            if response.status_code == 200:
                with open(zip_path, 'wb') as f:
                    f.write(response.content)
                print("Download concluído.")
            else:
                print(f"Erro no download (Status: {response.status_code}). Tentando dia anterior.")
                return False
                
        print("Extraindo ZIP...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
            
    return csv_path

def run_backtest(csv_path):
    print(f"Carregando CSV {csv_path} na memória (isso pode levar 1 minuto)...")
    # Colunas: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker, is_best_match
    df = pd.read_csv(csv_path, header=None, names=['id', 'price', 'qty', 'f_id', 'l_id', 'time', 'is_bm', 'is_best'])
    
    print(f"Total de Ticks (AggTrades): {len(df)}")
    
    prices = df['price'].values
    times = df['time'].values # in milliseconds
    
    # Parâmetros do Sniper
    THRESHOLD = 50.00
    WINDOW_MS = 500
    MULTIPLIER = 800
    STAKE = 10.0
    COMMISSION = 0.24 # 24% da Stake
    
    opportunities = 0
    total_net_profit = 0.0
    
    # Otimização usando dois ponteiros para janela deslizante
    print("Analisando microestrutura em janelas de 500ms...")
    
    left = 0
    last_trigger_time = 0
    
    for right in range(1, len(times)):
        # Avança o ponteiro da esquerda até ficar dentro da janela de 500ms
        while (times[right] - times[left])/1000.0 > WINDOW_MS:
            left += 1
            
        if left == right:
            continue
            
        # O preço mudou rápido?
        diff = prices[right] - prices[left]
        
        # Só dispara se não tiver disparado no último 1 segundo
        if abs(diff) >= THRESHOLD and ((times[right] - last_trigger_time)/1000.0 > 1000):
            opportunities += 1
            last_trigger_time = times[right]
            
            # Cálculo financeiro
            pct_move = abs(diff) / prices[left]
            gross_profit = pct_move * MULTIPLIER * STAKE
            net_profit = gross_profit - (STAKE * COMMISSION)
            total_net_profit += net_profit
            
            dir_str = "UP" if diff > 0 else "DOWN"
            print(f"[{pd.to_datetime(times[right], unit='us')}] Choque de {dir_str}: ${diff:.2f} em {(times[right] - times[left])/1000.0}ms -> Lucro Líquido: ${net_profit:.2f}")

    print("\n" + "="*40)
    print("📊 RESULTADOS DO BACKTEST HFT")
    print("="*40)
    print(f"Janela de Tempo: 1 Dia de Operação")
    print(f"Tiros Disparados (Price Shocks > $50): {opportunities}")
    if opportunities > 0:
        print(f"Lucro Líquido Total Esperado: ${total_net_profit:.2f}")
        print(f"Lucro Médio por Tiro: ${total_net_profit/opportunities:.2f}")
    print("="*40)

if __name__ == "__main__":
    # Tenta ontem
    target_date = datetime.utcnow() - timedelta(days=1)
    date_str = target_date.strftime("%Y-%m-%d")
    
    csv_path = download_data(date_str)
    
    if not csv_path:
        # Tenta anteontem
        target_date = datetime.utcnow() - timedelta(days=2)
        date_str = target_date.strftime("%Y-%m-%d")
        csv_path = download_data(date_str)
        
    if csv_path:
        run_backtest(csv_path)
