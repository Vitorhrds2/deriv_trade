"""
App ID / Channel Pricing Arbitrage Probe
==========================================
Hipotese: a Deriv pode entregar cotacoes (ask_price/payout) diferentes para o
MESMO contrato (mesmo symbol/contract_type/duration/stake, mesmo spot/tick)
dependendo do app_id e/ou do endpoint (canal) usado para pedir a `proposal`.

Testa 3 bracos em paralelo, no MESMO instante (mesmo tick, quando possivel):
  A) new_custom    : wss://api.derivws.com/trading/v1/options/ws/public + app_id do projeto (OAuth, registrado em app.deriv.com)
  B) new_generic   : wss://api.derivws.com/trading/v1/options/ws/public + app_id=1089 (publico/legado, generico)
  C) legacy_generic: wss://ws.derivws.com/websockets/v3                 + app_id=1089 (gateway legado, usado por SmartTrader/apps antigos)

`proposal` NAO exige autenticacao -- roda 100% anonimo, sem tocar a conta demo/real.

Uso: python3 app_id_pricing_probe.py
"""
import asyncio
import json
import time
import statistics
import websockets

SYMBOL = "R_10"  # 1HZ10V nao e oferecido no gateway legado (app_id=1089) -- usar simbolo classico presente em ambos
CONTRACT_TYPE = "CALL"
DURATION = 5
DURATION_UNIT = "t"
STAKE = 10.0
N_ROUNDS = 40
SLEEP_BETWEEN_S = 1.5

PROJECT_APP_ID = "33iJWIKcLfzGYo9IE1Y6f"
PUBLIC_APP_ID = "1089"

# new_generic (app_id=1089 no MESMO endpoint novo) ja foi confirmado 100% identico a
# new_custom em 40/40 rounds (ask/payout/spot bit-a-bit iguais) -- app_id nao importa
# dentro do mesmo gateway. Removido do rerun; mantido so o contraste de CANAL/gateway:
# endpoint novo ("options", usado por este projeto) vs endpoint legado (websockets/v3,
# usado por SmartTrader/apps publicos antigos). Schemas divergem: o legado usa "symbol",
# o novo usa "underlying_symbol" (por isso o primeiro run falhou com validation error).
ARMS = {
    "new":     ("wss://api.derivws.com/trading/v1/options/ws/public", PROJECT_APP_ID, "underlying_symbol"),
    "legacy":  ("wss://ws.derivws.com/websockets/v3", PUBLIC_APP_ID, "symbol"),
}

RESULTS_FILE = "app_id_pricing_results.jsonl"


class RawArm:
    def __init__(self, name, base_url, app_id, symbol_field):
        self.name = name
        self.url = f"{base_url}?app_id={app_id}"
        self.symbol_field = symbol_field
        self.ws = None
        self.req_id = 1
        self.alive = False

    async def connect(self):
        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(self.url, ping_interval=15, ping_timeout=45), timeout=10)
            self.alive = True
            print(f"  [{self.name}] conectado OK -> {self.url}", flush=True)
        except Exception as e:
            self.alive = False
            print(f"  [{self.name}] FALHA ao conectar: {e}", flush=True)

    async def proposal(self):
        if not self.alive:
            return None
        payload = {
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": CONTRACT_TYPE,
            "currency": "USD",
            self.symbol_field: SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
            "req_id": self.req_id,
        }
        rid = self.req_id
        self.req_id += 1
        t0 = time.time()
        try:
            await self.ws.send(json.dumps(payload))
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=8)
                data = json.loads(raw)
                if data.get("req_id") == rid:
                    lat = time.time() - t0
                    if data.get("error"):
                        return {"arm": self.name, "error": data["error"].get("message"), "latency_s": lat}
                    p = data.get("proposal", {})
                    return {
                        "arm": self.name,
                        "ask_price": p.get("ask_price"),
                        "payout": p.get("payout"),
                        "spot": p.get("spot"),
                        "spot_time": p.get("spot_time"),
                        "display_value": p.get("display_value"),
                        "latency_s": lat,
                    }
        except Exception as e:
            return {"arm": self.name, "error": str(e), "latency_s": time.time() - t0}

    async def close(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass


async def main():
    print("=" * 90)
    print(f"App ID / Channel Pricing Arbitrage -- {SYMBOL} {CONTRACT_TYPE} dur={DURATION}{DURATION_UNIT} "
          f"stake=${STAKE} N={N_ROUNDS}")
    print("=" * 90, flush=True)

    arms = {name: RawArm(name, url, app_id, sym_field) for name, (url, app_id, sym_field) in ARMS.items()}
    await asyncio.gather(*[a.connect() for a in arms.values()])

    live_arms = {n: a for n, a in arms.items() if a.alive}
    if len(live_arms) < 2:
        print(">>> Menos de 2 bracos conectados -- impossivel comparar. Abortando.")
        return

    print(f"\n  Bracos ativos: {list(live_arms.keys())}\n", flush=True)

    all_rounds = []
    with open(RESULTS_FILE, "w") as f:
        for i in range(N_ROUNDS):
            t_round = time.time()
            outs = await asyncio.gather(*[a.proposal() for a in live_arms.values()])
            rec = {"round": i, "ts": t_round, "quotes": outs}
            all_rounds.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()

            parts = []
            for o in outs:
                if o is None:
                    continue
                if "error" in o:
                    parts.append(f"{o.get('arm')}=ERR({o.get('error')})")
                else:
                    parts.append(f"{o.get('arm')}: ask={o.get('ask_price')} payout={o.get('payout')} "
                                 f"spot={o.get('spot')} lat={o.get('latency_s', 0)*1000:.0f}ms")
            print(f"  [{i}] " + " | ".join(parts), flush=True)

            await asyncio.sleep(SLEEP_BETWEEN_S)

    await asyncio.gather(*[a.close() for a in arms.values()])

    # ---- Summary ----
    print("\n" + "=" * 90)
    print("RESUMO")
    print("=" * 90)

    arm_names = list(live_arms.keys())
    same_spot_rounds = 0
    pairs = [(a, b) for i, a in enumerate(arm_names) for b in arm_names[i + 1:]]
    diffs = {pair: [] for pair in pairs}
    payout_diffs = {pair: [] for pair in pairs}

    for rec in all_rounds:
        by_arm = {o["arm"]: o for o in rec["quotes"] if o and "error" not in o}
        spots = {by_arm[a]["spot"] for a in by_arm if by_arm[a].get("spot") is not None}
        if len(spots) == 1 and len(by_arm) == len(arm_names):
            same_spot_rounds += 1
            for (a, b) in pairs:
                if a in by_arm and b in by_arm:
                    pa, pb = by_arm[a].get("ask_price"), by_arm[b].get("ask_price")
                    poa, pob = by_arm[a].get("payout"), by_arm[b].get("payout")
                    if pa is not None and pb is not None:
                        diffs[(a, b)].append(pa - pb)
                    if poa is not None and pob is not None:
                        payout_diffs[(a, b)].append(poa - pob)

    print(f"Rounds com spot identico entre todos os bracos: {same_spot_rounds}/{len(all_rounds)}")
    for pair in pairs:
        vals = diffs[pair]
        pd = payout_diffs[pair]
        if vals:
            print(f"  {pair[0]} vs {pair[1]}: n={len(vals)} "
                  f"ask_price_diff mean={statistics.mean(vals):+.4f} max_abs={max(abs(x) for x in vals):.4f} | "
                  f"payout_diff mean={statistics.mean(pd):+.4f} max_abs={max(abs(x) for x in pd):.4f}")
        else:
            print(f"  {pair[0]} vs {pair[1]}: sem rounds com spot identico para comparar")

    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
