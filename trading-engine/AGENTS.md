# Regras Invariantes de Engenharia Quantitativa — Trading Engine & D107

Estas regras são obrigatórias para qualquer criação, ajuste ou auditoria de estratégias e simuladores dentro de `trading-engine/`.

## 1. Proibição Estrita de Micro-Scalping Intra-Janela no D107 (`0s–300s`)
- Durante os primeiros 300 segundos de um contrato Multiplier com *Deal Cancellation*, o prêmio do seguro (put option) já foi pago.
- **Invariante:** `in_window_auto_sell` DEVE permanecer `False` por padrão. Nunca configure take-profits ou trailing stops curtos (`<$1.0x` stake) dentro da janela de 5 minutos. A janela de 5m existe exclusivamente para descartar perdedores pelo custo fixo da taxa (`cancel_loser`) e qualificar vencedores para conversão em *perpetual runners* (`1.0x–8.0x` stake).

## 2. Consistência Estrita de Unidades PnL (Net-vs-Net)
- Em contratos com *Deal Cancellation*, `buy_price = stake + cancellation_fee`.
- **Invariante:** Nunca compare `net_pnl` (`bid_price - buy_price`) contra limiares derivados de `gross_pnl` (`bid_price - stake`). Toda lógica de *ratchet*, *trailing stop* ou preservação de capital deve comparar exclusivamente **Lucro Líquido Atual (`net_pnl`) vs. Pico de Lucro Líquido (`peak_net_pnl = max(0.0, peak_gross - cancel_fee)`)**.

## 3. Ratchet Progressivo Perpetual de 4 Níveis (Pós-300s)
- Após cruzar a fronteira de 5 minutos (`held_winner`), as posições devem ter espaço para respirar contra o ruído browniano antes de ativar travas de lucro:
  - **Tier 0 (`peak_net < 1.0x` stake):** Sem trailing stop; stop de preservação relaxado (`0.35 * stake` após `30s`) para suportar retrações normais (como o drawdown de `-85%` superado pelo runner `#19127889519`).
  - **Tier 1 (`1.0x <= peak_net < 2.0x` stake):** Trava piso garantido em `+0.20 * stake` líquido.
  - **Tier 2 (`2.0x <= peak_net < 4.0x` stake):** Trava piso garantido em `+1.00 * stake` líquido (`1x` garantido).
  - **Tier 3 (`4.0x <= peak_net < 8.0x` stake):** Trava piso garantido em `+2.50 * stake` líquido.
  - **Tier 4 (`peak_net >= 8.0x` stake):** Saída no alvo `8.0x` ou trailing stop retendo `80%` do pico.

## 4. Alinhamento Multi-Timeframe Obrigatório (Zero Alternância Cega)
- **Invariante:** É proibido usar alternância mecânica cega (`MULTUP` <-> `MULTDOWN`) ou médias de curtíssimo prazo (`<= 15 ticks`) para definir direção de entrada em tendência.
- Toda entrada direcional e qualificação na fronteira de `285s` deve exigir concordância entre a maré macro (`EMA 30t vs 120t` + regressão linear) e força de tendência (`Wilder ADX(14) >= 20.0` com concordância `+DI / -DI`). Em regime lateral (`ADX < 20`), o bot deve pausar novas compras (`trend_alignment_pause`).

## 5. Conservação de Caixa e Taxas Não-Reembolsáveis em Simuladores
- **Invariante de Backtest:** Em qualquer simulador de Deal Cancellation (`d107_exact_historical_simulation.py`), a taxa `cancellation_fee` é um custo afundado (*sunk cost*) não-reembolsável:
  - No `cancel_loser`: reembolsa `stake` (`terminal_net = -cancellation_fee`).
  - No `close_manual`: recebe `stake + mark` (`terminal_net = mark - cancellation_fee`, jamais `cost + mark`).
  - No `stopout`: recebe `0.0` (`terminal_net = -cost`, jamais reembolsando `cancellation_fee`).
