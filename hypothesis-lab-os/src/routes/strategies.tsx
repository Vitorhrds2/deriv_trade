import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Mono, Stat, Dot } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { getHftStatus, getHftTrades, isHftLive } from "@/lib/hft-api";
import { getUnlockStatus, getUnlockStats } from "@/lib/unlock-api";
import { fmtMoney } from "@/lib/mock-data";
import { CircuitBoard, Cpu, Radio, Unlock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

export const Route = createFileRoute("/strategies")({
  head: () => ({ meta: [{ title: "Live Strategies — TradeLab OS" }] }),
  component: StrategiesPage,
});

function StrategiesPage() {
  const hftStatusQuery = useQuery({
    queryKey: ["hft-status"],
    queryFn: () => getHftStatus(),
    refetchInterval: 5000,
  });
  const hftTradesQuery = useQuery({
    queryKey: ["hft-trades"],
    queryFn: () => getHftTrades(),
    refetchInterval: 5000,
  });
  const unlockStatusQuery = useQuery({
    queryKey: ["unlock-status"],
    queryFn: () => getUnlockStatus(),
    refetchInterval: 10000,
  });
  const unlockStatsQuery = useQuery({
    queryKey: ["unlock-stats"],
    queryFn: () => getUnlockStats(),
    refetchInterval: 15000,
  });

  const hftStatus = hftStatusQuery.data;
  const hftTrades = hftTradesQuery.data;
  const unlockStatus = unlockStatusQuery.data;
  const unlockStats = unlockStatsQuery.data;

  const hftLive = hftStatus ? isHftLive(hftStatus) : false;
  const unlockConnected = unlockStatus?.connected ?? false;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="research › live strategies"
        title="Live Strategies"
        description="Bots em execução real no ecossistema — status ao vivo via APIs na AWS EC2."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat
          label="Bots ativos"
          value={(hftLive ? 1 : 0) + (unlockConnected ? 1 : 0)}
          hint="de 2 deployados"
        />
        <Stat
          label="hft_bot trades"
          value={hftTrades?.total.n ?? "—"}
          hint="conta demo Deriv"
        />
        <Stat
          label="unlock_bot trades"
          value={unlockStats?.total_trades ?? "—"}
          hint="paper trading"
        />
        <Stat
          label="PnL agregado"
          value={fmtMoney(
            (hftTrades?.total.pnlTotal ?? 0) + (unlockStatus?.total_pnl ?? 0)
          )}
          tone={
            (hftTrades?.total.pnlTotal ?? 0) + (unlockStatus?.total_pnl ?? 0) < 0
              ? "neg"
              : "pos"
          }
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* hft_bot card */}
        <Panel
          className="col-span-12 xl:col-span-6"
          title={
            <span className="flex items-center gap-2">
              <Radio className="h-4 w-4" />
              hft_bot
            </span>
          }
          subtitle="HYP-HFT-01 · cryBTCUSD Multiplier x800 · Deriv demo"
          actions={
            <Dot tone={hftLive ? "pos" : "muted"} className={hftLive ? "animate-pulse" : ""} />
          }
        >
          <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">
                {hftLive ? "ao vivo" : "offline"}
              </span>
              <Badge
                variant="outline"
                className={`text-[10px] uppercase ${
                  hftLive
                    ? "border-success/40 text-success bg-success/10"
                    : "border-destructive/40 text-destructive bg-destructive/10"
                }`}
              >
                {hftLive ? "running" : "stopped"}
              </Badge>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Trades
                </Mono>
                <div className="mt-1 font-mono text-sm">
                  {hftTrades?.total.n ?? "—"}
                </div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Win Rate
                </Mono>
                <div className="mt-1 font-mono text-sm">
                  {hftTrades ? `${Math.round(hftTrades.total.winRate * 100)}%` : "—"}
                </div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  PnL
                </Mono>
                <div
                  className={`mt-1 font-mono text-sm ${
                    (hftTrades?.total.pnlTotal ?? 0) < 0
                      ? "text-neg"
                      : "text-pos"
                  }`}
                >
                  {hftTrades ? fmtMoney(hftTrades.total.pnlTotal) : "—"}
                </div>
              </div>
            </div>

            <div className="rounded border p-3 space-y-2">
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                Config (V6.2)
              </Mono>
              <div className="text-xs font-mono space-y-1 text-muted-foreground">
                <div>STAKE=$10.0 · MULTIPLIER=800 · THRESHOLD=45.00</div>
                <div>TP=0.80% · SL=0.25% · WINDOW=50ms</div>
                <div>GOLDEN_HOUR: 12-18 UTC · SAFETY_TIMEOUT: 30min</div>
              </div>
            </div>

            <div className="rounded border p-3 space-y-2">
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                Script
              </Mono>
              <div className="text-xs font-mono text-foreground/80">
                hft_arbitrage_bot.py
              </div>
              <div className="text-[10px] text-muted-foreground">
                Deploy: EC2 us-east-1 · tmux session "hft_bot" · auto-restart on WS death
              </div>
            </div>

            <div className="text-xs text-muted-foreground">
              <CircuitBoard className="h-3 w-3 inline mr-1" />
              Veredito: EV/trade IC95% [-$4.70, -$1.18] — provisoriamente refutado, shadow A/B ativo
            </div>
          </div>
        </Panel>

        {/* unlock_bot card */}
        <Panel
          className="col-span-12 xl:col-span-6"
          title={
            <span className="flex items-center gap-2">
              <Unlock className="h-4 w-4" />
              unlock_short_bot
            </span>
          }
          subtitle="HYP-UNLOCK-01 · Binance spot · 10 tokens · paper trading"
          actions={
            <Dot
              tone={unlockConnected ? "pos" : "muted"}
              className={unlockConnected ? "animate-pulse" : ""}
            />
          }
        >
          <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">
                {unlockConnected ? "conectado" : "offline"}
              </span>
              <Badge
                variant="outline"
                className={`text-[10px] uppercase ${
                  unlockConnected
                    ? "border-success/40 text-success bg-success/10"
                    : "border-destructive/40 text-destructive bg-destructive/10"
                }`}
              >
                {unlockStatus?.mode ?? "—"}
              </Badge>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Posições abertas
                </Mono>
                <div className="mt-1 font-mono text-sm">
                  {unlockStatus?.open_count ?? "—"}
                </div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Trades fechados
                </Mono>
                <div className="mt-1 font-mono text-sm">
                  {unlockStatus?.closed_count ?? unlockStats?.total_trades ?? "—"}
                </div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Win Rate
                </Mono>
                <div className="mt-1 font-mono text-sm">
                  {unlockStatus ? `${Math.round(unlockStatus.win_rate * 100)}%` : "—"}
                </div>
              </div>
            </div>

            <div className="rounded border p-3 space-y-2">
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                Config (D17)
              </Mono>
              <div className="text-xs font-mono space-y-1 text-muted-foreground">
                <div>Entry: -3d · Exit: +3d · Fees: 20bps + real funding</div>
                <div>Min unlock: $50M · Max concurrent: 5</div>
                <div>Stop loss: 15% · Kelly fraction: 0.25</div>
              </div>
            </div>

            <div className="rounded border p-3 space-y-2">
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                Edge validado (3 períodos)
              </Mono>
              <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                <div>
                  <span className="text-muted-foreground">IS: </span>
                  <span className="text-pos">WR 61% · +285bps</span>
                </div>
                <div>
                  <span className="text-muted-foreground">OOS-25: </span>
                  <span className="text-pos">WR 79% · +656bps</span>
                </div>
                <div>
                  <span className="text-muted-foreground">OOS-26: </span>
                  <span className="text-pos">WR 67% · +384bps</span>
                </div>
              </div>
            </div>

            {unlockStatus && unlockStatus.open_count > 0 && (
              <div className="rounded border p-3 space-y-2">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Posições abertas agora
                </Mono>
                <div className="space-y-1.5">
                  {unlockStatus.open_positions.map((p, i) => (
                    <div key={i} className="flex justify-between text-xs font-mono">
                      <span className="text-foreground">{p.symbol}</span>
                      <Badge
                        variant="outline"
                        className="text-[10px] uppercase border-destructive/40 text-destructive bg-destructive/10"
                      >
                        {p.side}
                      </Badge>
                      <span className="text-muted-foreground">
                        {fmtMoney(p.notional)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="text-xs text-muted-foreground">
              <Cpu className="h-3 w-3 inline mr-1" />
              Deploy: EC2 us-east-1 · tmux session "unlock_bot" · paper trading mode
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
