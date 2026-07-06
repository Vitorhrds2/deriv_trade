"""
Static Replication Arbitrage Probe
=====================================
Hipotese: contratos complementares (exatamente um dos dois sempre vence) podem ter
soma de ask_price < payout garantido, o que seria uma arbitragem estatica pura
(compra os dois lados, recebe o payout fixo de qualquer forma, sem exposicao a
direcao do mercado).

Pares testados, ambos com basis="payout" (fixa o payout, pergunta o custo):
  A) CALL + PUT no mesmo underlying/duration (sem barrier -- relativo ao entry spot).
     Exatamente um vence (ignorando probabilidade ~0 de empate exato em spot continuo).
  B) HIGHER(barrier) + LOWER(barrier) no mesmo barrier explicito/duration.
     Idem, complementares em torno do barrier.

Para cada rodada, pede as duas propostas em paralelo (mesmo instante/tick) e calcula:
  arb_$ = payout_alvo - (ask_leg1 + ask_leg2)
  arb_$ > 0  => arbitragem real (lucro garantido comprando os dois lados)
  arb_$ < 0  => margem da casa (esperado)

100% anonimo (proposal nao exige autenticacao) -- nao toca a conta demo/real.

Uso: python3 static_replication_probe.py
"""
import asyncio
import json
import statistics
import time
import websockets

APP_ID = "33iJWIKcLfzGYo9IE1Y6f"
WS_URL = f"wss://api.derivws.com/trading/v1/options/ws/public?app_id={APP_ID}"

SYMBOL = "1HZ10V"
DURATION = 5
DURATION_UNIT = "t"
PAYOUT_TARGET = 100.0
N_ROUNDS = 40
SLEEP_BETWEEN_S = 1.2

# Distancias de barrier (em '+X'/'-X') testadas para o par HIGHER/LOWER.
BARRIER_OFFSETS = ["+0.5", "+1.0", "+2.0"]

RESULTS_FILE = "static_replication_results.jsonl"


class Quoter:
    """Uma conexao WS dedicada -- recv() nao e concorrente entre chamadas."""
    def __init__(self):
        self.ws = None
        self.req_id = 1

    async def connect(self):
        self.ws = await websockets.connect(WS_URL, ping_interval=15, ping_timeout=45)

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def proposal(self, contract_type, barrier=None):
        payload = {
            "proposal": 1,
            "amount": PAYOUT_TARGET,
            "basis": "payout",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
            "req_id": self.req_id,
        }
        if barrier is not None:
            payload["barrier"] = str(barrier)
        rid = self.req_id
        self.req_id += 1
        t0 = time.time()
        await self.ws.send(json.dumps(payload))
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=8)
            data = json.loads(raw)
            if data.get("req_id") == rid:
                lat = time.time() - t0
                if data.get("error"):
                    return {"error": data["error"].get("message"), "latency_s": lat}
                p = data.get("proposal", {})
                return {
                    "ask_price": p.get("ask_price"),
                    "payout": p.get("payout"),
                    "spot": p.get("spot"),
                    "barrier": barrier,
                    "latency_s": lat,
                }


async def run_pair(quoter_a, quoter_b, name, leg_a_type, leg_b_type, barrier=None):
    a, b = await asyncio.gather(
        quoter_a.proposal(leg_a_type, barrier),
        quoter_b.proposal(leg_b_type, barrier),
    )
    return {"pair": name, "barrier": barrier, "leg_a": {leg_a_type: a}, "leg_b": {leg_b_type: b}}


async def main():
    print("=" * 90)
    print(f"Static Replication Arbitrage -- {SYMBOL} dur={DURATION}{DURATION_UNIT} "
          f"payout_target=${PAYOUT_TARGET} N={N_ROUNDS}")
    print("=" * 90, flush=True)

    q_a, q_b = Quoter(), Quoter()
    await asyncio.gather(q_a.connect(), q_b.connect())

    all_recs = []
    with open(RESULTS_FILE, "w") as f:
        for i in range(N_ROUNDS):
            # Par A: CALL + PUT (sem barrier, relativo ao entry spot)
            cp = await run_pair(q_a, q_b, "CALL+PUT", "CALL", "PUT")
            # Par B: HIGHER + LOWER num barrier explicito (rotaciona pelos offsets)
            offset = BARRIER_OFFSETS[i % len(BARRIER_OFFSETS)]
            hl = await run_pair(q_a, q_b, "HIGHER+LOWER", "HIGHER", "LOWER", barrier=offset)

            rec = {"round": i, "ts": time.time(), "call_put": cp, "higher_lower": hl}
            all_recs.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()

            def fmt(pairrec, leg_a_type, leg_b_type):
                a = pairrec["leg_a"][leg_a_type]
                b = pairrec["leg_b"][leg_b_type]
                if a.get("error") or b.get("error"):
                    return f"{pairrec['pair']}: ERR a={a.get('error')} b={b.get('error')}"
                arb = PAYOUT_TARGET - (a["ask_price"] + b["ask_price"])
                same_spot = "OK" if a["spot"] == b["spot"] else "SPOT-MISMATCH"
                return (f"{pairrec['pair']}(bar={pairrec['barrier']}): "
                        f"ask_{leg_a_type}={a['ask_price']:.2f} ask_{leg_b_type}={b['ask_price']:.2f} "
                        f"sum={a['ask_price']+b['ask_price']:.2f} arb=${arb:+.2f} [{same_spot}]")

            print(f"  [{i}] {fmt(cp, 'CALL', 'PUT')} | {fmt(hl, 'HIGHER', 'LOWER')}", flush=True)
            await asyncio.sleep(SLEEP_BETWEEN_S)

    await asyncio.gather(q_a.close(), q_b.close())

    # ---- Summary ----
    print("\n" + "=" * 90)
    print("RESUMO")
    print("=" * 90)

    def summarize(key, leg_a_type, leg_b_type, group_by_barrier=False):
        groups = {}
        for rec in all_recs:
            pairrec = rec[key]
            a = pairrec["leg_a"][leg_a_type]
            b = pairrec["leg_b"][leg_b_type]
            if a.get("error") or b.get("error"):
                continue
            if a["spot"] != b["spot"]:
                continue
            arb = PAYOUT_TARGET - (a["ask_price"] + b["ask_price"])
            gkey = pairrec["barrier"] if group_by_barrier else "ALL"
            groups.setdefault(gkey, []).append(arb)

        for gkey, vals in groups.items():
            if not vals:
                continue
            n_arb_positive = sum(1 for v in vals if v > 0)
            label = f"{key} barrier={gkey}" if group_by_barrier else key
            print(f"  {label}: n={len(vals)} (spot-matched) | arb_$ mean={statistics.mean(vals):+.3f} "
                  f"min={min(vals):+.3f} max={max(vals):+.3f} | rounds com arb>0: {n_arb_positive}/{len(vals)}")

    summarize("call_put", "CALL", "PUT")
    summarize("higher_lower", "HIGHER", "LOWER", group_by_barrier=True)
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
