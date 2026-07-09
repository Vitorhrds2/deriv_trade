import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { getUnlockSchedule, getUnlockStatus, type UpcomingUnlock } from "@/lib/unlock-api";
import { CalendarClock, Search, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fmtMoney } from "@/lib/format";

export const Route = createFileRoute("/events")({
  head: () => ({ meta: [{ title: "Event Intelligence — TradeLab OS" }] }),
  component: EventsPage,
});

function impactLevel(u: UpcomingUnlock): "high" | "med" | "low" {
  if (u.unlock_value_mm >= 200 || u.pct_supply >= 5) return "high";
  if (u.unlock_value_mm >= 50 || u.pct_supply >= 2) return "med";
  return "low";
}

function fmtDate(s: string) {
  if (!s) return "—";
  try {
    const d = new Date(s + "T00:00:00Z");
    return d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric", timeZone: "UTC" });
  } catch {
    return s;
  }
}

function EventsPage() {
  const [query, setQuery] = useState("");

  const scheduleQuery = useQuery({
    queryKey: ["unlock-schedule"],
    queryFn: () => getUnlockSchedule(),
    refetchInterval: 30000,
  });
  const statusQuery = useQuery({
    queryKey: ["unlock-status"],
    queryFn: () => getUnlockStatus(),
    refetchInterval: 10000,
  });

  const schedule = scheduleQuery.data;
  const status = statusQuery.data;
  const upcoming = schedule?.upcoming ?? [];
  const connected = schedule?.connected ?? false;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return upcoming;
    return upcoming.filter((u) =>
      u.symbol.toLowerCase().includes(q) ||
      u.source.toLowerCase().includes(q)
    );
  }, [upcoming, query]);

  const highImpact = upcoming.filter((u) => impactLevel(u) === "high").length;
  const nextEvent = upcoming.length > 0 ? upcoming[0] : null;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › event intelligence"
        title="Token Unlock Calendar"
        description="Calendário real de token unlocks (D17) — único edge validado do ecossistema. Dados via unlock_short_bot na AWS."
        actions={
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => { scheduleQuery.refetch(); statusQuery.refetch(); }}
          >
            <RefreshCw className={`h-4 w-4 ${scheduleQuery.isFetching ? "animate-spin" : ""}`} />
            Atualizar
          </Button>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat
          label="Unlocks próximos"
          value={upcoming.length}
          hint="próximos 30 dias"
        />
        <Stat
          label="Alto impacto (≥$200M)"
          value={highImpact}
          tone={highImpact > 0 ? "neg" : "neutral"}
          hint="D17: 7/7 negativos"
        />
        <Stat
          label="API status"
          value={connected ? "conectado" : "offline"}
          tone={connected ? "pos" : "neg"}
        />
        <Stat
          label="Posições abertas"
          value={status?.open_count ?? "—"}
          hint={status?.mode ? `modo ${status.mode}` : undefined}
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          className="col-span-12 xl:col-span-8"
          title="Próximos token unlocks"
          subtitle={`${filtered.length} evento${filtered.length === 1 ? "" : "s"} · fonte: TokenUnlocksApp`}
          actions={
            <div className="relative">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="filtrar símbolo…"
                className="h-8 w-44 pl-8 text-xs font-mono bg-muted/40"
              />
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            </div>
          }
        >
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Token</th>
                <th className="text-left px-4 py-2">Unlock Date</th>
                <th className="text-right px-4 py-2">Valor ($M)</th>
                <th className="text-right px-4 py-2">% Supply</th>
                <th className="text-left px-4 py-2">Entry (-3d)</th>
                <th className="text-left px-4 py-2">Exit (+3d)</th>
                <th className="text-right px-4 py-2">Dias</th>
                <th className="text-left px-4 py-2">Impacto</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {filtered.map((u, i) => {
                const imp = impactLevel(u);
                return (
                  <tr key={`${u.symbol}-${i}`} className="border-b border-border/40 last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-3 text-foreground font-medium">{u.symbol}</td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDate(u.unlock_date)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">${u.unlock_value_mm.toFixed(1)}M</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.pct_supply.toFixed(2)}%</td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDate(u.entry_date)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDate(u.exit_date)}</td>
                    <td className={`px-4 py-3 text-right tabular-nums ${u.days_until <= 3 ? "text-warning" : "text-muted-foreground"}`}>
                      {u.days_until}d
                    </td>
                    <td className="px-4 py-3">
                      <span className={`uppercase text-[10px] ${imp === "high" ? "text-destructive" : imp === "med" ? "text-warning" : "text-muted-foreground"}`}>
                        {imp}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    {scheduleQuery.isLoading ? "carregando…" : connected ? "Nenhum unlock próximo no momento." : "API inacessível."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </Panel>

        <Panel
          className="col-span-12 xl:col-span-4"
          title="D17 Strategy Status"
          subtitle="Edge validado: IS + OOS-2025 + OOS-2026"
        >
          <div className="p-4 space-y-4">
            <div className="flex items-center gap-2 text-sm">
              <Dot tone={connected ? "pos" : "muted"} className={connected ? "animate-pulse" : ""} />
              <span className="font-medium">
                {!schedule
                  ? "carregando…"
                  : connected
                    ? "unlock_bot ativo"
                    : "API inacessível"}
              </span>
            </div>

            {nextEvent && (
              <div className="rounded border p-3 space-y-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  Próximo evento
                </div>
                <div className="text-sm font-medium">{nextEvent.symbol}</div>
                <div className="text-xs text-muted-foreground">
                  {fmtDate(nextEvent.unlock_date)} · ${nextEvent.unlock_value_mm.toFixed(1)}M
                </div>
                <div className="text-xs">
                  <span className={nextEvent.days_until <= 3 ? "text-warning" : "text-muted-foreground"}>
                    {nextEvent.days_until} dias até unlock
                  </span>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Win Rate (OOS-25)
                </Mono>
                <div className="mt-1 font-mono text-success">79%</div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Net bps (OOS-25)
                </Mono>
                <div className="mt-1 font-mono text-success">+656</div>
              </div>
            </div>

            {status && status.open_count > 0 && (
              <div>
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
                  Posições abertas
                </Mono>
                <div className="mt-2 space-y-2">
                  {status.open_positions.map((p, i) => (
                    <div key={i} className="rounded border p-2 text-xs">
                      <div className="flex justify-between">
                        <span className="font-medium">{p.symbol}</span>
                        <Badge variant="outline" className="text-[10px] uppercase border-destructive/40 text-destructive bg-destructive/10">
                          {p.side}
                        </Badge>
                      </div>
                      <div className="text-muted-foreground mt-1">
                        Entry: ${p.entry_price.toFixed(4)} · Notional: {fmtMoney(p.notional)}
                      </div>
                      <div className="text-muted-foreground">
                        Unlock: {fmtDate(p.unlock_date)} · ${p.unlock_value_mm.toFixed(1)}M
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="text-[11px] text-muted-foreground">
              <CalendarClock className="h-3 w-3 inline mr-1" />
              Timing: -3d entry / +3d exit · 20bps fees + real funding
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
