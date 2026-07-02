# Mega Brain — Hypothesis Suite Summary

Todas as 5 hipoteses registradas em `run_hypothesis_suite.py` tem veredito (ultima atualizacao:
2026-07-02). `jump` e `vanilla` rodados nesta data; `hft_audit`, `boom_crash` e `accumulator`
rodados em 2026-07-01 (logs preservados, resumidos abaixo).

## jump — Fase 2: Jump Indices spike-timing

**Status:** OK (exit=0) (44s) | **Veredito: SEM EDGE**

Vies de direcao sempre dentro do IC95% de 50% (amostras de 8-17 saltos por simbolo). Hazard
rate essencialmente plano por faixa de "ticks desde o ultimo salto" em todos os 5 simbolos —
sem "temporizador" exploravel, consistente com processo memoryless.

```
JD10: N_saltos=12 | dir_up=66.7% | gap_medio=24.9min | CV=0.62 | faixa_hazard=0.000%-0.100%
JD25: N_saltos=16 | dir_up=62.5% | gap_medio=18.5min | CV=1.02 | faixa_hazard=0.000%-0.164%
JD50: N_saltos=12 | dir_up=50.0% | gap_medio=27.6min | CV=0.88 | faixa_hazard=0.000%-0.139%
JD75: N_saltos=17 | dir_up=41.2% | gap_medio=17.0min | CV=1.17 | faixa_hazard=0.000%-0.396%
JD100: N_saltos=8 | dir_up=50.0% | gap_medio=32.5min | CV=1.54 | faixa_hazard=0.000%-0.196%
```

## vanilla — Fase 2: Vanilla Options mispricing

**Status:** OK, rodado direto sem o teto de 600s da suite (21 celulas, ~20min com reconexoes) |
**Veredito: SEM EDGE**

21 celulas testadas (CALL/PUT x barreira x duracao 15m/60m em 1HZ100V), via Monte Carlo
driftless calibrado com 15000 ticks reais. **0/21 com EV_lo > 0.** EV medio -7.74% (min -20.4%,
max apenas -1.24% — nunca chegou perto de cruzar zero). Precisou rodar `vanilla_edge_scan.py`
diretamente (fora do wrapper da suite) porque o teto de 600s nao da conta da combinacao de
Monte Carlo pesado (20k sims x ate 3600 ticks) com a instabilidade conhecida do WS demo da
Deriv (cai a cada ~1 request). Log completo: `vanilla.log`.

## accumulator — Fase 2: Accumulators edge scan (2026-07-01)

**Veredito: SEM EDGE CONFIAVEL.** 630 celulas testadas (symbol x growth_rate x N). 1 unico
candidato com EV_lo > 0 (1HZ50V g=0.02 N=2: EV_lo=+$0.0019, marginal) — o proprio log ja
flagra o problema de multiplos testes (esperar ~31.5 falsos positivos a 5% em 630 celulas).
**Pre-requisito antes de qualquer capital: replicar essa celula especifica numa 2a amostra
independente.** Log completo: `accumulator.log`.

## boom_crash — T2: Boom/Crash SPIKE_TIMING (2026-07-01)

**Veredito: REFUTADA.** Pool de 238 gaps normalizados (10 simbolos). Weibull shape k=0.996
(IC95%[0.906,1.103], contem k=1), KS nao rejeita exponencial, hazard rate por idade sem
tendencia clara. Memoryless nao rejeitado — sem edge de timing. Log completo: `boom_crash.log`.

## hft_audit — Fase 1: Auditoria hft_bot (2026-07-01)

Amostra pequena (N=10 pos-corte V6.2, WR=10%, IC95% largo [1.79%,40.42%]) — inconclusivo por
falta de controle nulo explicito (hft_bot so entra na direcao do choque, nunca sorteia
'anti'). Ver `docs/hft_v62_audit_report.md` para o veredito completo e a recomendacao de
shadow A/B ao vivo. Log completo: `hft_audit.log`.
