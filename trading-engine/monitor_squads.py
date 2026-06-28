"""Monitor recorrente da Batalha dos Esquadrões.

Lê os logs isolados de cada esquadrão (logs/skynet/skynet_global_<MODE>_C*.log) e
imprime um placar consolidado de PnL Global, Wins/Losses e WinRate.

Uso:
    python monitor_squads.py                 # snapshot único
    python monitor_squads.py --watch 30      # atualiza a cada 30s
    python monitor_squads.py --mode REAL     # outro ambiente
"""
import glob
import os
import re
import sys
import time

LOG_DIR = os.path.join("logs", "skynet")
PNL_RE = re.compile(r"PNL GLOBAL: \$(-?[\d\.]+)")
SQUAD_RE = re.compile(r"_C(\d+)\.log$")


def summarize(mode):
    rows = []
    pattern = os.path.join(LOG_DIR, f"skynet_global_{mode}_C*.log")
    for path in sorted(glob.glob(pattern)):
        m = SQUAD_RE.search(path)
        squad = f"{m.group(1)}%" if m else "?"
        pnl, wins, losses, last = None, 0, 0, ""
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "✅ WIN" in line:
                        wins += 1
                    elif "❌ LOSS" in line:
                        losses += 1
                    pm = PNL_RE.search(line)
                    if pm:
                        pnl = float(pm.group(1))
                    if line.startswith("[") and len(line) > 20:
                        last = line[1:20]
        except OSError:
            continue
        total = wins + losses
        wr = (wins / total * 100) if total else 0.0
        rows.append({"squad": squad, "pnl": pnl, "wins": wins,
                     "losses": losses, "wr": wr, "last": last})
    return rows


def render(rows, mode):
    print(f"\n=== BATALHA DOS ESQUADRÕES ({mode}) | {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    if not rows:
        print("(nenhum log de esquadrão encontrado ainda)")
        return
    print(f"{'ESQUADRÃO':<11}{'PNL GLOBAL':<14}{'W':<6}{'L':<6}{'WR':<9}{'ÚLT. ATIVIDADE':<20}")
    print("-" * 66)
    leader = None
    for r in rows:
        pnl_txt = f"${r['pnl']:.2f}" if r["pnl"] is not None else "n/a"
        wr_txt = f"{r['wr']:.1f}%"
        print(f"{r['squad']:<11}{pnl_txt:<14}{r['wins']:<6}{r['losses']:<6}{wr_txt:<9}{r['last']:<20}")
        if r["pnl"] is not None and (leader is None or r["pnl"] > leader["pnl"]):
            leader = r
    if leader:
        print("-" * 66)
        print(f"🏆 Líder atual: Esquadrão {leader['squad']} com ${leader['pnl']:.2f}")


def main():
    argv = sys.argv[1:]
    mode = "DEMO"
    watch = 0
    if "--mode" in argv:
        mode = argv[argv.index("--mode") + 1]
    if "--watch" in argv:
        i = argv.index("--watch")
        watch = int(argv[i + 1]) if i + 1 < len(argv) else 30
    while True:
        render(summarize(mode), mode)
        if not watch:
            break
        time.sleep(watch)


if __name__ == "__main__":
    main()
