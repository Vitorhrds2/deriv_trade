import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, ConceptBanner } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { events as seedEvents } from "@/lib/mock-data";
import { CalendarClock, Filter, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

export const Route = createFileRoute("/events")({
  head: () => ({ meta: [{ title: "Event Intelligence — TradeLab OS" }] }),
  component: EventsPage,
});

const feedSeed = [
  { t: "12:04", src: "BLS",   txt: "US CPI YoY 3.4% (cons. 3.2%, prev. 3.2%) — surpresa alta." },
  { t: "11:58", src: "X",     txt: "@federalreserve agendou statement para 14:00 ET." },
  { t: "11:30", src: "OnChain", txt: "ETH whale moved 12,420 ETH para Coinbase Prime." },
  { t: "10:42", src: "Polymarket", txt: "Volume diário em mercado eleitoral atinge $4.1M." },
  { t: "09:11", src: "NOAA",  txt: "Anomalia térmica Texas Δ+3.2σ — janela 72h." },
];

const kinds: Record<string, string> = {
  macro:    "border-info/40 text-info bg-info/10",
  earnings: "border-primary/40 text-primary bg-primary/10",
  onchain:  "border-accent/40 text-accent bg-accent/10",
  politics: "border-warning/40 text-warning bg-warning/10",
  weather:  "border-muted-foreground/30 text-muted-foreground bg-muted",
};

const KIND_KEYS = ["all", "macro", "earnings", "onchain", "politics", "weather"] as const;
const IMPACT_KEYS = ["all", "high", "med", "low"] as const;
const SOURCES = ["BLS", "X", "OnChain", "Polymarket", "NOAA"];

function EventsPage() {
  const [kind, setKind] = useState<(typeof KIND_KEYS)[number]>("all");
  const [impact, setImpact] = useState<(typeof IMPACT_KEYS)[number]>("all");
  const [query, setQuery] = useState("");
  const [enabledSrc, setEnabledSrc] = useState<string[]>(SOURCES);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return seedEvents.filter((e) => {
      if (kind !== "all" && e.kind !== kind) return false;
      if (impact !== "all" && e.impact !== impact) return false;
      if (q && !(e.name.toLowerCase().includes(q) || e.kind.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [kind, impact, query]);

  const filteredFeed = useMemo(() => feedSeed.filter((f) => enabledSrc.includes(f.src)), [enabledSrc]);

  const toggleSrc = (s: string) =>
    setEnabledSrc((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="ops › event intelligence"
        title="Event Intelligence Layer"
        description="Transforme eventos macro, on-chain, esportivos e sociais em sinais executáveis."
        actions={<Button size="sm" className="gap-1.5" onClick={() => toast.info("Conceito — sem conectores reais implementados ainda.")}><CalendarClock className="h-4 w-4" />Conectar fonte</Button>}
      />

      <ConceptBanner>
        Nenhuma fonte de evento real conectada (macro/on-chain/social). O ecossistema hoje só reage a choques de preço em tempo real via <Mono>hft_arbitrage_bot.py</Mono> — os eventos e o feed abaixo são ilustrativos de uma possível Event Intelligence Layer futura.
      </ConceptBanner>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Eventos hoje" value={seedEvents.length} />
        <Stat label="Alto impacto" value={seedEvents.filter((e) => e.impact === "high").length} tone="neg" delta="próximos 8h" />
        <Stat label="Fontes ativas" value={`${enabledSrc.length}/${SOURCES.length}`} hint="macro · social · on-chain" />
        <Stat label="Sinais disparados" value="32" delta="+18% wow" tone="pos" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-7" title="Calendário do dia" subtitle={`${filtered.length} resultado${filtered.length === 1 ? "" : "s"}`} actions={
          <div className="relative">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="filtrar evento…" className="h-8 w-52 pl-8 text-xs font-mono bg-muted/40" />
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          </div>
        }>
          <div className="px-4 py-2 border-b border-border/60 flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mr-1">tipo</span>
            {KIND_KEYS.map((k) => (
              <button key={k} onClick={() => setKind(k)} className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border transition-colors ${kind === k ? "bg-primary/15 border-primary/40 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>{k}</button>
            ))}
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mx-1 ml-3"><Filter className="h-3 w-3 inline" /> impacto</span>
            {IMPACT_KEYS.map((k) => (
              <button key={k} onClick={() => setImpact(k)} className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border transition-colors ${impact === k ? "bg-primary/15 border-primary/40 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>{k}</button>
            ))}
          </div>
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Hora</th>
                <th className="text-left px-4 py-2">Evento</th>
                <th className="text-left px-4 py-2">Tipo</th>
                <th className="text-left px-4 py-2">Impacto</th>
                <th className="text-right px-4 py-2">Consenso</th>
                <th className="text-right px-4 py-2">Real</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {filtered.map((e) => (
                <tr key={e.id} className="border-b border-border/40 last:border-0 hover:bg-muted/30 cursor-pointer" onClick={() => toast.info(`${e.name}`, { description: `Tipo ${e.kind} · impacto ${e.impact}` })}>
                  <td className="px-4 py-3 text-muted-foreground">{e.time}</td>
                  <td className="px-4 py-3 text-foreground">{e.name}</td>
                  <td className="px-4 py-3"><Badge variant="outline" className={`uppercase text-[10px] ${kinds[e.kind]}`}>{e.kind}</Badge></td>
                  <td className="px-4 py-3 uppercase text-[10px]"><span className={e.impact === "high" ? "text-destructive" : e.impact === "med" ? "text-warning" : "text-muted-foreground"}>{e.impact}</span></td>
                  <td className="px-4 py-3 text-right">{e.consensus ?? "—"}</td>
                  <td className={`px-4 py-3 text-right ${e.actual && e.actual !== "—" ? "text-pos" : "text-muted-foreground"}`}>{e.actual ?? "—"}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">Nenhum evento com esses filtros.</td></tr>
              )}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 xl:col-span-5" title="Feed de sinais" subtitle="Eventos brutos detectados pelas fontes conectadas" actions={
          <div className="flex flex-wrap gap-1">
            {SOURCES.map((s) => {
              const on = enabledSrc.includes(s);
              return (
                <button key={s} onClick={() => toggleSrc(s)} className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border transition-colors ${on ? "border-primary/40 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>{s}</button>
              );
            })}
          </div>
        }>
          <ul className="divide-y divide-border/60">
            {filteredFeed.map((f, i) => (
              <li key={i} className="px-4 py-3 flex gap-3 hover:bg-muted/30 transition-colors">
                <Mono className="text-muted-foreground shrink-0 w-12">{f.t}</Mono>
                <div className="shrink-0 w-20"><Badge variant="outline" className="font-mono text-[10px] uppercase border-border text-muted-foreground">{f.src}</Badge></div>
                <p className="text-sm text-foreground/90 flex-1 leading-snug">{f.txt}</p>
              </li>
            ))}
            {filteredFeed.length === 0 && (
              <li className="px-4 py-10 text-center text-xs text-muted-foreground">Nenhuma fonte ativada.</li>
            )}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
