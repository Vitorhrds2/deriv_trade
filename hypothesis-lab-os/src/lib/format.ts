// Shared formatting utilities used across the dashboard (real-data pages only —
// see hypotheses-data.ts, hft-api.ts, unlock-api.ts for the actual data sources).

export function fmtMoney(n: number) {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtPct(n: number, digits = 1) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

// `sorted` must already be sorted ascending.
export function percentile(sorted: number[], p: number) {
  if (sorted.length === 0) return null;
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
}
