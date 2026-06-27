import subprocess
import time
import os
import threading
import re
import sys
from datetime import datetime

print("🌐 Iniciando a Skynet HFT DEMO (Orquestração Multi-Mercado)...")

os.makedirs('logs/skynet', exist_ok=True)

STAKE = 60.00
WINDOW = 1000
VL = 2
SOROS = 3
MODE = "DEMO"
FREEROLL = True

markets = [
    "1HZ10V",   # Volatility 10 (1s) Index
    "1HZ25V",   # Volatility 25 (1s) Index
    "R_10",     # Volatility 10 Index (2s)
    "RDBEAR",   # Bear Market Index
    "RDBULL"    # Bull Market Index
]

global_pnl = 0.0
pnl_lock = threading.Lock()
log_file = open(f'logs/skynet/skynet_global_{MODE}.log', 'a', encoding='utf-8')

def log_global(line, is_important=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_line = f"[{timestamp}] {line.strip()}\n"
    log_file.write(formatted_line)
    log_file.flush()
    if is_important:
        sys.stdout.write(formatted_line)
        sys.stdout.flush()

def monitor_bot(process, symbol):
    global global_pnl
    # Capturar lucro ou prejuízo
    win_pattern = re.compile(r"✅ WIN \| Lucro: \+\$([\d\.]+)")
    loss_pattern = re.compile(r"❌ LOSS \| Prejuízo: \$\-?([\d\.]+)")

    for line in iter(process.stdout.readline, b''):
        decoded_line = line.decode('utf-8').strip()
        if not decoded_line: continue
        
        is_important = False
        pnl_changed = False
        
        win_match = win_pattern.search(decoded_line)
        if win_match:
            profit = float(win_match.group(1))
            with pnl_lock:
                global_pnl += profit
            is_important = True
            pnl_changed = True
            
        loss_match = loss_pattern.search(decoded_line)
        if loss_match:
            loss = float(loss_match.group(1))
            with pnl_lock:
                global_pnl -= loss
            is_important = True
            pnl_changed = True

        if any(icon in decoded_line for icon in ["💥", "🔫", "🛡️", "📈", "🎯", "⚠️"]):
            is_important = True

        if pnl_changed:
            with pnl_lock:
                decoded_line += f" | 🌍 PNL GLOBAL: ${global_pnl:.2f}"
                
        # Limpar o prefixo do log do bot
        clean_line = re.sub(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ - BOT_[^:]+:(INFO|WARNING|ERROR|DEBUG):', f'[{symbol}] ', decoded_line)

        log_global(clean_line, is_important)

processes = []
threads = []

freeroll_flag = "--freeroll" if FREEROLL else ""

for symbol in markets:
    cmd = f".venv/bin/python oracle_diff_bot_6.py --symbol {symbol} --stake {STAKE} --window {WINDOW} --vl {VL} --soros {SOROS} --mode {MODE} --envfile .env {freeroll_flag}"
    print(f"🚀 Lançando Skynet Node [{MODE} - {symbol}]: {cmd}")
    
    p = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    processes.append(p)
    
    t = threading.Thread(target=monitor_bot, args=(p, symbol), daemon=True)
    t.start()
    threads.append(t)
    
    time.sleep(2)

print(f"✅ Skynet {MODE} Online. Acompanhamento Global Ativo. Aposta base: ${STAKE}")
print("==========================================================================================")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print(f"\n🛑 Derrubando a Skynet {MODE}...")
    for p in processes:
        p.terminate()
    log_file.close()
    print(f"Orquestração encerrada. PnL Global Final: ${global_pnl:.2f}")
