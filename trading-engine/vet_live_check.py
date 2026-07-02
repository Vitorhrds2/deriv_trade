"""Verificacao AO VIVO do auto-vet: roda Monitor._vet_ev_edge contra a API real e diz se
um candidato EV_EDGE sobreviveria a uma amostra fresca grande. Serve de prova (o falso
R_50/DIGITUNDER:4 deve ser REJEITADO) e de ferramenta para vetar candidatos futuros a mao.

Uso:
  python vet_live_check.py R_50 DIGITUNDER:4 2.43        # gross informado
  python vet_live_check.py R_50 DIGITUNDER:4             # busca o gross via proposal ao vivo
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

from synthetic_anomaly_monitor import Config, Monitor, get_gross_return, parse_contracts

load_dotenv()


async def main():
    sym = sys.argv[1] if len(sys.argv) > 1 else "R_50"
    label = sys.argv[2] if len(sys.argv) > 2 else "DIGITUNDER:4"
    gross_arg = float(sys.argv[3]) if len(sys.argv) > 3 else None
    cfg = Config(symbols=[sym], contracts=parse_contracts(label),
                 app_id=os.getenv("DERIV_APP_ID", "1089") or "1089",
                 api_token=os.getenv("DERIV_API_TOKEN", ""), vet_sample=40000)
    spec = cfg.contracts[0]
    m = Monitor(cfg)
    await m.client.connect()
    await m._load_pips()
    gross = gross_arg
    if gross is None:
        gross = await get_gross_return(m.client, sym, spec, cfg.stake, cfg.duration, cfg.duration_unit)
        print(f"  gross ao vivo p/ {sym} {label} = {gross}")
    pip = m.states[sym].pip
    print(f"vetando {sym} {label} @ gross {gross} (pip={pip}, amostra={cfg.vet_sample}) ...")
    if not gross:
        print("  ! sem gross (proposal indisponivel); informe na CLI")
        await m.client.disconnect()
        return
    res = await m._vet_ev_edge(sym, spec, gross)
    await m.client.disconnect()
    print("RESULTADO:", res)
    if res.get("inconclusive"):
        print(">>> INCONCLUSIVO (o monitor emitiria com ressalva).")
    elif res.get("survived"):
        print(f">>> SOBREVIVERIA -> escalaria a CRITICAL. EV_lo={res['ev_lo']:+.4f}, "
              f"p in [{res['p_lo'] * 100:.2f}%, {res['p_hi'] * 100:.2f}%], n={res['n']}.")
    else:
        print(f">>> REJEITADO (blip de variancia): EV_lo={res['ev_lo']:+.4f}, "
              f"p in [{res['p_lo'] * 100:.2f}%, {res['p_hi'] * 100:.2f}%], n={res['n']}.")
        print(">>> O auto-vet teria matado o falso-positivo R_50 ANTES de virar CRITICAL.")


if __name__ == "__main__":
    asyncio.run(main())
