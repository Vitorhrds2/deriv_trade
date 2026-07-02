# T3 v2 — Valor-relativo em contratos exóticos/barreira (Deriv sintéticos)

*Data:* **29 de Junho de 2026**
*Script:* `exotic_value_scan.py` · *Probe de specs:* `probe_contracts_for.py` · *Evidência:* `logs/anomaly_monitor/t3_exotic_scan.out`
*Antecedente:* T3 v1 (`relative_value_scan.py`) cobriu Rise/Fall por duração → margem da casa em toda duração.

---

## 1. Hipótese
A margem da casa pode **variar entre famílias de payoff**. Os exóticos têm payoff **path-dependent** (tocar/ficar dentro), então a precificação pode deixar uma duração/barreira com EV > 0 (valor-relativo explorável) que o Rise/Fall não revela.

Contratos varridos: **ONETOUCH, NOTOUCH** (toca/não toca), **EXPIRYRANGE, EXPIRYMISS** (termina dentro/fora), **RANGE, UPORDOWN** (fica dentro / sai). Higher/Lower (CALL/PUT com barreira) ficou de fora: a API limita a distância da barreira em durações curtas (`Invalid barrier`) e é quase-vanilla (já coberto no v1).

## 2. Método (3 medidas independentes por célula)
1. **P_emp** — probabilidade de vitória medida em **janelas NÃO-sobrepostas** (`step = n`) do histórico do próprio feed (model-free), com barreira relativa ao início de cada janela.
2. **P_mc** — probabilidade teórica por **Monte Carlo no GBM driftless** (`mu = 0`). É **fiel**: o índice sintético só existe nos ticks e a Deriv avalia a barreira tick a tick, logo um GBM discreto por tick é o modelo correto, não uma aproximação.
3. **payout** — `gross_return` real ao vivo (`proposal` da API) = `payout / ask`.

`EV/$1 = P_emp · gross_return − 1`. Barreira = `k · σ_horizonte`, com `σ_horizonte = sd · √n` e `n = duração_s / tick_dt` (tick_dt medido do feed).

**Gate de credibilidade** (mesma filosofia do auto-vet do monitor): uma célula só é candidata a edge se `EV_lo > 0` **E** `|P_emp − P_mc| < 3pp` **E** `N ≥ 100` janelas independentes.

## 3. Dois falsos-positivos capturados e corrigidos
O scan ingênuo (1ª versão) cuspia **dezenas de "EDGE+"** (até `EV_lo +0.14`). Ambos eram artefato:

- **Drift de amostra.** Os sintéticos são **martingales por construção** (`mu = 0`). Calibrar `mu` de uma amostra finita capta ruído `~N(0, sd/√N)`; injetado no MC, ele inflava probabilidade de tocar/ficar **para cima** (todos os `ONETOUCH_up` "ganhavam"). Prova decisiva: `ONETOUCH_up 600s k=1.0` dava `P_mc ≈ implied ≈ 31.7%` sob `mu=0` (princípio de reflexão), confirmando que o "edge" era 100% o drift. → **Corrigido: MC driftless por padrão** (`--use-drift` só para diagnóstico).
- **Janelas sobrepostas.** Medir `P_emp` deslizando 1 tick com janelas de 600 ticks dá ~166 amostras **independentes** em 100k ticks, mas o Wilson era calculado com `N ≈ 100k` → IC ~15× estreito demais → `EV_lo > 0` falso. → **Corrigido: janelas não-sobrepostas** (`step = n`), IC honesto.

## 4. Resultado final (chunks 40, MC 20k, R_100 + 1HZ100V)
- **0 células com `EV_lo > 0`.** O único sobrevivente da versão anterior (`1HZ100V EXPIRYRANGE 600s k=1.5`, `P_emp=100%`) **sumiu** ao aumentar o histórico → era fluke de N baixo (~33 janelas).
- Pelo **MC driftless (DGP verdadeiro)**, `P_mc < implied` em **toda** célula.
- `max|P_emp − P_mc|` caiu de **13.41pp → 5.83pp**, resíduo dominado por células de N baixo.

```
>>> SEM EDGE. 0 celula(s) com EV_lo>0. Pelo MC driftless, P_mc < implied em toda
    celula -> margem da casa nos exoticos tambem. Os 'edges' eram drift + N baixo.
```

## 5. Conclusão
**Não há valor-relativo nos exóticos/barreira.** A margem da casa está presente em touch/no-touch/ends/stays exatamente como no Rise/Fall (v1). O DGP driftless explica os preços; os "edges" do scan ingênuo eram drift de amostra + replicação pseudo de janelas. T3 (v1 + v2) encerrado **sem edge**.

## 6. Reproduzir
```bash
python exotic_value_scan.py --symbols R_100,1HZ100V --chunks 40 \
    --durations-s 120,300,600 --k 1.0,1.5 --mc 20000
# diagnóstico do artefato de drift:
python exotic_value_scan.py --use-drift ...   # reaparecem os 'edges' falsos
```
