"""Accumulator Tick-Barrier Race -- probe de exploracao (Item 2, candidato #1).

Mecanica do ACCU: a cada tick sobrevivido, o stake acumulado cresce (1+growth_rate)x. Se o
PROXIMO tick cair fora de [low_barrier, high_barrier] (calculados a partir do tick anterior),
o contrato e IMEDIATAMENTE zerado (perde 100% do valor acumulado) -- ao contrario de vender
manualmente ANTES do knockout, que preserva 100% do valor acumulado ate ali. Essa assimetria
binaria (tudo vs nada, decidida por um unico tick) e o que torna uma race de timing aqui
potencialmente muito mais valiosa que o Early Sell (que so troca "profit parcial" por "profit
total/perda total").

Hipotese: existe uma janela onde (a) o tick que rompe a barreira ja chegou via `ticks`
subscription (dado bruto, nosso proprio calculo local), mas (b) o `proposal_open_contract`
ainda nao processou o knockout oficialmente (ainda mostra is_sold=false / bid_price>0). Se
essa janela existir, um `sell` disparado no INSTANTE em que detectamos localmente a ruptura
deveria conseguir resgatar o valor acumulado ANTES do sistema zerar o contrato.

Metodo:
  1. Subscreve ticks brutos do symbol (fonte independente da verdade).
  2. Compra ACCU (growth_rate configuravel). Guarda high_barrier/low_barrier vigentes via
     poll rapido (a cada POLL_INTERVAL_S) de proposal_open_contract.
  3. Callback de tick (assincrono, mas NUNCA da await direto em send_request dentro do
     dispatch do _listen -- ver nota de deadlock abaixo) compara o tick recebido contra o
     ultimo [low_barrier, high_barrier] conhecido. Se romper, dispara `sell` em uma task
     separada (fire-and-forget) e marca o instante local da deteccao.
  4. Registra: se a venda foi aceita, a que preco, e o gap entre deteccao local e o proximo
     poll que confirma is_sold=true no lado do servidor.

Nota de deadlock (importante p/ quem for mexer aqui): `_listen()` faz `await cb(data)`
sincronamente dentro do proprio loop que le mensagens do WS. Se o callback de tick desse
`await client.send_request(...)` DIRETAMENTE, o Future dessa venda so seria resolvido quando
`_listen()` recebesse a resposta -- mas `_listen()` esta BLOQUEADO esperando o callback
terminar. Deadlock. Por isso o callback so AGENDA a venda via `asyncio.create_task(...)` e
retorna na hora, deixando `_listen()` livre pra continuar recebendo (inclusive a resposta da
propria venda).
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accu_tick_race_results.jsonl")

SYMBOL = "1HZ100V"
GROWTH_RATE = 0.05
STAKE = 1.0
POLL_INTERVAL_S = 0.3
MAX_TRIAL_SECONDS = 180

tick_state = {}
active_contract = {}


async def validate_demo(client):
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
    ok = bool(client.use_demo and connected in demo_ids and connected not in real_ids)
    print(f"Conta: {connected} | demo={demo_ids} | real={real_ids} -> {'OK DEMO' if ok else 'NAO DEMO!'}", flush=True)
    return ok


async def verify_and_sell(client, cid, ac):
    """So dispara o sell se uma leitura FRESCA (pos-suspeita) confirmar que o contrato
    ainda esta vivo com bid_price>0 -- evita falso positivo por barrier em cache
    desatualizado no lado do CLIENTE (polling tem lag proprio, independente do servidor)."""
    c = await poll_open_contract(client, cid)
    fresh_bid = float(c.get("bid_price", 0) or 0)
    fresh_is_sold = bool(c.get("is_sold"))
    ac["fresh_check_bid"] = fresh_bid
    ac["fresh_check_is_sold"] = fresh_is_sold
    ac["fresh_check_at"] = time.time()

    if fresh_is_sold or fresh_bid <= 0:
        ac["false_positive"] = True
        print(f"    [race] tick={ac['breach_candidate_tick']} pareceu romper "
              f"[{ac['breach_candidate_lb']},{ac['breach_candidate_hb']}], mas leitura fresca "
              f"ja mostra bid=${fresh_bid} is_sold={fresh_is_sold} -- FALSO POSITIVO (cache local desatualizado)",
              flush=True)
        ac["checking"] = False
        return

    ac["sell_attempted"] = True
    ac["breach_detected_at"] = time.time()
    ac["breach_tick"] = ac["breach_candidate_tick"]
    ac["bid_price_before_breach"] = fresh_bid
    print(f"    [race] tick={ac['breach_tick']} rompeu [{ac['breach_candidate_lb']},{ac['breach_candidate_hb']}] "
          f"E leitura fresca CONFIRMA vivo (bid=${fresh_bid}) -- disparando SELL imediato", flush=True)
    try:
        res = await client.sell_contract(cid, price=0)
        ac["sell_result"] = res
    except Exception as e:
        ac["sell_result"] = {"error": {"message": str(e)}}
    ac["sell_completed_at"] = time.time()
    if ac["sell_result"] and "error" not in ac["sell_result"]:
        sold = ac["sell_result"].get("sell", {})
        print(f"    >>> SELL aceito: preco=${float(sold.get('sold_for', 0)):.4f} "
              f"lag_deteccao->resposta={ac['sell_completed_at'] - ac['breach_detected_at']:.3f}s", flush=True)
    else:
        msg = ac["sell_result"]["error"].get("message", "") if ac["sell_result"] else "?"
        print(f"    >>> SELL REJEITADO: {msg}", flush=True)


def make_on_tick(client):
    async def on_tick(data):
        t = data.get("tick")
        if not (t and "quote" in t):
            return
        sym = t.get("symbol")
        q = float(t["quote"])
        if sym:
            tick_state[sym] = {"value": q, "epoch": int(t.get("epoch", 0)), "local_t": time.time()}

        ac = active_contract
        if not ac or ac.get("checking") or ac.get("sell_attempted") or sym != ac.get("symbol"):
            return
        hb, lb = ac.get("high_barrier"), ac.get("low_barrier")
        if hb is None or lb is None:
            return
        if q > hb or q < lb:
            ac["checking"] = True
            ac["breach_candidate_tick"] = q
            ac["breach_candidate_hb"] = hb
            ac["breach_candidate_lb"] = lb
            ac["breach_candidate_epoch"] = int(t.get("epoch", 0))
            ac["breach_candidate_detected_at"] = time.time()
            asyncio.create_task(verify_and_sell(client, ac["cid"], ac))
    return on_tick


async def poll_open_contract(client, cid, retries=6):
    for attempt in range(retries):
        try:
            poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
            if isinstance(poc, dict) and "error" in poc:
                await asyncio.sleep(1)
                continue
            return poc.get("proposal_open_contract", {})
        except Exception:
            await asyncio.sleep(min(2 * (attempt + 1), 8))
    return {}


async def run_trial(client, idx):
    global active_contract
    proposal = await client.get_proposal("ACCU", STAKE, symbol=SYMBOL, growth_rate=GROWTH_RATE)
    if "error" in proposal:
        print(f"  [{idx}] proposal erro: {proposal['error'].get('message')}", flush=True)
        return None
    p = proposal["proposal"]
    buy_res = await client.buy_contract(p["id"], float(p["ask_price"]))
    if "error" in buy_res:
        print(f"  [{idx}] buy erro: {buy_res['error'].get('message')}", flush=True)
        return None

    b = buy_res["buy"]
    cid = b["contract_id"]
    buy_price = float(b.get("buy_price", STAKE))

    active_contract = {
        "cid": cid, "symbol": SYMBOL, "checking": False,
        "high_barrier": None, "low_barrier": None, "bid_price": None,
        "sell_attempted": False, "sell_result": None, "false_positive": False,
        "breach_detected_at": None, "breach_tick": None, "breach_epoch": None,
        "bid_price_before_breach": None, "sell_completed_at": None,
    }

    start = time.time()
    final = None
    n_polls = 0
    while time.time() - start < MAX_TRIAL_SECONDS:
        c = await poll_open_contract(client, cid)
        n_polls += 1
        if c.get("high_barrier") is not None:
            active_contract["high_barrier"] = float(c["high_barrier"])
        if c.get("low_barrier") is not None:
            active_contract["low_barrier"] = float(c["low_barrier"])
        if c.get("bid_price") is not None:
            active_contract["bid_price"] = float(c["bid_price"])
        if c.get("is_sold"):
            final = c
            break
        if active_contract["sell_attempted"] and active_contract["sell_completed_at"]:
            await asyncio.sleep(0.5)
            c2 = await poll_open_contract(client, cid)
            final = c2 if c2.get("is_sold") else c
            break
        await asyncio.sleep(POLL_INTERVAL_S)

    if not final:
        # timeout sem breach -- fecha manualmente pra nao deixar posicao aberta
        try:
            await client.sell_contract(cid, price=0)
        except Exception:
            pass
        await asyncio.sleep(1)
        final = await poll_open_contract(client, cid)

    lag = None
    if active_contract["breach_detected_at"] and active_contract["sell_completed_at"]:
        lag = active_contract["sell_completed_at"] - active_contract["breach_detected_at"]

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "idx": idx, "contract_id": cid, "buy_price": buy_price,
        "growth_rate": GROWTH_RATE, "n_polls": n_polls,
        "breach_detected": active_contract["breach_detected_at"] is not None,
        "false_positive": active_contract["false_positive"],
        "bid_price_before_breach": active_contract["bid_price_before_breach"],
        "sell_attempted": active_contract["sell_attempted"],
        "sell_response_lag_s": lag,
        "sell_result": active_contract["sell_result"],
        "final_profit": float(final.get("profit", 0) or 0),
        "final_status": final.get("status"),
        "final_is_sold": final.get("is_sold"),
    }
    won_race = False
    if rec["sell_attempted"] and rec["sell_result"] and "error" not in rec["sell_result"]:
        sold_for = float(rec["sell_result"]["sell"].get("sold_for", 0))
        rec["sold_for"] = sold_for
        won_race = sold_for > 0.005  # recuperou valor > 0 na venda pos-deteccao de breach
    rec["won_race"] = won_race

    print(f"  [{idx}] breach={rec['breach_detected']} sell_attempt={rec['sell_attempted']} "
          f"lag={lag} sold_for={rec.get('sold_for')} profit=${rec['final_profit']:+.4f} "
          f"status={rec['final_status']}", flush=True)
    return rec


async def main():
    ap = argparse.ArgumentParser(description="Accumulator Tick-Barrier Race probe")
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--cooldown-s", type=float, default=2.0)
    args = ap.parse_args()

    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados.")
        return

    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    ok = await validate_demo(client)
    if not ok:
        print(">>> TRAVA: conta nao DEMO. ABORTANDO.", flush=True)
        await client.disconnect()
        return

    await client.subscribe_ticks(SYMBOL, make_on_tick(client))
    await asyncio.sleep(2)

    print("=" * 90, flush=True)
    print(f"Accumulator Tick-Barrier Race -- {SYMBOL} growth_rate={GROWTH_RATE} stake=${STAKE} "
          f"poll={POLL_INTERVAL_S}s N={args.trials}", flush=True)
    print("=" * 90, flush=True)

    results = []
    with open(RESULTS_FILE, "a") as fh:
        for i in range(args.trials):
            try:
                rec = await run_trial(client, i)
            except Exception as e:
                print(f"  [{i}] trial exception: {e}", flush=True)
                rec = None
            if rec:
                results.append(rec)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            await asyncio.sleep(args.cooldown_s)

    print("\n" + "=" * 90, flush=True)
    breaches = [r for r in results if r["breach_detected"]]
    races_won = [r for r in breaches if r["won_race"]]
    print(f"Total trials: {len(results)} | breaches detectados localmente: {len(breaches)} | "
          f"vendas com valor recuperado pos-breach: {len(races_won)}", flush=True)
    if breaches:
        lags = [r["sell_response_lag_s"] for r in breaches if r["sell_response_lag_s"] is not None]
        if lags:
            print(f"Lag deteccao->resposta do sell: media={statistics.mean(lags):.3f}s "
                  f"min={min(lags):.3f}s max={max(lags):.3f}s", flush=True)
        recovered = [r["sold_for"] for r in races_won]
        if recovered:
            print(f"Valor recuperado nas vendas pos-breach: total=${sum(recovered):.2f} "
                  f"media=${statistics.mean(recovered):.4f}", flush=True)
    print("=" * 90, flush=True)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
