"""
Deal Cancellation -- Validacao AO VIVO (trades reais, demo)
===============================================================
D52 (deal_cancellation_edge_scan.py) estimou via Monte Carlo que o fee cobrado pela
Deriv pela feature "Deal Cancellation" dos Multipliers fica ~8-12% ABAIXO do valor
justo simulado. Isso e so um MODELO teorico. Este probe testa com CONTRATOS REAIS,
igual metodologia do early_sell_test.py (hold vs sell empirico, nao simulado).

Mecanismo confirmado ao vivo (checado manualmente antes deste script):
  - Enquanto a cancellation esta ativa E o profit fica negativo, `is_valid_to_sell=0`
    e um `sell` normal e REJEITADO com validation_error_code="CancelIsBetter" --
    a propria Deriv avisa explicitamente para usar `{"cancel": contract_id}`.
  - `{"cancel": contract_id}` devolve `sold_for` = stake exato (P&L=0), confirmado.

Estrategia non-hindsight (nao usa informacao futura):
  - Compra MULTUP/MULTDOWN alternando, com `cancellation=5m`.
  - Faz poll de `proposal_open_contract` a cada ~0.5s.
  - No PRIMEIRO poll em que profit<0 (E is_valid_to_cancel=1): cancela IMEDIATAMENTE.
    valor_realizado_da_cancellation = stake - bid_price NESSE poll (o que um sell
    normal teria dado, se fosse permitido, vs o stake integral que a cancellation
    de fato devolve).
  - Se o profit nunca fica negativo ate a janela expirar: vende normalmente ao fim
    da janela (a cancellation "nao foi usada" -- valor_realizado=0 para o fee pago).

EV_cancellation = media(valor_realizado) - fee_pago. Comparar com fair_value_MC do
scan teorico (D52) e com o proprio fee.

100% DEMO. Uso: python3 deal_cancellation_live_probe.py
"""
import asyncio
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import bootstrap_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = os.getenv("D95_SYMBOL", "1HZ100V")
MULTIPLIER = int(os.getenv("D95_MULTIPLIER", "400"))
STAKE = float(os.getenv("D95_STAKE", "1.0"))
CANCELLATION = os.getenv("D95_CANCELLATION", "5m")


def _cancellation_to_seconds(c):
    m = re.match(r"^(\d+)([smhd])$", c)
    if not m:
        raise ValueError(f"Invalid cancellation duration: {c!r}")
    n, unit = m.groups()
    return int(n) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


CANCELLATION_SECONDS = _cancellation_to_seconds(CANCELLATION)
SLOW_POLL_INTERVAL_S = 1.0   # durante a maior parte da janela, so p/ log
FAST_POLL_INTERVAL_S = 0.3   # nos ultimos segundos antes do date_expiry
FAST_POLL_WINDOW_S = 8.0     # entra em modo "decisao" quando faltar <= isso p/ expirar
MAX_POLLS = 700          # ~350s de folga sobre os 300s da janela de 5m
N_TRIALS = int(os.getenv("D95_N_TRIALS", "20"))
CONTRACT_TYPES = ["MULTUP", "MULTDOWN"]  # alterna para nao ter vies direcional

RESULTS_FILE = os.getenv("D95_RESULTS_FILE", "d95_deal_cancellation_live_results.jsonl")


async def buy_with_cancellation(client, contract_type):
    res = await client.send_request({
        "proposal": 1, "amount": STAKE, "basis": "stake",
        "contract_type": contract_type, "currency": "USD",
        "underlying_symbol": SYMBOL, "multiplier": MULTIPLIER,
        "cancellation": CANCELLATION,
    })
    if "error" in res:
        return None, res["error"].get("message")
    p = res["proposal"]
    fee = float(p.get("cancellation", {}).get("ask_price", 0))
    date_start = p.get("date_start")
    raw_expiry = p.get("cancellation", {}).get("date_expiry")
    # Fallback: API sometimes returns cancellation.date_expiry == date_start (bug);
    # expected expiry is exactly date_start + cancellation duration.
    expected_expiry = (date_start + CANCELLATION_SECONDS) if date_start else None
    if expected_expiry and (raw_expiry is None or abs(raw_expiry - expected_expiry) > 10):
        expiry = expected_expiry
    else:
        expiry = raw_expiry
    buy = await client.buy_contract(p["id"], p["ask_price"])
    if "error" in buy:
        return None, buy["error"].get("message")
    b = buy["buy"]
    return {
        "contract_id": b["contract_id"], "buy_price": float(b["buy_price"]),
        "date_start": date_start, "fee": fee, "contract_type": contract_type,
        "raw_cancellation_expiry": raw_expiry, "cancellation_expiry": expiry,
    }, None


async def poll_contract(client, contract_id):
    res = await client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
    return res.get("proposal_open_contract", {})


async def run_trial(client, i, contract_type):
    """Estrategia EUROPEIA (decide so perto do fim da janela, nao no primeiro sinal
    negativo): logo apos a compra, `profit` fica levemente negativo so pela comissao
    de entrada (~$0.15), ANTES de qualquer movimento real de mercado -- cancelar nesse
    instante so "recupera" a comissao, nao testa a hipotese (protecao contra risco real
    de mercado ao longo da janela). Alem disso, como o cancel SEMPRE devolve o stake
    integral independente de quao negativo o profit esta, nao ha nenhum ganho em
    exercer cedo -- esperar ate o ultimo instante preserva a chance de recuperacao sem
    custo adicional. Por isso: so poll (logging) devagar durante a maior parte da
    janela, e so decide (cancela ou vende) nos ultimos segundos antes do date_expiry."""
    info, err = await buy_with_cancellation(client, contract_type)
    if info is None:
        return {"trial": i, "error": err}

    cid = info["contract_id"]
    expiry = info["cancellation_expiry"]
    rec = {
        "trial": i, "contract_id": cid, "contract_type": contract_type,
        "buy_price": info["buy_price"], "fee": info["fee"],
        "date_start": info.get("date_start"),
        "raw_cancellation_expiry": info.get("raw_cancellation_expiry"),
        "cancellation_expiry": expiry,
    }

    last = {}
    last_profit = None
    last_bid_price = None
    for poll_i in range(MAX_POLLS):
        c = await poll_contract(client, cid)
        last = c
        profit = float(c.get("profit", 0) or 0)
        bid_price = float(c.get("bid_price", 0) or 0)
        is_valid_to_cancel = bool(c.get("is_valid_to_cancel"))
        is_sold = bool(c.get("is_sold"))
        secs_to_expiry = (expiry - time.time()) if expiry else 999

        near_expiry = secs_to_expiry <= FAST_POLL_WINDOW_S

        if near_expiry and not is_sold and is_valid_to_cancel and profit < 0:
            cancel_res = await client.send_request({"cancel": cid})
            if "error" in cancel_res:
                rec["cancel_error"] = cancel_res["error"].get("message")
                sell_res = await client.sell_contract(cid, 0)
                rec["fallback_sell"] = sell_res.get("sell") or sell_res.get("error")
                rec["action"] = "cancel_failed_sold_instead"
                rec["realized_value"] = max(0.0, -profit)
                rec["poll_at_action"] = poll_i
                rec["profit_at_action"] = profit
                rec["bid_price_at_action"] = bid_price
            else:
                sold_for = float(cancel_res["cancel"]["sold_for"])
                realized_value = sold_for - bid_price  # quanto a cancellation "salvou" vs um sell normal
                rec.update({
                    "action": "cancelled", "poll_at_action": poll_i,
                    "bid_price_at_action": bid_price, "profit_at_action": profit,
                    "sold_for": sold_for, "realized_value": realized_value,
                })
            break

        if c.get("status") == "cancelled" and not is_sold:
            # stop-out triggered a cancellation; is_sold may not be updated yet in this poll.
            # Use the pre-cancellation profit from the previous poll.
            realized_value = max(0.0, -last_profit) if last_profit is not None else 0.0
            rec.update({
                "action": "cancelled_auto_stopout", "poll_at_action": poll_i,
                "profit_at_action": profit, "bid_price_at_action": bid_price,
                "last_profit": last_profit, "last_bid_price": last_bid_price,
                "realized_value": realized_value,
            })
            break

        if is_sold or not is_valid_to_cancel:
            # terminal: cancel window closed or contract already closed
            if c.get("status") == "cancelled":
                # cancellation triggered (stop-out or already closed). Use last pre-cancellation profit.
                realized_value = max(0.0, -last_profit) if last_profit is not None else 0.0
                rec.update({
                    "action": "cancelled_auto_stopout", "poll_at_action": poll_i,
                    "profit_at_action": profit, "bid_price_at_action": bid_price,
                    "last_profit": last_profit, "last_bid_price": last_bid_price,
                    "realized_value": realized_value,
                })
            elif profit > 0:
                if bool(c.get("is_valid_to_sell")):
                    sell_res = await client.sell_contract(cid, 0)
                    s = sell_res.get("sell", {})
                    rec.update({
                        "action": "expired_held_to_profit", "poll_at_action": poll_i,
                        "sold_for": float(s.get("sold_for", bid_price)),
                        "profit_at_action": profit, "bid_price_at_action": bid_price,
                        "realized_value": 0.0,
                    })
                else:
                    rec.update({"action": "expired_unsellable", "poll_at_action": poll_i,
                                "profit_at_action": profit, "bid_price_at_action": bid_price,
                                "realized_value": 0.0})
            else:
                # loss or breakeven: cancellation value = max(0, -profit)
                realized_value = max(0.0, -profit)
                if bool(c.get("is_valid_to_sell")):
                    sell_res = await client.sell_contract(cid, 0)
                    s = sell_res.get("sell", {})
                    rec.update({
                        "action": "expired_sold_at_loss", "poll_at_action": poll_i,
                        "sold_for": float(s.get("sold_for", bid_price)),
                        "profit_at_action": profit, "bid_price_at_action": bid_price,
                        "realized_value": realized_value,
                    })
                else:
                    rec.update({
                        "action": "expired_unsellable_at_loss", "poll_at_action": poll_i,
                        "profit_at_action": profit, "bid_price_at_action": bid_price,
                        "realized_value": realized_value,
                    })
            break

        # update for the next poll (so we have the pre-cancellation state if stop-out triggers)
        last_profit = profit
        last_bid_price = bid_price
        await asyncio.sleep(FAST_POLL_INTERVAL_S if near_expiry else SLOW_POLL_INTERVAL_S)

    if "action" not in rec:
        rec["action"] = "timeout_incomplete"
        rec["realized_value"] = 0.0
        rec["last_poll"] = {k: last.get(k) for k in ("profit", "bid_price", "is_valid_to_cancel", "is_valid_to_sell", "is_sold")}

    return rec


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print("=" * 100)
    print(f"Deal Cancellation LIVE -- {SYMBOL} multiplier={MULTIPLIER}x stake=${STAKE} "
          f"cancellation={CANCELLATION} N={N_TRIALS} (trades reais, demo)")
    print("=" * 100, flush=True)

    results = []
    with open(RESULTS_FILE, "a") as f:
        for i in range(N_TRIALS):
            contract_type = CONTRACT_TYPES[i % len(CONTRACT_TYPES)]
            rec = await run_trial(client, i, contract_type)
            results.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()

            if "error" in rec:
                print(f"  [{i}] {contract_type} ERRO: {rec['error']}", flush=True)
            else:
                print(f"  [{i}] {contract_type} cid={rec['contract_id']} fee=${rec['fee']:.2f} "
                      f"action={rec['action']} realized_value=${rec.get('realized_value')} "
                      f"(poll={rec.get('poll_at_action')})", flush=True)
            await asyncio.sleep(1.5)

    await client.disconnect()

    # ---- Summary ----
    valid = [r for r in results if "error" not in r and r.get("realized_value") is not None]
    print("\n" + "=" * 100)
    print("RESUMO")
    print("=" * 100)
    print(f"Trials validos: {len(valid)}/{N_TRIALS}")
    n_cancelled = sum(1 for r in valid if r["action"] in ("cancelled", "cancelled_auto_stopout"))
    n_held = sum(1 for r in valid if r["action"] in ("expired_held_to_profit", "expired_unsellable", "expired_sold_at_loss", "expired_unsellable_at_loss"))
    print(f"Cancelados (profit ficou negativo): {n_cancelled} | "
          f"Nunca ficou negativo (fee 'desperdicado'): {n_held}")

    if valid:
        fees = [r["fee"] for r in valid]
        values = [r["realized_value"] for r in valid]
        net = [v - fe for v, fe in zip(values, fees)]
        lo, mean, hi = bootstrap_ci(net, n_boot=2000)
        print(f"\nFee medio pago: ${sum(fees)/len(fees):.4f} | "
              f"Valor realizado medio da cancellation: ${sum(values)/len(values):.4f}")
        print(f"EV liquido por trade (valor_realizado - fee): ${mean:+.4f} "
              f"IC95%[${lo:+.4f}, ${hi:+.4f}]")
        flag = " <<< EDGE CONFIRMADO AO VIVO" if lo > 0 else (
            " <<< SEM EDGE (fee >= valor realizado)" if hi < 0 else " <<< INCONCLUSIVO (IC cruza zero)")
        print(flag)
        print(f"\nTotal: {len(valid)} trials | soma_fees=${sum(fees):.2f} | "
              f"soma_valor_realizado=${sum(values):.2f} | liquido=${sum(values)-sum(fees):+.2f}")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
