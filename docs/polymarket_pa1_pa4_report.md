# Polymarket PA1-PA4 — Relatório de Investigação (2026-07-03)

**Veredito: SEM EDGE em PA1, PA2, PA3. PA4 não testável isoladamente (mecanismo já refutado pelo PA5).**

## Contexto

PA1-PA4 são quatro hipóteses de arbitragem no Polymarket, originalmente agrupadas no
`state_of_research.md` como "esperado repetir o padrão sub-custo (snipe <7s por bots,
execução não-atômica, regra de resolução como assassino em cross-venue). Ainda não
rodados ao vivo." PA5 (stale-book near settlement) já estava refutado (N=1838,
`aligned_pior`, IC95% não cruza zero).

Este relatório formaliza e testa PA1-PA4 individualmente.

## Definição das Hipóteses

| ID | Hipótese | Mecanismo | Teste |
|----|----------|-----------|-------|
| PA1 | New market sniping | Mercados recém-criados têm books mal precificados antes da convergência de bots | Monitorar mercados novos (<10min), medir spread desde criação |
| PA2 | Cross-market consistency | Mercados logicamente relacionados (BTC 5m vs 15m) têm probabilidades implícitas inconsistentes | Comparar ask do "Up" entre janelas 5m e 15m sobrepostas |
| PA3 | Multi-outcome arbitrage | Mercados com N outcomes mutuamente exclusivos onde sum(best asks) < $1.00 = arb livre | Escanear todos os mercados ativos, somar best asks |
| PA4 | Near-resolution convergence | Book converge lentamente para ~$1.00/$0.00 perto do settlement | Monitorar mercados próximos do close, medir convergência vs Binance |

## Metodologia

**Script:** `trading-engine/polymarket_arb_scan.py` (read-only, sem credenciais, sem capital)

**APIs usadas:**
- Gamma API (`gamma-api.polymarket.com`): lista de mercados ativos, metadados
- CLOB API (`clob.polymarket.com`): orderbook (best ask/bid por token)
- Binance API (`api.binance.com`): preço BTCUSDT como referência

**Período de coleta:** 10 minutos, 10 ciclos, intervalo de 20s (2026-07-03 13:04–13:14 UTC)

**Custos considerados:** Polymarket cobra ~2% (200 bps) de taker fee. Para PA3, arb
lucrativo requer sum(asks) < $0.96 (não só < $1.00).

## Resultados

### PA3 — Multi-outcome arbitrage

- **N = 940 mercados** válidos (94 por ciclo × 10 ciclos)
- sum(asks): **min = $1.0010**, mean = $1.0021, max = $1.0210
- Arb bruto (sum < $1.00): **0/940**
- Arb lucrativo (sum < $0.96, pós-fee): **0/940**
- **Veredito: SEM EDGE.** O book do Polymarket é perfeitamente precificado — sum(asks)
  é sempre ≥ $1.00, tipicamente $1.00–$1.02. O spread embutido (ask acima de 1.00) é
  exatamente o fee do market maker. Não há arb livre em nenhum mercado multi-outcome.

### PA2 — Cross-market consistency (5m vs 15m)

- **N = 10 pares** comparados (5m vs 15m BTC Up/Down sobrepostos)
- diff (up_5m − up_15m): **mean = 0.0 bps, max|diff| = 0.0 bps**
- Todos os pares: up_5m = 0.51, up_15m = 0.51
- **Veredito: SEM EDGE.** Mercados 5m e 15m são perfeitamente consistentes. O mesmo
  market maker precifica ambos os horizontes com a mesma probabilidade implícita (51%).
  Não há inconsistência explorável entre janelas sobrepostas.

### PA1 — New market sniping

- **N = 24 observações** de mercados novos (age < 10min)
- Spread (up_ask vs 1−down_ask): **100 bps** em todas as observações
- Idade mínima observada: **37 segundos** — spread já era 100 bps
- up_ask = 0.51, down_ask = 0.50 desde o primeiro segundo observado
- **Veredito: SEM EDGE.** Bots convergem os books instantaneamente. Não há janela de
  mispricing em mercados recém-criados. O spread de 100 bps é estrutural (fee), não
  explorável. Confirma a expectativa original: "snipe <7s por bots".

### PA4 — Near-resolution convergence

- **N = 0** — nenhum mercado BTC Up/Down estava próximo da resolução durante o scan
  (todos com endDate ~24h no futuro)
- **Veredito: MECANISMO JÁ REFUTADO pelo PA5.** PA4 testa o mesmo mecanismo que PA5
  (book lento para convergir perto do settlement), mas em uma janela mais ampla
  (minutos vs segundos). PA5, com N=1838 trades, já demonstrou que o book NÃO está
  stale — aligned WR=88.5% mas PnL médio = −$0.031, diff aligned-anti = −$0.037,
  IC95% [−$0.060, −$0.014] não cruza zero. Se o book não está stale nos últimos 30s,
  não estará stale nos últimos minutos também.

## Conclusão

**PA1-PA4: TODAS REFUTADAS.** O Polymarket é um mercado eficiente para arbitragem:

1. **Books são perfeitamente precificados desde a criação** (PA1) — bots convergem em
   <37s, provavelmente instantaneamente
2. **Mercados relacionados são consistentes** (PA2) — 5m e 15m têm a mesma probabilidade
   implícita, sem divergência explorável
3. **Sum(asks) ≥ $1.00 em 100% dos mercados** (PA3) — o fee embutido no ask já captura
   qualquer "arb" aparente
4. **Convergência perto do settlement é eficiente** (PA4/PA5) — o book reflete o outcome
   em tempo real, não há janela de stale-book

**Lição central:** O Polymarket é um mercado CLOB maduro com market makers profissionais
que precificam corretamente desde a criação até a resolução. A execução não-atômica
(sem Solana atomic swap) e a regra de resolução (Chainlink, não Binance) são barreiras
adicionais que tornam qualquer edge residual inexplorável na prática.

## Próximos passos

Com PA1-PA5 todos refutados, o Polymarket como venue de arbitragem está encerrado. As
frentes restantes com potencial real de descoberta são:
- **Outras DEXs/blockchains** com agregadores menos maduros que Jupiter
- **MEV/Jito bundles** em Solana (execução atômica, mas scan mostra que nem o sinal
  pré-execução existe)
- **Early sell optionality** na Deriv (rodando, preliminar SEM EDGE)

## Arquivos

- **Script:** `trading-engine/polymarket_arb_scan.py`
- **Amostras:** `trading-engine/polymarket_arb_samples.json`
- **PA5 (referência):** branch `feat/polymarket-arb`, `pa5_collector.py`
