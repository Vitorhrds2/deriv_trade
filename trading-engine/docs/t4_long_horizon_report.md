# T4 — Viés direcional pós-choque em horizonte longo (BTCUSDT real)

*Data:* **29 de Junho de 2026**
*Script:* `realmarket_backtest.py --longsweep` · *Evidência:* `logs/t4_longsweep.out`
*Dados:* Binance aggTrades diários, **2026-06-21 a 2026-06-27 (7 dias, ~7,2M ticks)**, cache em `binance_cache/`.

---

## 1. Hipótese (premissa pura)
Após um choque de preço (`≥ threshold` em `≤ 500ms`), existe **viés direcional** — continuação (momentum) **ou** reversão (fade) — ao longo de **minutos a 1 hora**? Se nem o retorno **bruto** (sem custo/multiplier) bater o nulo aleatório com IC95% > 0, T4 morre antes de discutir instrumento ou liquidação.

## 2. Método (rigor)
- **Trades não-sobrepostos** (`cooldown = hold`) para não inflar significância por autocorrelação.
- Entrada no **gatilho + latência** (150ms), saída real após o hold. Mede retorno **bruto**.
- **Controle nulo**: direção aleatória nos mesmos gatilhos. Momentum e fade são comparados contra o nulo.
- **Bootstrap IC95%** no retorno médio por célula.
- Grade: `thr = {30, 50, 75, 100}` × `hold = {1, 3, 5, 15, 30, 60} min` = **24 células**.
- **Powered/OOS**: 7 dias diferentes (vs. 1 dia da rodada anterior).

## 3. Resultado
- De **24 células**, **apenas 1** teve IC95% > 0: `FADE thr=30 hold=5min` → `+0.0226%` (IC_lo `+0.0037`).
- Essa célula é **sub-custo** (break-even `~0.0300%/trade`) **e** um **fluke de múltiplos testes** (1 em 24, IC_lo mal acima de zero).
- **Momentum** (a hipótese principal) **não tem viés positivo com IC95% > 0 em nenhuma célula**. As médias grandes em holds de 60min (`+0.10%`, `+0.32%`) vêm de `N` minúsculo (13–119) com IC cruzando zero → ruído.

```
>>> 1 celula(s) com IC95%>0 (vies direcional bruto):
    FADE thr=30 hold=300s: +0.0226% (IC_lo +0.0037) vs be 0.0300% -> mas SUB-CUSTO
>>> Vies de multiplos testes! OBRIGATORIO validar OOS + custo + liquidacao.
```

## 4. Conclusão
**T4 refutado com poder.** Pós-choque em horizonte longo é **ruído**: nenhum viés direcional (momentum nem fade) sobrevive ao controle nulo + custo, mesmo em 7 dias OOS. A única célula "positiva" é sub-custo e artefato de múltiplos testes. Não há premissa para prosseguir a instrumento/liquidação.

## 5. Reproduzir
```bash
python realmarket_backtest.py --symbol BTCUSDT --start 2026-06-21 --days 7 --longsweep \
    --window-ms 500 --latency-ms 150 \
    --lh-thresholds 30,50,75,100 --lh-holds 60,180,300,900,1800,3600
```
