import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

# 1. Carregar os dados
df = pd.read_csv('multi_exchange_ticks.csv')

# 2. Deslocar a coluna da Deriv para alinhar o tempo (-690ms)
# Nosso CSV tem amostras a cada 50ms (0.050s).
# 690ms / 50ms = 13.8 amostras de atraso (vamos usar 14)
delay_samples = 14
df['deriv_shifted'] = df['deriv'].shift(-delay_samples)

# Remover as linhas com NaN (no final devido ao shift)
df = df.dropna()

print(f"Total de amostras alinhadas: {len(df)}")

# 3. Preparar variáveis X (Binance, Coinbase, Kraken) e Y (Deriv)
X = df[['binance', 'coinbase', 'kraken']]
y = df['deriv_shifted']

# 4. Executar Regressão Linear Múltipla
model = LinearRegression()
model.fit(X, y)

print("\n=== RESULTADOS DA ENGENHARIA REVERSA DO ÍNDICE ===")
print("R² (Score de Previsão):", f"{model.score(X, y):.6f}")

weights = model.coef_
intercept = model.intercept_

print(f"\nPeso Binance:  {weights[0]*100:.2f}%")
print(f"Peso Coinbase: {weights[1]*100:.2f}%")
print(f"Peso Kraken:   {weights[2]*100:.2f}%")
print(f"Constante (Intercept): {intercept:.4f}")

# Calcular volatilidade/amplitude do preço
max_price = y.max()
min_price = y.min()
print(f"\nRange de Preço Deriv: {min_price:.2f} a {max_price:.2f}")

# 5. Salvar a fórmula final em um arquivo
formula = f"Deriv = {weights[0]:.4f}*Binance + {weights[1]:.4f}*Coinbase + {weights[2]:.4f}*Kraken + {intercept:.4f}"
with open('deriv_formula.txt', 'w') as f:
    f.write(formula)
    f.write(f"\nR2: {model.score(X, y):.6f}")

print("\nFórmula salva em deriv_formula.txt")
