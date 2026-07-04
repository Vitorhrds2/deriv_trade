# D37-D41 — Hipóteses Agressivas (Jul 2026)

## D37 — Exchange Outflow Signal (on-chain alpha)

**Tese:** Saídas grandes de BTC/ETH de exchanges = holders movendo para cold storage
= redução de supply vendável = bullish. Detectar outflows em tempo real → comprar
antes do mercado precificar.

**Status:** SCAN FUNCIONANDO — Whale Alert API key configurada
- Whale Alert: autenticado com sucesso (API key do .env)
- 0 outflows > $1M detectados na última 1h (mercado calmo, não há whale movements)
- Blockchain.com: unconfirmed txs API não retornou dados (fallback)
- Preço BTC: $63,302

**Resultado:** API funcional. Necessário rodar continuamente por dias para capturar
outflows grandes e correlacionar com movimento de preço.

**Próximo:** Deploy na AWS em loop contínuo. Quando detectar outflow > $5M →
registrar preço BTC e trackear 1h/4h/24h após.

---

## D38 — Binance Announcement Front-Run

**Tese:** Binance posts anúncios (listings, delistings) em sua página de suporte.
Se detectarmos em segundos via polling a cada 3s, podemos comprar o token listado
antes do pump.

**Status:** SCAN FUNCIONANDO — 80 anúncios baseline, polling a cada 3s
- API: `cms/article/list/query` retorna `data.catalogs[].articles[]`
- Catalogs detectados: New Cryptocurrency Listing, Delisting, Maintenance, etc.
- 0 novos anúncios em 60s (esperado — Binance posta ~3-10/dia)

**Resultado inicial:** Scanner funcional. Necessário rodar por horas/dias para
capturar um listing event em tempo real e medir tempo de reação vs movimento de preço.

**Próximo:** Deploy na AWS em loop contínuo. Quando detectar "Will List" →
imediatamente comprar token na Binance Spot e trackear preço por 60s.

---

## D39 — Options Max Pain Magnet (Deribit)

**Tese:** No expiry day, preço do underlying gravita toward max pain strike
(preço onde máximo de opções expira worthless, beneficiando MMs).

**Status:** SCAN FUNCIONANDO — dados em tempo real do Deribit

**Resultado inicial:**

### BTC
| Expiry | Days | Max Pain | Spot | Diff% |
|--------|------|----------|------|-------|
| 10JUL26 | 5.5 | $61,000 | $63,447 | +3.86% |
| 17JUL26 | 12.5 | $60,000 | $63,447 | +5.43% |
| 31JUL26 | 26.5 | $64,000 | $63,447 | -0.87% |

### ETH
| Expiry | Days | Max Pain | Spot | Diff% |
|--------|------|----------|------|-------|
| 10JUL26 | 5.5 | $1,700 | $1,788 | +4.90% |
| 31JUL26 | 26.5 | $1,800 | $1,788 | -0.69% |

**Análise:** Max pain para 10JUL26 (próximo expiry, 5.5d) está ~4% abaixo do spot
para ambos BTC e ETH. Se magnet effect funcionar, preço deve cair toward max pain
nos próximos 5 dias. Sinal: SHORT BTC/ETH toward max pain.

**Próximo:** Trackear preço até 10JUL26 expiry (8:00 UTC). Se preço convergir
para max pain, edge = ~4% - 0.1% fees = ~3.9% net.

---

## D40 — Stablecoin Mint Signal (capital inflow)

**Tese:** Mints grandes de USDT/USDC = capital novo entrando no ecossistema →
pressão compradora → BTC price up.

**Status:** SCAN FUNCIONANDO — DefiLlama + Etherscan V2 API

**Resultado inicial:**
- Supply total stablecoins: ~$309.5B
- 3-day change: **-$337M (REDEMPTION, não mint)**
- Daily avg: -$112M/d
- Etherscan V2: 14 large USDT transfers encontrados (>$1M)
  - $100M transfer from Tether treasury (2026-07-03)
  - $40M transfer from Tether treasury (2026-07-03)
- Sinal: NEUTRAL/BEARISH (stablecoins sendo redeemidas, não mintadas)

**Análise:** Mercado está em regime de contração de stablecoins (redeemptions > mints).
Isso é bearish para crypto — capital saindo do ecossistema, não entrando.

**Próximo:** Monitorar daily. Quando 3d change > +$500M → LONG BTC.
Etherscan V2 funcional para real-time mint detection.

---

## D41 — Binance WS Trade Duplication / Wash Trading Detector

**Tese:** Padrões anômalos no trade stream (duplicações, clusters, volume bursts)
revelam operações coordenadas ou wash trading. Seguir o flow dos "smart money".

**Status:** SCAN FUNCIONANDO — WebSocket em tempo real (thresholds ajustados)

**Resultado inicial (120s, 2,388 trades, thresholds ajustados):**

| Anomalia | Count | % trades |
|----------|-------|----------|
| Trade clusters | 9 | 0.38% |
| Volume bursts | 7 | 0.29% |
| Dup trade IDs | 0 | 0% |

### Per-symbol
| Symbol | Trades | Buy/Sell ratio | Buy Vol / Sell Vol |
|--------|--------|----------------|---------------------|
| BTCUSDT | 1,451 | 4.62 | 4.09 |
| ETHUSDT | 630 | 1.92 | 0.48 |
| SOLUSDT | 307 | 2.07 | 2.45 |

**Análise:**
- **0 duplicate trade IDs** — Binance não está duplicando trades (não há wash trading óbvio)
- **9 trade clusters** (5+ trades idênticos em <100ms, com cooldown 500ms) — provável
  algoritmo de execução de ordens grandes (TWAP/VWAP). Clusters em ambos BUY e SELL.
- **7 volume bursts** (10x avg em 30s, com cooldown) — bursts reais de atividade
- **Buy/Sell ratio fortemente inclinado para BUY** em BTC (4.6:1) e SOL (2:1)
- ETH tem sell volume dominante (24.7 vs 11.7) apesar de mais buy trades

**Próximo:**
1. Correlacionar clusters com movimento de preço subsequente (30s, 60s, 5min)
2. Deploy na AWS por 24h+ para capturar padrões raros
3. Classificar clusters por direção e tamanho para identificar "smart money" flow

---

## Resumo D37-D41

| # | Hipótese | Status | Achado inicial |
|---|----------|--------|----------------|
| D37 | Exchange Outflow | Funcionando (API key) | 0 outflows na última 1h (mercado calmo) |
| D38 | Announcement Front-Run | Funcionando | 0 anúncios em 120s (esperado, ~3-10/dia) |
| D39 | Max Pain Magnet | Funcionando | Max pain 4% abaixo spot (SHORT signal 10JUL26) |
| D40 | Stablecoin Mint | Funcionando (Etherscan V2) | -$337M 3d (redemption). $100M USDT treasury transfer detectado |
| D41 | Wash Trading Detector | Funcionando (thresholds ajustados) | 9 clusters, 7 vol bursts, 0 dup IDs, BTC buy 4.6:1 |
