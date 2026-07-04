"""
Unifica os orquestradores de TESTE (nao de bots ao vivo) do Mega Brain 2.0.

Diferenca de proposito vs. mega_brain_orchestrator.py / multi_market_orchestrator.py /
real_market_orchestrator.py / battle_launcher.py: aqueles rodam BOTS que arriscam capital
(demo ou real) continuamente. Este roda scripts de ANALISE/AUDITORIA (read-only ou stake
minimo controlado internamente) que TERMINAM sozinhos e imprimem um veredito, e consolida
tudo em um relatorio unico -- o objetivo e testar hipoteses novas rapido, em paralelo, sem
duplicar boilerplate de subprocess/logging a cada novo script.

Registro de hipoteses = HYPOTHESIS_SUITE abaixo. Adicionar uma nova hipotese = adicionar uma
linha aqui apontando pro script (mesmo padrao de hypothesis_configs.json, mas para testes).

Uso:
  python run_hypothesis_suite.py                  # roda todas
  python run_hypothesis_suite.py --only jump,vanilla   # roda so um subconjunto (por id)
  python run_hypothesis_suite.py --list            # so lista as hipoteses registradas
"""
import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class HypothesisTest:
    id: str
    name: str
    cmd: list
    needs_api: bool = True      # se True, escalona o lancamento p/ nao estourar rate-limit da Deriv
    timeout_s: int = 600
    tail_lines: int = 18        # quantas linhas finais do stdout guardar no resumo


HYPOTHESIS_SUITE = [
    HypothesisTest(
        id="hft_audit", name="Fase 1: Auditoria hft_bot (logs locais)",
        cmd=[sys.executable, "audit_hft_trades.py"], needs_api=False, timeout_s=120,
    ),
    HypothesisTest(
        id="jump", name="Fase 2: Jump Indices spike-timing",
        cmd=[sys.executable, "jump_index_spike_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="vanilla", name="Fase 2: Vanilla Options mispricing",
        cmd=[sys.executable, "vanilla_edge_scan.py"], timeout_s=600,
    ),
    HypothesisTest(
        id="boom_crash", name="T2: Boom/Crash SPIKE_TIMING",
        cmd=[sys.executable, "boom_timing_test.py", "--chunks", "15"], timeout_s=400,
    ),
    HypothesisTest(
        id="accumulator", name="Fase 2: Accumulators edge scan",
        cmd=[sys.executable, "accumulator_edge_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="tickhigh", name="Fase 3: High/Low Ticks (TICKHIGH/TICKLOW) mispricing",
        cmd=[sys.executable, "tickhigh_edge_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="runs", name="Fase 3: Only Ups/Only Downs (RUNHIGH/RUNLOW) mispricing",
        cmd=[sys.executable, "runs_edge_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="asian", name="Fase 3: Asians (ASIANU/ASIAND) mispricing",
        cmd=[sys.executable, "asian_edge_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="reset", name="Fase 3: Reset Call/Put (RESETCALL/RESETPUT) mispricing",
        cmd=[sys.executable, "reset_edge_scan.py"], timeout_s=400,
    ),
    HypothesisTest(
        id="turbos", name="Fase 3: Turbos (TURBOSLONG/TURBOSSHORT) mispricing",
        cmd=[sys.executable, "turbos_edge_scan.py"], timeout_s=600,
    ),
    HypothesisTest(
        id="higher_lower", name="Fase 3: HIGHER/LOWER barrier mispricing",
        cmd=[sys.executable, "higher_lower_edge_scan.py"], timeout_s=600,
    ),
    HypothesisTest(
        id="multiplier", name="Fase 4: Multipliers (MULTUP/MULTDOWN) mispricing standalone",
        cmd=[sys.executable, "multiplier_edge_scan.py"], timeout_s=900,
    ),
    HypothesisTest(
        id="early_sell", name="Fase 4: Early sell optionality (bid_price vs hold)",
        cmd=[sys.executable, "early_sell_test.py", "--trials", "20"], timeout_s=2400,
    ),
    HypothesisTest(
        id="cross_symbol", name="Fase 4: Cross-symbol arbitrage (RNG independence)",
        cmd=[sys.executable, "cross_symbol_arb_test.py"], timeout_s=600,
    ),
    HypothesisTest(
        id="dex_arb", name="Fase 5: DEX arbitrage (Jupiter vs Binance + triangular)",
        cmd=[sys.executable, "dex_arb_scan.py", "--duration-min", "10", "--interval-s", "7"], timeout_s=900,
    ),
    HypothesisTest(
        id="pa1_pa4", name="Fase 5: PA1-PA4 Polymarket (multi-outcome + cross-market + new market + near-resolution)",
        cmd=[sys.executable, "polymarket_arb_scan.py", "--duration-min", "10", "--interval-s", "20"], timeout_s=900,
    ),
    HypothesisTest(
        id="dex_cross_agg", name="Fase 5: D6 Cross-aggregator DEX arb (OpenOcean vs Paraswap vs LiFi on BSC/Base/Arb/Polygon)",
        cmd=[sys.executable, "dex_cross_agg_scan.py", "--duration-min", "10", "--interval-s", "30"], timeout_s=900,
    ),
    HypothesisTest(
        id="cex_arb", name="Fase 5: D7+D8 CEX-CEX arb + Triangular (Binance/Bybit/OKX)",
        cmd=[sys.executable, "cex_arb_scan.py", "--duration-min", "10", "--interval-s", "15"], timeout_s=900,
    ),
    HypothesisTest(
        id="funding_carry", name="Fase 5: D9 Funding rate carry trade scan (Binance/Bybit/OKX perps)",
        cmd=[sys.executable, "funding_rate_scan.py", "--days", "30"], timeout_s=300,
    ),
    HypothesisTest(
        id="defi_liq", name="Fase 5: D10 DeFi liquidation scan (Aave V3 via RPC)",
        cmd=[sys.executable, "defi_liquidation_scan.py", "--blocks", "200000", "--chains", "base"], timeout_s=300,
    ),
    HypothesisTest(
        id="options_iv", name="Fase 5: D11 Options IV mispricing scan (Deribit BTC/ETH)",
        cmd=[sys.executable, "options_iv_scan.py"], timeout_s=120,
    ),
    HypothesisTest(
        id="stat_arb", name="Fase 5: D12 Statistical arbitrage scan (Binance pairs trading)",
        cmd=[sys.executable, "stat_arb_scan.py", "--interval", "1d", "--limit", "500"], timeout_s=300,
    ),
    HypothesisTest(
        id="funding_signal", name="Fase 6: D13 Funding rate directional signal scan",
        cmd=[sys.executable, "funding_signal_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="trend_follow", name="Fase 6: D14 BTC trend following scan",
        cmd=[sys.executable, "trend_follow_scan.py"], timeout_s=120,
    ),
    HypothesisTest(
        id="combined_signal", name="Fase 6: D15 Combined funding + trend signal scan",
        cmd=[sys.executable, "combined_signal_scan.py"], timeout_s=120,
    ),
    HypothesisTest(
        id="cvd_signal", name="Fase 6: D16v2 CVD / order flow signal (rigorous: 5k candles, k-fold, Bonferroni)",
        cmd=[sys.executable, "cvd_signal_v2_scan.py", "--interval", "1h", "--limit", "5000", "--k-folds", "5"], timeout_s=600,
    ),
    HypothesisTest(
        id="token_unlock", name="Fase 6: D17 Token unlock impact (short pre-unlock)",
        cmd=[sys.executable, "token_unlock_scan.py"], timeout_s=300,
    ),
    HypothesisTest(
        id="listing_impact", name="Fase 6: D18 Binance listing announcement impact",
        cmd=[sys.executable, "listing_impact_scan.py"], timeout_s=600,
    ),
]

STAGGER_S = 4  # atraso entre lancamentos de scripts que usam a API da Deriv (evita bater rate-limit junto)


async def run_one(test: HypothesisTest, log_dir: Path):
    log_path = log_dir / f"{test.id}.log"
    print(f"[{test.id}] iniciando -> {' '.join(test.cmd)}  (log: {log_path.name})")
    t0 = time.time()
    with open(log_path, "w") as logf:
        try:
            proc = await asyncio.create_subprocess_exec(
                *test.cmd, cwd=str(HERE),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            lines = []
            try:
                async def _pump():
                    async for raw in proc.stdout:
                        line = raw.decode(errors="replace")
                        logf.write(line)
                        lines.append(line.rstrip("\n"))
                await asyncio.wait_for(_pump(), timeout=test.timeout_s)
                await proc.wait()
                status = f"OK (exit={proc.returncode})" if proc.returncode == 0 else f"FALHOU (exit={proc.returncode})"
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                status = f"TIMEOUT (>{test.timeout_s}s)"
        except FileNotFoundError as e:
            status = f"ERRO ao iniciar: {e}"
            lines = []
    dt = time.time() - t0
    tail = lines[-test.tail_lines:] if lines else []
    print(f"[{test.id}] concluido em {dt:.0f}s -> {status}")
    return {"id": test.id, "name": test.name, "status": status, "elapsed_s": dt, "tail": tail}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="lista de ids separados por virgula (ex.: jump,vanilla)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for t in HYPOTHESIS_SUITE:
            print(f"  {t.id:12s} {t.name}")
        return

    selected = HYPOTHESIS_SUITE
    if args.only:
        wanted = set(s.strip() for s in args.only.split(","))
        selected = [t for t in HYPOTHESIS_SUITE if t.id in wanted]
        missing = wanted - {t.id for t in selected}
        if missing:
            print(f"AVISO: ids nao encontrados no registro: {missing}")

    log_dir = HERE / "logs" / "hypothesis_suite"
    log_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"MEGA BRAIN — Hypothesis Suite ({len(selected)} hipoteses, logs em {log_dir})")
    print("=" * 70)

    tasks = []
    delay = 0.0
    for t in selected:
        tasks.append(asyncio.create_task(_delayed(t, log_dir, delay)))
        if t.needs_api:
            delay += STAGGER_S

    results = await asyncio.gather(*tasks)

    print("\n" + "=" * 70)
    print("RESUMO CONSOLIDADO — Mega Brain Hypothesis Suite")
    print("=" * 70)
    for r in results:
        print(f"\n### {r['id']} — {r['name']}  [{r['status']}, {r['elapsed_s']:.0f}s]")
        for line in r["tail"]:
            print(f"    {line}")

    report_path = HERE / "logs" / "hypothesis_suite" / "SUMMARY.md"
    with open(report_path, "w") as f:
        f.write("# Mega Brain — Hypothesis Suite Summary\n\n")
        for r in results:
            f.write(f"## {r['id']} — {r['name']}\n\n**Status:** {r['status']} ({r['elapsed_s']:.0f}s)\n\n```\n")
            f.write("\n".join(r["tail"]))
            f.write("\n```\n\n")
    print(f"\nRelatorio salvo em: {report_path}")


async def _delayed(test, log_dir, delay):
    if delay:
        await asyncio.sleep(delay)
    return await run_one(test, log_dir)


if __name__ == "__main__":
    asyncio.run(main())
