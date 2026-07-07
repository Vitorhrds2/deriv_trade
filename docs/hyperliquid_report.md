# D55 — Hyperliquid (perp DEX on-chain) vs Binance: funding arb + oracle/mid divergence

**Data:** 2026-07-06
**Status:** VALIDANDO (sinal parcial em D55a, precisa mais rigor antes de considerar live)
**Autor:** `trading-engine/hyperliquid_probe.py`
**Confiança:** 35% (sinal real em 4/10 ativos sobreviveu 1 split IS/OOS; D55b sem edge aparente)

## Contexto

Primeira hipótese em plataforma genuinamente nova desde o fechamento do ecossistema Deriv
(14 produtos, exaustivo) e Polymarket (PA1-PA5). Hyperliquid é um perp DEX on-chain com
microestrutura diferente de qualquer CEX já testado (D7/D8/D9/D32, todos Binance/Bybit/OKX):

- **Construção perp-perp** elimina a perna spot que o D9 (funding CEX-CEX, refutado)
  precisava para hedgear — round-trip cai de 40bps (D9) para ~19bps.
- **oraclePx / markPx / midPx publicados juntos** no mesmo endpoint (`metaAndAssetCtxs`) —
  mecanismo que não existe em CEX puro (lá só há um preço, o do próprio livro).

## Tese

**D55a:** Se a taxa de funding da Hyperliquid diverge persistentemente da Binance para o
mesmo ativo, uma posição perp-perp delta-neutra (long no venue de funding baixo/negativo,
short no de funding alto) captura a diferença, líquida de ~19bps round-trip.

**D55b:** Se `midPx` (preço realmente tradeable no livro da HL) atrasa em relação ao
`oraclePx`/preço da Binance, há uma janela para comprar/vender no livro da HL a um preço
defasado antes da convergência, líquida de ~9.5bps round-trip (1 taker de cada lado).

## Metodologia

- Dados via API pública HL (`https://api.hyperliquid.xyz/info`, sem key) + Binance REST.
- **D55a:** histórico de funding HL (`fundingHistory`, paginado — endpoint devolve no
  máx. 500 registros a partir de `startTime` **pra frente**, não "últimos N até agora";
  sem paginação explícita o resultado fica preso numa janela antiga) vs Binance
  (`fundingRate`, 8h). Funding HL (mais frequente) somado dentro de cada janela de 8h
  alinhada ao timestamp Binance. 90 dias, 10 ativos (BTC, ETH, SOL, ARB, OP, AVAX, LINK,
  DOGE, SUI, APT).
- **Validação IS/OOS:** direção da posição decidida na 1ª metade cronológica (IS),
  testada de verdade só na 2ª metade (OOS) — mesma disciplina usada em D9-validação e
  D17. Sem isso, "net > 0 no período inteiro" tem viés de retrospecto puro (a mesma
  armadilha que fez D9 cair de 14/20 "lucrativos" para 0/19 na validação OOS real).
- **D55b:** polling a cada 3s de `metaAndAssetCtxs` (BTC/ETH/SOL) + `bookTicker` Binance,
  calculando `basis_mid_bps = (hl_mid - binance_mid)/binance_mid × 1e4`. Rodando
  continuamente na AWS (`hyperliquid_divergence.log`, alvo 12h) para acumular amostra
  maior que o teste inicial de 5 min (N=100).

## Resultados

### D55a — Funding rate arb (90 dias, N=270 janelas de 8h/ativo)

| Ativo | Total diff (período inteiro) | Net após custos (retrospecto) | **OOS (direção fixada na IS)** | Veredito |
|---|---|---|---|---|
| BTC | +57.6bps | +38.6bps | **-2.2bps** | OOS não confirma |
| ETH | +67.2bps | +48.2bps | **+11.4bps** (CI95 [+0.13,+0.32]) | **OOS confirma** |
| SOL | +45.0bps | +26.0bps | **+16.9bps** (CI95 [+0.15,+0.38]) | **OOS confirma** |
| ARB | -13.9bps | -5.1bps | -58.6bps | negativo |
| OP | -138.6bps | +119.6bps | **+62.3bps** (CI95 [+0.31,+0.90]) | **OOS confirma** |
| AVAX | +77.0bps | +58.0bps | -22.7bps | OOS não confirma |
| LINK | +129.0bps | +110.0bps | **+42.1bps** (CI95 [+0.37,+0.54]) | **OOS confirma** |
| DOGE | +69.4bps | +50.4bps | -11.7bps | OOS não confirma |
| SUI | -6.5bps | -12.6bps | -49.4bps | negativo |
| APT | -42.7bps | +23.7bps | -15.5bps | OOS não confirma |

**8/10 pareciam lucrativos no período inteiro (mesmo padrão de falso positivo do D9:
14/20 → 4/19). Só 4/10 sobrevivem o split IS/OOS: ETH, SOL, OP, LINK — todos com CI95%
da metade OOS não cruzando zero.**

### D55b — Divergência oraclePx/markPx/midPx vs Binance (5min inicial, N=100, AWS rodando p/ N maior)

| Ativo | basis_mid médio | CI95% | max abs | % amostras > custo (9.5bps) | Veredito |
|---|---|---|---|---|---|
| BTC | +4.00bps | [+3.77,+4.21] | 6.26bps | 0% | sem edge |
| ETH | +8.40bps | [+8.13,+8.67] | 13.01bps | 11% | limítrofe |
| SOL | +4.45bps | [+4.14,+4.75] | 8.36bps | 0% | sem edge |

Basis é **persistente e positivo** (CI apertado ao redor da média, não oscila em torno de
zero) — parece prêmio estrutural (mecanismo de funding da própria HL provavelmente
compensa isso), não ruído mean-reverting explorável. Diferente do que se esperava
(divergência tipo "livro desatualizado"), a HL parece precificar corretamente, só que
com um viés de prêmio persistente. Rodando 12h contínuas na AWS para confirmar com
amostra maior antes de descartar de vez.

## Veredito preliminar

**D55a: sinal real, mas não confirmado o suficiente para live.** 4/10 ativos (ETH, SOL,
OP, LINK) sobreviveram 1 split IS/OOS com magnitude não-trivial (11-62bps líquidos em
~45 dias). Isso é qualitativamente diferente do colapso total do D9 (0/19). Mas 1 split
não é validação robusta — precisa: (a) walk-forward com múltiplas janelas, não um único
corte IS/OOS; (b) considerar custo de capital/margem em ambos os venues (não incluído
ainda, ao contrário do D9 que incluía explicitamente); (c) confirmar que o funding da HL
listado via API reflete o que seria realmente pago/recebido (mecanismo de HL é hourly,
Binance 8h — a soma pode ter erro de alinhamento nas bordas).

**D55b: sem edge aparente até agora**, prêmio parece estrutural/não capturável via
reversão simples. Aguardando amostra maior (rodando na AWS) antes de fechar veredito.

## Próximos passos

1. Deixar `hyperliquid_probe.py --mode divergence` rodando na AWS (12h) e reavaliar D55b
   com N maior.
2. Walk-forward multi-janela em D55a para ETH/SOL/OP/LINK especificamente (não só 1 split).
3. Se sobreviver, considerar paper-trade ao vivo (análogo ao D34/D36) antes de qualquer
   capital real — este ecossistema já tem infra de guardrails/telegram pronta
   (`risk_guardrails.py`, `telegram_alerts.py`) que pode ser reaproveitada.

## Arquivos

- **Script:** `trading-engine/hyperliquid_probe.py`
- **Resultados D55a:** `trading-engine/hyperliquid_funding_arb_results.json`
- **Log/dados D55b (AWS):** `trading-engine/hyperliquid_divergence.log`,
  `trading-engine/hyperliquid_divergence_results.jsonl`
