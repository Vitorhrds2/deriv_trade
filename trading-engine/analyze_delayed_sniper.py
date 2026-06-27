import pandas as pd
import numpy as np

def run_delayed_sniper(csv_path):
    print("Carregando dados...")
    df = pd.read_csv(csv_path, header=None, names=['id', 'price', 'qty', 'f_id', 'l_id', 'time', 'is_bm', 'is_best'])
    prices = df['price'].values
    times = df['time'].values # microseconds
    
    THRESHOLD = 20.00
    WAIT_MS = 350
    
    # Parâmetros Deriv
    DERIV_DELAY = 690
    EXEC_DELAY = 250
    HOLD_TIME = 1000
    
    MULTIPLIER = 800
    STAKE = 10.0
    COMMISSION = 0.24 # 24% of stake -> $2.40 spread
    
    print("Buscando oportunidades...")
    
    results = []
    
    left = 0
    last_trigger_time = 0
    
    for right in range(1, len(times)):
        # Janela de 200ms para identificar o pulo inicial
        while (times[right] - times[left])/1000.0 > 200:
            left += 1
            
        if left == right:
            continue
            
        diff = prices[right] - prices[left]
        
        if abs(diff) >= THRESHOLD and ((times[right] - last_trigger_time)/1000.0 > 2000):
            # T0 = times[right]
            t0_ms = times[right] / 1000.0
            t_base_ms = times[left] / 1000.0
            
            # Encontrar o preço em T0 + WAIT_MS (momento da decisão)
            idx_wait = right
            while idx_wait < len(times) and (times[idx_wait]/1000.0 - t0_ms) < WAIT_MS:
                idx_wait += 1
            if idx_wait >= len(times): break
            
            price_at_wait = prices[idx_wait]
            diff_at_wait = price_at_wait - prices[left]
            
            # Condição do Sniper Atrasado: O preço AINDA tem que estar alto após WAIT_MS
            if (diff > 0 and diff_at_wait >= THRESHOLD * 0.8) or (diff < 0 and diff_at_wait <= -THRESHOLD * 0.8):
                # O salto sustentou! Disparar tiro!
                last_trigger_time = times[right]
                
                # Calcular preço de entrada na Deriv: T0 + WAIT_MS + EXEC_DELAY - DERIV_DELAY
                t_entry_deriv_ms = t0_ms + WAIT_MS + EXEC_DELAY - DERIV_DELAY
                idx_entry = right
                # voltar para achar o preço no passado
                while idx_entry > 0 and (times[idx_entry]/1000.0 > t_entry_deriv_ms):
                    idx_entry -= 1
                entry_price_deriv = prices[idx_entry]
                
                # Calcular preço de saída na Deriv: T0 + WAIT_MS + HOLD_TIME - DERIV_DELAY
                # A ordem de venda é enviada em T0 + WAIT_MS + HOLD_TIME, e preenchida quase imediatamente
                # O preço na Deriv reflete a Binance em T_sell - DERIV_DELAY
                t_exit_deriv_ms = t0_ms + WAIT_MS + HOLD_TIME - DERIV_DELAY
                idx_exit = right
                while idx_exit < len(times) and (times[idx_exit]/1000.0 < t_exit_deriv_ms):
                    idx_exit += 1
                if idx_exit >= len(times): break
                exit_price_deriv = prices[idx_exit]
                
                # Calcula lucro
                trade_diff = exit_price_deriv - entry_price_deriv
                if diff < 0: # aposta DOWN
                    trade_diff = -trade_diff
                    
                pct_move = trade_diff / entry_price_deriv
                gross_profit = pct_move * MULTIPLIER * STAKE
                net_profit = gross_profit - (STAKE * COMMISSION)
                
                results.append({
                    't0': t0_ms,
                    'jump_at_t0': diff,
                    'jump_at_wait': diff_at_wait,
                    'entry_price': entry_price_deriv,
                    'exit_price': exit_price_deriv,
                    'net_profit': net_profit
                })
                
    res_df = pd.DataFrame(results)
    print(f"\n--- Backtest: Delayed Sniper (Wait {WAIT_MS}ms) ---")
    if res_df.empty:
        print("Nenhum trade passou pelo filtro de sustentação.")
    else:
        print(f"Total Trades: {len(res_df)}")
        print(f"Win Rate: {(res_df['net_profit'] > 0).mean() * 100:.2f}%")
        print(f"Lucro Total: ${res_df['net_profit'].sum():.2f}")
        print(f"Lucro Médio: ${res_df['net_profit'].mean():.2f}")
        print(f"Pior Loss: ${res_df['net_profit'].min():.2f}")
        print(f"Maior Gain: ${res_df['net_profit'].max():.2f}")
        
if __name__ == "__main__":
    run_delayed_sniper("BTCUSDT-aggTrades-2026-06-25.csv")
