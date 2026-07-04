# D37-D41 — Hipóteses Agressivas (Jul 2026)

## D37 — Exchange Outflow Signal (on-chain alpha)

**Tese:** Saídas grandes de BTC/ETH de exchanges = holders movendo para cold storage
= redução de supply vendável = bullish. Detectar outflows em tempo real → comprar
antes do mercado precificar.

**Status:** SCAN INICIAL — APIs free tier limitadas
- Whale Alert: requer API key (401 unauthorized com demo)
- Blockchain.com: unconfirmed txs API não retornou dados
- Glassnode: requer API key

**Resultado inicial:** Sem dados em tempo real. Necessário API key do Whale Alert
ou Glassnode para validar a hipótese. Preço BTC: $63,218.

**Próximo:** Obter API key do Whale Alert (free tier: 10 calls/min) e rodar
continuamente por 7d, tracking preço após outflows > $5M.

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

**Status:** SCAN FUNCIONANDO — DefiLlama supply data

**Resultado inicial:**
- Supply total stablecoins: ~$309.5B
- 3-day change: **-$337M (REDEMPTION, não mint)**
- Daily avg: -$112M/d
- Sinal: NEUTRAL/BEARISH (stablecoins sendo redeemidas, não mintadas)

**Análise:** Mercado está em regime de contração de stablecoins (redeemptions > mints).
Isso é bearish para crypto — capital saindo do ecossistema, não entrando.

**Próximo:** Monitorar daily. Quando 3d change > +$500M → LONG BTC.
Para real-time, necessário Etherscan API key para monitorar Transfer events
do contrato USDT em tempo real.

---

## D41 — Binance WS Trade Duplication / Wash Trading Detector

**Tese:** Padrões anômalos no trade stream (duplicações, clusters, volume bursts)
revelam operações coordenadas ou wash trading. Seguir o flow dos "smart money".

**Status:** SCAN FUNCIONANDO — WebSocket em tempo real

**Resultado inicial (120s, 5,235 trades):**

| Anomalia | Count | % trades |
|----------|-------|----------|
| Trade clusters | 150 | 2.87% |
| Volume bursts | 4,514 | 86.2% |
| Dup trade IDs | 0 | 0% |

### Per-symbol
| Symbol | Trades | Buy/Sell ratio | Buy Vol / Sell Vol |
|--------|--------|----------------|---------------------|
| BTCUSDT | 3,687 | 1.26 | 1.26 |
| ETHUSDT | 1,076 | 1.33 | 1.95 |
| SOLUSDT | 472 | 2.13 | 4.05 |

**Análise:**
- **0 duplicate trade IDs** — Binance não está duplicando trades (não há wash trading óbvio)
- **150 trade clusters** (5+ trades idênticos em <100ms) — provável algoritmo de execução
  de ordens grandes (TWAP/VWAP) dividindo em múltiplas sub-ordens
- **Volume bursts** muito sensíveis (threshold 5x avg em 10s) — precisa ajustar threshold
- **Buy/Sell ratio inclinado para BUY** em todos os 3 símbolos, especialmente SOL (2:1)

**Próximo:**
1. Ajustar volume burst threshold (86% é falso positivo — threshold muito baixo)
2. Investigar clusters: são MMs executando TWAP? Seguir direção dos clusters
3. Deploy na AWS por 24h+ para capturar padrões raros
4. Correlacionar clusters com movimento de preço subsequente

---

## Resumo D37-D41

| # | Hipótese | Status | Achado inicial |
|---|----------|--------|----------------|
| D37 | Exchange Outflow | Limitado (API key) | Sem dados em tempo real |
| D38 | Announcement Front-Run | Funcionando | 0 anúncios em 60s (esperado) |
| D39 | Max Pain Magnet | Funcionando | Max pain 4% abaixo spot (SHORT signal) |
| D40 | Stablecoin Mint | Funcionando | -$337M 3d (redemption, bearish) |
| D41 | Wash Trading Detector | Funcionando | 150 clusters, 0 dup IDs, buy pressure |
