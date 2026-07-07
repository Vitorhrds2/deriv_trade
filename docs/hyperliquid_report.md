# D55 — Hyperliquid (perp DEX on-chain) vs Binance: funding arb + oracle/mid divergence

**Data:** 2026-07-06
**Status:** VALIDANDO — LINK isolado como candidato forte após walk-forward; ETH/SOL/OP
não sobrevivem custo realista de flip; D55b sem edge de reversão simples
**Autor:** `trading-engine/hyperliquid_probe.py`
**Confiança:** 55% para LINK especificamente (0 flips em 90d, 2 tamanhos de fold, net
+96-100bps, CI95% longe de zero, sobrevive custo de capital a partir de ~3x alavancagem);
~10% para ETH/SOL/OP (sinal real mas custo de flip domina); D55b confirma o mesmo prêmio
estrutural também no LINK (+7.64bps), reforçando que D55a/D55b são o mesmo mecanismo
(reduz um pouco a confiança de que seja "grátis" — pode ser compensação por segurar o
prêmio, não uma ineficiência pura, mas isso não invalida ser capturável na prática)

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

### D55a — Walk-forward multi-janela (ETH, SOL, OP, LINK + todos os 10 pra contexto)

Um único split IS/OOS é fraco (só 1 corte no tempo). Walk-forward de verdade: direção
decidida usando SÓ o fold anterior (sem look-ahead), testada no fold seguinte, deslizando
por todo o período. Duas versões testadas:

1. **Custo cobrado toda semana** (assume fechar/reabrir a posição toda semana): **0/4
   confirmam** — ETH, SOL, LINK, OP todos negativos. Mas isso é uma simulação de
   estratégia ERRADA: pune um sinal estável (que não precisa trocar de lado) exatamente
   igual a um sinal ruidoso (que troca toda hora).
2. **Custo só na entrada/saída/flip de direção** (posição mantida enquanto o sinal não
   virar — a forma correta de simular isso): resultado muda completamente.

| Ativo | Folds 7d | Flips | Win rate | Gross | Custo total | **Net** | CI95% | Veredito |
|---|---|---|---|---|---|---|---|---|
| **LINK** | 13 | **0** | **100%** (12/12) | +115.3bps | 19.0bps | **+96.3bps** | **[+71.6,+121.6]** | **CONFIRMA** |
| ETH | 13 | 4 | 66.7% (8/12) | +35.0bps | 95.0bps | -60.0bps | [-123.9,+0.3] | não confirma |
| SOL | 13 | 3 | 75.0% (9/12) | +31.8bps | 76.0bps | -44.3bps | [-89.6,-2.6] | não confirma |
| OP | 13 | 6 | 50.0% (6/12) | +21.0bps | 133.0bps | -112.0bps | [-235.2,+9.1] | não confirma |

**Robustez (fold de 5d em vez de 7d, todos os 10 ativos):** LINK se mantém idêntico —
**0 flips em 17 transições, 100% win rate, net +99.6bps, CI95%=[+84.4,+115.2]**. Nenhum
outro ativo confirma (ARB chega perto: net +5.9bps mas CI95% cruza zero). BTC, AVAX,
DOGE, SUI, APT — todos negativos líquidos, alguns fortemente (APT: 11 flips, net -295bps).

**LINK é qualitativamente diferente dos outros 3 candidatos**: o sinal nunca precisou
trocar de lado em 90 dias (13-18 folds, 2 tamanhos de fold testados) — ou seja, o funding
da Hyperliquid pro LINK-PERP é consistentemente mais alto que o da Binance, toda semana,
sem exceção. ETH/SOL/OP têm win rate majoritário (50-75%) mas trocam de lado com
frequência suficiente pra que o custo de cada flip (19bps) coma o edge semanal pequeno
(~3-9bps/semana). Direção do trade: **short Hyperliquid LINK-PERP + long Binance
LINK-PERP** (Hyperliquid funding > Binance funding para LINK, persistentemente).

### Custo de capital — sensibilidade por alavancagem (LINK, `capital_cost_sensitivity()`)

O walk-forward acima só debita fees de trading (19bps). Falta custo de capital, que o D9
tratava explicitamente (5% APR T-bill, oportunidade). Diferença chave: D9 era spot+perp
(perna spot exige 100% do notional), D55a é **perp-perp** (as duas pernas só exigem
margem, não notional cheio) — margem não é nettable entre exchanges diferentes, então
capital travado = notional/alavancagem **em cada perna** (2 pernas).

| Alavancagem/perna | Margem (% notional) | Custo capital (84d) | Net-net | Veredito |
|---|---|---|---|---|
| 2x | 100% | 115.1bps | -18.8bps | não sobrevive |
| **3x** | **67%** | **76.7bps** | **+19.6bps** | **sobrevive** |
| 5x | 40% | 46.0bps | +50.2bps | sobrevive |
| 10x | 20% | 23.0bps | +73.3bps | sobrevive |
| 20x | 10% | 11.5bps | +84.8bps | sobrevive |

**LINK sobrevive custo de capital a partir de ~3x de alavancagem por perna** (ambas
Hyperliquid e Binance oferecem >>3x pra LINK, então isso é uma barra baixa/realista, não
uma suposição otimista). Só falha em capital 100%-cash-secured (2x ou menos), cenário que
não reflete como se opera perp-perp na prática. Isso é uma diferença importante vs D9,
que morreu justamente porque exigia capital pleno na perna spot.

### D55b — Divergência oraclePx/markPx/midPx vs Binance

**Atualização (N=10.021, ~8.3h contínuas na AWS, run ainda ativo rumo a 12h):**

| Ativo | basis_mid médio | CI95% | min / max | % positivo | % amostras > custo (9.5bps) | Veredito |
|---|---|---|---|---|---|---|
| BTC | +4.82bps | [+4.79,+4.84] | -10.4 / +18.3bps | 99.8% | 0.26% | sem edge |
| ETH | +8.43bps | [+8.39,+8.47] | -18.5 / +23.5bps | 99.9% | **25.96%** | limítrofe, ver nota |
| SOL | +4.32bps | [+4.28,+4.37] | -23.3 / +17.0bps | 98.7% | 1.39% | sem edge |
| **LINK** (N=100, ~5min local) | **+7.64bps** | [+7.36,+7.92] | até 12.8bps abs | ~100% | 9.0% | sem edge, mas confirma mecanismo |

**LINK checado especificamente (motivado pelo resultado do D55a):** mesmo padrão dos
outros 3 — basis positivo, quase nunca cruza zero, perto mas abaixo do limiar de 10% de
amostras acima do custo. **Isso reforça a hipótese de que D55a (funding) e D55b
(basis) são o MESMO mecanismo**: o LINK-PERP da Hyperliquid negocia estruturalmente acima
do preço da Binance, o que empurra o funding da HL pra cima (compensando quem fica short)
— exatamente a direção do trade que o D55a encontrou. Amostra pequena (5min, N=100,
local) comparada às 8.3h dos outros 3; suficiente só para confirmar a direção/ordem de
grandeza, não para conclusão estatística forte isolada.

(Amostra inicial de 5min/N=100 já apontava a mesma direção: BTC +4.00, ETH +8.40,
SOL +4.45bps — números praticamente idênticos com 100x mais dados, o que já era um
indício forte de que não era ruído de curto prazo.)

Com amostra grande fica claro: o basis **não cruza zero** (98.7-99.9% das amostras do
mesmo sinal) — não é divergência tipo "livro desatualizado" que reverte, é um **prêmio
estrutural persistente** do midPx da HL sobre o mid da Binance. Isso é economicamente
consistente com o próprio mecanismo de funding da HL: `markPx` da Hyperliquid é uma EMA
do prêmio do livro sobre o `oraclePx`, e é esse prêmio que alimenta o `funding` pago/
recebido (D55a) — **o basis do D55b e o funding do D55a provavelmente são duas medidas
do MESMO fenômeno subjacente**, não dois edges independentes e empilháveis. Isso é
especialmente visível no ETH: é o ativo com o prêmio mais alto no D55b (+8.43bps, mais
perto do custo) **e também um dos 4 que sobreviveram o IS/OOS no D55a** — não é coincidência.

Um prêmio constante por si só não é capturável via reversão simples (comprar
Binance/vender HL uma vez não gera lucro recorrente, só captura o prêmio na entrada,
uma única vez). O que teria alguma chance seria uma estratégia de reversão **em torno
da média não-zero** (entrar quando o prêmio foge muito acima/abaixo dos +8.4bps do ETH,
apostando que volta pra média) — isso explicaria os 26% de amostras do ETH acima do
custo, mas **não foi testado como regra de entrada/saída de verdade**, só caracterizada
a distribuição. Não tratar como sinal até um backtest de uma regra específica.

## Veredito preliminar

**D55a: LINK é um sinal robusto; ETH/SOL/OP NÃO sobrevivem validação rigorosa.** O split
IS/OOS único tinha sugerido 4 candidatos (ETH, SOL, OP, LINK), mas o walk-forward
multi-janela (com custo modelado corretamente — só em entrada/saída/flip, não toda
semana) derruba 3 dos 4: ETH, SOL e OP têm sinal real (win rate 50-75%) mas ele é pequeno
demais e o sinal troca de lado com frequência suficiente pra que os custos de flip
dominem. **Só LINK sobrevive**, e sobrevive de forma robusta: 0 flips em 90 dias
(testado com fold de 7d E 5d, mesmo resultado), 100% win rate, net +96-100bps, CI95%
bem longe de zero. Isso é qualitativamente diferente do colapso total do D9 (0/19) —
é um sinal único, limpo, específico de um ativo, sobrevivendo dois tamanhos de fold
diferentes sem look-ahead. **Custo de capital testado (novo):** sobrevive a partir de
~3x de alavancagem por perna (net-net +19.6 a +84.8bps entre 3x-20x); só morre em
capital 100%-cash-secured (≤2x), cenário que não reflete como se opera perp-perp na
prática — diferença importante vs D9, que exigia capital pleno na perna spot e por
isso não sobrevivia nem com números brutos maiores. **D55b checado especificamente
para LINK (novo):** mesmo prêmio estrutural positivo dos outros 3 ativos (+7.64bps,
9% das amostras > custo) — reforça que D55a e D55b são o mesmo mecanismo. (Alinhamento
hourly-HL vs 8h-Binance já é tratado corretamente por `_compute_diffs_with_ts`: soma as
janelas hourly da HL estritamente dentro de `(bn_time - 8h, bn_time]` pra cada timestamp
de funding da Binance — não é um risco de viés nas bordas.) Ainda falta: (a) walk-forward
é só sobre os mesmos 90 dias já vistos no screening — ainda não é OOS no sentido temporal
(dados novos, futuros) — só é uma validação de robustez interna mais forte que 1 split;
(b) D55b do LINK rodou só 5min localmente (N=100) vs 8.3h dos outros — direção
confirmada, mas vale rodar mais tempo se for usado como confirmação independente forte.

**D55b: sem edge de reversão simples, confirmado com N=10.021 (~8.3h).** O prêmio é
estrutural (98.7-99.9% das amostras do mesmo sinal, não oscila em torno de zero) e
provavelmente é o mesmo mecanismo que gera o funding do D55a, não um segundo edge
independente. ETH é o caso mais próximo do custo (26% das amostras > 9.5bps) mas isso
não foi testado como estratégia real — só caracterização de distribuição. Deixar o run
chegar em 12h para o registro, mas a conclusão qualitativa já não deve mudar.

## Próximos passos

1. ~~Deixar `hyperliquid_probe.py --mode divergence` rodando na AWS e reavaliar D55b com
   N maior~~ — feito, N=10.021 confirma prêmio estrutural, sem edge de reversão simples.
2. ~~Walk-forward multi-janela em D55a para ETH/SOL/OP/LINK especificamente~~ — feito,
   2 tamanhos de fold (7d, 5d). Só LINK sobrevive (0 flips, 100% win rate, net +96-100bps).
3. ~~Checar se o prêmio D55b também é visível especificamente no LINK~~ — feito (local,
   N=100, +7.64bps, mesmo padrão dos outros 3), confirma mecanismo compartilhado.
4. ~~Custo de capital/margem~~ — feito (`capital_cost_sensitivity()`), LINK sobrevive a
   partir de ~3x de alavancagem por perna.
5. Considerar paper-trade ao vivo do LINK especificamente (análogo ao D34/D36) antes de
   qualquer capital real — este ecossistema já tem infra de guardrails/telegram pronta
   (`risk_guardrails.py`, `telegram_alerts.py`) que pode ser reaproveitada.

## Arquivos

- **Script:** `trading-engine/hyperliquid_probe.py`
- **Resultados D55a:** `trading-engine/hyperliquid_funding_arb_results.json`
- **Log/dados D55b (AWS):** `trading-engine/hyperliquid_divergence.log`,
  `trading-engine/hyperliquid_divergence_results.jsonl`
