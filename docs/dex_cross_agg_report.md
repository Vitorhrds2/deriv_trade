# D6 — Cross-Aggregator DEX Arbitrage Report (2026-07-03)

**Veredito: SEM EDGE.** Os spreads entre agregadores existem (20-450 bps) mas são
artefatos de quote APIs indicativas, não preços executáveis. O mercado real (BSC,
mais líquido) mostra roundtrip negativo de -1 a -3 bps.

## Contexto

Após refutar Solana DEX arb (Jupiter vs Binance, ~9 bps gap), a próxima fronteira era
testar chains EVM com agregadores menos maduros. A hipótese D6 postula que diferentes
agregadores DEX (OpenOcean, Paraswap, LiFi) podem encontrar rotas diferentes em chains
menos líquidas, criando spreads exploráveis.

## Hipótese

**D6a — Cross-aggregator spread:** Se agregadores diferentes retornam quotes diferentes
para o mesmo par, o spread entre melhor e pior pode indicar ineficiência de roteamento.

**D6b — Roundtrip arb:** Vender token A→B via melhor agregador, recomprar B→A via melhor
agregador. Se roundtrip > 0 bps (após gas), arb existe.

## Metodologia

**Script:** `trading-engine/dex_cross_agg_scan.py` (read-only, sem wallet, sem capital)

**Aggregators (todos gratuitos, sem API key):**
- OpenOcean v4 (30+ chains, 0.2% fee)
- Paraswap/Velora (10+ EVM chains, 0.15% positive slippage)
- LiFi (all chains, 0% fee, rate-limited)

**Chains testadas:** BSC (56), Base (8453), Arbitrum (42161), Polygon (137)

**Pares testados:** Native→USDT/USDC, CAKE→USDT, ETH→USDT, ARB→USDC, WETH→USDC

**Tamanhos:** 1 e 5 tokens nativos (~$250-$8500)

**Período:** 10 minutos, 5 ciclos, intervalo de 30s (2026-07-03 13:42-13:54 UTC)

**Custos considerados:** Gas não incluído na análise (L2s: $0.01-0.10/swap, BSC: $0.10-0.30/swap).
O foco é no spread bruto entre quotes.

## Resultados

### D6a — Cross-aggregator spread

| Chain | N | Mean (bps) | Max (bps) | Padrão |
|-------|---|------------|-----------|--------|
| **BSC** | 28 | 6.6 | 28.8 | Converge para 0-5 bps após ciclo 1 |
| **Base** | 10 | 22.7 | 34.0 | Paraswap consistentemente > OpenOcean por ~25 bps |
| **Arbitrum** | 19 | 48.8 | 165.6 | WETH/USDC: ~30 bps; ARB/USDC: 40-165 bps |
| **Polygon** | 20 | 175.6 | 453.1 | WMATIC/USDC: 280-450 bps (OpenOcean >> Paraswap) |

**Observação crítica:** O ciclo 1 teve spreads muito maiores que os ciclos 2-5,
sugerindo que as APIs aquecem caches no primeiro request. BSC convergiu de 28 bps
para 0-5 bps. Isso indica que os spreads iniciais são stale quotes, não ineficiências
reais.

### D6b — Roundtrip arbitrage

| Chain | Par | Roundtrip (bps) | Padrão |
|-------|-----|-----------------|--------|
| **BSC** | WBNB→USDT→WBNB | **-0.6 a -2.0** | Consistentemente negativo |
| **BSC** | WBNB→USDC→WBNB | **-2.2 a -3.4** | Consistentemente negativo |
| **Base** | WETH→USDC→WETH | +28.7 a +45.2 | Positivo via Paraswap→Paraswap |
| **Arbitrum** | WETH→USDC→WETH | +17.8 a +72.7 | Positivo via Paraswap→Paraswap |
| **Polygon** | WMATIC→USDC→WMATIC | +825 a +836 | Absurdo (stale quote OpenOcean) |

**15/25 roundtrips positivos**, mas o padrão revela que isso é artefato:

1. **BSC (controle de sanidade):** Roundtrip negativo (-1 a -3 bps). BSC é a chain
   mais líquida com mais DEXs (PancakeSwap, BiSwap, MDEX, ApeSwap, etc). Os agregadores
   convergem para o mesmo preço, e o roundtrip negativo reflete o custo real (spread +
   fee). **Este é o mercado real.**

2. **Base/Arbitrum (falso positivo):** Roundtrip positivo via Paraswap→Paraswap. Se o
   MESMO agregador cita 1748 USDC para vender WETH e depois cita 1.006 WETH para
   recomprar com 1748 USDC, está dando uma inconsistência interna de 60 bps. Isso é
   impossível em execução real — a quote API é indicativa e otimista.

3. **Polygon (stale quote):** OpenOcean cita WMATIC 400+ bps acima de Paraswap,
   consistentemente. Isso é quase certamente um preço cached/stale no OpenOcean para
   WMATIC/USDC. Em execução real, a transação reverte ou slippage come o spread.

## Análise: por que BSC é o controle de sanidade

BSC tem:
- Mais DEXs ativos que qualquer outra chain EVM (PancakeSwap V2/V3, BiSwap, MDEX,
  ApeSwap, BabySwap, etc.)
- Mais liquidez total em pools nativos
- Aggregators com routing mais maduro

Resultado: spreads convergem para 0-5 bps, roundtrip = -1 a -3 bps. **Este é o
comportamento esperado de um mercado eficiente** — o agregador encontra o melhor
preço, e o custo de ida e volta é o fee + slippage mínimo.

Nas chains menos líquidas (Base, Arbitrum, Polygon), os spreads são maiores não porque
há arb explorável, mas porque:
1. Menos pools = routing menos otimizado = quotes mais divergentes
2. Quote APIs são indicativas (não garantem execução)
3. Stale caches em agregadores menores (OpenOcean)
4. RFQ liquidity em Paraswap que pode não preencher em execução real

## Custo de execução real

Para que o roundtrip seja lucrativo, precisa cobrir:
- Gas: BSC ~$0.20/swap, Base ~$0.02/swap, Arbitrum ~$0.20/swap, Polygon ~$0.02/swap
- Slippage real (quote vs execução): tipicamente 5-30 bps em L2s
- Fee do agregador: OpenOcean 0.2%, Paraswap 0.15%, LiFi 0%

Para BSC (controle): roundtrip = -2 bps + gas $0.40 = **net negativo**.
Para Base (falso positivo): roundtrip = +35 bps em quote, mas slippage real ~20-30 bps
+ gas $0.04 = **net ~0 a +5 bps, dentro do ruído**.

## Conclusão

**D6: SEM EDGE.** O padrão se repete:

1. **Spreads entre agregadores existem** (20-450 bps em chains menos líquidas), mas são
   **artefatos de quote APIs indicativas**, não preços executáveis
2. **O mercado real (BSC, mais líquido) mostra roundtrip negativo** (-1 a -3 bps),
   confirmando que não há arb livre
3. **"Arb" aparente em Base/Arbitrum** é inconsistência interna da quote API do
   Paraswap (otimista em ambos os lados), não uma ineficiência de mercado
4. **Polygon WMATIC** é stale quote do OpenOcean (400+ bps é irreal)

**Lição central:** Assim como Jupiter em Solana (9 bps gap CEX-DEX), os agregadores
EVM já capturam ineficiências de roteamento. O que parece ser spread entre agregadores
é na verdade diferença na precisão/otimismo da quote API, não uma oportunidade de arb.
A execução real sempre converge para o preço do pool mais líquido, que é o mesmo que
todos os agregadores eventualmente encontram.

## Comparação com Solana DEX arb (D5)

| Métrica | Solana (Jupiter) | BSC (controle) | Base/Arb/Polygon |
|---------|-----------------|----------------|------------------|
| Spread CEX-DEX | ~9 bps | N/A | N/A |
| Spread cross-agg | N/A (1 aggregator) | 0-5 bps | 20-450 bps |
| Roundtrip real | ~0 bps | -1 a -3 bps | Indeterminado (quote artifacts) |
| Veredito | SEM EDGE | SEM EDGE | SEM EDGE |

## Arquivos

- **Script:** `trading-engine/dex_cross_agg_scan.py`
- **Amostras:** `trading-engine/dex_cross_agg_samples.json`
- **Logs:** `trading-engine/dex_cross_agg_scan.log`
