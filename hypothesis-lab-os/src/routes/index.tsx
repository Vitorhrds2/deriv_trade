import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Dot, Mono } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fmtMoney } from "@/lib/mock-data";
import { getHftStatus, getHftTrades, type HftTrade } from "@/lib/hft-api";
import { realHypotheses, hypStatusBadgeClass } from "@/lib/hypotheses-data";
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
import { ArrowUpRight, FlaskConical, Plug, Workflow } from "lucide-react";
import { useApp } from "@/lib/store";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Command Center — TradeLab OS" },
      { name: "description", content: "Visão geral em tempo real do ecossistema Mega Brain." },
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

function cumulativeEquity(trades: HftTrade[]) {
  let running = 0;
  return trades.map((t, i) => {
    running += t.profit ?? 0;
    return { t: `#${i + 1}`, equity: +running.toFixed(2), zero: 0 };
  });
}

const REAL_FEEDS = [
  { name: "Deriv", role: "corretora (execução)" },
  { name: "Binance", role: "feed de preço" },
  { name: "Coinbase", role: "feed de preço" },
  { name: "Kraken", role: "feed de preço" },
] as const;

function CommandCenter() {
  const killed = useApp((s) => s.killed);

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
  const isLive = !!status?.connected && status.tmuxSessionAlive && !status.logStale;

  const equityData = useMemo(() => cumulativeEquity(trades?.recentTrades ?? []), [trades]);
  const perTradeBars = useMemo(
    () => (trades?.recentTrades ?? []).slice(-20).map((t, i) => ({ i: i + 1, pnl: t.profit ?? 0 })),
    [trades],
  );
  const abSplit = useMemo(
    () => [
      { name: "ALIGNED", value: trades?.aligned.n ?? 0 },
      { name: "ANTI", value: trades?.anti.n ?? 0 },
    ],
    [trades],
  );
  const recentTape = (trades?.recentTrades ?? []).slice().reverse().slice(0, 6);
  const validatingHyp = realHypotheses.filter((h) => h.status === "validating").length;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="workspace › command center"
        title="Command Center"
        description={
          killed
            ? "Kill switch ATIVO no dashboard — retome no topo da tela (afeta apenas o estado da UI, não há API de controle remoto do hft_bot ainda)."
            : `${realHypotheses.length} hipóteses catalogadas (${validatingHyp} em validação) · hft_bot rodando em shadow A/B na Deriv (conta demo).`
        }
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to="/hypotheses"><FlaskConical className="h-4 w-4" />Hipóteses</Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat
          label="PnL acumulado (hft_bot)"
          value={trades ? <span className="tabular-nums">{fmtMoney(trades.total.pnlTotal)}</span> : "—"}
          tone={trades && trades.total.pnlTotal < 0 ? "neg" : "neutral"}
          hint="conta demo Deriv"
        />
        <Stat
          label="Win rate"
          value={trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"}
          hint={`N=${trades?.total.n ?? 0}`}
        />
        <Stat
          label="Hipóteses catalogadas"
          value={realHypotheses.length}
          hint={`${validatingHyp} em validação`}
        />
        <Stat
          label="hft_bot"
          value={statusQuery.isLoading ? "…" : isLive ? "ao vivo" : "offline"}
          tone={statusQuery.isLoading ? "neutral" : isLive ? "pos" : "neg"}
          hint="único bot em produção"
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          title="Equity real vs. null (EV=0)"
          subtitle="soma cumulativa do profit de cada trade fechada do hft_bot, na ordem em que ocorreram."
          className="col-span-12 xl:col-span-8"
        >
          <div className="h-[280px] p-3">
            {equityData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityData}>
                  <defs>
                    <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"  stopColor="oklch(0.65 0.22 25)" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="oklch(0.65 0.22 25)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                  <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
                  <Tooltip {...chartTooltip} />
                  <Area type="monotone" dataKey="zero" stroke="oklch(0.62 0.018 240)" strokeDasharray="3 3" fill="transparent" isAnimationActive={false} />
                  <Area type="monotone" dataKey="equity" stroke="oklch(0.65 0.22 25)" strokeWidth={2} fill="url(#g1)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                {tradesQuery.isLoading ? "carregando…" : "Sem trades ainda, ou API inacessível."}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Shadow A/B — ALIGNED vs ANTI" subtitle="split real de trades por grupo do teste." className="col-span-12 md:col-span-6 xl:col-span-4">
          <div className="h-[280px] grid grid-cols-2 items-center gap-2 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={abSplit} dataKey="value" innerRadius={50} outerRadius={85} paddingAngle={3} strokeWidth={0}>
                  {abSplit.map((_, i) => (
                    <Cell key={i} fill={`var(--chart-${i + 1})`} />
                  ))}
                </Pie>
                <Tooltip {...chartTooltip} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="space-y-2 text-xs font-mono">
              {abSplit.map((r, i) => (
                <li key={r.name} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-sm" style={{ background: `var(--chart-${i + 1})` }} />
                    {r.name}
                  </span>
                  <span className="text-muted-foreground">N={r.value}</span>
                </li>
              ))}
            </ul>
          </div>
          {trades && trades.anti.n === 0 && (
            <p className="px-4 pb-3 text-[11px] text-muted-foreground">
              Amostra ANTI ainda vazia — sinal é raro (restrito ao horário de ouro 12-18 UTC).
            </p>
          )}
        </Panel>

        <Panel title="P&L por trade (últimas 20)" subtitle="profit real de cada trade fechada, em ordem." className="col-span-12 md:col-span-6 xl:col-span-4">
          <div className="h-[220px] p-3">
            {perTradeBars.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={perTradeBars}>
                  <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                  <XAxis dataKey="i" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                  <Tooltip {...chartTooltip} />
                  <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                    {perTradeBars.map((p, i) => (
                      <Cell key={i} fill={p.pnl >= 0 ? "oklch(0.78 0.18 150)" : "oklch(0.65 0.22 25)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                Sem trades ainda.
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title={<div className="flex items-center gap-2">hft_bot <Mono className="text-muted-foreground">({isLive ? "1 rodando" : "0 rodando"})</Mono></div>}
          className="col-span-12 xl:col-span-8"
          actions={<Button size="sm" variant="outline" asChild><Link to="/bots"><Workflow className="h-4 w-4" />Orquestrar</Link></Button>}
        >
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <tr className="border-b border-border/70">
                <th className="text-left px-4 py-2">Bot</th>
                <th className="text-left px-4 py-2">Ambiente</th>
                <th className="text-left px-4 py-2">Estado</th>
                <th className="text-right px-4 py-2">Trades (N)</th>
                <th className="text-right px-4 py-2">Win rate</th>
                <th className="text-right px-4 py-2">PnL</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              <tr className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors">
                <td className="px-4 py-2.5">
                  <Link to="/bots" className="flex items-center gap-2 hover:text-primary transition-colors">
                    <Dot tone={statusQuery.isLoading ? "muted" : isLive ? "pos" : "neg"} className={isLive ? "animate-pulse" : ""} />
                    <span>hft_bot</span>
                  </Link>
                </td>
                <td className="px-4 py-2.5 uppercase text-[10px] tracking-wider text-muted-foreground">demo</td>
                <td className="px-4 py-2.5">
                  <Badge variant="outline" className={isLive ? "bg-success/15 text-success border-success/30 uppercase text-[10px] font-mono tracking-wider" : "bg-destructive/15 text-destructive border-destructive/40 uppercase text-[10px] font-mono tracking-wider"}>
                    {statusQuery.isLoading ? "…" : isLive ? "rodando" : "parado"}
                  </Badge>
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">{trades?.total.n ?? "—"}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"}</td>
                <td className={`px-4 py-2.5 text-right tabular-nums ${trades && trades.total.pnlTotal < 0 ? "text-neg" : "text-muted-foreground"}`}>{trades ? fmtMoney(trades.total.pnlTotal) : "—"}</td>
              </tr>
            </tbody>
          </table>
          <div className="px-4 py-3 text-[11px] text-muted-foreground border-t border-border/60">
            Único bot em produção hoje. 60+ scripts exploratórios em <Mono>trading-engine/</Mono> não deployados — ver <Link to="/bots" className="underline hover:text-primary">Bot Orchestrator</Link>.
          </div>
        </Panel>

        <Panel title="Feeds & conexões" className="col-span-12 md:col-span-6 xl:col-span-4" actions={<Button size="sm" variant="ghost" asChild><Link to="/brokers">Gerenciar <ArrowUpRight className="h-3.5 w-3.5" /></Link></Button>}>
          <ul className="divide-y divide-border/60">
            {REAL_FEEDS.map((b) => (
              <li key={b.name} className="px-4 py-3 flex items-center gap-3 hover:bg-muted/30 transition-colors">
                <Dot tone={statusQuery.isLoading ? "muted" : isLive ? "pos" : "neg"} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm flex items-center gap-2">
                    {b.name}
                    <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{b.role}</span>
                  </div>
                </div>
                <div className="text-right font-mono text-xs text-muted-foreground">
                  {statusQuery.isLoading ? "…" : isLive ? "conectado" : "instável"}
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title={<div className="flex items-center gap-2">
            Tape — trades reais recentes
            {isLive && <Badge variant="outline" className="font-mono text-[10px] border-success/40 text-success bg-success/10 gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />live
            </Badge>}
          </div>}
          subtitle="últimas execuções fechadas do hft_bot (Deriv, conta demo)."
          className="col-span-12 xl:col-span-8"
          actions={<Button size="sm" variant="ghost" className="gap-1.5" asChild><Link to="/live">Ver tape completo <ArrowUpRight className="h-3.5 w-3.5" /></Link></Button>}
        >
          <div className="font-mono text-xs">
            <div className="grid grid-cols-12 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <div className="col-span-3">hora</div>
              <div className="col-span-2">direção</div>
              <div className="col-span-2">grupo</div>
              <div className="col-span-2 text-right">salto</div>
              <div className="col-span-3 text-right">p&l</div>
            </div>
            {recentTape.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-muted-foreground">
                {tradesQuery.isLoading ? "carregando…" : "Sem trades reais ainda, ou API inacessível."}
              </div>
            ) : (
              recentTape.map((t, i) => (
                <div key={t.contractId ?? i} className="grid grid-cols-12 px-4 py-2 border-b border-border/30 last:border-0 hover:bg-muted/30">
                  <div className="col-span-3 text-muted-foreground">{t.ts ?? "—"}</div>
                  <div className={`col-span-2 ${t.direction === "UP" ? "text-pos" : "text-neg"}`}>{t.direction}</div>
                  <div className="col-span-2">{t.group}</div>
                  <div className="col-span-2 text-right tabular-nums">{t.jump.toFixed(2)}</div>
                  <div className={`col-span-3 text-right tabular-nums ${(t.profit ?? 0) > 0 ? "text-pos" : (t.profit ?? 0) < 0 ? "text-neg" : "text-muted-foreground"}`}>{t.profit != null ? fmtMoney(t.profit) : "—"}</div>
                </div>
              ))
            )}
          </div>
        </Panel>

        <Panel title="Eventos de mercado" subtitle="calendário macro/on-chain." className="col-span-12 md:col-span-6 xl:col-span-4">
          <div className="px-4 py-8 text-sm text-muted-foreground flex items-start gap-2">
            <Plug className="h-4 w-4 shrink-0 mt-0.5" />
            <span>Nenhum feed de eventos (macro/earnings/on-chain) implementado ainda. O ecossistema hoje reage só a choques de preço em tempo real — ver <Link to="/events" className="underline hover:text-primary">Event Layer</Link>.</span>
          </div>
        </Panel>

        <Panel
          title={<div className="flex items-center gap-2">Catálogo de hipóteses <Mono className="text-muted-foreground">({realHypotheses.length} testadas)</Mono></div>}
          className="col-span-12"
          actions={<Button size="sm" variant="ghost" asChild><Link to="/hypotheses">Ver todas <ArrowUpRight className="h-3.5 w-3.5" /></Link></Button>}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 p-3">
            {realHypotheses.slice(0, 3).map((h) => (
              <Link
                key={h.id}
                to="/hypotheses"
                onClick={() => useApp.getState().selectHyp(h.id)}
                className="rounded-md border bg-background/50 p-4 hover:border-primary/40 hover:bg-muted/30 transition-all block"
              >
                <div className="flex items-start justify-between gap-2">
                  <Mono className="text-muted-foreground">{h.id}</Mono>
                  <Badge variant="outline" className={`${hypStatusBadgeClass(h.status)} text-[10px] font-mono uppercase tracking-wider`}>{h.status}</Badge>
                </div>
                <div className="mt-2 font-medium leading-snug">{h.title}</div>
                <div className="mt-1 text-xs text-muted-foreground line-clamp-2">{h.verdict}</div>
                <div className="mt-3 flex items-center gap-2 text-[11px] font-mono">
                  <span className="text-muted-foreground">conf.</span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div style={{ width: `${h.confidence}%` }} className="h-full bg-gradient-to-r from-primary to-accent" />
                  </div>
                  <span>{h.confidence}%</span>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs">
                  <span className="font-mono text-muted-foreground">N={h.trades}</span>
                  <span className="text-muted-foreground truncate max-w-[60%]">{h.sampleUnit}</span>
                </div>
              </Link>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
