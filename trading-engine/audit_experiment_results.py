import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from massive_edge_sweep import binomial_sf


HERE = Path(__file__).resolve().parent


def strategy_name(record):
    return str(record.get("strategy") or record.get("vector") or record.get("contract_type") or record.get("ct") or "unknown")


def finite_profit(record):
    value = record.get("profit")
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def discover_files(root):
    files = sorted(path for path in root.rglob("d11*.jsonl") if path.is_file())
    unique = []
    duplicates = []
    digests = {}
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in digests:
            duplicates.append({"path": str(path), "duplicate_of": str(digests[digest])})
        else:
            digests[digest] = path
            unique.append(path)
    return unique, duplicates


def load_groups(root):
    files, duplicates = discover_files(root)
    groups = defaultdict(list)
    malformed = 0
    records = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    malformed += 1
                    continue
                profit = finite_profit(record)
                if profit is None:
                    continue
                groups[f"{relative}::{strategy_name(record)}"].append(profit)
                records += 1
    return groups, files, duplicates, malformed, records


def circular_block_sample(values, block, rng):
    n = len(values)
    parts = []
    while sum(len(part) for part in parts) < n:
        start = int(rng.integers(0, n))
        indices = (start + np.arange(block)) % n
        parts.append(values[indices])
    return np.concatenate(parts)[:n]


def block_bootstrap(values, iterations=3000, seed=117):
    array = np.asarray(values, dtype=np.float64)
    n = len(array)
    if n == 0:
        return 0.0, 0.0, 1.0
    if n == 1:
        return float(array[0]), float(array[0]), 1.0
    block = max(1, int(round(n ** (1.0 / 3.0))))
    rng = np.random.default_rng(seed)
    means = np.empty(iterations, dtype=np.float64)
    centered = array - array.mean()
    null_ge = 0
    observed = float(array.mean())
    for index in range(iterations):
        means[index] = circular_block_sample(array, block, rng).mean()
        if circular_block_sample(centered, block, rng).mean() >= observed:
            null_ge += 1
    low, high = np.quantile(means, (0.025, 0.975))
    p_value = (null_ge + 1) / (iterations + 1)
    return float(low), float(high), float(p_value)


def binary_test(values):
    rounded = sorted({round(float(value), 8) for value in values})
    if len(rounded) != 2 or rounded[0] >= 0 or rounded[1] <= 0:
        return None
    loss, win = rounded
    breakeven = -loss / (win - loss)
    wins = sum(value > 0 for value in values)
    return {
        "wins": wins,
        "breakeven": breakeven,
        "p": binomial_sf(wins, len(values), breakeven),
    }


def adjust_fdr(rows):
    order = sorted(range(len(rows)), key=lambda index: rows[index]["p"])
    running = 1.0
    m = len(order)
    for position in range(m - 1, -1, -1):
        rank = position + 1
        index = order[position]
        running = min(running, rows[index]["p"] * m / rank)
        rows[index]["q"] = min(1.0, running)


def summarize_group(key, values, iterations):
    n = len(values)
    mean = sum(values) / n
    first = values[: n // 2]
    second = values[n // 2:]
    ci_low, ci_high, bootstrap_p = block_bootstrap(values, iterations=iterations, seed=int(hashlib.sha256(key.encode()).hexdigest()[:8], 16))
    binary = binary_test(values)
    p_value = binary["p"] if binary else bootstrap_p
    return {
        "key": key,
        "n": n,
        "wins": sum(value > 0 for value in values),
        "win_rate": sum(value > 0 for value in values) / n,
        "pnl": sum(values),
        "mean": mean,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p": p_value,
        "binary": binary,
        "first_half_mean": sum(first) / len(first) if first else mean,
        "second_half_mean": sum(second) / len(second) if second else mean,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(HERE.parent))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / "data" / "legacy_results_audit.json"))
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--min-trades", type=int, default=30)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    groups, files, duplicates, malformed, records = load_groups(root)
    rows = [summarize_group(key, values, args.iterations) for key, values in groups.items() if len(values) >= args.min_trades]
    adjust_fdr(rows)
    for row in rows:
        row["stable"] = row["first_half_mean"] > 0 and row["second_half_mean"] > 0
        row["confirmed"] = row["q"] <= 0.05 and row["ci_low"] > 0 and row["stable"]
    rows.sort(key=lambda row: (row["q"], -row["mean"]))
    confirmed = [row for row in rows if row["confirmed"]]

    print(f"Arquivos únicos={len(files)} duplicados={len(duplicates)} registros P&L={records} malformed={malformed}")
    print(f"Grupos N>={args.min_trades}: {len(rows)} | confirmados após FDR+block-bootstrap+estabilidade: {len(confirmed)}")
    print("=" * 120)
    for row in rows[:30]:
        marker = "CONFIRMADO" if row["confirmed"] else "refutado/noise"
        print(
            f"{row['key'][:65]:<65} N={row['n']:>4} WR={row['win_rate']*100:>5.1f}% "
            f"PnL={row['pnl']:>+9.2f} EV={row['mean']:>+7.3f} "
            f"CI=[{row['ci_low']:+.3f},{row['ci_high']:+.3f}] p={row['p']:.3g} q={row['q']:.3g} "
            f"halves={row['first_half_mean']:+.3f}/{row['second_half_mean']:+.3f} {marker}"
        )
    print("=" * 120)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": str(root),
        "unique_files": len(files),
        "duplicates": duplicates,
        "profit_records": records,
        "malformed": malformed,
        "minimum_trades": args.min_trades,
        "groups": rows,
        "confirmed": confirmed,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Resultado completo: {output}")


if __name__ == "__main__":
    main()
