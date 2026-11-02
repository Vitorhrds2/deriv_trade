import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def utc_now(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def parse_utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_manifest(path):
    values = {}
    for line in read_text(path).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def read_status(path):
    text = read_text(path)
    if not text:
        return []
    return list(csv.DictReader(text.splitlines(), delimiter="\t"))


def load_json(path):
    try:
        value = json.loads(read_text(path))
        return value if isinstance(value, dict) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def file_age_s(path, now):
    try:
        return max(0.0, now.timestamp() - Path(path).stat().st_mtime)
    except OSError:
        return None


def timestamp_age_s(value, now):
    try:
        return max(0.0, (now - parse_utc(value)).total_seconds())
    except (TypeError, ValueError):
        return None


def process_pids(fragment, excludes=()):
    matches = []
    own_pid = os.getpid()
    for item in Path("/proc").glob("[0-9]*"):
        pid = integer(item.name, -1)
        if pid <= 0 or pid == own_pid:
            continue
        try:
            command = (item / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if fragment in command and not any(excluded in command for excluded in excludes):
            matches.append(pid)
    return sorted(matches)


def latest_attempt_log(campaign_dir):
    candidates = []
    for path in Path(campaign_dir).glob("attempt_*.log"):
        match = re.search(r"attempt_(\d+)\.log$", path.name)
        if match:
            candidates.append((integer(match.group(1)), path))
    if candidates:
        return max(candidates)[1]
    current = Path(campaign_dir) / "current.log"
    return current if current.exists() else None


def campaign_snapshot(campaign_dir, now, process_probe, max_silence_s):
    root = Path(campaign_dir)
    manifest = read_manifest(root / "manifest.txt")
    rows = read_status(root / "status.tsv")
    target_sessions = integer(manifest.get("target_valid_sessions"), 4)
    valid_from_rows = max((integer(row.get("valid_session")) for row in rows), default=0)
    valid_sessions = integer(manifest.get("valid_sessions"), valid_from_rows)
    attempts_from_rows = max((integer(row.get("attempt")) for row in rows), default=0)
    log_path = latest_attempt_log(root)
    attempt_from_log = 0
    if log_path:
        match = re.search(r"attempt_(\d+)\.log$", log_path.name)
        attempt_from_log = integer(match.group(1)) if match else 0
    attempt = max(attempts_from_rows, attempt_from_log, integer(manifest.get("attempts")))
    log_text = read_text(log_path) if log_path else ""
    completed_trials = len(re.findall(r"profit_hold=", log_text))
    target_match = re.search(r"--trials\s+(\d+)", manifest.get("command", ""))
    target_trials = integer(target_match.group(1), 20) if target_match else 20
    sample_trials = [integer(value) for value in re.findall(r"\[(\d+)\]\s+sample=", log_text)]
    age_s = file_age_s(log_path, now) if log_path else None
    pids = process_probe("repeat_campaign.sh", ("tmux new-session", "early_sell_status_monitor.py"))
    status = "complete" if valid_sessions >= target_sessions else "running" if pids else "stalled"
    fresh = status == "complete" or age_s is not None and age_s <= max_silence_s
    demo_validated = "OK DEMO" in log_text
    errors = []
    if status == "stalled":
        errors.append("repeat campaign sem processo ativo")
    if not fresh:
        errors.append(f"log sem atualizacao: age_s={age_s}")
    if not demo_validated:
        errors.append("validacao DEMO ausente no log atual")
    counts = {}
    for row in rows:
        value = row.get("status", "UNKNOWN")
        counts[value] = counts.get(value, 0) + 1
    return {
        "status": status,
        "healthy": not errors,
        "errors": errors,
        "process_pids": pids,
        "valid_sessions": valid_sessions,
        "target_valid_sessions": target_sessions,
        "attempt": attempt,
        "completed_trials_current_attempt": completed_trials,
        "target_trials_per_session": target_trials,
        "active_trial": sample_trials[-1] if sample_trials else None,
        "log_age_s": round(age_s, 3) if age_s is not None else None,
        "fresh": fresh,
        "demo_validated": demo_validated,
        "attempt_status_counts": counts,
    }


def ab_snapshot(ab_dir, campaign_complete, now, process_probe, max_silence_s):
    root = Path(ab_dir)
    manifest = read_manifest(root / "manifest.txt")
    stats = load_json(root / "stats.json") or {}
    results = [line for line in read_text(root / "results.jsonl").splitlines() if line.strip()]
    target_pairs = integer(stats.get("target_pairs"), integer(manifest.get("pairs"), 20))
    valid_pairs = integer(stats.get("valid_pairs"))
    pids = process_probe(str(root), ("early_sell_status_monitor.py",))
    started = bool(manifest.get("started_utc") or (root / "run.log").exists())
    ended = bool(manifest.get("ended_utc"))
    exit_code = integer(manifest.get("exit_code"), -1)
    stats_complete = valid_pairs >= target_pairs
    if stats_complete:
        stage = "complete"
    elif ended and exit_code != 0:
        stage = "failed"
    elif started and pids:
        stage = "running"
    elif pids and not campaign_complete:
        stage = "waiting"
    elif pids and campaign_complete:
        stage = "starting"
    elif not pids and not campaign_complete:
        stage = "missing_waiter"
    else:
        stage = "stalled"
    run_age_s = file_age_s(root / "run.log", now)
    stats_age_s = timestamp_age_s(stats.get("updated_utc"), now)
    started_age_s = timestamp_age_s(manifest.get("started_utc"), now)
    activity_ages = [value for value in (run_age_s, stats_age_s, started_age_s) if value is not None]
    activity_age_s = min(activity_ages) if activity_ages else None
    fresh = stage in ("waiting", "starting", "complete") or activity_age_s is not None and activity_age_s <= max_silence_s
    demo_only = "demo-only" in manifest.get("account", "").lower()
    errors = []
    if stage in ("failed", "missing_waiter", "stalled"):
        errors.append(f"A/B stage={stage}")
    if not fresh:
        errors.append(f"A/B sem atualizacao: age_s={activity_age_s}")
    if not demo_only:
        errors.append("declaracao demo-only ausente")
    return {
        "stage": stage,
        "healthy": not errors,
        "errors": errors,
        "process_pids": pids,
        "demo_only_declared": demo_only,
        "attempts": integer(stats.get("attempts"), len(results)),
        "valid_pairs": valid_pairs,
        "target_pairs": target_pairs,
        "results_records": len(results),
        "activity_age_s": round(activity_age_s, 3) if activity_age_s is not None else None,
        "fresh": fresh,
        "decision": stats.get("decision", "NOT_VALIDATED"),
        "demo_gate_pass": stats.get("demo_gate_pass") is True,
        "treatment_ev_ci95": stats.get("treatment_ev_ci95", [0.0, 0.0, 0.0]),
        "control_ev_ci95": stats.get("control_ev_ci95", [0.0, 0.0, 0.0]),
        "paired_diff_ci95": stats.get("paired_diff_ci95", [0.0, 0.0, 0.0]),
        "treatment_total_pnl": stats.get("treatment_total_pnl", 0.0),
        "control_total_pnl": stats.get("control_total_pnl", 0.0),
        "trigger_rate": stats.get("trigger_rate", 0.0),
        "fill_rate": stats.get("fill_rate", 0.0),
    }


def oos_snapshot(path, now, max_age_s):
    value = load_json(path)
    if not value:
        return {"healthy": False, "errors": ["snapshot OOS ausente ou invalido"]}
    age_s = timestamp_age_s(value.get("observed_utc"), now)
    fresh = age_s is not None and age_s <= max_age_s
    healthy = value.get("health") == "HEALTHY" and value.get("paper_only") is True and fresh
    return {
        "healthy": healthy,
        "errors": [] if healthy else [f"OOS health={value.get('health')} age_s={age_s}"],
        "health": value.get("health"),
        "paper_only": value.get("paper_only") is True,
        "decision": value.get("decision", "NOT_VALIDATED"),
        "signals": value.get("signals", []),
        "observed_utc": value.get("observed_utc"),
        "age_s": round(age_s, 3) if age_s is not None else None,
        "fresh": fresh,
    }


def build_snapshot(campaign_dir, ab_dir, oos_file, now=None, process_probe=process_pids):
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    campaign = campaign_snapshot(campaign_dir, current, process_probe, 1200.0)
    ab = ab_snapshot(ab_dir, campaign["status"] == "complete", current, process_probe, 1200.0)
    oos = oos_snapshot(oos_file, current, 420.0)
    healthy = campaign["healthy"] and ab["healthy"] and oos["healthy"]
    safe = campaign["demo_validated"] and ab["demo_only_declared"] and oos.get("paper_only") is True
    stage = "repeat" if campaign["status"] != "complete" else "paired_ab" if ab["stage"] != "complete" else "complete"
    return {
        "schema_version": 1,
        "observed_utc": utc_now(current),
        "health": "HEALTHY" if healthy else "DEGRADED",
        "demo_paper_only": safe,
        "pipeline_stage": stage,
        "campaign": campaign,
        "paired_ab": ab,
        "parallel_oos": oos,
    }


def atomic_write(path, value):
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def append_jsonl(path, value):
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", required=True)
    parser.add_argument("--ab-dir", required=True)
    parser.add_argument("--oos-current-file", required=True)
    parser.add_argument("--current-file", required=True)
    parser.add_argument("--history-file", required=True)
    parser.add_argument("--fail-on-degraded", action="store_true")
    args = parser.parse_args()
    snapshot = build_snapshot(args.campaign_dir, args.ab_dir, args.oos_current_file)
    atomic_write(args.current_file, snapshot)
    append_jsonl(args.history_file, snapshot)
    print(json.dumps(snapshot, sort_keys=True), flush=True)
    if args.fail_on_degraded and snapshot["health"] != "HEALTHY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
