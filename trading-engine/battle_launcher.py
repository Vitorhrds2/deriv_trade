"""Batalha dos Esquadrões — roda vários esquadrões em paralelo, cada um com uma
taxa de juros composta DISTINTA e logs ISOLADOS.

Corrige o bug arquitetônico onde todos os esquadrões viravam clones de 25%:
cada esquadrão é um `multi_market_orchestrator.py` com seu próprio `--compound`,
gravando em `logs/skynet/skynet_global_DEMO_C<taxa>.log`.

Uso:
    python battle_launcher.py            # esquadrões padrão: 0%, 25%, 50%
    python battle_launcher.py 25 50      # apenas 25% e 50%
    python battle_launcher.py 0 25 50    # com controle de 0%

Veredito anterior: 100% = ruína (aposentado). O objetivo agora é coroar 25% vs 50%.
"""
import os
import subprocess
import sys
import time

# Percentuais de juros compostos (Fase 1) por esquadrão.
percents = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [0, 25, 50]

child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

print("=" * 70)
print("⚔️  BATALHA DOS ESQUADRÕES (DEMO) — comparação de EV por taxa de juros")
print(f"Esquadrões: {[f'{p}%' for p in percents]}  (5 mercados cada)")
print("=" * 70)

processes = []
for p in percents:
    rate = p / 100.0
    cmd = [sys.executable, "multi_market_orchestrator.py", "--compound", str(rate)]
    print(f"🚀 Lançando Esquadrão C{p} -> {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, env=child_env)
    processes.append((p, proc))
    time.sleep(3)  # escalonar para não estourar rate-limit de WebSocket

print("\n✅ Esquadrões no ar. Logs isolados em logs/skynet/skynet_global_DEMO_C<taxa>.log")
print("📡 Acompanhe com:  python monitor_squads.py --watch 30")
print("🛑 Ctrl+C encerra todos os esquadrões.\n")

try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    print("\n🛑 Encerrando a Batalha...")
    for p, proc in processes:
        proc.terminate()
    print("Batalha encerrada.")
