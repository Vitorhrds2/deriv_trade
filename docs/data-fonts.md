## O que já temos (e funciona)

- **55 hipóteses testadas** — Deriv (14 produtos, fechado), Polymarket (fechado), CEX arb (fechado), DEX arb (fechado), microestrutura (D33/D41/D43, refutado por fees)
- **D17 validado** (token unlock, event-driven)
- **Hub algotrade** — teoria geral, focado em Vietnam equity/derivatives (pouco aplicável a crypto)
- **Infra AWS** — 15 processos rodando, WS streams, Binance API, Deriv API
- **Framework estatístico** — Wilson CI, bootstrap, Bonferroni, forward return tracker

## O que falta para alta assertividade em novas hipóteses

### 1. Papers acadêmicos de crypto microestrutura
Preciso de papers específicos sobre:
- **Funding rate dynamics** — padrões de funding em perps, predictabilidade, mean reversion
- **Liquidation cascades** — triggers, magnitude, recovery patterns
- **On-chain anomalies** — whale movements, exchange inflows/outflows como preditores de preço
- **Perpetual futures basis** — basis convergence patterns, funding arbitrage

**Onde buscar**: SSRN (papers de crypto market microstructure), arXiv (q-fin), papers de Coinbase Research, Binance Research

### 2. Dados on-chain (maior gap atual)
Não temos nenhuma fonte on-chain além de stablecoin mint (D40, superficial). Preciso de:
- **Glassnode / CryptoQuant API** — exchange inflows/outflows, whale alerts, miner reserves
- **Nansen** — wallet labeling, smart money tracking
- **Etherscan/BSCscan APIs** — large transfers, contract interactions

Isso abriria hipóteses como: "large exchange inflow → price drop within X hours" ou "whale accumulation → price pump"

### 3. Dados de opções crypto mais ricos
D36 (IV anomaly) usa Deribit mas só BTC/ETH. Preciso de:
- **Deribit API** acesso completo (todas expiries, todos strikes, greeks em tempo real)
- **Lyra Finance** (DeFi options on-chain)
- **Historical IV surface data** — para backtestar D36 com mais rigor

### 4. Plataformas DeFi não exploradas
Só testamos DEX arb (refutado). Não testamos:
- **MEV / sandwich attacks** — possível capturar como atacante em Solana/EVM?
- **Liquidation bots** — Aave/Compound com infra própria (D10 mostrou que retail não captura, mas vale re-testar com melhor infra)
- **GLP/GMX** — pegando fees do protocolo como LP
- **Pendle / fixed income** — yield trading, PT/YT arbitrage

### 5. Eventos crypto não testados
D17 (unlock) validou event-driven. Outros eventos não testados:
- **Governance votes** — price impact de propostas em DAOs
- **Protocol upgrades / forks** — price reaction a upgrades técnicos
- **ETF flows** — BTC ETF inflows/outflows como preditor
- **Halving / supply schedule events** — LTC halving, EIPs
- **Exchange listings/delistings** (D18 testou listing, refutado, mas delisting não)
- **Airdrops / token distributions** — similar a D17 mas grátis

### 6. Acesso a dados institucionais
- **Kaiko** — institutional trade data, order book depth history
- **Skew** — derivatives analytics, options flow
- **CoinMetrics** — on-chain + market data integrado

## Prioridade de ação

Se você me der acesso a **uma** dessas fontes, a de maior impacto seria:

| Prioridade | Fonte | Por quê | Hipóteses que abre |
|-----------|-------|---------|-------------------|
| **1** | CryptoQuant ou Glassnode API | On-chain data é o maior gap | 5-10 hipóteses novas (whale, inflow, miner) |
| **2** | Papers SSRN de crypto microstructure | Base teórica para hipóteses com fundamento | 3-5 hipóteses acadêmicas |
| **3** | Deribit API completo + historical IV | Expandir D36 com mais dados | 2-3 hipóteses de vol trading |
| **4** | Acesso a Solana RPC próprio | MEV/sandwich testing | 2-3 hipóteses DeFi |

**Você tem acesso a alguma dessas fontes?** Algum desses caminhos te interessa mais? Posso também buscar papers gratuitos no SSRN/arXiv agora mesmo se quiser começar por aí.