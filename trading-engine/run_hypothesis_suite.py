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
