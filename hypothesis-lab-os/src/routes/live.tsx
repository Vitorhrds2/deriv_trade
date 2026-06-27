import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { equityCurve, fmtMoney, orderbook, trades } from "@/lib/mock-data";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { OctagonX, Radio, X } from "lucide-react";
import { useApp, liveDerivedMid } from "@/lib/store";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AnimatePresence, motion } from "framer-motion";

export const Route = createFileRoute("/live")({
  head: () => ({ meta: [{ title: "Live Trading — TradeLab OS" }] }),
  component: LivePage,
});

const tt = { contentStyle: { background: "oklch(0.20 0.014 240)", border: "1px solid oklch(0.28 0.014 240)", borderRadius: 8, fontSize: 12, fontFamily: "JetBrains Mono" } };

type Pos = { sym: string; side: "LONG" | "SHORT" | "SPREAD"; qty: number; entry: number; mark: number; pnl: number; venue: string };
const initialPositions: Pos[] = [
  { sym: "BTC-PERP",  side: "LONG",  qty: 0.82, entry: 67_055.8, mark: 67_412.5, pnl:  293.1, venue: "Binance" },
  { sym: "TRUMP-YES", side: "SPREAD", qty: 850,  entry: 0.59,    mark: 0.62,     pnl:  255.0, venue: "Poly+Kshi" },
  { sym: "EUR/USD",   side: "SHORT", qty: 50_000, entry: 1.0842, mark: 1.0828,  pnl:   70.0, venue: "OANDA" },
  { sym: "NVDA",      side: "LONG",  qty: 12,    entry: 942.10,  mark: 938.25,  pnl:  -46.2, venue: "Alpaca" },
];

function LivePage() {
  const tick = useApp((s) => s.tick);
  const killed = useApp((s) => s.killed);
  const setKillOpen = useApp((s) => s.setKillOpen);
  const pushNotif = useApp((s) => s.pushNotif);
  const [positions, setPositions] = useState<Pos[]>(initialPositions);

  const mid = liveDerivedMid(tick);

  const liveEquity = useMemo(() => equityCurve.map((p, i) => ({ ...p, equity: p.equity + Math.sin((i + tick) / 4) * 200 })), [tick]);

  const flatten = (sym: string) => {
    setPositions((prev) => prev.filter((p) => p.sym !== sym));
    pushNotif({ kind: "warn", title: `Posição ${sym} encerrada`, desc: "Market order enviada." });
    toast(`Posição ${sym} encerrada`);
  };

  const flattenAll = () => {
    setPositions([]);
    pushNotif({ kind: "warn", title: "Todas posições encerradas", desc: "Flatten manual disparado." });
    toast.warning("Flatten executado em todas as posições");
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › live trading"
        title={<span className="flex items-center gap-3">Live Trading <span className={`flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider ${killed ? "text-destructive" : "text-success"}`}><Dot tone={killed ? "neg" : "pos"} className={killed ? "" : "animate-pulse"} />{killed ? "halt" : "ao vivo"}</span></span>}
        description="Ordens reais roteadas para brokers conectados. Risk engine sempre ativo."
        actions={
          <>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => toast.info("Smart Order Router", { description: "Reavaliando venues por liquidez…" })}>
              <Radio className="h-4 w-4" />Roteamento
            </Button>
            <Button variant="outline" size="sm" onClick={flattenAll} disabled={positions.length === 0}>
              Flatten all
            </Button>
            <Button variant="destructive" size="sm" className="gap-1.5" onClick={() => setKillOpen(true)}>
              <OctagonX className="h-4 w-4" />Kill switch
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Exposição bruta" value={fmtMoney(positions.reduce((a, p) => a + Math.abs(p.qty * p.mark), 0))} hint="gross notional" />
        <Stat label="Posições abertas" value={positions.length} delta={`${positions.filter(p => p.side === "LONG").length}L / ${positions.filter(p => p.side === "SHORT").length}S`} tone="neutral" />
        <Stat label="P&L aberto"      value={fmtMoney(positions.reduce((a, p) => a + p.pnl, 0))}  delta="+0.69%"  tone="pos" />
        <Stat label="Latência média"  value="78ms" delta="p99 142ms" tone="neutral" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="BTC-PERP · Binance" subtitle="bot: cpi-btc-prod · estratégia: cpi_btc_long_v3" actions={
          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="text-muted-foreground">mid</span>
            <AnimatePresence mode="popLayout">
              <motion.span key={mid.toFixed(1)} initial={{ opacity: 0, y: -3 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 3 }} className="text-foreground tabular-nums">
                {mid.toFixed(1)}
              </motion.span>
            </AnimatePresence>
          </div>
        }>
          <div className="h-[300px] p-3">
            <ResponsiveContainer>
              <AreaChart data={liveEquity}>
                <defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="oklch(0.85 0.18 130)" stopOpacity={0.4} /><stop offset="100%" stopColor="oklch(0.85 0.18 130)" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid stroke="oklch(0.24 0.014 240)" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "oklch(0.62 0.018 240)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip {...tt} />
                <Area type="monotone" dataKey="equity" stroke="oklch(0.85 0.18 130)" strokeWidth={2} fill="url(#lg)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="Order book" subtitle="L2 · BTC-PERP">
          <div className="font-mono text-[11px] divide-y divide-border/60">
            <div className="grid grid-cols-3 px-4 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              <div>preço</div><div className="text-right">size</div><div className="text-right">cum</div>
            </div>
            {orderbook.asks.slice().reverse().map((r, i) => {
              const size = +(r.size + Math.sin((i + tick) / 3) * 0.4).toFixed(3);
              return (
                <div key={i} className="grid grid-cols-3 px-4 py-1 relative">
                  <motion.div animate={{ width: `${Math.min(100, Math.abs(size) / 3 * 100)}%` }} transition={{ duration: 0.4 }} className="absolute inset-y-0 right-0 bg-destructive/10" />
                  <div className="text-neg relative tabular-nums">{r.price.toFixed(1)}</div>
                  <div className="text-right relative tabular-nums">{Math.abs(size).toFixed(2)}</div>
                  <div className="text-right text-muted-foreground relative tabular-nums">{r.cum}</div>
                </div>
              );
            })}
            <div className="grid grid-cols-3 px-4 py-2 bg-muted/30 text-center text-foreground">
              <div className="col-span-3 text-[10px] uppercase tracking-wider text-muted-foreground">spread 0.5 · mid <span className="text-foreground tabular-nums">{mid.toFixed(1)}</span></div>
            </div>
            {orderbook.bids.map((r, i) => {
              const size = +(r.size + Math.sin((i + tick) / 3 + 1) * 0.4).toFixed(3);
              return (
                <div key={i} className="grid grid-cols-3 px-4 py-1 relative">
                  <motion.div animate={{ width: `${Math.min(100, Math.abs(size) / 3 * 100)}%` }} transition={{ duration: 0.4 }} className="absolute inset-y-0 right-0 bg-success/10" />
                  <div className="text-pos relative tabular-nums">{r.price.toFixed(1)}</div>
                  <div className="text-right relative tabular-nums">{Math.abs(size).toFixed(2)}</div>
                  <div className="text-right text-muted-foreground relative tabular-nums">{r.cum}</div>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel className="col-span-12 xl:col-span-7" title="Posições abertas" subtitle={`${positions.length} posiç${positions.length === 1 ? "ão" : "ões"}`}>
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Símbolo</th>
                <th className="text-left px-4 py-2">Side</th>
                <th className="text-right px-4 py-2">Qty</th>
                <th className="text-right px-4 py-2">Entrada</th>
                <th className="text-right px-4 py-2">Mark</th>
                <th className="text-right px-4 py-2">P&L</th>
                <th className="text-left px-4 py-2">Venue</th>
                <th className="text-right px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              <AnimatePresence initial={false}>
                {positions.map((p) => (
                  <motion.tr key={p.sym} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, x: 40 }} className="border-b border-border/40 last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-3">{p.sym}</td>
                    <td className="px-4 py-3"><Badge variant="outline" className={`uppercase text-[10px] ${p.side === "LONG" ? "border-success/40 text-success bg-success/10" : p.side === "SHORT" ? "border-destructive/40 text-destructive bg-destructive/10" : "border-info/40 text-info bg-info/10"}`}>{p.side}</Badge></td>
                    <td className="px-4 py-3 text-right tabular-nums">{p.qty}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{p.entry.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{p.mark.toLocaleString()}</td>
                    <td className={`px-4 py-3 text-right tabular-nums ${p.pnl >= 0 ? "text-pos" : "text-neg"}`}>{p.pnl >= 0 ? "+" : ""}{p.pnl.toFixed(1)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{p.venue}</td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={() => flatten(p.sym)} title="Flatten">
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </motion.tr>
                ))}
              </AnimatePresence>
              {positions.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">Sem posições abertas.</td></tr>
              )}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 xl:col-span-5" title="Execuções recentes">
          <div className="font-mono text-xs divide-y divide-border/40">
            {trades.slice(0, 6).map((t) => (
              <div key={t.id} className="px-4 py-2.5 flex items-center gap-3 hover:bg-muted/30 transition-colors">
                <Mono className="text-muted-foreground w-16">{t.time}</Mono>
                <span className={`uppercase ${t.side === "BUY" ? "text-pos" : "text-neg"} w-10`}>{t.side}</span>
                <span className="flex-1 truncate">{t.symbol}</span>
                <span className="text-right tabular-nums">{t.qty}</span>
                <span className="text-right text-muted-foreground w-20 tabular-nums">@{t.price.toLocaleString()}</span>
                <span className={`text-right w-16 tabular-nums ${t.pnl > 0 ? "text-pos" : t.pnl < 0 ? "text-neg" : "text-muted-foreground"}`}>{t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
