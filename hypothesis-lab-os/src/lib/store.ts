// Global mock-app store: bots, selections, filters, kill switch, live tick.
import { create } from "zustand";
import { bots as seedBots, type Bot } from "./mock-data";
import { realHypotheses as seedHyp, type HypStatus } from "./hypotheses-data";

export type Notif = {
  id: string;
  title: string;
  desc?: string;
  kind: "info" | "success" | "warn" | "error";
  time: string;
  read?: boolean;
};

type State = {
  // Live tick counter (driven by ticker)
  tick: number;
  bumpTick: () => void;

  // Bots
  bots: Bot[];
  setBotState: (id: string, state: Bot["state"]) => void;
  restartBot: (id: string) => void;

  // Hypotheses
  selectedHypId: string;
  selectHyp: (id: string) => void;
  hypFilter: string;
  setHypFilter: (s: string) => void;
  hypStatus: "all" | HypStatus;
  setHypStatus: (s: State["hypStatus"]) => void;

  // Global search / command palette
  paletteOpen: boolean;
  setPaletteOpen: (b: boolean) => void;
  globalQuery: string;
  setGlobalQuery: (s: string) => void;

  // Kill switch
  killOpen: boolean;
  setKillOpen: (b: boolean) => void;
  killed: boolean;
  kill: () => void;
  resume: () => void;

  // Notifications
  notifs: Notif[];
  pushNotif: (n: Omit<Notif, "id" | "time" | "read">) => void;
  markAllRead: () => void;
};

const now = () => new Date().toLocaleTimeString("en-US", { hour12: false }).slice(0, 8);

export const useApp = create<State>((set) => ({
  tick: 0,
  bumpTick: () => set((s) => ({ tick: s.tick + 1 })),

  bots: seedBots,
  setBotState: (id, state) =>
    set((s) => ({
      bots: s.bots.map((b) =>
        b.id === id
          ? {
              ...b,
              state,
              uptime: state === "running" ? (b.uptime === "—" ? "00d 00h" : b.uptime) : "—",
              cpu: state === "running" ? Math.max(b.cpu, 5) : 0,
              memory: state === "running" ? Math.max(b.memory, 12) : 0,
            }
          : b,
      ),
    })),
  restartBot: (id) =>
    set((s) => ({
      bots: s.bots.map((b) => (b.id === id ? { ...b, state: "recovering" } : b)),
    })),

  selectedHypId: seedHyp[0].id,
  selectHyp: (id) => set({ selectedHypId: id }),
  hypFilter: "",
  setHypFilter: (s) => set({ hypFilter: s }),
  hypStatus: "all",
  setHypStatus: (s) => set({ hypStatus: s }),

  paletteOpen: false,
  setPaletteOpen: (b) => set({ paletteOpen: b }),
  globalQuery: "",
  setGlobalQuery: (s) => set({ globalQuery: s }),

  killOpen: false,
  setKillOpen: (b) => set({ killOpen: b }),
  killed: false,
  kill: () =>
    set((s) => ({
      killed: true,
      killOpen: false,
      bots: s.bots.map((b) =>
        b.env === "live" ? { ...b, state: "stopped", cpu: 0, memory: 0 } : b,
      ),
    })),
  resume: () => set({ killed: false }),

  notifs: [
    {
      id: "n1",
      title: "CPI release detectado",
      desc: "actual 3.4% > forecast 3.2% — cpi-btc-prod abriu posição.",
      kind: "success",
      time: "12:04",
    },
    {
      id: "n2",
      title: "Latência Kalshi acima do SLO",
      desc: "p95 220ms > 150ms",
      kind: "warn",
      time: "12:01",
    },
    {
      id: "n3",
      title: "Bot nvda-drift-sim em erro",
      desc: "data feed disconnected",
      kind: "error",
      time: "11:32",
    },
  ],
  pushNotif: (n) =>
    set((s) => ({
      notifs: [{ ...n, id: `n${Date.now()}`, time: now() }, ...s.notifs].slice(0, 30),
    })),
  markAllRead: () => set((s) => ({ notifs: s.notifs.map((n) => ({ ...n, read: true })) })),
}));

// Helper: live equity / pnl derived from base + tick
export function liveDerivedPnl(tick: number, base = 2118.43) {
  return base + Math.sin(tick / 4) * 84 + Math.cos(tick / 7) * 56;
}
export function liveDerivedEquity(tick: number, base = 118_403.21) {
  return base + Math.sin(tick / 3) * 142 + tick * 0.7;
}
export function liveDerivedMid(tick: number, base = 67_412.7) {
  return base + Math.sin(tick / 2) * 12 + Math.cos(tick / 5) * 7;
}
