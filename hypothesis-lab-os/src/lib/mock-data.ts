// Centralized mock data for the TradeLab OS interface.

export type Status = "draft" | "validating" | "live" | "paused" | "archived";

export interface Hypothesis {
  id: string;
  title: string;
  market: string;
  thesis: string;
  confidence: number; // 0-100
  status: Status;
  tags: string[];
  trigger: string;
  invalidation: string;
  createdAt: string;
  author: string;
  pnl: number;
  trades: number;
}

export const hypotheses: Hypothesis[] = [
  {
    id: "HYP-0142",
    title: "CPI surpresa > consenso → BTC long",
    market: "BTC-PERP",
    thesis: "CPI acima do consenso historicamente expande risk-on em ativos cripto em janela de 4h.",
    confidence: 72,
    status: "live",
    tags: ["macro", "cripto", "event-driven"],
    trigger: "US CPI release (actual > forecast)",
    invalidation: "DXY +0.8% em 30min após release",
    createdAt: "2025-05-12",
    author: "lucas.q",
    pnl: 4820.31,
    trades: 18,
  },
  {
    id: "HYP-0139",
    title: "FOMC dovish → curva 2s10s steepener",
    market: "ZN-ZT",
    thesis: "Linguagem dovish do FOMC abre espaço para steepening da curva nos 60min seguintes.",
    confidence: 64,
    status: "validating",
    tags: ["rates", "fomc", "macro"],
    trigger: "FOMC statement keyword-score < -0.4",
    invalidation: "10y yield +6bps em 15min",
    createdAt: "2025-04-29",
    author: "marina.r",
    pnl: -312.4,
    trades: 6,
  },
  {
    id: "HYP-0137",
    title: "Polymarket → Election arb vs Kalshi",
    market: "POLY/KSHI",
    thesis: "Spread sustentado > 3% entre Polymarket e Kalshi para mesmo candidato.",
    confidence: 81,
    status: "live",
    tags: ["arbitragem", "prediction", "eleições"],
    trigger: "spread_abs > 0.03 por > 5min",
    invalidation: "spread cruza zero",
    createdAt: "2025-05-02",
    author: "tomas.k",
    pnl: 12_140.7,
    trades: 47,
  },
  {
    id: "HYP-0131",
    title: "Earnings drift NVDA pós-beat",
    market: "NVDA",
    thesis: "Post-earnings announcement drift de 3-5 sessões após beat > 8% no EPS.",
    confidence: 58,
    status: "draft",
    tags: ["equity", "earnings", "drift"],
    trigger: "EPS surprise > 8%",
    invalidation: "fechamento abaixo do gap inicial",
    createdAt: "2025-05-18",
    author: "lucas.q",
    pnl: 0,
    trades: 0,
  },
  {
    id: "HYP-0128",
    title: "Funding rate extremo → mean reversion",
    market: "ETH-PERP",
    thesis: "Funding > +0.05% por 3 períodos consecutivos antecede reversão de 2-4%.",
    confidence: 69,
    status: "paused",
    tags: ["cripto", "microestrutura"],
    trigger: "funding 3-bar > 0.05",
    invalidation: "preço +1.5% após sinal",
    createdAt: "2025-03-22",
    author: "marina.r",
    pnl: 2104.8,
    trades: 31,
  },
  {
    id: "HYP-0119",
    title: "Clima → futuros de gás natural",
    market: "NG=F",
    thesis: "Anomalia térmica > 2σ em regiões consumidoras antecipa squeeze de 3 dias.",
    confidence: 55,
    status: "archived",
    tags: ["commodities", "clima"],
    trigger: "NOAA anomaly z > 2",
    invalidation: "estoque EIA > consenso",
    createdAt: "2025-02-10",
    author: "tomas.k",
    pnl: 870.12,
    trades: 9,
  },
];

export interface Strategy {
  id: string;
  name: string;
  hypothesisId: string;
  language: "Python" | "TypeScript" | "Visual";
  status: Status;
  sharpe: number;
  drawdown: number;
  winRate: number;
  pnl: number;
  lastRun: string;
  broker: string;
}

export const strategies: Strategy[] = [
  { id: "STR-001", name: "cpi_btc_long_v3", hypothesisId: "HYP-0142", language: "Python", status: "live", sharpe: 2.14, drawdown: 6.2, winRate: 0.63, pnl: 4820.31, lastRun: "há 2min", broker: "Binance" },
  { id: "STR-002", name: "fomc_steepener", hypothesisId: "HYP-0139", language: "Python", status: "validating", sharpe: 0.91, drawdown: 4.1, winRate: 0.51, pnl: -312.4, lastRun: "há 1h", broker: "Tradier" },
  { id: "STR-003", name: "poly_kshi_arb", hypothesisId: "HYP-0137", language: "TypeScript", status: "live", sharpe: 3.47, drawdown: 2.1, winRate: 0.81, pnl: 12_140.7, lastRun: "há 12s", broker: "Polymarket+Kalshi" },
  { id: "STR-004", name: "nvda_drift_v1", hypothesisId: "HYP-0131", language: "Visual", status: "draft", sharpe: 1.32, drawdown: 8.4, winRate: 0.55, pnl: 0, lastRun: "—", broker: "Alpaca" },
  { id: "STR-005", name: "eth_funding_revert", hypothesisId: "HYP-0128", language: "Python", status: "paused", sharpe: 1.78, drawdown: 5.6, winRate: 0.59, pnl: 2104.8, lastRun: "há 3d", broker: "dYdX" },
  { id: "STR-006", name: "ng_weather_squeeze", hypothesisId: "HYP-0119", language: "Python", status: "archived", sharpe: 0.74, drawdown: 12.1, winRate: 0.48, pnl: 870.12, lastRun: "há 41d", broker: "OANDA" },
];

export interface Bot {
  id: string;
  name: string;
  strategyId: string;
  env: "paper" | "live";
  state: "running" | "stopped" | "error" | "recovering";
  uptime: string;
  cpu: number;
  memory: number;
  ordersToday: number;
  latencyMs: number;
}

export const bots: Bot[] = [
  { id: "BOT-01", name: "cpi-btc-prod", strategyId: "STR-001", env: "live", state: "running", uptime: "12d 04h", cpu: 14, memory: 38, ordersToday: 42, latencyMs: 81 },
  { id: "BOT-02", name: "poly-kshi-arb-prod", strategyId: "STR-003", env: "live", state: "running", uptime: "06d 11h", cpu: 22, memory: 51, ordersToday: 188, latencyMs: 64 },
  { id: "BOT-03", name: "fomc-steepener-sim", strategyId: "STR-002", env: "paper", state: "running", uptime: "01d 02h", cpu: 8, memory: 24, ordersToday: 11, latencyMs: 142 },
  { id: "BOT-04", name: "eth-funding-paper", strategyId: "STR-005", env: "paper", state: "stopped", uptime: "—", cpu: 0, memory: 0, ordersToday: 0, latencyMs: 0 },
  { id: "BOT-05", name: "nvda-drift-sim", strategyId: "STR-004", env: "paper", state: "error", uptime: "—", cpu: 0, memory: 0, ordersToday: 0, latencyMs: 0 },
];

export interface BrokerConn {
  name: string;
  type: "Crypto" | "Forex" | "Equity" | "Prediction";
  status: "connected" | "degraded" | "offline";
  region: string;
  balance: number;
  latencyMs: number;
}

export const brokers: BrokerConn[] = [
  { name: "Binance", type: "Crypto", status: "connected", region: "ap-east-1", balance: 38_410.22, latencyMs: 41 },
  { name: "dYdX", type: "Crypto", status: "connected", region: "us-east-1", balance: 12_018.41, latencyMs: 88 },
  { name: "OANDA", type: "Forex", status: "connected", region: "eu-west-1", balance: 9_120.0, latencyMs: 62 },
  { name: "Alpaca", type: "Equity", status: "degraded", region: "us-east-1", balance: 24_500.99, latencyMs: 240 },
  { name: "Polymarket", type: "Prediction", status: "connected", region: "us-east-1", balance: 7_402.10, latencyMs: 102 },
  { name: "Kalshi", type: "Prediction", status: "connected", region: "us-east-1", balance: 5_211.50, latencyMs: 118 },
  { name: "Bybit", type: "Crypto", status: "offline", region: "ap-east-1", balance: 0, latencyMs: 0 },
];

export interface MarketEvent {
  id: string;
  time: string;
  name: string;
  kind: "macro" | "earnings" | "onchain" | "politics" | "weather";
  impact: "low" | "med" | "high";
  consensus?: string;
  actual?: string;
}

export const events: MarketEvent[] = [
  { id: "EV-001", time: "08:30 ET", name: "US CPI YoY",         kind: "macro", impact: "high", consensus: "3.2%", actual: "3.4%" },
  { id: "EV-002", time: "14:00 ET", name: "FOMC Statement",     kind: "macro", impact: "high", consensus: "hold", actual: "hold" },
  { id: "EV-003", time: "16:05 ET", name: "NVDA Earnings",      kind: "earnings", impact: "high", consensus: "$0.74", actual: "—" },
  { id: "EV-004", time: "—",         name: "ETH stETH depeg watch", kind: "onchain", impact: "med" },
  { id: "EV-005", time: "06:00 ET",  name: "Election poll drop", kind: "politics", impact: "med" },
  { id: "EV-006", time: "—",         name: "Texas heatwave Δ+3σ", kind: "weather", impact: "low" },
];

export interface Trade {
  id: string;
  bot: string;
  side: "BUY" | "SELL";
  symbol: string;
  qty: number;
  price: number;
  pnl: number;
  time: string;
  venue: string;
}

export const trades: Trade[] = [
  { id: "T-9912", bot: "cpi-btc-prod",       side: "BUY",  symbol: "BTC-PERP", qty: 0.42, price: 67_412.5, pnl:  121.4, time: "12:04:11", venue: "Binance" },
  { id: "T-9911", bot: "poly-kshi-arb-prod", side: "SELL", symbol: "TRUMP-YES", qty: 850,  price: 0.62,     pnl:   84.0, time: "12:03:58", venue: "Polymarket" },
  { id: "T-9910", bot: "poly-kshi-arb-prod", side: "BUY",  symbol: "TRUMP-YES", qty: 850,  price: 0.59,     pnl:    0.0, time: "12:03:58", venue: "Kalshi" },
  { id: "T-9909", bot: "cpi-btc-prod",       side: "SELL", symbol: "BTC-PERP", qty: 0.38, price: 67_201.0, pnl:  -42.1, time: "11:59:02", venue: "Binance" },
  { id: "T-9908", bot: "fomc-steepener-sim", side: "BUY",  symbol: "ZN",      qty: 5,    price: 110.21,    pnl:   13.6, time: "11:48:23", venue: "Tradier" },
  { id: "T-9907", bot: "poly-kshi-arb-prod", side: "BUY",  symbol: "FED-CUT-Y", qty: 300, price: 0.41,     pnl:   18.0, time: "11:41:00", venue: "Polymarket" },
  { id: "T-9906", bot: "cpi-btc-prod",       side: "BUY",  symbol: "BTC-PERP", qty: 0.20, price: 67_055.8, pnl:   62.2, time: "11:30:09", venue: "Binance" },
];

// Equity curve (last 30 buckets)
export const equityCurve = Array.from({ length: 60 }, (_, i) => {
  const base = 100_000;
  const t = i / 59;
  const drift = 18_000 * t;
  const wave = Math.sin(i / 4) * 1800 + Math.cos(i / 9) * 1200;
  const noise = (Math.sin(i * 13.37) * 500);
  return {
    t: `D${i + 1}`,
    equity: Math.round(base + drift + wave + noise),
    benchmark: Math.round(base + 8000 * t + Math.sin(i / 6) * 800),
  };
});

export const pnlBars = Array.from({ length: 14 }, (_, i) => ({
  d: `D${i + 1}`,
  pnl: Math.round((Math.sin(i * 1.3) + Math.cos(i / 2)) * 1200 + (i % 3 === 0 ? -800 : 600)),
}));

export const riskBreakdown = [
  { name: "Crypto",      value: 42 },
  { name: "Prediction",  value: 23 },
  { name: "Equity",      value: 18 },
  { name: "Forex",       value: 11 },
  { name: "Rates",       value: 6 },
];

export const orderbook = {
  bids: Array.from({ length: 8 }, (_, i) => ({
    price: 67_412.5 - i * 0.5,
    size: +(Math.random() * 3 + 0.2).toFixed(3),
    cum: +(i * 1.4 + 0.6).toFixed(2),
  })),
  asks: Array.from({ length: 8 }, (_, i) => ({
    price: 67_413.0 + i * 0.5,
    size: +(Math.random() * 3 + 0.2).toFixed(3),
    cum: +(i * 1.4 + 0.6).toFixed(2),
  })),
};

export function statusBadgeClass(s: Status | Bot["state"] | BrokerConn["status"]) {
  switch (s) {
    case "live":
    case "running":
    case "connected":
      return "bg-success/15 text-success border-success/30";
    case "validating":
    case "recovering":
    case "degraded":
      return "bg-warning/15 text-warning border-warning/30";
    case "paused":
    case "stopped":
    case "draft":
      return "bg-muted text-muted-foreground border-border";
    case "error":
    case "offline":
      return "bg-destructive/15 text-destructive border-destructive/40";
    case "archived":
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function fmtMoney(n: number) {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
export function fmtPct(n: number, digits = 1) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}
