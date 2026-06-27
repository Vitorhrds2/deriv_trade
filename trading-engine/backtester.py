import sqlite3
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "ticks.db"
SYMBOL = "1HZ100V"

def load_data():
    conn = sqlite3.connect(DB_PATH)
    # Get candles ordered by time
    df = pd.read_sql_query(f"SELECT * FROM candles WHERE symbol='{SYMBOL}' ORDER BY epoch ASC", conn)
    conn.close()
    return df

def calculate_bollinger_bands(df, window=20, num_sd=2.5):
    # Calcular SMA
    df['sma'] = df['close'].rolling(window=window).mean()
    # Calcular Desvio Padrão
    df['std'] = df['close'].rolling(window=window).std()
    # Bandas
    df['upper_band'] = df['sma'] + (df['std'] * num_sd)
    df['lower_band'] = df['sma'] - (df['std'] * num_sd)
    return df

def run_backtest(df, initial_capital=10000, risk_per_trade=0.02):
    capital = initial_capital
    position = 0 # 1 para Long, -1 para Short, 0 para Flat
    entry_price = 0.0
    stake_size = 0.0
    
    trades = []
    equity_curve = []
    
    for idx, row in df.iterrows():
        if pd.isna(row['sma']):
            equity_curve.append(capital)
            continue
            
        current_price = row['close']
        
        # Gerenciamento de posições abertas
        if position == 1: # Estamos Long
            sl_price = entry_price - (2.0 * row['std']) # Stop Loss: 2.0x Desvio Padrão
            if current_price >= row['sma']:
                # Take Profit na média
                profit = (current_price - entry_price) * stake_size
                capital += profit
                trades.append({'type': 'CLOSE_LONG', 'profit': profit, 'price': current_price, 'time': row['timestamp']})
                position = 0
                stake_size = 0.0
            elif current_price < sl_price: 
                # Stop Loss dinâmico
                loss = (current_price - entry_price) * stake_size
                capital += loss
                trades.append({'type': 'STOP_LONG', 'profit': loss, 'price': current_price, 'time': row['timestamp']})
                position = 0
                stake_size = 0.0
                
        elif position == -1: # Estamos Short
            sl_price = entry_price + (2.0 * row['std']) # Stop Loss: 2.0x Desvio Padrão
            if current_price <= row['sma']:
                # Take Profit na média
                profit = (entry_price - current_price) * stake_size
                capital += profit
                trades.append({'type': 'CLOSE_SHORT', 'profit': profit, 'price': current_price, 'time': row['timestamp']})
                position = 0
                stake_size = 0.0
            elif current_price > sl_price: 
                # Stop Loss dinâmico
                loss = (entry_price - current_price) * stake_size
                capital += loss
                trades.append({'type': 'STOP_SHORT', 'profit': loss, 'price': current_price, 'time': row['timestamp']})
                position = 0
                stake_size = 0.0
                
        # Sinais de Entrada (se estiver Flat)
        if position == 0:
            if current_price < row['lower_band']:
                # Sinal de Compra (Mean Reversion)
                position = 1
                entry_price = current_price
                sl_distance = 2.0 * row['std']
                stake_size = (capital * risk_per_trade) / sl_distance if sl_distance > 0 else 0
                trades.append({'type': 'OPEN_LONG', 'price': current_price, 'time': row['timestamp'], 'stake': stake_size})
            elif current_price > row['upper_band']:
                # Sinal de Venda a Descoberto
                position = -1
                entry_price = current_price
                sl_distance = 2.0 * row['std']
                stake_size = (capital * risk_per_trade) / sl_distance if sl_distance > 0 else 0
                trades.append({'type': 'OPEN_SHORT', 'price': current_price, 'time': row['timestamp'], 'stake': stake_size})
                
        # Calcula valor atual da carteira flutuante
        floating_pnl = 0
        if position == 1:
            floating_pnl = (current_price - entry_price) * stake_size
        elif position == -1:
            floating_pnl = (entry_price - current_price) * stake_size
            
        equity_curve.append(capital + floating_pnl)

    df['equity'] = equity_curve
    return df, trades, capital

def analyze_results(df, trades, initial_capital, final_capital):
    pnl = final_capital - initial_capital
    pnl_pct = (pnl / initial_capital) * 100
    
    # Win Rate
    closed_trades = [t for t in trades if 'profit' in t]
    wins = [t for t in closed_trades if t['profit'] > 0]
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
    
    # Maximum Drawdown
    df['peak'] = df['equity'].cummax()
    df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
    max_dd = df['drawdown'].min() * 100
    
    logger.info("="*40)
    logger.info("   RESULTADOS DO BACKTEST: MEAN-REVERSION")
    logger.info("="*40)
    logger.info(f"Total de Velas: {len(df)}")
    logger.info(f"Trades Executados: {len(closed_trades)}")
    logger.info(f"Win Rate: {win_rate:.2f}%")
    logger.info(f"PnL Absoluto: ${pnl:.2f}")
    logger.info(f"Retorno (ROI): {pnl_pct:.2f}%")
    logger.info(f"Max Drawdown: {max_dd:.2f}%")
    logger.info("="*40)

def main():
    logger.info("Carregando dados históricos do banco...")
    df = load_data()
    
    if df.empty:
        logger.error("Nenhum dado encontrado no banco. Execute o history_fetcher.py primeiro.")
        return
        
    logger.info("Calculando Bandas de Bollinger...")
    df = calculate_bollinger_bands(df)
    
    logger.info("Rodando o simulador de backtest...")
    initial_capital = 10000
    df, trades, final_capital = run_backtest(df, initial_capital=initial_capital)
    
    analyze_results(df, trades, initial_capital, final_capital)
    
    # Save results to csv for chart analysis
    df.to_csv("backtest_results.csv", index=False)
    logger.info("Resultados exportados para backtest_results.csv")

if __name__ == "__main__":
    main()
