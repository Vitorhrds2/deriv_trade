import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Dot, Mono } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fmtMoney } from "@/lib/mock-data";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Unlock,
  Activity,
  RefreshCw,
  Clock,
  Server,
  Cpu,
} from "lucide-react";
import { getUnlockStatus, getUnlockTrades, getUnlockSchedule } from "@/lib/unlock-api";
import { getHftStatus, getHftTrades, isHftLive } from "@/lib/hft-api";

export const Route = createFileRoute("/paper")({
  head: () => ({ meta: [{ title: "Paper Trading — TradeLab OS" }] }),
  component: PaperPage,
});

const tt = {
  contentStyle: {
    background: "oklch(0.20 0.014 240)",
    border: "1px solid oklch(0.28 0.014 240)",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "JetBrains Mono, monospace",
  },
  labelStyle: { color: "oklch(0.62 0.018 240)" },
};

function PaperPage() {
  const unlockStatusQ = useQuery({
    queryKey: ["unlock-status"],
    queryFn: () => getUnlockStatus(),
    refetchInterval: 10000,
  });
  const unlockTradesQ = useQuery({
    queryKey: ["unlock-trades"],
    queryFn: () => getUnlockTrades(),
    refetchInterval: 15000,
  });
  const unlockScheduleQ = useQuery({
    queryKey: ["unlock-schedule"],
    queryFn: () => getUnlockSchedule(),
    refetchInterval: 30000,
  });
  const hftStatusQ = useQuery({
    queryKey: ["hft-status"],
    queryFn: () => getHftStatus(),
    refetchInterval: 5000,
  });
  const hftTradesQ = useQuery({
    queryKey: ["hft-trades"],
    queryFn: () => getHftTrades(),
    refetchInterval: 5000,
  });

  const unlockStatus = unlockStatusQ.data;
  const unlockTrades = unlockTradesQ.data;
  const unlockSchedule = unlockScheduleQ.data;
  const hftStatus = hftStatusQ.data;
  const hftTrades = hftTradesQ.data;

  const unlockConnected = unlockStatus?.connected ?? false;
  const unlockRunning = unlockStatus?.tmux_session_alive ?? false;
  const hftConnected = hftStatus?.connected ?? false;
  const hftRunning = isHftLive(hftStatus ?? { connected: false, tmuxSessionAlive: false });

  const equityCurve = unlockTrades?.equity_curve ?? [{ trade: 0, equity: 10000 }];
  const finalEquity = unlockTrades?.final_equity ?? 10000;
  const totalReturn = unlockTrades?.total_return_pct ?? 0;
  const upcoming = unlockSchedule?.upcoming ?? [];
  const unlockPositions = unlockStatus?.open_positions ?? [];
  const allUnlockTrades = unlockTrades?.trades ?? [];
  const hftRecentTrades = hftTrades?.recentTrades ?? [];

  const allBots = [
    {
      name: "D17 Unlock Short",
      icon: Unlock,
      connected: unlockConnected,
      running: unlockRunning,
      mode: "paper",
      equity: finalEquity,
      totalReturn,
      positions: unlockPositions.length,
      closedTrades: allUnlockTrades.length,
      pnl: unlockStatus?.total_pnl ?? 0,
      winRate: unlockStatus?.win_rate ?? 0,
      lastCheck: unlockStatus?.last_check,
      link: "/d17" as const,
    },
    {
      name: "HFT Arbitrage V6.2",
      icon: Activity,
      connected: hftConnected,
      running: hftRunning,
      mode: "demo",
      equity: null,
      totalReturn: null,
      positions: 0,
      closedTrades: hftTrades?.total?.n ?? 0,
      pnl: hftTrades?.total?.pnlTotal ?? 0,
      winRate: hftTrades?.total?.winRate ? hftTrades.total.winRate * 100 : 0,
      lastCheck: null,
      link: "/live" as const,
    },
  ];

  const activeBots = allBots.filter((b) => b.running).length;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › paper trading"
        title="Paper Trading"
        description="Bots rodando em paper/demo mode na AWS EC2 (18.199.174.178). Dados em tempo real via status_api."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                unlockStatusQ.refetch();
                unlockTradesQ.refetch();
                unlockScheduleQ.refetch();
                hftStatusQ.refetch();
                hftTradesQ.refetch();
              }}
            >
              <RefreshCw className={`h-4 w-4 ${unlockStatusQ.isFetching || hftStatusQ.isFetching ? "animate-spin" : ""}`} />
              Atualizar
            </Button>
          </div>
        }
      />

      {/* ─── Connection status ──────────────────────────────────────────── */}
      <div className="mb-6 grid grid-cols-1 md:grid-cols-2 gap-3">
        {allBots.map((bot) => {
          const Icon = bot.icon;
          return (
            <div key={bot.name} className="rounded-lg border bg-card p-4 flex items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10">
                <Icon className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{bot.name}</span>
                  <Badge variant="outline" className="text-[10px] font-mono uppercase">{bot.mode}</Badge>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <Dot tone={bot.running ? "pos" : bot.connected ? "warn" : "neg"} className={bot.running ? "animate-pulse" : ""} />
                  <span className="text-xs text-muted-foreground">
                    {!bot.connected
                      ? "API desconectada"
                      : !bot.running
                        ? "API conectada — bot parado"
                        : "Bot ativo"}
                  </span>
                  {bot.lastCheck && (
                    <span className="text-[10px] text-muted-foreground font-mono ml-auto">
                      <Clock className="inline h-3 w-3 mr-0.5" />
                      {new Date(bot.lastCheck).toLocaleString("pt-BR")}
                    </span>
                  )}
                </div>
              </div>
              <Link to={bot.link}>
                <Button variant="ghost" size="sm" className="text-xs">Ver dashboard →</Button>
              </Link>
            </div>
          );
        })}
      </div>

      {/* ─── Top stats ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat
          label="Bots ativos"
          value={activeBots}
          hint={`${allBots.length} configurados`}
          tone={activeBots > 0 ? "pos" : "neg"}
        />
        <Stat
          label="D17 Equity"
          value={fmtMoney(finalEquity)}
          delta={`${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(1)}%`}
          tone={totalReturn > 0 ? "pos" : totalReturn < 0 ? "neg" : "neutral"}
        />
        <Stat
          label="D17 Posições abertas"
          value={unlockPositions.length}
          hint={`max ${unlockStatus?.config?.max_concurrent ?? 5}`}
          tone={unlockPositions.length > 0 ? "pos" : "neutral"}
        />
        <Stat
          label="HFT Trades (total)"
          value={hftTrades?.total?.n ?? 0}
          hint={`P&L ${fmtMoney(hftTrades?.total?.pnlTotal ?? 0)}`}
          tone={(hftTrades?.total?.pnlTotal ?? 0) > 0 ? "pos" : "neg"}
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* ─── D17 Equity Curve ─────────────────────────────────────────── */}
        <Panel
          className="col-span-12 xl:col-span-8"
          title={
            <div className="flex items-center gap-2">
              <Unlock className="h-4 w-4 text-primary" />
              D17 Equity Curve · Paper Trading
            </div>
          }
          subtitle={`$10,000 inicial → ${fmtMoney(finalEquity)} (${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(1)}%)`}
        >
          <div className="h-[280px] p-3">
            {equityCurve.length > 1 ? (
              <ResponsiveContainer>
                <AreaChart data={equityCurve}>
                  <defs>
                    <linearGradient id="paperEquity" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.72 0.14 230)" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="oklch(0.72 0.14 230)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                  <XAxis dataKey="trade" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
                  <Tooltip {...tt} />
                  <Area type="monotone" dataKey="equity" stroke="oklch(0.72 0.14 230)" strokeWidth={2} fill="url(#paperEquity)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
                <Activity className="h-8 w-8 opacity-40" />
                <p className="text-sm">Sem trades ainda — aguardando primeiro entry</p>
                <p className="text-xs font-mono">
                  Próximo: {upcoming[0]?.symbol ?? "—"} em {upcoming[0]?.entry_date ?? "—"}
                </p>
              </div>
            )}
          </div>
        </Panel>

        {/* ─── Upcoming unlocks ─────────────────────────────────────────── */}
        <Panel
          className="col-span-12 xl:col-span-4"
          title="Próximos unlocks"
          subtitle="D17 entry schedule"
        >
          <div className="max-h-[280px] overflow-y-auto">
            <ul className="divide-y divide-border/60">
              {upcoming.length === 0 && (
                <li className="px-4 py-6 text-center text-sm text-muted-foreground">
                  {unlockConnected ? "Nenhum unlock próximo" : "API desconectada"}
                </li>
              )}
              {upcoming.map((u) => (
                <li key={`${u.symbol}-${u.unlock_date}`} className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium">{u.symbol}</div>
                      <div className="text-[11px] text-muted-foreground font-mono">
                        Unlock: {u.unlock_date} · ${u.unlock_value_mm.toFixed(0)}M
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-mono text-primary">{u.entry_date}</div>
                      <div className="text-[10px] text-muted-foreground">{u.days_until}d</div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        {/* ─── D17 Open positions ───────────────────────────────────────── */}
        <Panel
          className="col-span-12 lg:col-span-6"
          title="D17 Posições abertas"
          subtitle={`${unlockPositions.length} posição(ões) · paper mode`}
        >
          {unlockPositions.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              {unlockConnected ? "Nenhuma posição aberta — aguardando entry date" : "API desconectada"}
            </div>
          ) : (
            <div className="font-mono text-xs">
              <div className="grid grid-cols-12 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border/70">
                <div className="col-span-3">símbolo</div>
                <div className="col-span-2">side</div>
                <div className="col-span-3 text-right">notional</div>
                <div className="col-span-2 text-right">entry</div>
                <div className="col-span-2 text-right">unlock</div>
              </div>
              {unlockPositions.map((p, i) => (
                <div key={i} className="grid grid-cols-12 px-4 py-2 border-b border-border/30 hover:bg-muted/30">
                  <div className="col-span-3">{p.symbol}</div>
                  <div className="col-span-2 text-neg">{p.side}</div>
                  <div className="col-span-3 text-right">{fmtMoney(p.notional)}</div>
                  <div className="col-span-2 text-right">{p.entry_price.toFixed(2)}</div>
                  <div className="col-span-2 text-right text-muted-foreground">{p.unlock_date}</div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* ─── HFT recent trades ────────────────────────────────────────── */}
        <Panel
          className="col-span-12 lg:col-span-6"
          title="HFT Trades recentes"
          subtitle={`${hftRecentTrades.length} trade(s) · demo mode`}
        >
          {hftRecentTrades.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              {hftConnected ? "Nenhum trade — 0 trades na era V6.2-final" : "API desconectada"}
            </div>
          ) : (
            <div className="font-mono text-xs">
              <div className="grid grid-cols-12 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border/70">
                <div className="col-span-3">timestamp</div>
                <div className="col-span-2">dir</div>
                <div className="col-span-2">grupo</div>
                <div className="col-span-2 text-right">jump</div>
                <div className="col-span-3 text-right">p&l</div>
              </div>
              {hftRecentTrades.slice(-20).reverse().map((t, i) => (
                <div key={i} className="grid grid-cols-12 px-4 py-2 border-b border-border/30 hover:bg-muted/30">
                  <div className="col-span-3 text-muted-foreground">{t.ts ?? "—"}</div>
                  <div className={`col-span-2 ${t.direction === "UP" ? "text-pos" : "text-neg"}`}>{t.direction}</div>
                  <div className="col-span-2 text-muted-foreground">{t.group}</div>
                  <div className="col-span-2 text-right">{t.jump.toFixed(1)}</div>
                  <div className={`col-span-3 text-right ${(t.profit ?? 0) > 0 ? "text-pos" : (t.profit ?? 0) < 0 ? "text-neg" : "text-muted-foreground"}`}>
                    {t.profit != null ? fmtMoney(t.profit) : "—"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* ─── D17 Closed trades ────────────────────────────────────────── */}
        <Panel
          className="col-span-12"
          title="D17 Trades fechadas"
          subtitle={`${allUnlockTrades.length} trade(s) · paper mode`}
        >
          {allUnlockTrades.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              {unlockConnected ? "Nenhuma trade fechada — bot aguardando primeiro entry (9 Jul: APTUSDT)" : "API desconectada"}
            </div>
          ) : (
            <div className="font-mono text-xs">
              <div className="grid grid-cols-12 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border/70">
                <div className="col-span-2">entry</div>
                <div className="col-span-2">exit</div>
                <div className="col-span-2">símbolo</div>
                <div className="col-span-1">side</div>
                <div className="col-span-2 text-right">notional</div>
                <div className="col-span-1 text-right">bps</div>
                <div className="col-span-1 text-right">reason</div>
                <div className="col-span-1 text-right">p&l</div>
              </div>
              {allUnlockTrades.slice(-50).reverse().map((t, i) => (
                <div key={i} className="grid grid-cols-12 px-4 py-2 border-b border-border/30 hover:bg-muted/30">
                  <div className="col-span-2 text-muted-foreground">{t.entry_time?.slice(0, 10)}</div>
                  <div className="col-span-2 text-muted-foreground">{t.exit_time?.slice(0, 10)}</div>
                  <div className="col-span-2">{t.symbol}</div>
                  <div className="col-span-1 text-neg">{t.side}</div>
                  <div className="col-span-2 text-right">{fmtMoney(t.notional)}</div>
                  <div className="col-span-1 text-right">{t.pnl_pct?.toFixed(0)}</div>
                  <div className="col-span-1 text-right text-muted-foreground">{t.close_reason}</div>
                  <div className={`col-span-1 text-right ${t.net_pnl > 0 ? "text-pos" : "text-neg"}`}>
                    {t.net_pnl >= 0 ? "+" : ""}{t.net_pnl.toFixed(1)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* ─── AWS server info ──────────────────────────────────────────── */}
        <Panel className="col-span-12" title={<div className="flex items-center gap-2"><Server className="h-4 w-4 text-muted-foreground" />AWS EC2 Server</div>}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">IP</div>
              <div className="text-sm font-mono mt-1">18.199.174.178</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Região</div>
              <div className="text-sm font-mono mt-1">eu-central-1</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">API Porta</div>
              <div className="text-sm font-mono mt-1">8787 (hft + unlock)</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Tmux Sessions</div>
              <div className="text-sm font-mono mt-1 flex items-center gap-1">
                <Cpu className="h-3 w-3" />
                15 ativas (hft_bot, unlock_bot, status_api, supervisor + 11 hypothesis bots)
              </div>
            </div>
          </div>
          <div className="px-4 pb-4 text-[11px] text-muted-foreground">
            Só hft_bot e unlock_bot têm API de status ao vivo (painéis acima). Os outros 11
            (D37-D41, D44, D34 liq_bot, D36 iv_anomaly, D29 basis, options/twap paper bots)
            rodam na mesma instância validando hipóteses de pesquisa, sem UI dedicada ainda —
            status real em <Mono>docs/state_of_research.md</Mono>. (D46 rodou, foi refutado com
            N=190.000 em 2026-07-06, e foi parado.)
          </div>
        </Panel>
      </div>
    </div>
  );
}
