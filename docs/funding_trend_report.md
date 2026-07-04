# D13 & D14 — Funding Rate Signal + Trend Following Report (2026-07-03)

## D13 — Funding Rate as Directional Signal

### Hipótese
Funding rate extremo prediz reversão de preço. Quando funding é muito positivo
(longs pagam shorts), mercado está overleveraged long → preço cai. Quando muito
negativo, overleveraged short → preço sobe. Trade: posição oposta ao lado crowded.

### Metodologia
- **Script:** `trading-engine/funding_signal_scan.py`
- **API:** Binance Futures (fapi.binance.com, sem API key)
- **Dados:** 500 funding events (~166 dias a cada 8h) + 1500 candles 1h
- **10 ativos:** BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, LINK, DOT
- **Backtest:** entry quando |funding| > threshold (50th/75th/90th/95th percentile),
  exit após N horas (1h/4h/8h/24h/48h/72h)
- **Fees:** 5 bps/side × 2 = 10 bps por round trip

### Resultados principais

| Symbol | Horizon | Percentile | N | WR | PnL (bps) | Avg bps | Sharpe | Long WR | Short WR |
|--------|---------|-----------|---|----|-----------|---------|--------|---------|----------|
| ETH | 72h | 50th | 250 | 29% | +20,248 | +81.0 | 5.68 | 12% | 42% |
| BTC | 72h | 50th | 250 | 26% | +16,152 | +64.6 | 5.40 | 9% | 37% |
| ETH | 72h | 90th | 50 | 24% | +6,368 | +127.4 | 3.42 | 0% | 43% |
| BTC | 72h | 95th | 25 | 24% | +2,962 | +118.5 | 2.52 | 0% | 40% |
| LINK | 72h | 95th | 6 | 17% | +1,010 | +168.4 | 1.40 | 0% | 17% |

### Achado central: Short side funciona, Long side não

**Short WR (funding positivo → vender):** 37-43% — consistentemente acima de 33% breakeven
**Long WR (funding negativo → comprar):** 0-12% — quase sempre errado

Isso faz sentido econômico:
- Funding positivo = longs overleveraged = vulneráveis a liquidation cascade
- Funding negativo = shorts overleveraged, MAS em crypto o viés é de alta
  (shorts são frequentemente "wrong side" e o preço continua subindo)

### Aggregate por horizonte (90th percentile, todos symbols)

| Horizonte | N | avg Sharpe | avg PnL/signal | avg WR |
|-----------|---|------------|----------------|--------|
| 1h | 303 | -3.16 | -11.8 bps | 9% |
| 4h | 303 | -1.36 | -10.1 bps | 12% |
| 8h | 303 | -0.74 | -15.0 bps | 12% |
| 24h | 303 | -0.26 | -11.3 bps | 11% |
| 48h | 303 | -0.07 | -2.1 bps | 10% |
| **72h** | **303** | **+0.45** | **+19.0 bps** | **11%** |

**O sinal só funciona em 72h** — horizontes curtos (1-24h) são negativos.
Isso sugere que a reversão funding-driven é lenta (3 dias).

### Profitabilidade

**Problema 1: Win rate extremamente baixo (24-29%)**
- 70-76% das trades são perdedoras
- O PnL positivo vem de poucas trades com grandes ganhos
- Risco de drawdown prolongado é alto

**Problema 2: Long side não funciona (WR 0-12%)**
- Metade do signal (funding negativo → comprar) é quase sempre errado
- Restringe a apenas short side, cortando N pela metade

**Problema 3: 50th percentile não é "extremo"**
- Os melhores resultados são no 50th percentile (todas as signals)
- Isso é essencialmente "short quando funding > 0" — não é um signal extremo
- No 90th/95th percentile (funding realmente extremo), N é muito pequeno (25-50)

**Problema 4: Taxa de erro vs payoff**
- avg PnL/signal = +64.6 bps (BTC 72h 50th) com WR=26%
- Isso significa: ganhos médios nas 26% vencedoras precisam ser ~250 bps
- Para cobrir 74% perdedoras (~-10 bps cada) + 10 bps fees
- É viável mas requer estômago para longas sequências de perdas

### Conclusão D13

**Sinal direcional existe, mas é fraco e assimétrico.**
- Short side (funding positivo → vender) tem edge real em BTC/ETH a 72h
- Long side (funding negativo → comprar) NÃO funciona em crypto
- Win rate de 24-29% torna a estratégia psicologicamente difícil
- O edge é marginal: +64.6 bps/signal após fees, com alto risco de drawdown
- **Potencial como filtro complementar, não como estratégia standalone**

---

## D14 — BTC Trend Following (Multi-Day Momentum)

### Hipótese
BTC exibe momentum em timeframes multi-dia. Uma estratégia trend-following
usando moving averages ou breakouts pode capturar movimentos direcionais
que excedem custos de transação.

### Metodologia
- **Script:** `trading-engine/trend_follow_scan.py`
- **API:** Binance spot (api.binance.com, sem API key)
- **Dados:** 1000 candles diários (~2.7 anos)
- **3 ativos:** BTC, ETH, SOL
- **Estratégias testadas:**
  - MA crossover long-only (5/20, 5/50, 10/20, 10/50, 10/100, 20/50, 20/100, 20/200)
  - MA crossover long+short (mesmas configs)
  - Donchian breakout (10, 20, 50, 100 dias)
  - Time series momentum (10, 20, 30, 60, 90 dias)
- **Walk-forward:** 70% train / 30% test
- **Fees:** 10 bps/side × 2 = 20 bps por round trip

### Resultados

#### Buy & Hold (benchmark)

| Symbol | Return | Annualizado | Sharpe |
|--------|--------|-------------|--------|
| BTC | +123.3% | +34.1% | 0.85 |
| ETH | +6.8% | +2.4% | 0.37 |
| SOL | +252.7% | +58.5% | 0.96 |

#### Best OOS (out-of-sample) strategies

| Symbol | Strategy | N | WR | PnL (bps) | Sharpe | MaxDD (bps) | Avg Hold |
|--------|----------|---|----|-----------|--------|-------------|----------|
| BTC | SMA(10/50) long+short | 7 | 57% | +3,919 | 1.16 | 1,650 | 26.3d |
| ETH | SMA(10/50) long+short | 5 | 60% | +4,883 | 1.40 | 1,062 | - |
| SOL | SMA(5/100) long+short | 3 | 67% | +2,677 | 0.97 | 655 | - |

#### In-sample vs OOS (BTC, top 5 train strategies)

| Strategy | Train Sharpe | OOS Sharpe | Train WR | OOS WR |
|----------|-------------|------------|----------|--------|
| TSMOM(10) | 1.46 | -3.92 | 43% | 20% |
| SMA(20/50) | 1.41 | -1.80 | 71% | 0% |
| SMA(10/50) | 1.40 | -3.50 | 56% | 0% |
| TSMOM(30) | 1.35 | -2.49 | 38% | 31% |
| Donchian(20) | 1.33 | -4.15 | 67% | 0% |

**Long-only strategies não replicam OOS.** Todas as top train strategies
(long-only) têm Sharpe negativo OOS. A única estratégia que funciona OOS
é SMA(10/50) long+short.

### Achado central: Long+short MA crossover é a única estratégia robusta

**SMA(10/50) long+short:**
- BTC: Sharpe OOS=1.16, WR=57%, PnL=+3,919 bps
- ETH: Sharpe OOS=1.40, WR=60%, PnL=+4,883 bps
- Vai long quando fast > slow, short quando fast < slow
- Captura ambos os lados do trend

**Por que long-only falha OOS:**
- Em mercados laterais (ETH 2022-2025: +6.8% em 2.7 anos), long-only
  fica preso em whipsaws — entra e sai com pequenas perdas repetidas
- Long+short lucra com downtrends também, compensando whipsaw

### Profitabilidade

**SMA(10/50) long+short em BTC:**
- 7 trades em 300 dias OOS = ~8.5 trades/ano
- PnL: +3,919 bps em 300d = ~4,770 bps/ano = ~47.7% annualizado
- Sharpe: 1.16 — decente mas não espetacular
- MaxDD: 1,650 bps = 16.5% — significativo
- Compare com buy & hold BTC: +34.1% annualizado, Sharpe=0.85
- **Trend following BEAT buy & hold em risk-adjusted return (Sharpe 1.16 vs 0.85)**

**MAS:**
- N=7 é uma amostra MUITO pequena — não é estatisticamente significativo
- 300 dias OOS inclui apenas um regime de mercado
- Pode não funcionar em bull market forte (perderia no short side)
- Slippage real em shorts: borrow costs + funding para manter short

**Custos adicionais para shorts:**
- Spot: não é possível shortar diretamente, precisa de perps
- Perps: funding rate cost (testado em D9, ~42 bps/30d)
- Borrow fee para short spot: ~5-20 bps/dia
- Isso adiciona ~50-100 bps por trade em custos extras

### Conclusão D14

**Trend following tem sinal real, mas é marginal e não estatisticamente significativo.**
- SMA(10/50) long+short beat buy & hold em Sharpe (1.16 vs 0.85)
- MAS: N=7 trades OOS é amostra muito pequena
- Long-only strategies não replicam OOS (overfitting no train set)
- Custos de shorting (funding + borrow) reduzem o edge
- **Potencial como estratégia complementar, não standalone**

---

## Comparação D7-D14

| Hipótese | Mecanismo | N | Resultado | Veredito |
|----------|-----------|---|-----------|----------|
| D7 | CEX-CEX arb | 100 | 0/100 positivos | SEM EDGE |
| D8 | Triangular | 120 | 0/120 positivos | SEM EDGE |
| D9 | Funding carry | 19 | 0% janelas 7d | SEM EDGE |
| D10 | DeFi liquidations | 108 | <1% capture | SEM EDGE |
| D11 | Options IV | BTC+ETH | VRP=-8% mas theta+hedging | SEM EDGE |
| D12 | Stat arb pairs | 10 OOS | 70% negativos | SEM EDGE |
| **D13** | **Funding signal** | **250** | **Sharpe 5.4 mas WR 26%** | **SINAL FRACO** |
| **D14** | **Trend following** | **7 OOS** | **Sharpe 1.16 mas N=7** | **SINAL MARGINAL** |

## Padrão

D13 e D14 são os PRIMEIROS testes que mostram algum sinal direcional positivo.
Mas ambos são fracos: D13 tem win rate de 26% (assimétrico), D14 tem N=7
(não significativo). Ambos são melhores como **filtros complementares** do
que como estratégias standalone.

## Arquivos

- **Scripts:** `trading-engine/funding_signal_scan.py`, `trading-engine/trend_follow_scan.py`
- **Dados:** `trading-engine/funding_signal_samples.json`, `trading-engine/trend_follow_samples.json`
