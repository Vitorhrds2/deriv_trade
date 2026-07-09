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

> ⚠️ **REFUTADO em 2026-07-06** com N=190.000 (o restart de 2026-07-05 rodou limpo por 7h e deu veredito conclusivo). Achado abaixo (N=542/300) era ruído de amostra pequena. Ver seção "UPDATE 2026-07-06" no final deste documento.

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

### D46 — Dados perdidos, restart com fix em 2026-07-05 (era "⚡ EDGE PRELIMINAR") — **ver desfecho final na seção UPDATE 2026-07-06 abaixo**

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

---

## UPDATE 2026-07-06 — Checagem de resultados 24h depois

**Contexto:** rotina de "checar processos AWS pra ver resultados de ontem pra hoje". Memória
estava crítica de novo (71MB disponíveis, swap em uso) por dois problemas novos encontrados
antes de conseguir ler os resultados com segurança.

### D46 — REFUTADO (era "⚡ EDGE PRELIMINAR")

O restart de 2026-07-05 rodou de forma limpa por ~7h (25.338s) até um WS drop às 05:38 de
2026-07-06, acumulando **N=190.000 ticks** de forma contínua antes de cair — amostra bem acima
do N=5000 que eu tinha estimado como suficiente. Resultado com a amostra grande:

- **Pattern `==D` → UP: 50.44%** (54.366/107.784) — z≈2.89 vs 50% (tecnicamente fora do ruído
  estatístico), mas **0.44 pontos percentuais** — ordens de magnitude abaixo de qualquer custo
  de transação em produtos Deriv (multiplier/digit sempre tem margem de casa de vários pontos
  percentuais).
- **Pattern `==U` → UP: 49.82%** (39.871/80.033) — z≈-1.02, nem estatisticamente diferente de
  50%.

Os 55.4%/56.7% de ontem (N=542/N=300) eram exatamente o tipo de falso positivo de amostra
pequena que este programa já catalogou várias vezes (Jump Indices N=14, D43 N=98 — mesma
história se repetindo). **Veredito: sem edge.** Bot parado (`tmux kill-session d46_pattern`) e
removido do supervisor — não restartar.

Antes de encerrar, corrigi também um bug real no script: modo `--continuous` não tinha loop de
reconexão (mesma classe de bug do D43/D42 — um WS drop mata o processo Python inteiro, e só o
supervisor externo percebe e recria a sessão do zero, perdendo os contadores). Corrigido no
código para referência futura, mesmo com o bot desligado.

### D41 — vazamento de memória encontrado e corrigido (sem mudança de veredito)

Durante a checagem de saúde da instância, achei que `wash_trading_scan.py` estava consumindo
344MB RSS (36.8% da RAM) após ~24h rodando, com CPU também anormalmente alta (39.6%). Causa
raiz: a lista `volume_timeline` (usada para detectar volume bursts) crescia sem nenhum limite
— diferente da lista `trades` do mesmo script, que já era corretamente limitada a 5000 entradas.
Como a lógica só precisa dos últimos 100 registros (média) e de uma janela de 30s (burst), o
fix foi limitar `volume_timeline` a 2000 entradas — mesmo padrão já usado pra `trades`. Isso
também corrige um `sum()` que rodava O(n) crescente a cada trade (explica a CPU alta). Processo
reiniciado; memória disponível da instância voltou de 71MB para ~400MB. Como o restart zera os
contadores internos (mesmo design do D46, sem persistência entre reconexões), o último ciclo
antes do fix (N=157.000 trades, timestamp_anomalies=24.2%) ficou registrado em
`docs/state_of_research.md` item 24 antes de ser perdido.

### Bug do supervisor: edição de arquivo não afeta processo já rodando

`unlock_status_api.py` (porta 8788, parado no dia anterior por ser código morto — todo tráfego
`/api/*` vai pra `status_api.py` na porta 8787 via `vercel.json`) **voltou sozinho**. Causa: o
supervisor (`aggressive_monitor_supervisor.sh`) já estava rodando havia horas com a lista de
sessões antiga carregada em memória (bash lê o array `SESSIONS` uma vez no início do script);
editar o arquivo no disco no dia anterior não teve efeito no processo bash já em execução, que
continuou recriando `unlock_api` sempre que a sessão desaparecia. Corrigido reiniciando a
própria sessão `aggressive_supervisor` para carregar a lista atualizada. **Lição: sempre
reiniciar o supervisor depois de editar seu script, nunca só editar o arquivo.**

### Achados de resultado (sem veredito fechado, mas dados novos relevantes)

- **D38** (announcement front-run): primeiros anúncios reais capturados — 3 no total, 1 deles
  LISTING (delist TST/IOTX, sentimento bullish) com price-reaction tracking em andamento.
- **D39** (max pain magnet): expiry 6JUL26 rolou pra 7JUL26 **sem convergência** — diff BTC
  spot-vs-max-pain foi de +2.00% pra +3.04% (divergiu) nas ~7h antes do rollover.
- **D36** (IV surface): paper bot ao vivo com 7 settles reais mostra WR=42.9%, bem abaixo do
  100% do backtest histórico, embora EV/trade continue positivo (+$137.52) com 115 posições
  ainda abertas. Vale acompanhar antes de qualquer decisão de capital real.
- **D29** (basis/funding arb paper bot): 19 trades settled, WR=68.4%, EV/trade=+0.36%, total
  +6.85% — resultado promissor, ainda sem relatório dedicado.

Ver `docs/state_of_research.md` itens 19, 21, 22, 24 e 27 para os dados completos.

---

## UPDATE 2026-07-07 — Correção crítica: Early Sell Optionality RE-REFUTADO

**Contexto:** rotina de checar todos os processos/resultados da AWS (D47-D52, early_sell_multi,
D55b). Memória ok (196-317MB disponíveis, sem incidente desta vez).

### Early Sell Optionality (HYP-SELL-01) — bug de hindsight bias encontrado

O "EDGE CONFIRMADO" reportado na seção acima (2026-07-05, N=50) e a extensão multi-símbolo
(`early_sell_multi.py`, N=550 acumulados em 10 símbolos até 2026-07-07) **tinham um bug
metodológico que invalida a conclusão**:

- `sell_profit = best_bid - buy_price`, onde `best_bid = max(bid_price em TODAS as amostras
  coletadas durante a vida do contrato)`. Isso é **viés de hindsight**: o máximo de um caminho
  de preço com ruído é, por construção matemática, sempre >= qualquer ponto fixo do mesmo
  caminho (incluindo o valor terminal/hold) — "vender no melhor ponto (visto em retrospecto)
  bate segurar" é quase uma tautologia, não evidência de mispricing da Deriv. Qualquer produto
  com optionality e ruído de preço mostraria o mesmo padrão em qualquer corretora.
- A checagem "non-hindsight" que supostamente confirmava o edge (vender no 1º bid >= threshold,
  já presente em `early_sell_test.py` desde a v1) tinha um bug relacionado: `EV_sell` era
  calculado só sobre os trials que DISPARARAM a regra (média condicional, também quase
  tautologicamente positiva, já que só dispara quando bid > buy_price) e o "EV_hold
  correspondente" pegava os primeiros N elementos de uma lista por ÍNDICE — não os hold-profits
  PAREADOS dos mesmos trials que dispararam. Uma comparação inválida que nunca de fato testou
  se a regra bate o hold.

**Correção aplicada e resultado:** comparação pareada por trial (se a regra dispara, usa o
profit da venda; senão, usa o profit do hold — sempre comparado contra "sempre segurar" como
baseline), bootstrap na diferença. Rodado em N=550 (10 símbolos, 8 thresholds ratio=1.1-1.8):

- **7/8 thresholds: diff EV cruza zero** (ex. ratio=1.3: n_triggered=367/550, diff=+0.05bps
  IC95%=[-0.54,+0.65]).
- **1/8 (ratio=1.8, o mais extremo): diff SIGNIFICATIVAMENTE NEGATIVO** (-0.20bps,
  IC95%=[-0.35,-0.01]).
- Nenhum dos 10 símbolos individualmente mostra IC95% excluindo zero em nenhum threshold.

Interpretação: vender cedo aumenta a win rate (trava lucro pequeno com mais frequência) mas
reduz o tamanho médio do ganho (perde os movimentos grandes que só aparecem segurando até o
expiry) — os dois efeitos se cancelam, sem EV líquido. **Sem edge.**

**Ações tomadas:**
1. `trading-engine/early_sell_multi.py`: `compute_stream_stats()` corrigido para expor
   `diff_ev_vs_hold`/`diff_ci95_vs_hold` (pareado, correto) por threshold; campos antigos
   (baseados em `best_bid`) renomeados com sufixo `_HINDSIGHT` e docstring explicando o viés,
   mantidos só por compatibilidade/contexto histórico. `periodic_summary()` agora imprime a
   métrica correta.
2. Redeployado na AWS, processo reiniciado (tmux `early_sell_multi`) — dados antigos
   preservados (`early_sell_multi_results.jsonl` é append-only).
3. `docs/state_of_research.md` (item 14, TL;DR, status consolidado) e `hypotheses-data.ts`
   (HYP-SELL-01: `status: live→refuted`, `confidence: 85→5`) atualizados.
4. **`early_sell_live.py` (executor real-money-ready) NÃO deve ser ativado** com este sinal.

### Checagem geral dos demais processos AWS (D47-D54, D52 live, D55b)

Tudo consistente com `docs/state_of_research.md` (itens 30-37), sem surpresas, exceto:
- **D48 (Accumulator tick-barrier race):** doc já descrevia o mecanismo (knockout atômico,
  sem janela de corrida) mas não tinha o EV agregado. Computado agora: N=20, 11/20 vendas
  genuínas mas EV total negativo (-$6.51, média -$0.3255/trial, IC95%=[-0.585,-0.060]) —
  reforça REFUTADO com número, não só mecanismo.
- **D52 (Deal Cancellation):** validação ao vivo (`deal_cancellation_live.py`, N=20 trades
  reais) já tinha sido rodada desde a última atualização do relatório — EV líquido
  +$0.147/trade, IC95%=[-$0.1415,+$0.4775] cruza zero, **INCONCLUSIVO** (script já imprime
  esse veredito). Ainda o único "quase-edge" nativo da Deriv na lista, mas precisa de mais
  amostra ao vivo.
- **D55b:** rodada original BTC/ETH/SOL (12h) a ~77% concluída. Nova rodada dedicada ao LINK
  (6h, motivada pelo LINK ter isolado como único sobrevivente do walk-forward de D55a) iniciada
  em paralelo (tmux `d55b_link`) — ver `docs/hyperliquid_report.md`.

Todos os outros (D37/D38/D39/D40/D41/D44/hft_bot/liq_bot/unlock_bot) seguem rodando sem
mudança de veredito relevante desde a última checagem.

---

## UPDATE 2026-07-08 — Auditoria completa dos 16 processos ativos (hft_bot + D29 + D34 + D36-D41)

**Contexto:** auditoria completa de todos os 16 processos tmux ativos na AWS (nada reiniciado
ou parado), cruzando `tmux ls` + `ps` + logs + `audit_hft_trades.py`. Ver `docs/state_of_research.md`
item 37 da Recomendação para o resumo consolidado em 3 categorias (estruturalmente sem caminho
pra veredito / esperando evento raro / amostra real acumulando).

### hft_bot — reconfirmado negativo com trades reais (não só H3 por analogia)

`audit_hft_trades.py` re-rodado encontra **32 ALIGNED / 2 ANTI** trades reais já fechados desde
o último check (2026-07-02, quando o shadow A/B ainda tinha 0 trades registrados). Segmentado
por versão (Wilson + bootstrap, dedup por `contract_id`): todas-versões N=34 (WR 23.5%, EV -$3.35,
IC95%[-$5.35,-$1.21]); subset V6.2-por-parâmetro (threshold=45 confirmado empírico, já que o
banner de restart não foi reimpresso após a mudança 50→45) N=12 (WR 8.3%, EV -$3.62,
IC95%[-$6.01,-$0.81]). **Ambos os cortes têm IC95% inteiramente negativo** — não é mais
"inconclusivo por N baixo". Shadow A/B ALIGNED vs ANTI: diff cruza zero e **ambos os grupos são
negativos** — reconfirma H3 (o problema é custo/timing de execução, não a direção escolhida).
Ver `docs/hft_v62_audit_report.md` e `hypotheses-data.ts` (HYP-HFT-01).

### D29 (basis_paper_bot.py) — segue melhorando com N maior

N=33 (subiu de 24), WR subiu para **72.7%** (de 70.8%), EV/trade +0.2635%, total +8.6958%,
duração média 1.2h. Trajetória 68.4%(N19)→70.8%(N24)→72.7%(N33) é o padrão saudável — oposto
do decaimento do D36. Ainda o lead mais promissor entre os processos em andamento, mas sem
IC95% formal computado (N ainda pequeno). Nota: este bot **não é D44** — são scripts e teses
diferentes (D29 = basis/funding disconnect persistente tipo carry trade; D44 = funding
extremo pontual) que compartilham o mesmo domínio. `docs/state_of_research.md` corrigido para
não confundir os dois (ver item 38).

### D36 (iv_anomaly_paper_bot.py) — decaimento agora é claro, não mais "ruído vs convergência"

N=37 (subiu de 14), WR caiu para **40.5%**. Com 5 leituras consecutivas em queda
(50.0%@N24→42.9%@N28→41.9%@N31→41.2%@N34→40.5%@N37), a trajetória é monotonicamente
decrescente — já não dá pra atribuir a ruído de amostra pequena como antes. Total ainda
positivo (+$1.517,90) só por skew (poucos winners grandes); os últimos 2 settles foram losses,
uma delas de -$420,94, derrubando o total de um pico de +$2.074,76@N35. Mesmo padrão de
decaimento que desmascarou o early-sell original. `hypotheses-data.ts`: confidence reduzida
40→20.

### D34, D38, D39, D40 — sem mudança de veredito, dados frescos

D34: ainda 0 cascades na janela mais recente. D38: mais anúncios capturados (torneios/promoções/
caridade, categoria OTHER), nenhum LISTING novo desde o TST. D39: expiry 9JUL26 se aproxima
(~1 dia), diffs BTC/ETH oscilando abaixo de 1%. D40: regime virou **STRONG SHORT** (3d supply
-$1.704M, grande redemption) — terceira mudança de regime em poucos dias.

### D37 e D41 — achado estrutural: não existe caminho para veredito no design atual

Revisando o código/output de `exchange_outflow_scan.py` (D37) e `wash_trading_scan.py` (D41) em
detalhe: **nenhum dos dois jamais correlaciona o signal score/anomalia com o retorno de preço
subsequente** — são scanners/contadores puros que só imprimem um score ou uma contagem de
anomalias a cada ciclo. D41 especificamente: revisados os 15 blocos "VERDICT" já impressos pelo
script desde que começou a rodar — todos contam só % de anomalias (ciclo mais recente: ~15M
trades/48.6h, clusters 0.401%, timestamp_anomalies 1.383%, volume_bursts 0.107%), nunca preço
antes/depois. **Isso significa que, como estão desenhados hoje, não existe caminho para produzir
um veredito de EV/win-rate nesses dois — precisariam de lógica nova (comparar retorno de preço
antes/depois de cada sinal), não mais tempo rodando ou mais amostra.** O mesmo problema estrutural
já existia em D40 (ver acima). `hypotheses-data.ts` atualizado com essa ressalva e confidence
reduzida (D37: 20→8, D41: 35→10).
