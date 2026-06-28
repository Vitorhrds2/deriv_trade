"""Sonda de CUSTO REAL do multiplicador Deriv (cryBTCUSD).

Teto de viabilidade do H1: o sinal direcional bruto medido no sweep e
~0.013%-0.022% de movimento favoravel por trade (independente do multiplicador,
pois gross_$ = move% x mult x stake). A comissao do multiplicador tambem e ~%
do nocional (mult x stake), entao o nocional se cancela: basta comparar
  comissao_% (round-trip)  vs  edge_%  (~0.013%-0.022%).
Se comissao_% round-trip >> edge_%, H1 morre por custo.

So consulta proposals (cotacao) em DEMO - nenhuma ordem e enviada.
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

# .env mora no repo principal (gitignored, nao copiado pro worktree)
for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    r"C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env",
]:
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
SYMBOL = "cryBTCUSD"
STAKE = 10.0

# edge bruto medido no sweep (move favoravel medio por trade, em %):
EDGE_BEST = 1.78 / (STAKE * 800) * 100      # melhor config (lat=50)  ~0.0223%
EDGE_REAL = 1.02 / (STAKE * 800) * 100      # amostra grande/realista ~0.0128%


async def main():
    if not API_TOKEN or not APP_ID:
        print("ERRO: DERIV_API_TOKEN/DERIV_APP_ID nao encontrados (.env).")
        return
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    try:
        print("=" * 88)
        print(f"CUSTO REAL multiplicador {SYMBOL} | stake ${STAKE:.0f}")
        print(f"Sinal bruto medido: edge realista ~{EDGE_REAL:.4f}% | edge melhor caso ~{EDGE_BEST:.4f}% por trade")
        print("=" * 88)

        # 1) multiplicadores validos
        cf = await client.send_request({"contracts_for": SYMBOL, "currency": "USD", "product_type": "basic"})
        mults = []
        for a in cf.get("contracts_for", {}).get("available", []):
            ct = a.get("contract_type", "")
            if "MULT" in ct or a.get("contract_category") == "multiplier":
                rng = a.get("multiplier_range") or a.get("multiplier") or []
                if isinstance(rng, list):
                    mults += rng
        mults = sorted({int(m) for m in mults}) if mults else [100, 200, 300, 400]
        print(f"Multiplicadores disponiveis: {mults}\n")

        test = mults
        if len(test) > 5:
            test = [mults[0], mults[len(mults) // 2], mults[-1]]

        print(f"  {'MULT':>6} {'NOCIONAL':>9} {'COMISSAO$':>10} {'COMISS%':>9} "
              f"{'ROUND-TRIP%':>11}  VEREDITO(vs edge realista)")
        print("  " + "-" * 74)
        for mult in test:
            res = await client.send_request({
                "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": "MULTUP",
                "currency": "USD", "underlying_symbol": SYMBOL, "multiplier": mult,
            })
            if "error" in res:
                print(f"  {mult:>6}  erro: {res['error'].get('message')}")
                continue
            p = res["proposal"]
            comm = float(p.get("commission", 0) or 0)
            notional = STAKE * mult
            comm_pct = comm / notional * 100 if notional else 0.0
            rt_pct = comm_pct * 2  # abrir + fechar
            verdict = "VIAVEL?" if rt_pct < EDGE_REAL else ("marginal" if rt_pct < EDGE_BEST else "MORRE")
            print(f"  {mult:>6} {notional:>9.0f} {comm:>10.4f} {comm_pct:>8.4f}% "
                  f"{rt_pct:>10.4f}%  {verdict}")
            await asyncio.sleep(0.3)

        # 2) proposal completo (todos os campos de custo)
        res = await client.send_request({
            "proposal": 1, "amount": STAKE, "basis": "stake", "contract_type": "MULTUP",
            "currency": "USD", "underlying_symbol": SYMBOL, "multiplier": test[-1],
        })
        print(f"\n=== proposal completo (mult={test[-1]}) ===")
        print(json.dumps(res.get("proposal", res), indent=2, ensure_ascii=False)[:2200])
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
