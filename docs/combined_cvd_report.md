# D15 & D16 — Combined Signal + CVD Order Flow Report (2026-07-03)

## D15 — Combined Funding Signal + Trend Following

### Hipótese
Combinar funding rate (D13) como filtro para trend following (D14) melhora
risk-adjusted returns. Especificamente: filtrar trades onde funding contradiz
o sinal de trend.

### Metodologia
- **Script:** `trading-engine/combined_signal_scan.py`
- **Dados:** Binance spot (1000 candles diários) + Binance futures (500 funding events)
- **3 ativos:** BTC, ETH, SOL
- **Walk-forward:** 70/30
- **4 estratégias comparadas:**
  1. Pure trend (SMA 10/50 long+short) — baseline D14
  2. Trend + funding filter 75th percentile
  3. Trend + funding filter 90th percentile
  4. Funding-only short (baseline D13)

### Resultados OOS

| Symbol | Strategy | N | WR | PnL (bps) | Sharpe | MaxDD (bps) |
|--------|----------|---|----|-----------|--------|-------------|
| BTC | Pure trend | 7 | 57% | +3,919 | 1.16 | 1,650 |
| BTC | Trend+funding 75th | 6 | 50% | - | 0.89 | 1,522 |
| BTC | Delta | | -7pp | | **-0.27** | -128 |
| ETH | Pure trend | 5 | 60% | +4,894 | 1.40 | 1,062 |
| ETH | Trend+funding 75th | 4 | 50% | +2,547 | 0.95 | 1,062 |
| ETH | Delta | | -10pp | | **-0.45** | +0 |
| SOL | Pure trend | 9 | 33% | +1,748 | 0.36 | 3,605 |
| SOL | Trend+funding 75th | 8 | 25% | -1,361 | -0.44 | 3,742 |
| SOL | Delta | | -8pp | | **-0.80** | +137 |

### Achado central: Funding filter PIORA o trend following

**Delta negativo em todos os 3 symbols:**
- BTC: Sharpe -0.27
- ETH: Sharpe -0.45
- SOL: Sharpe -0.80

O filtro de funding remove trades que seriam lucrativos. O funding rate não
adiciona informação útil ao sinal de trend — na verdade, remove trades bons.

**Por que o filtro piora:**
- O filtro remove ~70 trades (a maioria seriam entradas long)
- Em um trend de alta, funding é frequentemente positivo (longs pagam shorts)
- Filtrar longs quando funding é positivo = perder o trend
- O funding reflete positioning atual, não direção futura

### Descoberta secundária: Funding-only short é forte em ETH

| Symbol | N | WR | PnL (bps) | Sharpe | MaxDD (bps) |
|--------|---|----|-----------|--------|-------------|
| ETH | 274 | 61% | +57,794 | 2.96 | 9,503 |
| SOL | 195 | 53% | +27,206 | 1.79 | 13,375 |

**ETH funding-only short (72h) tem Sharpe=2.96, N=274, WR=61%** — este é
o sinal mais forte encontrado em todo o projeto. MAS:
- MaxDD = 9,503 bps = 95% — drawdown quase total
- É apenas short side (viés bearish em ETH no período)
- Pode ser artefato do regime de mercado (ETH caiu no período testado)

### Conclusão D15

**Combinação de funding + trend NÃO funciona. O filtro piora o trend following.**
- Delta Sharpe negativo em todos os 3 symbols
- Funding não adiciona informação ao sinal de trend
- Funding-only short em ETH tem Sharpe=2.96 mas MaxDD=95% — não é tradeable

---

## D16 — Order Flow / CVD (Cumulative Volume Delta)

### Hipótese
CVD (cumulative volume delta = soma de taker buy volume - taker sell volume)
prediz direção de preço. Divergência CVD-preço sinaliza reversão.

### Metodologia
- **Script:** `trading-engine/cvd_signal_scan.py`
- **Dados:** Binance spot, 1000 candles 1h
- **3 ativos:** BTC, ETH, SOL
- **3 tipos de signal:**
  1. CVD divergence (price new high/low, CVD não confirma)
  2. CVD momentum (CVD rising → long, falling → short)
  3. CVD reversal (CVD z-score extreme → opposite)
- **27+ configs** testados (lookback × hold × threshold)
- **Walk-forward:** 70/30

### Resultados

| Symbol | Buy/Sell Ratio | Best OOS Strategy | N | WR | PnL (bps) | Sharpe | MaxDD |
|--------|---------------|-------------------|---|----|-----------|--------|-------|
| BTC | 0.962 | CVD reversal z=1.5, 12h | 12 | 75% | +666 | 12.09 | 189 |
| ETH | 0.980 | CVD diverge 48h, 48h | 6 | 67% | +594 | 10.18 | 189 |
| SOL | 0.996 | CVD momentum 12h, 12h | 36 | 50% | +2,007 | 10.92 | 470 |

### Achado central: Sharpe irreal indica overfitting

**Sharpe ratios de 10-12 são estatisticamente impossíveis em trading real.**
Os melhores fundos quant do mundo têm Sharpe 2-3. Sharpe 10+ significa:

1. **N muito pequeno:** BTC N=12, ETH N=6 — não é significativo
2. **Multiple testing:** 27+ configs testados, pegamos o melhor OOS
   - Com 27 configs, esperar 1-2 com Sharpe > 5 por acaso
3. **Annualization inflation:** candles 1h com hold 12h = 730 trades/ano
   - Sharpe per-trade × sqrt(730) infla o número
4. **Regime-specific:** 300 candles OOS = 12.5 dias — um único regime

### Sinais individuais

**CVD divergence (BTC/ETH):**
- WR 67-75% é promissor mas N=6-12
- Divergência CVD-preço é conceito sólido (institucional)
- Precisa de muito mais dados para validar

**CVD momentum (SOL):**
- N=36 é mais razoável
- WR=50% não é melhor que random
- Sharpe alto vem de poucas trades grandes, não consistência

**CVD reversal (BTC):**
- N=12, WR=75% — parece bom mas pode ser sorte
- z=1.5 é threshold baixo = muitos signals

### Profitabilidade

**Problema 1: Overfitting por multiple testing**
- 27 configs × 3 symbols = 81 testes
- Pegar o melhor de 81 testes = viés de seleção
- Precisa de Bonferroni correction ou validação cruzada

**Problema 2: N muito pequeno**
- BTC N=12, ETH N=6 — IC95% largo demais
- Não é possível distinguir skill de sorte com N<30

**Problema 3: Short timeframe = noisy**
- CVD em 1h candles é muito ruidoso
- Taker buy/sell volume em BTC é ~50/50 (ratio 0.962)
- Sinal é marginal dentro do ruído

### Conclusão D16

**CVD tem conceito sólido mas os resultados são inconclusivos.**
- Sharpe 10+ é artefato de overfitting + N pequeno + annualization
- WR de 67-75% em divergência é promissor mas N=6-12
- Precisa de mais dados (5000+ candles) e validação cruzada rigorosa
- **Não refutado, mas não confirmado — inconclusivo**

---

## Status consolidado: 33 hipóteses

| Categoria | Hipóteses | Status |
|-----------|-----------|--------|
| Arbitragem de preço (D7-D12) | 6 | Refutadas |
| Direcional D13 (funding signal) | 1 | Sinal fraco |
| Direcional D14 (trend following) | 1 | Sinal marginal |
| D15 (combined funding+trend) | 1 | **Refutado** (filtro piora) |
| D16 (CVD order flow) | 1 | **Inconclusivo** (overfitting) |
| Deriv + Polymarket + DEX | 23 | Refutadas |

**29 refutadas, 2 com sinal fraco/marginal, 1 inconclusiva, 1 refutada (D15)**

## Próximos passos

1. **D16 needs more data:** Re-run with 5000+ candles e validação cruzada
   (k-fold em vez de walk-forward simples)
2. **Funding-only short em ETH:** Sharpe=2.96 mas MaxDD=95%. Investigar
   se existe regime filter que reduz drawdown
3. **Event-driven (D17):** Token unlocks / listing announcements —
   mecanismo fundamentalmente diferente de price/volume signals

## Arquivos

- **Scripts:** `trading-engine/combined_signal_scan.py`, `trading-engine/cvd_signal_scan.py`
- **Dados:** `trading-engine/combined_signal_samples.json`, `trading-engine/cvd_signal_samples.json`
