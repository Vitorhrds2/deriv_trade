import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Dot, Mono } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  brokers,
  equityCurve,
  events,
  fmtMoney,
  hypotheses,
  pnlBars,
  riskBreakdown,
  statusBadgeClass,
  trades as seedTrades,
  type Trade,
} from "@/lib/mock-data";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowUpRight, FlaskConical, Play, Plus, Workflow } from "lucide-react";
import { useApp, liveDerivedEquity, liveDerivedPnl } from "@/lib/store";
import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Command Center — TradeLab OS" },
      { name: "description", content: "Visão geral em tempo real do workspace quantitativo." },
    ],
  }),
  component: CommandCenter,
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

const SYMS = ["BTC-PERP", "ETH-PERP", "TRUMP-YES", "EUR/USD", "NVDA", "FED-CUT-Y"] as const;
const BOTS = ["cpi-btc-prod", "poly-kshi-arb-prod", "fomc-steepener-sim"] as const;
const VENUES = ["Binance", "Polymarket", "Kalshi", "OANDA", "Alpaca"] as const;

function genTrade(seed: number): Trade {
  const sym = SYMS[seed % SYMS.length];
  const side: "BUY" | "SELL" = seed % 2 === 0 ? "BUY" : "SELL";
  const basePrice = sym === "BTC-PERP" ? 67400 : sym === "ETH-PERP" ? 3120 : sym === "EUR/USD" ? 1.083 : sym === "NVDA" ? 940 : 0.6;
  const price = +(basePrice + (Math.sin(seed) * basePrice * 0.001)).toFixed(sym === "EUR/USD" ? 4 : 2);
  const qty = +(Math.abs(Math.sin(seed)) * (sym === "BTC-PERP" ? 0.5 : sym === "ETH-PERP" ? 4 : 800) + 0.1).toFixed(2);
  return {
    id: `T-${10000 + seed}`,
    bot: BOTS[seed % BOTS.length],
    side,
    symbol: sym,
    qty,
    price,
    pnl: +(Math.sin(seed * 1.7) * 120).toFixed(1),
    time: new Date().toLocaleTimeString("en-US", { hour12: false }),
    venue: VENUES[seed % VENUES.length],
  };
}

function CommandCenter() {
  const tick = useApp((s) => s.tick);
  const bots = useApp((s) => s.bots);
  const killed = useApp((s) => s.killed);
  const pushNotif = useApp((s) => s.pushNotif);

  // Live equity feed (rolling window)
  const [tf, setTf] = useState<"1D" | "30D" | "60D" | "YTD">("60D");
  const tfScale = tf === "1D" ? 0.3 : tf === "30D" ? 0.75 : tf === "YTD" ? 1.4 : 1;

  // Live equity feed (rolling window)
  const liveEquity = useMemo(() => {
    return equityCurve.map((p, i) => ({
      ...p,
      equity: p.equity * tfScale + Math.sin((i + tick) / 5) * 220,
      benchmark: p.benchmark * tfScale,
    }));
  }, [tick, tfScale]);

  // Live trade tape
  const [tape, setTape] = useState<Trade[]>(seedTrades);
  useEffect(() => {
    if (killed) return;
    const id = setInterval(() => {
      setTape((prev) => [genTrade(Math.floor(Math.random() * 9999)), ...prev].slice(0, 8));
    }, 3500);
    return () => clearInterval(id);
  }, [killed]);

  const liveBots = bots.filter((b) => b.state === "running").length;
  const liveHyp = hypotheses.filter((h) => h.status === "live").length;
  const equity = liveDerivedEquity(tick);
  const pnl = liveDerivedPnl(tick);

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="workspace › command center"
        title="Bom dia, Lucas."
        description={
          killed
            ? "Kill switch ATIVO — sistema em halt manual. Retome no topo da tela."
            : "3 hipóteses ativas, 2 bots executando ao vivo e 1 evento de alto impacto nas próximas 4h."
        }
        actions={
          <>
            <Button variant="outline" size="sm" asChild>
              <Link to="/hypotheses"><FlaskConical className="h-4 w-4" />Hipóteses</Link>
            </Button>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                pushNotif({ kind: "info", title: "Nova estratégia", desc: "STR-007 (rascunho) criada." });
                toast.success("Estratégia STR-007 criada");
              }}
              asChild
            >
              <Link to="/strategies"><Plus className="h-4 w-4" />Nova estratégia</Link>
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Equity total" value={<span className="tabular-nums">{fmtMoney(equity)}</span>} delta="+2.18% (24h)" tone="pos" hint="vs benchmark +1.12%" />
        <Stat label="P&L do dia"   value={<span className="tabular-nums">{fmtMoney(pnl)}</span>}    delta={pnl >= 0 ? "+1.82%" : "−0.42%"} tone={pnl >= 0 ? "pos" : "neg"} hint={`${tape.length * 2 + 6} trades`} />
        <Stat label="Drawdown"     value="−3.1%"                 delta="dentro do limite" tone="neutral" hint="cap: −8.0%" />
        <Stat label="Sharpe (90d)" value="2.41"                  delta="+0.14 wow"   tone="pos" hint="vol 11.4%" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          title={<div className="flex items-center gap-2">Equity vs Benchmark <Badge variant="outline" className="font-mono text-[10px] border-primary/40 text-primary bg-primary/10">{tf}</Badge></div>}
          subtitle="Performance agregada de todos os bots ativos."
          className="col-span-12 xl:col-span-8"
          actions={<>{(["1D","30D","60D","YTD"] as const).map(t => <Button key={t} variant={tf === t ? "secondary" : "ghost"} size="sm" onClick={() => setTf(t)}>{t}</Button>)}</>}
        >
          <div className="h-[280px] p-3">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={liveEquity}>
                <defs>
                  <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"  stopColor="oklch(0.85 0.18 130)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="oklch(0.85 0.18 130)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip {...chartTooltip} />
                <Area type="monotone" dataKey="benchmark" stroke="oklch(0.62 0.018 240)" strokeDasharray="3 3" fill="transparent" isAnimationActive={false} />
                <Area type="monotone" dataKey="equity"    stroke="oklch(0.85 0.18 130)" strokeWidth={2} fill="url(#g1)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Exposição por classe" subtitle="Capital alocado em %." className="col-span-12 md:col-span-6 xl:col-span-4">
          <div className="h-[280px] grid grid-cols-2 items-center gap-2 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={riskBreakdown} dataKey="value" innerRadius={50} outerRadius={85} paddingAngle={3} strokeWidth={0}>
                  {riskBreakdown.map((_, i) => (
                    <Cell key={i} fill={`var(--chart-${i + 1})`} />
                  ))}
                </Pie>
                <Tooltip {...chartTooltip} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="space-y-2 text-xs font-mono">
              {riskBreakdown.map((r, i) => (
                <li key={r.name} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-sm" style={{ background: `var(--chart-${i + 1})` }} />
                    {r.name}
                  </span>
                  <span className="text-muted-foreground">{r.value}%</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel title="P&L diário" subtitle="Últimos 14 pregões." className="col-span-12 md:col-span-6 xl:col-span-4">
          <div className="h-[220px] p-3">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pnlBars}>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="d" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                <Tooltip {...chartTooltip} />
                <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                  {pnlBars.map((p, i) => (
                    <Cell key={i} fill={p.pnl >= 0 ? "oklch(0.78 0.18 150)" : "oklch(0.65 0.22 25)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title={<div className="flex items-center gap-2">Bots em execução <Mono className="text-muted-foreground">({liveBots} de {bots.length})</Mono></div>}
          className="col-span-12 xl:col-span-8"
          actions={<Button size="sm" variant="outline" asChild><Link to="/bots"><Workflow className="h-4 w-4" />Orquestrar</Link></Button>}
        >
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <tr className="border-b border-border/70">
                <th className="text-left px-4 py-2">Bot</th>
                <th className="text-left px-4 py-2">Ambiente</th>
                <th className="text-left px-4 py-2">Estado</th>
                <th className="text-right px-4 py-2">Ordens 24h</th>
                <th className="text-right px-4 py-2">Latência</th>
                <th className="text-right px-4 py-2">Uptime</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {bots.slice(0, 5).map((b) => (
                <tr key={b.id} className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2.5">
                    <Link to="/bots" className="flex items-center gap-2 hover:text-primary transition-colors">
                      <Dot tone={b.state === "running" ? "pos" : b.state === "error" ? "neg" : b.state === "recovering" ? "warn" : "muted"} />
                      <span>{b.name}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 uppercase text-[10px] tracking-wider text-muted-foreground">{b.env}</td>
                  <td className="px-4 py-2.5">
                    <Badge variant="outline" className={`${statusBadgeClass(b.state)} uppercase text-[10px] font-mono tracking-wider`}>{b.state}</Badge>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{b.ordersToday}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{b.latencyMs ? `${b.latencyMs}ms` : "—"}</td>
                  <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">{b.uptime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Próximos eventos" subtitle="Calendário macro e on-chain monitorado." className="col-span-12 md:col-span-6 xl:col-span-4">
          <ul className="divide-y divide-border/60">
            {events.slice(0, 5).map((e) => (
              <li key={e.id} className="px-4 py-3 flex items-start gap-3 hover:bg-muted/30 transition-colors">
                <div className="font-mono text-[11px] text-muted-foreground w-16 shrink-0">{e.time}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{e.name}</div>
                  <div className="text-[11px] text-muted-foreground capitalize mt-0.5">
                    {e.kind} {e.consensus && <>· cons. <span className="text-foreground">{e.consensus}</span></>} {e.actual && e.actual !== "—" && <>· real <span className="text-pos">{e.actual}</span></>}
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={`uppercase text-[10px] font-mono ${e.impact === "high" ? "border-destructive/40 text-destructive bg-destructive/10" : e.impact === "med" ? "border-warning/40 text-warning bg-warning/10" : "border-border text-muted-foreground"}`}
                >
                  {e.impact}
                </Badge>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title={<div className="flex items-center gap-2">
            Tape — execuções recentes
            {!killed && <Badge variant="outline" className="font-mono text-[10px] border-success/40 text-success bg-success/10 gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />live
            </Badge>}
          </div>}
          subtitle="Stream em tempo real de todos os bots."
          className="col-span-12 xl:col-span-8"
          actions={<Button size="sm" variant="ghost" className="gap-1.5" asChild><Link to="/live">Ver tape completo <ArrowUpRight className="h-3.5 w-3.5" /></Link></Button>}
        >
          <div className="font-mono text-xs">
            <div className="grid grid-cols-12 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <div className="col-span-2">hora</div>
              <div className="col-span-2">bot</div>
              <div className="col-span-2">símbolo</div>
              <div className="col-span-1">side</div>
              <div className="col-span-1 text-right">qty</div>
              <div className="col-span-2 text-right">preço</div>
              <div className="col-span-1 text-right">venue</div>
              <div className="col-span-1 text-right">p&l</div>
            </div>
            <AnimatePresence initial={false}>
              {tape.map((t) => (
                <motion.div
                  key={t.id}
                  layout
                  initial={{ opacity: 0, y: -10, backgroundColor: t.pnl >= 0 ? "rgba(56,200,120,0.18)" : "rgba(220,80,60,0.18)" }}
                  animate={{ opacity: 1, y: 0, backgroundColor: "rgba(0,0,0,0)" }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.5 }}
                  className="grid grid-cols-12 px-4 py-2 border-b border-border/30 last:border-0 hover:bg-muted/30"
                >
                  <div className="col-span-2 text-muted-foreground">{t.time}</div>
                  <div className="col-span-2 truncate">{t.bot}</div>
                  <div className="col-span-2">{t.symbol}</div>
                  <div className={`col-span-1 ${t.side === "BUY" ? "text-pos" : "text-neg"}`}>{t.side}</div>
                  <div className="col-span-1 text-right tabular-nums">{t.qty}</div>
                  <div className="col-span-2 text-right tabular-nums">{t.price.toLocaleString()}</div>
                  <div className="col-span-1 text-right text-muted-foreground">{t.venue}</div>
                  <div className={`col-span-1 text-right tabular-nums ${t.pnl > 0 ? "text-pos" : t.pnl < 0 ? "text-neg" : "text-muted-foreground"}`}>{t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(1)}</div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </Panel>

        <Panel title="Saúde dos brokers" className="col-span-12 md:col-span-6 xl:col-span-4" actions={<Button size="sm" variant="ghost" asChild><Link to="/brokers">Gerenciar <ArrowUpRight className="h-3.5 w-3.5" /></Link></Button>}>
          <ul className="divide-y divide-border/60">
            {brokers.map((b) => (
              <li key={b.name} className="px-4 py-3 flex items-center gap-3 hover:bg-muted/30 transition-colors">
                <Dot tone={b.status === "connected" ? "pos" : b.status === "degraded" ? "warn" : "neg"} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm flex items-center gap-2">
                    {b.name}
                    <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{b.type}</span>
                  </div>
                  <div className="text-[11px] font-mono text-muted-foreground">{b.region}</div>
                </div>
                <div className="text-right font-mono text-xs">
                  <div className="tabular-nums">{fmtMoney(b.balance)}</div>
                  <div className="text-muted-foreground">{b.latencyMs ? `${b.latencyMs}ms` : "—"}</div>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title={<div className="flex items-center gap-2">Hipóteses em validação <Mono className="text-muted-foreground">({liveHyp} ativas)</Mono></div>}
          className="col-span-12"
          actions={<Button size="sm" variant="ghost" asChild><Link to="/hypotheses">Ver todas <ArrowUpRight className="h-3.5 w-3.5" /></Link></Button>}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 p-3">
            {hypotheses.slice(0, 3).map((h) => (
              <Link
                key={h.id}
                to="/hypotheses"
                onClick={() => useApp.getState().selectHyp(h.id)}
                className="rounded-md border bg-background/50 p-4 hover:border-primary/40 hover:bg-muted/30 transition-all block"
              >
                <div className="flex items-start justify-between gap-2">
                  <Mono className="text-muted-foreground">{h.id}</Mono>
                  <Badge variant="outline" className={`${statusBadgeClass(h.status)} text-[10px] font-mono uppercase tracking-wider`}>{h.status}</Badge>
                </div>
                <div className="mt-2 font-medium leading-snug">{h.title}</div>
                <div className="mt-1 text-xs text-muted-foreground line-clamp-2">{h.thesis}</div>
                <div className="mt-3 flex items-center gap-2 text-[11px] font-mono">
                  <span className="text-muted-foreground">conf.</span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${h.confidence}%` }} transition={{ duration: 0.9, ease: "easeOut" }} className="h-full bg-gradient-to-r from-primary to-accent" />
                  </div>
                  <span>{h.confidence}%</span>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs">
                  <span className={`font-mono ${h.pnl >= 0 ? "text-pos" : "text-neg"}`}>{fmtMoney(h.pnl)}</span>
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-primary transition-colors">
                    <Play className="h-3 w-3" />Simular
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
