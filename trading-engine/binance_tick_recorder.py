"""binance_tick_recorder.py — gravador de ticks REAIS da Binance (live WebSocket) para
coleta de longo prazo (ex.: 24h co-locado em AWS ap-northeast-1, mesma regiao da Binance).

Usa APENAS streams PUBLICOS (@aggTrade) -> nao precisa de API key/segredo na VM.

Para cada trade agregado grava uma linha CSV (1 arquivo por simbolo, rotacao HORARIA):
    recv_ns,event_ms,trade_ms,agg_id,price,qty,first_id,last_id,is_buyer_maker
  - recv_ns  : time.time_ns() local no momento da recepcao. NAO existe nos dumps
               historicos da Binance -> habilita estudo de skew/latencia (era exatamente
               o gargalo medido no teste H3: sinal ~2.6ms co-locado).
  - event_ms : campo E (event time do servidor).
  - trade_ms : campo T (trade time).

Com --book, tambem grava best bid/ask (stream @bookTicker) por simbolo em
arquivo separado (<symbol>-bookticker-YYYYMMDD-HH.csv):
    recv_ns,update_id,best_bid,best_bid_qty,best_ask,best_ask_qty
  Sem event_ms/trade_ms aqui - a Binance nao envia event time nesse stream.

Robustez p/ rodar dias sem supervisao:
  - auto-reconnect com backoff exponencial (1s -> 60s), resetado a cada mensagem boa;
  - ping de cliente (ping_interval) p/ derrubar conexao morta (half-open) rapido;
  - flush periodico (crash-safe: CSV em texto puro, nao gzip a meio caminho);
  - rotacao horaria de arquivo (arquivos fechados podem ser comprimidos/baixados ao vivo);
  - --max-runtime (default 24h) e encerramento limpo em SIGINT/SIGTERM (flush + close);
  - stats periodicas (ticks totais, por simbolo, reconexoes, arquivo atual).

Dep: websockets (pip install websockets). Python 3.8+.
"""
import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    sys.exit("Falta a lib 'websockets': pip install websockets")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WS_BASE = "wss://stream.binance.com:9443/stream?streams="
CSV_HEADER = "recv_ns,event_ms,trade_ms,agg_id,price,qty,first_id,last_id,is_buyer_maker\n"
# bookTicker (best bid/ask) - opcional, via --book. Payload da Binance NAO tem
# event time ("E") para este stream, so update_id ("u") - por isso so recv_ns.
BOOK_HEADER = "recv_ns,update_id,best_bid,best_bid_qty,best_ask,best_ask_qty\n"


class HourlyWriter:
    """Um arquivo CSV por simbolo/tipo, rotacionado quando muda a hora UTC."""

    def __init__(self, outdir, symbol, kind="aggtrade", header=CSV_HEADER):
        self.outdir = outdir
        self.symbol = symbol.lower()
        self.kind = kind
        self.header = header
        self.cur_hour = None
        self.fh = None
        self.path = None
        self.rows = 0

    def _hour_key(self, ts):
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d-%H")

    def _rotate(self, hour_key):
        if self.fh:
            try:
                self.fh.flush()
                self.fh.close()
            except Exception:
                pass
            print(f"  [rotate] {self.symbol}/{self.kind}: fechado {os.path.basename(self.path)} "
                  f"({self.rows} linhas)", flush=True)
        os.makedirs(self.outdir, exist_ok=True)
        self.path = os.path.join(self.outdir, f"{self.symbol}-{self.kind}-{hour_key}.csv")
        new_file = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
        self.fh = open(self.path, "a", encoding="utf-8", buffering=1 << 16)
        if new_file:
            self.fh.write(self.header)
        self.cur_hour = hour_key
        self.rows = 0

    def write(self, recv_ns, d):
        hk = self._hour_key(recv_ns / 1e9)
        if hk != self.cur_hour:
            self._rotate(hk)
        self.fh.write(
            f"{recv_ns},{d.get('E','')},{d.get('T','')},{d.get('a','')},"
            f"{d.get('p','')},{d.get('q','')},{d.get('f','')},{d.get('l','')},"
            f"{1 if d.get('m') else 0}\n"
        )
        self.rows += 1

    def write_book(self, recv_ns, d):
        hk = self._hour_key(recv_ns / 1e9)
        if hk != self.cur_hour:
            self._rotate(hk)
        self.fh.write(
            f"{recv_ns},{d.get('u','')},{d.get('b','')},{d.get('B','')},"
            f"{d.get('a','')},{d.get('A','')}\n"
        )
        self.rows += 1

    def flush(self):
        if self.fh:
            try:
                self.fh.flush()
                os.fsync(self.fh.fileno())
            except Exception:
                pass

    def close(self):
        if self.fh:
            try:
                self.fh.flush()
                self.fh.close()
            except Exception:
                pass
            self.fh = None


class Recorder:
    def __init__(self, symbols, outdir, max_runtime, flush_s, stats_s, book=False):
        self.symbols = [s.strip().lower() for s in symbols if s.strip()]
        self.outdir = outdir
        self.max_runtime = max_runtime
        self.flush_s = flush_s
        self.stats_s = stats_s
        self.book = book
        self.writers = {s: HourlyWriter(outdir, s, "aggtrade", CSV_HEADER) for s in self.symbols}
        self.counts = {s: 0 for s in self.symbols}
        self.book_writers = {s: HourlyWriter(outdir, s, "bookticker", BOOK_HEADER) for s in self.symbols} if book else {}
        self.book_counts = {s: 0 for s in self.symbols}
        self.total = 0
        self.reconnects = 0
        self.start = time.time()
        self._stop = asyncio.Event()

    def stop(self, *_):
        self._stop.set()

    def _url(self):
        streams = [f"{s}@aggTrade" for s in self.symbols]
        if self.book:
            streams += [f"{s}@bookTicker" for s in self.symbols]
        return WS_BASE + "/".join(streams)

    async def _flush_loop(self):
        while not self._stop.is_set():
            await asyncio.sleep(self.flush_s)
            for w in self.writers.values():
                w.flush()
            for w in self.book_writers.values():
                w.flush()

    async def _stats_loop(self):
        while not self._stop.is_set():
            await asyncio.sleep(self.stats_s)
            el = time.time() - self.start
            rate = self.total / el if el > 0 else 0
            per = " ".join(f"{s.upper()}={self.counts[s]:,}" for s in self.symbols)
            extra = ""
            if self.book:
                extra = " | book: " + " ".join(f"{s.upper()}={self.book_counts[s]:,}" for s in self.symbols)
            print(f"  [stats] t={el/3600:.2f}h ticks={self.total:,} ({rate:.1f}/s) "
                  f"reconex={self.reconnects} | {per}{extra}", flush=True)

    async def _runtime_guard(self):
        if self.max_runtime <= 0:
            return
        while not self._stop.is_set():
            if time.time() - self.start >= self.max_runtime:
                print(f"  [runtime] {self.max_runtime/3600:.1f}h atingidas; encerrando.", flush=True)
                self._stop.set()
                return
            await asyncio.sleep(5)

    async def _consume(self):
        backoff = 1.0
        url = self._url()
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=20,
                    max_queue=None, close_timeout=5,
                ) as ws:
                    kinds = "@aggTrade+@bookTicker" if self.book else "@aggTrade"
                    print(f"  [ws] conectado: {len(self.symbols)} simbolo(s) {kinds}", flush=True)
                    backoff = 1.0
                    while not self._stop.is_set():
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        recv_ns = time.time_ns()
                        msg = json.loads(raw)
                        d = msg.get("data") or msg
                        sym = (d.get("s") or "").lower()
                        if d.get("e") == "aggTrade":
                            w = self.writers.get(sym)
                            if w is None:
                                continue
                            w.write(recv_ns, d)
                            self.counts[sym] += 1
                            self.total += 1
                        elif self.book and "b" in d and "a" in d and "u" in d:
                            # bookTicker: sem campo "e" no payload da Binance
                            bw = self.book_writers.get(sym)
                            if bw is None:
                                continue
                            bw.write_book(recv_ns, d)
                            self.book_counts[sym] += 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if self._stop.is_set():
                    break
                self.reconnects += 1
                print(f"  [ws] caiu ({type(e).__name__}: {e}); reconectando em {backoff:.0f}s "
                      f"(reconex={self.reconnects})", flush=True)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 60.0)

    async def run(self):
        os.makedirs(self.outdir, exist_ok=True)
        print(f">>> binance_tick_recorder | simbolos={','.join(s.upper() for s in self.symbols)} "
              f"| outdir={self.outdir} | max_runtime={self.max_runtime/3600:.1f}h", flush=True)
        tasks = [
            asyncio.create_task(self._consume()),
            asyncio.create_task(self._flush_loop()),
            asyncio.create_task(self._stats_loop()),
            asyncio.create_task(self._runtime_guard()),
        ]
        await self._stop.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for w in self.writers.values():
            w.close()
        for w in self.book_writers.values():
            w.close()
        el = time.time() - self.start
        print(f">>> ENCERRADO | {el/3600:.2f}h | ticks={self.total:,} | reconex={self.reconnects}",
              flush=True)


def main():
    ap = argparse.ArgumentParser(description="Gravador de ticks reais da Binance (live WS)")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    ap.add_argument("--outdir", default=os.path.join("data", "binance_ticks"))
    ap.add_argument("--book", action="store_true",
                    help="tambem grava bookTicker (bid/ask), alem de aggTrade")
    ap.add_argument("--max-runtime", type=float, default=86400.0, dest="max_runtime",
                    help="segundos (default 86400 = 24h; 0 = sem limite)")
    ap.add_argument("--flush-s", type=float, default=2.0, dest="flush_s")
    ap.add_argument("--stats-s", type=float, default=60.0, dest="stats_s")
    args = ap.parse_args()

    rec = Recorder([s for s in args.symbols.split(",")], args.outdir,
                   args.max_runtime, args.flush_s, args.stats_s, book=args.book)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, rec.stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, rec.stop)  # Windows
    try:
        loop.run_until_complete(rec.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
