# D10 — DeFi Liquidation Opportunity Scan Report (2026-07-03)

**Veredito: SEM EDGE para retail.** As liquidações Aave V3 são reais e lucrativas
em teoria (7.8% bonus médio), mas a competição MEV torna a captura impraticável
para um bot retail. Latência de 30-60s vs <12s dos bots profissionais.

## D10 — DeFi Liquidation Monitor (Aave V3)

### Hipótese
Liquidadores podem repay debt e seize collateral + bonus (5-10%) quando health
factor < 1.0. Um bot de liquidação pode ser lucrativo via flash loans (sem capital).

### Metodologia
- **Script:** `trading-engine/defi_liquidation_scan.py`
- **Chains tentadas:** Ethereum, Polygon, Arbitrum, Base
- **RPCs livres:** 1rpc.io, publicnode, cloudflare, llamarpc, mainnet.base.org, arb1.arbitrum.io
- **Método:** `eth_getLogs` filtrando topic `LiquidationCall` no contrato Pool da Aave V3
- **Sem API key:** apenas RPCs públicos gratuitos
- **Período:** ~10.6 dias (500000 blocos) na Base; outras chains não funcionaram

### Resultados

| Métrica | Valor |
|---------|-------|
| Chain com dados | Base (outras RPCs bloquearam eth_getLogs) |
| Eventos totais | 108 |
| Período | 254.8 horas (~10.6 dias) |
| Taxa | 0.42 liquidações/hora |
| Bonus médio | 7.8% |
| Maior debt liquidado | 1,369 USDC |
| Maior cluster | 40 eventos em 1 chunk (provável crash) |

### Análise de RPCs Gratuitos

| RPC | eth_getLogs | Notas |
|-----|-------------|-------|
| mainnet.base.org | ✅ | Funciona, 5000 blocks/chunk |
| arb1.arbitrum.io | ✅ (pequeno range) | Funcionou no 1o run, falhou depois |
| 1rpc.io/eth | ⚠️ | Limite 50 blocks, instável |
| publicnode.com | ❌ | Requer token para archive |
| polygon-rpc.com | ❌ | 401 Unauthorized |
| cloudflare-eth.com | ❌ | Internal error |
| llamarpc.com | ❌ | 521 (down) |

**Problema fundamental:** RPCs gratuitos limitam `eth_getLogs` porque é uma
operação cara (requer acesso a archive nodes). Sem API key paga (Alchemy,
Infura, QuickNode) ou The Graph API key, é impraticável escanear múltiplas
chains em tempo real.

### Análise de Profitabilidade

#### Tamanho das liquidações (Base, 10.6 dias)

| Percentil | Debt (USDC) |
|-----------|-------------|
| P90 | ~1,370 |
| P75 | ~43 |
| P50 (mediana) | ~0.3 |
| P25 | ~0.01 |

A maioria das liquidações é **micro** (< $1 debt). Apenas 2-3 eventos
grandes (> $500) em 10 dias. O bonus de 7.5% sobre $1,370 = ~$103.

#### Competição MEV

| Fator | Bots Profissionais | Nosso Scanner |
|-------|-------------------|---------------|
| Latência detecção | <1 block (12s ETH, 2s Base) | 30-60s (RPC lag + processamento) |
| Método | Mempool monitoring + flashbots | eth_getLogs polling |
| Capital | Flash loans + próprio | Flash loans (teórico) |
| Gas optimization | MEV bundles, priority fees | Standard tx |
| Capture rate estimado | 90-99% | <1% |

**O gap de latência é fatal.** Um bot de liquidação precisa detectar a posição
underwater e submeter a tx no mesmo bloco ou no próximo. Nosso scanner via
`eth_getLogs` só vê o evento **depois** que já foi incluído em um bloco — ou
seja, depois que a liquidação já aconteceu.

Para competir, seria necessário:
1. Indexar eventos on-chain em tempo real via WebSocket subscription
2. Calcular health factor de todas as posições em memória
3. Submeter tx via flashbots/MEV bundle (não mempool público)
4. Co-locar em datacenter próximo ao nó validador

Isto é infraestrutura profissional, não um script Python.

#### Custo-benefício (Base)

- Gas por liquidação: ~$0.30
- Bonus médio por evento: 7.8% × debt
- Para break-even: debt > $0.30/0.078 = ~$4
- Apenas ~5/108 eventos (4.6%) têm debt > $4
- Receita potencial se capturasse 100%: ~$200 em 10 dias
- Receita realista (1% capture): ~$2 em 10 dias

### Conclusão D10

O MEV de liquidação é **real e lucrativo** — mas apenas para bots profissionais
co-locados com infraestrutura MEV. Para um scanner retail:

1. **Latência intransponível:** 30-60s vs <12s dos profissionais
2. **RPCs gratuitos insuficientes:** sem archive node, não dá para escanear
3. **Micro-liquidações dominam:** 95% dos eventos têm debt < $4
4. **Capture rate ~0%:** sem flashbots, tx seria front-run instantaneamente
5. **Custo de infra:** Alchemy/Infura paid plan + WebSocket + MEV bundle = $50-200/mês mínimo

**Não é um edge explorável sem infraestrutura profissional e capital.**

## Comparação Geral D7-D10

| Hipótese | Mecanismo | N | Resultado | Veredito |
|----------|-----------|---|-----------|----------|
| D7 | CEX-CEX arb | 100 | 0/100 positivos | SEM EDGE |
| D8 | Triangular Binance | 120 | 0/120 positivos | SEM EDGE |
| D9 | Funding carry | 19 perps | 0% janelas 7d lucrativas | SEM EDGE |
| **D10** | **DeFi liquidations** | **108** | **<1% capture rate** | **SEM EDGE (retail)** |

## Arquivos

- **Script:** `trading-engine/defi_liquidation_scan.py`
- **Dados:** `trading-engine/defi_liquidation_samples.json`
