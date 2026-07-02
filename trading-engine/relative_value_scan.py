"""T3 - Scanner de VALOR-RELATIVO com DGP conhecido (Deriv sinteticos).

O scan antigo (contract_edge_scan.py) so olhou contratos de 1 TICK ATM. Este varre a
dimensao que ele ignorou: a DURACAO do Rise/Fall (CALL/PUT). A tese: a margem da casa
pode VARIAR com a duracao; se houver uma duracao onde a margem e minima ou INVERTE
(edge>0), e valor-relativo exploravel.

Rigor (3 medidas independentes por celula do grid):
  1. P_emp   : prob de vitoria MEDIDA nos ticks historicos (janelas deslizantes).
  2. P_teo   : prob TEORICA do GBM auto-calibrado (mu,sigma dos log-retornos do proprio
               feed -> P(soma de d log-rets > 0) = Phi(mu*sqrt(d)/sigma)). Cross-check do
               DGP: se P_emp ~ P_teo, o modelo bate e nao ha path-dependence escondida.
  3. payout  : gross_return REAL ao vivo (API proposal).
edge = P_emp - 1/gross_return ; EV/$1 = P_emp*gross_return - 1.
Pessimista: so crava edge se o PISO de Wilson de P ainda der EV>0.

Uso:
  python relative_value_scan.py --symbols R_100,1HZ100V --chunks 30 --durations 1,2,3,5,7,10
"""
import argparse
import asyncio
import math
import os
import sys
from statistics import mean, pstdev

from dotenv import load_dotenv
from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
STAKE = 10.0
Z = 1.96  # IC95%


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def wilson(successes, n, z=Z):
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


async def fetch_prices(client, symbol, chunks, delay=0.7):
    current_end, prices = "latest", []
    for i in range(chunks):
        res = None
        for attempt in range(4):
            res = await client.send_request({
                "ticks_history": symbol, "adjust_start_time": 1,
                "count": 5000, "end": current_end, "style": "ticks",
            })
            if "error" not in res:
                break
            await asyncio.sleep(2 ** (attempt + 1))
        if res is None or "error" in res:
            break
        hist = res.get("history", {})
        times, pr = hist.get("times", []), hist.get("prices", [])
        if not pr or not times:
            break
        prices = list(pr) + prices
        current_end = times[0] - 1
        await asyncio.sleep(delay)
    return [float(p) for p in prices]


async def get_gross_return(client, symbol, ct, duration):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": ct, "currency": "USD",
        "underlying_symbol": symbol, "duration": duration, "duration_unit": "t",
    })
    if "error" in res:
        return None, res["error"].get("message", "erro")
    p = res.get("proposal", {})
    payout, ask = p.get("payout"), p.get("ask_price")
    if not payout or not ask:
        return None, "sem payout"
    return payout / ask, None


def emp_prob(prices, d, up=True):
    """P(preco sobe/desce apos d ticks) em janelas deslizantes. Retorna (wins, n)."""
    wins = n = 0
    for i in range(len(prices) - d):
        a, b = prices[i], prices[i + d]
        if b == a:
            continue  # empate (raro) nao conta
        n += 1
        if (b > a) == up:
            wins += 1
    return wins, n


async def scan_symbol(symbol, chunks, durations):
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    rows = []
    try:
        print(f"\n>>> {symbol}: baixando ~{chunks} blocos...")
        prices = await fetch_prices(client, symbol, chunks)
        if len(prices) < 3000:
            print(f"  ! ticks insuficientes ({len(prices)}). Pulando.")
            return rows
        rets = [math.log(prices[i + 1] / prices[i]) for i in range(len(prices) - 1)
                if prices[i] > 0 and prices[i + 1] > 0]
        mu, sd = mean(rets), pstdev(rets)
        print(f"  {len(prices):,} ticks | log-ret mu={mu:.2e} sd={sd:.2e} "
              f"(drift/ruido = {abs(mu)/sd*100:.2f}% do desvio por tick)")

        for d in durations:
            for ct, up in (("CALL", True), ("PUT", False)):
                gr, err = await get_gross_return(client, symbol, ct, d)
                await asyncio.sleep(0.25)
                if gr is None:
                    print(f"  {ct} d={d}: sem cotacao ({err})")
                    continue
                w, n = emp_prob(prices, d, up=up)
                p_emp = w / n if n else 0.0
                p_lo, _ = wilson(w, n)
                # teorico: soma de d log-rets > 0 (CALL) ; sinal do drift muda p/ PUT
                z_teo = (mu * d) / (sd * math.sqrt(d)) if sd > 0 else 0.0
                p_teo = norm_cdf(z_teo) if up else norm_cdf(-z_teo)
                ev = p_emp * gr - 1.0
                ev_lo = p_lo * gr - 1.0
                rows.append((symbol, ct, d, p_emp, p_teo, gr, ev, ev_lo, n))
    finally:
        await client.disconnect()
    return rows


def print_table(rows):
    rows.sort(key=lambda r: r[6], reverse=True)
    print("\n" + "=" * 96)
    print(f"  {'SIMBOLO':9} {'CT':4} {'DUR':>3} {'P_emp':>7} {'P_teo':>7} "
          f"{'IMPLIC':>7} {'PAYOUT':>7} {'EV/$1':>8} {'EV_lo':>8}")
    print("=" * 96)
    for sym, ct, d, pe, pt, gr, ev, evlo, n in rows:
        implied = 1.0 / gr
        flag = "  <== EDGE+" if evlo > 0 else (" <- EV+ (s/ margem seg)" if ev > 0 else "")
        print(f"  {sym:9} {ct:4} {d:3d} {pe*100:6.2f}% {pt*100:6.2f}% "
              f"{implied*100:6.2f}% {(gr-1)*100:6.2f}% {ev:+8.4f} {evlo:+8.4f}{flag}")
    print("=" * 96)
    best = max(rows, key=lambda r: r[7])  # melhor EV pessimista
    if best[7] > 0:
        print(f"\n>>> EDGE PESSIMISTA: {best[0]} {best[1]} d={best[2]} -> EV_lo {best[7]:+.4f}/$1. "
              f"CONFIRMAR ao vivo (payout muda) e checar P_emp~P_teo.")
    else:
        bev = max(rows, key=lambda r: r[6])
        print(f"\n>>> SEM EDGE. Melhor EV (ponto) = {bev[1]} d={bev[2]} ({bev[0]}) {bev[6]:+.4f}/$1; "
              f"melhor EV_lo {best[7]:+.4f}. Margem da casa presente em todas as duracoes.")
    # diagnostico de modelo
    div = max(abs(r[3] - r[4]) for r in rows)
    print(f"    cross-check DGP: max|P_emp - P_teo| = {div*100:.2f}pp "
          + ("(modelo bate)" if div < 0.03 else "(DIVERGE -> path-dependence/drift?)"))


async def main():
    ap = argparse.ArgumentParser(description="Scanner de valor-relativo (duracao) Deriv")
    ap.add_argument("--symbols", default="R_100,1HZ100V")
    ap.add_argument("--chunks", type=int, default=30)
    ap.add_argument("--durations", default="1,2,3,5,7,10")
    args = ap.parse_args()
    durations = [int(x) for x in args.durations.split(",") if x.strip()]
    all_rows = []
    for sym in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        all_rows += await scan_symbol(sym, args.chunks, durations)
    if all_rows:
        print_table(all_rows)
    else:
        print("Nenhum dado coletado.")


if __name__ == "__main__":
    asyncio.run(main())
