import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { fmtMoney } from "@/lib/mock-data";
import { getHftStatus, getHftTrades, isHftLive } from "@/lib/hft-api";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { OctagonX } from "lucide-react";
import { useApp } from "@/lib/store";
import { useQuery } from "@tanstack/react-query";

export const Route = createFileRoute("/risk")({
  head: () => ({ meta: [{ title: "Risk Engine — TradeLab OS" }] }),
  component: RiskPage,
});

// Constantes reais lidas de trading-engine/hft_arbitrage_bot.py (V6.2 Ultra-Momentum).
// Atualizar manualmente se o script mudar — não há endpoint que exponha config hoje.
const REAL_LIMITS = [
  { name: "Stake por trade",       value: "$10.00 fixo",     note: "STAKE, sem sizing dinâmico" },
  { name: "Multiplier",            value: "800x",            note: "cryBTCUSD (Deriv)" },
  { name: "Take profit",           value: "80% do stake (~$8)", note: "TAKE_PROFIT_PCT" },
  { name: "Stop loss",             value: "25% do stake (~$2.50)", note: "STOP_LOSS_PCT — fechamentos reais historicamente piores (slippage), ver hft_v62_audit_report.md" },
  { name: "Force-close (failsafe)", value: "30 min",          note: "SAFETY_TIMEOUT, rede de segurança de última instância" },
  { name: "Janela de operação",    value: "12:00–18:00 UTC", note: "golden hour — fora disso o bot só monitora, não dispara" },
];

function RiskPage() {
  const setKillOpen = useApp((s) => s.setKillOpen);
  const notifs = useApp((s) => s.notifs);
  const statusQuery = useQuery({ queryKey: ["hft-status"], queryFn: () => getHftStatus(), refetchInterval: 5000 });
  const tradesQuery = useQuery({ queryKey: ["hft-trades"], queryFn: () => getHftTrades(), refetchInterval: 5000 });
  const status = statusQuery.data;
  const trades = tradesQuery.data;
  const isLive = status ? isHftLive(status) : false;

  const abSplit = [
    { name: "ALIGNED", value: trades?.aligned.n ?? 0 },
    { name: "ANTI", value: trades?.anti.n ?? 0 },
  ];

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › risk engine"
        title="Risk Engine"
        description="Configuração de risco real do único bot em produção (hft_arbitrage_bot.py). Um bot, uma posição por vez, conta demo — sem portfolio multi-estratégia."
        actions={
          <Button variant="destructive" size="sm" className="gap-1.5" onClick={() => setKillOpen(true)}>
            <OctagonX className="h-4 w-4" />Kill switch (dashboard)
          </Button>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <Stat label="Stake configurado" value="$10.00" hint="fixo, por trade" />
        <Stat
          label="PnL acumulado"
          value={trades ? fmtMoney(trades.total.pnlTotal) : "—"}
          tone={trades && trades.total.pnlTotal < 0 ? "neg" : "neutral"}
        />
        <Stat label="Win rate" value={trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"} hint={`N=${trades?.total.n ?? 0}`} />
        <Stat
          label="hft_bot"
          value={statusQuery.isLoading ? "…" : isLive ? "ao vivo" : "offline"}
          tone={statusQuery.isLoading ? "neutral" : isLive ? "pos" : "neg"}
        />
        <Stat
          label="Downtime golden hour (hoje)"
          value={status ? `${Math.round(status.goldenHourDowntime.secondsToday)}s` : "—"}
          tone={status && status.goldenHourDowntime.secondsToday > 0 ? "neg" : "neutral"}
          delta={status ? `${status.goldenHourDowntime.eventsToday} evento(s)` : undefined}
          hint={status ? `total: ${Math.round(status.goldenHourDowntime.secondsTotal)}s` : undefined}
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Configuração de risco (real)" subtitle="constantes do script, não limites dinâmicos">
          <ul className="divide-y divide-border/60">
            {REAL_LIMITS.map((l) => (
              <li key={l.name} className="px-4 py-4 grid grid-cols-12 gap-3 items-center">
                <div className="col-span-4 text-sm">{l.name}</div>
                <div className="col-span-3 text-right font-mono text-sm">{l.value}</div>
                <div className="col-span-5 text-[11px] text-muted-foreground">{l.note}</div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="Shadow A/B — split real" subtitle="ALIGNED vs ANTI, sorteio 50/50">
          <div className="h-[220px] p-3">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={abSplit} dataKey="value" innerRadius={55} outerRadius={90} paddingAngle={3} strokeWidth={0}>
                  {abSplit.map((_, i) => <Cell key={i} fill={`var(--chart-${i + 1})`} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="px-4 pb-4 flex justify-center gap-4 text-xs font-mono text-muted-foreground">
            <span>ALIGNED N={trades?.aligned.n ?? 0}</span>
            <span>ANTI N={trades?.anti.n ?? 0}</span>
          </div>
        </Panel>

        <Panel className="col-span-12" title="Alertas (reais)" subtitle="gerados por useHftAlerts + kill switch — sem eventos fabricados">
          <ul className="divide-y divide-border/60 font-mono text-xs">
            {notifs.length === 0 && (
              <li className="px-4 py-8 text-center text-muted-foreground">Nenhum alerta até agora.</li>
            )}
            {notifs.map((n) => (
              <li key={n.id} className="px-4 py-3 flex items-center gap-3">
                <Mono className="text-muted-foreground w-16">{n.time}</Mono>
                <Badge variant="outline" className={`uppercase text-[10px] ${n.kind === "error" ? "border-destructive/40 text-destructive bg-destructive/10" : n.kind === "warn" ? "border-warning/40 text-warning bg-warning/10" : n.kind === "success" ? "border-success/40 text-success bg-success/10" : "border-info/40 text-info bg-info/10"}`}>{n.kind}</Badge>
                <span className="flex-1 text-foreground/90">{n.title}{n.desc ? ` — ${n.desc}` : ""}</span>
                <Dot tone={n.kind === "error" ? "neg" : n.kind === "warn" ? "warn" : n.kind === "success" ? "pos" : "info"} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
