# D32 — Cross-Exchange Latency Arbitrage (Binance vs Bybit/OKX)

**Data:** 2026-07-04
**Status:** REFUTADO
**Autor:** `latency_arb_scan.py`
**Confiança:** 5% (refutado com alta confiança)

## Tese

Binance é a exchange mais rápida. Se o preço do BTC move na Binance primeiro, Bybit/OKX
lagam em milliseconds. Se lag > 0.2% (fees roundtrip taker), comprar na exchange lagging
quando o leader move é arbitragem livre.

## Metodologia

- Polling de 3 exchanges (Binance, Bybit, OKX) via REST API
- Símbolos: BTC, ETH, SOL (USDT perps)
- Intervalo alvo: 100ms (5min = 3000 samples)
- Divergência calculada: max(|Binance - Bybit|, |Binance - OKX|) / Binance
- Threshold de profit: divergência > 0.2% (fees roundtrip taker)

## Resultados

### Dados coletados
- **1,200+ samples** coletados (scan ainda rodando mas veredito já conclusivo)
- Tempo real por sample: **~2.5s** (não 100ms) — 3 chamadas HTTP sequenciais

### Divergência observada

| Métrica | Valor |
|---|---|
| Divergência máxima | ~0.02% ($12 em $63,000) |
| Divergência média | ~0.005% ($3 em $63,000) |
| Fees roundtrip taker | 0.2% ($126 em $63,000) |
| Razão divergência/fees | 1:10 (divergência 10x menor) |

### Exemplos de samples

```
Sample 801: Binance=$63,314.01  Bybit=$63,315.70  OKX=$63,326.10  → max diff $12.09 (0.019%)
Sample 701: Binance=$63,271.99  Bybit=$63,277.10  OKX=$63,284.00  → max diff $12.01 (0.019%)
Sample 201: Binance=$63,212.01  Bybit=$63,209.90  OKX=$63,212.30  → max diff $2.41 (0.004%)
```

### Problemas identificados

1. **REST API é lenta demais:** Cada sample faz 3 requests HTTP sequenciais (Binance + Bybit + OKX), cada um levando 1-2s. Resultado: 1 sample a cada ~127s, não 100ms. O `time.sleep(0.1)` é irrelevante — o bottleneck é a latência das chamadas REST.

2. **Divergência máxima 10x menor que fees:** Maior divergência observada em 1200+ samples foi 0.02%. Fees roundtrip taker são 0.2%. Mesmo que Binance liderasse 100% das vezes, o profit seria negativo.

3. **Não há leader consistente:** Em alguns samples Bybit está acima de Binance, em outros abaixo. A direção do lag é aleatória a esta granularidade — não há sinal de que Binance consistentemente lidera.

## Veredito

**REFUTADO.** Latency arbitrage entre exchanges é um jogo institucional que requer:

| Requisito | Nosso setup | Necessário |
|---|---|---|
| Latência de dados | ~2-5s (REST) | <1ms (WebSocket) |
| Distância dos servidores | EC2 Europa | Co-location near exchange matching engines |
| Execução | REST API | WebSocket API + FIX protocol |
| Custos | 0.2% taker roundtrip | Maker orders (0% ou negativo) |

Firms como Jump Trading e Wintermute gastam milhões em co-location e infra sub-microsecond.
Não é viável sem infra profissional.

## Arquivos

- **Scan script:** `trading-engine/latency_arb_scan.py`
- **Log:** `trading-engine/latency_arb_scan.log`
- **Dashboard:** `hypothesis-lab-os/src/lib/hypotheses-data.ts` (HYP-LATARB-01)
