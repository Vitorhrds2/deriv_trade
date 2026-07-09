import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Activity,
  BarChart3,
  Beaker,
  CircuitBoard,
  FlaskConical,
  Gauge,
  LineChart,
  OctagonX,
  Plug,
  Plus,
  Radio,
  Shield,
  Unlock,
  Workflow,
} from "lucide-react";
import { useApp } from "@/lib/store";
import { toast } from "sonner";
import { Dot } from "@/components/kit";
import { realHypotheses, type HypStatus } from "@/lib/hypotheses-data";

const routes = [
  { to: "/",            label: "Command Center", icon: Gauge },
  { to: "/hypotheses",  label: "Hypothesis Engine", icon: FlaskConical },
  { to: "/d17",         label: "D17 Dashboard", icon: Unlock },
  { to: "/strategies",  label: "Strategy Builder", icon: Workflow },
  { to: "/simulations", label: "Simulations", icon: Beaker },
  { to: "/paper",       label: "Paper Trading", icon: LineChart },
  { to: "/live",        label: "Live Trading", icon: Radio },
  { to: "/bots",        label: "Bot Orchestrator", icon: CircuitBoard },
  { to: "/risk",        label: "Risk Engine", icon: Shield },
  { to: "/events",      label: "Event Layer", icon: Activity },
  { to: "/brokers",     label: "Brokers", icon: Plug },
  { to: "/analytics",   label: "Analytics", icon: BarChart3 },
] as const;

function hypDotTone(s: HypStatus): "pos" | "neg" | "warn" | "muted" | "info" {
  switch (s) {
    case "live": return "pos";
    case "validating": return "warn";
    case "weak-signal": return "info";
    case "refuted": return "neg";
    default: return "muted";
  }
}

export function CommandPalette() {
  const open = useApp((s) => s.paletteOpen);
  const setOpen = useApp((s) => s.setPaletteOpen);
  const setKillOpen = useApp((s) => s.setKillOpen);
  const selectHyp = useApp((s) => s.selectHyp);
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  // Reset the query whenever the palette closes so it doesn't reopen mid-search.
  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  const go = (to: string) => {
    setOpen(false);
    navigate({ to });
  };

  const goHyp = (id: string) => {
    setOpen(false);
    selectHyp(id);
    navigate({ to: "/hypotheses" });
  };

  const hypItems = useMemo(
    () =>
      realHypotheses.map((h) => ({
        h,
        searchValue: `${h.id} ${h.title} ${h.market} ${h.tags.join(" ")}`,
      })),
    [],
  );

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        value={search}
        onValueChange={setSearch}
        placeholder="Buscar páginas, ações, hipóteses, bots…"
      />
      <CommandList>
        <CommandEmpty>Nada encontrado.</CommandEmpty>
        <CommandGroup heading="Navegar">
          {routes.map((r) => (
            <CommandItem key={r.to} value={r.label} onSelect={() => go(r.to)}>
              <r.icon className="h-4 w-4 mr-2" />
              {r.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Ações">
          <CommandItem
            value="nova hipótese"
            onSelect={() => {
              setOpen(false);
              toast.success("Nova hipótese criada", { description: "HYP-0143 (rascunho)" });
              navigate({ to: "/hypotheses" });
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Nova hipótese
          </CommandItem>
          <CommandItem
            value="kill switch"
            className="text-destructive data-[selected=true]:text-destructive"
            onSelect={() => {
              setOpen(false);
              setKillOpen(true);
            }}
          >
            <OctagonX className="h-4 w-4 mr-2" />
            Acionar kill switch
          </CommandItem>
        </CommandGroup>
        {search.trim() !== "" && (
          <>
            <CommandSeparator />
            <CommandGroup heading={`Hipóteses (${realHypotheses.length} no catálogo)`}>
              {hypItems.map(({ h, searchValue }) => (
                <CommandItem key={h.id} value={searchValue} onSelect={() => goHyp(h.id)}>
                  <Dot tone={hypDotTone(h.status)} className="mr-1" />
                  <span className="font-mono text-[11px] text-muted-foreground shrink-0">{h.id}</span>
                  <span className="truncate">{h.title}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
