# D7+D8+D9 — CEX Arbitrage & Funding Rate Carry Report (2026-07-03)

**Veredito D7: SEM EDGE.** CEX-CEX spread é 0-4 bps, fees são 20 bps/side. 0/100 lucrativo.
**Veredito D8: SEM EDGE.** Triangular arb na Binance é -10 bps gross médio. 0/120 lucrativo.
**Veredito D9: SEM EDGE.** Funding rate carry parece lucrativo em scan superficial (14/20), mas validação
rigorosa com 30 dias completos refuta: apenas 4/19 lucrativos e 0% das janelas de 7 dias são positivas.

## D7 — Cross-Exchange Arbitrage (Binance vs Bybit vs OKX)

### Hipótese
Se o mesmo par (ex: BTC/USDT) tem bid em uma exchange > ask em outra (após fees), há arb
cross-exchange.

### Metodologia
- **Script:** `trading-engine/cex_arb_scan.py`
- **Exchanges:** Binance, Bybit, OKX (REST APIs públicas, sem auth)
- **Pares:** BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK vs USDT
- **Dados:** Best bid/ask (bookTicker) de cada exchange simultaneamente
- **Fees:** 10 bps taker por lado (0.10%), 20 bps total ida+volta
- **Período:** 10 minutos, 20 ciclos, intervalo 15s (2026-07-03 14:07-14:17 UTC)

### Resultados

| Métrica | Valor |
|---------|-------|
| Observações | 100 |
| Gross spread médio | 0.0 bps |
| Gross spread máximo | 3.9 bps |
| Gross spread mínimo | -5.9 bps |
| Net spread médio | -20.0 bps |
| Net spread máximo | -16.1 bps |
| **Positivos (net)** | **0/100** |

### Análise
As três exchanges (Binance, Bybit, OKX) têm preços quase idênticos para os mesmos pares.
O spread bruto médio é **0.0 bps** — quando uma exchange tem ask ligeiramente mais baixo,
a mesma exchange tende a ter bid ligeiramente mais baixo também, eliminando qualquer
oportunidade. O spread máximo encontrado foi 3.9 bps, contra 20 bps de fees. Para ser
lucrativo, precisaríamos de spread > 20 bps, que nunca ocorreu.

**Comparação com D5 (Solana DEX vs Binance):** O gap CEX-DEX era ~9 bps. O gap CEX-CEX
é ~0-4 bps. Isto faz sentido: CEXs têm market makers profissionais fazendo arbitragem
cross-exchange em tempo real, comprimendo o spread a zero.

## D8 — Triangular Arbitrage (Binance)

### Hipótese
Se BTC→ETH→USDT→BTC roundtrip retorna > 1.0 (após fees), há triangular arb.

### Metodologia
- **Script:** `trading-engine/cex_arb_scan.py` (mesmo script que D7)
- **Exchange:** Binance apenas (mais líquida)
- **Caminhos:** 6 paths triangulares (BTC↔ETH↔USDT, BTC↔SOL↔USDT, ETH↔SOL↔USDT,
  BTC↔XRP↔USDT, ETH↔XRP↔USDT, BTC↔DOGE↔USDT)
- **Fees:** 10 bps taker por leg, 30 bps total (3 legs)
- **Período:** 20 ciclos, 120 observações

### Resultados

| Métrica | Valor |
|---------|-------|
| Observações | 120 |
| Gross roundtrip médio | -10.1 bps |
| Gross roundtrip máximo | 2.0 bps |
| Gross roundtrip mínimo | -67.9 bps |
| Net roundtrip médio | -40.1 bps |
| Net roundtrip máximo | -28.0 bps |
| **Positivos (net)** | **0/120** |

### Análiise
O triangular arb na Binance é consistentemente **negativo** mesmo antes das fees
(gross médio -10 bps). Isto é esperado: o spread bid-ask em cada leg consome qualquer
ineficiência. O melhor gross observado foi +2.0 bps (uma vez), contra 30 bps de fees.

O path BTC→DOGE→USDT→BTC teve o pior desempenho (-60 a -68 bps gross), provavelmente
porque DOGE tem spread bid-ask maior e o par BTC/DOGE é menos líquido.

**Comparação com D5 (Solana triangular):** Solana triangular tinha gross ~0 bps (máx +7.9).
Binance triangular tem gross -10 bps (máx +2.0). A Binance é mais eficiente que Solana DEX
neste aspecto, provavelmente porque tem mais volume e market making.

## D9 — Funding Rate Carry Trade

### Hipótese
Se funding rate de perpetual futures é persistentemente positivo (longs pagam shorts),
um carry trade delta-neutral (buy spot + short perp, collect funding a cada 8h) é lucrativo
após fees.

### Metodologia
- **Scripts:** `trading-engine/funding_rate_scan.py` (scan inicial) e
  `trading-engine/funding_rate_validate.py` (validação rigorosa)
- **Exchanges:** Binance, Bybit, OKX (REST APIs públicas)
- **Perpetuals:** 20 símbolos (BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK, BNB, DOT,
  MATIC, LTC, ATOM, NEAR, APT, ARB, OP, INJ, SUI, TIA)
- **Carry trade mechanics:**
  1. Buy spot (10 bps fee)
  2. Short perp (10 bps fee)
  3. Collect funding a cada 8h por N períodos
  4. Close both (20 bps fee)
  5. Total fees: 40 bps entry+exit
- **Custo de capital:** 5% APR T-bill (opportunity cost)
- **Validação:** 30 dias de histórico, 90 períodos de 8h (Binance) / 180-360 (OKX)

### Resultados — Scan Inicial (funding_rate_scan.py)

O scan inicial com OKX retornou apenas ~11 dias de histórico (274 registros horários),
mostrando **14/20 perps "lucrativos"**:

| Symbol | Net (bps/30d) | Avg Funding (bps/8h) | Persistence |
|--------|---------------|----------------------|-------------|
| NEARUSDT | +95.3 | 0.49 | 79% |
| SUIUSDT | +71.7 | 0.37 | 73% |
| DOGEUSDT | +65.3 | 0.38 | 75% |
| BNBUSDT | +61.2 | 0.37 | 72% |
| OPUSDT | +54.0 | 0.34 | 72% |

### Resultados — Validação Rigorosa (funding_rate_validate.py)

Com 30 dias completos de dados (90 períodos de 8h na Binance, 180-360 na OKX),
incluindo custo de capital (5% APR):

| Symbol | Exchange | N | Net (bps/30d) | Avg (bps) | Persistence | AutoCorr | Sharpe | 7d Win% |
|--------|----------|---|---------------|-----------|-------------|----------|--------|---------|
| DOGEUSDT | okx | 180 | +90.0 | 0.266 | 69% | 0.20 | 146.2 | **0%** |
| LTCUSDT | okx | 180 | +68.4 | 0.146 | 64% | 0.10 | 77.9 | **0%** |
| TIAUSDT | okx | 360 | +46.8 | 0.013 | 56% | 0.41 | 7.4 | **0%** |
| MATICUSDT | binance | 90 | +8.9 | 1.000 | 100% | 0.00 | 0.0 | **0%** |

**Apenas 4/19 perps têm net positivo em 30 dias** (vs 14/20 no scan superficial).

### Análise Crítica

1. **O sinal positivo inicial era viés de amostra curta.** O scan inicial usou apenas
   ~11 dias de dados OKX (274 registros horários = ~11 dias), capturando um período
   onde funding foi anormalmente positivo. Com 30 dias completos, a maioria dos símbolos
   fica negativa.

2. **0% das janelas de 7 dias são lucrativas.** Nenhum símbolo teve nenhuma janela
   contínua de 7 dias onde o carry trade seria lucrativo após fees + custo de capital.
   Isto significa que o trader precisaria manter a posição por semanas ou meses para
   ter chance de lucro, assumindo risco de base (spot vs perp price divergence) durante
   todo esse período.

3. **Funding rate é autocorrelacionado (lag-1).** 18/19 símbolos têm autocorrelação
   positiva (média ~0.3). Isto significa que funding alto tende a persistir — mas a
   persistência não é forte o suficiente para superar as fees de 40 bps.

4. **MATICUSDT tem persistence 100% e autocorr 0.0** — isto é suspeito. Provavelmente
   o funding rate está capped em 1.0 bps (0.01%) na Binance, e o histórico é todo
   igual. Não é um sinal real.

5. **Custos não contabilizados que pioram o quadro:**
   - **Basis risk:** Spot e perp podem divergir, causando perda na marcação ao mercado
   - **Slippage:** Entrada/saída com ordem market tem slippage além da fee
   - **Liquidation risk:** Se perp price sobe muito, o short pode ser liquidado
   - **Borrow cost:** Se precisar emprestar o spot (ou usar margin), há custo adicional

6. **DOGEUSDT "lucrativo" (+90 bps) é ilusório:** O Sharpe de 146 é alto porque a
   volatilidade do funding é muito baixa (funding quase sempre +1 bps), mas 0% das
   janelas de 7 dias são lucrativas. O lucro só aparece no agregado de 30 dias, e
   mesmo assim é < 1% em 30 dias — menos que T-bill.

### Conclusão D9

O funding rate carry trade é **teoricamente válido** (funding é persistente e positivo
em muitos perps), mas **não é lucrativo na prática** porque:
- Fees de entrada + saída (40 bps) consomem a maior parte do funding coletado
- Custo de capital (5% APR = ~42 bps/30d) consome o resto
- 0% das janelas de 7 dias são lucrativas
- Basis risk não contabilizado piora o quadro

O carry trade só seria viável com:
- Fees maker (2 bps/side = 8 bps total) em vez de taker (40 bps)
- Capital próprio (sem opportunity cost)
- Hold time de meses
- Tolerância a basis risk

Mesmo assim, o retorno seria ~1-3% ao mês não anualizado, sujeito a risco de
funding reversal. **Não é um edge explorável com capital retail.**

## Comparação Geral

| Hipótese | Mecanismo | N | Gross (bps) | Net (bps) | Positivos | Veredito |
|----------|-----------|---|-------------|-----------|-----------|----------|
| D5 | Solana DEX vs Binance | 199 | ~9 | ~-11 | 0/199 | SEM EDGE |
| D6 | EVM cross-agg | 160 | 0-450 | -1 a -3 | 0 real | SEM EDGE |
| **D7** | **CEX-CEX** | **100** | **0-4** | **-16 a -26** | **0/100** | **SEM EDGE** |
| **D8** | **Triangular Binance** | **120** | **-10** | **-28 a -98** | **0/120** | **SEM EDGE** |
| **D9** | **Funding carry** | **19 perps** | **+0 a +135** | **-162 a +90** | **4/19** | **SEM EDGE** |

## Arquivos

- **Scripts:** `trading-engine/cex_arb_scan.py`, `trading-engine/funding_rate_scan.py`,
  `trading-engine/funding_rate_validate.py`
- **Dados:** `trading-engine/cex_arb_samples.json`, `trading-engine/funding_rate_samples.json`,
  `trading-engine/funding_rate_validation.json`
- **Logs:** `trading-engine/cex_arb_scan.log`
