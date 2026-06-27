
import matplotlib.pyplot as plt
import numpy as np

def plot_histogram():
    try:
        with open("boom_distances.txt", "r") as f:
            distances = [int(line.strip()) for line in f.readlines()]
    except FileNotFoundError:
        return
        
    plt.figure(figsize=(10, 6))
    
    # Histogram of actual data
    counts, bins, _ = plt.hist(distances, bins=50, density=True, alpha=0.6, color='blue', label='Dados Reais (Boom 500)')
    
    # Theoretical exponential distribution
    mean_dist = np.mean(distances)
    x = np.linspace(0, max(distances), 100)
    pdf = (1 / mean_dist) * np.exp(-x / mean_dist)
    plt.plot(x, pdf, 'r-', lw=2, label=f'Distribuição Exponencial Teórica (Média={mean_dist:.0f})')
    
    plt.title('Distribuição da Distância (em Ticks) entre Spikes no BOOM 500')
    plt.xlabel('Ticks entre Spikes')
    plt.ylabel('Densidade de Probabilidade')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.savefig('boom_histogram.png', dpi=300, bbox_inches='tight')
    print("Plot saved to boom_histogram.png")

if __name__ == "__main__":
    plot_histogram()
