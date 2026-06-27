import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { riskBreakdown } from "@/lib/mock-data";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { AlertTriangle, OctagonX, ShieldCheck } from "lucide-react";
import { useApp } from "@/lib/store";
import { toast } from "sonner";

export const Route = createFileRoute("/risk")({
  head: () => ({ meta: [{ title: "Risk Engine — TradeLab OS" }] }),
  component: RiskPage,
});

const limits = [
  { name: "Max position size",   used: 62, cap: "$50k",  hard: false },
  { name: "Max leverage",        used: 35, cap: "5x",    hard: false },
  { name: "Portfolio gross",     used: 78, cap: "$200k", hard: false },
  { name: "Daily loss limit",    used: 22, cap: "−$4k",  hard: true  },
  { name: "VaR 95% (1d)",        used: 48, cap: "$8.2k", hard: false },
  { name: "Single-venue concentration", used: 91, cap: "70%", hard: true },
];

const alerts = [
  { t: "12:01", sev: "warn",  msg: "Concentração em Polymarket excede 70% (91%)." },
  { t: "11:42", sev: "info",  msg: "VaR recalculado: $3.9k → $4.0k (+2.6%)." },
  { t: "10:18", sev: "error", msg: "Bot nvda-drift-sim parou: data feed perdido." },
  { t: "09:54", sev: "info",  msg: "Daily loss limit ajustado de $3k para $4k por marina.r." },
];

function RiskPage() {
  const setKillOpen = useApp((s) => s.setKillOpen);
  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › risk engine"
        title="Risk Engine"
        description="Limites de exposição, leverage, drawdown, VaR e circuit breakers — em tempo real."
        actions={
          <>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => toast.info("Editor de políticas aberto")}>
              <ShieldCheck className="h-4 w-4" />Políticas
            </Button>
            <Button variant="destructive" size="sm" className="gap-1.5" onClick={() => setKillOpen(true)}>
              <OctagonX className="h-4 w-4" />Kill switch global
            </Button>
          </>
        }
      />


      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Gross exposure" value="$156k" hint="cap $200k" />
        <Stat label="Net exposure"   value="$41k"  delta="long bias" tone="neutral" />
        <Stat label="VaR 95% (1d)"   value="$4.0k" delta="+2.6% hoje" tone="neutral" />
        <Stat label="Drawdown atual" value="−3.1%" delta="cap −8.0%" tone="neutral" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Limites de risco">
          <ul className="divide-y divide-border/60">
            {limits.map((l) => (
              <li key={l.name} className="px-4 py-4 grid grid-cols-12 gap-3 items-center">
                <div className="col-span-4 text-sm flex items-center gap-2">
                  {l.hard && <AlertTriangle className="h-3.5 w-3.5 text-warning" />}
                  {l.name}
                </div>
                <div className="col-span-6">
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full ${l.used > 85 ? "bg-destructive" : l.used > 65 ? "bg-warning" : "bg-primary"}`} style={{ width: `${l.used}%` }} />
                  </div>
                </div>
                <div className="col-span-2 text-right font-mono text-xs">
                  <span className={l.used > 85 ? "text-destructive" : l.used > 65 ? "text-warning" : "text-foreground"}>{l.used}%</span>
                  <span className="text-muted-foreground"> / {l.cap}</span>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="Concentração por classe">
          <div className="h-[260px] p-3">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={riskBreakdown} dataKey="value" innerRadius={55} outerRadius={90} paddingAngle={3} strokeWidth={0}>
                  {riskBreakdown.map((_, i) => <Cell key={i} fill={`var(--chart-${i + 1})`} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="col-span-12" title="Alertas e auditoria">
          <ul className="divide-y divide-border/60 font-mono text-xs">
            {alerts.map((a, i) => (
              <li key={i} className="px-4 py-3 flex items-center gap-3">
                <Mono className="text-muted-foreground w-12">{a.t}</Mono>
                <Badge variant="outline" className={`uppercase text-[10px] ${a.sev === "error" ? "border-destructive/40 text-destructive bg-destructive/10" : a.sev === "warn" ? "border-warning/40 text-warning bg-warning/10" : "border-info/40 text-info bg-info/10"}`}>{a.sev}</Badge>
                <span className="flex-1 text-foreground/90">{a.msg}</span>
                <Dot tone={a.sev === "error" ? "neg" : a.sev === "warn" ? "warn" : "info"} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
