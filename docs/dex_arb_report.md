# DEX Arbitrage Scan — Jupiter (Solana) vs Binance CEX + Triangular (2026-07-03)

**Hipótese:** O agregador DEX Jupiter (Solana) pode ter pricing stale ou ineficiente vs Binance,
criando janela de arbitragem CEX-DEX. Adicionalmente, triangular arb (SOL→USDC→SOL) via Jupiter
pode ter roundtrip > 1.0 se as rotas otimizadas explorarem pools com pricing divergente.

## Metodologia

Script: `trading-engine/dex_arb_scan.py` (read-only, sem carteira, sem capital).

Três testes simultâneos, todos com dados reais ao vivo:

1. **CEX-DEX divergence (sell):** Quote Jupiter SOL→USDC vs Binance bookTicker mid.
   Divergência = (preço_jupiter - mid_binance) / mid_binance em bps.

2. **CEX-DEX divergence (buy):** Quote Jupiter USDC→SOL vs Binance mid.
   Mesmo cálculo, direção oposta.

3. **Triangular arb (chained):** SOL→USDC (leg 1), then usar o `outAmount` real da leg 1
   como input da leg 2 USDC→SOL. Roundtrip ratio = outAmount_leg2 / inAmount_leg1.
   **Crítico:** usar o output real da leg 1 (não um valor fixo baseado em Binance) —
   senão o ratio é inflacionado artificialmente.

### Dados coletados

| Run | Duração | Intervalo | Size | N válido | Binance spread |
|-----|---------|-----------|------|----------|----------------|
| 1   | 10 min  | 5s        | 1 SOL (~$81.5) | 104 | 1.2 bps |
| 2   | 10 min  | 7s        | 1 SOL (~$81.3) | 63  | 1.2 bps |
| 3   | 5 min   | 8s        | 10 SOL (~$813)  | 32  | 1.2 bps |

Total: ~199 amostras válidas em 3 runs.

### Jupiter Swap API

- Endpoint: `GET https://api.jup.ag/swap/v1/quote`
- Parâmetros: `inputMint`, `outputMint`, `amount` (lamports/micro-USDC), `slippageBps=50`
- Sem necessidade de API key para quotes (diferente da Prediction API)
- Rate limit: ~3 requests/ciclo com 0.5s stagger evita maioria dos 429s
- Rotas observadas: HumidiFi, GoonFi V2, Quantum, BisonFi, Riptide, SolFi V2, Meteora DLMM,
  Raydium CLMM, Orca Whirlpool, AlphaQ, TesseraV, Manifest+Scorch, PancakeSwap, Deriverse

## Resultados

### CEX-DEX Divergence

| Direção | N | Mean (bps) | Median | P5 | P95 | Min | Max | % positivo |
|---------|---|------------|--------|----|-----|-----|-----|------------|
| SOL→USDC (1 SOL) | 104 | -8.93 | -8.91 | -10.00 | -7.85 | -10.66 | -6.08 | 0.0% |
| USDC→SOL (1 SOL) | 104 | -9.43 | -9.37 | -10.76 | -8.35 | -12.27 | -7.11 | 0.0% |
| SOL→USDC (10 SOL) | 32 | -9.68 | -9.48 | -10.82 | -8.76 | -10.94 | -8.64 | 0.0% |
| USDC→SOL (10 SOL) | 32 | -9.65 | -9.45 | -11.75 | -8.65 | -11.99 | -8.65 | 0.0% |

**Zero amostras com divergência positiva** em qualquer run ou direção. Jupiter é consistentemente
~9 bps pior que Binance mid. O gap é o fee implícito do agregador (AMM pool fee + Jupiter routing fee).

### Triangular Arbitrage (chained)

| Size | N | Mean (bps) | Median | P5 | P95 | Min | Max | % > 0 |
|------|---|------------|--------|----|-----|-----|-----|--------|
| 1 SOL | 63 | +0.76 | +0.53 | -0.52 | +2.82 | -1.09 | +7.93 | 77.8% |
| 10 SOL | 32 | -0.11 | -0.06 | -1.05 | +2.15 | -3.01 | +2.18 | 40.6% |

Roundtrip é essencialmente zero. O max observado (+7.93 bps) está muito abaixo do threshold
necessário (~50 bps para cobrir 2x AMM fee + tx fee + priority fee). Com 10 SOL, o roundtrip
fica levemente negativo (price impact cresce com tamanho).

### Bug crítico corrigido

A primeira versão do script usava um `usdc_raw` fixo (baseado no mid da Binance) como input
da leg 2, em vez do `outAmount` real da leg 1. Como Jupiter é ~9 bps mais barato que Binance,
o input da leg 2 era artificialmente maior que o output real da leg 1, inflando o roundtrip
ratio para +28 bps médios (falso positivo). Após corrigir para usar o output encadeado real,
o roundtrip caiu para ~0 bps. **Lição reutilizável:** em arb triangular, sempre encadear
o output real da perna anterior — nunca usar um valor de referência externo.

## Veredito

**SEM EDGE.** Três frentes testadas, todas refutadas:

1. **CEX-DEX sell:** Jupiter sempre ~9 bps abaixo de Binance. Nunca supera o fee de ~25 bps
   (AMM pool fee) necessário para break-even. 0/199 amostras positivas.

2. **CEX-DEX buy:** Mesmo padrão, ~9.5 bps abaixo. 0/199 amostras positivas.

3. **Triangular:** Roundtrip ~0 bps (máx +7.93 bps em 1 SOL, -0.11 bps em 10 SOL).
   Threshold necessário: ~50 bps. Margem insuficiente por fator 6-25x.

### Por que não há edge

Jupiter é um **agregador** — ele já roteia entre 15+ DEXs (HumidiFi, GoonFi, Quantum, Meteora,
Raydium, Orca, etc.) para encontrar o melhor preço disponível. O "arbitrage" dentro do agregador
já é capturado pelo próprio motor de roteamento (Metis). O fee de ~9 bps é o custo residual
depois da otimização, não uma ineficiência explorável.

O gap CEX-DEX de ~9 bps é estrutural: AMM pools têm fees embutidos (0.25% típico = 25 bps por
swap, mas Jupiter encontra rotas mais baratas via pools de menor fee), e o agregador adiciona
seu próprio fee. Binance tem spread de 1.2 bps e zero fee de taker para VIP 0 (maker/taker
varia). A diferença estrutural é permanente, não transiente.

Diferente de Deriv (onde a casa embute margem no payout), aqui o custo é transparente e
competitivo — mas ainda é custo. O mercado DEX em Solana é eficiente o suficiente para que
um agregador já capture qualquer ineficiência intra-DEX.

## Próximos passos

- **MEV/Jito bundles:** A única forma de capturar arb em Solana seria com execução atômica
  (Jito bundle) onde ambas as pernas fecham no mesmo slot. Mas o scan mostra que nem o
  sinal pré-execução existe — o gap é sempre negativo.
- **Pools individuais (não agregadas):** Jupiter já otimiza entre elas, mas talvez pools
  muito pequenas/little-known não entrem no agregador. Difícil de escalar e provavelmente
  liquidity insuficiente.
- **CEX-DEX com outras venues:** Testar com Coinbase ou Kraken em vez de Binance. Mas
  CEXs têm spreads similares e o gap estrutural de fee DEX permanece.
