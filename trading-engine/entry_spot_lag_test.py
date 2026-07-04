"""Verificacao DIRETA (nao por inferencia estatistica de WR agregado) da regra
documentada "Entry Spot Lag" (docs/antigravity-brain/hypothesis/implementation_plan.md):
para contratos de tick, o entry_spot deveria ser SEMPRE o tick T+1 (o PROXIMO apos o
sinal), nunca o tick T0 ja visto via subscribe_ticks. Essa regra foi inferida ate agora
so por win rate agregado (36-38%, rng_smoothing_exploit.py) batendo com a teoria --
nunca comparada tick-a-tick contra o dado bruto da API.

Pergunta: existe uma janela de race onde o tick JA CONHECIDO (T0, visto pela subscricao
ANTES do buy ser enviado) escapa como entry_spot oficial do contrato? Se sim, seria uma
falha real (o "futuro" da aposta deixaria de ser desconhecido no momento da decisao,
ja que T0 ja foi visto). Se o entry for SEMPRE T+1 (ou mais tarde), a regra documentada
se confirma robustamente por medicao direta, fechando esta hipotese.

Metodo:
  1. Subscreve ticks do simbolo, guardando o ultimo tick visto (valor + epoch + tempo local).
  2. Para cada trial: registra T0_seen, dispara IMEDIATAMENTE buy_direct (CALL, 1 tick),
     espera o contrato assentar entry_tick/entry_spot (via proposal_open_contract), compara.
  3. Agrega: fracao de trials onde entry_spot == T0_seen (exploit real) vs sempre novo
     (regra confirmada), e o gap real (segundos) entre T0_seen e o entry oficial.

Usa conta DEMO (trava explicita, mesmo padrao de arb_order_test.py) e stake minimo --
contratos reais de 1 tick sao comprados de verdade (nao ha como ler entry_spot sem
comprar; a API nao expoe isso via 'proposal' sozinho).

Uso:
  python entry_spot_lag_test.py --symbol 1HZ10V --trials 20 --stake 1
"""
import argparse
import asyncio
import json
import os
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

from deriv_client import DerivClient
from stats_utils import summarize

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

state = {"last_tick": None}  # {"value": float, "epoch": int, "local_t": float}


def on_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        state["last_tick"] = {
            "value": float(t["quote"]),
            "epoch": int(t.get("epoch", 0)),
            "local_t": time.time(),
        }


async def validate_demo(client):
    # Autoritativo: confirma pela API que a conta conectada e account_type=demo (mesmo
    # padrao de arb_order_test.py). Nunca envia ordem sem essa confirmacao.
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
    print(f"  Conta conectada: {connected} | demo={demo_ids} | real={real_ids} -> "
          f"{'OK DEMO' if ok else 'NAO CONFIRMADA COMO DEMO!'}")
    return ok


async def run_trial(client, symbol, stake, idx):
    t0 = state["last_tick"]
    if t0 is None:
        print(f"  [{idx}] sem tick ainda, pulando.")
        return None

    buy = await client.buy_direct(contract_type="CALL", stake=stake, symbol=symbol,
                                   duration=1, duration_unit="t")
    if "error" in buy:
        print(f"  [{idx}] buy erro: {buy['error'].get('message')}")
        return None
    cid = buy["buy"]["contract_id"]

    entry = None
    final = None
    for _ in range(100):  # ate ~20s de poll (1 tick ~1-2s p/ entry + ~1-2s p/ exit)
        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        c = poc.get("proposal_open_contract", {})
        if entry is None and (c.get("entry_tick") is not None or c.get("entry_spot") is not None):
            entry = dict(c)
            if idx == 0:
                print(f"  [debug trial 0] campos disponiveis: {sorted(c.keys())}")
        if c.get("is_sold"):
            final = c
            break
        await asyncio.sleep(0.2)

    if entry is None:
        print(f"  [{idx}] timeout esperando entry_spot (contrato {cid}) -- descartando trial.")
        return None
    if final is None:
        print(f"  [{idx}] entry OK mas timeout esperando settlement (contrato {cid}) -- profit N/A.")

    entry_spot = float(entry.get("entry_tick") if entry.get("entry_tick") is not None
                        else entry.get("entry_spot"))
    entry_epoch = int(entry.get("entry_tick_time") or entry.get("entry_spot_time") or 0)
    profit = float(final.get("profit", 0)) if final is not None else None

    # Identidade real de "mesmo tick reaproveitado" e o EPOCH (quando o tick aconteceu),
    # nao o VALOR do preco -- 1HZ10V tem incrementos pequenos/discretos, entao dois ticks
    # DIFERENTES no tempo podem coincidir no preco por puro acaso (falso positivo). So um
    # epoch igual ao do tick ja visto seria uma race de verdade (reaproveitar o MESMO evento).
    same_epoch = bool(entry_epoch and t0["epoch"] and entry_epoch == t0["epoch"])
    same_value = abs(entry_spot - t0["value"]) < 1e-9
    gap_s = (entry_epoch - t0["epoch"]) if entry_epoch and t0["epoch"] else None

    if same_epoch:
        flag = "*** MESMO EPOCH DO TICK JA VISTO (race real!) ***"
    elif same_value:
        flag = "valor coincide por acaso, epoch novo (OK, T+1 confirmado)"
    else:
        flag = "novo (OK, T+1 confirmado)"
    print(f"  [{idx}] T0_visto={t0['value']:.5f}(ep{t0['epoch']}) -> entry={entry_spot:.5f}"
          f"(ep{entry_epoch}) | gap={gap_s}s | {flag} | "
          f"profit={f'${profit:+.4f}' if profit is not None else 'N/A'}")

    return {
        "t0_value": t0["value"], "t0_epoch": t0["epoch"],
        "entry_spot": entry_spot, "entry_epoch": entry_epoch,
        "same_as_seen": same_epoch, "same_value_only": same_value and not same_epoch,
        "gap_s": gap_s, "profit": profit,
    }


async def main():
    ap = argparse.ArgumentParser(description="Teste direto do Entry Spot Lag (race T0-ja-visto vs T+1)")
    ap.add_argument("--symbol", default="1HZ10V")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--cooldown-s", type=float, default=1.0)
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
    print(f">>> Symbol={args.symbol} | trials={args.trials} | stake=${args.stake} | duration=1 tick (CALL)")
    print("=" * 84)

    await client.subscribe_ticks(args.symbol, on_tick)
    await asyncio.sleep(2)  # espera o primeiro tick chegar

    results = []
    try:
        for i in range(args.trials):
            rec = await run_trial(client, args.symbol, args.stake, i)
            if rec:
                results.append(rec)
            await asyncio.sleep(args.cooldown_s)
    finally:
        await client.disconnect()

    print("\n" + "=" * 84)
    n = len(results)
    same_epoch = sum(1 for r in results if r["same_as_seen"])
    same_value = sum(1 for r in results if r.get("same_value_only"))
    print(f"RESULTADO: {n} trials validos | mesmo EPOCH do tick ja visto: {same_epoch}/{n} "
          f"| valor coincidiu por acaso (epoch diferente): {same_value}/{n}")
    if n == 0:
        print(">>> Nenhum trial valido -- verifique conexao/simbolo e rode novamente.")
    elif same_epoch == 0:
        print(">>> Regra 'Entry Spot Lag' CONFIRMADA por medicao direta (identidade por EPOCH,")
        print("    nao por valor): entry_spot NUNCA reaproveitou o MESMO evento de tick ja")
        print("    conhecido no momento do buy -- sempre um epoch nao visto (T+1 ou mais tarde).")
        if same_value:
            print(f"    ({same_value} caso(s) tiveram valor de preco IGUAL por coincidencia, mas em")
            print("     epoch diferente -- esperado num simbolo de incrementos pequenos/discretos,")
            print("     nao e evidencia de race. Sem exploit encontrado.")
    else:
        print(f">>> !!! RACE REAL DETECTADA em {same_epoch} trial(s): entry_spot reutilizou o")
        print("    MESMO epoch de um tick ja conhecido no momento da decisao. Achado potencialmente")
        print("    exploravel -- investigar se e reproduzivel e se da pra converter em EV positivo.")
    gaps = [r["gap_s"] for r in results if r["gap_s"] is not None]
    if gaps:
        print(f"    Gap medio T0_visto -> entry oficial: {sum(gaps)/len(gaps):.2f}s "
              f"(min={min(gaps)}s, max={max(gaps)}s)")
    profits = [r["profit"] for r in results if r["profit"] is not None]
    if profits:
        summarize(f"Sanity check WR/EV ({args.symbol}, 1 tick, CALL)", profits)
    print("=" * 84)


if __name__ == "__main__":
    asyncio.run(main())
