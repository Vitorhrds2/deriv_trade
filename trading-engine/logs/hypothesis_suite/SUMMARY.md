# Mega Brain — Hypothesis Suite Summary

Todas as 10 hipoteses registradas em `run_hypothesis_suite.py` tem veredito (ultima atualizacao:
2026-07-03). `jump` e `vanilla` rodados em 2026-07-02; `hft_audit`, `boom_crash` e `accumulator`
rodados em 2026-07-01 (logs preservados, resumidos abaixo). As 5 hipoteses da Fase 3
(`tickhigh`, `runs`, `asian`, `reset`, `turbos`) cobrem produtos da Deriv NUNCA testados neste
ecossistema ate 2026-07-03 -- rodadas diretamente (fora do wrapper da suite, mesmo motivo do
`vanilla`: Monte Carlo pesado + instabilidade conhecida do WS demo).

## tickhigh — Fase 3: High/Low Ticks (TICKHIGH/TICKLOW) mispricing (2026-07-03)

**Veredito: SEM EDGE.** Descoberta inicial intrigante: o payout cotado por posicao tem formato
em U (posicao 1 e 5 pagam mais que 2,3,4) — a hipotese ingenua "5 ticks intercambiaveis => 1/5
de chance cada" sugeriria mispricing grande. Mas a distribuicao EMPIRICA da posicao do
extremo (Monte Carlo driftless, 200k simulacoes bootstrap com ticks reais de 1HZ100V) bate
quase exatamente com a formula teorica da lei do arcsine/Sparre-Andersen para passeios
aleatorios simetricos (ex.: posicao 1: 26.78% empirico vs 27.34% teorico; posicao 3: 14.19%
vs 14.06%). A Deriv precifica corretamente segundo a teoria certa, nao a ingenua — depois de
usar o fair value certo, sobra so o house edge normal. **0/10 celulas (TICKHIGH/TICKLOW x
posicao 1-5) com EV_lo>0.** EV entre -2.1% e -8.4% do stake (media -6.0%), dentro do padrao do
resto do ecossistema. Achado
metodologicamente relevante: mostra por que comparar contra o fair value CORRETO (nao um
baseline ingenuo) e essencial antes de declarar mispricing.

## runs — Fase 3: Only Ups/Only Downs (RUNHIGH/RUNLOW) mispricing (2026-07-03)

**Veredito: SEM EDGE.** Mecanica: paga se os proximos N ticks (N=2..5) subirem/descerem
sucessivamente. Medido via replay direto (nao bootstrap) de 15000 ticks reais em janelas NAO
sobrepostas (evita autocorrelacao), usando o criterio literal do longcode. **0/8 celulas
(RUNHIGH/RUNLOW x N=2,3,4,5) com EV_lo>0** — EV entre -3.8% e -19.2% do stake. Nota: a
probabilidade empirica de sequencia ficou consistentemente um pouco ABAIXO do ingenuo 0.5^N
(ex.: N=2 empirico 23.2%-24.4% vs 25% ingenuo), provavelmente por ticks empatados/planos que
quebram ambas as direcoes — so reforca a conclusao negativa, nao muda o veredito.

## asian — Fase 3: Asians (ASIANU/ASIAND) mispricing (2026-07-03)

**Veredito: SEM EDGE.** Mecanica: paga se o ultimo tick de uma janela de N ticks (N=5..10) for
maior/menor que a MEDIA da janela. Fair value teorico e exatamente 50% por simetria (processo
driftless continuo) — confirmado empiricamente via replay direto de ticks reais em todas as 6
duracoes (P_emp sempre entre 48.7% e 51.1%, dentro do IC95% de 50%). **0/12 celulas
(ASIANU/ASIAND x N=5..10) com EV_lo>0.** Payout cotado ~$19.53 vs fair value $20.00 — house
edge pequeno e consistente (~2-3%), o menor "spread ingenuo vs cotado" do ecossistema.

## reset — Fase 3: Reset Call/Put (RESETCALL/RESETPUT) mispricing (2026-07-03)

**Veredito: SEM EDGE.** Mecanica: strike "reseta" para o menor (RESETCALL) ou maior
(RESETPUT) entre o preco de entrada e o preco no meio do contrato — mais favoravel ao
comprador que uma call/put ATM comum (P(vitoria) teorico >50%). Monte Carlo driftless (20k
simulacoes, 2 checkpoints) em 4 duracoes (5m/15m/30m/60m) mediu P_emp consistente ~62-63% para
ambos os lados. **0/8 celulas com EV_lo>0** — mas com a margem mais fina encontrada no projeto
ate agora: EV entre -1.1% e -2.7% do stake (payout cotado ~$15.7 vs fair value ~$15.9-16.0).
Vale re-visitar se a Deriv reprecificar esse produto no futuro, mas hoje fica dentro do erro
estatistico esperado de um house edge legitimo, nao um sinal de mispricing.

## turbos — Fase 3: Turbos (TURBOSLONG/TURBOSSHORT) mispricing (2026-07-03)

**Veredito: SEM EDGE.** Produto mais complexo testado: barreira de knockout (LONG usa
distancia negativa abaixo do spot, SHORT usa distancia positiva acima) + payout escalavel
(`payout_per_point x distancia entre preco final e barreira`, se sobreviver ate o expiry sem
tocar a barreira). Monte Carlo driftless vetorizado (numpy, 10k simulacoes de path completo
com deteccao de touch, nao so 2 checkpoints) cobrindo as 10 distancias de barreira x 2
duracoes (15m/60m) x LONG/SHORT = 40 celulas, **40/40 com dados validos, 0 com EV_lo>0**. EV
entre -0.03% (barreiras mais distantes, quase 100% sobrevivencia) e -7.8% (barreiras mais
proximas, maior risco de knockout) — padrao monotono e suave, sem nenhuma distancia ou
duracao chegando perto de EV positivo. Nota tecnica: o probe inicial tinha um bug de
"barreira obsoleta" (placeholder coincidia por acaso com um tier valido, casando o
payout_per_point de UM tier com o barrier_rel de OUTRO e inflando o EV artificialmente para
50-150x o stake) — corrigido forcando descoberta de barreira fresca via `error.details.
barrier_choices` a cada consulta; o padrao final e limpo e internamente consistente.

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

## accumulator — Fase 2: Accumulators edge scan (2026-07-01, replicado 2026-07-02)

**Veredito: SEM EDGE (confirmado por replicacao).** Amostra original (07-01, `accumulator.log`):
630 celulas testadas (symbol x growth_rate x N), 1 unico candidato com EV_lo > 0 (1HZ50V g=0.02
N=2: EV_lo=+$0.0019, marginal) — o proprio log ja flagrava o problema de multiplos testes
(esperar ~31.5 falsos positivos a 5% em 630 celulas) e exigia replicacao antes de qualquer
capital. **Replicacao rodada em 07-02 com amostra fresca e independente** (`ticks_stayed_in`
e mantido pela propria API da Deriv, nao precisa esperar 24h manualmente — so rodar de novo):
`accumulator_replication.log`, **0/630 celulas com EV_lo>0** — o candidato de 07-01 NAO se
repetiu, confirmando que era ruido de multiplos testes, nao edge real. Hipotese encerrada.

## boom_crash — T2: Boom/Crash SPIKE_TIMING (2026-07-01)

**Veredito: REFUTADA.** Pool de 238 gaps normalizados (10 simbolos). Weibull shape k=0.996
(IC95%[0.906,1.103], contem k=1), KS nao rejeita exponencial, hazard rate por idade sem
tendencia clara. Memoryless nao rejeitado — sem edge de timing. Log completo: `boom_crash.log`.

## hft_audit — Fase 1: Auditoria hft_bot (2026-07-01)

Amostra pequena (N=10 pos-corte V6.2, WR=10%, IC95% largo [1.79%,40.42%]) — inconclusivo por
falta de controle nulo explicito (hft_bot so entra na direcao do choque, nunca sorteia
'anti'). Ver `docs/hft_v62_audit_report.md` para o veredito completo e a recomendacao de
shadow A/B ao vivo. Log completo: `hft_audit.log`.
