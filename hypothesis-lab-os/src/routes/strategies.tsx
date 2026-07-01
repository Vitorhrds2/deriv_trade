import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Mono, Stat, ConceptBanner } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { strategies, statusBadgeClass, fmtMoney } from "@/lib/mock-data";
import { Code2, GitBranch, MousePointerSquareDashed, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

export const Route = createFileRoute("/strategies")({
  head: () => ({ meta: [{ title: "Strategy Builder — TradeLab OS" }] }),
  component: StrategiesPage,
});

const code = `# cpi_btc_long_v3.py
from tradelab import Strategy, signals

class CpiBtcLong(Strategy):
    market = "BTC-PERP"
    timeframe = "1m"

    def on_event(self, ev):
        if ev.name != "US_CPI":
            return
        if ev.actual > ev.forecast:
            self.long(
                size=self.risk.notional(0.02),
                tp=signals.atr(14) * 2,
                sl=signals.atr(14) * 1,
                exit_after="4h",
            )

    def on_tick(self, bar):
        if self.position and bar.drawdown > 0.02:
            self.flatten()`;

function StrategiesPage() {
  const [deploying, setDeploying] = useState(0);
  const [selectedId, setSelectedId] = useState(strategies[0].id);
  const selected = strategies.find((x) => x.id === selectedId) ?? strategies[0];
  const startDeploy = () => {
    if (deploying > 0) return;
    setDeploying(5);
    const steps = [20, 42, 68, 88, 100];
    steps.forEach((p, i) => setTimeout(() => setDeploying(p), 250 + i * 350));
    setTimeout(() => {
      setDeploying(0);
      toast.info("Demo de UI — sem pipeline de deploy real", { description: "O unico deploy real hoje (hft_bot) e manual: scp + tmux na EC2. Ver /bots." });
    }, 250 + steps.length * 350 + 200);
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="research › strategy builder"
        title="Strategy Builder"
        description="Converta hipóteses em lógica executável — visual ou em código — com versionamento e revisão por par."
        actions={<Button size="sm" className="gap-1.5" onClick={() => toast.info("Conceito — sem editor de estratégias real implementado ainda.")}><Plus className="h-4 w-4" />Nova estratégia</Button>}
      />

      <ConceptBanner>
        Preview de UI para um strategy builder multi-linguagem com deploy versionado. Na prática, estratégias são scripts Python standalone em <Mono>trading-engine/</Mono>, sem abstração comum nem deploy automatizado.
      </ConceptBanner>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Estratégias" value={strategies.length} />
        <Stat label="Sharpe médio" value={(strategies.reduce((a, s) => a + s.sharpe, 0) / strategies.length).toFixed(2)} delta="+0.18 mês" tone="pos" />
        <Stat label="Win rate médio" value={`${Math.round((strategies.reduce((a, s) => a + s.winRate, 0) / strategies.length) * 100)}%`} />
        <Stat label="Drawdown agregado" value="6.4%" delta="dentro do limite" tone="neutral" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-7" title="Estratégias do workspace">
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Nome</th>
                <th className="text-left px-4 py-2">Hipótese</th>
                <th className="text-left px-4 py-2">Lang</th>
                <th className="text-right px-4 py-2">Sharpe</th>
                <th className="text-right px-4 py-2">DD</th>
                <th className="text-right px-4 py-2">Win%</th>
                <th className="text-right px-4 py-2">P&L</th>
                <th className="text-left px-4 py-2">Estado</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {strategies.map((s) => {
                const active = s.id === selectedId;
                return (
                  <tr key={s.id} onClick={() => setSelectedId(s.id)} className={`border-b border-border/40 last:border-0 cursor-pointer transition-colors ${active ? "bg-primary/5" : "hover:bg-muted/30"}`}>
                    <td className="px-4 py-3">
                      <div className={`text-sm font-sans font-medium ${active ? "text-primary" : "text-foreground"}`}>{s.name}</div>
                      <div className="text-[10px] text-muted-foreground">{s.id} · {s.broker}</div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{s.hypothesisId}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className="text-[10px] font-mono uppercase border-border">
                        {s.language === "Python" && <Code2 className="h-3 w-3 mr-1" />}
                        {s.language === "Visual" && <MousePointerSquareDashed className="h-3 w-3 mr-1" />}
                        {s.language === "TypeScript" && <Code2 className="h-3 w-3 mr-1" />}
                        {s.language}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">{s.sharpe.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-warning">{s.drawdown.toFixed(1)}%</td>
                    <td className="px-4 py-3 text-right">{Math.round(s.winRate * 100)}%</td>
                    <td className={`px-4 py-3 text-right ${s.pnl > 0 ? "text-pos" : s.pnl < 0 ? "text-neg" : "text-muted-foreground"}`}>{fmtMoney(s.pnl)}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={`${statusBadgeClass(s.status)} text-[10px] uppercase tracking-wider`}>{s.status}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 xl:col-span-5" title={<><Mono className="text-muted-foreground">~/</Mono> {selected.name}.py</>} subtitle={`${selected.id} · ${selected.broker} · sharpe ${selected.sharpe.toFixed(2)}`} actions={
          <>
            <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => toast.info("Branch: main", { description: "3 commits ahead of origin." })}><GitBranch className="h-4 w-4" />main</Button>
            <Button size="sm" onClick={startDeploy} disabled={deploying > 0}>{deploying > 0 ? `Deploying ${deploying}%` : "Deploy"}</Button>
          </>
        }>
          {deploying > 0 && <Progress value={deploying} className="h-0.5 rounded-none" />}
          <pre className="font-mono text-[11px] leading-relaxed p-4 overflow-auto max-h-[460px] bg-background/30 text-foreground/90">
            <code>{code}</code>
          </pre>
        </Panel>

        <Panel className="col-span-12" title="Visual builder (preview)" subtitle="Conecte triggers, indicadores e operadores lógicos.">
          <div className="p-6 grid-bg rounded-b-lg">
            <div className="grid grid-cols-5 gap-4 items-stretch text-xs font-mono">
              {[
                { t: "EVENT", v: "US CPI", c: "border-accent/40 text-accent" },
                { t: "FILTER", v: "actual > forecast", c: "border-info/40 text-info" },
                { t: "INDICATOR", v: "ATR(14)", c: "border-primary/40 text-primary" },
                { t: "ACTION", v: "LONG BTC-PERP", c: "border-success/40 text-success" },
                { t: "EXIT", v: "after 4h | sl=ATR", c: "border-warning/40 text-warning" },
              ].map((n, i) => (
                <div key={i} className={`rounded-md border bg-card p-4 ${n.c} relative`}>
                  <div className="text-[9px] uppercase tracking-[0.2em] text-muted-foreground">{n.t}</div>
                  <div className="text-sm font-medium mt-2 text-foreground">{n.v}</div>
                  {i < 4 && <div className="hidden xl:block absolute top-1/2 -right-3 w-3 h-px bg-border" />}
                </div>
              ))}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
