import json
import numpy as np
import matplotlib.pyplot as plt
from scipy import interpolate

def analyze_latency():
    try:
        with open("latency_data.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Data file not found.")
        return

    binance = data.get("binance", [])
    deriv = data.get("deriv", [])

    if len(binance) < 2 or len(deriv) < 2:
        print("Not enough data.")
        return

    b_times = [t["t"] for t in binance]
    b_prices = [t["p"] for t in binance]
    
    d_times = [t["t"] for t in deriv]
    d_prices = [t["p"] for t in deriv]

    # Interpolar em uma grade uniforme de 10ms
    start_time = max(b_times[0], d_times[0])
    end_time = min(b_times[-1], d_times[-1])
    
    common_times = np.arange(start_time, end_time, 0.01) # 10ms steps
    
    # Deriv prices need to be normalized because they might have a constant offset
    f_binance = interpolate.interp1d(b_times, b_prices, kind='previous', fill_value="extrapolate")
    f_deriv = interpolate.interp1d(d_times, d_prices, kind='previous', fill_value="extrapolate")

    b_interp = f_binance(common_times)
    d_interp = f_deriv(common_times)
    
    # Remover média para correlação
    b_norm = b_interp - np.mean(b_interp)
    d_norm = d_interp - np.mean(d_interp)

    # Calcular cross-correlation
    correlation = np.correlate(d_norm, b_norm, mode='full')
    lags = np.arange(-len(b_norm) + 1, len(b_norm)) * 10 # in ms (since step is 0.01s)
    
    # O lag onde a correlação é máxima nos diz o quanto a Deriv está atrasada
    # Lags positivos indicam que o sinal 1 (Deriv) está atrasado em relação ao sinal 2 (Binance)
    best_lag_idx = np.argmax(correlation)
    best_lag_ms = lags[best_lag_idx]
    
    max_corr = correlation[best_lag_idx] / (np.std(b_norm) * np.std(d_norm) * len(b_norm))
    
    print(f"Delay da Deriv em relação à Binance: {best_lag_ms} ms")
    print(f"Correlação Máxima: {max_corr:.2f}")

    # Plotar
    plt.figure(figsize=(12, 6))
    
    plt.subplot(2, 1, 1)
    plt.plot(common_times - start_time, b_interp, label="Binance BTC/USDT")
    plt.plot(common_times - start_time, d_interp, label="Deriv BTC/USD")
    plt.title("Preços (Sem Sincronização)")
    plt.legend()
    
    plt.subplot(2, 1, 2)
    plt.plot(lags, correlation)
    plt.axvline(x=best_lag_ms, color='r', linestyle='--', label=f'Lag Ótimo: {best_lag_ms}ms')
    plt.title("Cross-Correlation")
    plt.xlabel("Lag (ms)")
    plt.xlim(-5000, 5000) # Mostrar +- 5 segundos
    plt.legend()
    
    plt.tight_layout()
    plt.savefig('latency_correlation.png', dpi=300)
    print("Plot salvo em latency_correlation.png")

if __name__ == "__main__":
    analyze_latency()
