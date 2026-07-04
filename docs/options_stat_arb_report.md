# D11 & D12 — Options IV Mispricing + Statistical Arbitrage Report (2026-07-03)

## D11 — Options IV Mispricing Scan (Deribit)

### Hipótese
Se IV (implied volatility) nas opções Deribit é sistematicamente mispriced
vs RV (realized volatility), há edge em vender vol overpriced ou comprar vol underpriced.

### Metodologia
- **Script:** `trading-engine/options_iv_scan.py`
- **API:** Deribit public (sem API key)
- **Dados:** DVOL (volatility index), historical RV, ATM IV por expiry, book summary
- **Ativos:** BTC, ETH

### Resultados

| Métrica | BTC | ETH |
|---------|-----|-----|
| Spot | $62,153 | $1,736 |
| RV 30d | 48.7% | 63.9% |
| IV (DVOL) | 40.5% | 55.1% |
| **Vol Risk Premium** | **-8.2%** | **-8.8%** |
| Term structure | Contango (+9.3%) | Contango (+9.6%) |
| Skew (ATM) | 0.0% | 0.0% |

### Achado central: VRP negativo

IV está **abaixo** de RV para ambos BTC e ETH. Isso significa:
- Opções estão **underpriced** relativo à vol realizada
- **Comprar vol** (long options) teoricamente lucrativo
- **MAS:** long vol = theta decay (tempo trabalha contra você)
- O VRP negativo é consistente com literatura acadêmica que mostra que
  em crypto, o prêmio de vol é frequentemente negativo (especuladores
  vendem vol barato, demandando proteção é caro)

### Term structure
- Contango: near IV (27.6% BTC, 40.2% ETH) < far IV (36.9% BTC, 49.8% ETH)
- Mercado espera aumento de vol — normal em períodos calmos
- Não há edge óbvio em calendar spreads (a curva já precifica o aumento)

### Skew
- ATM put-call skew = 0.0% para ambos — esperado para European options
- Para medir skew real seria necessário comparar OTM puts vs OTM calls
- Não há sinal de crash hedging (skew não está elevado)

### Profitabilidade

**Problema 1: Theta decay**
- Comprar opções = pagar premium que decai com o tempo
- Mesmo que IV < RV, se a vol realizada não se materializar no prazo certo,
  o theta come o premium
- VRP negativo não é edge direcional — é uma constatação estatística

**Problema 2: Delta hedging**
- Para capturar VRP puro (sem directional bias), é necessário delta hedge
- Cada rebalance = fees + slippage
- Delta hedge diário em BTC: ~$20-50/dia em fees (0.03% × $62k × 2 legs)
- Over 30 days: $600-1500 em fees de hedge alone

**Problema 3: Bid-ask spreads**
- Spreads de 5-15% do premium da opção
- Em opções ATM de 1 dia: premium ~$200 BTC, spread ~$10-30
- Entrar + sair = 2 × spread = $20-60 só em spread

**Problema 4: Tail risk**
- Se vender vol (short options) e VRP for negativo, perde duplamente
- Se comprar vol (long options) e vol não aumentar, perde theta
- Não há direção "segura" — ambos os lados têm riscos assimétricos

### Conclusão D11

**VRP negativo é uma anomalia interessante, mas não é um edge simples.**
- IV < RV sugere que comprar vol é teoricamente correto
- Mas theta decay + delta hedging costs + bid-ask spreads consomem o edge
- Para capturar VRP seria necessário: delta hedge frequente + gerenciar theta
- Isso é uma estratégia de vol trading profissional, não um script Python
- **Sem edge explorável sem infraestrutura de delta hedging ativo**

---

## D12 — Statistical Arbitrage (Crypto Pairs Trading)

### Hipótese
Se dois criptoativos são cointegrados (spread mean-reverte), pairs trading
pode lucrar com divergências temporais.

### Metodologia
- **Script:** `trading-engine/stat_arb_scan.py`
- **API:** Binance public (sem API key)
- **Dados:** 500 candles diários, 20 ativos (top USDT pairs)
- **Teste:** Engle-Granger cointegration + ADF + half-life
- **Backtest:** Walk-forward 70/30, z-score entry/exit, 40bps fees per round trip

### Resultados

| Métrica | Valor |
|---------|-------|
| Símbolos analisados | 20 |
| Pares testados | 190 |
| Pares cointegrados (p<0.01) | 76 (40%) |
| Pares backtested (top 10) | 10 |
| Pares lucrativos (OOS) | 3/10 (30%) |
| PnL médio | -278 bps |
| Sharpe médio | -0.26 |
| Win rate médio | 63% |

### Backtest out-of-sample (top 10 pares cointegrados)

| Pair | Trades | WR | PnL (bps) | Sharpe | MaxDD (bps) | Avg Hold |
|------|--------|----|-----------|--------|-------------|----------|
| ADA/ARB | 16 | 56% | -714 | -0.64 | 2,168 | 7.9d |
| XRP/LTC | 20 | 65% | -721 | -0.83 | 1,324 | 4.6d |
| ADA/AVAX | 12 | 50% | +178 | 0.21 | 1,278 | 11.9d |
| ADA/DOT | 16 | 62% | -826 | -0.96 | 1,115 | 7.6d |
| AVAX/DOGE | 14 | 57% | -470 | -0.74 | 724 | 7.6d |
| DOGE/LTC | 14 | 71% | +773 | 1.10 | 658 | 7.2d |
| ADA/SUI | 13 | 69% | +1,417 | 1.69 | 762 | 9.7d |
| XRP/DOGE | 12 | 67% | -42 | -0.07 | 685 | 7.8d |
| ADA/ATOM | 13 | 62% | -1,164 | -1.20 | 1,445 | 11.5d |
| SOL/DOGE | 15 | 67% | -1,212 | -1.10 | 1,675 | 8.3d |

### Análise

**Cointegração é necessária mas não suficiente:**
- 40% dos pares são cointegrados — cripto é altamente correlacionado
- Mas 70% dos pares backtested perderam dinheiro after fees
- Win rate de 63% é enganosa: ganhos médios < perdas médias + fees

**Custo de fees é determinante:**
- 40 bps por round trip × ~15 trades = 600 bps em fees alone
- Melhor par (ADA/SUI): +1,417 bps bruto, mas ~600 bps em fees = ~817 bps net
- Esse ~817 bps em ~150 dias = ~5.4% annualizado — marginal

**Risco de quebra de cointegração:**
- Cointegração em cripto quebra frequentemente (novos listings, regulatory, hacks)
- Exemplo histórico: LUNA/UST era cointegrado antes de colapsar em Mai 2022
- Half-life médio: 6-45 dias — relativamente rápido, mas pode quebrar

**Por que win rate alto mas PnL negativo:**
- A estratégia ganha pequeno quando o spread reverte (exit at z=0.5)
- Mas perde grande quando o spread diverge além do stop (z=4.0)
- Stop loss em z=4.0 = ~4 desvios padrão = perda grande
- Assimetria: muitos ganhos pequenos, poucas perdas grandes

### Conclusão D12

**Cointegração existe em cripto, mas o edge é insuficiente após fees.**
- 76/190 pares cointegrados mostra que cripto é altamente correlacionado
- Mas 70% dos backtests OOS são negativos após 40bps fees
- Melhor par: ADA/SUI +1,417 bps (~5.4% annualizado) — marginal
- Risco de quebra de cointegração = perda potencial grande
- **Sem edge explorável após custos para um bot retail**

---

## Comparação Geral D7-D12

| Hipótese | Mecanismo | N | Resultado | Veredito |
|----------|-----------|---|-----------|----------|
| D7 | CEX-CEX arb | 100 | 0/100 positivos | SEM EDGE |
| D8 | Triangular Binance | 120 | 0/120 positivos | SEM EDGE |
| D9 | Funding carry | 19 perps | 0% janelas 7d | SEM EDGE |
| D10 | DeFi liquidations | 108 events | <1% capture rate | SEM EDGE (retail) |
| D11 | Options IV mispricing | BTC+ETH | VRP=-8% mas theta+hedging costs | SEM EDGE (simples) |
| D12 | Stat arb pairs | 10 pairs OOS | 70% negativos após fees | SEM EDGE |

## Padrão Universal

29 hipóteses testadas. Em todas, o sinal existe mas é **menor que os custos**
(fees, spread, slippage, theta, competição MEV, infraestrutura). O mercado
crypto é notavelmente eficiente para um participante retail.

## Arquivos

- **Scripts:** `trading-engine/options_iv_scan.py`, `trading-engine/stat_arb_scan.py`
- **Dados:** `trading-engine/options_iv_samples.json`, `trading-engine/stat_arb_samples.json`
