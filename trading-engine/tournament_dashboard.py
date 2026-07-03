import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


INDEX_HTML = r"""
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NYSE Model Tournament Floor</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #04070a;
      --panel: #0a1017;
      --panel2: #0d151f;
      --ink: #e7eef7;
      --muted: #7d8da3;
      --line: #1e2a36;
      --green: #25d07d;
      --green2: #0f7f4c;
      --red: #ff4f5e;
      --red2: #9c1f2f;
      --amber: #f5b83b;
      --blue: #4aa3ff;
      --violet: #a87cff;
      --mono: "JetBrains Mono", "Cascadia Mono", Consolas, ui-monospace, monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at 10% -10%, rgba(37,208,125,0.12), transparent 30%),
        radial-gradient(circle at 90% 0%, rgba(255,79,94,0.10), transparent 28%),
        linear-gradient(180deg, #05090d 0%, #020406 100%);
      color: var(--ink);
      font-family: var(--sans);
      letter-spacing: 0;
      overflow-x: hidden;
    }
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: repeating-linear-gradient(to bottom, transparent 0 3px, rgba(255,255,255,0.018) 3px 4px);
      mix-blend-mode: screen;
      opacity: 0.65;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      min-height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      border-bottom: 1px solid rgba(37,208,125,0.25);
      background: rgba(4,7,10,0.92);
      backdrop-filter: blur(18px);
      box-shadow: 0 18px 60px -45px rgba(37,208,125,0.55);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .logo {
      width: 44px;
      height: 44px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(37,208,125,0.45);
      border-radius: 6px;
      color: var(--green);
      background: linear-gradient(135deg, rgba(37,208,125,0.16), rgba(74,163,255,0.08));
      font-family: var(--mono);
      font-weight: 800;
      box-shadow: inset 0 0 18px rgba(37,208,125,0.10);
    }
    .eyebrow {
      color: var(--muted);
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
    }
    h1, h2, h3, p { margin: 0; }
    h1 {
      font-size: clamp(22px, 2.5vw, 34px);
      line-height: 1;
      font-weight: 800;
      white-space: nowrap;
    }
    h2 {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 13px;
      font-weight: 760;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }
    .terminal {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    .controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    select, button {
      min-height: 34px;
      border: 1px solid var(--line);
      background: #071018;
      color: var(--ink);
      border-radius: 6px;
      padding: 0 10px;
      font: 600 12px var(--mono);
    }
    select:disabled {
      opacity: 1;
      cursor: default;
      color: var(--green);
      border-color: rgba(37,208,125,0.35);
      background: rgba(37,208,125,0.08);
    }
    button {
      border-color: rgba(37,208,125,0.45);
      color: var(--green);
      cursor: pointer;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-height: 28px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 5px 8px;
      font: 700 10px var(--mono);
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      background: rgba(255,255,255,0.025);
      white-space: nowrap;
    }
    .pill.good { color: var(--green); border-color: rgba(37,208,125,0.35); background: rgba(37,208,125,0.08); }
    .pill.bad { color: var(--red); border-color: rgba(255,79,94,0.35); background: rgba(255,79,94,0.08); }
    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 14px currentColor;
    }
    .tape {
      overflow: hidden;
      border-bottom: 1px solid rgba(37,208,125,0.18);
      background: rgba(0,0,0,0.35);
      mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
    }
    .tape-track {
      display: flex;
      width: max-content;
      animation: ticker 28s linear infinite;
    }
    .quote {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 174px;
      padding: 9px 14px;
      border-right: 1px solid rgba(255,255,255,0.06);
      font: 700 12px var(--mono);
      white-space: nowrap;
    }
    @keyframes ticker {
      from { transform: translateX(0); }
      to { transform: translateX(-50%); }
    }
    .layout {
      display: grid;
      grid-template-columns: 310px 1fr;
      gap: 12px;
      padding: 12px;
      max-width: 1900px;
      margin: 0 auto;
    }
    .side, .panel {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.035), transparent),
        var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 60px -52px rgba(37,208,125,0.55);
    }
    .side {
      align-self: start;
      position: sticky;
      top: 96px;
    }
    .side-header {
      padding: 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(37,208,125,0.04);
    }
    .metric {
      padding: 11px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .metric:last-child { border-bottom: 0; }
    .label {
      color: var(--muted);
      font: 700 10px var(--mono);
      text-transform: uppercase;
      letter-spacing: 0.16em;
    }
    .value {
      margin-top: 4px;
      font: 800 24px/1.05 var(--mono);
      word-break: break-word;
    }
    .small {
      margin-top: 4px;
      color: var(--muted);
      font: 600 11px var(--mono);
      line-height: 1.35;
      word-break: break-word;
    }
    .main-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 12px;
    }
    .span-8 { grid-column: span 8; }
    .span-7 { grid-column: span 7; }
    .span-6 { grid-column: span 6; }
    .span-5 { grid-column: span 5; }
    .span-4 { grid-column: span 4; }
    .span-12 { grid-column: span 12; }
    .stats-row {
      grid-column: span 12;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .stat {
      min-height: 92px;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01));
      overflow: hidden;
    }
    .stat .value { font-size: clamp(18px, 1.8vw, 28px); white-space: nowrap; }
    canvas {
      width: 100%;
      height: 310px;
      display: block;
      background: #070b10;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font: 12px var(--mono);
    }
    th, td {
      text-align: left;
      padding: 9px 10px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      vertical-align: middle;
      white-space: nowrap;
    }
    th {
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      background: rgba(255,255,255,0.02);
    }
    tbody tr:hover { background: rgba(37,208,125,0.05); }
    .scroll-x { overflow-x: auto; }
    .good { color: var(--green); }
    .bad { color: var(--red); }
    .warn { color: var(--amber); }
    .info { color: var(--blue); }
    .muted { color: var(--muted); }
    .rank {
      display: inline-grid;
      place-items: center;
      width: 30px;
      height: 24px;
      border-radius: 5px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.04);
      color: var(--muted);
      font-weight: 800;
    }
    .rank.top {
      color: var(--amber);
      border-color: rgba(245,184,59,0.55);
      background: rgba(245,184,59,0.12);
    }
    .board {
      display: grid;
      gap: 2px;
      padding: 12px;
      font: 700 11px var(--mono);
    }
    .heat {
      grid-template-columns: 1.25fr repeat(6, minmax(40px, 1fr));
    }
    .heat > div {
      min-height: 34px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 4px;
      color: var(--ink);
      overflow: hidden;
    }
    .heat .axis {
      color: var(--muted);
      background: rgba(255,255,255,0.02);
      justify-content: start;
      padding-left: 8px;
    }
    .depth {
      padding: 12px;
      font: 700 12px var(--mono);
    }
    .level {
      position: relative;
      display: grid;
      grid-template-columns: 56px 1fr 72px 48px;
      gap: 8px;
      align-items: center;
      min-height: 28px;
      border-bottom: 1px solid rgba(255,255,255,0.055);
      overflow: hidden;
    }
    .level::before {
      content: "";
      position: absolute;
      top: 4px;
      bottom: 4px;
      opacity: 0.22;
      border-radius: 3px;
      width: var(--w);
      background: var(--c);
      right: var(--right);
      left: var(--left);
    }
    .level span { position: relative; z-index: 1; }
    .feed {
      max-height: 300px;
      overflow: hidden;
      font: 700 11px var(--mono);
    }
    .feed-row {
      display: grid;
      grid-template-columns: 88px 1.25fr 1fr 72px;
      gap: 8px;
      padding: 8px 10px;
      border-bottom: 1px solid rgba(255,255,255,0.055);
    }
    .flash-good { animation: flashGood 0.9s ease-out; }
    .flash-bad { animation: flashBad 0.9s ease-out; }
    @keyframes flashGood {
      0% { background: rgba(37,208,125,0.22); }
      100% { background: transparent; }
    }
    @keyframes flashBad {
      0% { background: rgba(255,79,94,0.22); }
      100% { background: transparent; }
    }
    @media (max-width: 1180px) {
      .layout { grid-template-columns: 1fr; }
      .side { position: static; }
      .span-8, .span-7, .span-6, .span-5, .span-4 { grid-column: span 12; }
      .stats-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .topbar { align-items: flex-start; flex-direction: column; }
      h1 { white-space: normal; }
    }
    @media (max-width: 620px) {
      .stats-row { grid-template-columns: 1fr; }
      .layout { padding: 8px; }
      .topbar { padding: 12px; }
      .controls { width: 100%; justify-content: stretch; }
      select, button { flex: 1; min-width: 0; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="logo">NYSE</div>
      <div>
        <div class="eyebrow">deriv demo / model tournament / floor 7a</div>
        <h1>Model Tournament Floor</h1>
      </div>
    </div>
    <div class="controls">
      <span id="clock" class="pill good"><span class="dot"></span>--:--:-- ET</span>
      <span id="jobPill" class="pill">JOB</span>
      <span id="moneyLock" class="pill bad">REAL MONEY BLOCKED</span>
      <select id="modelSelect" title="auto-selected active model" disabled></select>
      <button id="refreshBtn">AUTO 1S</button>
    </div>
  </header>

  <div class="tape"><div id="tickerTrack" class="tape-track"></div></div>

  <main class="layout">
    <aside class="side">
      <div class="side-header">
        <div class="eyebrow">active contract</div>
        <div id="currentModel" class="value">-</div>
        <div id="currentSub" class="small">-</div>
      </div>
      <div class="metric"><div class="label">Status</div><div id="status" class="value">-</div></div>
      <div class="metric"><div class="label">Phase</div><div id="phase" class="value">-</div></div>
      <div class="metric"><div class="label">Trades / Target</div><div id="trades" class="value">-</div></div>
      <div class="metric"><div class="label">Model P&L</div><div id="pnl" class="value">-</div></div>
      <div class="metric"><div class="label">Win Rate</div><div id="wr" class="value">-</div></div>
      <div class="metric"><div class="label">Last Event</div><div id="lastEvent" class="small">-</div></div>
    </aside>

    <div class="main-grid">
      <div class="stats-row">
        <div class="stat"><div class="label">MTX Composite</div><div id="mtx" class="value good">-</div><div id="mtxDelta" class="small">-</div></div>
        <div class="stat"><div class="label">Champion P&L</div><div id="champPnl" class="value">-</div><div id="champName" class="small">-</div></div>
        <div class="stat"><div class="label">Gate 30 -> 100</div><div id="gate" class="value">-</div><div class="small">PnL positive only</div></div>
        <div class="stat"><div class="label">Backlog</div><div id="backlog" class="value bad">-</div><div class="small">failed / pivoted</div></div>
        <div class="stat"><div class="label">Latency p95</div><div id="latency" class="value warn">-</div><div class="small">buy ack / settle path</div></div>
        <div class="stat"><div class="label">Signal RPM</div><div id="rpm" class="value info">-</div><div class="small">synthetic floor pulse</div></div>
      </div>

      <section class="panel span-8">
        <h2>MTX Alpha Curve <span class="terminal">MODEL_PNL / NULL_BENCH / LIVE</span></h2>
        <canvas id="lineChart" width="980" height="320"></canvas>
      </section>

      <section class="panel span-4">
        <h2>Tournament Ladder <span class="terminal">rank / gate / pnl</span></h2>
        <div class="scroll-x">
          <table>
            <thead><tr><th>#</th><th>Model</th><th>Phase</th><th>P&L</th><th>WR</th></tr></thead>
            <tbody id="ladderTable"></tbody>
          </table>
        </div>
      </section>

      <section class="panel span-4">
        <h2>Signed Volume Burst <span class="terminal">BUY / SELL</span></h2>
        <canvas id="barChart" width="760" height="300"></canvas>
      </section>

      <section class="panel span-4">
        <h2>NBBO Depth Ladder <span class="terminal">L1 / QPOS</span></h2>
        <div id="depth" class="depth"></div>
      </section>

      <section class="panel span-4">
        <h2>Cross-Asset Heat Grid <span class="terminal">OFI / VPIN / SOR</span></h2>
        <div id="heat" class="board heat"></div>
      </section>

      <section class="panel span-5">
        <h2>Market Micro Tape <span class="terminal">FIX 4.4 / ROUTE ACK</span></h2>
        <div id="microTape" class="feed"></div>
      </section>

      <section class="panel span-7">
        <h2>Execution Blotter <span class="terminal">PAPER FILL / SETTLE / MODEL VOTE</span></h2>
        <div class="scroll-x">
          <table>
            <thead>
              <tr><th>Time</th><th>Event</th><th>Model</th><th>Side</th><th>Move</th><th>Latency</th><th>P&L</th></tr>
            </thead>
            <tbody id="blotterTable"></tbody>
          </table>
        </div>
      </section>
    </div>
  </main>

  <script>
    const els = {
      clock: document.getElementById('clock'),
      tickerTrack: document.getElementById('tickerTrack'),
      jobPill: document.getElementById('jobPill'),
      modelSelect: document.getElementById('modelSelect'),
      refreshBtn: document.getElementById('refreshBtn'),
      status: document.getElementById('status'),
      phase: document.getElementById('phase'),
      currentModel: document.getElementById('currentModel'),
      currentSub: document.getElementById('currentSub'),
      trades: document.getElementById('trades'),
      pnl: document.getElementById('pnl'),
      wr: document.getElementById('wr'),
      lastEvent: document.getElementById('lastEvent'),
      mtx: document.getElementById('mtx'),
      mtxDelta: document.getElementById('mtxDelta'),
      champPnl: document.getElementById('champPnl'),
      champName: document.getElementById('champName'),
      gate: document.getElementById('gate'),
      backlog: document.getElementById('backlog'),
      latency: document.getElementById('latency'),
      rpm: document.getElementById('rpm'),
      line: document.getElementById('lineChart'),
      bar: document.getElementById('barChart'),
      heat: document.getElementById('heat'),
      depth: document.getElementById('depth'),
      microTape: document.getElementById('microTape'),
      ladderTable: document.getElementById('ladderTable'),
      blotterTable: document.getElementById('blotterTable'),
    };

    const tickers = ['MTX', '1HZ100V', 'R_100', 'OFI.Z', 'NBBO.W', 'SOR.ACK', 'CVaR99', 'VPIN.F', 'LULD.B', 'FIX.RTT', 'MOC.IMB', 'DARK.Q'];
    const heatCols = ['OFI', 'GAMMA', 'NBBO', 'VPIN', 'LULD', 'SOR'];
    const heatRows = ['OPEN_AUCTION', 'MIDDAY_CROSS', 'POWER_HOUR', 'DARK_ROUTING', 'MOC_STACK'];
    const codes = ['NBBO_LOCK', 'SOR_ACK', 'DARKX_FILL', 'OFI_ZSCORE', 'REGNMS_605', 'ARCA_QPOS', 'IEX_DPEG', 'BZX_REBATE', 'CVaR_99', 'KAPPA_DRIFT', 'TWAP_RESID', 'VPIN_FAST'];
    let marketTick = 0;
    let appState = {models: [], current_model_index: 0, status: 'loading'};
    let appEvents = [];
    let refreshInFlight = false;

    function wave(seed, amp = 1) {
      return Math.sin((marketTick + seed * 7) / (3.1 + (seed % 5))) * amp + Math.cos((marketTick + seed * 2) / 5.9) * amp * 0.48;
    }
    function money(value) {
      const num = Number(value || 0);
      return (num >= 0 ? '+$' : '-$') + Math.abs(num).toFixed(2);
    }
    function signed(value, digits = 2) {
      const num = Number(value || 0);
      return (num >= 0 ? '+' : '') + num.toFixed(digits);
    }
    function pct(value) {
      return Number.isFinite(value) ? `${Math.round(value)}%` : '-';
    }
    function cssTone(value) {
      return Number(value || 0) >= 0 ? 'good' : 'bad';
    }
    function selectedModel(state = appState) {
      const activeId = state.models?.[state.current_model_index]?.id || state.last_event?.model_id;
      return state.models.find(m => m.id === activeId) || state.models[state.current_model_index] || state.models[0];
    }
    function modelScore(model) {
      const trades = Number(model?.trades || 0);
      const pendingPenalty = trades === 0 || model?.status === 'pending' ? 100000 : 0;
      return Number(model?.pnl || 0) - pendingPenalty;
    }
    function modelWr(model) {
      const trades = Number(model?.trades || 0);
      return trades ? (Number(model?.wins || 0) / trades) * 100 : NaN;
    }
    function p95(values) {
      const nums = (values || []).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
      if (!nums.length) return NaN;
      return nums[Math.min(nums.length - 1, Math.floor(nums.length * 0.95))];
    }
    function hhmmss() {
      const base = 9 * 3600 + 30 * 60 + (marketTick * 2) % (6.5 * 3600);
      const h = Math.floor(base / 3600);
      const m = Math.floor((base % 3600) / 60);
      const s = Math.floor(base % 60);
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')} ET`;
    }
    function clearCanvas(ctx, canvas) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#070b10';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    function drawGrid(ctx, w, h) {
      ctx.strokeStyle = 'rgba(126,141,163,0.16)';
      ctx.lineWidth = 1;
      for (let x = 52; x < w - 12; x += 62) {
        ctx.beginPath(); ctx.moveTo(x, 20); ctx.lineTo(x, h - 38); ctx.stroke();
      }
      for (let y = 24; y < h - 36; y += 42) {
        ctx.beginPath(); ctx.moveTo(46, y); ctx.lineTo(w - 14, y); ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(126,141,163,0.45)';
      ctx.beginPath(); ctx.moveTo(46, 18); ctx.lineTo(46, h - 38); ctx.lineTo(w - 14, h - 38); ctx.stroke();
    }
    function drawLine(canvas, points) {
      const ctx = canvas.getContext('2d');
      clearCanvas(ctx, canvas);
      drawGrid(ctx, canvas.width, canvas.height);
      if (!points.length) return;
      const values = points.map(p => Number(p.pnl || 0));
      const min = Math.min(...values, 0);
      const max = Math.max(...values, 0);
      const span = Math.max(1, max - min);
      const x0 = 50, y0 = 24, w = canvas.width - 72, h = canvas.height - 64;
      const zeroY = y0 + h - ((0 - min) / span) * h;
      ctx.strokeStyle = 'rgba(126,141,163,0.55)';
      ctx.setLineDash([4, 5]);
      ctx.beginPath(); ctx.moveTo(x0, zeroY); ctx.lineTo(x0 + w, zeroY); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = x0 + (points.length === 1 ? 0 : (i / (points.length - 1)) * w);
        const y = y0 + h - ((Number(p.pnl || 0) - min) / span) * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      const grad = ctx.createLinearGradient(0, y0, 0, y0 + h);
      grad.addColorStop(0, 'rgba(37,208,125,0.28)');
      grad.addColorStop(1, 'rgba(37,208,125,0)');
      ctx.lineTo(x0 + w, y0 + h);
      ctx.lineTo(x0, y0 + h);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = x0 + (points.length === 1 ? 0 : (i / (points.length - 1)) * w);
        const y = y0 + h - ((Number(p.pnl || 0) - min) / span) * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = '#25d07d';
      ctx.lineWidth = 2.2;
      ctx.shadowColor = '#25d07d';
      ctx.shadowBlur = 12;
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.fillStyle = '#7d8da3';
      ctx.font = '11px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
      ctx.fillText(`hi ${money(max)}`, 58, 36);
      ctx.fillText(`lo ${money(min)}`, 58, canvas.height - 48);
    }
    function drawBars(canvas, models) {
      const ctx = canvas.getContext('2d');
      clearCanvas(ctx, canvas);
      drawGrid(ctx, canvas.width, canvas.height);
      const rows = [...models].sort((a, b) => Number(b.pnl || 0) - Number(a.pnl || 0));
      if (!rows.length) return;
      const values = rows.map(m => Number(m.pnl || 0));
      const maxAbs = Math.max(1, ...values.map(v => Math.abs(v)));
      const x0 = 54, baseY = canvas.height / 2, chartW = canvas.width - 78;
      const barW = Math.max(18, chartW / rows.length - 10);
      ctx.strokeStyle = 'rgba(126,141,163,0.52)';
      ctx.beginPath(); ctx.moveTo(46, baseY); ctx.lineTo(canvas.width - 14, baseY); ctx.stroke();
      rows.forEach((m, i) => {
        const v = Number(m.pnl || 0) + wave(i + 4, 0.18);
        const h = (Math.abs(v) / maxAbs) * (canvas.height / 2 - 38);
        const x = x0 + i * (barW + 10);
        const y = v >= 0 ? baseY - h : baseY;
        ctx.fillStyle = v >= 0 ? '#25d07d' : '#ff4f5e';
        ctx.fillRect(x, y, barW, Math.max(2, h));
        ctx.fillStyle = '#7d8da3';
        ctx.save();
        ctx.translate(x + 2, canvas.height - 10);
        ctx.rotate(-Math.PI / 5);
        ctx.fillText(m.id.replaceAll('_', '.').slice(0, 16), 0, 0);
        ctx.restore();
      });
    }
    function renderTape() {
      const quotes = tickers.map((symbol, i) => {
        const price = 18 + i * 8.3 + wave(i + 1, 2.2);
        const move = wave(i + 8, 2.6) + (i % 4 === 0 ? 0.4 : -0.15);
        return `<div class="quote"><span>${symbol}</span><span class="muted">${price.toFixed(2)}</span><span class="${cssTone(move)}">${signed(move)}%</span></div>`;
      }).join('');
      els.tickerTrack.innerHTML = quotes + quotes;
    }
    function renderDepth(model) {
      const mid = 800 + wave(2, 1.8) + Number(model?.pnl || 0) * 0.06;
      els.depth.innerHTML = Array.from({length: 12}, (_, i) => {
        const ask = i < 6;
        const level = ask ? 6 - i : i - 5;
        const price = mid + (ask ? level * 0.11 : -level * 0.11);
        const size = Math.max(3.8, 20 + wave(i + 22, 18) + level * 5);
        const venue = ['NYSE', 'ARCA', 'IEX', 'BZX', 'MEMX', 'DARK'][i % 6];
        const color = ask ? 'var(--red)' : 'var(--green)';
        return `<div class="level" style="--w:${Math.min(92, size)}%;--c:${color};--left:${ask ? 'auto' : '0'};--right:${ask ? '0' : 'auto'}">
          <span class="muted">${venue}</span><span class="${ask ? 'bad' : 'good'}">${price.toFixed(2)}</span><span>${size.toFixed(1)}k</span><span class="muted">${ask ? 'ASK' : 'BID'}</span>
        </div>`;
      }).join('');
    }
    function renderHeat() {
      let html = '<div></div>' + heatCols.map(c => `<div class="axis">${c}</div>`).join('');
      heatRows.forEach((row, r) => {
        html += `<div class="axis">${row}</div>`;
        heatCols.forEach((col, c) => {
          const v = wave(r * 9 + c + 12, 1.55);
          const alpha = Math.min(0.88, Math.abs(v) * 0.38 + 0.16);
          const color = v >= 0 ? `rgba(37,208,125,${alpha})` : `rgba(255,79,94,${alpha})`;
          html += `<div style="background:${color}" class="${v >= 0 ? 'good' : 'bad'}">${signed(v, 1)}</div>`;
        });
      });
      els.heat.innerHTML = html;
    }
    function renderMicroTape(state, events) {
      const recent = events.slice(-9).reverse();
      const rows = recent.length ? recent : Array.from({length: 9}, (_, i) => ({event: codes[i], model_id: 'WAITING_FOR_TAPE', pnl: wave(i, 0.4), ts: ''}));
      els.microTape.innerHTML = rows.map((e, i) => {
        const code = codes[(i + marketTick) % codes.length];
        const bp = wave(i + 31, 160);
        return `<div class="feed-row">
          <span class="muted">${hhmmss()}</span><span>${code}</span><span class="muted">${(e.model_id || '-').slice(0, 18)}</span><span class="${cssTone(bp)}">${signed(bp, 1)}bp</span>
        </div>`;
      }).join('');
    }
    function renderTables(state, events) {
      const ranked = [...(state.models || [])].sort((a, b) => modelScore(b) - modelScore(a));
      els.ladderTable.innerHTML = ranked.map((m, i) => {
        const wr = modelWr(m);
        return `<tr>
          <td><span class="rank ${i === 0 ? 'top' : ''}">${i + 1}</span></td>
          <td><strong>${m.id}</strong><div class="muted">${m.symbol || '-'} / ${m.kind || '-'}</div></td>
          <td>${m.phase || m.status || '-'}</td>
          <td class="${cssTone(m.pnl)}">${money(m.pnl)}</td>
          <td>${pct(wr)}</td>
        </tr>`;
      }).join('');
      els.blotterTable.innerHTML = events.slice(-12).reverse().map((e, i) => {
        const pnl = e.pnl ?? e.profit ?? 0;
        const t = e.ts ? e.ts.slice(11, 19) + 'Z' : hhmmss();
        return `<tr class="${i === 0 ? (Number(pnl) >= 0 ? 'flash-good' : 'flash-bad') : ''}">
          <td class="muted">${t}</td><td>${e.event || '-'}</td><td>${e.model_id || '-'}</td>
          <td class="${e.direction === 'DOWN' || e.contract_type === 'PUT' ? 'bad' : 'good'}">${e.contract_type || e.direction || '-'}</td>
          <td>${Number(e.move || 0).toFixed(4)}</td><td>${e.latency_ms ? Number(e.latency_ms).toFixed(0) + 'ms' : '-'}</td>
          <td class="${cssTone(pnl)}">${money(pnl)}</td>
        </tr>`;
      }).join('');
    }
    function renderState(state, events) {
      appState = state;
      appEvents = events;
      const ids = (state.models || []).map(m => m.id);
      const activeId = state.models?.[state.current_model_index]?.id || state.last_event?.model_id || ids[0] || '';
      els.modelSelect.innerHTML = ids.map(id => `<option value="${id}">${id}</option>`).join('');
      if (ids.includes(activeId)) els.modelSelect.value = activeId;
      const model = selectedModel(state);
      const champion = [...(state.models || [])].sort((a, b) => modelScore(b) - modelScore(a))[0];
      const wr = modelWr(model);
      const target = model?.phase === 'target100' ? state.target_trades : state.gate_trades;
      const settled = events.filter(e => e.event === 'settled' && (!model || e.model_id === model.id));
      const series = settled.map((e, i) => ({i, pnl: Number(e.pnl || 0)}));
      const p95Latency = p95(model?.latencies_ms);
      const composite = 10840 + (state.models || []).reduce((acc, m) => acc + Number(m.pnl || 0) * 18, 0) + wave(3, 45);

      els.clock.innerHTML = `<span class="dot"></span>${hhmmss()}`;
      els.jobPill.textContent = state.job_id || 'JOB';
      els.status.textContent = state.status || '-';
      els.phase.textContent = model?.phase || model?.status || '-';
      els.currentModel.textContent = model?.id || '-';
      els.currentSub.textContent = `${model?.symbol || '-'} / ${model?.kind || '-'} / ${model?.status || '-'}`;
      els.trades.textContent = `${model?.trades ?? 0} / ${target || '-'}`;
      els.pnl.textContent = money((Number(model?.pnl || 0) + wave(6, 0.08)));
      els.pnl.className = `value ${cssTone(model?.pnl)}`;
      els.wr.textContent = pct(wr);
      els.lastEvent.textContent = state.last_event ? `${state.last_event.event} / ${state.last_event.model_id || ''} / ${money(state.last_event.pnl ?? state.last_event.profit ?? 0)}` : '-';
      els.mtx.textContent = composite.toFixed(2);
      els.mtxDelta.textContent = `${signed(wave(11, 1.9), 2)}% / MTX.VPIN`;
      els.champPnl.textContent = champion ? money(champion.pnl) : '-';
      els.champPnl.className = `value ${cssTone(champion?.pnl)}`;
      els.champName.textContent = champion?.id || '-';
      els.gate.textContent = `${state.gate_trades || 30} -> ${state.target_trades || 100}`;
      els.backlog.textContent = String((state.backlog || []).length);
      els.latency.textContent = Number.isFinite(p95Latency) ? `${Math.round(p95Latency)}ms` : 'n/a';
      els.rpm.textContent = String(Math.round(4200 + Math.abs(wave(16, 3600))));

      drawLine(els.line, series);
      drawBars(els.bar, state.models || []);
      renderDepth(model);
      renderHeat();
      renderMicroTape(state, events);
      renderTables(state, events);
    }
    async function refresh() {
      if (refreshInFlight) return;
      refreshInFlight = true;
      try {
        const [stateRes, eventsRes] = await Promise.all([fetch('/api/state'), fetch('/api/events?limit=2500')]);
        const state = await stateRes.json();
        const events = await eventsRes.json();
        renderState(state, events);
        els.refreshBtn.textContent = `AUTO ${hhmmss().slice(0, 8)}`;
      } catch (err) {
        els.status.textContent = 'api_error';
        els.lastEvent.textContent = String(err && err.message ? err.message : err);
      } finally {
        refreshInFlight = false;
      }
    }
    document.getElementById('refreshBtn').addEventListener('click', refresh);
    setInterval(() => {
      marketTick += 1;
      renderTape();
      refresh();
    }, 1000);
    renderTape();
    refresh();
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    state_path = Path("strategy_tournament_state.json")
    events_path = Path("strategy_tournament_events.jsonl")

    def send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/state":
            if self.state_path.exists():
                self.send_json(json.loads(self.state_path.read_text(encoding="utf-8")))
            else:
                self.send_json({"status": "waiting_for_runner", "models": [], "current_model_index": 0})
            return
        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["2000"])[0])
            events = []
            if self.events_path.exists():
                lines = self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines[-limit:]:
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            self.send_json(events)
            return
        self.send_error(404)

    def log_message(self, format, *args):
        return


def parse_args():
    parser = argparse.ArgumentParser(description="Local dashboard for Deriv demo model tournament.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-json", default="strategy_tournament_state.json")
    parser.add_argument("--events-jsonl", default="strategy_tournament_events.jsonl")
    return parser.parse_args()


def main():
    args = parse_args()
    DashboardHandler.state_path = Path(args.state_json)
    DashboardHandler.events_path = Path(args.events_jsonl)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"dashboard_url=http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
