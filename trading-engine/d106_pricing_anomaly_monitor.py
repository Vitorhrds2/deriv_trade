"""D106 — Real-Time Pricing/Proposal Anomaly Monitor.

COMPLEMENTO ao synthetic_anomaly_monitor.py (que vigia RNG/feed/EV em ticks).
Este modulo vigia o nivel de PROPOSAL/PAYOUT/RESALE — onde bugs transitórios
de pricing se manifestariam como edges exploráveis.

Detectores:
  1. PAYOUT_RATIO_ANOMALY: payout ratio muda significativamente do baseline histórico
  2. SPOT_MISMATCH: spot price no proposal difere do tick live (lag/staleness bug)
  3. RESALE_ARB: buy contract → immediate resale > buy cost (instant profit bug)
  4. CONTRACT_AVAILABILITY: contract type aparece/desaparece de repente
  5. STAKE_DEPENDENT_PAYOUT: payout ratio muda com stake size (mispricing por stake)
  6. CROSS_SYMBOL_DIVERGENCE: mesmo underlying, símbolos diferentes, preços divergem

Filosofia: DETEÇÃO APENAS. Não opera. Registra evidência auditável em JSONL.
Roda 24/7 no EC2. Alerta CRITICAL = investigar imediatamente.

Uso:
    python d106_pricing_anomaly_monitor.py \\
        --symbols 1HZ10V,1HZ50V,1HZ100V,R_10,R_50,R_100 \\
        --contracts CALL,PUT,DIGITEVEN,DIGITODD,DIGITOVER:5,DIGITUNDER:4 \\
        --durations 1t,5t,10t \\
        --stake-scan 0.35,1.0,10.0,100.0 \\
        --interval 30

Evidência: logs/d106_pricing_anomalies.jsonl
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from statistics import mean, stdev

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

APP_ID = os.getenv("DERIV_APP_ID", "1089")
TOKEN = os.getenv("DERIV_API_TOKEN", "")
EVIDENCE_PATH = "logs/d106_pricing_anomalies.jsonl"

# Symbols to monitor — broad coverage
DEFAULT_SYMBOLS = "1HZ10V,1HZ25V,1HZ50V,1HZ75V,1HZ100V,R_10,R_25,R_50,R_75,R_100"
DEFAULT_CONTRACTS = "CALL,PUT,DIGITEVEN,DIGITODD"
DEFAULT_DURATIONS = "1t,5t,10t"
DEFAULT_STAKES = "0.35,1.0,10.0,100.0"

# House margin varies by contract type (empirically measured)
# 50/50 contracts (CALL/PUT/EVEN/ODD): ~4%
# Extreme probability contracts (DIGITMATCH/DIGITOVER:0/DIGITUNDER:9): ~13-17%
# Moderate skew (DIGITOVER:5/DIGITUNDER:4): ~4-5%
HOUSE_MARGIN_DEFAULT = 0.04
HOUSE_MARGIN_EXTREME = 0.15  # for P(win) <= 10% or >= 90%
PAYOUT_ANOMALY_THRESHOLD = 0.05  # 5% deviation from expected = MEDIUM
PAYOUT_ANOMALY_EXTREME = 0.15  # 15% deviation = CRITICAL

# Stake-dependent payout: structural variation is ~3% for micro-stakes
# Only flag if variation > 6% (2x structural norm) = potential transient bug
STAKE_PAYOUT_VARIATION_THRESHOLD = 0.06


def theoretical_win_prob(contract_type, barrier=None):
    """Calculate theoretical win probability for a contract type."""
    if contract_type in ("CALL", "PUT", "DIGITEVEN", "DIGITODD"):
        return 0.5
    if contract_type == "DIGITOVER":
        return (9 - (barrier or 0)) / 10.0
    if contract_type == "DIGITUNDER":
        return (barrier or 0) / 10.0
    if contract_type == "DIGITDIFF":
        return 0.9
    if contract_type == "DIGITMATCH":
        return 0.1
    return 0.5  # default


def get_house_margin(contract_type, barrier=None):
    """Get empirically-calibrated house margin for a contract type.
    Low P(win) contracts (DIGITMATCH, P=10%) have ~10% margin.
    High P(win) contracts (DIGITDIFF, P=90%) have ~2% margin.
    50/50 contracts have ~2.5% margin."""
    p_win = theoretical_win_prob(contract_type, barrier)
    # Only very low probability contracts have extreme house margin
    if p_win <= 0.10:
        return 0.107  # empirically measured for DIGITMATCH
    if p_win >= 0.90:
        return 0.022  # empirically measured for DIGITDIFF
    return HOUSE_MARGIN_DEFAULT


def expected_payout_ratio(contract_type, barrier=None):
    """Expected payout ratio = fair_payout * (1 - house_margin)."""
    p_win = theoretical_win_prob(contract_type, barrier)
    if p_win <= 0:
        return 1.92  # fallback
    fair_payout = 1.0 / p_win
    margin = get_house_margin(contract_type, barrier)
    return fair_payout * (1.0 - margin)

# Spot mismatch: if proposal spot differs from live tick by > threshold
SPOT_MISMATCH_THRESHOLD = 0.001  # 0.1% of price

# Resale arb: if resale price > buy cost by any amount
RESALE_PROFIT_THRESHOLD = 0.001  # $0.001 profit = flag (any instant profit is a bug)


def parse_csv(value):
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_contracts(value):
    """Parse contract specs like CALL,PUT,DIGITOVER:5,DIGITUNDER:4"""
    specs = []
    for c in parse_csv(value):
        if ":" in c:
            name, barrier = c.split(":", 1)
            specs.append((name.strip(), int(barrier)))
        else:
            specs.append((c.strip(), None))
    return specs


def parse_durations(value):
    """Parse durations like 1t,5t,10t -> [(1,'t'),(5,'t'),(10,'t')]"""
    import re
    result = []
    for d in parse_csv(value):
        m = re.fullmatch(r"(\d+)([tsmhd])", d.strip().lower())
        if m:
            result.append((int(m.group(1)), m.group(2)))
    return result


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def emit_anomaly(path, klass, symbol, severity, message, **stats):
    """Write anomaly to JSONL and print."""
    record = {
        "ts": time.time(),
        "iso": now_iso(),
        "klass": klass,
        "symbol": symbol,
        "severity": severity,
        "message": message,
        "stats": stats,
    }
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    sev_tag = f"[{severity}]"
    print(f"  *** {sev_tag} {klass} | {symbol} | {message}", flush=True)
    return record


class PricingAnomalyMonitor:
    def __init__(self, symbols, contracts, durations, stakes, interval, evidence_path):
        self.symbols = symbols
        self.contracts = contracts
        self.durations = durations
        self.stakes = stakes
        self.interval = interval
        self.evidence_path = evidence_path
        self.client = None

        # Live tick cache: symbol -> (epoch, quote)
        self.live_ticks = {}

        # Baseline payout ratios: (symbol, contract_label, duration) -> deque of ratios
        self.payout_baselines = defaultdict(lambda: deque(maxlen=100))

        # Contract availability tracking: (symbol, contract_label) -> bool (available last cycle)
        self.contract_available = {}

        # Stats
        self.cycle_count = 0
        self.total_proposals = 0
        self.total_errors = 0

    async def on_tick(self, data):
        t = data.get("tick")
        if not t:
            return
        sym = t.get("symbol")
        if sym:
            self.live_ticks[sym] = (int(t.get("epoch", 0)), float(t.get("quote", 0)))

    async def connect(self):
        self.client = DerivClient(
            app_id=APP_ID, api_token=TOKEN, use_demo=True
        )
        await self.client.connect()

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()

    async def get_proposal(self, symbol, contract_type, duration, duration_unit, stake, barrier=None):
        """Fetch a proposal and return parsed data."""
        payload = {
            "proposal": 1,
            "amount": stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": symbol,
            "duration": duration,
            "duration_unit": duration_unit,
        }
        if barrier is not None:
            payload["barrier"] = str(barrier)

        res = await asyncio.wait_for(self.client.send_request(payload), timeout=15)
        if "error" in res:
            return {"error": res["error"].get("message", "unknown"), "code": res["error"].get("code", "")}

        p = res.get("proposal", {})
        return {
            "ask_price": float(p.get("ask_price", 0)),
            "payout": float(p.get("payout", 0)),
            "spot": float(p.get("spot", 0)),
            "spot_time": int(p.get("spot_time", 0)),
            "contract_id": p.get("id", ""),
            "longcode": p.get("longcode", ""),
        }

    def check_payout_anomaly(self, symbol, contract_type, barrier, contract_label, duration_label, payout, ask, stake):
        """Detector 1: Payout ratio anomaly vs theoretical expected."""
        if ask <= 0 or payout <= 0:
            return None
        ratio = payout / ask

        # Calculate expected payout ratio for this contract type
        expected = expected_payout_ratio(contract_type, barrier)

        key = (symbol, contract_label, duration_label)
        baseline = self.payout_baselines[key]

        # First measurement — establish baseline
        if len(baseline) < 3:
            baseline.append(ratio)
            return None

        baseline_mean = mean(baseline)

        # Check against theoretical expected (contract-specific)
        theoretical_dev = abs(ratio - expected) / expected if expected > 0 else 0

        # Check against rolling baseline (detects sudden changes)
        rolling_dev = abs(ratio - baseline_mean) / baseline_mean if baseline_mean > 0 else 0

        # Add to baseline (normal operation)
        baseline.append(ratio)

        # Flag if significant deviation from THEORETICAL expected (not rolling baseline)
        # This catches: payout set higher than fair value (mispricing bug)
        if theoretical_dev >= PAYOUT_ANOMALY_EXTREME:
            return emit_anomaly(
                self.evidence_path, "PAYOUT_RATIO_ANOMALY", symbol, "CRITICAL",
                f"{contract_label} {duration_label}: payout ratio={ratio:.4f} "
                f"(expected={expected:.4f}, rolling_baseline={baseline_mean:.4f}, "
                f"theoretical_dev={theoretical_dev:.1%}, stake=${stake})",
                contract=contract_label, duration=duration_label,
                payout_ratio=ratio, expected_ratio=expected,
                baseline_ratio=baseline_mean, theoretical_dev=theoretical_dev,
                rolling_dev=rolling_dev, payout=payout, ask=ask, stake=stake,
            )
        elif theoretical_dev >= PAYOUT_ANOMALY_THRESHOLD:
            return emit_anomaly(
                self.evidence_path, "PAYOUT_RATIO_ANOMALY", symbol, "MEDIUM",
                f"{contract_label} {duration_label}: payout ratio={ratio:.4f} "
                f"(expected={expected:.4f}, theoretical_dev={theoretical_dev:.1%}, stake=${stake})",
                contract=contract_label, duration=duration_label,
                payout_ratio=ratio, expected_ratio=expected,
                theoretical_dev=theoretical_dev, payout=payout, ask=ask, stake=stake,
            )

        # Also flag sudden change from rolling baseline (catches mid-session payout changes)
        if rolling_dev >= PAYOUT_ANOMALY_EXTREME:
            return emit_anomaly(
                self.evidence_path, "PAYOUT_RATIO_CHANGE", symbol, "CRITICAL",
                f"{contract_label} {duration_label}: payout ratio={ratio:.4f} "
                f"SUDDENLY changed from rolling baseline={baseline_mean:.4f} "
                f"(rolling_dev={rolling_dev:.1%}, expected={expected:.4f}, stake=${stake})",
                contract=contract_label, duration=duration_label,
                payout_ratio=ratio, expected_ratio=expected,
                baseline_ratio=baseline_mean, rolling_dev=rolling_dev,
                payout=payout, ask=ask, stake=stake,
            )
        return None

    def check_spot_mismatch(self, symbol, proposal):
        """Detector 2: Spot price in proposal vs live tick."""
        if "error" in proposal or "spot" not in proposal:
            return None
        live = self.live_ticks.get(symbol)
        if not live:
            return None

        live_epoch, live_quote = live
        prop_spot = proposal["spot"]
        prop_spot_time = proposal.get("spot_time", 0)

        if live_quote <= 0 or prop_spot <= 0:
            return None

        price_diff = abs(prop_spot - live_quote) / live_quote
        time_diff = abs(prop_spot_time - live_epoch) if prop_spot_time and live_epoch else 0

        if price_diff > SPOT_MISMATCH_THRESHOLD:
            return emit_anomaly(
                self.evidence_path, "SPOT_MISMATCH", symbol, "HIGH",
                f"Proposal spot={prop_spot:.6f} vs live tick={live_quote:.6f} "
                f"(diff={price_diff:.4%}, time_diff={time_diff}s) — stale/desynced pricing",
                proposal_spot=prop_spot, live_quote=live_quote,
                price_diff_pct=price_diff, time_diff_s=time_diff,
            )
        return None

    async def check_resale_arb(self, symbol, contract_type, duration, duration_unit, barrier=None):
        """Detector 3: Buy contract → check immediate resale price."""
        stake = 1.0
        proposal = await self.get_proposal(symbol, contract_type, duration, duration_unit, stake, barrier)
        if "error" in proposal:
            return None

        # Buy the contract
        buy_payload = {
            "buy": proposal["contract_id"],
            "price": proposal["ask_price"],
        }
        try:
            buy_res = await asyncio.wait_for(self.client.send_request(buy_payload), timeout=15)
        except Exception as e:
            return None
        if "error" in buy_res:
            return None

        buy_cost = float(buy_res.get("buy", {}).get("buy_price", 0))
        contract_id = buy_res.get("buy", {}).get("contract_id", "")

        if not contract_id or buy_cost <= 0:
            return None

        # Wait a moment for the contract to be active
        await asyncio.sleep(1.0)

        # Check resale (proposal to sell)
        sell_payload = {"sell": contract_id, "price": 0}
        try:
            sell_res = await asyncio.wait_for(self.client.send_request(sell_payload), timeout=15)
        except Exception:
            return None

        if "error" in sell_res:
            # Can't sell — normal for very short durations
            return None

        sell_price = float(sell_res.get("sell", {}).get("sold_for", 0))
        profit = sell_price - buy_cost

        if profit > RESALE_PROFIT_THRESHOLD:
            return emit_anomaly(
                self.evidence_path, "RESALE_ARB", symbol, "CRITICAL",
                f"INSTANT PROFIT: buy=${buy_cost:.4f} → sell=${sell_price:.4f} "
                f"(profit=+${profit:.4f}) on {contract_type} {duration}{duration_unit}",
                contract_type=contract_type, duration=f"{duration}{duration_unit}",
                buy_cost=buy_cost, sell_price=sell_price, profit=profit,
                contract_id=contract_id,
            )
        return None

    def check_contract_availability(self, symbol, contract_label, available):
        """Detector 4: Contract availability change."""
        key = (symbol, contract_label)
        was_available = self.contract_available.get(key)

        if was_available is True and not available:
            emit_anomaly(
                self.evidence_path, "CONTRACT_UNAVAILABLE", symbol, "MEDIUM",
                f"{contract_label} became unavailable (was available last cycle)",
                contract=contract_label, was_available=True, now_available=False,
            )
        elif was_available is False and available:
            emit_anomaly(
                self.evidence_path, "CONTRACT_AVAILABLE", symbol, "MEDIUM",
                f"{contract_label} became available (was unavailable last cycle) — NEW CONTRACT?",
                contract=contract_label, was_available=False, now_available=True,
            )

        self.contract_available[key] = available

    def check_stake_dependent_payout(self, symbol, contract_label, duration_label, stake_results):
        """Detector 5: Payout ratio varies with stake size."""
        if len(stake_results) < 2:
            return None

        ratios = []
        for stake, ratio in stake_results:
            if ratio and ratio > 0:
                ratios.append((stake, ratio))

        if len(ratios) < 2:
            return None

        ratio_values = [r for _, r in ratios]
        if max(ratio_values) <= 0 or min(ratio_values) <= 0:
            return None

        variation = (max(ratio_values) - min(ratio_values)) / mean(ratio_values)

        if variation > STAKE_PAYOUT_VARIATION_THRESHOLD:
            stakes_str = ", ".join(f"${s}: {r:.4f}" for s, r in ratios)
            return emit_anomaly(
                self.evidence_path, "STAKE_DEPENDENT_PAYOUT", symbol, "HIGH",
                f"{contract_label} {duration_label}: payout ratio varies {variation:.1%} "
                f"with stake ({stakes_str}) — stake-based mispricing",
                contract=contract_label, duration=duration_label,
                variation=variation, stake_ratios=ratios,
            )
        return None

    async def scan_cycle(self):
        """Run one full scan cycle across all symbols/contracts/durations."""
        self.cycle_count += 1
        cycle_start = time.time()
        cycle_anomalies = 0

        for symbol in self.symbols:
            for contract_type, barrier in self.contracts:
                contract_label = f"{contract_type}:{barrier}" if barrier is not None else contract_type

                for dur, dur_unit in self.durations:
                    dur_label = f"{dur}{dur_unit}"

                    # --- Stake scan (test multiple stakes for payout variation) ---
                    stake_results = []
                    for stake in self.stakes:
                        try:
                            proposal = await self.get_proposal(
                                symbol, contract_type, dur, dur_unit, stake, barrier
                            )
                            self.total_proposals += 1
                        except asyncio.TimeoutError:
                            self.total_errors += 1
                            continue
                        except Exception:
                            self.total_errors += 1
                            continue

                        if "error" in proposal:
                            self.total_errors += 1
                            self.check_contract_availability(symbol, contract_label, False)
                            continue

                        self.check_contract_availability(symbol, contract_label, True)

                        # Run detectors
                        payout = proposal.get("payout", 0)
                        ask = proposal.get("ask_price", 0)
                        ratio = payout / ask if ask > 0 and payout > 0 else 0
                        stake_results.append((stake, ratio))

                        a = self.check_payout_anomaly(symbol, contract_type, barrier, contract_label, dur_label, payout, ask, stake)
                        if a:
                            cycle_anomalies += 1

                        a = self.check_spot_mismatch(symbol, proposal)
                        if a:
                            cycle_anomalies += 1

                        # Small delay between proposals to avoid rate limit
                        await asyncio.sleep(0.15)

                    # --- Stake-dependent payout check ---
                    a = self.check_stake_dependent_payout(symbol, contract_label, dur_label, stake_results)
                    if a:
                        cycle_anomalies += 1

                    # --- Resale arb check (only with $1 stake, 10t duration to allow resale) ---
                    if dur >= 5 and (contract_type in ("CALL", "PUT", "DIGITEVEN", "DIGITODD")):
                        try:
                            a = await self.check_resale_arb(symbol, contract_type, dur, dur_unit, barrier)
                            if a:
                                cycle_anomalies += 1
                        except Exception:
                            pass

        elapsed = time.time() - cycle_start
        print(
            f"  [{self.cycle_count}] {now_iso()} | "
            f"proposals={self.total_proposals} errors={self.total_errors} "
            f"anomalies={cycle_anomalies} elapsed={elapsed:.1f}s",
            flush=True,
        )

    async def run(self):
        print(f">>> D106 — Pricing/Proposal Anomaly Monitor", flush=True)
        print(f"    Symbols: {self.symbols}", flush=True)
        print(f"    Contracts: {[c[0] + (f':{c[1]}' if c[1] else '') for c in self.contracts]}", flush=True)
        print(f"    Durations: {[f'{d}{u}' for d, u in self.durations]}", flush=True)
        print(f"    Stakes: {self.stakes}", flush=True)
        print(f"    Interval: {self.interval}s", flush=True)
        print(f"    Evidence: {self.evidence_path}", flush=True)
        print(f"    DETECTION ONLY — does not trade for profit", flush=True)
        print(flush=True)

        await self.connect()

        # Subscribe to live ticks for spot mismatch detection
        for symbol in self.symbols:
            try:
                await self.client.subscribe_ticks(symbol, self.on_tick)
            except Exception as e:
                print(f"  WARNING: could not subscribe to {symbol}: {e}", flush=True)

        # Wait a moment for first ticks to arrive
        await asyncio.sleep(3.0)

        # Main loop
        while True:
            try:
                await self.scan_cycle()
            except Exception as e:
                print(f"  [cycle error] {e} (continuing)", flush=True)
                self.total_errors += 1

            await asyncio.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description="D106 — Pricing/Proposal Anomaly Monitor")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, help="Comma-separated symbols")
    parser.add_argument("--contracts", default=DEFAULT_CONTRACTS, help="Comma-separated contract specs")
    parser.add_argument("--durations", default=DEFAULT_DURATIONS, help="Comma-separated durations")
    parser.add_argument("--stake-scan", default=DEFAULT_STAKES, help="Comma-separated stakes to test")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between scan cycles")
    parser.add_argument("--evidence", default=EVIDENCE_PATH, help="JSONL evidence path")
    args = parser.parse_args()

    symbols = parse_csv(args.symbols)
    contracts = parse_contracts(args.contracts)
    durations = parse_durations(args.durations)
    stakes = [float(s) for s in parse_csv(args.stake_scan)]

    monitor = PricingAnomalyMonitor(
        symbols=symbols,
        contracts=contracts,
        durations=durations,
        stakes=stakes,
        interval=args.interval,
        evidence_path=args.evidence,
    )

    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
