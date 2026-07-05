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

---

## D42 — Deriv vs Binance Cross-Venue Latency Arbitrage

> ⚠️ **REFUTADO em 2026-07-05** com N=6.830 (13h AWS) — ver seção "UPDATE 2026-07-05" no final deste documento. O achado abaixo é o teste inicial de 60s, mantido só para histórico.

**Tese:** Deriv's crypto price feed (cryBTCUSD) lags Binance's real-time price.
If lag > 100ms, we can trade on Deriv knowing where price already moved on Binance.

**Método:**
- Stream Binance WS trades + Deriv WS ticks simultaneously
- Cross-correlate price movements at varying time offsets (0-1000ms, 50ms steps)
- If consistent lag > 100ms → executable edge (buy/sell on Deriv before it catches up)

**Resultado inicial (60s scan):**
- Binance: 1,367 trades | Deriv: 63 ticks
- **Average lag: 164ms** (oscillates 0-300ms)
- Deriv updates ~1 tick/s vs Binance ~20 trades/s
- Lag is real but variable — sometimes 0ms, sometimes 300ms
- **Veredito preliminar:** Lag detectado, mas variabilidade alta. Necessário medir consistência do lag em janelas de 1h+ para determinar se é explorável na prática (execução Deriv precisa ser < 164ms)

**Deploy:** Rodando continuamente na AWS (tmux: d42_latency)

---

## D43 — Binance Order Book Imbalance Predictor ⚡ EDGE DETECTED

> ⚠️ **REFUTADO em 2026-07-05** — auto-concluído com N=24.994 (9.3h AWS), accuracy caiu 75.4%→58.8%. Ver seção "UPDATE 2026-07-05" no final deste documento. O achado abaixo é o teste inicial de 120s (N=98), mantido só para histórico.

**Tese:** When bid volume >> ask volume (or vice versa) in the top 20 order book levels,
price moves in the direction of the imbalance within 30s.

**Método:**
- Stream Binance depth20@100ms for BTC/ETH/SOL
- Compute bid/ask volume ratio every 100ms
- When imbalance > 70% → predict direction (UP if bid heavy, DOWN if ask heavy)
- Track prediction accuracy at 1s, 5s, 10s, 30s horizons

**Resultado inicial (120s scan, 98 predictions):**
- **1s: 22.4% accuracy** (noise — too fast for order book to matter)
- **5s: 54.3%** (marginal)
- **10s: 71.9%** ⚡ **EDGE**
- **30s: 75.4%** ⚡ **EDGE**

**Veredito:** ***EDGE DETECTADO*** — Order book imbalance > 70% prediz direção do preço com 75.4% de acurácia em 30s. Isso é diretamente negociável:
1. Detectar imbalance > 70% bid → BUY
2. Detectar imbalance > 70% ask → SELL
3. Close após 30s
4. Expected win rate: ~75%

**Próximo passo:** Validar com N=500+ em monitoramento contínuo. Se mantiver > 65%, implementar bot de execução real.

**Deploy:** Rodando continuamente na AWS (tmux: d43_orderbook)

---

## D44 — Binance Funding Rate + Basis Arbitrage

**Tese:** When perpetual futures funding rate is extreme, basis reverts.
Short futures + long spot when funding > 0.05%/8h (delta neutral, collect funding).

**Método:**
- Poll funding rates for 20 perpetuals every 5 min
- When funding > 0.05%/8h → SHORT futures signal
- When funding < -0.03%/8h → LONG futures signal
- Track basis reversion

**Resultado inicial:**
- 20 symbols scanned
- 0 signals — all funding rates within normal range
- Mercado estável, sem extremos de funding

**Veredito:** Aguardando condições extremas. Funding rates extremos ocorrem durante eventos de alta volatilidade (liquidation cascades, news events). Monitoramento contínuo necessário.

**Deploy:** Rodando continuamente na AWS (tmux: d44_funding, polling 5min)

---

## D45 — Binance Liquidation Cascade Predictor

> ⚠️ **RETIRADO em 2026-07-05** — redundante com D34 (`liquidation_cascade_scan.py`), que já rodava com design mais rigoroso. Ver seção "UPDATE 2026-07-05" no final deste documento. Não usar este script novamente, usar D34.

**Tese:** When 3+ liquidations occur in 10s on the same side, a cascade forms
that amplifies the price move. Joining the cascade direction for 30-60s captures
the forced flow.

**Método:**
- Stream Binance futures markPrice + forceOrder (liquidation) WS
- When 3+ liquidations in 10s same direction → cascade detected
- Track price 10s, 30s, 60s after cascade start
- If price continues in cascade direction > 65% → executable

**Resultado inicial (120s):**
- 0 liquidations detected (mercado calmo)
- Liquidation cascades are rare events (need hours/days)

**Veredito:** Aguardando eventos. Cascades ocorrem durante:
- Flash crashes (5+ std dev moves)
- High leverage flushouts
- News events with extreme sentiment

**Deploy:** Rodando continuamente na AWS (tmux: d45_liq)

---

## D46 — Deriv Tick Pattern Exploitation ⚡ EDGE DETECTED

> ⚠️ **DADOS PERDIDOS em 2026-07-05** (crash sem checkpoint) — corrigido e restartado do zero. Achado abaixo (N=542/300) ainda não confirmado em amostra maior. Ver seção "UPDATE 2026-07-05" no final deste documento.

**Tese:** Deriv's synthetic price feed may have exploitable patterns at the tick level.
Duplicate ticks (==) followed by a directional tick (U or D) may predict reversion.

**Método:**
- Stream 10 Deriv synthetic symbols (R_10-100, 1HZ10V-100V) via WS
- Record every tick with timestamp
- Track 3-tick sequential patterns (e.g., ==D, ==U, UUD, DDU)
- For each pattern, measure next-tick direction accuracy
- If any pattern > 55% → executable 1-tick trade

**Resultado inicial (120s, 880 ticks across 10 symbols):**
- **Pattern '==D' → UP: 55.4% accuracy (N=542)** ⚡
- **Pattern '==U' → DOWN: 56.7% accuracy (N=300)** ⚡
- 146 timing gaps > 2s detected (avg 2054ms — Deriv's ~2s tick interval for 2s symbols)
- 0 duplicate sequences of 3+ identical ticks

**Interpretation:** When 2 identical ticks are followed by a directional tick,
the NEXT tick tends to REVERT (opposite direction). This is a mean-reversion
pattern in Deriv's synthetic feed:
- ==D (flat-flat-down) → next tick UP 55.4% of the time
- ==U (flat-flat-up) → next tick DOWN 56.7% of the time

**Veredito:** ***EDGE PRELIMINAR*** — Mean reversion pattern detectado nos ticks sintéticos da Deriv. N=542 e N=300 são amostras razoáveis mas precisam de validação com N=5000+ para confirmação estatística (Wilson CI).

**Próximo passo:** Rodar continuamente por 24h+ para acumular N=5000+. Se padrão mantiver > 55%, implementar execução: 1-tick CALL/PUT trade após detectar padrão ==D ou ==U.

**Deploy:** Rodando continuamente na AWS (tmux: d46_pattern)

---

## Resumo D42-D46 (achados iniciais, 60-120s local — ver UPDATE abaixo para dados reais de 13h)

| # | Hipótese | Status inicial | Achado inicial |
|---|----------|--------|----------------|
| D42 | Latency Arb (Deriv vs Binance) | Lag detectado | 164ms avg lag (0-300ms variável). Necessário medir consistência |
| D43 | Order Book Imbalance | ⚡ EDGE DETECTADO | 75.4% accuracy em 30s (N=98). Diretamente negociável |
| D44 | Funding Rate Arb | Aguardando | 0 sinais (mercado estável). Monitorando 20 perps |
| D45 | Liquidation Cascade | Aguardando | 0 cascades em 120s. Eventos raros, precisa dias |
| D46 | Deriv Tick Patterns | ⚡ EDGE PRELIMINAR | ==D→UP 55.4% (N=542), ==U→DOWN 56.7% (N=300). Mean reversion |

---

## UPDATE 2026-07-05 — Auditoria pós-incidente AWS (dados reais de 13h)

**Contexto:** A instância AWS ficou inacessível por ~5h (09:26-15:46 UTC) por pressão de
memória (t3.micro, 911MB RAM, sem swap, ~20 processos concorrentes). Antes de religar
qualquer bot, foi feita uma auditoria completa dos logs acumulados (13h de dados reais,
muito maior que os scans locais de 60-120s acima) e uma checagem cruzada contra o resto
do `state_of_research.md` para achar hipóteses já testadas de forma mais rigorosa.
Ver detalhes completos em `docs/state_of_research.md` item 26 (nota do incidente).

### D42 — REFUTADO (era "lag detectado")

Com N=6.830 amostras (13h), o lag médio do FEED se confirma em ~204.5ms (max 950ms) —
maior amostra, mesma conclusão qualitativa do teste local. **MAS** esta pergunta específica
(lag do feed Deriv vs Binance) já tinha sido respondida de forma **muito mais rigorosa** por
`docs/h3_latency_arb_report.md`: H3 mediu o MESMO lag de feed (~0.51 corr em +400ms) só que
foi além — testou a **execução real** (60 + 41 ordens demo, incluindo VM co-localizada em
Tóquio) e descobriu que o fill da Deriv **sempre reprecifica fresco**, tornando o lag do feed
inexplorável. Custo ~489x a captura, mesmo co-locado. D42 mede só o "Passo 1" de H3 (feed),
nunca chegou ao "Passo 3" (fill real), que é o teste decisivo. **Não restartado.**

### D43 — REFUTADO (era "⚡ EDGE DETECTADO")

O processo rodou 33.487s (9.3h) sem supervisão e **concluiu sozinho** (WS caiu naturalmente,
o script não tinha reconexão automática em modo `--continuous` — bug notado, sem impacto aqui
porque o resultado final já é conclusivo). Com N=24.994 predictions e 756 resolvidas:
accuracy em 30s **caiu de 75.4% (N=98) para 58.8% (N=756)** — abaixo do próprio threshold de
60% que eu tinha definido como "edge". Isso é clássica regressão à média de false-positive de
amostra pequena. Além disso, `docs/order_book_imbalance_report.md` (D33) já tinha testado
exatamente esta tese com N=2.400+ e fees incluídos: WR direcional real de até 62.5% em 10s,
mas **0% dos trades lucrativos após taker fee de 0.1%/lado** — o movimento de preço em 10-30s
é menor que o custo de transação. D43 nunca contabilizou fees; se tivesse, o resultado teria
sido o mesmo 0% lucrativo do D33. **Não restartado.**

### D44 — Sem mudança de veredito (aguardando evento extremo)

113 ciclos completos em 13h (a cada 5min). Único sinal persistente: ATOMUSDT LONG_FUT com
funding ~-0.03%/8h, bem na borda do threshold, magnitude pequena. Nenhum extremo real
observado. **Restartado** — é barato (polling REST leve) e a pergunta central (o que acontece
quando funding é REALMENTE extremo) ainda não foi testada.

### D45 — RETIRADO (redundante com D34)

Durante a auditoria, descobri que esta hipótese (3+ liquidações/10s = cascade) já existia
como **D34** (`liquidation_cascade_scan.py`, tmux `liq_bot`), rodando continuamente desde
antes desta sessão, com design **mais rigoroso**: 4 hold periods testados (30/60/120/300s)
e P&L já ajustado por fee (0.1%/lado). D34 confirma 0 cascades em todos os ciclos ao longo
de dias de dados — mesmo resultado do D45 (0 em 120s), só que com muito mais tempo de
observação. Rodar os dois em paralelo desperdiça recursos (críticos agora, ver incidente).
**D45 não restartado — D34 é a fonte única desta tese daqui em diante.**

### D46 — Dados perdidos, restart com fix (era "⚡ EDGE PRELIMINAR")

O script rodou ~8h na AWS mas **nunca escreveu nenhum checkpoint** — o design original só
salva o JSON de resultado DEPOIS que `ws.run_forever()` retorna (ou seja, só numa desconexão
"limpa"). Como o processo morreu abruptamente no crash de memória, **todo o progresso
acumulado em 8h foi perdido**; o log na AWS só tinha os mesmos N=542/300 do teste local
inicial de 120s. **Corrigido:** adicionado `save_checkpoint()` chamado a cada 500 ticks, para
que crashes futuros percam no máximo alguns minutos de dados, não 8h. Restartado do zero com
o fix — ainda preliminar, precisa N=5000+ (≈24h+) para validação Wilson CI. Esta é a única das
5 hipóteses agressivas que **não colide** com nenhuma pesquisa anterior (o mecanismo de
"dígitos" já testado é sobre o último dígito do preço, não sobre sequências de 3 ticks) —
continua sendo uma pista genuinamente nova e vale manter rodando.

### Achado bônus não relacionado a D42-46: Early Sell Optionality FECHOU

Durante a mesma auditoria, encontrei que `early_sell_test.py` (hipótese separada, rodando na
AWS desde antes desta sessão) **completou seus 50 trials programados** exatamente durante a
janela do incidente. Resultado: **EDGE CONFIRMADO**. Sell (vender no melhor bid) WR 86%
(IC95%[73.8%,93.1%]) vs Hold WR 52% (IC95%[38.5%,65.2%]); diferença de EV = +$5.23/trade,
IC95%[+$3.22,+$7.17] não cruza zero. Confirmado por regra non-hindsight (vender no 1º bid≥
threshold) em todos os 8 thresholds testados. Ver `docs/state_of_research.md` item 14 e
`hypotheses-data.ts` (HYP-SELL-01, agora `status: live`).

### Fix de infraestrutura

Adicionado swapfile de 2GB (`/swapfile`, persistente via `/etc/fstab`) para dar margem de
segurança contra pressão de memória futura. Supervisor (`aggressive_monitor_supervisor.sh`)
atualizado para NÃO religar D42/D43/D45 automaticamente.
