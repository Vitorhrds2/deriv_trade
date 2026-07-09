import { Bell, Command, OctagonX, Search, Zap } from "lucide-react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dot } from "@/components/kit";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useApp } from "@/lib/store";
import { fmtMoney } from "@/lib/format";
import { getHftStatus, getHftTrades, isHftLive } from "@/lib/hft-api";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "@tanstack/react-router";

function TickerNumber({ value, className }: { value: string; className?: string }) {
  return (
    <AnimatePresence mode="popLayout">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 4 }}
        transition={{ duration: 0.2 }}
        className={className}
      >
        {value}
      </motion.span>
    </AnimatePresence>
  );
}

export function TopBar() {
  const setPaletteOpen = useApp((s) => s.setPaletteOpen);
  const setKillOpen = useApp((s) => s.setKillOpen);
  const killed = useApp((s) => s.killed);
  const notifs = useApp((s) => s.notifs);
  const markAllRead = useApp((s) => s.markAllRead);
  const navigate = useNavigate();

  const statusQuery = useQuery({ queryKey: ["hft-status"], queryFn: () => getHftStatus(), refetchInterval: 5000 });
  const tradesQuery = useQuery({ queryKey: ["hft-trades"], queryFn: () => getHftTrades(), refetchInterval: 5000 });
  const status = statusQuery.data;
  const trades = tradesQuery.data;
  const isLive = status ? isHftLive(status) : false;
  const unread = notifs.filter((n) => !n.read).length;

  return (
    <header className="h-14 flex items-center gap-3 border-b bg-background/80 backdrop-blur px-3 sticky top-0 z-30">
      <SidebarTrigger className="text-muted-foreground" />
      <div className="hidden md:flex items-center gap-2 text-xs font-mono text-muted-foreground">
        <span>workspace</span>
        <span className="text-foreground/70">/</span>
        <span className="text-foreground">mega-brain</span>
        {killed ? (
          <Badge variant="outline" className="ml-1 h-5 border-destructive/40 text-destructive bg-destructive/10 font-mono uppercase text-[10px] tracking-wider animate-pulse">
            halted
          </Badge>
        ) : (
          <Badge variant="outline" className="ml-1 h-5 border-success/40 text-success bg-success/10 font-mono uppercase text-[10px] tracking-wider">prod</Badge>
        )}
      </div>

      <button
        onClick={() => setPaletteOpen(true)}
        className="flex-1 max-w-xl mx-auto relative group text-left"
      >
        <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <div className="pl-9 pr-16 h-9 flex items-center rounded-md bg-muted/40 border border-border/70 text-sm text-muted-foreground hover:border-primary/40 hover:bg-muted/60 transition-colors">
          Buscar hipóteses, estratégias, bots, eventos…
        </div>
        <kbd className="absolute right-2 top-1/2 -translate-y-1/2 hidden sm:flex items-center gap-1 text-[10px] font-mono text-muted-foreground border border-border rounded px-1.5 py-0.5 bg-background/60">
          <Command className="h-3 w-3" /> K
        </kbd>
      </button>

      <div className="hidden lg:flex items-center gap-4 px-3 border-l border-r h-9 font-mono text-[11px]">
        <div className="flex items-center gap-1.5">
          <Dot tone={statusQuery.isLoading ? "muted" : isLive ? "pos" : "neg"} className={isLive ? "animate-pulse" : ""} />
          <span className="text-muted-foreground">hft_bot</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">PNL</span>
          <TickerNumber value={trades ? fmtMoney(trades.total.pnlTotal) : "—"} className={trades && trades.total.pnlTotal < 0 ? "text-neg tabular-nums" : "text-muted-foreground tabular-nums"} />
        </div>
        <div><span className="text-muted-foreground">N</span> <span>{trades?.total.n ?? "—"}</span></div>
        <div><span className="text-muted-foreground">WR</span> <span>{trades ? `${Math.round(trades.total.winRate * 100)}%` : "—"}</span></div>
      </div>

      {killed && (
        <Button
          size="sm"
          variant="outline"
          className="border-destructive/40 text-destructive hover:bg-destructive/10 gap-1.5"
          onClick={() => useApp.getState().resume()}
        >
          <OctagonX className="h-4 w-4" /> Retomar
        </Button>
      )}

      <Popover>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon" className="relative text-muted-foreground hover:text-foreground">
            <Bell className="h-4 w-4" />
            {unread > 0 && (
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-destructive animate-pulse" />
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-80 p-0">
          <div className="flex items-center justify-between px-3 py-2 border-b">
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">notificações</div>
            <button className="text-[11px] text-muted-foreground hover:text-foreground" onClick={markAllRead}>
              Marcar como lidas
            </button>
          </div>
          <div className="max-h-80 overflow-auto divide-y divide-border/60">
            {notifs.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">Tudo em ordem.</div>
            )}
            {notifs.map((n) => (
              <div key={n.id} className="px-3 py-2.5 flex items-start gap-2.5 hover:bg-muted/40">
                <span className={`mt-1.5 h-1.5 w-1.5 rounded-full shrink-0 ${
                  n.kind === "success" ? "bg-success" :
                  n.kind === "warn" ? "bg-warning" :
                  n.kind === "error" ? "bg-destructive" : "bg-info"
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm leading-snug">{n.title}</div>
                  {n.desc && <div className="text-[11px] text-muted-foreground mt-0.5">{n.desc}</div>}
                  <div className="text-[10px] font-mono text-muted-foreground mt-1">{n.time}</div>
                </div>
              </div>
            ))}
          </div>
        </PopoverContent>
      </Popover>

      <Button size="sm" className="gap-1.5" onClick={() => navigate({ to: "/hypotheses" })}>
        <Zap className="h-4 w-4" /> Hipóteses
      </Button>
    </header>
  );
}
