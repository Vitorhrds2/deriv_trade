import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, Stat, Mono, Dot } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { statusBadgeClass } from "@/lib/mock-data";
import { Pause, Play, RefreshCw, Square, Terminal } from "lucide-react";
import { useApp } from "@/lib/store";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AnimatePresence, motion } from "framer-motion";

export const Route = createFileRoute("/bots")({
  head: () => ({ meta: [{ title: "Bot Orchestrator — TradeLab OS" }] }),
  component: BotsPage,
});

type Log = { id: number; t: string; level: "info" | "warn" | "error"; msg: string };

const seedLogs: Log[] = [
  { id: 1, t: "12:04:11.241", level: "info",  msg: "[cpi-btc-prod] order filled 0.42 BTC @ 67412.5" },
  { id: 2, t: "12:04:11.198", level: "info",  msg: "[cpi-btc-prod] signal triggered: actual=3.4 > forecast=3.2" },
  { id: 3, t: "12:03:58.612", level: "info",  msg: "[poly-kshi-arb-prod] spread 3.4% > threshold → leg in" },
  { id: 4, t: "12:01:02.001", level: "warn",  msg: "[poly-kshi-arb-prod] kalshi latency 220ms (above SLO 150ms)" },
  { id: 5, t: "11:59:02.781", level: "info",  msg: "[cpi-btc-prod] trailing stop moved to 67050" },
  { id: 6, t: "11:48:23.512", level: "info",  msg: "[fomc-steepener-sim] entered ZN long 5 contracts" },
  { id: 7, t: "11:32:10.014", level: "error", msg: "[nvda-drift-sim] data feed disconnected, retrying (3/5)" },
  { id: 8, t: "11:31:42.221", level: "info",  msg: "[scheduler] cron tick → 11 jobs evaluated, 2 dispatched" },
];

const LOG_SAMPLES: Log[] = [
  { id: 0, t: "", level: "info",  msg: "[cpi-btc-prod] heartbeat ok · cpu 14% · mem 38%" },
  { id: 0, t: "", level: "info",  msg: "[poly-kshi-arb-prod] orderbook depth refreshed (32 levels)" },
  { id: 0, t: "", level: "warn",  msg: "[fomc-steepener-sim] slippage 1.2bp above expected" },
  { id: 0, t: "", level: "info",  msg: "[scheduler] dispatched 3 jobs to worker pool" },
  { id: 0, t: "", level: "info",  msg: "[risk-engine] VaR recompute 4.0k → 4.1k" },
];

function BotsPage() {
  const bots = useApp((s) => s.bots);
  const setBotState = useApp((s) => s.setBotState);
  const restartBot = useApp((s) => s.restartBot);
  const killed = useApp((s) => s.killed);
  const pushNotif = useApp((s) => s.pushNotif);

  const [logs, setLogs] = useState<Log[]>(seedLogs);

  useEffect(() => {
    if (killed) return;
    const id = setInterval(() => {
      const pick = LOG_SAMPLES[Math.floor(Math.random() * LOG_SAMPLES.length)];
      const now = new Date();
      const t = now.toLocaleTimeString("en-US", { hour12: false }) + "." + String(now.getMilliseconds()).padStart(3, "0");
      setLogs((prev) => [{ ...pick, id: Date.now(), t }, ...prev].slice(0, 40));
    }, 2200);
    return () => clearInterval(id);
  }, [killed]);

  const handlePause = (id: string, name: string) => {
    setBotState(id, "stopped");
    pushNotif({ kind: "warn", title: `Bot ${name} pausado`, desc: "Ordens novas bloqueadas." });
    toast(`${name} pausado`);
  };
  const handleResume = (id: string, name: string) => {
    setBotState(id, "running");
    pushNotif({ kind: "success", title: `Bot ${name} ativo`, desc: "Aceitando sinais novamente." });
    toast.success(`${name} em execução`);
  };
  const handleRestart = (id: string, name: string) => {
    restartBot(id);
    toast.info(`${name} reiniciando…`);
    setTimeout(() => {
      setBotState(id, "running");
      pushNotif({ kind: "success", title: `Bot ${name} reiniciado`, desc: "Healthcheck OK." });
    }, 1600);
  };
  const handleStop = (id: string, name: string) => {
    setBotState(id, "stopped");
    pushNotif({ kind: "error", title: `Bot ${name} desligado`, desc: "Posições mantidas, sem novas ordens." });
    toast.error(`${name} encerrado`);
  };

  const running = bots.filter((b) => b.state === "running").length;
  const errored = bots.filter((b) => b.state === "error").length;

  return (
    <div className="max-w-[1600px] mx-auto">
      <PageHeader
        eyebrow="execution › bot orchestrator"
        title="Bot Orchestrator"
        description="Deploy, monitoramento, health checks e auto-recovery em ambientes paper e live."
        actions={<Button size="sm" className="gap-1.5" onClick={() => toast.success("Bot BOT-06 deployed", { description: "Aguardando primeiro tick…" })}><Play className="h-4 w-4" />Deploy bot</Button>}
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <Stat label="Bots totais" value={bots.length} />
        <Stat label="Em execução" value={running} delta={`${bots.filter(b => b.env === "live" && b.state === "running").length} live · ${bots.filter(b => b.env === "paper" && b.state === "running").length} paper`} tone="pos" />
        <Stat label="Em erro" value={errored} tone={errored > 0 ? "neg" : "neutral"} delta="auto-recovery ativo" />
        <Stat label="CPU médio" value={`${Math.round(bots.filter(b => b.state === "running").reduce((a, b) => a + b.cpu, 0) / Math.max(running, 1))}%`} />
        <Stat label="Latência p99" value="142ms" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-7" title="Frota de bots">
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border/70">
              <tr>
                <th className="text-left px-4 py-2">Bot</th>
                <th className="text-left px-4 py-2">Env</th>
                <th className="text-left px-4 py-2">Estado</th>
                <th className="text-right px-4 py-2">CPU</th>
                <th className="text-right px-4 py-2">Mem</th>
                <th className="text-right px-4 py-2">Ordens</th>
                <th className="text-right px-4 py-2">Latência</th>
                <th className="text-right px-4 py-2">Uptime</th>
                <th className="text-right px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {bots.map((b) => (
                <tr key={b.id} className="border-b border-border/40 last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Dot tone={b.state === "running" ? "pos" : b.state === "error" ? "neg" : b.state === "recovering" ? "warn" : "muted"} className={b.state === "running" ? "animate-pulse" : ""} />
                      <span className="text-foreground">{b.name}</span>
                    </div>
                    <Mono className="text-muted-foreground">{b.id} · {b.strategyId}</Mono>
                  </td>
                  <td className="px-4 py-3 uppercase text-[10px] tracking-wider text-muted-foreground">{b.env}</td>
                  <td className="px-4 py-3"><Badge variant="outline" className={`${statusBadgeClass(b.state)} uppercase text-[10px]`}>{b.state}</Badge></td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    <div className="inline-flex items-center gap-1.5">
                      <div className="w-10 h-1 rounded-full bg-muted overflow-hidden">
                        <motion.div animate={{ width: `${b.cpu}%` }} transition={{ duration: 0.4 }} className={`h-full ${b.cpu > 70 ? "bg-destructive" : b.cpu > 40 ? "bg-warning" : "bg-primary"}`} />
                      </div>
                      {b.cpu}%
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{b.memory}%</td>
                  <td className="px-4 py-3 text-right tabular-nums">{b.ordersToday}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{b.latencyMs ? `${b.latencyMs}ms` : "—"}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground tabular-nums">{b.uptime}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      {b.state === "running" ? (
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handlePause(b.id, b.name)} title="Pausar">
                          <Pause className="h-3.5 w-3.5" />
                        </Button>
                      ) : (
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-primary" onClick={() => handleResume(b.id, b.name)} title="Retomar">
                          <Play className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleRestart(b.id, b.name)} title="Reiniciar">
                        <RefreshCw className={`h-3.5 w-3.5 ${b.state === "recovering" ? "animate-spin" : ""}`} />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => handleStop(b.id, b.name)} title="Desligar">
                        <Square className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel className="col-span-12 xl:col-span-5" title={<div className="flex items-center gap-2"><Terminal className="h-4 w-4" />Live logs · stream</div>} subtitle="Agregado de todos os bots ativos" actions={
          <Badge variant="outline" className={`font-mono text-[10px] gap-1 ${killed ? "border-destructive/40 text-destructive bg-destructive/10" : "border-success/40 text-success bg-success/10"}`}>
            <Dot tone={killed ? "neg" : "pos"} className={killed ? "" : "animate-pulse"} />
            {killed ? "halted" : "streaming"}
          </Badge>
        }>
          <div className="font-mono text-[11px] max-h-[440px] overflow-auto bg-background/30">
            <AnimatePresence initial={false}>
              {logs.map((l) => (
                <motion.div
                  key={l.id}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="px-4 py-1.5 border-b border-border/30 flex gap-3 hover:bg-muted/30"
                >
                  <span className="text-muted-foreground shrink-0">{l.t}</span>
                  <span className={`uppercase shrink-0 w-12 ${l.level === "info" ? "text-info" : l.level === "warn" ? "text-warning" : "text-destructive"}`}>{l.level}</span>
                  <span className="text-foreground/90 truncate">{l.msg}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </Panel>
      </div>
    </div>
  );
}
