# D34 — Liquidation Cascade Detection & Front-Run

**Data:** 2026-07-04
**Status:** EM TESTE CONTÍNUO (aguardando eventos)
**Autor:** `liquidation_cascade_scan.py`
**Confiança:** 25% (potencial alto, mas sem dados ainda)

## Tese

Liquidações em cascata: 3+ liquidations em 10s mesma direção = cascade. Se longs sendo
liquidados, preço continua caindo (forced selling) → short e ride cascade. Se shorts sendo
liquidados, preço continua subindo (forced buying) → long e ride cascade.

Scan: monitora liquidations em tempo real na Binance Futures, detecta cascades, simula
P&L a 30s/60s/120s/300s hold. Net após 0.1% taker fee por lado.

## Metodologia

- Polling de Binance Futures liquidation orders a cada 2s por 30min
- Detecção de cascade: 3+ liquidations em janela de 10s na mesma direção (BUY ou SELL)
- Quando cascade detectada: simula entrada na direção da cascade
- Hold periods testados: 30s, 60s, 120s, 300s
- Fee: 0.1% taker por lado (0.2% roundtrip)
- Bot reiniciado em loop infinito na AWS (30min scan + 60s pause + repeat)

## Resultados

### Primeiro scan (30min)
- **0 liquidations detectadas** — mercado calmo
- **0 cascades detectadas**
- **0 trades simulados**

### Status na AWS
- Bot rodando em loop contínuo (tmux session `liq_bot`)
- A cada 30min: novo scan completo
- Log: `liquidation_cascade_scan.log` na AWS

### Por que 0 eventos?

Cascades de liquidação são **eventos raros** que requerem:
- Volatilidade alta (crash ou pump)
- Alto leverage no mercado (muitas posições alavancadas)
- Trigger de preço que atinge stop losses em sequência

Em mercado calmo (BTC ~$63k, baixa volatilidade), liquidations são esporádicas e não
formam cascades. O bot precisa rodar por **dias** para capturar eventos durante:
- Flash crashes
- Notícias macro (CPI, FOMC, etc)
- Movimentos de whale
- Expiries de opções grandes

## Veredito

**EM TESTE CONTÍNUO.** Sem dados suficientes para veredito. Cascade continuation é
potencialmente o edge mais agressivo possível (front-run forced selling/buying), mas
precisa capturar eventos reais para validar.

### Próximos passos
1. Deixar bot rodando na AWS por dias/semanas
2. Quando cascade for detectada, analisar:
   - WR de continuation após cascade
   - EV por trade após fees
   - Optimal hold period (30s vs 60s vs 120s vs 300s)
   - Correlação com tamanho da cascade (número de liquidations, volume)
3. Se WR > 60% após fees, implementar trading real

## Arquivos

- **Scan script:** `trading-engine/liquidation_cascade_scan.py`
- **Log (AWS):** `liquidation_cascade_scan.log`
- **Dashboard:** `hypothesis-lab-os/src/lib/hypotheses-data.ts` (HYP-LIQ-01)
- **Paper bot:** N/A (scan only, sem paper trading bot ainda)
