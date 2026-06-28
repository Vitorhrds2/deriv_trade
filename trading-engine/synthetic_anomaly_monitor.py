"""Monitor AO VIVO de anomalias em indices sinteticos da Deriv.

Por que existe
--------------
O relatorio `docs/edge_investigation_report.md` REFUTOU um edge de ESTRUTURA FIXA:
em regime normal todos os 46 contratos tem EV negativo (margem da casa embutida no
payout). Mas o "jackpot" que ja foi explorado uma vez era TRANSIENTE — um mispricing
ou bug operacional que a Deriv corrigiu em dias. Backtest estatico nao captura isso.
Este modulo e o instrumento certo: vigia o feed em tempo real e dispara quando uma
janela momentanea fica estatisticamente +EV ou quando o RNG/feed se comporta fora da
especificacao.

Filosofia (a mesma que matou o Oraculo)
---------------------------------------
  - Nada de capital sem significancia estatistica.
  - EV so e "edge" se o LIMITE INFERIOR de Wilson de (p_win * payout - 1) bater a
    margem de custo. Pessimista de proposito.
  - Anomalia so e confirmada se PERSISTIR por N ciclos seguidos (mata variancia).
  - Tudo vira evidencia auditavel (JSONL com timestamp) — rastreabilidade.
  - O monitor NAO opera. Ele caca e registra. Armar capital e um passo separado.

Uso
---
    # Teste offline (sem rede, sem credenciais) — prova que os detectores funcionam:
    python synthetic_anomaly_monitor.py --selftest

    # Ao vivo (precisa DERIV_APP_ID; EV precisa tambem de DERIV_API_TOKEN no .env):
    python synthetic_anomaly_monitor.py --symbols 1HZ10V,1HZ100V,R_10 \
        --contracts DIGITEVEN,DIGITODD,CALL,PUT,DIGITDIFF:0

Evidencia bruta: logs/anomaly_monitor/anomalies.jsonl
"""
import argparse
import asyncio
import json
import math
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from anomaly_stats import (
    CHI2_CRIT_DF9,
    Z_CRIT,
    chi_square_uniform,
    digit_z_scores,
    ev_bounds,
    implied_prob,
    runs_test_z,
    wilson_interval,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_BARRIER_CONTRACTS = ("DIGITOVER", "DIGITUNDER", "DIGITDIFF", "DIGITMATCH")
_DEFAULT_BARRIER = {"DIGITOVER": 0, "DIGITUNDER": 9, "DIGITDIFF": 0, "DIGITMATCH": 0}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class ContractSpec:
    name: str
    barrier: Optional[int]
    label: str


@dataclass
class Config:
    symbols: list = field(default_factory=lambda: ["1HZ10V", "1HZ100V", "R_10"])
    contracts: list = field(default_factory=list)
    window: int = 2000
    min_samples: int = 500
    cycle: float = 5.0
    ev_interval: float = 8.0
    ev_gap: float = 0.25
    chi2_level: float = 0.001
    z_level: float = 0.001
    persistence: int = 3
    cost_margin: float = 0.01
    freeze_ticks: int = 5
    interval_tol_lo: float = 0.5
    interval_tol_hi: float = 2.0
    stake: float = 1.0
    duration: int = 1
    duration_unit: str = "t"
    use_demo: bool = True
    app_id: str = "1089"
    api_token: str = ""
    evidence_path: str = ""
    max_runtime: float = 0.0
    chi2_crit: float = 0.0
    z_crit: float = 0.0

    def __post_init__(self):
        self.chi2_crit = CHI2_CRIT_DF9.get(self.chi2_level, CHI2_CRIT_DF9[0.001])
        self.z_crit = Z_CRIT.get(self.z_level, Z_CRIT[0.001])


def parse_contracts(raw):
    specs = []
    for tok in [t.strip() for t in raw.split(",") if t.strip()]:
        if ":" in tok:
            name, b = tok.split(":", 1)
            name = name.strip().upper()
            barrier = int(b)
        else:
            name = tok.strip().upper()
            barrier = _DEFAULT_BARRIER.get(name) if name in _BARRIER_CONTRACTS else None
        specs.append(ContractSpec(name=name, barrier=barrier, label=tok.strip().upper()))
    return specs


# --------------------------------------------------------------------------- #
# Helpers Deriv (pip / digito / payout) — reproduzem a logica CORRETA do scan
# --------------------------------------------------------------------------- #
def last_digit(price, pip):
    return int(round(float(price) / pip)) % 10


def infer_pip(prices):
    min_diff = None
    for i in range(1, len(prices)):
        d = abs(round(float(prices[i]) - float(prices[i - 1]), 10))
        if d > 0 and (min_diff is None or d < min_diff):
            min_diff = d
    if not min_diff:
        return 0.01
    decimals = max(0, min(round(-math.log10(min_diff)), 8))
    return 10 ** (-decimals)


def expected_interval(symbol):
    if symbol.startswith("1HZ"):
        return 1.0
    if symbol.startswith("R_"):
        return 2.0
    if symbol.startswith(("BOOM", "CRASH")):
        return 1.0
    return None


async def get_gross_return(client, symbol, spec, stake, duration, dunit):
    payload = {
        "proposal": 1, "amount": stake, "basis": "stake",
        "contract_type": spec.name, "currency": "USD",
        "underlying_symbol": symbol, "duration": duration, "duration_unit": dunit,
    }
    if spec.barrier is not None and spec.name in _BARRIER_CONTRACTS:
        payload["barrier"] = str(spec.barrier)
    res = await client.send_request(payload)
    if "error" in res:
        return None
    p = res.get("proposal", {})
    payout, ask = p.get("payout"), p.get("ask_price")
    if not payout or not ask:
        return None
    return payout / ask


# --------------------------------------------------------------------------- #
# Estado por simbolo
# --------------------------------------------------------------------------- #
class SymbolState:
    def __init__(self, symbol, window, pip=None):
        self.symbol = symbol
        self.window = window
        self.pip = pip
        self.prices = deque(maxlen=window)
        self.digits = deque(maxlen=window)
        self.moves = deque(maxlen=window)
        self.interarrivals = deque(maxlen=window)
        self.last_price = None
        self.last_epoch = None
        self.dup_run = 0
        self.tick_count = 0

    def on_tick(self, epoch, price):
        self.tick_count += 1
        if self.last_epoch is not None:
            dt = epoch - self.last_epoch
            if dt >= 0:
                self.interarrivals.append(dt)
        if self.last_price is not None:
            if price > self.last_price:
                self.moves.append(1)
                self.dup_run = 0
            elif price < self.last_price:
                self.moves.append(0)
                self.dup_run = 0
            else:
                self.dup_run += 1
        self.prices.append(price)
        if self.pip:
            self.digits.append(last_digit(price, self.pip))
        self.last_price = price
        self.last_epoch = epoch

    def set_pip(self, pip):
        self.pip = pip
        self.digits = deque((last_digit(p, pip) for p in self.prices), maxlen=self.window)

    def digit_counts(self):
        c = [0] * 10
        for d in self.digits:
            c[d] += 1
        return c


def contract_success_count(state, spec):
    name, b = spec.name, spec.barrier
    if name in ("DIGITEVEN", "DIGITODD", "DIGITOVER", "DIGITUNDER", "DIGITDIFF", "DIGITMATCH"):
        counts = state.digit_counts()
        n = sum(counts)
        if n == 0:
            return 0, 0
        if name == "DIGITEVEN":
            s = sum(counts[d] for d in (0, 2, 4, 6, 8))
        elif name == "DIGITODD":
            s = sum(counts[d] for d in (1, 3, 5, 7, 9))
        elif name == "DIGITOVER":
            s = sum(counts[d] for d in range((b or 0) + 1, 10))
        elif name == "DIGITUNDER":
            s = sum(counts[d] for d in range(0, b if b is not None else 0))
        elif name == "DIGITDIFF":
            s = n - counts[b or 0]
        else:  # DIGITMATCH
            s = counts[b or 0]
        return s, n
    if name in ("CALL", "PUT"):
        n = len(state.moves)
        ups = sum(state.moves)
        return (ups if name == "CALL" else n - ups), n
    return 0, 0


# --------------------------------------------------------------------------- #
# Anomalias / detectores
# --------------------------------------------------------------------------- #
def _anomaly(symbol, klass, key, severity, message, immediate=False, **stats):
    return {
        "ts": time.time(),
        "iso": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "klass": klass, "key": key,
        "severity": severity, "message": message, "immediate": immediate,
        "stats": stats,
    }


def detect_rng_bias(state, cfg):
    counts = state.digit_counts()
    n = sum(counts)
    if n < cfg.min_samples:
        return []
    chi = chi_square_uniform(counts)
    if chi < cfg.chi2_crit:
        return []
    z = digit_z_scores(counts)
    worst = max(range(10), key=lambda d: abs(z[d]))
    msg = (f"distribuicao de digitos nao-uniforme: chi2={chi:.1f} "
           f"(>{cfg.chi2_crit:.1f}); digito {worst} z={z[worst]:+.2f} "
           f"({counts[worst] / n * 100:.2f}% vs 10%)")
    return [_anomaly(state.symbol, "RNG_BIAS", "chi2", "HIGH", msg,
                     chi2=chi, n=n, worst_digit=worst, worst_z=z[worst],
                     freq=[round(c / n, 4) for c in counts])]


def detect_runs(state, cfg):
    bits = list(state.moves)
    if len(bits) < cfg.min_samples:
        return []
    z = runs_test_z(bits)
    if abs(z) < cfg.z_crit:
        return []
    direction = "memoria (tendencia)" if z < 0 else "anti-memoria (reversao)"
    msg = f"teste de corridas anomalo: z={z:+.2f} -> {direction} no up/down"
    return [_anomaly(state.symbol, "RNG_RUNS", "runs", "MEDIUM", msg, runs_z=z, n=len(bits))]


def detect_feed(state, cfg):
    out = []
    if state.dup_run >= cfg.freeze_ticks:
        out.append(_anomaly(state.symbol, "FEED_FREEZE", "freeze", "HIGH",
                            f"feed congelado: {state.dup_run} ticks identicos consecutivos",
                            immediate=True, dup_run=state.dup_run))
    ia = list(state.interarrivals)
    if len(ia) >= cfg.min_samples:
        mean_dt = sum(ia) / len(ia)
        exp = expected_interval(state.symbol)
        if exp and (mean_dt > exp * cfg.interval_tol_hi or mean_dt < exp * cfg.interval_tol_lo):
            out.append(_anomaly(state.symbol, "FEED_TIMING", "timing", "MEDIUM",
                                f"intervalo medio {mean_dt:.2f}s fora do esperado (~{exp:.1f}s)",
                                mean_dt=mean_dt, expected=exp))
    return out


def detect_ev(state, gross_returns, cfg):
    out = []
    for spec in cfg.contracts:
        g = gross_returns.get(spec.label)
        if not g:
            continue
        s, n = contract_success_count(state, spec)
        if n < cfg.min_samples:
            continue
        p_lo, p_hi = wilson_interval(s, n)
        ev_lo, ev_hi = ev_bounds(p_lo, p_hi, g)
        if ev_lo > cfg.cost_margin:
            msg = (f"{spec.label}: EV_lo={ev_lo:+.4f}/$1 (>margem {cfg.cost_margin:+.3f}) | "
                   f"p_win in [{p_lo * 100:.2f}%, {p_hi * 100:.2f}%], payout liq {(g - 1) * 100:.2f}%, "
                   f"implicita {implied_prob(g) * 100:.2f}%, n={n}")
            out.append(_anomaly(state.symbol, "EV_EDGE", spec.label, "CRITICAL", msg,
                                ev_lo=ev_lo, ev_hi=ev_hi, p_lo=p_lo, p_hi=p_hi,
                                gross_return=g, n=n))
    return out


# --------------------------------------------------------------------------- #
# Logger de evidencias
# --------------------------------------------------------------------------- #
class AnomalyLogger:
    def __init__(self, path, cooldown=60.0):
        self.path = path
        self.cooldown = cooldown
        self._last = {}
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def emit(self, a):
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
        key = (a["symbol"], a["klass"], a["key"])
        now = time.time()
        if now - self._last.get(key, 0.0) >= self.cooldown:
            self._last[key] = now
            streak = a.get("streak")
            tag = f" x{streak}" if streak else ""
            print(f"  [{a['severity']}]{tag} {a['symbol']} {a['klass']}:{a['key']} | {a['message']}",
                  flush=True)


# --------------------------------------------------------------------------- #
# Orquestrador ao vivo
# --------------------------------------------------------------------------- #
class Monitor:
    def __init__(self, cfg):
        from deriv_client import DerivClient
        self.cfg = cfg
        self.client = DerivClient(app_id=cfg.app_id, api_token=cfg.api_token, use_demo=cfg.use_demo)
        self.states = {s: SymbolState(s, cfg.window) for s in cfg.symbols}
        self.gross_returns = {s: {} for s in cfg.symbols}
        self.logger = AnomalyLogger(cfg.evidence_path)
        self.streaks = {}
        self._stop = asyncio.Event()
        self._ev_enabled = bool(cfg.api_token) and bool(cfg.contracts)

    async def on_tick(self, data):
        t = data.get("tick")
        if not t:
            return
        st = self.states.get(t.get("symbol"))
        if st is None:
            return
        try:
            st.on_tick(int(t["epoch"]), float(t["quote"]))
        except (KeyError, ValueError, TypeError):
            pass

    async def _load_pips(self):
        # active_symbols (API options) usa 'underlying_symbol' e 'pip_size' — NAO
        # 'symbol'/'pip'. Errar a chave faz cair na inferencia (pip errado = digito
        # errado = exatamente o bug do relatorio de edge).
        try:
            res = await self.client.send_request({"active_symbols": "full"})
        except Exception:
            res = {}
        pips = {s.get("underlying_symbol"): s.get("pip_size")
                for s in res.get("active_symbols", []) if s.get("pip_size")}
        for sym, st in self.states.items():
            if pips.get(sym):
                st.set_pip(float(pips[sym]))
                print(f"  pip[{sym}] = {st.pip} (API)")
            else:
                print(f"  AVISO pip[{sym}]: nao veio da API; usara inferencia ao acumular ticks")

    def _ensure_pips(self):
        # Fallback so se a API falhar: exige amostra grande, senao a granularidade
        # observada engana (ex.: 1HZ25V inferido como pip=1 em poucos ticks).
        for st in self.states.values():
            if st.pip is None and len(st.prices) >= 512:
                st.set_pip(infer_pip(list(st.prices)))
                print(f"  pip[{st.symbol}] = {st.pip} (inferido, fallback)")

    def _heartbeat(self):
        parts = []
        for sym, st in self.states.items():
            chi = chi_square_uniform(st.digit_counts()) if st.digits else 0.0
            best = ""
            grs = self.gross_returns.get(sym, {})
            best_ev = None
            for spec in self.cfg.contracts:
                g = grs.get(spec.label)
                if not g:
                    continue
                s, n = contract_success_count(st, spec)
                if n < self.cfg.min_samples:
                    continue
                p_lo, _ = wilson_interval(s, n)
                ev_lo = p_lo * g - 1.0
                if best_ev is None or ev_lo > best_ev[0]:
                    best_ev = (ev_lo, spec.label)
            if best_ev:
                best = f" bestEV_lo={best_ev[0]:+.3f}({best_ev[1]})"
            parts.append(f"{sym}:n={st.tick_count},chi2={chi:.1f},dup={st.dup_run}{best}")
        print(f"  . {datetime.now().strftime('%H:%M:%S')} | " + " | ".join(parts), flush=True)

    async def _detector_loop(self):
        cfg = self.cfg
        start = time.time()
        cycles = 0
        while not self._stop.is_set():
            await asyncio.sleep(cfg.cycle)
            self._ensure_pips()
            active = set()
            for sym, st in self.states.items():
                cands = []
                cands += detect_rng_bias(st, cfg)
                cands += detect_runs(st, cfg)
                cands += detect_feed(st, cfg)
                cands += detect_ev(st, self.gross_returns.get(sym, {}), cfg)
                for a in cands:
                    if a.get("immediate"):
                        self.logger.emit(a)
                        continue
                    key = (a["symbol"], a["klass"], a["key"])
                    active.add(key)
                    self.streaks[key] = self.streaks.get(key, 0) + 1
                    if self.streaks[key] >= cfg.persistence:
                        a["streak"] = self.streaks[key]
                        self.logger.emit(a)
            for key in list(self.streaks):
                if key not in active:
                    self.streaks[key] = 0
            cycles += 1
            self._heartbeat()
            if cfg.max_runtime and (time.time() - start) >= cfg.max_runtime:
                self._stop.set()

    async def _ev_probe_loop(self):
        cfg = self.cfg
        while not self._stop.is_set():
            for sym in cfg.symbols:
                for spec in cfg.contracts:
                    try:
                        g = await get_gross_return(self.client, sym, spec, cfg.stake,
                                                   cfg.duration, cfg.duration_unit)
                    except Exception:
                        g = None
                    if g:
                        self.gross_returns[sym][spec.label] = g
                    await asyncio.sleep(cfg.ev_gap)
            await asyncio.sleep(cfg.ev_interval)

    async def run(self):
        print(f">>> Monitor de anomalias sinteticas | simbolos={','.join(self.cfg.symbols)}")
        print(f"    janela={self.cfg.window} min_amostras={self.cfg.min_samples} "
              f"persistencia={self.cfg.persistence} chi2_crit={self.cfg.chi2_crit:.1f} "
              f"margem_custo={self.cfg.cost_margin:+.3f}")
        print(f"    EV/mispricing: {'ON' if self._ev_enabled else 'OFF (sem DERIV_API_TOKEN)'} | "
              f"contratos={[s.label for s in self.cfg.contracts] or '-'}")
        print(f"    evidencia -> {self.cfg.evidence_path or '(stdout)'} | DETECCAO APENAS (nao opera)")
        await self.client.connect()
        await self._load_pips()
        for sym in self.cfg.symbols:
            await self.client.subscribe_ticks(sym, self.on_tick)
        tasks = [asyncio.create_task(self._detector_loop())]
        if self._ev_enabled:
            tasks.append(asyncio.create_task(self._ev_probe_loop()))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            self._stop.set()
            await self.client.disconnect()


# --------------------------------------------------------------------------- #
# Self-test offline (cama de teste minima — sem rede, sem credenciais)
# --------------------------------------------------------------------------- #
def _feed_digits(state, digit_seq, pip=0.01, base=100.0, start_epoch=1_700_000_000):
    state.set_pip(pip)
    ep = start_epoch
    for d in digit_seq:
        ep += 1
        state.on_tick(ep, round(base + d * pip, 10))


def run_selftest():
    cfg = Config(window=1500, min_samples=400, persistence=3, cost_margin=0.01,
                 chi2_level=0.001, contracts=parse_contracts("CALL,DIGITEVEN"))
    rng = random.Random(20240628)
    failures = []

    def check(cond, label):
        print(f"  {'PASS' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    # 1) CONTROLE: RNG uniforme NAO deve disparar vies (baixa taxa de falso-positivo).
    false_pos = 0
    trials = 60
    for _ in range(trials):
        st = SymbolState("1HZ10V", cfg.window)
        _feed_digits(st, [rng.randrange(10) for _ in range(cfg.window)])
        if detect_rng_bias(st, cfg):
            false_pos += 1
    check(false_pos <= 1, f"controle RNG uniforme: falso-positivo {false_pos}/{trials} (esperado ~0)")

    # 2) INJECAO: digito 7 suprimido (3%) deve disparar RNG_BIAS.
    st = SymbolState("1HZ10V", cfg.window)
    biased = []
    for _ in range(cfg.window):
        d = rng.randrange(10)
        if d == 7 and rng.random() > 0.3:
            d = rng.choice([0, 1, 2, 3, 4, 5, 6, 8, 9])
        biased.append(d)
    a = detect_rng_bias(st_fed(st, biased), cfg)
    check(bool(a) and a[0]["stats"]["worst_digit"] == 7, "injecao vies digito 7 -> RNG_BIAS detectado")

    # 3) EV CONTROLE: 50/50 com payout liq 95% (g=1.95) NAO e edge.
    st = SymbolState("1HZ10V", cfg.window)
    st.moves = deque([1, 0] * 1000, maxlen=cfg.window)
    check(not detect_ev(st, {"CALL": 1.95}, cfg), "EV controle g=1.95 (50/50) -> sem edge")

    # 4) EV INJECAO: mesmo 50/50, mas payout liq 120% (g=2.20) -> +EV confiavel.
    ev = detect_ev(st, {"CALL": 2.20}, cfg)
    check(bool(ev) and ev[0]["stats"]["ev_lo"] > cfg.cost_margin, "EV injecao g=2.20 (50/50) -> EV_EDGE detectado")

    # 5) FEED FREEZE: ticks identicos consecutivos -> alerta imediato.
    st = SymbolState("1HZ10V", cfg.window, pip=0.01)
    ep = 1_700_000_000
    for _ in range(cfg.freeze_ticks + 2):
        ep += 1
        st.on_tick(ep, 100.00)
    feed = detect_feed(st, cfg)
    check(any(x["klass"] == "FEED_FREEZE" for x in feed), "feed congelado -> FEED_FREEZE imediato")

    print(f"\n{'TODOS OS TESTES PASSARAM' if not failures else 'FALHAS: ' + ', '.join(failures)}")
    return 1 if failures else 0


def st_fed(state, digit_seq):
    _feed_digits(state, digit_seq)
    return state


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_config(args):
    api_token = os.getenv("DERIV_API_TOKEN", "") if not args.no_token else ""
    app_id = os.getenv("DERIV_APP_ID", "1089") or "1089"
    evidence = args.evidence or os.path.join("logs", "anomaly_monitor", "anomalies.jsonl")
    return Config(
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        contracts=parse_contracts(args.contracts),
        window=args.window, min_samples=args.min_samples, cycle=args.cycle,
        ev_interval=args.ev_interval, persistence=args.persistence,
        chi2_level=args.chi2_level, z_level=args.z_level, cost_margin=args.cost_margin,
        freeze_ticks=args.freeze_ticks, stake=args.stake, duration=args.duration,
        use_demo=not args.real, app_id=app_id, api_token=api_token,
        evidence_path=evidence, max_runtime=args.max_runtime,
    )


def main():
    ap = argparse.ArgumentParser(description="Monitor ao vivo de anomalias sinteticas (Deriv)")
    ap.add_argument("--symbols", default="1HZ10V,1HZ100V,R_10")
    ap.add_argument("--contracts", default="DIGITEVEN,DIGITODD,CALL,PUT,DIGITDIFF:0")
    ap.add_argument("--window", type=int, default=2000)
    ap.add_argument("--min-samples", type=int, default=500, dest="min_samples")
    ap.add_argument("--cycle", type=float, default=5.0)
    ap.add_argument("--ev-interval", type=float, default=8.0, dest="ev_interval")
    ap.add_argument("--persistence", type=int, default=3)
    ap.add_argument("--chi2-level", type=float, default=0.001, dest="chi2_level",
                    choices=[0.05, 0.01, 0.001])
    ap.add_argument("--z-level", type=float, default=0.001, dest="z_level",
                    choices=[0.05, 0.01, 0.001])
    ap.add_argument("--cost-margin", type=float, default=0.01, dest="cost_margin")
    ap.add_argument("--freeze-ticks", type=int, default=5, dest="freeze_ticks")
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=1)
    ap.add_argument("--max-runtime", type=float, default=0.0, dest="max_runtime")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--real", action="store_true", help="usa conta real (padrao: demo)")
    ap.add_argument("--no-token", action="store_true", dest="no_token",
                    help="ignora DERIV_API_TOKEN (desliga EV; so RNG/feed publicos)")
    ap.add_argument("--selftest", action="store_true", help="testes offline e sai")
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(run_selftest())

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    cfg = build_config(args)
    if not cfg.app_id:
        print("ERRO: defina DERIV_APP_ID no .env (use 1089 para dados publicos).")
        raise SystemExit(2)
    monitor = Monitor(cfg)
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuario.")


if __name__ == "__main__":
    main()
