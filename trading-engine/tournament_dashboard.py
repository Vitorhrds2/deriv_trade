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
  <title>Deriv Demo Model Tournament</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #64748b;
      --line: #d7dde8;
      --green: #12805c;
      --red: #b42318;
      --blue: #2563eb;
      --amber: #b7791f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
      letter-spacing: 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 {
      font-size: 18px;
      margin: 0;
      font-weight: 700;
    }
    main {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 14px;
      padding: 14px;
    }
    aside, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .metric {
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
    }
    .metric:last-child { border-bottom: 0; }
    .label { color: var(--muted); font-size: 12px; }
    .value { font-size: 24px; font-weight: 750; margin-top: 3px; }
    select, button {
      min-height: 36px;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }
    canvas {
      width: 100%;
      height: 280px;
      display: block;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 650; }
    .good { color: var(--green); }
    .bad { color: var(--red); }
    .muted { color: var(--muted); }
    .controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Deriv Demo Model Tournament</h1>
    <div class="controls">
      <select id="modelSelect"></select>
      <button id="refreshBtn">Atualizar</button>
    </div>
  </header>
  <main>
    <aside>
      <div class="metric"><div class="label">Status</div><div id="status" class="value">-</div></div>
      <div class="metric"><div class="label">Modelo atual</div><div id="currentModel" class="value">-</div></div>
      <div class="metric"><div class="label">Trades do modelo</div><div id="trades" class="value">-</div></div>
      <div class="metric"><div class="label">PnL do modelo</div><div id="pnl" class="value">-</div></div>
      <div class="metric"><div class="label">Gate</div><div id="gate" class="value">30 -> 100</div></div>
      <div class="metric"><div class="label">Ultimo evento</div><div id="lastEvent" class="muted">-</div></div>
    </aside>
    <div class="grid">
      <section>
        <h2>PnL Ao Longo Do Tempo</h2>
        <canvas id="lineChart" width="760" height="280"></canvas>
      </section>
      <section>
        <h2>PnL Por Modelo</h2>
        <canvas id="barChart" width="760" height="280"></canvas>
      </section>
      <section>
        <h2>Distribuicao</h2>
        <canvas id="pieChart" width="760" height="280"></canvas>
      </section>
      <section>
        <h2>Modelos E Pivos</h2>
        <table>
          <thead>
            <tr><th>Modelo</th><th>Status</th><th>Trades</th><th>PnL</th><th>Motivo</th></tr>
          </thead>
          <tbody id="modelsTable"></tbody>
        </table>
      </section>
    </div>
  </main>
  <script>
    const els = {
      modelSelect: document.getElementById('modelSelect'),
      status: document.getElementById('status'),
      currentModel: document.getElementById('currentModel'),
      trades: document.getElementById('trades'),
      pnl: document.getElementById('pnl'),
      lastEvent: document.getElementById('lastEvent'),
      modelsTable: document.getElementById('modelsTable'),
      line: document.getElementById('lineChart'),
      bar: document.getElementById('barChart'),
      pie: document.getElementById('pieChart'),
    };

    function money(value) {
      const num = Number(value || 0);
      return (num >= 0 ? '+$' : '-$') + Math.abs(num).toFixed(2);
    }

    function clear(ctx, canvas) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    function drawAxes(ctx, w, h) {
      ctx.strokeStyle = '#d7dde8';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(44, 18);
      ctx.lineTo(44, h - 34);
      ctx.lineTo(w - 14, h - 34);
      ctx.stroke();
    }

    function drawLine(canvas, points) {
      const ctx = canvas.getContext('2d');
      clear(ctx, canvas);
      drawAxes(ctx, canvas.width, canvas.height);
      if (!points.length) return;
      const values = points.map(p => Number(p.pnl || 0));
      const min = Math.min(...values, 0);
      const max = Math.max(...values, 0);
      const span = Math.max(1, max - min);
      const x0 = 44, y0 = 18, w = canvas.width - 64, h = canvas.height - 52;
      ctx.strokeStyle = '#2563eb';
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = x0 + (points.length === 1 ? 0 : (i / (points.length - 1)) * w);
        const y = y0 + h - ((Number(p.pnl || 0) - min) / span) * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.strokeStyle = '#94a3b8';
      const zeroY = y0 + h - ((0 - min) / span) * h;
      ctx.beginPath(); ctx.moveTo(x0, zeroY); ctx.lineTo(x0 + w, zeroY); ctx.stroke();
      ctx.fillStyle = '#64748b';
      ctx.fillText(`max ${max.toFixed(2)}`, 52, 28);
      ctx.fillText(`min ${min.toFixed(2)}`, 52, canvas.height - 42);
    }

    function drawBars(canvas, models) {
      const ctx = canvas.getContext('2d');
      clear(ctx, canvas);
      drawAxes(ctx, canvas.width, canvas.height);
      if (!models.length) return;
      const values = models.map(m => Number(m.pnl || 0));
      const maxAbs = Math.max(1, ...values.map(v => Math.abs(v)));
      const x0 = 52, baseY = canvas.height / 2, chartW = canvas.width - 78;
      const barW = Math.max(18, chartW / models.length - 8);
      ctx.strokeStyle = '#94a3b8';
      ctx.beginPath(); ctx.moveTo(44, baseY); ctx.lineTo(canvas.width - 14, baseY); ctx.stroke();
      models.forEach((m, i) => {
        const v = Number(m.pnl || 0);
        const h = (Math.abs(v) / maxAbs) * (canvas.height / 2 - 32);
        const x = x0 + i * (barW + 8);
        const y = v >= 0 ? baseY - h : baseY;
        ctx.fillStyle = v >= 0 ? '#12805c' : '#b42318';
        ctx.fillRect(x, y, barW, h);
        ctx.fillStyle = '#17202a';
        ctx.save();
        ctx.translate(x + 2, canvas.height - 8);
        ctx.rotate(-Math.PI / 5);
        ctx.fillText(m.id.slice(0, 18), 0, 0);
        ctx.restore();
      });
    }

    function drawPie(canvas, model) {
      const ctx = canvas.getContext('2d');
      clear(ctx, canvas);
      const wins = Number(model?.wins || 0);
      const losses = Number(model?.losses || 0);
      const rejects = Number(model?.rejects || 0);
      const values = [
        ['wins', wins, '#12805c'],
        ['losses', losses, '#b42318'],
        ['rejects', rejects, '#b7791f'],
      ].filter(x => x[1] > 0);
      const total = values.reduce((acc, x) => acc + x[1], 0);
      if (!total) return;
      let start = -Math.PI / 2;
      const cx = canvas.width / 2, cy = canvas.height / 2, r = Math.min(canvas.width, canvas.height) / 3;
      values.forEach(([label, value, color]) => {
        const end = start + (value / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, start, end);
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
        start = end;
      });
      ctx.fillStyle = '#17202a';
      values.forEach(([label, value, color], i) => {
        ctx.fillStyle = color;
        ctx.fillRect(20, 24 + i * 22, 14, 14);
        ctx.fillStyle = '#17202a';
        ctx.fillText(`${label}: ${value}`, 42, 36 + i * 22);
      });
    }

    function selectedModel(state) {
      const selected = els.modelSelect.value;
      if (selected) return state.models.find(m => m.id === selected) || state.models[state.current_model_index];
      return state.models[state.current_model_index] || state.models[0];
    }

    async function refresh() {
      const [stateRes, eventsRes] = await Promise.all([fetch('/api/state'), fetch('/api/events')]);
      const state = await stateRes.json();
      const events = await eventsRes.json();
      const ids = state.models.map(m => m.id);
      const prev = els.modelSelect.value;
      els.modelSelect.innerHTML = ids.map(id => `<option value="${id}">${id}</option>`).join('');
      if (ids.includes(prev)) els.modelSelect.value = prev;
      const model = selectedModel(state);

      els.status.textContent = state.status || '-';
      els.currentModel.textContent = model?.id || '-';
      els.trades.textContent = String(model?.trades ?? '-');
      els.pnl.textContent = money(model?.pnl || 0);
      els.pnl.className = Number(model?.pnl || 0) >= 0 ? 'value good' : 'value bad';
      els.lastEvent.textContent = state.last_event ? `${state.last_event.event} ${state.last_event.model_id || ''}` : '-';

      els.modelsTable.innerHTML = state.models.map(m => (
        `<tr><td>${m.id}</td><td>${m.status}</td><td>${m.trades}</td>` +
        `<td class="${Number(m.pnl || 0) >= 0 ? 'good' : 'bad'}">${money(m.pnl)}</td>` +
        `<td>${m.pivot_reason || m.rationale || ''}</td></tr>`
      )).join('');

      const filtered = events
        .filter(e => e.event === 'settled')
        .filter(e => !model || e.model_id === model.id)
        .map(e => ({ts: e.ts, pnl: e.pnl}));
      drawLine(els.line, filtered);
      drawBars(els.bar, state.models);
      drawPie(els.pie, model);
    }

    document.getElementById('refreshBtn').addEventListener('click', refresh);
    els.modelSelect.addEventListener('change', refresh);
    refresh();
    setInterval(refresh, 3000);
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
