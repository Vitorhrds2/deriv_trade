"""H3 passo 3 - Teste DECISIVO de fill: ordem demo cronometrada a um movimento Binance.

Pergunta: ao detectar um movimento na Binance e abrir IMEDIATAMENTE um multiplicador
cryBTCUSD na direcao do movimento, a entrada pega um preco DEFASADO (que depois
'alcanca' o movimento que ja vi na Binance) -> lucro consistente = arbitragem real?

Salvaguardas (ordens reais, ainda que em DEMO):
  - use_demo=True FIXO + trava: ABORTA se a conta nao for demo/virtual.
  - --live obrigatorio para enviar ordens; sem ele = dry-run (so valida conta + fluxo).
  - stake pequeno, --max-trades e --max-seconds com teto, cooldown entre trades.
  - sempre tenta FECHAR a posicao (sell com retry); nunca deixa contrato aberto.

Mede: P&L liquido por trade (aligned com o movimento) + win rate (Wilson), com
controle de direcao ALEATORIA. Tabela por trade com entry_spot vs Binance.

Uso:
  python arb_order_test.py                 # dry-run (sem ordens) - valida conta/fluxo
  python arb_order_test.py --live --max-trades 12
"""
import argparse
import asyncio
import bisect
import math
import os
import random
import sys
import time

from dotenv import load_dotenv

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    r"C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env",
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

import websockets  # noqa: E402
import json  # noqa: E402
from deriv_client import DerivClient  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
DERIV_SYMBOL = "cryBTCUSD"

b_ts, b_px = [], []   # binance timeline (sorted by ts)


async def capture_binance(stop):
    try:
        async with websockets.connect(BINANCE_WS, ping_interval=20) as ws:
            while not stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(msg)
                if "p" in d:
                    b_ts.append(time.time()); b_px.append(float(d["p"]))
    except Exception as e:
        print(f"  ! binance ws: {e}")


def binance_at(ts):
    if not b_ts:
        return None
    i = bisect.bisect_right(b_ts, ts) - 1
    return b_px[max(0, i)]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


async def validate_demo(client):
    # Autoritativo: confirma pela API que a conta conectada e account_type=demo (e NAO real).
    import urllib.request as _u

    def _fetch():
        req = _u.Request("https://api.derivws.com/trading/v1/options/accounts")
        req.add_header("Authorization", f"Bearer {API_TOKEN}")
        req.add_header("Deriv-App-ID", str(APP_ID))
        with _u.urlopen(req) as r:
            return json.loads(r.read().decode())

    accs = (await asyncio.get_running_loop().run_in_executor(None, _fetch)).get("data", [])
    demo_ids = [a["account_id"] for a in accs if a.get("account_type") == "demo"]
    real_ids = [a["account_id"] for a in accs if a.get("account_type") != "demo"]
    connected = client.account_id
    bres = await client.send_request({"balance": 1})
    bb = bres.get("balance", {})
    print(f"  Conta conectada: {connected} | saldo={bb.get('balance')} {bb.get('currency')} | use_demo={client.use_demo}")
    print(f"  Classificacao API -> demo={demo_ids} | real={real_ids}")
    ok = bool(client.use_demo and connected in demo_ids and connected not in real_ids)
    if ok:
        print(f"  OK: {connected} CONFIRMADA como DEMO.")
    else:
        print(f"  !! {connected} NAO confirmada como demo (ou e real).")
    return ok


async def close_contract(client, cid):
    for _ in range(5):
        try:
            res = await client.sell_contract(cid, price=0)
            if "sell" in res:
                return res["sell"].get("sold_for")
            if "error" in res and "already" in res["error"].get("message", "").lower():
                return None
        except Exception:
            pass
        await asyncio.sleep(0.8)
    print(f"  !! ATENCAO: nao consegui fechar o contrato {cid} - verifique manualmente.")
    return None


async def do_trade(client, direction, stake, mult, hold_s, tag, live):
    ct = "MULTUP" if direction > 0 else "MULTDOWN"
    prop = await client.send_request({
        "proposal": 1, "amount": stake, "basis": "stake", "contract_type": ct,
        "currency": "USD", "underlying_symbol": DERIV_SYMBOL, "multiplier": mult,
    })
    if "error" in prop:
        print(f"  [{tag}] proposal erro: {prop['error'].get('message')}")
        return None
    p = prop["proposal"]
    pspot = float(p.get("spot", 0) or 0)
    b_buy = binance_at(time.time())
    rec = {"tag": tag, "dir": direction, "ct": ct, "pspot": pspot, "b_buy": b_buy}

    if not live:
        rec["dry"] = True
        print(f"  [{tag}] DRY {ct} | proposal spot={pspot:.2f} | binance={b_buy:.2f}")
        return rec

    buy = await client.buy_contract(p["id"], price=stake)
    if "error" in buy:
        print(f"  [{tag}] buy erro: {buy['error'].get('message')}")
        return None
    cid = buy["buy"]["contract_id"]
    buy_price = float(buy["buy"]["buy_price"])
    poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
    poc_c = poc.get("proposal_open_contract", {})
    entry_spot = float(poc_c.get("entry_spot") or poc_c.get("entry_tick") or pspot or 0)

    await asyncio.sleep(hold_s)

    b_sell = binance_at(time.time())
    sold_for = await close_contract(client, cid)
    if sold_for is None:
        return None
    profit = float(sold_for) - buy_price
    rec.update({"entry_spot": entry_spot, "b_sell": b_sell, "buy_price": buy_price,
                "sold_for": float(sold_for), "profit": profit})
    arrow = "UP" if direction > 0 else "DN"
    print(f"  [{tag}] {arrow} entry={entry_spot:.2f} binance_buy={b_buy:.2f} -> "
          f"binance_sell={b_sell:.2f} | P&L=${profit:+.4f}")
    return rec


async def main():
    ap = argparse.ArgumentParser(description="Teste de ordem demo (arb latencia) Deriv x Binance")
    ap.add_argument("--live", action="store_true", help="enviar ordens reais (demo). Sem isso = dry-run")
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--mult", type=int, default=100)
    ap.add_argument("--hold-s", type=float, default=2.0)
    ap.add_argument("--threshold", type=float, default=30.0, help="$ do movimento Binance gatilho")
    ap.add_argument("--lookback-ms", type=int, default=600)
    ap.add_argument("--cooldown-s", type=float, default=3.0)
    ap.add_argument("--max-trades", type=int, default=12)
    ap.add_argument("--max-seconds", type=int, default=360)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados (.env).")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    print("=" * 84)
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao confirmada como DEMO/virtual. ABORTANDO (nenhuma ordem enviada).")
        await client.disconnect()
        return
    mode = "LIVE (ordens demo)" if args.live else "DRY-RUN (sem ordens)"
    print(f">>> Modo: {mode} | stake ${args.stake} x{args.mult} | hold {args.hold_s}s | "
          f"max {args.max_trades} trades / {args.max_seconds}s")
    print("=" * 84)

    stop = asyncio.Event()
    btask = asyncio.create_task(capture_binance(stop))
    await asyncio.sleep(3)  # warm up binance feed

    trades = []
    t_start = time.time()
    last_trade = 0.0
    try:
        while len(trades) < args.max_trades and (time.time() - t_start) < args.max_seconds:
            now = time.time()
            if now - last_trade < args.cooldown_s or len(b_ts) < 5:
                await asyncio.sleep(0.05)
                continue
            p_now = binance_at(now)
            p_past = binance_at(now - args.lookback_ms / 1000.0)
            if p_now is None or p_past is None:
                await asyncio.sleep(0.03)
                continue
            diff = p_now - p_past
            if abs(diff) < args.threshold:
                await asyncio.sleep(0.03)
                continue
            # disparou um movimento real -> coin-flip A/B na MESMA condicao
            move_dir = 1 if diff > 0 else -1
            if random.random() < 0.5:
                direction, tag = move_dir, "aligned"
            else:
                direction, tag = -move_dir, "anti"
            rec = await do_trade(client, direction, args.stake, args.mult, args.hold_s, tag, args.live)
            if rec:
                rec["move"] = diff
                trades.append(rec)
                last_trade = time.time()
                print(f"    -> {len(trades)} trades (movimento Binance ${diff:+.1f})")
    finally:
        stop.set()
        await asyncio.gather(btask, return_exceptions=True)
        try:
            await client.disconnect()
        except Exception:
            pass

    live_trades = [t for t in trades if "profit" in t]
    print("\n" + "=" * 84)
    print(f"Trades: {len(trades)} (com fill: {len(live_trades)})")
    if not live_trades:
        print("(dry-run ou sem fills) - rode com --live para medir P&L.")
        print("=" * 84)
        return
    for grp in ("aligned", "anti"):
        g = [t for t in live_trades if t["tag"] == grp]
        if not g:
            continue
        pnl = [t["profit"] for t in g]
        wins = sum(1 for x in pnl if x > 0)
        wr = wins / len(g)
        wlo, whi = wilson(wins, len(g))
        mean = sum(pnl) / len(g)
        print(f"  {grp:8}: n={len(g):3d} | WR={wr*100:5.1f}% [{wlo*100:.1f},{whi*100:.1f}] | "
              f"P&L medio=${mean:+.4f} | total=${sum(pnl):+.4f}")
    print("=" * 84)
    al = [t["profit"] for t in live_trades if t["tag"] == "aligned"]
    an = [t["profit"] for t in live_trades if t["tag"] == "anti"]
    if al and an:
        ma, mn = sum(al) / len(al), sum(an) / len(an)
        edge = ma - mn
        print(f">>> aligned - anti = ${edge:+.4f}/trade (edge direcional do lag, ja liquido de custo).")
        if ma > 0 and edge > 0:
            print("    SINAL DE ARB: aligned lucra E supera anti. Aumentar amostra p/ significancia "
                  "antes de qualquer capital real.")
        else:
            print("    SEM ARB no fill: aligned nao supera anti -> o lag do feed nao e explor\u00e1vel na execucao.")
    elif al:
        print(f">>> so aligned (n={len(al)}): P&L medio ${sum(al)/len(al):+.4f}. Faltam trades 'anti' p/ comparar.")
    print("=" * 84)


if __name__ == "__main__":
    asyncio.run(main())
