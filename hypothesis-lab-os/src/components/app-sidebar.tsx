import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  BarChart3,
  Beaker,
  Boxes,
  CircuitBoard,
  FlaskConical,
  Gauge,
  LineChart,
  Plug,
  Radio,
  Shield,
  Unlock,
  Workflow,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const research = [
  { title: "Command Center", url: "/",            icon: Gauge },
  { title: "Hypotheses",     url: "/hypotheses",  icon: FlaskConical },
  { title: "D17 Dashboard",  url: "/d17",         icon: Unlock },
  { title: "Strategies",     url: "/strategies",  icon: Workflow },
  { title: "Simulations",    url: "/simulations", icon: Beaker },
];

const execution = [
  { title: "Paper Trading",  url: "/paper",       icon: LineChart },
  { title: "Live Trading",   url: "/live",        icon: Radio },
  { title: "Bot Orchestrator", url: "/bots",      icon: CircuitBoard },
];

const ops = [
  { title: "Risk Engine",    url: "/risk",        icon: Shield },
  { title: "Event Layer",    url: "/events",      icon: Activity },
  { title: "Brokers",        url: "/brokers",     icon: Plug },
  { title: "Analytics",      url: "/analytics",   icon: BarChart3 },
];

function NavSection({
  label,
  items,
}: {
  label: string;
  items: { title: string; url: string; icon: typeof Boxes }[];
}) {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="text-[10px] tracking-[0.18em] uppercase text-muted-foreground/70 font-mono">
        {label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((it) => {
            const active = pathname === it.url;
            return (
              <SidebarMenuItem key={it.url}>
                <SidebarMenuButton asChild isActive={active} className="data-[active=true]:bg-sidebar-accent data-[active=true]:text-primary">
                  <Link to={it.url} className="flex items-center gap-2">
                    <it.icon className="h-4 w-4" />
                    <span>{it.title}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

export function AppSidebar() {
  return (
    <Sidebar collapsible="icon" className="border-r">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-2">
          <div className="h-7 w-7 rounded-md bg-primary/15 border border-primary/40 grid place-items-center glow-primary">
            <Boxes className="h-4 w-4 text-primary" />
          </div>
          <div className="leading-none">
            <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">TradeLab</div>
            <div className="font-semibold text-sm">OS <span className="text-muted-foreground font-mono text-xs">v0.42</span></div>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <NavSection label="Research"  items={research} />
        <NavSection label="Execution" items={execution} />
        <NavSection label="Ops"       items={ops} />
      </SidebarContent>

      <SidebarFooter>
        <div className="px-2 py-2 text-[10px] font-mono text-muted-foreground flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
            cluster: eu-central-1
          </span>
          <span>p99 81ms</span>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
