import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono } from "@/components/kit";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { realHypotheses, hypStatusBadgeClass, type RealHypothesis } from "@/lib/hypotheses-data";
import { fmtMoney } from "@/lib/format";
import { Search, FileText, FlaskConical, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";

export const Route = createFileRoute("/simulations")({
  head: () => ({ meta: [{ title: "Hypothesis Test Suite — TradeLab OS" }] }),
  component: SimulationsPage,
});

const STATUS_FILTERS = ["all", "refuted", "validating", "live"] as const;
type SortKey = "trades" | "evPerTrade" | "pnl";

function SimulationsPage() {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: realHypotheses.length };
    for (const h of realHypotheses) counts[h.status] = (counts[h.status] ?? 0) + 1;
    return counts;
  }, []);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = realHypotheses.filter((h) => {
      if (statusFilter !== "all" && h.status !== statusFilter) return false;
      if (q && !(
        h.id.toLowerCase().includes(q) ||
        h.title.toLowerCase().includes(q) ||
        h.market.toLowerCase().includes(q) ||
        h.tags.some((t) => t.toLowerCase().includes(q))
      )) return false;
      return true;
    });
    if (!sortKey) return base;
    const sign = sortDir === "asc" ? 1 : -1;
    return [...base].sort((a, b) => {
      const av = sortKey === "evPerTrade" ? (a.evPerTrade ?? 0) : a[sortKey];
      const bv = sortKey === "evPerTrade" ? (b.evPerTrade ?? 0) : b[sortKey];
      return (av - bv) * sign;
    });
  }, [query, statusFilter, sortKey, sortDir]);

  const selected = useMemo(
    () => realHypotheses.find((h) => h.id === selectedId) ?? null,
    [selectedId]
  );

  const refutedCount = statusCounts.refuted ?? 0;
  const validatingCount = statusCounts.validating ?? 0;
  const liveCount = statusCounts.live ?? 0;
  const totalSample = realHypotheses.reduce((a, h) => a + h.trades, 0);

  const SortHeader = ({ label, k, align = "right" }: { label: string; k: SortKey; align?: "left" | "right" }) => (
    <th className={`px-4 py-2 ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        onClick={() => toggleSort(k)}
        className={`inline-flex items-center gap-1 hover:text-foreground transition-colors ${sortKey === k ? "text-primary" : ""}`}
      >
        {label}
        {sortKey === k ? (
          sortDir === "desc" ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-40" />
        )}
      </button>
    </th>
  );

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="research › hypothesis test suite"
        title="Hypothesis Test Suite"
        description={
          <>
            Leaderboard quantitativo — ordene {realHypotheses.length} hipóteses por N, EV/trade ou
            PnL. Para a tese completa (thesis/trigger/invalidation) de cada uma, veja o{" "}
            <Link to="/hypotheses" className="underline hover:text-primary">catálogo em Hypothesis Engine</Link>.
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <Stat label="Total testadas" value={realHypotheses.length} hint={`${refutedCount} refutadas · ${validatingCount} validando · ${liveCount} edge validado`} />
        <Stat label="Refutadas" value={refutedCount} tone="neg" hint="sem edge após teste rigoroso" />
        <Stat label="Validando" value={validatingCount} tone="neutral" hint="em andamento ou amostra insuficiente" />
        <Stat label="Edge validado" value={liveCount} tone="pos" hint="D17 token unlock" />
        <Stat label="Amostra total" value={totalSample.toLocaleString()} hint="trades/ticks/events" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel
          className="col-span-12 xl:col-span-8"
          title="Resultados dos testes"
          subtitle={`${filtered.length} resultado${filtered.length === 1 ? "" : "s"}`}
          actions={
            <div className="flex items-center gap-2">
              <div className="relative">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="filtrar hipótese…"
                  className="h-8 w-48 pl-8 text-xs font-mono bg-muted/40"
                />
                <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              </div>
            </div>
          }
        >
          <div className="px-4 py-2 border-b border-border/60 flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mr-1">status</span>
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border transition-colors ${
                  statusFilter === s
                    ? "bg-primary/15 border-primary/40 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {s} <span className="opacity-60">({statusCounts[s] ?? 0})</span>
              </button>
            ))}
          </div>
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">ID</th>
                <th className="text-left px-4 py-2">Hipótese</th>
                <th className="text-left px-4 py-2">Mercado</th>
                <SortHeader label="N" k="trades" />
                <SortHeader label="EV/trade" k="evPerTrade" />
                <SortHeader label="PnL" k="pnl" />
                <th className="text-left px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {filtered.map((h) => (
                <tr
                  key={h.id}
                  onClick={() => setSelectedId(h.id)}
                  className={`border-b border-border/40 last:border-0 cursor-pointer transition-colors ${
                    selectedId === h.id ? "bg-primary/5" : "hover:bg-muted/30"
                  }`}
                >
                  <td className="px-4 py-3">
                    <Mono className={selectedId === h.id ? "text-primary" : "text-muted-foreground"}>
                      {h.id}
                    </Mono>
                  </td>
                  <td className="px-4 py-3 text-foreground max-w-[280px] truncate">
                    {h.title}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground max-w-[160px] truncate">
                    {h.market}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {h.trades.toLocaleString()}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums ${
                    h.evPerTrade != null && h.evPerTrade < 0
                      ? "text-neg"
                      : h.evPerTrade != null && h.evPerTrade > 0
                        ? "text-pos"
                        : "text-muted-foreground"
                  }`}>
                    {h.evPerTrade != null ? fmtMoney(h.evPerTrade) : "—"}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums ${
                    h.pnl > 0 ? "text-pos" : h.pnl < 0 ? "text-neg" : "text-muted-foreground"
                  }`}>
                    {h.pnl !== 0 ? fmtMoney(h.pnl) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      variant="outline"
                      className={`uppercase text-[10px] tracking-wider ${hypStatusBadgeClass(h.status)}`}
                    >
                      {h.status}
                    </Badge>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    Nenhuma hipótese com esses filtros.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </Panel>

        <Panel
          className="col-span-12 xl:col-span-4"
          title={selected ? selected.id : "Detalhes"}
          subtitle={selected ? selected.title : "Selecione uma hipótese para ver detalhes"}
        >
          {selected ? <HypothesisDetail h={selected} /> : (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              <FlaskConical className="h-8 w-8 mx-auto mb-2 opacity-40" />
              Clique em uma hipótese para ver o veredito completo.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function HypothesisDetail({ h }: { h: RealHypothesis }) {
  return (
    <div className="p-4 space-y-4 overflow-auto max-h-[600px]">
      <div>
        <Badge
          variant="outline"
          className={`uppercase text-[10px] tracking-wider ${hypStatusBadgeClass(h.status)}`}
        >
          {h.status}
        </Badge>
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground ml-2">
          confiança {h.confidence}%
        </span>
      </div>

      <div>
        <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">Mercado</Mono>
        <div className="text-sm mt-1">{h.market}</div>
      </div>

      <div>
        <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">Tese</Mono>
        <p className="text-sm mt-1 text-foreground/90 leading-snug">{h.thesis}</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded border p-3">
          <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">Amostra</Mono>
          <div className="mt-1 font-mono text-sm">{h.trades.toLocaleString()}</div>
          <div className="text-[10px] text-muted-foreground">{h.sampleUnit}</div>
        </div>
        {h.evPerTrade != null && (
          <div className="rounded border p-3">
            <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">EV/trade</Mono>
            <div className={`mt-1 font-mono text-sm ${h.evPerTrade < 0 ? "text-neg" : "text-pos"}`}>
              {fmtMoney(h.evPerTrade)}
            </div>
          </div>
        )}
        {h.ci95 && (
          <div className="rounded border p-3 col-span-2">
            <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">
              {h.ci95Label ?? "CI 95%"}
            </Mono>
            <div className="mt-1 font-mono text-sm">
              [{h.ci95[0]}, {h.ci95[1]}]
            </div>
          </div>
        )}
        {h.pnl !== 0 && (
          <div className="rounded border p-3">
            <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">PnL real</Mono>
            <div className={`mt-1 font-mono text-sm ${h.pnl > 0 ? "text-pos" : "text-neg"}`}>
              {fmtMoney(h.pnl)}
            </div>
          </div>
        )}
      </div>

      <div>
        <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">Trigger</Mono>
        <p className="text-xs mt-1 text-muted-foreground leading-snug">{h.trigger}</p>
      </div>

      <div>
        <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">Veredito</Mono>
        <p className="text-xs mt-1 text-foreground/90 leading-snug">{h.verdict}</p>
      </div>

      <div>
        <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">Ferramentas</Mono>
        <div className="flex flex-wrap gap-1 mt-1">
          {h.tools.map((t) => (
            <Badge key={t} variant="outline" className="text-[10px] font-mono border-border text-muted-foreground">
              {t}
            </Badge>
          ))}
        </div>
      </div>

      <div className="pt-2 border-t border-border/60">
        <a
          href={`https://github.com/vitorhrds2/deriv_trade/blob/main/${h.reportFile}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-primary hover:underline inline-flex items-center gap-1"
        >
          <FileText className="h-3 w-3" />
          {h.reportFile}
        </a>
      </div>
    </div>
  );
}
