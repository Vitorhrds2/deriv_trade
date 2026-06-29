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
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Optional

from anomaly_stats import (
    CHI2_CRIT_DF9,
    Z_CRIT,
    chi_square_uniform,
    digit_z_scores,
    ev_bounds,
    implied_prob,
    runs_test_z,
    spike_timing_z,
    wilson_interval,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_BARRIER_CONTRACTS = ("DIGITOVER", "DIGITUNDER", "DIGITDIFF", "DIGITMATCH")
_DEFAULT_BARRIER = {"DIGITOVER": 0, "DIGITUNDER": 9, "DIGITDIFF": 0, "DIGITMATCH": 0}

# Deteccao de spike (Boom/Crash): um spike e um retorno na direcao do indice cujo
# modulo excede SPIKE_MULT x a mediana do |retorno| recente (o drift normal).
SPIKE_MULT = 8.0
SPIKE_MIN_SCALE = 50  # |retornos| recentes minimos antes de estimar a escala


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
    min_spikes: int = 25
    prime: int = 0
    cycle: float = 5.0
    ev_interval: float = 8.0
    ev_gap: float = 0.25
    chi2_level: float = 0.001
    z_level: float = 0.001
    persistence: int = 3
    persist_turnover: float = 0.5
    cost_margin: float = 0.01
    freeze_ticks: int = 5
    stall_timeout: float = 30.0
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
    vet_sample: int = 30000
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


def parse_spike_index(symbol):
    """(direcao, N) para indices Boom/Crash; (0, 0) caso contrario.

    Boom sobe num spike raro (direcao +1); Crash cai (direcao -1). N = media de
    ticks por spike, extraida do nome (BOOM1000->1000, CRASH300N->300).
    """
    s = (symbol or "").upper()
    if s.startswith("BOOM"):
        direction = 1
    elif s.startswith("CRASH"):
        direction = -1
    else:
        return 0, 0
    m = re.search(r"(\d+)", s)
    return direction, (int(m.group(1)) if m else 0)


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
        # Estado de spike (so usado em Boom/Crash).
        self.spike_dir, self.spike_n = parse_spike_index(symbol)
        self.abs_returns = deque(maxlen=512)
        self.spike_gaps = deque(maxlen=400)
        self.ticks_since_spike = 0
        self.spike_count = 0
        self.spike_seen = False

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
            self._track_spike(price - self.last_price)
        self.prices.append(price)
        if self.pip:
            self.digits.append(last_digit(price, self.pip))
        self.last_price = price
        self.last_epoch = epoch

    def _track_spike(self, r):
        # So Boom/Crash. Spike = retorno grande na direcao do indice; entre spikes
        # o preco faz um drift pequeno no sentido oposto.
        if not self.spike_dir:
            return
        if len(self.abs_returns) >= SPIKE_MIN_SCALE:
            thr = median(self.abs_returns) * SPIKE_MULT
            is_spike = thr > 0 and abs(r) > thr and ((r > 0) == (self.spike_dir > 0))
            if is_spike:
                if self.spike_seen:  # descarta o 1o gap (medido desde o inicio)
                    self.spike_gaps.append(self.ticks_since_spike + 1)
                self.spike_seen = True
                self.ticks_since_spike = 0
                self.spike_count += 1
            else:
                self.ticks_since_spike += 1
        else:
            self.ticks_since_spike += 1
        self.abs_returns.append(abs(r))

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


def vet_ev_on_prices(symbol, prices, pip, spec, gross, cfg):
    """Re-mede o EV de um contrato numa amostra grande e INDEPENDENTE da janela deslizante.
    Mata o falso-positivo de variancia: o R_50/DIGITUNDER:4 deu p_win~43.7% em 2000 ticks,
    mas 39.98% (o valor justo) em 40k. Retorna dict (survived/ev_lo/ev_hi/p_lo/p_hi/n) ou
    None se a amostra for insuficiente para um veredito confiavel."""
    if not prices or pip is None:
        return None
    st = SymbolState(symbol, len(prices) + 1, pip=pip)
    ep = 1_700_000_000
    for px in prices:
        ep += 1
        try:
            st.on_tick(ep, float(px))
        except (ValueError, TypeError):
            pass
    s, n = contract_success_count(st, spec)
    if n < max(cfg.min_samples, 2000):
        return None
    p_lo, p_hi = wilson_interval(s, n)
    ev_lo, ev_hi = ev_bounds(p_lo, p_hi, gross)
    return {"survived": bool(ev_lo > cfg.cost_margin), "ev_lo": ev_lo, "ev_hi": ev_hi,
            "p_lo": p_lo, "p_hi": p_hi, "n": n}


def detect_spike_timing(state, cfg):
    # Cadencia de spikes Boom/Crash vs. especificacao (~1 spike a cada N ticks).
    # Um desvio persistente = bug/mispricing no gerador (anomalia operacional).
    if not state.spike_dir or state.spike_n <= 0:
        return []
    gaps = list(state.spike_gaps)
    if len(gaps) < cfg.min_spikes:
        return []
    z = spike_timing_z(gaps, state.spike_n)
    if abs(z) < cfg.z_crit:
        return []
    mean_gap = sum(gaps) / len(gaps)
    desc = ("spikes ACELERADOS (mais frequentes que o spec)" if mean_gap < state.spike_n
            else "spikes ATRASADOS (mais raros que o spec)")
    msg = (f"cadencia de spikes fora do spec: gap medio {mean_gap:.0f} vs "
           f"{state.spike_n} ticks (z={z:+.2f}, {len(gaps)} spikes) -> {desc}")
    return [_anomaly(state.symbol, "SPIKE_TIMING", "cadence", "HIGH", msg,
                     mean_gap=mean_gap, expected_gap=state.spike_n, z=z, spikes=len(gaps))]


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


def streak_confirm(ss, tick_count, persistence, need_fresh):
    """Gate de persistencia por VIRADA DE JANELA (mata falso-positivo de variancia).

    O gate antigo (N ciclos seguidos) era enganado por janelas de turnover lento: ex.
    R_50 ticka ~1/2s, entao em 15s (3 ciclos) a janela de 2000 mal muda e uma flutuacao
    amostral "persiste" trivialmente (foi o que gerou 36 falsos R_50/DIGITUNDER:4). Aqui
    so confirma se, desde que a anomalia comecou a aparecer, entraram >= need_fresh ticks
    NOVOS (dado fresco de verdade), e no maximo 1x por episodio. `ss` e o estado por chave
    (None p/ iniciar). Retorna (ss, confirma_agora, fresh_ticks).
    """
    if ss is None:
        ss = {"cycles": 0, "start_count": tick_count, "emitted": False}
    ss["cycles"] += 1
    fresh = tick_count - ss["start_count"]
    confirm_now = (not ss["emitted"]
                   and ss["cycles"] >= persistence
                   and fresh >= need_fresh)
    if confirm_now:
        ss["emitted"] = True
    return ss, confirm_now, fresh


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
        self.streak_state = {}
        self.last_wall = {}
        self._stalled = set()
        self._stop = asyncio.Event()
        self._ev_enabled = bool(cfg.api_token) and bool(cfg.contracts)

    async def on_tick(self, data):
        t = data.get("tick")
        if not t:
            return
        sym = t.get("symbol")
        st = self.states.get(sym)
        if st is None:
            return
        self.last_wall[sym] = time.monotonic()
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

    async def _fetch_history(self, symbol, count):
        # ticks_history entrega <=1000 ticks/request; pagina para tras pelo tempo.
        times, prices = [], []
        end = "latest"
        remaining = int(count)
        while remaining > 0:
            c = min(1000, remaining)
            res = await self.client.send_request({
                "ticks_history": symbol, "end": end, "count": c, "style": "ticks",
            })
            hist = res.get("history") or {}
            ps, ts = hist.get("prices") or [], hist.get("times") or []
            if not ps:
                break
            times = list(ts) + times
            prices = list(ps) + prices
            remaining -= len(ps)
            if len(ps) < c:
                break
            end = int(ts[0]) - 1
        return times, prices

    async def _vet_ev_edge(self, symbol, spec, gross):
        """Puxa uma amostra FRESCA e grande (cfg.vet_sample) e re-mede o EV do contrato,
        independente da janela deslizante. Um blip de variancia (ex.: DIGITUNDER:4 a 43.7%
        em 2000 ticks) regride ao valor justo (~40%) numa amostra grande e e rejeitado."""
        st = self.states.get(symbol)
        pip = st.pip if st else None
        try:
            _, prices = await self._fetch_history(symbol, self.cfg.vet_sample)
        except Exception as e:
            return {"survived": True, "inconclusive": True, "note": f"fetch falhou: {e}"}
        prices = [float(p) for p in prices]
        if pip is None and prices:
            pip = infer_pip(prices)
        res = vet_ev_on_prices(symbol, prices, pip, spec, gross, self.cfg)
        if res is None:
            return {"survived": True, "inconclusive": True, "note": f"amostra insuficiente (n={len(prices)})"}
        return res

    async def _confirm_or_reject_ev(self, a, symbol):
        """Vet de amostra fresca ANTES de escalar um EV_EDGE para CRITICAL. Sobreviveu ->
        emite com a prova. Nao sobreviveu -> rebaixa para EV_EDGE_REJECTED (blip auditavel)."""
        spec = next((s for s in self.cfg.contracts if s.label == a["key"]), None)
        gross = a["stats"].get("gross_return")
        if spec is None or not gross:
            self.logger.emit(a)
            return
        vet = await self._vet_ev_edge(symbol, spec, gross)
        a["stats"]["vet"] = vet
        if vet.get("survived"):
            if vet.get("inconclusive"):
                a["message"] += f" | VET INCONCLUSIVO ({vet.get('note', '')}) -> emitido com ressalva"
            else:
                a["message"] += (f" | VET OK em amostra fresca n={vet['n']}: "
                                 f"EV_lo={vet['ev_lo']:+.4f}, p in [{vet['p_lo'] * 100:.2f}%, {vet['p_hi'] * 100:.2f}%]")
            self.logger.emit(a)
        else:
            a["klass"] = "EV_EDGE_REJECTED"
            a["severity"] = "INFO"
            a["message"] = (f"{a['key']}: REJEITADO pelo vet de amostra fresca (blip de variancia). "
                            f"Janela dizia EV_lo={a['stats'].get('ev_lo', 0.0):+.4f}; amostra fresca n={vet['n']} "
                            f"da EV_lo={vet['ev_lo']:+.4f} (p in [{vet['p_lo'] * 100:.2f}%, {vet['p_hi'] * 100:.2f}%], "
                            f"margem {self.cfg.cost_margin:+.3f})")
            self.logger.emit(a)

    async def _prime_from_history(self):
        # Pre-carrega as janelas com historico real -> detectores ativos no 1o ciclo
        # (sem cegueira de aquecimento) e pip confiavel por amostra grande.
        if self.cfg.prime <= 0:
            return
        for sym, st in self.states.items():
            try:
                times, prices = await self._fetch_history(sym, self.cfg.prime)
            except Exception as e:
                print(f"  AVISO priming[{sym}] falhou: {e}")
                continue
            if not prices:
                continue
            if st.pip is None and len(prices) >= 64:
                st.set_pip(infer_pip(prices))
                print(f"  pip[{sym}] = {st.pip} (inferido do historico)")
            for ep, px in zip(times, prices):
                try:
                    st.on_tick(int(ep), float(px))
                except (ValueError, TypeError):
                    pass
            extra = f", spikes={st.spike_count}" if st.spike_dir else ""
            print(f"  priming[{sym}]: {len(prices)} ticks (n={st.tick_count}{extra})")

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
            spk = ""
            if st.spike_dir:
                g = (sum(st.spike_gaps) / len(st.spike_gaps)) if st.spike_gaps else 0.0
                spk = f" spk={st.spike_count},gap~{g:.0f}/{st.spike_n}"
            parts.append(f"{sym}:n={st.tick_count},chi2={chi:.1f},dup={st.dup_run}{best}{spk}")
        rc = getattr(self.client, "_reconnects", 0)
        tail = f" | rc={rc}" if rc else ""
        print(f"  . {datetime.now().strftime('%H:%M:%S')} | " + " | ".join(parts) + tail, flush=True)

    async def _detector_loop(self):
        cfg = self.cfg
        start = time.time()
        cycles = 0
        while not self._stop.is_set():
            await asyncio.sleep(cfg.cycle)
            # Blindagem: um erro inesperado num ciclo NAO pode encerrar uma vigilia de
            # dias/semanas. Loga e segue (CancelledError nao e Exception -> cancela ok).
            try:
                self._ensure_pips()
                active = set()
                for sym, st in self.states.items():
                    cands = []
                    cands += detect_rng_bias(st, cfg)
                    cands += detect_runs(st, cfg)
                    cands += detect_feed(st, cfg)
                    cands += detect_ev(st, self.gross_returns.get(sym, {}), cfg)
                    cands += detect_spike_timing(st, cfg)
                    for a in cands:
                        if a.get("immediate"):
                            self.logger.emit(a)
                            continue
                        sym_a = a["symbol"]
                        key = (sym_a, a["klass"], a["key"])
                        active.add(key)
                        st_a = self.states[sym_a]
                        need = int(cfg.persist_turnover * st_a.window)
                        ss, confirm_now, fresh = streak_confirm(
                            self.streak_state.get(key), st_a.tick_count,
                            cfg.persistence, need)
                        self.streak_state[key] = ss
                        if confirm_now:
                            a["streak"] = ss["cycles"]
                            a["stats"]["fresh_ticks"] = fresh
                            a["stats"]["turnover"] = round(fresh / st_a.window, 3)
                            if a["klass"] == "EV_EDGE" and cfg.vet_sample > 0:
                                await self._confirm_or_reject_ev(a, sym_a)
                            else:
                                self.logger.emit(a)
                for key in list(self.streak_state):
                    if key not in active:
                        del self.streak_state[key]
                cycles += 1
                self._heartbeat()
            except Exception as e:
                print(f"  [detector] erro no ciclo (ignorado p/ manter a vigilia): {e}", flush=True)
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

    def _eval_stalls(self, silent_by_sym):
        # Latch: marca stall UMA vez por episodio e limpa ao retomar (evita spam).
        new_stall, recovered = [], []
        for sym, silent in silent_by_sym.items():
            if silent >= self.cfg.stall_timeout:
                if sym not in self._stalled:
                    self._stalled.add(sym)
                    new_stall.append(sym)
            elif sym in self._stalled:
                self._stalled.discard(sym)
                recovered.append(sym)
        return new_stall, recovered

    async def _watchdog_loop(self):
        # Vigia a SAUDE do feed: se um simbolo fica em silencio (sem ticks) alem do
        # limite, alarma FEED_STALL. O bug real (WS 1011 ping timeout) deixava o monitor
        # "vivo" mas cego — isto torna a falha VISIVEL. A reconexao em si e do cliente
        # (auto-reconnect com backoff); aqui so observamos e registramos evidencia.
        cfg = self.cfg
        started = time.monotonic()
        interval = max(2.0, min(cfg.stall_timeout / 2.0, 10.0))
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            try:
                now = time.monotonic()
                silent = {sym: now - self.last_wall.get(sym, started) for sym in cfg.symbols}
                new_stall, recovered = self._eval_stalls(silent)
                rc = getattr(self.client, "_reconnects", 0)
                for sym in new_stall:
                    self.logger.emit(_anomaly(
                        sym, "FEED_STALL", "stall", "HIGH",
                        f"sem ticks ha {silent[sym]:.0f}s (limite {cfg.stall_timeout:.0f}s); "
                        f"WS caiu? auto-reconnect do cliente em curso (reconexoes={rc})",
                        immediate=True, silent_s=round(silent[sym], 1), reconnects=rc))
                for sym in recovered:
                    print(f"  [feed] {sym} retomou ticks (reconexoes={rc})", flush=True)
            except Exception as e:
                print(f"  [watchdog] erro (ignorado): {e}", flush=True)

    async def run(self):
        print(f">>> Monitor de anomalias sinteticas | simbolos={','.join(self.cfg.symbols)}")
        print(f"    janela={self.cfg.window} min_amostras={self.cfg.min_samples} "
              f"min_spikes={self.cfg.min_spikes} prime={self.cfg.prime} "
              f"persistencia={self.cfg.persistence}c+turnover>={self.cfg.persist_turnover:.0%} "
              f"chi2_crit={self.cfg.chi2_crit:.1f} "
              f"margem_custo={self.cfg.cost_margin:+.3f} stall={self.cfg.stall_timeout:.0f}s")
        print(f"    EV/mispricing: {'ON' if self._ev_enabled else 'OFF (sem DERIV_API_TOKEN)'} | "
              f"contratos={[s.label for s in self.cfg.contracts] or '-'}")
        print(f"    evidencia -> {self.cfg.evidence_path or '(stdout)'} | DETECCAO APENAS (nao opera)")
        await self.client.connect()
        await self._load_pips()
        await self._prime_from_history()
        for sym in self.cfg.symbols:
            await self.client.subscribe_ticks(sym, self.on_tick)
        tasks = [asyncio.create_task(self._detector_loop()),
                 asyncio.create_task(self._watchdog_loop())]
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


def _feed_spikes(state, n_spikes, period, base=10000.0, start_epoch=1_700_000_000):
    """Alimenta um Boom/Crash: drift pequeno (1) no sentido oposto + spike grande
    (50) na direcao do indice a cada `period` ticks. Gaps observados ~= period."""
    ep = start_epoch
    price = base
    d = state.spike_dir or 1
    total = n_spikes * period + SPIKE_MIN_SCALE + 5
    for i in range(1, total + 1):
        ep += 1
        price += (50.0 * d) if (i % period == 0) else (-1.0 * d)
        state.on_tick(ep, round(price, 4))


def run_selftest():
    cfg = Config(window=1500, min_samples=400, persistence=3, cost_margin=0.01,
                 chi2_level=0.001, min_spikes=25, stall_timeout=30.0,
                 contracts=parse_contracts("CALL,DIGITEVEN"))
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

    # 6) SPIKE CONTROLE: Boom com spikes na cadencia do spec (N=300) NAO dispara.
    st = SymbolState("BOOM300N", cfg.window)
    _feed_spikes(st, n_spikes=30, period=300)
    check(not detect_spike_timing(st, cfg), "spike controle (cadencia=spec) -> sem alarme")

    # 7) SPIKE INJECAO: spikes 3x mais rapidos (cada 100 vs 300) -> SPIKE_TIMING.
    st = SymbolState("BOOM300N", cfg.window)
    _feed_spikes(st, n_spikes=30, period=100)
    sp = detect_spike_timing(st, cfg)
    check(bool(sp) and sp[0]["stats"]["z"] < 0, "spike injecao 3x acelerado -> SPIKE_TIMING (z<0)")

    # 8) FEED STALL: watchdog marca stall apos silencio e limpa ao retomar (latch).
    m = Monitor(Config(symbols=["1HZ10V", "R_10"], stall_timeout=30.0))
    ns, _ = m._eval_stalls({"1HZ10V": 45.0, "R_10": 3.0})
    no_realarm, _ = m._eval_stalls({"1HZ10V": 50.0, "R_10": 3.0})
    _, rec = m._eval_stalls({"1HZ10V": 2.0, "R_10": 3.0})
    check("1HZ10V" in ns and "R_10" not in ns and not no_realarm and "1HZ10V" in rec,
          "feed stall: alarme no silencio, sem realarme, recovery ao retomar")

    # 9) PERSISTENCIA POR TURNOVER (mata o falso-positivo tipo R_50/DIGITUNDER:4): a MESMA
    #    janela parada nao confirma por mais ciclos que passem; so confirma quando entra
    #    dado fresco suficiente, e no maximo 1x por episodio.
    need = int(0.5 * 2000)
    ss = None
    stale_never = True
    for _ in range(50):  # 50 ciclos sem nenhum tick novo (tick_count fixo)
        ss, conf, _ = streak_confirm(ss, 10_000, 3, need)
        stale_never = stale_never and not conf
    ss, conf_fresh, _ = streak_confirm(ss, 10_000 + need, 3, need)        # entrou dado fresco
    ss, conf_again, _ = streak_confirm(ss, 10_000 + need + 500, 3, need)  # nao re-emite
    check(stale_never and conf_fresh and not conf_again,
          "persistencia por turnover: janela parada nao confirma; dado fresco confirma 1x")

    # 10) AUTO-VET de amostra fresca (mata o blip tipo R_50/DIGITUNDER:4): re-medido numa
    #     amostra grande UNIFORME o "edge" some (REJEITADO); num vies de digito REAL sobrevive.
    spec_u4 = parse_contracts("DIGITUNDER:4")[0]
    rng2 = random.Random(99)
    fair = [round(100.0 + rng2.randrange(10) * 0.01, 10) for _ in range(30000)]
    vet_fair = vet_ev_on_prices("R_50", fair, 0.01, spec_u4, 2.43, cfg)
    biased_px = []
    for _ in range(30000):
        d = rng2.randrange(10)
        if d >= 4 and rng2.random() < 0.30:
            d = rng2.randrange(4)
        biased_px.append(round(100.0 + d * 0.01, 10))
    vet_biased = vet_ev_on_prices("R_50", biased_px, 0.01, spec_u4, 2.43, cfg)
    check(vet_fair is not None and not vet_fair["survived"]
          and vet_biased is not None and vet_biased["survived"],
          "auto-vet: blip uniforme REJEITADO; vies real SOBREVIVE")

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
        persist_turnover=args.persist_turnover,
        chi2_level=args.chi2_level, z_level=args.z_level, cost_margin=args.cost_margin,
        freeze_ticks=args.freeze_ticks, stall_timeout=args.stall_timeout,
        stake=args.stake, duration=args.duration,
        min_spikes=args.min_spikes, prime=(args.prime or args.window),
        use_demo=not args.real, app_id=app_id, api_token=api_token,
        evidence_path=evidence, max_runtime=args.max_runtime, vet_sample=args.vet_sample,
    )


def main():
    ap = argparse.ArgumentParser(description="Monitor ao vivo de anomalias sinteticas (Deriv)")
    ap.add_argument("--symbols", default="1HZ10V,1HZ100V,R_10")
    ap.add_argument("--contracts", default="DIGITEVEN,DIGITODD,CALL,PUT,DIGITDIFF:0")
    ap.add_argument("--window", type=int, default=2000)
    ap.add_argument("--min-samples", type=int, default=500, dest="min_samples")
    ap.add_argument("--min-spikes", type=int, default=25, dest="min_spikes",
                    help="min de spikes Boom/Crash antes de avaliar a cadencia")
    ap.add_argument("--prime", type=int, default=0,
                    help="ticks de historico para pre-carregar (0 = usar --window)")
    ap.add_argument("--cycle", type=float, default=5.0)
    ap.add_argument("--ev-interval", type=float, default=8.0, dest="ev_interval")
    ap.add_argument("--persistence", type=int, default=3,
                    help="piso de ciclos seguidos (gate secundario; o principal e --persist-turnover)")
    ap.add_argument("--persist-turnover", type=float, default=0.5, dest="persist_turnover",
                    help="fracao da janela que precisa ser de ticks NOVOS p/ confirmar (mata variancia de janela parada)")
    ap.add_argument("--chi2-level", type=float, default=0.001, dest="chi2_level",
                    choices=[0.05, 0.01, 0.001])
    ap.add_argument("--z-level", type=float, default=0.001, dest="z_level",
                    choices=[0.05, 0.01, 0.001])
    ap.add_argument("--cost-margin", type=float, default=0.01, dest="cost_margin")
    ap.add_argument("--freeze-ticks", type=int, default=5, dest="freeze_ticks")
    ap.add_argument("--stall-timeout", type=float, default=30.0, dest="stall_timeout",
                    help="segundos sem ticks por simbolo antes de alarmar FEED_STALL")
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=1)
    ap.add_argument("--max-runtime", type=float, default=0.0, dest="max_runtime")
    ap.add_argument("--vet-sample", type=int, default=30000, dest="vet_sample",
                    help="ticks frescos p/ revalidar um EV_EDGE antes de escalar a CRITICAL (0 desliga)")
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
