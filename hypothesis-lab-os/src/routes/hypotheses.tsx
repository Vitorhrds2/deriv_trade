import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Mono, Stat } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { hypotheses, statusBadgeClass, fmtMoney, type Hypothesis } from "@/lib/mock-data";
import { Filter, FlaskConical, GitBranch, Play, Plus, Sparkles, X } from "lucide-react";
import { useApp } from "@/lib/store";
import { useMemo } from "react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";

export const Route = createFileRoute("/hypotheses")({
  head: () => ({ meta: [{ title: "Hypothesis Engine — TradeLab OS" }] }),
  component: HypothesesPage,
});

const STATUSES: ("all" | Hypothesis["status"])[] = ["all", "live", "validating", "draft", "paused", "archived"];

function HypothesesPage() {
  const filter = useApp((s) => s.hypFilter);
  const setFilter = useApp((s) => s.setHypFilter);
  const status = useApp((s) => s.hypStatus);
  const setStatus = useApp((s) => s.setHypStatus);
  const selectedId = useApp((s) => s.selectedHypId);
  const select = useApp((s) => s.selectHyp);
  const pushNotif = useApp((s) => s.pushNotif);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return hypotheses.filter((h) => {
      if (status !== "all" && h.status !== status) return false;
      if (!q) return true;
      return (
        h.title.toLowerCase().includes(q) ||
        h.market.toLowerCase().includes(q) ||
        h.tags.some((t) => t.toLowerCase().includes(q)) ||
        h.id.toLowerCase().includes(q)
      );
    });
  }, [filter, status]);

  const selected = hypotheses.find((h) => h.id === selectedId) ?? hypotheses[0];

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="research › hypothesis engine"
        title="Hypothesis Engine"
        description="Estruture teses operacionais como objetos versionados, com gatilhos, invalidações e métricas."
        actions={
          <>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => toast.info("AI suggestion engine", { description: "Analisando 4.2k notícias e on-chain feeds…" })}>
              <Sparkles className="h-4 w-4" />Sugerir com AI
            </Button>
            <Button size="sm" className="gap-1.5" onClick={() => {
              pushNotif({ kind: "info", title: "Hipótese HYP-0143 criada", desc: "Rascunho salvo no workspace." });
              toast.success("Hipótese HYP-0143 criada");
            }}><Plus className="h-4 w-4" />Nova hipótese</Button>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Total" value={hypotheses.length} hint="todos os estados" />
        <Stat label="Ativas" value={hypotheses.filter((h) => h.status === "live").length} delta="2 gerando alpha" tone="pos" />
        <Stat label="Em validação" value={hypotheses.filter((h) => h.status === "validating").length} />
        <Stat label="Confiança média" value={`${Math.round(hypotheses.reduce((a, h) => a + h.confidence, 0) / hypotheses.length)}%`} />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Catálogo de hipóteses" subtitle={`${filtered.length} resultado${filtered.length === 1 ? "" : "s"}`} actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <Input
                placeholder="filtrar por tag, mercado, id…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="h-8 w-64 pl-8 pr-8 bg-muted/40 text-xs font-mono"
              />
              <Filter className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              {filter && (
                <button onClick={() => setFilter("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        }>
          <div className="px-4 py-2 border-b border-border/60 flex items-center gap-1.5 flex-wrap">
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border transition-colors ${
                  status === s
                    ? "bg-primary/15 border-primary/40 text-primary"
                    : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">ID</th>
                <th className="text-left px-4 py-2">Título</th>
                <th className="text-left px-4 py-2">Mercado</th>
                <th className="text-left px-4 py-2">Conf.</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Trades</th>
                <th className="text-right px-4 py-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              <AnimatePresence initial={false}>
                {filtered.map((h) => {
                  const active = h.id === selectedId;
                  return (
                    <motion.tr
                      key={h.id}
                      layout
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      onClick={() => select(h.id)}
                      className={`border-b border-border/40 last:border-0 cursor-pointer transition-colors ${active ? "bg-primary/5" : "hover:bg-muted/30"}`}
                    >
                      <td className="px-4 py-3"><Mono className={active ? "text-primary" : "text-muted-foreground"}>{h.id}</Mono></td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{h.title}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5 flex gap-1.5 flex-wrap">
                          {h.tags.map((t) => <span key={t} className="font-mono">#{t}</span>)}
                        </div>
                      </td>
                      <td className="px-4 py-3"><Mono>{h.market}</Mono></td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 w-32">
                          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                            <motion.div initial={{ width: 0 }} animate={{ width: `${h.confidence}%` }} transition={{ duration: 0.6 }} className="h-full bg-gradient-to-r from-primary to-accent" />
                          </div>
                          <Mono>{h.confidence}%</Mono>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="outline" className={`${statusBadgeClass(h.status)} text-[10px] font-mono uppercase`}>{h.status}</Badge>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">{h.trades}</td>
                      <td className={`px-4 py-3 text-right font-mono text-xs tabular-nums ${h.pnl > 0 ? "text-pos" : h.pnl < 0 ? "text-neg" : "text-muted-foreground"}`}>{fmtMoney(h.pnl)}</td>
                    </motion.tr>
                  );
                })}
              </AnimatePresence>
              {filtered.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">Nenhuma hipótese encontrada para os filtros atuais.</td></tr>
              )}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 xl:col-span-4" title="Hipótese selecionada" subtitle={selected.id + " · " + selected.author}>
          <motion.div key={selected.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="p-4 space-y-4">
            <div>
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">title</Mono>
              <div className="font-semibold mt-1">{selected.title}</div>
            </div>
            <div>
              <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">thesis</Mono>
              <p className="text-sm text-muted-foreground mt-1 leading-relaxed">{selected.thesis}</p>
            </div>
            <div className="rounded-md border bg-background/40 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
{`title: ${selected.title}
market: ${selected.market}
trigger:
  ${selected.trigger}
invalidation:
  ${selected.invalidation}
status: ${selected.status}
confidence: ${selected.confidence}%`}
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">trades</Mono>
                <div className="mt-1 font-mono">{selected.trades}</div>
              </div>
              <div className="rounded border p-3">
                <Mono className="text-muted-foreground uppercase tracking-wider text-[10px]">p&l acum.</Mono>
                <div className={`mt-1 font-mono ${selected.pnl >= 0 ? "text-pos" : "text-neg"}`}>{fmtMoney(selected.pnl)}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 pt-2 border-t">
              <Button
                size="sm" className="flex-1 gap-1.5"
                onClick={() => toast.success(`Backtest enfileirado para ${selected.id}`, { description: "Resultado em ~12s." })}
              >
                <FlaskConical className="h-4 w-4" />Backtest
              </Button>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => toast.info("Hipótese forkada", { description: `${selected.id} → HYP-0143-fork` })}>
                <GitBranch className="h-4 w-4" />Fork
              </Button>
              <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => toast.success("Simulação iniciada", { description: "Monte Carlo · 10k caminhos" })}>
                <Play className="h-4 w-4" />Simular
              </Button>
            </div>
          </motion.div>
        </Panel>
      </div>
    </div>
  );
}
