// Global app store: selections, filters, kill switch, live tick, notifications.
import { create } from "zustand";
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
      bots: s.bots.map((b: any) =>
        b.env === "live" ? { ...b, state: "stopped", cpu: 0, memory: 0 } : b,
      ),
    })),
  resume: () => set({ killed: false }),

  // Sem eventos fabricados: notificações reais (ex.: hft_bot offline) devem ser
  // empurradas via pushNotif() por quem detectar a condição real (ver useHftAlerts).
  notifs: [],
  pushNotif: (n) =>
    set((s) => ({
      notifs: [{ ...n, id: `n${Date.now()}`, time: now() }, ...s.notifs].slice(0, 30),
    })),
  markAllRead: () => set((s) => ({ notifs: s.notifs.map((n) => ({ ...n, read: true })) })),
}));
