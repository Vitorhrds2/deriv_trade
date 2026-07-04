"""
D22 — CEX liquidation cascade scan.

Hipotese: clusters de liquidacoes em Binance Futures predizem reversoes
de curto prazo. Quando muitos longs sao liquidados simultaneamente,
o preco ja caiu muito rapido e tende a reverter (bounce).
Quando muitos shorts sao liquidados, tende a cair (pullback).

Mecanismo:
- Liquidation cascade: preco cai -> longs liquidados -> selling pressure -> mais queda -> mais liquidacoes
- Apos cascade exaustivo, preco tende a reverter (oversold)
- Simetrico para short squeeze

Data source (gratuito, publico, sem API key):
- Binance Futures WS: wss://fstream.binance.com/ws/!forceOrder@arr
  Stream publico de TODAS as liquidacoes em Binance Futures
- Binance Futures WS: wss://fstream.binance.com/ws/btcusdt@aggTrade
  Para preco em tempo real

Teste:
1. Coletar liquidacoes + preco por N minutos
2. Detectar clusters (janela de 60s com > X liquidacoes ou volume > Y)
3. Medir retorno do BTC 30s, 60s, 120s, 300s apos cluster
4. Veredito: clusters predizem reversao?
"""
import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict, deque
from datetime import datetime

try:
    import websockets
except ImportError:
    print("ERRO: websockets nao instalado. Run: pip3 install websockets")
    sys.exit(1)

try:
    from stats_utils import bootstrap_ci, wilson_ci
except ImportError:
    print("ERRO: stats_utils.py nao encontrado. Execute do diretorio trading-engine/")
    sys.exit(1)


class LiquidationScanner:
    def __init__(self, duration_min=15, cluster_window_s=60, cluster_count_min=5, cluster_volume_min=50000):
        self.duration_min = duration_min
        self.cluster_window_s = cluster_window_s
        self.cluster_count_min = cluster_count_min
        self.cluster_volume_min = cluster_volume_min

        self.liquidations = []  # all liquidation events
        self.trades = []  # BTC price ticks
        self.clusters = []  # detected clusters

        self.btc_prices = deque()  # (timestamp, price) for forward return calc

    async def listen_liquidations(self):
        """Listen to Binance Futures liquidation stream."""
        url = "wss://fstream.binance.com/ws/!forceOrder@arr"
        try:
            async with websockets.connect(url) as ws:
                print(f"  Liquidacoes WS conectado: {url}")
                start = time.time()
                while time.time() - start < self.duration_min * 60:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(msg)
                    o = data.get("o", {})
                    symbol = o.get("s", "")
                    side = o.get("S", "")  # BUY = short liquidation, SELL = long liquidation
                    price = float(o.get("ap", 0) or o.get("p", 0))
                    qty = float(o.get("q", 0))
                    notional = price * qty
                    ts = o.get("T", int(time.time() * 1000))

                    self.liquidations.append({
                        "ts": ts,
                        "symbol": symbol,
                        "side": side,
                        "price": price,
                        "qty": qty,
                        "notional": notional,
                        "time": datetime.utcfromtimestamp(ts / 1000).strftime("%H:%M:%S"),
                    })

                    # Print significant liquidations
                    if notional > 10000:
                        direction = "SHORT liq" if side == "BUY" else "LONG liq"
                        print(f"  [{datetime.utcfromtimestamp(ts/1000).strftime('%H:%M:%S')}] {symbol} {direction} ${notional:,.0f}")

        except Exception as e:
            print(f"  WS erro: {e}")

    async def listen_btc_price(self):
        """Listen to BTC aggTrade stream for real-time price."""
        url = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
        try:
            async with websockets.connect(url) as ws:
                start = time.time()
                while time.time() - start < self.duration_min * 60:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        price = float(data.get("p", 0))
                        ts = data.get("T", int(time.time() * 1000))
                        if price > 0:
                            self.btc_prices.append((ts, price))
                            # Keep only last 10 minutes of prices
                            cutoff = ts - 600000
                            while self.btc_prices and self.btc_prices[0][0] < cutoff:
                                self.btc_prices.popleft()
                    except asyncio.TimeoutError:
                        pass
        except Exception as e:
            print(f"  BTC price WS erro: {e}")

    async def run(self):
        """Run both listeners concurrently."""
        print(f"\n  Coletando dados por {self.duration_min} minutos...")
        print(f"  Cluster detection: janela={self.cluster_window_s}s, min_count={self.cluster_count_min}, min_volume=${self.cluster_volume_min:,.0f}")
        print()

        await asyncio.gather(
            self.listen_liquidations(),
            self.listen_btc_price(),
        )

    def detect_clusters(self):
        """Detect liquidation clusters in the collected data."""
        if not self.liquidations:
            return

        liqs = sorted(self.liquidations, key=lambda x: x["ts"])
        window_ms = self.cluster_window_s * 1000

        i = 0
        while i < len(liqs):
            window_start = liqs[i]["ts"]
            window_end = window_start + window_ms
            window_liqs = []
            j = i
            while j < len(liqs) and liqs[j]["ts"] < window_end:
                window_liqs.append(liqs[j])
                j += 1

            total_volume = sum(l["notional"] for l in window_liqs)
            long_liqs = [l for l in window_liqs if l["side"] == "SELL"]
            short_liqs = [l for l in window_liqs if l["side"] == "BUY"]

            if len(window_liqs) >= self.cluster_count_min or total_volume >= self.cluster_volume_min:
                # Find BTC price at cluster time
                cluster_ts = window_start
                btc_price_at_cluster = self._get_btc_price(cluster_ts)

                # Forward returns
                fwd_returns = {}
                for horizon_s in (30, 60, 120, 300):
                    fwd_price = self._get_btc_price(cluster_ts + horizon_s * 1000)
                    if btc_price_at_cluster and fwd_price:
                        fwd_returns[f"{horizon_s}s"] = (fwd_price - btc_price_at_cluster) / btc_price_at_cluster * 100
                    else:
                        fwd_returns[f"{horizon_s}s"] = None

                cluster = {
                    "ts": cluster_ts,
                    "time": datetime.utcfromtimestamp(cluster_ts / 1000).strftime("%H:%M:%S"),
                    "n_liquidations": len(window_liqs),
                    "total_volume": total_volume,
                    "long_liqs": len(long_liqs),
                    "short_liqs": len(short_liqs),
                    "dominant": "LONG_LIQ" if len(long_liqs) > len(short_liqs) else "SHORT_LIQ",
                    "btc_price": btc_price_at_cluster,
                    "fwd_returns": fwd_returns,
                }
                self.clusters.append(cluster)

            i = j if j > i else i + 1

    def _get_btc_price(self, ts_ms):
        """Get BTC price closest to timestamp."""
        if not self.btc_prices:
            return None
        closest = None
        min_diff = float("inf")
        for pts, price in self.btc_prices:
            diff = abs(pts - ts_ms)
            if diff < min_diff:
                min_diff = diff
                closest = price
        # Only return if within 10 seconds
        if min_diff < 10000:
            return closest
        return None

    def analyze(self):
        """Analyze results and print verdict."""
        print("\n" + "=" * 100)
        print("ANALISE")
        print("=" * 100)

        total_liqs = len(self.liquidations)
        total_volume = sum(l["notional"] for l in self.liquidations)
        long_liqs = [l for l in self.liquidations if l["side"] == "SELL"]
        short_liqs = [l for l in self.liquidations if l["side"] == "BUY"]

        print(f"\nTotal liquidacoes: {total_liqs} | Volume total: ${total_volume:,.0f}")
        print(f"  LONG liquidations: {len(long_liqs)} (${sum(l['notional'] for l in long_liqs):,.0f})")
        print(f"  SHORT liquidations: {len(short_liqs)} (${sum(l['notional'] for l in short_liqs):,.0f})")

        # Top symbols
        symbol_stats = defaultdict(lambda: {"count": 0, "volume": 0})
        for l in self.liquidations:
            symbol_stats[l["symbol"]]["count"] += 1
            symbol_stats[l["symbol"]]["volume"] += l["notional"]

        print(f"\nTop 10 symbols por volume:")
        for sym, stats in sorted(symbol_stats.items(), key=lambda x: -x[1]["volume"])[:10]:
            print(f"  {sym:<16} N={stats['count']:<6} Vol=${stats['volume']:,.0f}")

        # Cluster analysis
        print(f"\nClusters detectados: {len(self.clusters)}")
        if not self.clusters:
            print("  Nenhum cluster atingiu o threshold minimo.")
            print("  (Isso pode indicar mercado calmo durante o periodo de coleta)")
            return

        print(f"\n{'Time':<12} {'Type':<12} {'N':<6} {'Volume':<14} {'BTC':<12} {'30s':<8} {'60s':<8} {'120s':<8} {'300s':<8}")
        print("-" * 100)
        for c in self.clusters:
            fwd = c["fwd_returns"]
            print(f"  {c['time']:<10} {c['dominant']:<12} {c['n_liquidations']:<6} ${c['total_volume']:<13,.0f} {c['btc_price'] or 0:<12.2f} "
                  f"{fwd.get('30s', 0) or 0:<8.3f} {fwd.get('60s', 0) or 0:<8.3f} {fwd.get('120s', 0) or 0:<8.3f} {fwd.get('300s', 0) or 0:<8.3f}")

        # Forward return analysis by cluster type
        print("\n" + "=" * 80)
        print("FORWARD RETURNS POR TIPO DE CLUSTER")
        print("=" * 80)

        for cluster_type in ["LONG_LIQ", "SHORT_LIQ"]:
            type_clusters = [c for c in self.clusters if c["dominant"] == cluster_type]
            if not type_clusters:
                continue

            direction = "LONG (bounce)" if cluster_type == "LONG_LIQ" else "SHORT (pullback)"
            print(f"\n  {cluster_type} -> signal: {direction} | N={len(type_clusters)}")

            for horizon in ["30s", "60s", "120s", "300s"]:
                returns = [c["fwd_returns"].get(horizon) for c in type_clusters if c["fwd_returns"].get(horizon) is not None]
                if len(returns) < 3:
                    print(f"    {horizon}: N insuficiente ({len(returns)})")
                    continue

                lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
                wins = sum(1 for r in returns if r > 0)
                wr = wins / len(returns) if returns else 0
                wr_lo, wr_hi = wilson_ci(wins, len(returns))
                print(f"    {horizon}: N={len(returns)} | Retorno medio={avg:.4f}% IC95%[{lo:.4f}%, {hi:.4f}%] | WR={wr*100:.1f}% IC95%[{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]")

        # Save
        output = {
            "duration_min": self.duration_min,
            "total_liquidations": total_liqs,
            "total_volume": total_volume,
            "long_liqs": len(long_liqs),
            "short_liqs": len(short_liqs),
            "clusters": self.clusters,
            "top_symbols": dict(sorted(symbol_stats.items(), key=lambda x: -x[1]["volume"])[:10]),
        }
        with open("cex_liquidation_samples.json", "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\nAmostras salvas em cex_liquidation_samples.json")

        # Verdict
        print("\n" + "=" * 100)
        print("VEREDITO PRELIMINAR")
        print("=" * 100)

        if len(self.clusters) < 3:
            print(f"  DADOS INSUFICIENTES: apenas {len(self.clusters)} clusters em {self.duration_min}min")
            print("  Necessario periodo mais longo ou mercado mais volatil para concluir.")
        else:
            # Check if LONG_LIQ clusters have positive forward returns (bounce)
            long_clusters = [c for c in self.clusters if c["dominant"] == "LONG_LIQ"]
            short_clusters = [c for c in self.clusters if c["dominant"] == "SHORT_LIQ"]

            edge_found = False
            if long_clusters:
                for h in ["60s", "120s", "300s"]:
                    returns = [c["fwd_returns"].get(h) for c in long_clusters if c["fwd_returns"].get(h) is not None]
                    if len(returns) >= 3:
                        lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
                        if lo > 0:
                            print(f"  LONG_LIQ -> bounce em {h}: +{avg:.4f}% IC95%[{lo:.4f}%, {hi:.4f}%]")
                            edge_found = True

            if short_clusters:
                for h in ["60s", "120s", "300s"]:
                    returns = [c["fwd_returns"].get(h) for c in short_clusters if c["fwd_returns"].get(h) is not None]
                    if len(returns) >= 3:
                        lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
                        if hi < 0:
                            print(f"  SHORT_LIQ -> pullback em {h}: {avg:.4f}% IC95%[{lo:.4f}%, {hi:.4f}%]")
                            edge_found = True

            if not edge_found:
                print("  SEM EDGE: clusters de liquidacao nao predizem reversao com significancia estatistica")
                print(f"  ({len(self.clusters)} clusters, {self.duration_min}min de coleta)")
                print("  Para validacao: coletar por varias horas, filtrar por volume,")
                print("  e testar em diferentes condicoes de mercado (trending vs ranging).")


def main():
    parser = argparse.ArgumentParser(description="D22 — CEX liquidation cascade scan")
    parser.add_argument("--duration-min", type=int, default=15, help="Collection duration in minutes")
    parser.add_argument("--cluster-window-s", type=int, default=60, help="Cluster detection window in seconds")
    parser.add_argument("--cluster-count-min", type=int, default=5, help="Min liquidations per cluster")
    parser.add_argument("--cluster-volume-min", type=float, default=50000, help="Min cluster volume in USD")
    args = parser.parse_args()

    print("=" * 100)
    print(f"D22 — CEX Liquidation Cascade Scan | {args.duration_min}min | cluster={args.cluster_window_s}s/{args.cluster_count_min}liqs/${args.cluster_volume_min:,.0f}")
    print("=" * 100)

    scanner = LiquidationScanner(
        duration_min=args.duration_min,
        cluster_window_s=args.cluster_window_s,
        cluster_count_min=args.cluster_count_min,
        cluster_volume_min=args.cluster_volume_min,
    )

    asyncio.run(scanner.run())

    print(f"\nColeta finalizada: {len(scanner.liquidations)} liquidacoes, {len(scanner.btc_prices)} price ticks")

    scanner.detect_clusters()
    scanner.analyze()


if __name__ == "__main__":
    main()
