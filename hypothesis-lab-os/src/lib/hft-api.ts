// Server functions que consomem a status_api.py rodando na EC2 (18.199.174.178:8787),
// ao lado do hft_arbitrage_bot. Rodam no servidor (Cloudflare Worker em produção, Node em
// dev) e fazem um fetch() HTTP simples -- é o único transporte que o Worker suporta (sem
// SSH/subprocess). Se a EC2 estiver inacessível, retornam `connected: false` em vez de
// lançar erro, para as páginas mostrarem um estado "desconectado" honesto.
import { createServerFn } from "@tanstack/react-start";

const DEFAULT_STATUS_API_URL = "http://18.199.174.178:8787";

function apiBase(): string {
  return process.env.HFT_STATUS_API_URL ?? DEFAULT_STATUS_API_URL;
}

async function fetchJson<T>(path: string, timeoutMs = 4000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${apiBase()}${path}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export interface HftStatus {
  connected: boolean;
  tmuxSessionAlive: boolean;
  logAgeSeconds: number | null;
  logStale: boolean;
  lastErrorLine: string | null;
  recentLogLines: string[];
  error?: string;
}

export const getHftStatus = createServerFn({ method: "GET" }).handler(
  async (): Promise<HftStatus> => {
    try {
      const data = await fetchJson<{
        tmux_session_alive: boolean;
        log_age_seconds: number | null;
        log_stale: boolean;
        last_error_line: string | null;
        recent_log_lines: string[];
      }>("/api/hft/status");
      return {
        connected: true,
        tmuxSessionAlive: data.tmux_session_alive,
        logAgeSeconds: data.log_age_seconds,
        logStale: data.log_stale,
        lastErrorLine: data.last_error_line,
        recentLogLines: data.recent_log_lines ?? [],
      };
    } catch (e) {
      return {
        connected: false,
        tmuxSessionAlive: false,
        logAgeSeconds: null,
        logStale: true,
        lastErrorLine: null,
        recentLogLines: [],
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
);

export interface HftGroupSummary {
  n: number;
  wins: number;
  winRate: number;
  pnlTotal: number;
  evPerTrade: number;
}

const EMPTY_GROUP: HftGroupSummary = { n: 0, wins: 0, winRate: 0, pnlTotal: 0, evPerTrade: 0 };

export interface HftTrade {
  version: string;
  ts: string | null;
  direction: "UP" | "DOWN";
  group: "ALIGNED" | "ANTI";
  jump: number;
  formationMs: number;
  execMs: number | null;
  contractId: string | null;
  closeReason: string | null;
  profit: number | null;
}

export interface HftTradesResponse {
  connected: boolean;
  total: HftGroupSummary;
  aligned: HftGroupSummary;
  anti: HftGroupSummary;
  recentTrades: HftTrade[];
  error?: string;
}

function mapGroup(g: {
  n: number;
  wins: number;
  win_rate: number;
  pnl_total: number;
  ev_per_trade: number;
}): HftGroupSummary {
  return {
    n: g.n,
    wins: g.wins,
    winRate: g.win_rate,
    pnlTotal: g.pnl_total,
    evPerTrade: g.ev_per_trade,
  };
}

export const getHftTrades = createServerFn({ method: "GET" }).handler(
  async (): Promise<HftTradesResponse> => {
    try {
      const data = await fetchJson<{
        total: Parameters<typeof mapGroup>[0];
        aligned: Parameters<typeof mapGroup>[0];
        anti: Parameters<typeof mapGroup>[0];
        recent_trades: Array<{
          version: string;
          ts: string | null;
          direction: "UP" | "DOWN";
          group?: "ALIGNED" | "ANTI";
          jump: number;
          formation_ms: number;
          exec_ms: number | null;
          contract_id: string | null;
          close_reason: string | null;
          profit: number | null;
        }>;
      }>("/api/hft/trades");
      return {
        connected: true,
        total: mapGroup(data.total),
        aligned: mapGroup(data.aligned),
        anti: mapGroup(data.anti),
        recentTrades: (data.recent_trades ?? []).map((t) => ({
          version: t.version,
          ts: t.ts,
          direction: t.direction,
          group: t.group ?? "ALIGNED",
          jump: t.jump,
          formationMs: t.formation_ms,
          execMs: t.exec_ms,
          contractId: t.contract_id,
          closeReason: t.close_reason,
          profit: t.profit,
        })),
      };
    } catch (e) {
      return {
        connected: false,
        total: EMPTY_GROUP,
        aligned: EMPTY_GROUP,
        anti: EMPTY_GROUP,
        recentTrades: [],
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
);
