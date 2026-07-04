import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Dot, Mono } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Unlock,
  TrendingDown,
  Clock,
  DollarSign,
  Target,
  Zap,
  ArrowLeft,
  Activity,
  Trophy,
  Shield,
  RefreshCw,
} from "lucide-react";
import {
  getUnlockStatus,
  getUnlockTrades,
  getUnlockSchedule,
  getUnlockStats,
} from "@/lib/unlock-api";
import { fmtMoney } from "@/lib/mock-data";
import {
  TIMING_RESULTS,
  FUNDING_COST,
  LARGE_UNLOCKS,
} from "@/lib/unlock-data";

export const Route = createFileRoute("/d17")({
  head: () => ({
    meta: [
      { title: "D17 Token Unlock Short — TradeLab OS" },
      { name: "description", content: "Dashboard do D17: edge validado em 3 períodos, timing otimizado, bot implementado." },
    ],
  }),
  component: D17Dashboard,
});

const chartTooltip = {
  contentStyle: {
    background: "oklch(0.20 0.014 240)",
    border: "1px solid oklch(0.28 0.014 240)",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "JetBrains Mono, monospace",
  },
  labelStyle: { color: "oklch(0.62 0.018 240)" },
};

function D17Dashboard() {
  const statusQuery = useQuery({
    queryKey: ["unlock-status"],
    queryFn: () => getUnlockStatus(),
    refetchInterval: 5000,
  });
  const tradesQuery = useQuery({
    queryKey: ["unlock-trades"],
    queryFn: () => getUnlockTrades(),
    refetchInterval: 10000,
  });
  const scheduleQuery = useQuery({
    queryKey: ["unlock-schedule"],
    queryFn: () => getUnlockSchedule(),
    refetchInterval: 30000,
  });
  const statsQuery = useQuery({
    queryKey: ["unlock-stats"],
    queryFn: () => getUnlockStats(),
    refetchInterval: 10000,
  });

  const status = statusQuery.data;
  const tradesData = tradesQuery.data;
  const scheduleData = scheduleQuery.data;
  const statsData = statsQuery.data;

  const connected = status?.connected ?? false;
  const botRunning = status?.tmux_session_alive ?? false;
  const openPositions = status?.open_positions ?? [];
  const closedCount = status?.closed_count ?? 0;
  const totalPnl = status?.total_pnl ?? 0;
  const winRate = status?.win_rate ?? 0;
  const equityCurve = tradesData?.equity_curve ?? [{ trade: 0, equity: 10000 }];
  const finalEquity = tradesData?.final_equity ?? 10000;
  const totalReturn = tradesData?.total_return_pct ?? 0;
  const upcoming = scheduleData?.upcoming ?? [];
  const periodStats = statsData?.period_stats;
  const perSymbol = statsData?.per_symbol ?? [];
  const allTrades = tradesData?.trades ?? [];
  const config = status?.config;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="research › event-driven › D17"
        title={
          <span className="flex items-center gap-3">
            <Unlock className="h-7 w-7 text-primary" />
            Token Unlock Short
          </span>
        }
        description="Short 3d antes do unlock, exit 3d depois. Paper trading ao vivo na AWS. Edge validado em 3 períodos (IS/OOS-25/OOS-26)."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                statusQuery.refetch();
                tradesQuery.refetch();
                scheduleQuery.refetch();
                statsQuery.refetch();
              }}
            >
              <RefreshCw className={`h-4 w-4 ${statusQuery.isFetching ? "animate-spin" : ""}`} />
              Atualizar
            </Button>
            <Link to="/hypotheses">
              <Button variant="outline" size="sm" className="gap-1.5">
                <ArrowLeft className="h-4 w-4" />
                Hipóteses
              </Button>
            </Link>
          </div>
        }
      />

      {/* ─── Connection status banner ─────────────────────────────────── */}
      <div className="mb-6 flex items-center gap-3 rounded-lg border px-4 py-3">
        <Dot tone={connected ? "pos" : "neg"} className={connected ? "animate-pulse" : ""} />
        <span className="text-sm font-medium">
          {!connected
            ? "API desconectada — bot não acessível na AWS"
            : !botRunning
              ? "API conectada — bot não está rodando (tmux inativo)"
              : "Paper trading ativo — bot rodando na AWS"}
        </span>
        {status?.last_check && (
          <span className="text-xs text-muted-foreground ml-auto">
            Última verificação: {new Date(status.last_check).toLocaleString("pt-BR")}
          </span>
        )}
        {status?.error && (
          <span className="text-xs text-destructive ml-auto">{status.error}</span>
        )}
      </div>

      {/* ─── Top stats ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
        <Stat
          label="Posições abertas"
          value={openPositions.length}
          tone={openPositions.length > 0 ? "pos" : "neutral"}
          hint={`max ${config?.max_concurrent ?? 5}`}
        />
        <Stat
          label="Trades fechados"
          value={closedCount}
          hint="paper trading"
        />
        <Stat
          label="Win rate"
          value={closedCount > 0 ? `${winRate}%` : "—"}
          tone={winRate >= 50 ? "pos" : "neutral"}
          hint={closedCount > 0 ? `${closedCount} trades` : "sem trades ainda"}
        />
        <Stat
          label="PnL total"
          value={closedCount > 0 ? fmtMoney(totalPnl) : "—"}
          tone={totalPnl > 0 ? "pos" : totalPnl < 0 ? "neg" : "neutral"}
          hint="paper"
        />
        <Stat
          label="Equity"
          value={fmtMoney(finalEquity)}
          hint={`start $${(tradesData?.starting_equity ?? 10000).toLocaleString()}`}
        />
        <Stat
          label="Retorno"
          value={closedCount > 0 ? `${totalReturn > 0 ? "+" : ""}${totalReturn}%` : "—"}
          tone={totalReturn > 0 ? "pos" : "neutral"}
          hint="acumulado"
        />
      </div>

      {/* ─── Equity curve + period comparison ──────────────────────────── */}
      <div className="grid grid-cols-12 gap-4 mb-6">
        <Panel
          className="col-span-12 lg:col-span-8"
          title={
            <span className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Equity Curve — Paper Trading
            </span>
          }
          subtitle={`${allTrades.length} trades · ${config?.fee_bps ?? 20}bps fees · half-Kelly sizing`}
        >
          <div className="p-4 h-[300px]">
            {equityCurve.length <= 1 ? (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                Sem trades ainda. O bot abre posições 3 dias antes de cada unlock.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityCurve}>
                  <defs>
                    <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.72 0.17 152)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.72 0.17 152)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.28 0.014 240)" />
                  <XAxis
                    dataKey="trade"
                    tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 11, fontFamily: "JetBrains Mono" }}
                    label={{ value: "Trade #", position: "insideBottom", offset: -5, style: { fill: "oklch(0.62 0.018 240)", fontSize: 11 } }}
                  />
                  <YAxis
                    tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 11, fontFamily: "JetBrains Mono" }}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip {...chartTooltip} formatter={(v: number) => [`$${v.toLocaleString()}`, "Equity"]} />
                  <ReferenceLine y={tradesData?.starting_equity ?? 10000} stroke="oklch(0.62 0.018 240)" strokeDasharray="4 4" label={{ value: "Start", fill: "oklch(0.62 0.018 240)", fontSize: 10 }} />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="oklch(0.72 0.17 152)"
                    strokeWidth={2}
                    fill="url(#equityGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>

        <Panel
          className="col-span-12 lg:col-span-4"
          title={
            <span className="flex items-center gap-2">
              <Target className="h-4 w-4" />
              Performance por período
            </span>
          }
          subtitle="Paper trading ao vivo"
        >
          <div className="p-4 space-y-4">
            {periodStats ? (
              [
                { label: "ALL", data: periodStats.all },
                { label: "IS (2023-2024)", data: periodStats.is },
                { label: "OOS-2025", data: periodStats.oos25 },
                { label: "OOS-2026", data: periodStats.oos26 },
              ].map(({ label, data: p }) => (
                <div key={label} className="rounded-lg border p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{label}</span>
                    <Badge variant="outline" className="font-mono text-xs">
                      N={p.n}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-muted-foreground uppercase tracking-wider text-[10px]">WR</div>
                      <div className={`font-mono text-sm ${p.wr >= 50 ? "text-success" : "text-foreground"}`}>
                        {p.n > 0 ? `${p.wr}%` : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground uppercase tracking-wider text-[10px]">Avg $</div>
                      <div className={`font-mono text-sm ${p.avg_pnl > 0 ? "text-success" : p.avg_pnl < 0 ? "text-destructive" : "text-muted-foreground"}`}>
                        {p.n > 0 ? fmtMoney(p.avg_pnl) : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground uppercase tracking-wider text-[10px]">t-stat</div>
                      <div className={`font-mono text-sm ${p.t_stat > 2 ? "text-success" : p.t_stat > 0 ? "text-warning" : "text-muted-foreground"}`}>
                        {p.n > 1 ? p.t_stat.toFixed(2) : "—"}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-muted-foreground">Carregando…</div>
            )}
          </div>
        </Panel>
      </div>

      {/* ─── Open positions + timing optimization ──────────────────────── */}
      <div className="grid grid-cols-12 gap-4 mb-6">
        <Panel
          className="col-span-12 xl:col-span-5"
          title={
            <span className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Posições abertas
            </span>
          }
          subtitle={`${openPositions.length}/${config?.max_concurrent ?? 5} posições · paper mode`}
        >
          <div className="p-4">
            {openPositions.length === 0 ? (
              <div className="text-center py-8 text-sm text-muted-foreground">
                Nenhuma posição aberta no momento.
                <br />
                O bot abre shorts 3 dias antes de cada unlock.
              </div>
            ) : (
              <div className="space-y-3">
                {openPositions.map((pos, i) => (
                  <div key={i} className="rounded-lg border p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{pos.symbol.replace("USDT", "")}</span>
                      <Badge className="bg-destructive/15 text-destructive border-destructive/40">SHORT</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-muted-foreground">Entry:</span>
                        <span className="font-mono ml-1">${pos.entry_price.toFixed(4)}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Notional:</span>
                        <span className="font-mono ml-1">${pos.notional.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Unlock:</span>
                        <span className="font-mono ml-1">{pos.unlock_date}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Stop:</span>
                        <span className="font-mono ml-1">${pos.stop_loss_price.toFixed(4)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Panel>

        <Panel
          className="col-span-12 xl:col-span-7"
          title={
            <span className="flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Timing Optimization — Top 10 (referência histórica)
            </span>
          }
          subtitle="25 combos testadas. -3d/+3d é o ótimo."
        >
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/70 text-muted-foreground uppercase tracking-wider text-[10px]">
                  <th className="px-3 py-2 text-left">#</th>
                  <th className="px-3 py-2 text-right">Entry</th>
                  <th className="px-3 py-2 text-right">Exit</th>
                  <th className="px-3 py-2 text-right">Hold</th>
                  <th className="px-3 py-2 text-right">ALL t</th>
                  <th className="px-3 py-2 text-right">ALL avg</th>
                  <th className="px-3 py-2 text-right">25 t</th>
                  <th className="px-3 py-2 text-right">25 avg</th>
                  <th className="px-3 py-2 text-right">26 t</th>
                  <th className="px-3 py-2 text-right">26 avg</th>
                </tr>
              </thead>
              <tbody>
                {TIMING_RESULTS.map((r, i) => {
                  const isBest = r.entryDays === -3 && r.exitDays === 3;
                  return (
                    <tr
                      key={`${r.entryDays}-${r.exitDays}`}
                      className={`border-b border-border/30 ${isBest ? "bg-success/5" : ""}`}
                    >
                      <td className="px-3 py-2">
                        {isBest ? (
                          <span className="flex items-center gap-1 text-success">
                            <Trophy className="h-3 w-3" />
                            {i + 1}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{i + 1}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{r.entryDays}d</td>
                      <td className="px-3 py-2 text-right font-mono">+{r.exitDays}d</td>
                      <td className="px-3 py-2 text-right font-mono text-muted-foreground">{r.holdDays}d</td>
                      <td className={`px-3 py-2 text-right font-mono ${r.allT > 3 ? "text-success" : "text-foreground"}`}>
                        {r.allT.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">+{r.allAvg}</td>
                      <td className={`px-3 py-2 text-right font-mono ${r.oos25T > 4 ? "text-success" : "text-foreground"}`}>
                        {r.oos25T.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">+{r.oos25Avg}</td>
                      <td className={`px-3 py-2 text-right font-mono ${r.oos26T > 2 ? "text-success" : "text-warning"}`}>
                        {r.oos26T.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">+{r.oos26Avg}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

      </div>

      {/* ─── Upcoming unlocks + per-symbol + config ────────────────────── */}
      <div className="grid grid-cols-12 gap-4 mb-6">
        <Panel
          className="col-span-12 lg:col-span-8"
          title={
            <span className="flex items-center gap-2">
              <Zap className="h-4 w-4" />
              Próximos unlocks — Agenda do bot
            </span>
          }
          subtitle={`Entry = 3d antes · Exit = 3d depois · Min $${config?.min_unlock_value_mm ?? 50}M`}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/70 text-muted-foreground uppercase tracking-wider text-[10px]">
                  <th className="px-4 py-2 text-left">Data</th>
                  <th className="px-4 py-2 text-left">Token</th>
                  <th className="px-4 py-2 text-right">Valor</th>
                  <th className="px-4 py-2 text-right">% Supply</th>
                  <th className="px-4 py-2 text-right">Entry date</th>
                  <th className="px-4 py-2 text-right">Exit date</th>
                  <th className="px-4 py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">
                      {connected ? "Nenhum unlock próximo (≥$50M) nos próximos 30 dias." : "API desconectada — não foi possível carregar a agenda."}
                    </td>
                  </tr>
                ) : (
                  upcoming.map((u, i) => {
                    const isNext = i === 0;
                    return (
                      <tr key={`${u.symbol}-${u.unlock_date}`} className={`border-b border-border/30 ${isNext ? "bg-primary/5" : ""}`}>
                        <td className="px-4 py-2.5 font-mono text-xs">{u.unlock_date}</td>
                        <td className="px-4 py-2.5">
                          <span className="font-medium">{u.symbol.replace("USDT", "")}</span>
                          <span className="text-muted-foreground text-xs ml-1">USDT-M</span>
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono">${u.unlock_value_mm}M</td>
                        <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{u.pct_supply}%</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-primary">{u.entry_date}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">{u.exit_date}</td>
                        <td className="px-4 py-2.5 text-right">
                          {u.days_until > 0 ? (
                            <Badge variant="outline" className={isNext ? "border-primary/40 text-primary" : ""}>
                              {u.days_until}d
                            </Badge>
                          ) : u.days_until === 0 ? (
                            <Badge className="bg-warning/15 text-warning border-warning/40">HOJE</Badge>
                          ) : (
                            <Badge variant="outline" className="text-muted-foreground">passado</Badge>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          className="col-span-12 lg:col-span-4"
          title={
            <span className="flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Configuração do bot
            </span>
          }
          subtitle="unlock_short_bot.py · paper mode"
        >
          <div className="p-4 space-y-3">
            <ConfigRow label="Entry" value={`${Math.abs(config?.entry_days ?? -3)}d antes`} />
            <ConfigRow label="Exit" value={`+${config?.exit_days ?? 3}d depois`} />
            <ConfigRow label="Hold period" value={`${(config?.exit_days ?? 3) - (config?.entry_days ?? -3)}d`} />
            <ConfigRow label="Fees" value={`${config?.fee_bps ?? 20}bps round trip`} />
            <ConfigRow label="Stop loss" value={`-${config?.stop_loss_pct ?? 15}%`} />
            <ConfigRow label="Max concurrent" value={`${config?.max_concurrent ?? 5} posições`} />
            <ConfigRow label="Max position" value={`${config?.max_position_pct ?? 25}% equity`} />
            <ConfigRow label="Kelly fraction" value={`${config?.kelly_fraction ?? 0.5} (half-Kelly)`} />
            <ConfigRow label="Min unlock" value={`$${config?.min_unlock_value_mm ?? 50}M`} />
            <ConfigRow label="Entry time" value={`${config?.entry_time_utc ?? "00:05"} UTC`} />

            <div className="pt-3 border-t border-border/50">
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2">
                Status AWS
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <Dot tone={connected ? "pos" : "neg"} />
                  <span>API: {connected ? "conectada" : "offline"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Dot tone={botRunning ? "pos" : "neg"} className={botRunning ? "animate-pulse" : ""} />
                  <span>Bot: {botRunning ? "rodando (tmux)" : "parado"}</span>
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      {/* ─── Per-symbol + funding + large unlocks ──────────────────────── */}
      <div className="grid grid-cols-12 gap-4 mb-6">
        <Panel
          className="col-span-12 xl:col-span-5"
          title={
            <span className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Per-symbol (paper trading)
            </span>
          }
          subtitle="Win rate e PnL por token"
        >
          <div className="p-4 h-[280px]">
            {perSymbol.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                Sem trades fechados ainda.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={perSymbol} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.28 0.014 240)" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 11, fontFamily: "JetBrains Mono" }}
                    tickFormatter={(v) => `$${v}`}
                  />
                  <YAxis
                    type="category"
                    dataKey="symbol"
                    tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    width={80}
                  />
                  <Tooltip {...chartTooltip} formatter={(v: number) => [`$${v.toFixed(2)}`, "Total PnL"]} />
                  <ReferenceLine x={0} stroke="oklch(0.4 0.014 240)" />
                  <Bar dataKey="total_pnl" radius={[0, 4, 4, 0]}>
                    {perSymbol.map((s, i) => (
                      <Cell key={i} fill={s.total_pnl > 0 ? "oklch(0.72 0.17 152)" : "oklch(0.65 0.2 25)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>


        <Panel
          className="col-span-12 md:col-span-4"
          title={
            <span className="flex items-center gap-2">
              <DollarSign className="h-4 w-4" />
              Funding cost (referência)
            </span>
          }
          subtitle="Binance USDT-M perp · 6d hold"
        >
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded border p-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">OOS Gross</div>
                <div className="font-mono text-lg text-success">+{FUNDING_COST.oosGrossBps}bps</div>
              </div>
              <div className="rounded border p-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">OOS Funding</div>
                <div className="font-mono text-lg text-muted-foreground">{FUNDING_COST.oosFundingBps}bps</div>
              </div>
              <div className="rounded border p-3 col-span-2 bg-success/5">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">NET OOS</div>
                <div className="font-mono text-xl text-success">+{FUNDING_COST.oosNetBps}bps</div>
                <div className="text-xs text-muted-foreground mt-1">t-stat = {FUNDING_COST.oosNetTStat}</div>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{FUNDING_COST.note}</p>
          </div>
        </Panel>

        <Panel
          className="col-span-12 md:col-span-3"
          title={
            <span className="flex items-center gap-2">
              <Trophy className="h-4 w-4" />
              Large unlocks (ref.)
            </span>
          }
          subtitle="≥$200M · backtest histórico"
        >
          <div className="p-4 space-y-3">
            <div className="rounded border p-4 bg-success/5 text-center">
              <div className="text-3xl font-mono font-bold text-success">{LARGE_UNLOCKS.winRate}%</div>
              <div className="text-xs text-muted-foreground mt-1">Win rate ({LARGE_UNLOCKS.count} trades)</div>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Avg PnL</span>
              <span className="font-mono text-success">+{LARGE_UNLOCKS.avgBps}bps</span>
            </div>
            <p className="text-xs text-muted-foreground">{LARGE_UNLOCKS.note}</p>
          </div>
        </Panel>

      </div>

      {/* ─── Recent trades table ───────────────────────────────────────── */}
      <Panel
        className="col-span-12"
        title="Trades recentes"
        subtitle={`${allTrades.length} trades fechados · paper trading`}
      >
        <div className="overflow-x-auto">
          {allTrades.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              Nenhum trade fechado ainda. O bot precisa de unlocks ≥$50M para abrir posições.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/70 text-muted-foreground uppercase tracking-wider text-[10px]">
                  <th className="px-4 py-2 text-left">Token</th>
                  <th className="px-4 py-2 text-left">Unlock</th>
                  <th className="px-4 py-2 text-right">Entry</th>
                  <th className="px-4 py-2 text-right">Exit</th>
                  <th className="px-4 py-2 text-right">Notional</th>
                  <th className="px-4 py-2 text-right">Gross PnL</th>
                  <th className="px-4 py-2 text-right">Fees</th>
                  <th className="px-4 py-2 text-right">Net PnL</th>
                  <th className="px-4 py-2 text-right">%</th>
                  <th className="px-4 py-2 text-left">Reason</th>
                </tr>
              </thead>
              <tbody>
                {allTrades.slice().reverse().slice(0, 50).map((t, i) => (
                  <tr key={i} className="border-b border-border/30">
                    <td className="px-4 py-2.5 font-medium">{t.symbol.replace("USDT", "")}</td>
                    <td className="px-4 py-2.5 font-mono text-xs">{t.unlock_date}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">${t.entry_price.toFixed(4)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">${t.exit_price.toFixed(4)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">${t.notional.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{fmtMoney(t.gross_pnl)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">{fmtMoney(t.fees)}</td>
                    <td className={`px-4 py-2.5 text-right font-mono text-xs ${t.net_pnl > 0 ? "text-success" : "text-destructive"}`}>
                      {fmtMoney(t.net_pnl)}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-mono text-xs ${t.pnl_pct > 0 ? "text-success" : "text-destructive"}`}>
                      {t.pnl_pct > 0 ? "+" : ""}{t.pnl_pct.toFixed(2)}%
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant="outline" className="text-xs">
                        {t.close_reason}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Panel>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

