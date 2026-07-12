import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


RUNNERS = {
    "d55": {
        "service": "d55-oos-paper.service",
        "state": "d55/state.json",
        "stats": "d55/stats.json",
        "max_age_s": 180.0,
    },
    "d36": {
        "service": "d36-oos-paper.service",
        "state": "d36/state.json",
        "stats": "d36/stats.json",
        "max_age_s": 4500.0,
    },
    "d34": {
        "service": "d34-cascade-live.service",
        "state": "d34/state.json",
        "stats": "d34/stats.json",
        "max_age_s": 180.0,
    },
}


def utc_now(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def parse_utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp UTC ausente")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON raiz deve ser objeto")
    return payload


def atomic_write(path, value):
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    temporary = f"{absolute}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, absolute)


def append_jsonl(path, value):
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ratio(value, target):
    return min(1.0, value / target) if target > 0 else 0.0


def probe_service(service):
    command = [
        "systemctl",
        "show",
        service,
        "--no-pager",
        "--property=LoadState",
        "--property=ActiveState",
        "--property=SubState",
        "--property=NRestarts",
        "--property=MainPID",
        "--property=Result",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "name": service,
            "active": False,
            "error": str(error),
        }
    properties = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            properties[key] = value
    active = (
        completed.returncode == 0
        and properties.get("LoadState") == "loaded"
        and properties.get("ActiveState") == "active"
        and integer(properties.get("MainPID")) > 0
    )
    result = {
        "name": service,
        "active": active,
        "load_state": properties.get("LoadState"),
        "active_state": properties.get("ActiveState"),
        "sub_state": properties.get("SubState"),
        "restarts": integer(properties.get("NRestarts")),
        "main_pid": integer(properties.get("MainPID")),
        "result": properties.get("Result"),
    }
    if completed.returncode != 0:
        result["error"] = completed.stderr.strip() or f"systemctl rc={completed.returncode}"
    return result


def paper_only(name, state):
    if name == "d36":
        return state.get("config", {}).get("paper_only") is True
    return state.get("paper_only") is True


def progress(observations, target, **extra):
    value = {
        "observations": observations,
        "target": target,
        "ratio": ratio(observations, target),
    }
    value.update(extra)
    return value


def extract_metrics(name, state, stats):
    if name == "d55":
        observations = integer(stats.get("cycles"))
        target = integer(stats.get("target_cycles"))
        return {
            "progress": progress(observations, target),
            "pnl": {
                "current_exit_net_bps": stats.get("current_exit_net_bps", 0.0),
                "current_exit_net_usd": stats.get("current_exit_net_usd", 0.0),
                "incremental_ev_bps_ci95": stats.get("incremental_ev_bps_ci95", [0.0, 0.0, 0.0]),
                "funding_hl_total_bps": stats.get("funding_hl_total_bps", 0.0),
                "funding_bn_total_bps": stats.get("funding_bn_total_bps", 0.0),
            },
            "quality": {
                "missed_events": integer(stats.get("missed_events")),
                "win_rate": stats.get("win_rate", 0.0),
                "win_rate_wilson_ci95": stats.get("win_rate_wilson_ci95", [0.0, 0.0]),
            },
        }
    if name == "d36":
        observations = integer(stats.get("settled"))
        target = integer(stats.get("target_settled"))
        clusters = integer(stats.get("settled_clusters"))
        target_clusters = integer(stats.get("target_clusters"))
        return {
            "progress": progress(
                observations,
                target,
                open=integer(stats.get("open")),
                settled_clusters=clusters,
                target_clusters=target_clusters,
                cluster_ratio=ratio(clusters, target_clusters),
            ),
            "pnl": {
                "total_pnl_pct": stats.get("total_pnl_pct", 0.0),
                "total_pnl_usd": stats.get("total_pnl_usd", 0.0),
                "ev_pct_ci95": stats.get("ev_pct_ci95", [0.0, 0.0, 0.0]),
                "cluster_ev_pct_ci95": stats.get("cluster_ev_pct_ci95", [0.0, 0.0, 0.0]),
            },
            "quality": {
                "cycles": integer(stats.get("cycles")),
                "win_rate": stats.get("win_rate", 0.0),
                "win_rate_wilson_ci95": stats.get("win_rate_wilson_ci95", [0.0, 0.0]),
            },
        }
    primary = str(stats.get("primary_horizon_s", state.get("config", {}).get("primary_horizon", 30)))
    horizon = stats.get("horizons", {}).get(primary, {})
    observations = integer(horizon.get("n"))
    target = integer(stats.get("target_per_horizon"))
    return {
        "progress": progress(
            observations,
            target,
            primary_horizon_s=integer(primary, 30),
            liquidations_seen=integer(stats.get("liquidations_seen")),
            cascades=integer(stats.get("cascades")),
            resolved_results=integer(stats.get("resolved_results")),
        ),
        "pnl": {
            "total_pnl_pct": horizon.get("total_pnl_pct", 0.0),
            "ev_pct_ci95": horizon.get("ev_pct_ci95", [0.0, 0.0, 0.0]),
        },
        "quality": {
            "missed_results": integer(stats.get("missed_results")),
            "win_rate": horizon.get("win_rate", 0.0),
            "win_rate_wilson_ci95": horizon.get("win_rate_wilson_ci95", [0.0, 0.0]),
            "passing_horizons_s": stats.get("passing_horizons_s", []),
        },
    }


def build_runner(name, config, base_dir, now, service_probe):
    state_path = Path(base_dir) / config["state"]
    stats_path = Path(base_dir) / config["stats"]
    errors = []
    try:
        state = load_json(state_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        state = {}
        errors.append(f"state: {error}")
    try:
        stats = load_json(stats_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        stats = {}
        errors.append(f"stats: {error}")
    updated_utc = stats.get("updated_utc")
    age_s = None
    try:
        age_s = max(0.0, (now - parse_utc(updated_utc)).total_seconds())
    except (TypeError, ValueError):
        if stats_path.exists():
            age_s = max(0.0, now.timestamp() - stats_path.stat().st_mtime)
        else:
            errors.append("freshness: stats ausente")
    fresh = age_s is not None and age_s <= config["max_age_s"]
    if not fresh:
        errors.append(f"freshness: age_s={age_s} max_age_s={config['max_age_s']}")
    is_paper_only = paper_only(name, state)
    if not is_paper_only:
        errors.append("paper_only: trava ausente")
    service = service_probe(config["service"]) if service_probe else {
        "name": config["service"],
        "active": None,
        "skipped": True,
    }
    if service_probe and not service.get("active"):
        errors.append("service: inativo")
    result = {
        "decision": stats.get("decision", "NOT_VALIDATED"),
        "paper_gate_pass": stats.get("paper_gate_pass") is True,
        "paper_only": is_paper_only,
        "updated_utc": updated_utc,
        "age_s": round(age_s, 3) if age_s is not None else None,
        "max_age_s": config["max_age_s"],
        "fresh": fresh,
        "service": service,
        "healthy": not errors,
        "errors": errors,
    }
    result.update(extract_metrics(name, state, stats))
    return result


def build_snapshot(base_dir, now=None, service_probe=probe_service):
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    runners = {
        name: build_runner(name, config, base_dir, current, service_probe)
        for name, config in RUNNERS.items()
    }
    signals = [
        name
        for name, value in runners.items()
        if value["paper_gate_pass"] and value["healthy"]
    ]
    healthy = all(value["healthy"] for value in runners.values())
    return {
        "schema_version": 1,
        "observed_utc": utc_now(current),
        "base_dir": str(Path(base_dir).resolve()),
        "paper_only": all(value["paper_only"] for value in runners.values()),
        "health": "HEALTHY" if healthy else "DEGRADED",
        "decision": "PAPER_SIGNAL" if signals else "NOT_VALIDATED",
        "signals": signals,
        "runners": runners,
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--current-file")
    parser.add_argument("--history-file")
    parser.add_argument("--skip-service-checks", action="store_true")
    parser.add_argument("--fail-on-degraded", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(args.base_dir).resolve()
    current_file = args.current_file or str(base_dir / "monitor" / "current.json")
    history_file = args.history_file or str(base_dir / "monitor" / "history.jsonl")
    snapshot = build_snapshot(
        base_dir,
        service_probe=None if args.skip_service_checks else probe_service,
    )
    atomic_write(current_file, snapshot)
    append_jsonl(history_file, snapshot)
    print(json.dumps(snapshot, sort_keys=True), flush=True)
    if args.fail_on_degraded and snapshot["health"] != "HEALTHY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
