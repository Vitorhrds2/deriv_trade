# D35 — Funding Rate Prediction (momentum + premium index)

**Data:** 2026-07-04
**Status:** REFUTADO (backtest decisivo)
**Autor:** `funding_prediction_scan.py` + `funding_momentum_backtest.py`
**Confiança:** 10% (refutado após backtest rigoroso)

## Tese

Binance funding rate é determinada por: `funding = clamp(premium_index + 0.01%, ±0.75%)`.
Premium index é publicado em tempo real → podemos prever funding ANTES de ser postado.

Estratégia: se premium > 0.1% → SHORT para receber funding positivo.
Também testa momentum: últimos 3 fundings positivos predizem próximo positivo?

## Metodologia

### Fase 1 — Scan inicial (direction prediction)
- Fetch de funding history para top 10 perps (BTC, ETH, SOL, etc)
- Teste de momentum: últimos 3 fundings predizem direção do próximo?
- N = 205 funding events

### Fase 2 — Backtest decisivo (profitability after fees)
- 3 estratégias testadas em top 20 perps, ~30 dias de history
- **Strategy 1:** 3-period momentum (last 3 same direction)
- **Strategy 2:** 2-period momentum (last 2 same direction)
- **Strategy 3:** 1-period momentum (follow last funding)
- Fee: 0.08% roundtrip (0.04% taker × 2 sides)
- Position size: $1,000
- N = 1,269 trades (Strategy 1), 1,517 (Strategy 2), 1,980 (Strategy 3)

## Resultados

### Fase 1 — Direction prediction

| Métrica | Valor |
|---|---|
| Momentum accuracy | **88.7%** (N=204) |
| Últimos 3 fundings predizem próximo | Sim, altamente significativo |

### Fase 2 — Backtest after fees (DECISIVO)

| Estratégia | Trades | Dir WR | Profit WR | EV/trade | Total P&L | Sharpe | Annualized |
|---|---|---|---|---|---|---|---|
| 3-period | 1,269 | 87.3% | **11.7%** | -$0.43 | -$548 | -0.36 | -47.3% |
| 2-period | 1,517 | 84.7% | **10.0%** | -$0.48 | -$721 | -0.42 | -52.1% |
| 1-period | 1,980 | 77.4% | **7.9%** | -$0.53 | -$1,056 | -0.53 | -58.4% |

### Per-symbol breakdown (3-period momentum)

| Symbol | Trades | WR% | Total P&L | Avg Funding% |
|---|---|---|---|---|
| LABUSDT | 91 | 70.3% | +$142.81 | -0.2319% |
| SLXUSDT | 93 | 74.2% | +$74.81 | -0.1617% |
| BNBUSDT | 13 | 0.0% | -$9.59 | +0.0022% |
| BTCUSDT | 58 | 0.0% | -$44.05 | +0.0028% |
| ETHUSDT | 51 | 0.0% | -$39.03 | +0.0011% |
| SOLUSDT | 70 | 0.0% | -$50.82 | -0.0033% |

### Achado central

**Momentum prediz direção corretamente (87.3%), mas NÃO É PROFITÁVEL após fees.**

O problema: funding rates médios são 0.002-0.01% — 10x menores que as fees de 0.08%
roundtrip. Momentum acerta a direção, mas o valor coletado é insuficiente para cobrir custos.

**Exceções:** LABUSDT (+$142.81, WR 70.3%) e SLXUSDT (+$74.81) — perps com funding médio
anormalmente alto (-0.23% e -0.16%). Mas estes são outliers e podem não persistir.

## Veredito

**REFUTADO.** Funding momentum é real (87.3% direction accuracy) mas:
1. Funding rates são太小 vs fees na maioria dos períodos
2. Profitable WR é apenas 11.7% (vs 87.3% direction WR)
3. EV -$0.43/trade, annualized -47.3%
4. Edge só existe quando funding > 0.08% (alta volatilidade) — mas estes períodos são raros
5. Exceções (LABUSDT, SLXUSDT) são perps illiquid com funding anômalo — não escaláveis

Paper bot `fund_paper` parado na AWS após refutação.

## Arquivos

- **Scan script:** `trading-engine/funding_prediction_scan.py`
- **Backtest script:** `trading-engine/funding_momentum_backtest.py`
- **Paper bot:** `trading-engine/funding_paper_bot.py` (parado)
- **Results:** `funding_momentum_backtest_results.json`
- **Dashboard:** `hypothesis-lab-os/src/lib/hypotheses-data.ts` (HYP-FUNDPRED-01)
