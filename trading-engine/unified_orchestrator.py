"""Unified orchestrator — replaces arena_launcher, multi_market_orchestrator,
mega_brain_orchestrator, and aws_fleet_manager into a single config-driven entry point.

Modes:
  --config orchestrator.json   Run processes defined in a JSON config
  --arena                      Quick-launch the classic 6-thesis param sweep
  --multi-market               Multi-symbol oracle_diff_bot_6 with PnL tracking
  --hypothesis-suite           Launch enabled hypothesis scripts from config
  --fleet                      AWS EC2 latency probe provisioning (dry-run by default)

Config format (orchestrator.json):
{
  "processes": [
    {
      "id": "oracle-1k",
      "script": "oracle_diff_bot_6.py",
      "args": {"window": 1000, "vl": 1, "contract": "DIGITDIFF"},
      "enabled": true
    }
  ],
  "hypotheses": [
    {
      "id": "HYP-ACCU-01",
      "script": "accumulator_edge_scan.py",
      "enabled": false
    }
  ],
  "fleet": {
    "regions": ["eu-west-1", "ap-northeast-1", "us-east-1"],
    "dry_run": true
  }
}

Usage:
  python3 unified_orchestrator.py --config orchestrator.json
  python3 unified_orchestrator.py --arena
  python3 unified_orchestrator.py --multi-market --compound 0.25
  python3 unified_orchestrator.py --hypothesis-suite
  python3 unified_orchestrator.py --fleet
  python3 unified_orchestrator.py --fleet --real
"""
import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from strategy_utils import WIN_PATTERN, LOSS_PATTERN

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [ORCHESTRATOR] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ORCHESTRATOR")

os.makedirs("logs/orchestrator", exist_ok=True)

# ---------------------------------------------------------------------------
# Process management with PnL tracking
# ---------------------------------------------------------------------------

_pnl_lock = threading.Lock()
_global_pnl = 0.0
_closed_trades = 0


def _log_global(line, is_important=False):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {line.strip()}\n"
    with open("logs/orchestrator/orchestrator.log", "a", encoding="utf-8") as f:
        f.write(formatted)
        f.flush()
    if is_important:
        sys.stdout.write(formatted)
        sys.stdout.flush()


def _monitor_process(proc, label):
    """Read stdout lines from a child process, track PnL, and log."""
    global _global_pnl, _closed_trades
    for line in iter(proc.stdout.readline, b""):
        decoded = line.decode("utf-8", errors="replace").strip()
        if not decoded:
            continue

        is_important = False
        win_match = WIN_PATTERN.search(decoded)
        loss_match = LOSS_PATTERN.search(decoded)

        if win_match:
            profit = float(win_match.group(1))
            with _pnl_lock:
                _global_pnl += profit
                _closed_trades += 1
            is_important = True
        elif loss_match:
            loss = float(loss_match.group(1))
            with _pnl_lock:
                _global_pnl -= loss
                _closed_trades += 1
            is_important = True

        if any(icon in decoded for icon in ["💥", "🔫", "🛡️", "📈", "🎯", "⚠️", "✅", "❌"]):
            is_important = True

        clean = re.sub(
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ - BOT_[^:]+:(INFO|WARNING|ERROR|DEBUG):",
            f"[{label}] ",
            decoded,
        )
        if win_match or loss_match:
            with _pnl_lock:
                clean += f" | 🌍 PNL GLOBAL: ${_global_pnl:.2f} (trades: {_closed_trades})"

        _log_global(clean, is_important)


def _launch_process(cmd, label, env=None):
    """Launch a single subprocess and start a monitor thread."""
    child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if env:
        child_env.update(env)
    logger.info(f"🚀 [{label}] Launching: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=child_env,
    )
    t = threading.Thread(target=_monitor_process, args=(proc, label), daemon=True)
    t.start()
    return proc, t


def _run_sync(config_path):
    """Run processes defined in a JSON config synchronously (subprocess + threads)."""
    with open(config_path) as f:
        config = json.load(f)

    processes = []
    threads = []

    # 1. Generic processes
    for p in config.get("processes", []):
        if not p.get("enabled", True):
            logger.info(f"⏸️  Skipping disabled: {p['id']}")
            continue
        script = p["script"]
        if not Path(script).exists():
            logger.error(f"❌ Script not found: {script}")
            continue
        cmd = [sys.executable, script]
        for k, v in p.get("args", {}).items():
            cmd.extend([f"--{k.replace('_', '-')}", str(v)])
        proc, t = _launch_process(cmd, p["id"])
        processes.append(proc)
        threads.append(t)
        time.sleep(2)

    # 2. Hypothesis scripts
    for h in config.get("hypotheses", []):
        if not h.get("enabled", True):
            logger.info(f"⏸️  Skipping disabled hypothesis: {h['id']}")
            continue
        script = h["script"]
        if not Path(script).exists():
            logger.error(f"❌ Script not found: {script} for {h['id']}")
            continue
        env = {f"{h['id']}_PARAMS": json.dumps(h.get("params", {}))}
        proc, t = _launch_process([sys.executable, script], h["id"], env=env)
        processes.append(proc)
        threads.append(t)
        time.sleep(2)

    if not processes:
        logger.info("No enabled processes to run.")
        return

    logger.info(f"✅ {len(processes)} processes launched. Ctrl+C to stop all.")
    logger.info(f"📊 Global PnL tracker active. Logs: logs/orchestrator/orchestrator.log")

    try:
        while True:
            time.sleep(5)
            alive = sum(1 for p in processes if p.poll() is None)
            if alive == 0:
                logger.info("🏁 All processes finished.")
                break
            logger.info(f"Heartbeat: {alive}/{len(processes)} alive | PnL: ${_global_pnl:.2f}")
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping all processes...")
        for p in processes:
            p.terminate()
        logger.info(f"Orchestrator stopped. Final PnL: ${_global_pnl:.2f} | Trades: {_closed_trades}")


# ---------------------------------------------------------------------------
# Arena mode (classic 6-thesis param sweep)
# ---------------------------------------------------------------------------

ARENA_COMMANDS = [
    ("thesis-1k-1vl", "oracle_diff_bot_6.py --window 1000 --vl 1 --contract DIGITDIFF"),
    ("thesis-500-1vl", "oracle_diff_bot_6.py --window 500 --vl 1 --contract DIGITDIFF"),
    ("thesis-2k-1vl", "oracle_diff_bot_6.py --window 2000 --vl 1 --contract DIGITDIFF"),
    ("thesis-1k-2vl", "oracle_diff_bot_6.py --window 1000 --vl 2 --contract DIGITDIFF"),
    ("thesis-1k-match", "oracle_diff_bot_6.py --window 1000 --vl 1 --contract DIGITMATCH"),
    ("thesis-classic", "oracle_diff_bot_2.py"),
]


def _run_arena():
    logger.info("🔥 Arena mode: 6 parametric theses")
    processes = []
    for label, cmd_str in ARENA_COMMANDS:
        cmd = [sys.executable] + cmd_str.split()
        proc, t = _launch_process(cmd, label)
        processes.append(proc)
        time.sleep(2)
    logger.info(f"✅ {len(processes)} arena bots launched.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping arena...")
        for p in processes:
            p.terminate()
        logger.info("Arena stopped.")


# ---------------------------------------------------------------------------
# Multi-market mode (oracle_diff_bot_6 across symbols with PnL tracking)
# ---------------------------------------------------------------------------

MULTI_MARKET_SYMBOLS = ["1HZ10V", "1HZ25V", "R_10", "RDBEAR", "RDBULL"]


def _run_multi_market(compound=0.25, stake=1.0, window=1000, vl=2, soros=3, freeroll=True):
    logger.info(f"🌐 Multi-market mode: {len(MULTI_MARKET_SYMBOLS)} symbols, compound={compound*100}%")
    squad = f"C{int(round(compound * 100))}"
    processes = []
    for symbol in MULTI_MARKET_SYMBOLS:
        cmd = [
            sys.executable, "oracle_diff_bot_6.py",
            "--symbol", symbol,
            "--stake", str(stake),
            "--window", str(window),
            "--vl", str(vl),
            "--soros", str(soros),
            "--compound", str(compound),
            "--mode", "DEMO",
            "--envfile", ".env",
        ]
        if freeroll:
            cmd.append("--freeroll")
        proc, t = _launch_process(cmd, f"{squad}-{symbol}")
        processes.append(proc)
        time.sleep(2)
    logger.info(f"✅ Multi-market squad {squad} online. Stake: ${stake}")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info(f"\n🛑 Stopping squad {squad}...")
        for p in processes:
            p.terminate()
        logger.info(f"Squad stopped. Final PnL: ${_global_pnl:.2f}")


# ---------------------------------------------------------------------------
# Hypothesis suite mode (from JSON config)
# ---------------------------------------------------------------------------

def _run_hypothesis_suite(config_path="hypothesis_configs.json"):
    logger.info("🧠 Hypothesis suite mode")
    if not Path(config_path).exists():
        logger.error(f"Config file not found: {config_path}")
        return

    with open(config_path) as f:
        config = json.load(f)

    demo_mode = config.get("global_settings", {}).get("demo_mode", True)
    logger.info(f"⚙️  Mode: {'DEMO' if demo_mode else 'REAL'}")

    async def _run_async():
        tasks = []
        for h in config.get("hypotheses", []):
            if not h.get("enabled"):
                logger.info(f"⏸️  Disabled: {h.get('id')}")
                continue
            script = h["script"]
            if not Path(script).exists():
                logger.error(f"❌ Script not found: {script} for {h['id']}")
                continue
            os.environ[f"{h['id']}_PARAMS"] = json.dumps(h.get("params", {}))
            os.environ["MEGA_BRAIN_DEMO"] = "1" if demo_mode else "0"

            async def _run_one(h_id, h_script):
                logger.info(f"🚀 Starting: {h_id} ({h_script})")
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, h_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                async def _read(stream, prefix):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        text = line.decode().strip()
                        if text:
                            _log_global(f"{prefix} | {text}")
                await asyncio.gather(
                    _read(proc.stdout, f"[{h_id}]"),
                    _read(proc.stderr, f"[{h_id}] ERR"),
                )
                await proc.wait()
                logger.warning(f"🛑 Finished: {h_id} (exit {proc.returncode})")

            tasks.append(asyncio.create_task(_run_one(h["id"], script)))

        if not tasks:
            logger.info("No enabled hypotheses.")
            return
        await asyncio.gather(*tasks)
        logger.info("🏁 All hypotheses completed.")

    try:
        asyncio.run(_run_async())
    except KeyboardInterrupt:
        logger.info("Interrupted.")


# ---------------------------------------------------------------------------
# Fleet mode (AWS EC2 provisioning — delegates to aws_fleet_manager)
# ---------------------------------------------------------------------------

def _run_fleet(real=False, regions=None):
    logger.info(f"🚀 Fleet mode: {'REAL' if real else 'DRY-RUN'}")
    try:
        from aws_fleet_manager import AWSFleetManager, TARGET_REGIONS
    except ImportError:
        logger.error("❌ aws_fleet_manager.py not found or boto3 not installed.")
        return
    fleet = AWSFleetManager(regions=regions or TARGET_REGIONS)
    fleet.provision_latency_probes(dry_run=not real)
    if not real:
        logger.info("Dry-run complete. Use --real to provision (generates cost).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Unified orchestrator — replaces arena_launcher, multi_market_orchestrator, "
                    "mega_brain_orchestrator, and aws_fleet_manager."
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--config", help="Path to JSON config file")
    mode.add_argument("--arena", action="store_true", help="Classic 6-thesis param sweep")
    mode.add_argument("--multi-market", action="store_true", help="Multi-symbol oracle_diff_bot_6")
    mode.add_argument("--hypothesis-suite", action="store_true", help="Launch hypothesis scripts from config")
    mode.add_argument("--fleet", action="store_true", help="AWS EC2 latency probe provisioning")

    ap.add_argument("--compound", type=float, default=0.25, help="Compound rate (multi-market mode)")
    ap.add_argument("--stake", type=float, default=1.0, help="Stake per trade (multi-market mode)")
    ap.add_argument("--real", action="store_true", help="Real provisioning (fleet mode only)")
    ap.add_argument("--regions", default=None, help="Comma-separated AWS regions (fleet mode)")
    args = ap.parse_args()

    if args.config:
        _run_sync(args.config)
    elif args.arena:
        _run_arena()
    elif args.multi_market:
        _run_multi_market(compound=args.compound, stake=args.stake)
    elif args.hypothesis_suite:
        _run_hypothesis_suite()
    elif args.fleet:
        regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
        _run_fleet(real=args.real, regions=regions)


if __name__ == "__main__":
    main()
