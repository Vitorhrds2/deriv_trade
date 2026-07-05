// Client-side fetch para os endpoints /api/unlock/* servidos por status_api.py na EC2
// (18.199.174.178:8787, proxied via rewrite em vercel.json). status_api.py absorveu a lógica
// de unlock_status_api.py -- esse script legado (porta 8788) não é mais usado por nada e foi
// parado em 2026-07-05 (confirmado: nenhum path do frontend aponta pra 8788).
// CORS habilitado na API (Access-Control-Allow-Origin: *), então o browser
// pode fetch direto sem precisar de server function (evita timeout nas Vercel
// serverless functions que não conseguem reach a EC2).
const API_URL = "";

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

// ─── Types ─────────────────────────────────────────────────────────────────

export interface UnlockPosition {
  symbol: string;
  side: string;
  entry_price: number;
  notional: number;
  quantity: number;
  entry_time: string;
  unlock_date: string;
  unlock_value_mm: number;
  mode: string;
  stop_loss_price: number;
}

export interface UnlockConfig {
  entry_days: number;
  exit_days: number;
  fee_bps: number;
  stop_loss_pct: number;
  max_concurrent: number;
  max_position_pct: number;
  min_unlock_value_mm: number;
  kelly_fraction: number;
  entry_time_utc: string;
}

export interface UnlockStatus {
  connected: boolean;
  tmux_session_alive: boolean;
  mode: string;
  open_positions: UnlockPosition[];
  open_count: number;
  closed_count: number;
  total_pnl: number;
  win_rate: number;
  last_check: string | null;
  config: UnlockConfig | null;
  error?: string;
}

export interface UnlockTrade {
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  notional: number;
  quantity: number;
  entry_time: string;
  exit_time: string;
  unlock_date: string;
  unlock_value_mm: number;
  mode: string;
  gross_pnl: number;
  fees: number;
  net_pnl: number;
  pnl_pct: number;
  close_reason: string;
}

export interface PeriodStatsRaw {
  n: number;
  wr: number;
  avg_pnl: number;
  total_pnl: number;
  t_stat: number;
}

export interface EquityPoint {
  trade: number;
  equity: number;
}

export interface UnlockTradesResponse {
  connected: boolean;
  trades: UnlockTrade[];
  equity_curve: EquityPoint[];
  stats: {
    all: PeriodStatsRaw;
    is: PeriodStatsRaw;
    oos25: PeriodStatsRaw;
    oos26: PeriodStatsRaw;
  };
  starting_equity: number;
  final_equity: number;
  total_return_pct: number;
  error?: string;
}

export interface UpcomingUnlock {
  symbol: string;
  unlock_date: string;
  unlock_value_mm: number;
  pct_supply: number;
  source: string;
  entry_date: string;
  exit_date: string;
  days_until: number;
}

export interface UnlockScheduleResponse {
  connected: boolean;
  upcoming: UpcomingUnlock[];
  config: { entry_days: number; exit_days: number; min_unlock_value_mm: number };
  error?: string;
}

export interface PerSymbolRaw {
  symbol: string;
  n: number;
  wr: number;
  avg_pnl: number;
  total_pnl: number;
}

export interface UnlockStatsResponse {
  connected: boolean;
  period_stats: {
    all: PeriodStatsRaw;
    is: PeriodStatsRaw;
    oos25: PeriodStatsRaw;
    oos26: PeriodStatsRaw;
  };
  per_symbol: PerSymbolRaw[];
  total_trades: number;
  error?: string;
}

// ─── API functions (client-side fetch) ──────────────────────────────────────

export async function getUnlockStatus(): Promise<UnlockStatus> {
  try {
    return await fetchJson<UnlockStatus>("/api/unlock/status");
  } catch (e) {
    return {
      connected: false,
      tmux_session_alive: false,
      mode: "paper",
      open_positions: [],
      open_count: 0,
      closed_count: 0,
      total_pnl: 0,
      win_rate: 0,
      last_check: null,
      config: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function getUnlockTrades(): Promise<UnlockTradesResponse> {
  try {
    return await fetchJson<UnlockTradesResponse>("/api/unlock/trades");
  } catch (e) {
    return {
      connected: false,
      trades: [],
      equity_curve: [{ trade: 0, equity: 10000 }],
      stats: {
        all: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
        is: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
        oos25: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
        oos26: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
      },
      starting_equity: 10000,
      final_equity: 10000,
      total_return_pct: 0,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function getUnlockSchedule(): Promise<UnlockScheduleResponse> {
  try {
    return await fetchJson<UnlockScheduleResponse>("/api/unlock/schedule");
  } catch (e) {
    return {
      connected: false,
      upcoming: [],
      config: { entry_days: -3, exit_days: 3, min_unlock_value_mm: 50 },
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function getUnlockStats(): Promise<UnlockStatsResponse> {
  try {
    return await fetchJson<UnlockStatsResponse>("/api/unlock/stats");
  } catch (e) {
    return {
      connected: false,
      period_stats: {
        all: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
        is: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
        oos25: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
        oos26: { n: 0, wr: 0, avg_pnl: 0, total_pnl: 0, t_stat: 0 },
      },
      per_symbol: [],
      total_trades: 0,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
