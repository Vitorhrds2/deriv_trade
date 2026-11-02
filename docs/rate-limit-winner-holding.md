# Hipótese: Rate-Limit Winner Holding

> **Status**: Estudo ativo — descoberta acidental em 15 Jul 2026
> **Origem**: Bots D52/D95 na AWS eu-central-1b
> **Símbolo**: 1HZ10V (principal), 1HZ100V (secundário)
> **Tipo**: Multiplier 400x com deal cancellation 5min

## Descoberta

Rate limiting da API SELL da Deriv impediu o bot de fechar winners. Resultado: losers cancelados (-$0.44 cada), winners ficaram abertos como perpétuos (expiry 2126) acumulando 400x leverage.

### Números (15 Jul 2026, Demo)

- 71 posições abertas: +$1,316.96 unrealized
- 73 fechadas: -$762.12 (todas cancelled losers, 0% WR)
- D52: 767 tentativas, 470 rate-limited, 69 cancelled, 51 sold, 195 expired unsellable
- Bot comprou 162 MULTUP vs 153 MULTDOWN (50/50)
- Sobreviveram: 64 MULTDOWN vs 7 MULTUP (1HZ10V caiu -0.62%)

## Mecanismo

1. Compra MULTUP/MULTDOWN 400x + cancellation 5min ($0.44 fee)
2. Loser aos 5min → cancela → perde $0.44
3. Winner aos 5min → NÃO VENDE → posição perpétua → 400x acumula profit

## Versão Intencional

1. Compra com 400x + cancellation 5min
2. Loss aos 5min → cancela
3. Profit aos 5min → deixa correr (NÃO vende)
4. Trailing stop-loss (fecha se profit cair 50% do pico)
5. Fecha manualmente quando trend reverter

## Variáveis

- Direção: 50/50 vs trend-following
- Stake: $10 vs $1
- Multiplier: 400x
- Cancel timing: 5min Europeia
- Max positions: capital allocation
- Stop-loss: trailing 50% vs fixo vs nenhum
- Símbolo: 1HZ10V (estável) vs 1HZ100V (volátil)

## Guardrails para real

- Stake máximo: $10 por posição
- Max positions simultâneas: 10
- Stop-loss global: 50% do capital deployado
- Capital máximo deployado: 20% do saldo

## Backtest (15 Jul 2026, 1000 candles 1min, 1HZ10V)

Mercado: 9467.99 → 9391.25 (-0.811% em ~16h)

| Estratégia | Buys | Cancels | Holds/Sells | Open | Realizado | Unrealizado | NET |
|---|---|---|---|---|---|---|---|
| **Rate-Limit Winner Holding (hold winners)** | 200 | 87 | 113 holds | 113 | -$38.28 | +$412.15 | **+$373.87** |
| Buy and hold | 200 | 0 | 0 | 200 | $0 | +$32.16 | +$32.16 |
| D52 original (sell winners) | 200 | 87 | 113 sells | 0 | +$91.32 | $0 | +$91.32 |

**Rate-Limit Winner Holding é 4x mais rentável que buy-and-hold e 4x mais que D52 original.**

### Análise do backtest

- Rate-Limit Winner Holding cancelou 87 losers (-$38.28 em fees) e segurou 113 winners
- Os 113 winners acumularam +$412.15 em unrealized profit com 400x leverage
- D52 original vendeu os 113 winners imediatamente (+$91.32 realizado) — matou o upside
- Buy and hold não cancelou losers, então 200 posições ficaram abertas mas só +$32.16 net (losers diluíram winners)
- **O segredo do Rate-Limit Winner Holding**: cancelar losers limita downside a $0.44, enquanto segur winners permite 400x amplificação

## Histórico da conversa original

Ver arquivo: `docs/Conversation-post-rate-limiting-error-verification.md` (3 turnos de conversa User/Devin que levaram à descoberta)
