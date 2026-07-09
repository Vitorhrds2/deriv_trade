import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono } from "@/components/kit";
import { fmtMoney, percentile } from "@/lib/format";
import { getHftTrades, type HftTrade } from "@/lib/hft-api";
import { realHypotheses } from "@/lib/hypotheses-data";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

export const Route = createFileRoute("/analytics")({
  head: () => ({ meta: [{ title: "Analytics — TradeLab OS" }] }),
  component: AnalyticsPage,
});

const tt = { contentStyle: { background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12, fontFamily: "JetBrains Mono" } };

function cumulativeEquity(trades: HftTrade[]) {
  let running = 0;
  return trades.map((t, i) => {
    running += t.profit ?? 0;
    return { t: `#${i + 1}`, equity: +running.toFixed(2) };
  });
}

function pnlByHour(trades: HftTrade[]) {
  const buckets = Array.from({ length: 24 }, (_, h) => ({ h: `${h}h`, pnl: 0, n: 0 }));
  for (const t of trades) {
    if (!t.ts || t.profit == null) continue;
    const h = parseInt(t.ts.slice(11, 13), 10);
    if (Number.isNaN(h)) continue;
    buckets[h].pnl += t.profit;
    buckets[h].n += 1;
  }
  return buckets;
}

function AnalyticsPage() {
  const tradesQuery = useQuery({ queryKey: ["hft-trades"], queryFn: () => getHftTrades(), refetchInterval: 5000 });
  const trades = tradesQuery.data;
  const allTrades = trades?.recentTrades ?? [];

  const equityData = useMemo(() => cumulativeEquity(allTrades), [allTrades]);
  const hourData = useMemo(() => pnlByHour(allTrades), [allTrades]);
  const execTimes = useMemo(
    () => allTrades.map((t) => t.execMs).filter((v): v is number => v != null).sort((a, b) => a - b),
    [allTrades],
  );
  const avgExec = execTimes.length ? execTimes.reduce((a, b) => a + b, 0) / execTimes.length : null;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › observability"
        title="Analytics & Performance"
        description="Métricas reais derivadas dos trades do hft_bot — único fluxo de execução do ecossistema hoje."
        actions={
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => toast.info("Conceito — sem geração de relatório real implementada ainda.")}>
            <Download className="h-4 w-4" />Exportar
          </Button>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat
          label="PnL acumulado"
          value={trades ? fmtMoney(trades.total.pnlTotal) : "—"}
          tone={trades && trades.total.pnlTotal < 0 ? "neg" : "neutral"}
        />
        <Stat label="Win rate" value={trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"} hint={`N=${trades?.total.n ?? 0}`} />
        <Stat
          label="EV/trade"
          value={trades ? fmtMoney(trades.total.evPerTrade) : "—"}
          tone={trades && trades.total.evPerTrade < 0 ? "neg" : "neutral"}
        />
        <Stat label="Hipóteses c/ capital real" value={1} hint={`de ${realHypotheses.length} testadas (só hft_bot)`} />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Curva de equity real (hft_bot)" subtitle="soma cumulativa do profit de cada trade fechada, em ordem">
          <div className="h-[300px] p-3">
            {equityData.length > 0 ? (
              <ResponsiveContainer>
                <AreaChart data={equityData}>
                  <defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="oklch(0.70 0.20 340)" stopOpacity={0.35} /><stop offset="100%" stopColor="oklch(0.70 0.20 340)" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                  <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
                  <Tooltip {...tt} />
                  <Area type="monotone" dataKey="equity" stroke="oklch(0.70 0.20 340)" strokeWidth={2} fill="url(#ag)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                {tradesQuery.isLoading ? "carregando…" : "Sem trades ainda, ou API inacessível."}
              </div>
            )}
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="P&L por hipótese (real)" subtitle="a maioria foi teste puramente estatístico, sem capital">
          <ul className="divide-y divide-border/60">
            {realHypotheses.map((h) => {
              const max = Math.max(...realHypotheses.map((x) => Math.abs(x.pnl))) || 1;
              const pct = (Math.abs(h.pnl) / max) * 100;
              return (
                <li key={h.id} className="px-4 py-3 cursor-pointer hover:bg-muted/30" onClick={() => toast.info(h.title, { description: `P&L ${fmtMoney(h.pnl)} · N=${h.trades} ${h.sampleUnit}` })}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="truncate">{h.title}</span>
                    <span className={`font-mono ${h.pnl >= 0 ? "text-pos" : "text-neg"}`}>{fmtMoney(h.pnl)}</span>
                  </div>
                  <div className="h-1.5 bg-muted rounded-full mt-2 overflow-hidden">
                    <div className={`h-full transition-all ${h.pnl >= 0 ? "bg-success" : "bg-destructive"}`} style={{ width: `${pct}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </Panel>

        <Panel className="col-span-12 xl:col-span-7" title="P&L por hora (real)" subtitle="hora local do log (GMT-3) · golden hour do bot: 12-18 UTC = 9-15 GMT-3">
          <div className="h-[260px] p-3">
            {allTrades.length > 0 ? (
              <ResponsiveContainer>
                <BarChart data={hourData}>
                  <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                  <XAxis dataKey="h" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 9 }} axisLine={false} tickLine={false} interval={1} />
                  <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip {...tt} formatter={(v: number) => [fmtMoney(v), "pnl"]} />
                  <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                    {hourData.map((p, i) => <Cell key={i} fill={p.pnl >= 0 ? "oklch(0.85 0.18 130)" : "oklch(0.65 0.22 25)"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">Sem trades ainda.</div>
            )}
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-5" title="Métricas de execução (reais)" subtitle="Execution Time real logado por trade, ver hft_v62_audit_report.md">
          <div className="grid grid-cols-3 divide-x divide-border/60 h-full">
            {[
              { l: "amostras", v: execTimes.length ? String(execTimes.length) : "—" },
              { l: "latência média", v: avgExec != null ? `${Math.round(avgExec)}ms` : "—" },
              { l: "latência p99", v: percentile(execTimes, 99) != null ? `${percentile(execTimes, 99)}ms` : "—" },
            ].map((m) => (
              <div key={m.l} className="p-4 flex flex-col justify-center">
                <Mono className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.l}</Mono>
                <div className="text-xl font-mono font-semibold mt-1">{m.v}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
