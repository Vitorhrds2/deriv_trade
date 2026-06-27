import subprocess
import time
import os

print("🔥 Iniciando a Mega Arena HFT (6 Teses Parametrizadas)...")

os.makedirs('logs/arena', exist_ok=True)

commands = [
    # 1. Tese 1 (Controle Dinâmico): Janela de 1000, 1 VL, DIGITDIFF
    ".venv/bin/python oracle_diff_bot_6.py --window 1000 --vl 1 --contract DIGITDIFF",
    
    # 2. Tese 2 (Memória Curta): Janela de 500, 1 VL, DIGITDIFF
    ".venv/bin/python oracle_diff_bot_6.py --window 500 --vl 1 --contract DIGITDIFF",
    
    # 3. Tese 3 (Memória Longa): Janela de 2000, 1 VL, DIGITDIFF
    ".venv/bin/python oracle_diff_bot_6.py --window 2000 --vl 1 --contract DIGITDIFF",
    
    # 4. Tese 4 (Sniper Duplo): Janela de 1000, 2 VLs consecutivos, DIGITDIFF
    ".venv/bin/python oracle_diff_bot_6.py --window 1000 --vl 2 --contract DIGITDIFF",
    
    # 5. Tese 5 (Caçador de Cisnes): Janela de 1000, 1 VL, DIGITMATCH
    ".venv/bin/python oracle_diff_bot_6.py --window 1000 --vl 1 --contract DIGITMATCH",
    
    # 6. Tese 6 (O Controle Clássico - Estático)
    ".venv/bin/python oracle_diff_bot_2.py"
]

processes = []

for cmd in commands:
    print(f"🚀 Lançando processo: {cmd}")
    # Usando Popen para rodar assincronamente (background nativo do OS)
    p = subprocess.Popen(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes.append(p)
    time.sleep(2) # Evitar rate limit de WS na inicialização

print("✅ Todos os 6 robôs foram lançados! A Mega Arena está ativa no plano de fundo do seu OS.")
print("Eles rodarão até você interromper os processos do terminal ou reiniciar a máquina.")

try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("\n🛑 Encerrando a Mega Arena...")
    for p in processes:
        p.terminate()
    print("Arena encerrada.")
