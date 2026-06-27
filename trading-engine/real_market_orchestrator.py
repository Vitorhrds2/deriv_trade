import subprocess
import time
import os

print("🌐 Iniciando a Skynet HFT REAL (Orquestração Multi-Mercado em Conta Real)...")

os.makedirs('logs/skynet', exist_ok=True)

STAKE = 0.20
WINDOW = 1000
VL = 2
SOROS = 99
MODE = "REAL"

markets = [
    "1HZ10V",   # Volatility 10 (1s) Index
    "1HZ25V",   # Volatility 25 (1s) Index
    "1HZ50V",   # Volatility 50 (1s) Index
    "1HZ75V",   # Volatility 75 (1s) Index
    "1HZ100V"   # Volatility 100 (1s) Index
]

processes = []

for symbol in markets:
    cmd = f".venv/bin/python oracle_diff_bot_6.py --symbol {symbol} --stake {STAKE} --window {WINDOW} --vl {VL} --soros {SOROS} --mode {MODE} --envfile .env --freeroll"
    print(f"🚀 Lançando Skynet Node [{MODE} - {symbol}]: {cmd}")
    
    p = subprocess.Popen(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes.append(p)
    time.sleep(2)

print(f"✅ Skynet {MODE} Online. Aposta Base de $0.20 com Soros Infinito (99).")

try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print(f"\n🛑 Derrubando a Skynet {MODE}...")
    for p in processes:
        p.terminate()
    print("Orquestração REAL encerrada.")
