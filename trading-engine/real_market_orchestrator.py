import subprocess
import time
import os
import threading
import re
import sys
from datetime import datetime
from strategy_utils import WIN_PATTERN, LOSS_PATTERN

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

print("🌐 Iniciando a Skynet HFT REAL (Orquestração Multi-Mercado em Conta Real)...")

os.makedirs('logs/skynet', exist_ok=True)

STAKE = 0.20
WINDOW = 1000
VL = 2
SOROS = 99
MODE = "REAL"
FREEROLL = True

markets = [
    "1HZ10V",   # Volatility 10 (1s) Index
    "1HZ25V",   # Volatility 25 (1s) Index
    "1HZ50V",   # Volatility 50 (1s) Index
    "1HZ75V",   # Volatility 75 (1s) Index
    "1HZ100V"   # Volatility 100 (1s) Index
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
    win_pattern = WIN_PATTERN
    loss_pattern = LOSS_PATTERN

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

child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

for symbol in markets:
    cmd = [sys.executable, "oracle_diff_bot_6.py", "--symbol", symbol,
           "--stake", str(STAKE), "--window", str(WINDOW), "--vl", str(VL),
           "--soros", str(SOROS), "--mode", MODE, "--envfile", ".env"]
    if FREEROLL:
        cmd.append("--freeroll")
    print(f"🚀 Lançando Skynet Node [{MODE} - {symbol}]")
    
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=child_env)
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
    print(f"Orquestração REAL encerrada. PnL Global Final: ${global_pnl:.2f}")
