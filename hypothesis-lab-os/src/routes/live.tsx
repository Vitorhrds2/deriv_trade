import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Dot } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { getHftStatus, getHftTrades, isHftLive, type HftTrade } from "@/lib/hft-api";
import { fmtMoney } from "@/lib/format";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

export const Route = createFileRoute("/live")({
  head: () => ({ meta: [{ title: "Live: hft_bot — TradeLab OS" }] }),
  component: LivePage,
});

const tt = {
  contentStyle: {
    background: "oklch(0.20 0.014 240)",
    border: "1px solid oklch(0.28 0.014 240)",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "JetBrains Mono",
  },
};

function cumulativeEquity(trades: HftTrade[]) {
  let running = 0;
  return trades.map((t, i) => {
    running += t.profit ?? 0;
    return { t: `#${i + 1}`, equity: +running.toFixed(2) };
  });
}

function LivePage() {
  const statusQuery = useQuery({
    queryKey: ["hft-status"],
    queryFn: () => getHftStatus(),
    refetchInterval: 5000,
  });
  const tradesQuery = useQuery({
    queryKey: ["hft-trades"],
    queryFn: () => getHftTrades(),
    refetchInterval: 5000,
  });

  const status = statusQuery.data;
  const trades = tradesQuery.data;
  const isLive = status ? isHftLive(status) : false;
  const equityData = useMemo(() => cumulativeEquity(trades?.recentTrades ?? []), [trades]);
  const recentDesc = trades?.recentTrades.slice().reverse().slice(0, 25) ?? [];

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › live"
        title={
          <span className="flex items-center gap-3">
            Live: hft_bot
            <span
              className={`flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider ${isLive ? "text-success" : "text-muted-foreground"}`}
            >
              <Dot tone={isLive ? "pos" : "muted"} className={isLive ? "animate-pulse" : ""} />
              {isLive ? "ao vivo" : "offline"}
            </span>
          </span>
        }
        description="Único fluxo real de execução do ecossistema hoje: Multiplier contracts em cryBTCUSD (Deriv, conta demo). Sem book multi-asset/multi-broker fake."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Trades (N)" value={trades?.total.n ?? "—"} hint="conta demo Deriv" />
        <Stat
          label="Win rate"
          value={trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"}
        />
        <Stat
          label="PnL acumulado"
          value={trades ? fmtMoney(trades.total.pnlTotal) : "—"}
          tone={trades && trades.total.pnlTotal < 0 ? "neg" : "neutral"}
        />
        <Stat
          label="EV/trade"
          value={trades ? fmtMoney(trades.total.evPerTrade) : "—"}
          tone={trades && trades.total.evPerTrade < 0 ? "neg" : "neutral"}
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          className="col-span-12"
          title="Equity acumulada (real)"
          subtitle="soma cumulativa do profit de cada trade fechada, na ordem em que ocorreram"
        >
          <div className="h-[280px] p-3">
            {equityData.length > 0 ? (
              <ResponsiveContainer>
                <AreaChart data={equityData}>
                  <defs>
                    <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.65 0.22 25)" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="oklch(0.65 0.22 25)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                  <XAxis
                    dataKey="t"
                    tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `$${v}`}
                  />
                  <Tooltip {...tt} formatter={(v: number) => [`$${v.toFixed(2)}`, "equity"]} />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="oklch(0.65 0.22 25)"
                    strokeWidth={2}
                    fill="url(#lg)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                {tradesQuery.isLoading ? "carregando…" : "Sem trades ainda, ou API inacessível."}
              </div>
            )}
          </div>
        </Panel>

        <Panel
          className="col-span-12"
          title="Trades recentes (reais)"
          subtitle={`${trades?.total.n ?? 0} trades totais · conta demo Deriv`}
        >
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Timestamp</th>
                <th className="text-left px-4 py-2">Direção</th>
                <th className="text-left px-4 py-2">Grupo</th>
                <th className="text-right px-4 py-2">Salto</th>
                <th className="text-right px-4 py-2">Exec</th>
                <th className="text-left px-4 py-2">Fechamento</th>
                <th className="text-right px-4 py-2">Profit</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {recentDesc.map((t, i) => (
                <tr
                  key={t.contractId ?? i}
                  className="border-b border-border/40 last:border-0 hover:bg-muted/30"
                >
                  <td className="px-4 py-2.5 text-muted-foreground">{t.ts ?? "—"}</td>
                  <td className={`px-4 py-2.5 ${t.direction === "UP" ? "text-pos" : "text-neg"}`}>
                    {t.direction}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge
                      variant="outline"
                      className={`text-[10px] uppercase ${t.group === "ANTI" ? "border-info/40 text-info bg-info/10" : "border-border text-muted-foreground"}`}
                    >
                      {t.group}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{t.jump.toFixed(2)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {t.execMs != null ? `${t.execMs}ms` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground truncate max-w-[220px]">
                    {t.closeReason ?? "—"}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums ${(t.profit ?? 0) > 0 ? "text-pos" : (t.profit ?? 0) < 0 ? "text-neg" : "text-muted-foreground"}`}
                  >
                    {t.profit != null ? fmtMoney(t.profit) : "—"}
                  </td>
                </tr>
              ))}
              {recentDesc.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    {tradesQuery.isLoading
                      ? "carregando…"
                      : "Sem trades reais ainda, ou API inacessível."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
