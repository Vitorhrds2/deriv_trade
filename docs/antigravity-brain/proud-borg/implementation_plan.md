# Calibração Agressiva: V6.2 (Ultra-Momentum)

Como você quer colocar fogo no parquinho e testar o limite da estratégia na Conta Demo amanhã, precisamos transformar o nosso "Sniper" paciente em uma "Metralhadora" estatística.

A ideia aqui é explorar o fato de que a nossa assimetria de Risco/Retorno (ganhar muito e perder pouco) permite que a gente erre a maioria das trades, contanto que o volume de acertos pague a conta.

## ⚠️ User Review Required

Esta calibração aumentará drasticamente o número de operações diárias. O robô vai entrar em muitos "falsos rompimentos" e tomará vários *Stop Losses* seguidos. O objetivo é que 1 vitória cubra de 3 a 4 derrotas curtas.

## 🛠️ Proposed Changes

### [MODIFY] `hft_arbitrage_bot.py`

Vamos ajustar três alavancas fundamentais no código:

1. **Gatilho de Entrada (Threshold):**
   - **De:** `55.00`
   - **Para:** `45.00`
   - *Por quê?* Isso vai triplicar a frequência de operações. O bot vai atirar em qualquer sobressalto moderado do Bitcoin, capturando o início de tendências que o filtro anterior ignorava.

2. **Stop Loss (Risco):**
   - **De:** `-35%` (`-$3.50`)
   - **Para:** `-25%` (`-$2.50`)
   - *Por quê?* Como vamos entrar em muito mais "ruído" (mercado lateral), precisamos de uma coleira curtíssima. Se o preço pular e não engatar uma tendência forte imediatamente, nós pulamos fora perdendo o mínimo possível.

3. **Take Profit (Alvo):**
   - **De:** `+60%` (`+$6.00`)
   - **Para:** `+80%` (`+$8.00`)
   - *Por quê?* Quando acertarmos um verdadeiro choque de `> 45.00` que desestabilize a Deriv, vamos espremer o Momentum até o limite. Uma única vitória de `$8.00` paga mais de 3 derrotas de `$2.50`.

## 🧪 Verification Plan

1. Subir a modificação no servidor AWS.
2. Reiniciar o serviço pelo tmux.
3. Deixar rodar ao longo da noite/madrugada asiática (que tem bons picos de volatilidade).
4. Coletar os logs pela manhã para ver se a "Metralhadora" superou o PnL do "Sniper".
