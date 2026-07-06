"""
Concurrent Duplicate-Buy Race Probe
======================================
Hipotese: se o backend da Deriv tiver uma race condition de concorrencia na validacao
de `proposal_id`, disparar 2 requests "buy" SIMULTANEOS referenciando o MESMO
proposal_id (antes de qualquer resposta chegar) poderia fazer os DOIS serem aceitos
-- um contrato "de graca" (debito de apenas 1 stake mas 2 posicoes abertas), ou pelo
menos uma janela onde o proposal_id nao invalida atomically.

Mecanismo != D47 (stale proposal buy race): D47 testava um DELAY antes de comprar
(preco desatualizado). Aqui o delay e ZERO -- as duas requisicoes saem via 2 conexoes
WS AUTENTICADAS SEPARADAS (mesma conta demo) o mais simultaneamente possivel
(asyncio.gather, sem await entre elas), testando concorrencia no processamento do
backend, nao staleness de preco.

Para cada trial: pega 1 proposal, dispara 2 "buy" com o mesmo proposal_id em paralelo,
registra que legs foram aceitos/rejeitados, se geraram o MESMO contract_id (impossivel
mas checado por seguranca) ou dois contract_ids DIFERENTES (= dois contratos reais
comprados de 1 unica proposal), e o saldo debitado real da conta.

100% DEMO. Uso: python3 duplicate_buy_race_probe.py
"""
import asyncio
import json
import os
import sys
import time

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

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
CONTRACT_TYPE = "CALL"
DURATION = 5
DURATION_UNIT = "t"
STAKE = 1.0
N_TRIALS = 15
SLEEP_BETWEEN_S = 3.0

RESULTS_FILE = "duplicate_buy_race_results.jsonl"


async def get_balance(client):
    r = await client.get_balance()
    return float(r.get("balance", {}).get("balance", 0))


def parse_buy(res):
    if isinstance(res, Exception):
        return {"ok": False, "error": str(res)}
    if "error" in res:
        return {"ok": False, "error": res["error"].get("message")}
    b = res.get("buy", {})
    return {
        "ok": True,
        "contract_id": b.get("contract_id"),
        "buy_price": b.get("buy_price"),
        "transaction_id": b.get("transaction_id"),
    }


async def run_trial(client_a, client_b, i):
    prop = await client_a.get_proposal(
        CONTRACT_TYPE, STAKE, symbol=SYMBOL, duration=DURATION, duration_unit=DURATION_UNIT)
    if "error" in prop:
        return {"trial": i, "error": prop["error"].get("message")}
    p = prop.get("proposal", {})
    proposal_id = p.get("id")
    ask_price = float(p.get("ask_price", STAKE))

    bal_before = await get_balance(client_a)

    t0 = time.time()
    res_a, res_b = await asyncio.gather(
        client_a.buy_contract(proposal_id, ask_price),
        client_b.buy_contract(proposal_id, ask_price),
        return_exceptions=True,
    )
    lat = time.time() - t0

    ra, rb = parse_buy(res_a), parse_buy(res_b)
    both_ok = ra["ok"] and rb["ok"]
    same_contract = both_ok and ra.get("contract_id") == rb.get("contract_id")

    await asyncio.sleep(1.0)
    bal_after = await get_balance(client_a)
    debited = bal_before - bal_after

    return {
        "trial": i, "proposal_id": proposal_id, "ask_price": ask_price,
        "race_latency_s": lat, "leg_a": ra, "leg_b": rb,
        "both_accepted": both_ok, "same_contract_id": same_contract,
        "balance_before": bal_before, "balance_after": bal_after, "debited": debited,
    }


async def main():
    client_a = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    client_b = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await asyncio.gather(client_a.connect(), client_b.connect())
    print("=" * 90)
    print(f"Concurrent Duplicate-Buy Race -- {SYMBOL} {CONTRACT_TYPE} dur={DURATION}{DURATION_UNIT} "
          f"stake=${STAKE} N={N_TRIALS} (2 sessoes autenticadas, mesma conta demo)")
    print("=" * 90, flush=True)

    results = []
    with open(RESULTS_FILE, "w") as f:
        for i in range(N_TRIALS):
            rec = await run_trial(client_a, client_b, i)
            results.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()

            if "error" in rec:
                print(f"  [{i}] ERRO ao pedir proposal: {rec['error']}", flush=True)
                await asyncio.sleep(SLEEP_BETWEEN_S)
                continue

            la = "OK(cid=%s)" % rec["leg_a"]["contract_id"] if rec["leg_a"]["ok"] else f"REJ({rec['leg_a']['error']})"
            lb = "OK(cid=%s)" % rec["leg_b"]["contract_id"] if rec["leg_b"]["ok"] else f"REJ({rec['leg_b']['error']})"
            print(f"  [{i}] ask=${rec['ask_price']:.2f} race_lat={rec['race_latency_s']*1000:.0f}ms | "
                  f"A={la} | B={lb} | AMBOS_ACEITOS={rec['both_accepted']} | "
                  f"debitado=${rec['debited']:.2f}", flush=True)
            await asyncio.sleep(SLEEP_BETWEEN_S)

    await asyncio.gather(client_a.disconnect(), client_b.disconnect())

    valid = [r for r in results if "error" not in r]
    both_accepted = [r for r in valid if r["both_accepted"]]
    same_id = [r for r in valid if r["same_contract_id"]]

    print("\n" + "=" * 90)
    print("RESUMO")
    print("=" * 90)
    print(f"Trials validos: {len(valid)}/{N_TRIALS}")
    print(f"Ambos os legs aceitos (2 buys de 1 proposal_id): {len(both_accepted)}/{len(valid)}")
    print(f"Mesmo contract_id retornado nos 2 legs (bug de idempotencia): {len(same_id)}/{len(valid)}")
    if both_accepted:
        for r in both_accepted:
            expected = 2 * r["ask_price"]
            bug = " <<< POSSIVEL BUG: debito nao bate com 2x stake" if abs(r["debited"] - expected) > 0.05 else ""
            print(f"  trial={r['trial']} debitado=${r['debited']:.2f} (esperado 2x stake=${expected:.2f}){bug}")
    else:
        print(">>> Nenhum trial teve os 2 legs aceitos -- backend rejeita corretamente o "
              "segundo buy referenciando um proposal_id ja consumido.")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
