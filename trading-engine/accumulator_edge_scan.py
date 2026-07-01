"""
Scan de edge em Accumulators (ACCU) -- primeira hipotese GENUINAMENTE NOVA do Mega Brain 2.0
(produto nunca testado neste ecossistema).

Mecanica (confirmada via probe_accumulator.py, contract_details da API real):
- Cada tick, o range permitido e "tick_size_barrier" (%) em torno do ultimo spot.
- Se sobreviver, o stake cresce (1+growth_rate) por tick. Se sair do range, perde tudo (knockout).
- A propria API devolve "ticks_stayed_in": amostra historica real de quantos ticks contratos
  passados (mesmo symbol+growth_rate) sobreviveram antes do knockout -- e o P_emp pronto, sem
  precisarmos baixar/replaying tick history nos mesmos.

Teste (mesmo gate de credibilidade do T3): para cada (symbol, growth_rate, N alvo de ticks),
  P_emp(sobreviver >= N) = fracao empirica de ticks_stayed_in >= N
  payout bruto se vender exatamente ao atingir N ticks = (1+growth_rate)^N
  EV/$1 = P_emp * payout - 1   |   EV_lo usa o limite INFERIOR do Wilson CI (pessimista)
Edge so conta se EV_lo > 0 E N_amostra >= MIN_SAMPLES (evita blip de amostra pequena, o mesmo
erro que o scan ingenuo de T3 cometeu antes de corrigir).
"""
import asyncio
import os
from dotenv import load_dotenv
from deriv_client import DerivClient
from stats_utils import wilson_ci

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOLS = ["R_10", "R_25", "R_50", "R_75", "R_100", "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V"]
GROWTH_RATES = [0.01, 0.02, 0.03, 0.04, 0.05]
MIN_SAMPLES = 50
TARGET_N_TICKS = [1, 2, 3, 5, 8, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 250]


async def fetch_one(client, symbol, gr):
    res = await client.get_proposal("ACCU", stake=10.0, symbol=symbol, growth_rate=gr)
    if "error" in res:
        return None
    p = res.get("proposal", {})
    cd = p.get("contract_details", {})
    return {
        "symbol": symbol,
        "growth_rate": gr,
        "tick_size_barrier_pct": cd.get("tick_size_barrier_percentage"),
        "maximum_ticks": cd.get("maximum_ticks"),
        "ticks_stayed_in": cd.get("ticks_stayed_in", []),
    }


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    all_candidates = []
    all_cells = 0

    for symbol in SYMBOLS:
        for gr in GROWTH_RATES:
            data = await fetch_one(client, symbol, gr)
            if not data:
                print(f"{symbol} growth_rate={gr}: sem dados (contrato indisponivel)")
                continue
            survivals = data["ticks_stayed_in"]
            n = len(survivals)
            if n < MIN_SAMPLES:
                print(f"{symbol} growth_rate={gr}: N={n} < MIN_SAMPLES={MIN_SAMPLES}, pulando")
                continue

            print(f"\n{symbol} growth_rate={gr} (barreira={data['tick_size_barrier_pct']}, "
                  f"max_ticks={data['maximum_ticks']}, N_amostra={n})")

            for target_n in TARGET_N_TICKS:
                if data["maximum_ticks"] and target_n > data["maximum_ticks"]:
                    continue
                survived = sum(1 for s in survivals if s >= target_n)
                p_emp = survived / n
                wr_lo, wr_hi = wilson_ci(survived, n)
                payout_mult = (1 + gr) ** target_n
                ev = p_emp * payout_mult - 1
                ev_lo = wr_lo * payout_mult - 1
                all_cells += 1

                flag = ""
                if ev_lo > 0:
                    flag = " <<< CANDIDATO A EDGE (EV_lo > 0)"
                    all_candidates.append({
                        "symbol": symbol, "growth_rate": gr, "target_n": target_n,
                        "n_amostra": n, "p_emp": p_emp, "wr_ci": (wr_lo, wr_hi),
                        "payout_mult": payout_mult, "ev": ev, "ev_lo": ev_lo,
                    })
                print(f"  N={target_n:>3} ticks | sobreviveram {survived:>3}/{n} ({p_emp*100:5.1f}%, "
                      f"IC95%[{wr_lo*100:5.1f}%,{wr_hi*100:5.1f}%]) | payout={payout_mult:6.3f}x | "
                      f"EV=${ev:+.4f} | EV_lo=${ev_lo:+.4f}{flag}")

    await client.disconnect()

    print("\n" + "=" * 70)
    print(f"VEREDITO FINAL — {all_cells} celulas testadas (symbol x growth_rate x N)")
    print("=" * 70)
    if all_candidates:
        print(f">>> {len(all_candidates)} candidato(s) a edge (EV_lo > 0):")
        for c in all_candidates:
            print(f"    {c['symbol']} g={c['growth_rate']} N={c['target_n']}: "
                  f"EV_lo=${c['ev_lo']:+.4f} (P_emp={c['p_emp']*100:.1f}%, N_amostra={c['n_amostra']})")
        print("\n>>> PRE-REQUISITO antes de qualquer capital: confirmar com uma 2a amostra")
        print("    independente (rodar de novo em outro momento) -- viés de multiplos testes")
        print(f"    ({all_cells} celulas testadas, esperar ~{all_cells*0.05:.1f} falsos positivos a 5%).")
    else:
        print(">>> SEM EDGE. 0 celulas com EV_lo>0 em nenhum symbol/growth_rate/N testado.")
        print("    Consistente com o padrao do resto do ecossistema: margem da casa embutida")
        print("    na largura da barreira, calibrada para o growth_rate cobrado.")


if __name__ == "__main__":
    asyncio.run(main())
