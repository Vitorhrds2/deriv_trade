# D16v2 — CVD Signal Rigorous Re-test Report (2026-07-03)

## Contexto

D16v1 mostrou Sharpe 10+ OOS — estatisticamente irreal. Identificamos três problemas:
1. N=6-12 trades (amostra muito pequena)
2. 27+ configs testados = viés de seleção (multiple testing)
3. Annualization inflation (1h candles × sqrt(730) infla Sharpe)

D16v2 corrige os três com:
- **5000 candles** (vs 1000) — 5x mais dados
- **5-fold cross-validation** — testa robustez em 5 períodos distintos
- **Permutation test** (1000 iterations) — p-value real, não assumindo distribuição normal
- **Bonferroni correction** — alpha = 0.05 / 27 configs = 0.0019
- **Per-trade Sharpe** — sem annualization inflation
- **Edge declarado só se:** p < 0.0019 AND positivo em ≥4/5 folds

## Metodologia

- **Script:** `trading-engine/cvd_signal_v2_scan.py`
- **Dados:** Binance spot, 5000 candles 1h (~208 dias)
- **3 ativos:** BTC, ETH, SOL
- **27 configs:** 3 signal types × 3 parameters × 3 hold periods
- **K-fold:** 5 folds contíguos de 1000 candles cada
- **Permutation test:** shuffle PnL signs 1000x, comparar avg observado vs null
- **Fees:** 10 bps/side × 2 = 20 bps por round trip

## Resultados

### Resumo

| Symbol | Candles | Buy & Hold | Best Config | N | Avg bps | WR | p-value | Folds+ | Robust? |
|--------|---------|------------|-------------|---|---------|----|---------|--------|---------|
| BTC | 5000 | -30.4% (Sharpe -1.15) | reversal z=3.0, 12h | 46 | +11.7 | 63% | 0.300 | 3/5 | **NO** |
| ETH | 5000 | -42.6% (Sharpe -1.28) | diverge 96h, 48h | 51 | +64.9 | 76% | 0.107 | 4/5 | **NO** |
| SOL | 5000 | -37.5% (Sharpe -0.89) | diverge 96h, 48h | 56 | +23.7 | 70% | 0.305 | 3/5 | **NO** |

### Nenhum config passou no critério de robustez

**Bonferroni-corrected alpha = 0.0019** — nenhum config chegou perto:
- BTC: melhor p-value = 0.300 (15x acima do threshold)
- ETH: melhor p-value = 0.107 (56x acima do threshold)
- SOL: melhor p-value = 0.305 (160x acima do threshold)

### ETH diverge_96h_48h — o mais próximo de um edge

- N=51, avg=+64.9 bps, WR=76%, p=0.107, folds+=4/5
- **Quase robusto** (4/5 folds positivas) mas **não significativo** (p=0.107 >> 0.0019)
- Fold 4 foi negativa (-212.5 bps) — quebra de robustez
- WR de 76% é promissor mas pode ser sorte com N=51

### Per-fold breakdown — ETH diverge_96h_48h

| Fold | Avg bps | WR | Sharpe/trade |
|------|---------|----|-------------|
| 0 | +114.3 | 70% | 0.608 |
| 1 | +11.3 | 75% | 0.028 |
| 2 | +188.8 | 93% | 1.274 |
| 3 | -28.9 | 56% | -0.103 |
| 4 | -212.5 | 45% | -0.440 |

Fold 2 (WR 93%) sugere que o sinal funciona em certos regimes.
Fold 4 (WR 45%, -212 bps) mostra que falha em outros.
**Não é robusto — é regime-dependent.**

### Comparação v1 vs v2

| Metric | D16v1 | D16v2 |
|--------|-------|-------|
| Candles | 1000 | 5000 |
| Validation | 70/30 walk-forward | 5-fold CV |
| Multiple testing | Ignored | Bonferroni (α=0.0019) |
| P-value | Not computed | Permutation test (1000x) |
| Sharpe | Annualized (inflated) | Per-trade (conservative) |
| BTC best Sharpe | 12.09 | 0.608 (best fold) |
| ETH best Sharpe | 10.18 | 1.274 (best fold) |
| Verdict | "Inconclusive" | **Refuted** |

**O Sharpe 10+ do v1 era puramente artefato de annualization + overfitting.**
Sem annualization, o melhor per-trade Sharpe é 0.608 (fold 0, ETH) — modesto.

## Conclusão

**D16v2: CVD / order flow signal — REFUTADO.**

- Nenhum config passou no Bonferroni-corrected significance test
- Nenhum config foi robusto em 5-fold cross-validation
- O Sharpe 10+ do v1 era artefato de annualization inflation + multiple testing
- ETH diverge_96h_48h (WR 76%, p=0.107) é o mais próximo de um edge mas não é estatisticamente significativo
- O sinal CVD é **regime-dependent** — funciona em alguns períodos (fold 2: WR 93%) mas falha em outros (fold 4: WR 45%)
- **Conceito de microestrutura é válido mas não é explorável como signal standalone em 1h timeframe**

## Lições metodológicas

1. **Annualization inflation:** Sharpe per-trade × sqrt(trades/year) pode inflar 10-50x. Sempre reportar per-trade Sharpe.
2. **Multiple testing:** 27 configs × 3 symbols = 81 testes. Pegar o melhor = viés de seleção. Bonferroni é conservador mas necessário.
3. **K-fold > walk-forward:** Walk-forward único (70/30) é 1 fold. K-fold (5) testa robustez em 5 períodos.
4. **Permutation test:** Não assume distribuição normal. Mais robusto para PnL com outliers.

## Arquivos

- **Script:** `trading-engine/cvd_signal_v2_scan.py`
- **Dados:** `trading-engine/cvd_signal_v2_samples.json`
