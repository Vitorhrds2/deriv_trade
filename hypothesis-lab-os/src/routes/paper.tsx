import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, ConceptBanner } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { equityCurve, fmtMoney, trades } from "@/lib/mock-data";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Trophy } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/paper")({
  head: () => ({ meta: [{ title: "Paper Trading — TradeLab OS" }] }),
  component: PaperPage,
});

const tt = { contentStyle: { background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12, fontFamily: "JetBrains Mono" } };

const leaderboard = [
  { rank: 1, name: "poly_kshi_arb",        owner: "tomas.k",  pnl: 12_140.7, sharpe: 3.47, trades: 1244 },
  { rank: 2, name: "cpi_btc_long_v3",      owner: "lucas.q",  pnl:  4_820.3, sharpe: 2.14, trades:  184 },
  { rank: 3, name: "eth_funding_revert",   owner: "marina.r", pnl:  2_104.8, sharpe: 1.78, trades:  312 },
  { rank: 4, name: "ng_weather_squeeze",   owner: "tomas.k",  pnl:    870.1, sharpe: 0.74, trades:    9 },
  { rank: 5, name: "fomc_steepener",       owner: "marina.r", pnl:   -312.4, sharpe: 0.91, trades:   67 },
];

function PaperPage() {
  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › paper trading"
        title="Paper Trading"
        description="Preview de UI para uma conta paper isolada por estratégia. Não existe hoje — o hft_bot roda direto em conta demo Deriv (que já é sem risco financeiro real)."
        actions={<Button size="sm" onClick={() => toast.info("Conceito — sem contas paper isoladas implementadas ainda.")}>Nova conta paper</Button>}
      />

      <ConceptBanner>
        Leaderboard, equity e tape abaixo são ilustrativos (traders/estratégias fictícios). O ecossistema real não tem contas paper separadas por estratégia — hoje é um bot, uma conta demo Deriv.
      </ConceptBanner>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Conta paper" value={fmtMoney(112_882.3)} delta="+12.88%" tone="pos" />
        <Stat label="Bots ativos" value="3" hint="de 5 configurados" />
        <Stat label="P&L semana" value={fmtMoney(4_120.5)} tone="pos" delta="+3.81%" />
        <Stat label="Conversão paper→live" value="62%" delta="estratégias aprovadas" tone="pos" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Equity simulado · helios-paper-01">
          <div className="h-[280px] p-3">
            <ResponsiveContainer>
              <AreaChart data={equityCurve}>
                <defs>
                  <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="oklch(0.72 0.14 230)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="oklch(0.72 0.14 230)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip {...tt} />
                <Area type="monotone" dataKey="equity" stroke="oklch(0.72 0.14 230)" strokeWidth={2} fill="url(#pg)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title={<div className="flex items-center gap-2"><Trophy className="h-4 w-4 text-accent" />Leaderboard interno</div>} subtitle="Estratégias do workspace em paper">
          <ul className="divide-y divide-border/60">
            {leaderboard.map((s) => (
              <li key={s.name} className="px-4 py-3 flex items-center gap-3">
                <div className={`w-7 h-7 rounded-md grid place-items-center font-mono text-xs ${s.rank === 1 ? "bg-accent/20 text-accent" : "bg-muted text-muted-foreground"}`}>{s.rank}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{s.name}</div>
                  <div className="text-[11px] text-muted-foreground font-mono">@{s.owner} · {s.trades} trades</div>
                </div>
                <div className="text-right font-mono text-xs">
                  <div className={s.pnl >= 0 ? "text-pos" : "text-neg"}>{fmtMoney(s.pnl)}</div>
                  <div className="text-muted-foreground">SR {s.sharpe.toFixed(2)}</div>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel className="col-span-12" title="Tape paper · execuções simuladas">
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
            {trades.map((t) => (
              <div key={t.id} className="grid grid-cols-12 px-4 py-2 border-b border-border/30 hover:bg-muted/30">
                <div className="col-span-2 text-muted-foreground">{t.time}</div>
                <div className="col-span-2 truncate">{t.bot}</div>
                <div className="col-span-2">{t.symbol}</div>
                <div className={`col-span-1 ${t.side === "BUY" ? "text-pos" : "text-neg"}`}>{t.side}</div>
                <div className="col-span-1 text-right">{t.qty}</div>
                <div className="col-span-2 text-right">{t.price.toLocaleString()}</div>
                <div className="col-span-1 text-right text-muted-foreground">{t.venue}</div>
                <div className={`col-span-1 text-right ${t.pnl > 0 ? "text-pos" : t.pnl < 0 ? "text-neg" : "text-muted-foreground"}`}>{t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(1)}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
