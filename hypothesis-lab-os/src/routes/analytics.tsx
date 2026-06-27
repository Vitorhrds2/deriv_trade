import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono } from "@/components/kit";
import { equityCurve, pnlBars, hypotheses, fmtMoney } from "@/lib/mock-data";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

export const Route = createFileRoute("/analytics")({
  head: () => ({ meta: [{ title: "Analytics — TradeLab OS" }] }),
  component: AnalyticsPage,
});

const tt = { contentStyle: { background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12, fontFamily: "JetBrains Mono" } };

function cellColor(v: number) {
  if (v > 700) return "bg-success/70";
  if (v > 200) return "bg-success/40";
  if (v > -200) return "bg-muted";
  if (v > -700) return "bg-destructive/40";
  return "bg-destructive/70";
}

const TFS = ["1D", "7D", "30D", "60D", "YTD"] as const;
type TF = (typeof TFS)[number];

function AnalyticsPage() {
  const [tf, setTf] = useState<TF>("60D");
  const [hoverCell, setHoverCell] = useState<{ d: number; h: number; v: number } | null>(null);

  const scale = tf === "1D" ? 0.4 : tf === "7D" ? 0.7 : tf === "30D" ? 0.9 : tf === "YTD" ? 1.4 : 1;
  const data = useMemo(() => equityCurve.map((p, i) => ({ ...p, equity: p.equity * scale + Math.sin(i / 4) * 80, benchmark: p.benchmark * scale })), [scale]);

  const heatmap = useMemo(() => Array.from({ length: 7 }, (_, d) =>
    Array.from({ length: 8 }, (_, h) => ({
      d, h,
      pnl: (Math.sin(d * 1.1 + h * 0.6) * 800 + Math.cos(h - d) * 400 + (h === 4 ? 600 : 0)) * scale,
    }))
  ), [scale]);

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › observability"
        title="Analytics & Performance"
        description="Atribuição de PnL por hipótese, heatmaps, métricas de execução e replay de trades."
        actions={
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => toast.success("Relatório exportado", { description: "performance_60d.pdf gerado." })}>
            <Download className="h-4 w-4" />Exportar
          </Button>
        }
      />

      <div className="px-1 mb-4 flex items-center gap-1">
        {TFS.map((t) => (
          <button key={t} onClick={() => setTf(t)} className={`text-[10px] font-mono uppercase tracking-wider px-3 py-1.5 rounded border transition-colors ${tf === t ? "bg-primary/15 border-primary/40 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>{t}</button>
        ))}
        <span className="ml-3 text-[11px] font-mono text-muted-foreground">janela ativa: {tf}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Retorno YTD" value={`+${(18.4 * scale).toFixed(1)}%`} delta="benchmark +6.1%" tone="pos" />
        <Stat label="Sharpe" value={(2.41 * (scale > 1 ? 1.05 : scale)).toFixed(2)} delta="+0.21 vs Q-1" tone="pos" />
        <Stat label="Win rate" value="63%" delta="184 trades" />
        <Stat label="Expectancy" value={fmtMoney(268 * scale)} delta="por trade" tone="pos" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title={`Curva de equity composta · ${tf}`}>
          <div className="h-[300px] p-3">
            <ResponsiveContainer>
              <AreaChart data={data}>
                <defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="oklch(0.70 0.20 340)" stopOpacity={0.35} /><stop offset="100%" stopColor="oklch(0.70 0.20 340)" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip {...tt} />
                <Area type="monotone" dataKey="equity" stroke="oklch(0.70 0.20 340)" strokeWidth={2} fill="url(#ag)" />
                <Area type="monotone" dataKey="benchmark" stroke="oklch(0.62 0.018 240)" strokeDasharray="3 3" fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="P&L por hipótese">
          <ul className="divide-y divide-border/60">
            {hypotheses.slice(0, 5).map((h) => {
              const max = Math.max(...hypotheses.map((x) => Math.abs(x.pnl))) || 1;
              const pct = (Math.abs(h.pnl) / max) * 100;
              return (
                <li key={h.id} className="px-4 py-3 cursor-pointer hover:bg-muted/30" onClick={() => toast.info(h.title, { description: `P&L ${fmtMoney(h.pnl)} · ${h.trades} trades` })}>
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

        <Panel className="col-span-12 xl:col-span-7" title="Heatmap — P&L por dia × hora" subtitle={hoverCell ? `${["seg","ter","qua","qui","sex","sáb","dom"][hoverCell.d]} ${(hoverCell.h * 3).toString().padStart(2, "0")}h · ${fmtMoney(hoverCell.v)}` : "passe o mouse nas células"}>
          <div className="p-4">
            <div className="flex items-center gap-1 mb-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <div className="w-10"></div>
              {Array.from({ length: 8 }, (_, h) => <div key={h} className="flex-1 text-center">{(h * 3).toString().padStart(2, "0")}h</div>)}
            </div>
            {heatmap.map((row, d) => (
              <div key={d} className="flex items-center gap-1 mb-1">
                <div className="w-10 text-[10px] font-mono uppercase text-muted-foreground">{["seg","ter","qua","qui","sex","sáb","dom"][d]}</div>
                {row.map((c, i) => (
                  <div key={i}
                    onMouseEnter={() => setHoverCell({ d: c.d, h: c.h, v: c.pnl })}
                    onMouseLeave={() => setHoverCell(null)}
                    onClick={() => toast.info(`${["seg","ter","qua","qui","sex","sáb","dom"][c.d]} ${(c.h * 3).toString().padStart(2, "0")}h`, { description: fmtMoney(c.pnl) })}
                    className={`flex-1 aspect-square rounded ${cellColor(c.pnl)} hover:ring-2 hover:ring-primary/60 transition cursor-pointer`} />
                ))}
              </div>
            ))}
            <div className="flex items-center justify-end gap-2 mt-3 text-[10px] font-mono text-muted-foreground">
              <span>−</span>
              <div className="h-2 w-3 rounded bg-destructive/70" />
              <div className="h-2 w-3 rounded bg-destructive/40" />
              <div className="h-2 w-3 rounded bg-muted" />
              <div className="h-2 w-3 rounded bg-success/40" />
              <div className="h-2 w-3 rounded bg-success/70" />
              <span>+</span>
            </div>
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-5" title="Atribuição diária">
          <div className="h-[300px] p-3">
            <ResponsiveContainer>
              <BarChart data={pnlBars}>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="d" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip {...tt} />
                <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                  {pnlBars.map((p, i) => <Cell key={i} fill={p.pnl >= 0 ? "oklch(0.85 0.18 130)" : "oklch(0.65 0.22 25)"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="col-span-12" title="Métricas de execução">
          <div className="grid grid-cols-2 md:grid-cols-6 divide-x divide-border/60">
            {[
              { l: "fill rate",        v: "98.4%", t: "+0.6%" },
              { l: "slippage médio",   v: "1.2bp", t: "−0.3bp" },
              { l: "latência p50",     v: "64ms",  t: "vs SLO 100" },
              { l: "latência p99",     v: "142ms", t: "vs SLO 250" },
              { l: "rejeições",        v: "0.21%", t: "−12%" },
              { l: "uptime",           v: "99.97%", t: "30d" },
            ].map((m) => (
              <div key={m.l} className="p-4">
                <Mono className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.l}</Mono>
                <div className="text-xl font-mono font-semibold mt-1">{m.v}</div>
                <div className="text-[11px] font-mono text-muted-foreground mt-0.5">{m.t}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
