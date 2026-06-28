"""Scanner de EDGE por tipo de contrato Deriv.

Pergunta central: a Deriv precifica ALGUM contrato com payout que implique uma
probabilidade MENOR que a probabilidade VERDADEIRA? Se sim -> edge (mispricing).
Senao -> a taxa da casa esta embutida em todos (EV < 0).

Para cada contrato:
  - busca o PAYOUT real ao vivo via API `proposal` (gross_return = payout/stake)
  - mede a PROBABILIDADE verdadeira nos ticks historicos (digito extraido pelo
    pip_size CORRETO do simbolo, nao o *100 do bot)
  - EV/$1 = p_win * gross_return - 1   |  edge = p_win - prob_implicita(=1/gross_return)

Contratos: DIGITDIFF, DIGITMATCH, DIGITEVEN, DIGITODD, DIGITOVER 0..8,
DIGITUNDER 1..9, CALL, PUT (duracao 1 tick).

Uso:
  python contract_edge_scan.py --symbols 1HZ10V,R_10 --chunks 40
"""
import argparse
import asyncio
import math
import os
import sys
from collections import Counter
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
DURATION = 1  # ticks


def last_digit(price, pip):
    return int(round(float(price) / pip)) % 10


def infer_pip(prices):
    """Deduz o pip pelo menor incremento real entre ticks (granularidade = pip)."""
    min_diff = None
    for i in range(1, len(prices)):
        d = abs(round(float(prices[i]) - float(prices[i - 1]), 10))
        if d > 0 and (min_diff is None or d < min_diff):
            min_diff = d
    if not min_diff:
        return 0.01
    decimals = max(0, min(round(-math.log10(min_diff)), 8))
    return 10 ** (-decimals)


async def get_pip(client, symbol):
    res = await client.send_request({"active_symbols": "full"})
    for s in res.get("active_symbols", []):
        if s.get("symbol") == symbol and s.get("pip"):
            return float(s["pip"])
    return None


async def get_gross_return(client, symbol, ct, barrier=None):
    payload = {
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": ct, "currency": "USD",
        "underlying_symbol": symbol, "duration": DURATION, "duration_unit": "t",
    }
    if barrier is not None:
        payload["barrier"] = str(barrier)
    res = await client.send_request(payload)
    if "error" in res:
        return None
    p = res.get("proposal", {})
    payout, ask = p.get("payout"), p.get("ask_price")
    if not payout or not ask:
        return None
    return payout / ask


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
        if (i + 1) % 10 == 0 or i == chunks - 1:
            print(f"  {symbol}: {i+1}/{chunks} -> {len(prices):,} ticks")
        await asyncio.sleep(delay)
    return prices


def p_win_digit(freq, ct, barrier):
    if ct == "DIGITDIFF":
        return 1 - freq[int(barrier)]
    if ct == "DIGITMATCH":
        return freq[int(barrier)]
    if ct == "DIGITEVEN":
        return sum(freq[d] for d in (0, 2, 4, 6, 8))
    if ct == "DIGITODD":
        return sum(freq[d] for d in (1, 3, 5, 7, 9))
    if ct == "DIGITOVER":
        return sum(freq[d] for d in range(int(barrier) + 1, 10))
    if ct == "DIGITUNDER":
        return sum(freq[d] for d in range(0, int(barrier)))
    return None


async def scan_symbol(symbol, chunks):
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    rows = []
    try:
        print(f"\n>>> {symbol}  baixando {chunks} blocos...")
        prices = await fetch_prices(client, symbol, chunks)
        if len(prices) < 2000:
            print(f"  ! {symbol}: ticks insuficientes ({len(prices)}). Pulando.")
            return None
        pip_api = await get_pip(client, symbol)
        pip_inf = infer_pip(prices)
        pip = pip_api or pip_inf
        print(f"  pip_size: API={pip_api} inferido(granularidade)={pip_inf} -> usando {pip}")
        if pip_api and abs(pip_api - pip_inf) > 1e-12:
            print(f"  AVISO: pip da API difere do inferido; usando o da API ({pip_api}).")

        digits = [last_digit(p, pip) for p in prices]
        n = len(digits)
        cnt = Counter(digits)
        freq = [cnt.get(d, 0) / n for d in range(10)]
        exp = n / 10.0
        chi = sum((cnt.get(d, 0) - exp) ** 2 / exp for d in range(10))

        ups = sum(1 for i in range(len(prices) - 1) if float(prices[i + 1]) > float(prices[i]))
        downs = sum(1 for i in range(len(prices) - 1) if float(prices[i + 1]) < float(prices[i]))
        m = len(prices) - 1
        p_call, p_put = ups / m, downs / m

        print(f"  dist digitos: {[round(f*100,1) for f in freq]}")
        print(f"  chi2 vs uniforme (df=9): {chi:.2f}  (critico 16.92)  -> "
              + ("UNIFORME" if chi < 16.92 else "NAO uniforme <<< possivel mispricing"))
        print(f"  P[subida 1 tick]={p_call*100:.2f}%  P[queda]={p_put*100:.2f}%")

        specs = [("DIGITDIFF", "5"), ("DIGITMATCH", "5"), ("DIGITEVEN", None), ("DIGITODD", None)]
        specs += [("DIGITOVER", str(b)) for b in range(0, 9)]
        specs += [("DIGITUNDER", str(b)) for b in range(1, 10)]
        for ct, b in specs:
            gr = await get_gross_return(client, symbol, ct, b)
            await asyncio.sleep(0.25)
            if gr is None:
                continue
            pw = p_win_digit(freq, ct, b)
            rows.append((symbol, ct, b or "-", pw, gr, pw * gr - 1))
        for ct in ("CALL", "PUT"):
            gr = await get_gross_return(client, symbol, ct, None)
            await asyncio.sleep(0.25)
            if gr is None:
                continue
            pw = p_call if ct == "CALL" else p_put
            rows.append((symbol, ct, "-", pw, gr, pw * gr - 1))
    finally:
        await client.disconnect()
    return rows


def print_table(rows):
    rows = sorted(rows, key=lambda r: r[5], reverse=True)
    print("\n" + "=" * 86)
    print(f"  {'SIMBOLO':9} {'CONTRATO':11} {'BARR':5} {'P_WIN':>7} {'IMPLIC':>7} "
          f"{'EDGE':>7} {'PAYOUT':>7} {'EV/$1':>8}")
    print("=" * 86)
    for sym, ct, b, pw, gr, ev in rows:
        implied = 1.0 / gr
        edge = pw - implied
        flag = "  <== EDGE+" if ev > 0 else ""
        print(f"  {sym:9} {ct:11} {b:5} {pw*100:6.2f}% {implied*100:6.2f}% "
              f"{edge*100:+6.2f}% {(gr-1)*100:6.2f}% {ev:+8.4f}{flag}")
    print("=" * 86)
    best = max(rows, key=lambda r: r[5])
    if best[5] > 0:
        print(f"\n>>> POSSIVEL EDGE: {best[0]} {best[1]} {best[2]} -> EV {best[5]:+.4f}/$1. "
              f"VERIFICAR ao vivo (payout varia) antes de confiar.")
    else:
        print(f"\n>>> SEM EDGE EM NENHUM CONTRATO. Melhor EV = {best[1]} {best[2]} ({best[0]}) "
              f"= {best[5]:+.4f}/$1. Taxa da casa presente em todos.")


async def main():
    ap = argparse.ArgumentParser(description="Scanner de edge por tipo de contrato Deriv")
    ap.add_argument("--symbols", type=str, default="1HZ10V,R_10")
    ap.add_argument("--chunks", type=int, default=40)
    args = ap.parse_args()

    all_rows = []
    for sym in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        rows = await scan_symbol(sym, args.chunks)
        if rows:
            all_rows += rows
    if all_rows:
        print_table(all_rows)
    else:
        print("Nenhum dado coletado.")


if __name__ == "__main__":
    asyncio.run(main())
