"""
Streamed Proposal Staleness Probe
====================================
Hipotese: o preco de uma `proposal` ASSINADA (subscribe:1, feed continuo, o que a UI
tipicamente exibe) pode atualizar com lag em relacao a um request avulso (`proposal`
sem subscribe, pedido pontualmente) para o MESMO contrato/instante. Se o stream
atrasar, um cliente poderia comprar usando um `proposal_id` do stream que "parece"
atual na tela mas ja esta desatualizado frente ao mercado real.

Mecanismo != D47 (stale proposal buy race): D47 testava um DELAY ARTIFICIAL imposto
pelo cliente antes de comprar. Aqui o "atraso" (se existir) e NATURAL do proprio
sistema de streaming da Deriv, nao induzido -- e a compra e feita assim que uma
divergencia e detectada, nao apos esperar de proposito.

Metodo:
  1. Assina `proposal` (subscribe:1) para CALL 1HZ10V, mantem o ultimo quote recebido.
  2. A cada ~2s, pede uma `proposal` avulsa (fresh, sem subscribe) para o MESMO
     contrato, e compara spot/ask_price/tempo contra o ultimo push do stream.
  3. A cada poucas rodadas, tenta COMPRAR usando o proposal_id ATUAL do stream logo
     apos notar um novo tick (potencial janela de defasagem) -- registra se o barrier/
     entry_spot do contrato resultante bate com o que o stream mostrava ou e
     recalculado (RECALC), igual ao teste do D47.

100% DEMO (buys usam stake pequeno). Uso: python3 proposal_stream_staleness_probe.py
"""
import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request

import websockets
from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")
BASE_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

SYMBOL = "1HZ10V"
CONTRACT_TYPE = "CALL"
DURATION = 5
DURATION_UNIT = "t"
STAKE = 1.0
N_CHECKS = 24
CHECK_INTERVAL_S = 2.0
BUY_TEST_EVERY = 6  # tenta comprar do stream a cada N rodadas

RESULTS_FILE = "proposal_stream_staleness_results.jsonl"


async def get_auth_url(app_id, api_token, use_demo=True):
    loop = asyncio.get_running_loop()

    def fetch_accounts():
        req = urllib.request.Request("https://api.derivws.com/trading/v1/options/accounts")
        req.add_header("Authorization", f"Bearer {api_token}")
        req.add_header("Deriv-App-ID", str(app_id))
        req.add_header("User-Agent", "Codex-DerivDemo/1.0")
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())

    def fetch_otp(acc_id):
        req = urllib.request.Request(
            f"https://api.derivws.com/trading/v1/options/accounts/{acc_id}/otp", method="POST")
        req.add_header("Authorization", f"Bearer {api_token}")
        req.add_header("Deriv-App-ID", str(app_id))
        req.add_header("User-Agent", "Codex-DerivDemo/1.0")
        req.add_header("Content-Length", "0")
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())

    acc_data = await loop.run_in_executor(None, fetch_accounts)
    target = next((a for a in acc_data.get("data", [])
                   if a.get("account_type") == ("demo" if use_demo else "real")), None)
    otp_data = await loop.run_in_executor(None, fetch_otp, target["account_id"])
    return f"{otp_data['data']['url']}&app_id={app_id}"


class StreamClient:
    """Cliente WS minimo com suporte a subscriptions PERSISTENTES (nao consome o
    callback apos a 1a mensagem, diferente do DerivClient padrao deste repo)."""
    def __init__(self):
        self.ws = None
        self.req_id = 1
        self.futures = {}
        self.sub_callbacks = {}
        self._listen_task = None

    async def connect(self, url):
        self.ws = await websockets.connect(url, ping_interval=15, ping_timeout=45)
        self._listen_task = asyncio.create_task(self._listen())

    async def close(self):
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()

    async def _listen(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                rid = data.get("req_id")
                if rid in self.futures:
                    fut = self.futures.pop(rid)
                    if not fut.done():
                        fut.set_result(data)
                if rid in self.sub_callbacks:
                    cb = self.sub_callbacks[rid]
                    cb(data)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"  [listen error] {e}", flush=True)

    async def send(self, payload):
        rid = self.req_id
        self.req_id += 1
        payload = dict(payload, req_id=rid)
        fut = asyncio.get_running_loop().create_future()
        self.futures[rid] = fut
        await self.ws.send(json.dumps(payload))
        return await asyncio.wait_for(fut, timeout=10), rid

    async def subscribe(self, payload, callback):
        rid = self.req_id
        self.req_id += 1
        payload = dict(payload, subscribe=1, req_id=rid)
        self.sub_callbacks[rid] = callback
        fut = asyncio.get_running_loop().create_future()
        self.futures[rid] = fut
        await self.ws.send(json.dumps(payload))
        first = await asyncio.wait_for(fut, timeout=10)
        return first, rid

    async def forget(self, subscription_id):
        try:
            await self.send({"forget": subscription_id})
        except Exception:
            pass


def proposal_payload():
    return {
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": CONTRACT_TYPE, "currency": "USD",
        "underlying_symbol": SYMBOL, "duration": DURATION, "duration_unit": DURATION_UNIT,
    }


async def main():
    print("=" * 100)
    print(f"Streamed Proposal Staleness -- {SYMBOL} {CONTRACT_TYPE} dur={DURATION}{DURATION_UNIT} "
          f"stake=${STAKE} N={N_CHECKS}")
    print("=" * 100, flush=True)

    # OTP e single-use -- cada conexao precisa da sua propria URL de auth fresca.
    url_a, url_b = await asyncio.gather(
        get_auth_url(APP_ID, TOKEN, use_demo=True),
        get_auth_url(APP_ID, TOKEN, use_demo=True))
    stream_client = StreamClient()
    fresh_client = StreamClient()
    await asyncio.gather(stream_client.connect(url_a), fresh_client.connect(url_b))

    latest_stream = {}

    def on_push(data):
        if data.get("error"):
            latest_stream["error"] = data["error"].get("message")
            return
        p = data.get("proposal", {})
        latest_stream.update({
            "proposal_id": p.get("id"),
            "ask_price": p.get("ask_price"),
            "spot": p.get("spot"),
            "spot_time": p.get("spot_time"),
            "received_at": time.time(),
            "error": None,
        })

    first, sub_req_id = await stream_client.subscribe(proposal_payload(), on_push)
    on_push(first)
    print(f"  Stream assinado (req_id={sub_req_id}). Primeiro quote: spot={latest_stream.get('spot')} "
          f"ask={latest_stream.get('ask_price')}\n", flush=True)

    records = []
    with open(RESULTS_FILE, "w") as f:
        for i in range(N_CHECKS):
            t_check = time.time()
            fresh_res, _ = await fresh_client.send(proposal_payload())
            fp = fresh_res.get("proposal", {})
            fresh = {
                "proposal_id": fp.get("id"), "ask_price": fp.get("ask_price"),
                "spot": fp.get("spot"), "spot_time": fp.get("spot_time"),
                "received_at": t_check,
            }

            stream_snapshot = dict(latest_stream)
            stream_age_s = t_check - stream_snapshot.get("received_at", t_check)
            spot_match = stream_snapshot.get("spot") == fresh.get("spot")
            spot_time_lag = (fresh.get("spot_time") or 0) - (stream_snapshot.get("spot_time") or 0)

            rec = {
                "round": i, "ts": t_check, "stream": stream_snapshot, "fresh": fresh,
                "stream_age_s": stream_age_s, "spot_match": spot_match,
                "spot_time_lag_ticks": spot_time_lag,
            }

            # A cada BUY_TEST_EVERY rodadas: compra usando o proposal_id ATUAL do
            # STREAM (nao o fresh) bem no instante em que percebemos um novo tick,
            # e registra se o contrato bate com o que o stream mostrava.
            if i > 0 and i % BUY_TEST_EVERY == 0 and stream_snapshot.get("proposal_id"):
                buy_res, _ = await stream_client.send(
                    {"buy": stream_snapshot["proposal_id"], "price": stream_snapshot["ask_price"]})
                if "error" in buy_res:
                    rec["buy_attempt"] = {"ok": False, "error": buy_res["error"].get("message")}
                else:
                    b = buy_res.get("buy", {})
                    poc, _ = await stream_client.send({"proposal_open_contract": 1, "contract_id": b.get("contract_id")})
                    c = poc.get("proposal_open_contract", {})
                    rec["buy_attempt"] = {
                        "ok": True, "contract_id": b.get("contract_id"),
                        "buy_price": b.get("buy_price"),
                        "entry_spot": c.get("entry_spot"),
                        "stream_spot_at_buy": stream_snapshot.get("spot"),
                        "matches_stream_spot": c.get("entry_spot") == stream_snapshot.get("spot"),
                    }

            records.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()

            buy_info = ""
            if "buy_attempt" in rec:
                ba = rec["buy_attempt"]
                if ba["ok"]:
                    tag = "STREAM-SPOT-HONRADO" if ba["matches_stream_spot"] else "RECALC(fresh)"
                    buy_info = (f" | BUY cid={ba['contract_id']} entry_spot={ba['entry_spot']} "
                                f"stream_spot={ba['stream_spot_at_buy']} [{tag}]")
                else:
                    buy_info = f" | BUY ERRO: {ba['error']}"

            print(f"  [{i}] stream(spot={stream_snapshot.get('spot')}, idade={stream_age_s*1000:.0f}ms) "
                  f"vs fresh(spot={fresh.get('spot')}) | spot_match={spot_match} "
                  f"spot_time_lag={spot_time_lag:+.0f}ticks{buy_info}", flush=True)

            await asyncio.sleep(CHECK_INTERVAL_S)

    await asyncio.gather(stream_client.close(), fresh_client.close())

    # ---- Summary ----
    print("\n" + "=" * 100)
    print("RESUMO")
    print("=" * 100)
    ages = [r["stream_age_s"] for r in records]
    mismatches = [r for r in records if not r["spot_match"]]
    lags = [r["spot_time_lag_ticks"] for r in records]
    print(f"Idade do ultimo push do stream no momento do check fresco: "
          f"media={statistics.mean(ages)*1000:.0f}ms max={max(ages)*1000:.0f}ms")
    print(f"Rounds com spot(stream) != spot(fresh): {len(mismatches)}/{len(records)}")
    print(f"spot_time_lag (ticks, fresh - stream): media={statistics.mean(lags):+.2f} "
          f"min={min(lags):+.0f} max={max(lags):+.0f}")

    buy_attempts = [r["buy_attempt"] for r in records if "buy_attempt" in r]
    ok_buys = [b for b in buy_attempts if b.get("ok")]
    honored = [b for b in ok_buys if b.get("matches_stream_spot")]
    print(f"\nTentativas de compra via proposal_id do stream: {len(buy_attempts)} "
          f"(aceitas={len(ok_buys)})")
    print(f"Entry_spot bateu com o spot que o STREAM mostrava (nao recalculado): "
          f"{len(honored)}/{len(ok_buys)}")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
