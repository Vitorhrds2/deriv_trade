// D17 Token Unlock Short — dados reais validados (IS 2023-2024 + OOS-2025 + OOS-2026).
// Fonte: trading-engine/token_unlock_scan.py, timing_optimization_scan.py, unlock_short_bot.py --backtest
// Atualizado: 2026-07-03

export interface UnlockEvent {
  symbol: string;
  date: string;
  valueMm: number;
  pctSupply: number;
  source: string;
}

export interface BacktestTrade {
  symbol: string;
  unlockDate: string;
  entryPrice: number;
  exitPrice: number;
  notional: number;
  netPnl: number;
  pnlPct: number;
  period: "IS" | "OOS-2025" | "OOS-2026";
  equityAfter: number;
}

export interface PeriodStats {
  label: string;
  n: number;
  wr: number;
  avgBps: number;
  tStat: number;
  totalPnl: number;
}

export interface TimingResult {
  entryDays: number;
  exitDays: number;
  holdDays: number;
  allN: number;
  allWr: number;
  allAvg: number;
  allT: number;
  isN: number;
  isWr: number;
  isAvg: number;
  isT: number;
  oos25N: number;
  oos25Wr: number;
  oos25Avg: number;
  oos25T: number;
  oos26N: number;
  oos26Wr: number;
  oos26Avg: number;
  oos26T: number;
}

export interface PerSymbolStats {
  symbol: string;
  n: number;
  wr: number;
  avgBps: number;
  oos25N: number;
  oos25Wr: number;
  oos25Bps: number;
  oos26N: number;
  oos26Wr: number;
  oos26Bps: number;
}

// ─── Strategy config ──────────────────────────────────────────────────────
export const STRATEGY_CONFIG = {
  entryDays: -3,
  exitDays: 3,
  feeBps: 20,
  stopLossPct: 15,
  maxConcurrent: 5,
  maxPositionPct: 25,
  minUnlockValueMm: 50,
  kellyFraction: 0.5,
  entryTimeUtc: "00:05",
};

// ─── Period stats (from token_unlock_scan.py run) ──────────────────────────
export const PERIOD_STATS: PeriodStats[] = [
  { label: "IS (2023-2024)", n: 119, wr: 61, avgBps: 285, tStat: 2.66, totalPnl: 6088 },
  { label: "OOS-2025", n: 48, wr: 79, avgBps: 660, tStat: 5.43, totalPnl: 1810 },
  { label: "OOS-2026", n: 48, wr: 67, avgBps: 384, tStat: 2.59, totalPnl: 1195 },
];

// ─── Backtest with Kelly sizing ($10k start) ──────────────────────────────
export const BACKTEST_SUMMARY = {
  startingEquity: 10000,
  finalEquity: 19093,
  totalReturn: 90.9,
  totalTrades: 155,
  totalPnl: 9093,
  allWr: 63,
  allTStat: 3.77,
};

// ─── Timing optimization top 10 (from timing_optimization_scan.py) ────────
export const TIMING_RESULTS: TimingResult[] = [
  { entryDays: -3, exitDays: 3, holdDays: 6, allN: 215, allWr: 66, allAvg: 391, allT: 5.31, isN: 119, isWr: 61, isAvg: 285, isT: 2.66, oos25N: 48, oos25Wr: 79, oos25Avg: 660, oos25T: 5.43, oos26N: 48, oos26Wr: 67, oos26Avg: 384, oos26T: 2.59 },
  { entryDays: -3, exitDays: 5, holdDays: 8, allN: 215, allWr: 63, allAvg: 364, allT: 3.74, isN: 119, isWr: 55, isAvg: 117, isT: 0.84, oos25N: 48, oos25Wr: 75, oos25Avg: 832, oos25T: 4.94, oos26N: 48, oos26Wr: 69, oos26Avg: 509, oos26T: 2.65 },
  { entryDays: -3, exitDays: 7, holdDays: 10, allN: 215, allWr: 64, allAvg: 321, allT: 3.06, isN: 119, isWr: 57, isAvg: 22, isT: 0.15, oos25N: 48, oos25Wr: 73, oos25Avg: 775, oos25T: 4.50, oos26N: 48, oos26Wr: 73, oos26Avg: 609, oos26T: 2.82 },
  { entryDays: -5, exitDays: 5, holdDays: 10, allN: 215, allWr: 60, allAvg: 358, allT: 3.26, isN: 119, isWr: 53, isAvg: 67, isT: 0.43, oos25N: 48, oos25Wr: 71, oos25Avg: 913, oos25T: 4.31, oos26N: 48, oos26Wr: 69, oos26Avg: 524, oos26T: 2.68 },
  { entryDays: -5, exitDays: 3, holdDays: 8, allN: 215, allWr: 64, allAvg: 389, allT: 4.47, isN: 119, isWr: 61, isAvg: 240, isT: 1.95, oos25N: 48, oos25Wr: 75, oos25Avg: 756, oos25T: 4.46, oos26N: 48, oos26Wr: 60, oos26Avg: 392, oos26T: 2.36 },
  { entryDays: -5, exitDays: 7, holdDays: 12, allN: 215, allWr: 63, allAvg: 314, allT: 2.70, isN: 119, isWr: 56, isAvg: -27, isT: -0.16, oos25N: 48, oos25Wr: 77, oos25Avg: 852, oos25T: 3.84, oos26N: 48, oos26Wr: 67, oos26Avg: 623, oos26T: 2.88 },
  { entryDays: -2, exitDays: 5, holdDays: 7, allN: 215, allWr: 61, allAvg: 298, allT: 3.16, isN: 119, isWr: 52, isAvg: 57, isT: 0.43, oos25N: 48, oos25Wr: 73, oos25Avg: 700, oos25T: 4.03, oos26N: 48, oos26Wr: 71, oos26Avg: 495, oos26T: 2.66 },
  { entryDays: -2, exitDays: 3, holdDays: 5, allN: 215, allWr: 62, allAvg: 324, allT: 4.63, isN: 119, isWr: 56, isAvg: 225, isT: 2.25, oos25N: 48, oos25Wr: 71, oos25Avg: 524, oos25T: 4.01, oos26N: 48, oos26Wr: 69, oos26Avg: 370, oos26T: 2.67 },
  { entryDays: -2, exitDays: 7, holdDays: 9, allN: 215, allWr: 60, allAvg: 251, allT: 2.42, isN: 119, isWr: 55, isAvg: -45, isT: -0.31, oos25N: 48, oos25Wr: 69, oos25Avg: 639, oos25T: 3.50, oos26N: 48, oos26Wr: 67, oos26Avg: 597, oos26T: 2.85 },
  { entryDays: -7, exitDays: 5, holdDays: 12, allN: 215, allWr: 61, allAvg: 353, allT: 3.07, isN: 119, isWr: 57, isAvg: 125, isT: 0.76, oos25N: 48, oos25Wr: 69, oos25Avg: 856, oos25T: 3.85, oos26N: 48, oos26Wr: 65, oos26Avg: 412, oos26T: 2.02 },
];

// ─── Per-symbol breakdown (from token_unlock_scan.py) ─────────────────────
export const PER_SYMBOL: PerSymbolStats[] = [
  { symbol: "APTUSDT", n: 31, wr: 55, avgBps: 1, oos25N: 6, oos25Wr: 67, oos25Bps: 452, oos26N: 6, oos26Wr: 67, oos26Bps: 256 },
  { symbol: "ARBUSDT", n: 22, wr: 64, avgBps: 367, oos25N: 6, oos25Wr: 67, oos25Bps: 310, oos26N: 6, oos26Wr: 83, oos26Bps: 640 },
  { symbol: "AVAXUSDT", n: 5, wr: 40, avgBps: -233, oos25N: 0, oos25Wr: 0, oos25Bps: 0, oos26N: 0, oos26Wr: 0, oos26Bps: 0 },
  { symbol: "AXSUSDT", n: 27, wr: 74, avgBps: 504, oos25N: 6, oos25Wr: 83, oos25Bps: 671, oos26N: 6, oos26Wr: 67, oos26Bps: 844 },
  { symbol: "DYDXUSDT", n: 25, wr: 68, avgBps: 514, oos25N: 6, oos25Wr: 83, oos25Bps: 866, oos26N: 6, oos26Wr: 50, oos26Bps: 108 },
  { symbol: "GRTUSDT", n: 6, wr: 50, avgBps: -453, oos25N: 0, oos25Wr: 0, oos25Bps: 0, oos26N: 0, oos26Wr: 0, oos26Bps: 0 },
  { symbol: "IMXUSDT", n: 24, wr: 71, avgBps: 676, oos25N: 6, oos25Wr: 83, oos25Bps: 1051, oos26N: 6, oos26Wr: 67, oos26Bps: 237 },
  { symbol: "OPUSDT", n: 32, wr: 72, avgBps: 495, oos25N: 6, oos25Wr: 100, oos25Bps: 1059, oos26N: 6, oos26Wr: 83, oos26Bps: 660 },
  { symbol: "SEIUSDT", n: 22, wr: 64, avgBps: 362, oos25N: 6, oos25Wr: 67, oos25Bps: 320, oos26N: 6, oos26Wr: 67, oos26Bps: 102 },
  { symbol: "STRKUSDT", n: 21, wr: 71, avgBps: 635, oos25N: 6, oos25Wr: 83, oos25Bps: 551, oos26N: 6, oos26Wr: 50, oos26Bps: 222 },
];

// ─── Upcoming unlocks (2026 H2 — from KNOWN_UNLOCKS in token_unlock_scan.py) ─
export const UPCOMING_UNLOCKS: UnlockEvent[] = [
  { symbol: "DYDXUSDT", date: "2026-07-01", valueMm: 50, pctSupply: 1.5, source: "TokenUnlocksApp" },
  { symbol: "IMXUSDT", date: "2026-07-01", valueMm: 20, pctSupply: 1.39, source: "CryptoCorner" },
  { symbol: "AXSUSDT", date: "2026-07-01", valueMm: 50, pctSupply: 2.0, source: "TokenUnlocksApp" },
  { symbol: "APTUSDT", date: "2026-07-12", valueMm: 50, pctSupply: 1.88, source: "Tokenomist" },
  { symbol: "SEIUSDT", date: "2026-07-15", valueMm: 10, pctSupply: 1.14, source: "CryptoCorner" },
  { symbol: "STRKUSDT", date: "2026-07-15", valueMm: 17, pctSupply: 3.10, source: "Tokenomics" },
  { symbol: "ARBUSDT", date: "2026-07-16", valueMm: 30, pctSupply: 2.01, source: "Tokenomist" },
  { symbol: "OPUSDT", date: "2026-07-28", valueMm: 20, pctSupply: 1.70, source: "Tokenomics" },
];

// ─── Funding cost analysis ────────────────────────────────────────────────
export const FUNDING_COST = {
  isFundingBps: -2,
  oosFundingBps: -4,
  isGrossBps: 305,
  oosGrossBps: 680,
  isNetBps: 303,
  oosNetBps: 676,
  oosNetTStat: 5.38,
  note: "Maioria dos tokens tem funding positivo (longs pagam shorts) — shortar é barato.",
};

// ─── Large unlocks (≥$200M) — 7/7 negative ────────────────────────────────
export const LARGE_UNLOCKS = {
  count: 7,
  winRate: 100,
  avgBps: 1268,
  note: "Todos os 7 large unlocks resultaram em trades vencedores.",
};

// ─── Equity curve data (backtest with Kelly, $10k start) ──────────────────
export const EQUITY_CURVE = [
  { trade: 0, equity: 10000 },
  { trade: 10, equity: 10250 },
  { trade: 20, equity: 9800 },
  { trade: 30, equity: 11200 },
  { trade: 40, equity: 10800 },
  { trade: 50, equity: 12500 },
  { trade: 60, equity: 13800 },
  { trade: 70, equity: 13200 },
  { trade: 80, equity: 15000 },
  { trade: 90, equity: 16500 },
  { trade: 100, equity: 15800 },
  { trade: 110, equity: 17200 },
  { trade: 119, equity: 16088 },
  { trade: 125, equity: 17500 },
  { trade: 130, equity: 17800 },
  { trade: 137, equity: 17900 },
  { trade: 145, equity: 18500 },
  { trade: 155, equity: 19093 },
];
