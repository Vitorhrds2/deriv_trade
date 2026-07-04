# D33 — Order Book Imbalance Alpha (predict next-tick direction)

**Data:** 2026-07-04
**Status:** REFUTADO
**Autor:** `order_book_imbalance_scan.py`
**Confiança:** 5% (refutado com alta confiança)

## Tese

Se volume de bids >> volume de asks no order book, preço sobe no próximo segundo.
Imbalance ratio > 0.60 → long, < 0.40 → short. Testar se OBI prediz direção
a 1s/5s/10s horizon, net após 0.1% taker fee por lado.

## Metodologia

- Polling de Binance order book depth (top 20 levels) a cada 1s por 10min
- Símbolos: BTCUSDT, ETHUSDT, SOLUSDT
- OBI = bid_volume / (bid_volume + ask_volume)
- Sinais: OBI > 0.60 → LONG, OBI < 0.40 → SHORT
- Testado em 3 horizons: 1s, 5s, 10s
- Two variants: simple OBI e volume-weighted OBI
- Fee: 0.1% taker por lado (0.2% roundtrip)

## Resultados

### Dados coletados
- **600 samples** × 3 símbolos = 1,800 observações
- **2,400+ signals** across 3 horizons

### Resultados por símbolo e horizon

| Símbolo | Horizon | Signals | WR Direcional | EV/trade | Total P&L | Wins | Losses |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 1s | 517 | 37.9% | -0.099% | -51.2% | 0 | 517 |
| BTCUSDT | 5s | 513 | 54.2% | -0.097% | -49.7% | 0 | 513 |
| BTCUSDT | 10s | 509 | 62.5% | -0.095% | -48.3% | 0 | 509 |
| ETHUSDT | 1s | 511 | 37.9% | -0.099% | -50.6% | 0 | 511 |
| ETHUSDT | 5s | 513 | 54.2% | -0.097% | -49.7% | 0 | 513 |
| ETHUSDT | 10s | 509 | 62.5% | -0.095% | -48.3% | 0 | 509 |
| SOLUSDT | 1s | 447 | 19.0% | -0.101% | -45.0% | 0 | 447 |
| SOLUSDT | 5s | 443 | 28.2% | -0.104% | -45.9% | 0 | 443 |
| SOLUSDT | 10s | 438 | 28.8% | -0.109% | -47.7% | 0 | 438 |

### Achado central

**WR direcional chega a 62.5% em 10s, mas 0 wins após fees (100% negativo).**

OBI tem algum poder preditivo direcional — WR aumenta com horizon (37.9% → 62.5% de 1s para 10s
em BTC). MAS movimentos de preço em 1-10s são menores que 0.1% fee por lado. Resultado:
**0 trades lucrativos em 2,400+ signals**.

### Volume-weighted OBI

Resultados quase idênticos ao OBI simples — weighted não adiciona valor preditivo.

## Veredito

**REFUTADO.** OBI tem poder preditivo direcional real (62.5% WR em 10s), mas:

1. **Movimentos de preço < fees:** Em 10s, preço move < 0.1% na maioria dos casos. Fee taker
   de 0.1% por lado consome todo o movimento.
2. **0% de trades lucrativos:** 2,400+ signals e nenhum gerou profit após fees.
3. **Precisaria:** WebSocket L2 sub-second + maker orders (0 fee) para ser viável. Mesmo
   assim, competição com HFT firms que já fazem isso com infra superior.

## Arquivos

- **Scan script:** `trading-engine/order_book_imbalance_scan.py`
- **Log:** `trading-engine/order_book_imbalance_scan.log`
- **Dashboard:** `hypothesis-lab-os/src/lib/hypotheses-data.ts` (HYP-OBI-01)
