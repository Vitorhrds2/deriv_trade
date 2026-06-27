import { useEffect } from "react";
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
  Workflow,
} from "lucide-react";
import { useApp } from "@/lib/store";
import { toast } from "sonner";

const routes = [
  { to: "/",            label: "Command Center", icon: Gauge },
  { to: "/hypotheses",  label: "Hypothesis Engine", icon: FlaskConical },
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

export function CommandPalette() {
  const open = useApp((s) => s.paletteOpen);
  const setOpen = useApp((s) => s.setPaletteOpen);
  const setKillOpen = useApp((s) => s.setKillOpen);
  const navigate = useNavigate();

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

  const go = (to: string) => {
    setOpen(false);
    navigate({ to });
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Buscar páginas, ações, hipóteses…" />
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
      </CommandList>
    </CommandDialog>
  );
}
