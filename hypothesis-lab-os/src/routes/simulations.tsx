import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { equityCurve, fmtMoney, pnlBars } from "@/lib/mock-data";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Play, Repeat, Sliders } from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { toast } from "sonner";
import { useApp } from "@/lib/store";

export const Route = createFileRoute("/simulations")({
  head: () => ({ meta: [{ title: "Simulation Engine — TradeLab OS" }] }),
  component: SimulationsPage,
});

const tt = { contentStyle: { background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12, fontFamily: "JetBrains Mono" } };

type Run = { id: string; strategy: string; period: string; sharpe: number; dd: number; pnl: number; trades: number; hitRate: number; status: "passed" | "failed" | "warning" };

const initialRuns: Run[] = [
  { id: "SIM-2241", strategy: "cpi_btc_long_v3", period: "2022-01 → 2025-05", sharpe: 2.14, dd: 6.2, pnl: 48_210, trades: 184, hitRate: 0.62, status: "passed" },
  { id: "SIM-2240", strategy: "poly_kshi_arb",  period: "2024-06 → 2025-05", sharpe: 3.47, dd: 2.1, pnl: 71_022, trades: 1_244, hitRate: 0.81, status: "passed" },
  { id: "SIM-2239", strategy: "fomc_steepener", period: "2020-01 → 2025-05", sharpe: 0.91, dd: 11.2, pnl: -2_310, trades: 67, hitRate: 0.49, status: "failed" },
  { id: "SIM-2238", strategy: "eth_funding_revert", period: "2023-01 → 2025-05", sharpe: 1.78, dd: 5.6, pnl: 18_440, trades: 312, hitRate: 0.58, status: "warning" },
];

function SimulationsPage() {
  const pushNotif = useApp((s) => s.pushNotif);
  const [runs, setRuns] = useState<Run[]>(initialRuns);
  const [selectedId, setSelectedId] = useState(initialRuns[0].id);
  const [running, setRunning] = useState(0);
  const [paramsOpen, setParamsOpen] = useState(false);
  const [strategy, setStrategy] = useState("cpi_btc_long_v3");
  const [slippage, setSlippage] = useState([1]);
  const [fees, setFees] = useState([4]);
  const [trials, setTrials] = useState([10]);
  const [realEquity, setRealEquity] = useState<{ t: string; equity: number }[] | null>(null);

  useEffect(() => {
    fetch("/backtest_results.csv")
      .then((res) => {
        if (!res.ok) throw new Error("not found");
        return res.text();
      })
      .then((text) => {
        const lines = text.split("\n");
        const headers = lines[0].split(",");
        const equityIdx = headers.indexOf("equity");
        const timeIdx = headers.indexOf("timestamp");
        
        if (equityIdx > -1 && timeIdx > -1) {
          const parsed = lines.slice(1).filter(l => l.trim().length > 0).map(line => {
            const cols = line.split(",");
            return {
              t: cols[timeIdx].split(" ")[1] || cols[timeIdx], // try to get time portion
              equity: Number(cols[equityIdx])
            };
          });
          const sampled = parsed.filter((_, i) => i % Math.ceil(parsed.length / 200) === 0);
          setRealEquity(sampled);
        }
      })
      .catch(err => console.log("No backtest_results.csv found"));
  }, []);

  const selected = useMemo(() => runs.find((r) => r.id === selectedId) ?? runs[0], [runs, selectedId]);

  const runSim = () => {
    if (running > 0) return;
    setRunning(5);
    const steps = [18, 36, 58, 76, 92, 100];
    steps.forEach((p, i) => setTimeout(() => setRunning(p), 250 + i * 280));
    setTimeout(() => {
      setRunning(0);
      const id = `SIM-${2242 + runs.length - initialRuns.length}`;
      const sharpe = +(1.5 + Math.random() * 2).toFixed(2);
      const status: Run["status"] = sharpe > 2 ? "passed" : sharpe > 1 ? "warning" : "failed";
      const newRun: Run = {
        id, strategy, period: "2022-01 → 2025-05",
        sharpe, dd: +(2 + Math.random() * 8).toFixed(1),
        pnl: Math.round((Math.random() * 80000) - 5000),
        trades: 50 + Math.floor(Math.random() * 800),
        hitRate: +(0.45 + Math.random() * 0.4).toFixed(2),
        status,
      };
      setRuns((prev) => [newRun, ...prev]);
      setSelectedId(id);
      pushNotif({ kind: status === "passed" ? "success" : status === "warning" ? "warn" : "error", title: `Backtest ${id} concluído`, desc: `${strategy} · sharpe ${sharpe.toFixed(2)}` });
      toast.success(`Backtest ${id} concluído`, { description: `${strategy} · sharpe ${sharpe.toFixed(2)} · status ${status}` });
    }, 250 + steps.length * 280 + 200);
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="research › simulation engine"
        title="Simulation Engine"
        description="Backtests históricos, replay tick-by-tick, Monte Carlo e stress tests com slippage e taxas realistas."
        actions={
          <>
            <Dialog open={paramsOpen} onOpenChange={setParamsOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5"><Sliders className="h-4 w-4" />Parâmetros</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Parâmetros de simulação</DialogTitle>
                  <DialogDescription>Configuração aplicada à próxima execução.</DialogDescription>
                </DialogHeader>
                <div className="space-y-5 py-2">
                  <div>
                    <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Estratégia</label>
                    <Input value={strategy} onChange={(e) => setStrategy(e.target.value)} className="mt-1 font-mono" />
                  </div>
                  <div>
                    <div className="flex justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground"><span>Slippage</span><span>{slippage[0]} bp</span></div>
                    <Slider value={slippage} onValueChange={setSlippage} min={0} max={20} step={1} className="mt-2" />
                  </div>
                  <div>
                    <div className="flex justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground"><span>Fees</span><span>{fees[0]} bps</span></div>
                    <Slider value={fees} onValueChange={setFees} min={0} max={20} step={1} className="mt-2" />
                  </div>
                  <div>
                    <div className="flex justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground"><span>Monte Carlo trials</span><span>{trials[0]}k</span></div>
                    <Slider value={trials} onValueChange={setTrials} min={1} max={50} step={1} className="mt-2" />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="ghost" onClick={() => setParamsOpen(false)}>Fechar</Button>
                  <Button onClick={() => { setParamsOpen(false); toast.success("Parâmetros salvos"); }}>Salvar</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <Button size="sm" className="gap-1.5" onClick={runSim} disabled={running > 0}>
              <Play className="h-4 w-4" />{running > 0 ? `Rodando ${running}%` : "Rodar simulação"}
            </Button>
          </>
        }
      />

      {running > 0 && <Progress value={running} className="h-0.5 mb-4 rounded-full" />}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <Stat label="Sharpe" value={selected.sharpe.toFixed(2)} tone="pos" delta="benchmark 0.62" />
        <Stat label="Max Drawdown" value={`−${selected.dd.toFixed(1)}%`} tone="neutral" hint="cap −10%" />
        <Stat label="Hit Rate" value={`${Math.round(selected.hitRate * 100)}%`} />
        <Stat label="Expectancy" value={fmtMoney(selected.pnl / Math.max(selected.trades, 1))} delta="por trade" tone="pos" />
        <Stat label="P&L total" value={fmtMoney(selected.pnl)} delta={selected.pnl >= 0 ? `+${(selected.pnl / 1000).toFixed(1)}k` : `${(selected.pnl / 1000).toFixed(1)}k`} tone={selected.pnl >= 0 ? "pos" : "neg"} />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title={`Equity simulada · ${selected.strategy}`} subtitle={`${selected.period} · slippage ${slippage[0]}bp · fees ${fees[0]}bps`}>
          <div className="h-[300px] p-3">
            <ResponsiveContainer>
              <AreaChart data={realEquity || equityCurve}>
                <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="oklch(0.78 0.17 75)" stopOpacity={0.4} /><stop offset="100%" stopColor="oklch(0.78 0.17 75)" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip {...tt} />
                <Area type="monotone" dataKey="equity" stroke="oklch(0.78 0.17 75)" strokeWidth={2} fill="url(#sg)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="Distribuição de retornos" subtitle={`Monte Carlo · ${trials[0]}k trials`}>
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

        <Panel className="col-span-12" title="Histórico de runs" subtitle="clique em uma linha para inspecionar" actions={
          <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => { setStrategy(selected.strategy); runSim(); }} disabled={running > 0}>
            <Repeat className="h-4 w-4" />Re-rodar
          </Button>
        }>
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Run</th>
                <th className="text-left px-4 py-2">Estratégia</th>
                <th className="text-left px-4 py-2">Período</th>
                <th className="text-right px-4 py-2">Sharpe</th>
                <th className="text-right px-4 py-2">DD</th>
                <th className="text-right px-4 py-2">Trades</th>
                <th className="text-right px-4 py-2">Hit</th>
                <th className="text-right px-4 py-2">P&L</th>
                <th className="text-left px-4 py-2">Resultado</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {runs.map((r) => {
                const active = r.id === selectedId;
                return (
                  <tr key={r.id} onClick={() => setSelectedId(r.id)} className={`border-b border-border/40 last:border-0 cursor-pointer transition-colors ${active ? "bg-primary/5" : "hover:bg-muted/30"}`}>
                    <td className="px-4 py-3"><Mono className={active ? "text-primary" : "text-muted-foreground"}>{r.id}</Mono></td>
                    <td className="px-4 py-3 text-foreground">{r.strategy}</td>
                    <td className="px-4 py-3 text-muted-foreground">{r.period}</td>
                    <td className="px-4 py-3 text-right">{r.sharpe.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-warning">{r.dd.toFixed(1)}%</td>
                    <td className="px-4 py-3 text-right">{r.trades}</td>
                    <td className="px-4 py-3 text-right">{Math.round(r.hitRate * 100)}%</td>
                    <td className={`px-4 py-3 text-right ${r.pnl >= 0 ? "text-pos" : "text-neg"}`}>{fmtMoney(r.pnl)}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={`uppercase text-[10px] tracking-wider ${
                        r.status === "passed" ? "border-success/40 text-success bg-success/10" :
                        r.status === "warning" ? "border-warning/40 text-warning bg-warning/10" :
                        "border-destructive/40 text-destructive bg-destructive/10"
                      }`}>{r.status}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
