import asyncio
import os
import json
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from deriv_client import DerivClient
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

def calculate_rsi(data, window=14):
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data, slow=26, fast=12, signal=9):
    exp1 = data['close'].ewm(span=fast, adjust=False).mean()
    exp2 = data['close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

async def fetch_data():
    print("Conectando à Deriv para baixar o histórico (5000 velas de 1 minuto)...")
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    
    res = await client.send_request({
        "ticks_history": "cryBTCUSD",
        "end": "latest",
        "count": 5000,
        "style": "candles",
        "granularity": 60
    })
    
    await client.disconnect()
    
    if "candles" not in res:
        print("Erro ao obter dados:", res)
        return None
        
    return res["candles"]

async def main():
    candles = await fetch_data()
    if not candles:
        return
        
    print(f"✅ {len(candles)} velas baixadas com sucesso!")
    
    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['epoch'], unit='s')
    df = df.set_index('time')
    
    # Feature Engineering
    print("Calculando features técnicas...")
    df['returns'] = df['close'].pct_change()
    df['rsi'] = calculate_rsi(df)
    df['macd'], df['macd_signal'] = calculate_macd(df)
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['volatility'] = df['returns'].rolling(window=20).std()
    
    # Target: 1 se a próxima vela for de alta, 0 se for de baixa
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    
    # Remove NaN causados pelo rolling e shift
    df = df.dropna()
    
    # Variáveis preditoras
    features = ['rsi', 'macd', 'macd_signal', 'returns', 'volatility']
    X = df[features]
    y = df['target']
    
    # Divisão Temporal (NÃO podemos fazer shuffle em séries temporais!)
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Treinando RandomForest... (Train: {len(X_train)}, Test: {len(X_test)})")
    model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    
    print("\n" + "="*40)
    print("📊 RESULTADOS DO MODELO DE MACHINE LEARNING")
    print("="*40)
    print(f"Acurácia Global: {accuracy_score(y_test, y_pred):.4f}")
    print("\nRelatório de Classificação:")
    print(classification_report(y_test, y_pred))
    print("="*40)
    
    # Feature Importance
    importances = model.feature_importances_
    for i, v in enumerate(importances):
        print(f"Feature '{features[i]}': {v:.4f}")

if __name__ == "__main__":
    asyncio.run(main())
