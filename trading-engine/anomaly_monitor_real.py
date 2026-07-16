"""Anomaly Monitor para mercados com estrutura real (Binance).

Monitora microestrutura de mercados reais via WebSocket da Binance e detecta
anomalias estatisticamente significativas que NAO existem em indices sinteticos
(RNG memoryless). Categorias monitoradas:

  PRICE_SHOCK   - salto de preco em janela curta (microsegundos)
  VOLUME_SPIKE  - volume anormalmente alto em relacao a media movel
  SPREAD_WIDEN  - spread bid-ask se alarga abruptamente
  MOMENTUM_BURST- sequencia de ticks na mesma direcao acima do esperado
  FEED_STALL    - gap entre updates maior que o normal (infra)

Gate de decisao: so declara uma klass como "de interesse" apos >= MIN_KLASS_EVENTS
eventos da mesma categoria em JANELA_OBSERVACAO segundos. Isso evita falsos
positivos de uma unica observacao.

Uso:
  python anomaly_monitor_real.py --symbols btcusdt,ethusdt --interval 60
  python anomaly_monitor_real.py --symbols btcusdt --duration 3600

Nao faz trades. Nao precisa de keys. So observa.
"""
import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from collections import defaultdict, deque

try:
    import websockets
except ImportError:
    print("pip install websockets")
    raise

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] anomaly-monitor-real: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("anomaly-monitor-real")

# ---------------------------------------------------------------------------
# Parametros do gate (calibrados para mercado real, nao RNG sintetico)
# ---------------------------------------------------------------------------
JANELA_OBSERVACAO_S = 3600          # 1h de janela deslizante para contagem
MIN_KLASS_EVENTS = 2                # minimo de eventos da mesma klass para declarar "de interesse"
PRICE_SHOCK_THRESHOLD_PCT = 0.15    # 0.15% em <= 500ms (BTC move ~0.01%/tick normalmente)
VOLUME_SPIKE_SIGMA = 4.0            # 4 desvios-padrao acima da media mobil
SPREAD_WIDEN_SIGMA = 3.0            # 3 desvios-padrao no spread
MOMENTUM_BURST_MIN_TICKS = 8        # 8+ ticks consecutivos na mesma direcao
FEED_STALL_THRESHOLD_MS = 5000      # 5s sem update = stall
VOLUME_WINDOW = 100                 # janela para media movel de volume
SPREAD_WINDOW = 100                 # janela para media movel de spread


class MarketMonitor:
    """Monitora um unico simbolo via Binance bookTicker + aggTrade streams."""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.last_bid = None
        self.last_ask = None
        self.last_price = None
        self.last_update_time = time.time()

        # Buffers para deteccao
        self.price_history = deque(maxlen=200)       # (timestamp, price)
        self.volume_history = deque(maxlen=VOLUME_WINDOW)  # quantidades
        self.spread_history = deque(maxlen=SPREAD_WINDOW)  # spreads em bps
        self.tick_directions = deque(maxlen=20)      # +1 / -1 por tick

        # Contagem de eventos por klass (janela deslizante)
        self.events = defaultdict(lambda: deque(maxlen=500))  # klass -> deque(timestamps)

        # Stats acumuladas
        self.total_events = 0
        self.total_ticks = 0

    def _prune_old_events(self, now: float):
        """Remove eventos fora da janela de observacao."""
        cutoff = now - JANELA_OBSERVACAO_S
        for klass in list(self.events.keys()):
            dq = self.events[klass]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq:
                del self.events[klass]

    def _record_event(self, klass: str, detail: str, now: float):
        self.events[klass].append(now)
        self.total_events += 1
        self._prune_old_events(now)
        count = len(self.events[klass])
        logger.info(
            f"[{self.symbol}] {klass} | {detail} "
            f"(count={count}, min_gate={MIN_KLASS_EVENTS})"
        )

    def _klasses_of_interest(self) -> list:
        """Retorna klasses que atingiram o minimo de eventos na janela."""
        return [k for k, dq in self.events.items() if len(dq) >= MIN_KLASS_EVENTS]

    def _check_price_shock(self, price: float, now: float):
        if len(self.price_history) < 2:
            return
        # Procura o ponto mais antigo dentro de 500ms
        cutoff = now - 0.5
        oldest = None
        for t, p in self.price_history:
            if t >= cutoff:
                oldest = (t, p)
                break
        if oldest is None:
            return
        _, old_price = oldest
        if old_price == 0:
            return
        pct_change = abs(price - old_price) / old_price * 100
        if pct_change >= PRICE_SHOCK_THRESHOLD_PCT:
            direction = "UP" if price > old_price else "DOWN"
            self._record_event(
                "PRICE_SHOCK",
                f"{direction} {pct_change:.3f}% em {(now - oldest[0]) * 1000:.0f}ms",
                now,
            )

    def _check_volume_spike(self, qty: float, now: float):
        if len(self.volume_history) < VOLUME_WINDOW:
            return
        vols = list(self.volume_history)
        mean_vol = statistics.mean(vols)
        stdev_vol = statistics.stdev(vols) if len(vols) > 1 else 0
        if stdev_vol == 0:
            return
        z_score = (qty - mean_vol) / stdev_vol
        if z_score >= VOLUME_SPIKE_SIGMA:
            self._record_event(
                "VOLUME_SPIKE",
                f"qty={qty:.4f} z={z_score:.1f} (mean={mean_vol:.4f})",
                now,
            )

    def _check_spread_widen(self, bid: float, ask: float, now: float):
        if bid <= 0 or ask <= 0:
            return
        mid = (bid + ask) / 2
        if mid == 0:
            return
        spread_bps = (ask - bid) / mid * 10000
        self.spread_history.append(spread_bps)
        if len(self.spread_history) < SPREAD_WINDOW:
            return
        spreads = list(self.spread_history)
        mean_sp = statistics.mean(spreads)
        stdev_sp = statistics.stdev(spreads) if len(spreads) > 1 else 0
        if stdev_sp == 0:
            return
        z_score = (spread_bps - mean_sp) / stdev_sp
        if z_score >= SPREAD_WIDEN_SIGMA:
            self._record_event(
                "SPREAD_WIDEN",
                f"spread={spread_bps:.1f}bps z={z_score:.1f} (mean={mean_sp:.1f}bps)",
                now,
            )

    def _check_momentum_burst(self, price: float, now: float):
        if self.last_price is not None and price != self.last_price:
            direction = 1 if price > self.last_price else -1
            self.tick_directions.append(direction)

            if len(self.tick_directions) >= MOMENTUM_BURST_MIN_TICKS:
                recent = list(self.tick_directions)[-MOMENTUM_BURST_MIN_TICKS:]
                if all(d == recent[0] for d in recent) and recent[0] != 0:
                    dir_str = "UP" if recent[0] > 0 else "DOWN"
                    self._record_event(
                        "MOMENTUM_BURST",
                        f"{dir_str} {MOMENTUM_BURST_MIN_TICKS}+ ticks consecutivos",
                        now,
                    )
                    self.tick_directions.clear()

    def _check_feed_stall(self, now: float):
        gap_ms = (now - self.last_update_time) * 1000
        if gap_ms > FEED_STALL_THRESHOLD_MS:
            self._record_event(
                "FEED_STALL",
                f"gap={gap_ms:.0f}ms (threshold={FEED_STALL_THRESHOLD_MS}ms)",
                now,
            )

    def on_book_ticker(self, data: dict):
        """Stream bookTicker: {u, s, b, B, a, A}"""
        now = time.time()
        self.total_ticks += 1

        bid = float(data.get("b", 0))
        ask = float(data.get("a", 0))
        bid_qty = float(data.get("B", 0))
        ask_qty = float(data.get("A", 0))

        self.last_bid = bid
        self.last_ask = ask
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else None
        if mid:
            self.last_price = mid
            self.price_history.append((now, mid))
            self._check_price_shock(mid, now)
            self._check_momentum_burst(mid, now)

        self._check_spread_widen(bid, ask, now)
        self._check_feed_stall(now)
        self.last_update_time = now

    def on_agg_trade(self, data: dict):
        """Stream aggTrade: {e, E, s, a, p, q, f, l, T, m}"""
        now = time.time()
        qty = float(data.get("q", 0))
        price = float(data.get("p", 0))

        if qty > 0:
            self.volume_history.append(qty)
            self._check_volume_spike(qty, now)

        if price > 0 and self.last_price is None:
            self.last_price = price
            self.price_history.append((now, price))

    def snapshot(self) -> dict:
        now = time.time()
        self._prune_old_events(now)
        klasses = self._klasses_of_interest()
        event_counts = {k: len(dq) for k, dq in self.events.items()}
        return {
            "symbol": self.symbol,
            "total_ticks": self.total_ticks,
            "total_events": self.total_events,
            "event_counts": event_counts,
            "klasses_of_interest": klasses,
            "gate_min": MIN_KLASS_EVENTS,
            "gate_window_s": JANELA_OBSERVACAO_S,
            "last_price": self.last_price,
            "last_bid": self.last_bid,
            "last_ask": self.last_ask,
            "timestamp": now,
        }


class AnomalyMonitorReal:
    """Orquestra multiplos MarketMonitor em paralelo via Binance WebSocket."""

    def __init__(self, symbols: list, duration_s: int = 0, report_interval_s: int = 3600):
        self.symbols = [s.upper() for s in symbols]
        self.monitors = {s: MarketMonitor(s) for s in self.symbols}
        self.duration_s = duration_s
        self.report_interval_s = report_interval_s
        self.start_time = time.time()
        self.job_id = f"JOB-{time.strftime('%Y-%m-%d')}-{os.getpid():03d}"

    async def _run_stream(self, symbol: str, stream: str, handler_name: str):
        uri = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@{stream}"
        monitor = self.monitors[symbol]
        handler = getattr(monitor, handler_name)

        while True:
            try:
                async with websockets.connect(uri, ping_interval=20) as ws:
                    logger.info(f"[{symbol}] Conectado em {stream}")
                    async for message in ws:
                        data = json.loads(message)
                        handler(data)
            except Exception as e:
                logger.error(f"[{symbol}] Erro no stream {stream}: {e}. Reconectando em 3s...")
                await asyncio.sleep(3)

    async def _periodic_report(self):
        """Relatorio periodico: snapshot de todos os monitores."""
        while True:
            await asyncio.sleep(self.report_interval_s)
            self._print_report()

    def _print_report(self):
        now = time.time()
        elapsed = now - self.start_time
        total_events_all = 0
        all_klasses = []

        logger.info(f"{'=' * 70}")
        logger.info(f"[INFO] Relatorio periodico | {self.job_id} | elapsed={elapsed:.0f}s")
        for sym, mon in self.monitors.items():
            snap = mon.snapshot()
            total_events_all += snap["total_events"]
            all_klasses.extend(snap["klasses_of_interest"])
            logger.info(
                f"  [{sym}] ticks={snap['total_ticks']} eventos={snap['total_events']} "
                f"counts={snap['event_counts']} klasses_interesse={snap['klasses_of_interest']}"
            )
        logger.info(f"  TOTAL: eventos={total_events_all} klasses_de_interesse={all_klasses}")
        if not all_klasses:
            logger.info(
                f"  Nenhum klass de interesse atingido (min={MIN_KLASS_EVENTS}). "
                f"Continuando monitoramento..."
            )
        logger.info(f"{'=' * 70}")

    async def run(self):
        logger.info(f"[START] {self.job_id} | symbols={self.symbols} | "
                     f"report_interval={self.report_interval_s}s | "
                     f"duration={'unlimited' if not self.duration_s else self.duration_s}s")

        tasks = []
        for sym in self.symbols:
            tasks.append(asyncio.create_task(
                self._run_stream(sym, "bookTicker", "on_book_ticker")
            ))
            tasks.append(asyncio.create_task(
                self._run_stream(sym, "aggTrade", "on_agg_trade")
            ))

        tasks.append(asyncio.create_task(self._periodic_report()))

        if self.duration_s > 0:
            await asyncio.sleep(self.duration_s)
            self._print_report()
            logger.info(f"[END] {self.job_id} finalizado apos {self.duration_s}s")
        else:
            await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description="Anomaly Monitor - Mercados Reais (Binance)")
    parser.add_argument(
        "--symbols", type=str, default="btcusdt,ethusdt",
        help="Simbolos separados por virgula (ex: btcusdt,ethusdt,solusdt)"
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Duracao em segundos (0 = ilimitado)"
    )
    parser.add_argument(
        "--interval", type=int, default=3600,
        help="Intervalo entre relatorios em segundos (default: 3600 = 1h)"
    )
    parser.add_argument(
        "--log-file", type=str, default="",
        help="Arquivo de log adicional (opcional)"
    )
    args = parser.parse_args()

    if args.log_file:
        fh = logging.FileHandler(args.log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(fh)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    monitor = AnomalyMonitorReal(
        symbols=symbols,
        duration_s=args.duration,
        report_interval_s=args.interval,
    )

    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        monitor._print_report()
        logger.info(f"[END] {monitor.job_id} interrompido por usuario")


if __name__ == "__main__":
    main()
