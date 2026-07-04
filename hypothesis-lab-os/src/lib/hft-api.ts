// Client-side fetch para status_api.py rodando na EC2 (18.199.174.178:8787).
// CORS habilitado na API (Access-Control-Allow-Origin: *), então o browser
// pode fetch direto sem precisar de server function (evita timeout nas Vercel
// serverless functions que não conseguem reach a EC2).
const API_URL = "http://18.199.174.178:8787";

async function fetchJson<T>(path: string, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export interface GoldenHourDowntime {
  secondsToday: number;
  eventsToday: number;
  secondsTotal: number;
  eventsTotal: number;
}

const EMPTY_DOWNTIME: GoldenHourDowntime = {
  secondsToday: 0,
  eventsToday: 0,
  secondsTotal: 0,
  eventsTotal: 0,
};

export interface HftStatus {
  connected: boolean;
  tmuxSessionAlive: boolean;
  logAgeSeconds: number | null;
  logStale: boolean;
  lastErrorLine: string | null;
  recentLogLines: string[];
  goldenHourDowntime: GoldenHourDowntime;
  error?: string;
}

export async function getHftStatus(): Promise<HftStatus> {
  try {
    const data = await fetchJson<{
      tmux_session_alive: boolean;
      log_age_seconds: number | null;
      log_stale: boolean;
      last_error_line: string | null;
      recent_log_lines: string[];
      golden_hour_downtime?: {
        seconds_today: number | null;
        events_today: number;
        seconds_total: number | null;
        events_total: number;
      };
    }>("/api/hft/status");
    const dt = data.golden_hour_downtime;
    return {
      connected: true,
      tmuxSessionAlive: data.tmux_session_alive,
      logAgeSeconds: data.log_age_seconds,
      logStale: data.log_stale,
      lastErrorLine: data.last_error_line,
      recentLogLines: data.recent_log_lines ?? [],
      goldenHourDowntime: {
        secondsToday: dt?.seconds_today ?? 0,
        eventsToday: dt?.events_today ?? 0,
        secondsTotal: dt?.seconds_total ?? 0,
        eventsTotal: dt?.events_total ?? 0,
      },
    };
  } catch (e) {
    return {
      connected: false,
      tmuxSessionAlive: false,
      logAgeSeconds: null,
      logStale: true,
      lastErrorLine: null,
      recentLogLines: [],
      goldenHourDowntime: EMPTY_DOWNTIME,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

// O bot só loga em eventos (choque de preço, ordem, erro) -- não tem heartbeat periódico
// (deriv_tick_sync recebe ticks a cada ~1s mas não loga nenhum). Fora do golden hour
// (12-18 UTC) é normal o log ficar minutos sem nova linha mesmo com o processo saudável,
// então `logStale` sozinho NÃO é sinal confiável de "bot caiu" -- só tmux_session_alive é.
// Ver docs/progress notes 2026-07-01: log parado 33min com tmux vivo, fora do golden hour.
export function isHftLive(status: Pick<HftStatus, "connected" | "tmuxSessionAlive">): boolean {
  return status.connected && status.tmuxSessionAlive;
}

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

export async function getHftTrades(): Promise<HftTradesResponse> {
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
}
