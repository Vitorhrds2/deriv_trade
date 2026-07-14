# Estado da Pesquisa — Consolidado (2026-07-04)

**Propósito:** fonte única de verdade sobre todas as hipóteses de edge já testadas neste
repositório, seu veredito, e o que ainda está em aberto. Consolidado após o merge de
`feat/synthetic-anomaly-monitor` em `main` (commit `9cf907e`) trazer de volta várias frentes
de pesquisa paralelas. Atualizar esta tabela sempre que uma hipótese nova fechar veredito.

## TL;DR

**83 hipóteses testadas. 75 refutadas (D76 early-sell+signal REFUTADO 2026-07-11 3/3 CI cruza zero, D77 untested contract types REFUTADO 2026-07-11 PUTE WR=70% run1 era viés, WR=45% run2, D86 straddle arb REFUTADO 2026-07-11 0/330 spread=-$0.08, D81 buy limit REFUTADO 2026-07-11 100% rejeitado, D80 weekend vol REFUTADO 2026-07-11 RNG constante 1.03x, D75 tick spectral analysis REFUTADO 2026-07-11 Hurst=0.65 mas autocorr max=0.05, D74 proposal expiry REFUTADO 2026-07-11 entry sempre T+1, D73 lookback REFUTADO 2026-07-11 produto nao existe, D72 early-sell t130 REFUTADO 2026-07-11 sell EV=-$0.037 vs hold EV=+$0.248 diff=-$0.285 falso-positivo D71, D67 cross-duration info edge REFUTADO como artefato matematico 2026-07-11 P(10t|5t WON)=0.867 mas overlap de ticks, D68 tick arrival jitter REFUTADO 2026-07-11 server epoch 1.000s ± 0, D70 multi-contract entry spot REFUTADO 2026-07-11 20/20 diferentes mas nao previsivel, D63 duration non-linearity REFUTADO 2026-07-11 payout 1.920 constante em 1200 proposals, D64 entry spot timing REFUTADO 2026-07-11 3/3 bidirecional nao sistematico, D65 touch/notouch barrier REFUTADO 2026-07-11 barrier=None mesmo padrao D62, D66 tick count settlement REFUTADO 2026-07-11 3/3 tick_count exato, D59 POC subscription vs poll REFUTADO 2026-07-11 30/30 SUB nunca notificou, D60 tick gap REFUTADO 2026-07-11 626 ticks 0.80% missing apenas startup, D61 reconnection state REFUTADO 2026-07-11 0/13 barrier mismatches, D62 barrier rounding REFUTADO 2026-07-11 253/253 barrier=None CALL/PUT, D56 cross-symbol correlation REFUTADO 2026-07-11 N=2081 ticks 0/36 pares significativos, D57 stake non-linearity CONFIRMADO mas nao exploitavel 2026-07-11 payout ratio 1.886 em $0.35 vs 1.923 em $100, D58 sell limit order REFUTADO 2026-07-11 50/50 sells rejeitados 'Resale not offered' — CORRIGIDO por D69: sell funciona em duracoes > tick, D40 stablecoin mint REFUTADO 2026-07-10 WR=0% 24h, D44 funding extremo REFUTADO 2026-07-10 IC95% negativo, D52 deal cancellation REFUTADO 2026-07-09 N=120 EV encolhendo monotonicamente, D41 wash trading REFUTADO por fees 2026-07-08 WR 66% mas EV < 10bps), 2 com sinal fraco/marginal (D13, D14), 1 com edge validado (D17 — token unlock short, POSIÇÃO AO VIVO APTUSDT desde 2026-07-09), 1 com edge parcialmente confirmado (D36 — IV surface BUY side, N=58 WR RECUPEROU para 41.4%, total=+$2,948, pode não ser falso-positivo), 2 aguardando eventos (D34 — liquidation cascade, D39 — max pain), 3 em validação inicial (D37, D38, D55). **D69 (Long-Duration Resale) DESCOBERTA: sell funciona em 12/12 duracoes 1m-1d.** **D71 (Early-Sell Real Probe) EDGE ENCONTRADO: threshold 1.50 diff=+$0.681 CI95%[+$0.318,+$1.063] N=30 — sell no bid >= 1.50x buy tem EV positivo vs hold.** D46 (Deriv tick mean-reversion) **REFUTADO em 2026-07-06 com N=190.000**. **D47-D68, D70 todos REFUTADOS.** **D55 (Hyperliquid vs Binance) paper trading OOS ativo desde 2026-07-08, LINK como único candidato.**
O padrão se repete de forma notável: quando existe algum micro-sinal real (H1, H3, T4, PA5, D33, D35), ele é
**sempre menor que o custo de transação** (comissão/spread). Quando não há sinal real, a causa é
**margem da casa embutida no payout**, matematicamente presente em todo contrato testado (dígitos,
touch/no-touch, range, vanillas, accumulators, jump indices, multipliers, higher/lower, tickhigh,
runs, asian, reset, turbos). Nenhuma hipótese sobreviveu a controle nulo + IC95% + segunda fonte
independente, exceto D17 (edge validado) e D36 (anomalias reverting, aguardando P&L).

**Todos os 14 produtos Deriv ativos na API estão agora exaustivamente testados e refutados,**
**incluindo tick-level (D46, N=190.000, 2026-07-06).** O ecossistema Deriv está fechado para
mispricing de produtos. O Polymarket também está fechado (PA1-PA5 todos refutados). As frentes
**ainda em aberto** são: D17 (token unlock, bot em paper), D34 (liquidation cascade, loop contínuo
na AWS), D36 (IV surface anomaly, paper bot ativo na AWS), D44 (funding rate extremo, aguardando
evento) e **D55 (Hyperliquid vs Binance, primeira plataforma nova pós-Deriv/Polymarket — ver
item 36)**. **Early sell optionality — CORRIGIDO E RE-REFUTADO (2026-07-07, ver item 14).** A
"confirmação" original (N=50) e a extensão multi-símbolo (N=550, 10 símbolos) usavam um
critério de venda com viés de hindsight (melhor bid observado em TODA a vida do contrato,
um limite superior trivialmente positivo pra qualquer preço com ruído, não uma estratégia
acionável) — quando testado com a regra non-hindsight correta (vender no 1º bid≥threshold,
comparado par-a-par contra hold, não só a média condicional-a-disparar), o diff de EV cruza
zero em 7/8 thresholds e é **significativamente NEGATIVO** no 8º. **Quatro hipóteses de
execução/plataforma (D47-D50: stale proposal buy race, accumulator tick-barrier race,
app_id/canal pricing arbitrage, multiplier stop-out slippage) também foram testadas e
refutadas em 2026-07-06** — nenhum bug de execução, race condition ou segmentação de canal
se mostrou explorável (detalhes na tabela abaixo e itens 28-31 da Recomendação).

**Auditoria completa dos 13 processos ativos na AWS em 2026-07-10:**
`hft_bot` reconfirmado negativo e parado. `d41_wash` REFUTADO por fees (WR 66% real mas EV < 10bps). `d40_stable` REFUTADO e parado (WR=0% 24h). `d44_funding` REFUTADO e parado (IC95% negativo). `d52_live` REFUTADO e parado (N=120, EV encolhendo). `D36` mostrando RECUPERAÇÃO inesperada (WR 35.4%@N48 → 41.4%@N58, total=+$2,948) — pode não ser falso-positivo. `basis_paper_bot.py` (D29) continua INCONCLUSIVO (WR 72.7% mas EV cruza zero). `D17` com POSIÇÃO AO VIVO (APTUSDT short desde 2026-07-09, exit 2026-07-12). `D55` paper trading OOS ativo (LINK funding arb).

## Hipóteses refutadas — sem edge (margem da casa embutida no payout)

| # | Hipótese | Produto | Relatório | Achado central |
|---|---|---|---|---|
| 1 | Oráculo Dinâmico (DIGITDIFF + Virtual Loss) | Deriv sintéticos | `docs/edge_investigation_report.md` | IC95% real abaixo do break-even; todos os 46 contratos testados têm EV negativo |
| 2 | Accumulators (ACCU) | Deriv sintéticos | `docs/accumulator_edge_report.md` | Falso positivo de amostra pequena capturado; com 5.000 ticks reais, EV negativo em toda grade growth_rate×N |
| 3 | Jump Indices (JD10-100) — direção e timing | Deriv sintéticos | `docs/jump_index_report.md` | Direção 50/50 confirmada; timing memoryless confirmado; sinal candidato (92.9% UP) era fluke de N=14, sumiu em N=50 |
| 4 | Vanilla Options — mispricing vs. valor justo | Deriv sintéticos | `docs/vanilla_options_report.md` | 17/17 células com EV<0; margem cresce com grau de OTM, exatamente como precificação padrão de opções |
| 5 | T2 — SPIKE_TIMING (Boom/Crash) | Deriv sintéticos | `docs/t2_boom_crash_spike_timing_report.md` | Intervalo entre spikes consistente com processo memoryless |
| 6 | T3 — Valor-relativo em exóticos/barreira | Deriv sintéticos | `trading-engine/docs/t3_exotic_value_report.md` | 0 células com `EV_lo>0`; "edges" do scan ingênuo eram drift de amostra + N baixo |
| 7 | HIGHER/LOWER — barrier mispricing | Deriv sintéticos | `higher_lower_edge_scan.py` | 0/31 células com EV_lo>0; house margin 0.2-10% |
| 8 | Multipliers (MULTUP/MULTDOWN) — mispricing standalone | Deriv sintéticos | `multiplier_edge_scan.py` | 0/30 células com EV_lo>0; MC payoff≈$0 (martingale), EV=-comissão ($0.44-$7.61) |
| 9 | Cross-symbol arbitrage — RNG independence | Deriv sintéticos | `cross_symbol_arb_test.py` | Correlação ~0, VR ~1.0; RNGs independentes |
| 10 | Entry Spot Lag — reuso de tick T0 | Deriv sintéticos | `docs/entry_spot_lag_report.md` | 0/75 trials com mesmo epoch; regra T+1 confirmada |
| 11 | Direction Bias — viés direcional em 1 tick | Deriv sintéticos | `tick_direction_bias_test.py` | 200 trials randomizados: WR 52.5%, IC95% cruza breakeven |
| 17 | DEX arb — Jupiter (Solana) vs Binance CEX + triangular | Solana DEX / Binance | `docs/dex_arb_report.md` | CEX-DEX: 0/199 amostras positivas, Jupiter sempre ~9bps abaixo de Binance. Triangular: roundtrip ~0bps (máx +7.9bps), threshold ~50bps. Agregador já captura ineficiências |
| 18 | PA1-PA4 Polymarket — new market snipe + cross-market + multi-outcome arb + near-resolution | Polymarket (todos os mercados ativos) | `docs/polymarket_pa1_pa4_report.md` | PA3: 940 mercados, min sum(asks)=$1.001, 0 arb. PA2: 10 pares 5m/15m, diff=0.0bps. PA1: 24 novos mercados, spread=100bps desde age=37s. PA4: mecanismo já refutado pelo PA5 (N=1838) |
| 19 | D6 — Cross-aggregator DEX arb (EVM: BSC, Base, Arbitrum, Polygon) | OpenOcean vs Paraswap vs LiFi | `docs/dex_cross_agg_report.md` | BSC (controle): spread 0-5bps, roundtrip -1 a -3bps. Base/Arb: spread 20-165bps mas roundtrip positivo é artefato de quote API indicativa. Polygon: 450bps spread é stale quote. 160 observações, 5 ciclos |
| 20 | D7 — CEX-CEX arbitrage (Binance vs Bybit vs OKX) | CEX spot | `docs/cex_arb_report.md` | 100 observações, gross 0-4bps, net -16 a -26bps, 0/100 positivos. Market makers cross-exchange comprimem spread a zero |
| 21 | D8 — Triangular arbitrage (Binance) | CEX spot | `docs/cex_arb_report.md` | 120 observações, gross -10bps médio, net -28 a -98bps, 0/120 positivos. Spread bid-ask em cada leg consome qualquer ineficiência |
| 22 | D9 — Funding rate carry trade (Binance/Bybit/OKX perps) | CEX perps | `docs/cex_arb_report.md` | Scan inicial: 14/20 "lucrativos" (viés de amostra curta ~11 dias). Validação 30d: apenas 4/19, 0% das janelas 7d lucrativas. Fees 40bps + capital cost 42bps consomem funding |
| 23 | D10 — DeFi liquidation monitor (Aave V3) | DeFi (Base) | `docs/defi_liquidation_report.md` | 108 eventos em 10.6 dias na Base. Bonus médio 7.8%. Mas 95% dos eventos têm debt <$4. Latência 30-60s vs <12s bots MEV. Capture rate retail <1%. Sem edge sem infra profissional |
| 24 | D11 — Options IV mispricing (Deribit BTC/ETH) | Deribit options | `docs/options_stat_arb_report.md` | VRP negativo (-8.2% BTC, -8.8% ETH): IV < RV. Mas theta decay + delta hedging costs + bid-ask spreads consomem edge. Sem edge sem infra de vol trading profissional |
| 25 | D12 — Statistical arbitrage (crypto pairs trading) | Binance spot | `docs/options_stat_arb_report.md` | 76/190 pares cointegrados (40%). Backtest OOS: 7/10 pares negativos após 40bps fees. avg PnL=-278bps, avg Sharpe=-0.26. Cointegração existe mas edge < custos |
| 26 | D13 — Funding rate como signal direcional | Binance futures | `docs/funding_trend_report.md` | Short side (funding positivo → vender) tem WR 37-43% em 72h. Long side não funciona (WR 0-12%). Sharpe 5.4 BTC mas WR 26%. Sinal assimétrico e fraco, melhor como filtro complementar |
| 27 | D14 — BTC trend following (momentum multi-dia) | Binance spot | `docs/funding_trend_report.md` | SMA(10/50) long+short: Sharpe OOS 1.16 BTC, 1.40 ETH. Beat buy & hold em risk-adjusted. MAS N=7 trades OOS (não significativo). Long-only não replica OOS. Marginal |
| 28 | D15 — Combined funding filter + trend following | Binance spot+futures | `docs/combined_cvd_report.md` | Funding filter PIORA trend following: delta Sharpe -0.27 BTC, -0.45 ETH, -0.80 SOL. Filtro remove trades bons. Combinação não funciona |
| 29 | D16 — CVD / order flow signal | Binance spot (1h) | `docs/combined_cvd_report.md` | Sharpe 10+ OOS mas N=6-12 e 27+ configs testados = overfitting. CVD divergence WR 67-75% promissor mas inconclusivo. Precisa mais dados |
| 30 | D16v2 — CVD rigorous re-test (5k candles, k-fold, Bonferroni) | Binance spot (1h, 5000 candles) | `docs/cvd_v2_report.md` | REFUTADO. 5-fold CV + permutation test + Bonferroni (α=0.0019). Nenhum config significativo. ETH diverge_96h_48h WR 76% mas p=0.107. Sharpe 10+ do v1 era artefato de annualization |
| 31 | D17 — Token unlock impact (short pré-unlock) | Binance spot (10 tokens, 167 eventos: 119 IS + 48 OOS) | `docs/event_driven_report.md` | **SINAL VALIDADO OOS** — Short 3d antes/3d depois: IS WR 61% avg +285bps t=2.66, OOS WR 79% avg +660bps t=5.43. Edge MAIS FORTE em 2025. Large unlocks (≥$200M): 7/7 negativos, -19.2% excess 30d. Primeiro edge real em 36 hipóteses |
| 32 | D18 — Binance listing announcement impact | Binance spot+futures (43 listings) | `docs/event_driven_report.md` | REFUTADO. Buy at listing: WR 23%, avg +32bps (1d), t-stat=0.29. 30d excess=-15.3% (t=-3.34). Listings são "sell the news" — tokens caem após listing |
| 33 | D32 — Cross-exchange latency arbitrage (Binance vs Bybit/OKX) | CEX perps (REST API) | `docs/latency_arb_report.md` | REFUTADO. 1200+ samples, divergência máx 0.02% vs 0.2% fees (10x menor). REST ~2.5s/sample (não 100ms). Não há leader consistente. Latency arb é jogo institucional (co-location sub-ms, WebSocket/FIX) |
| 34 | D33 — Order book imbalance alpha (predict next-tick) | Binance spot (1s polling) | `docs/order_book_imbalance_report.md` | REFUTADO. 2400+ signals, WR direcional 62.5% em 10s MAS 0 wins após fees (100% negativo). Movimentos de preço < 0.1% fee em 10s. Precisaria WebSocket L2 + maker orders |
| 35 | D35 — Funding rate prediction (momentum + premium) | Binance futures (20 perps, 30d) | `docs/funding_prediction_report.md` | REFUTADO. Momentum direction WR 87.3% (N=1269) MAS Profitable WR 11.7%. EV -$0.43/trade, annualized -47.3%. Funding rates太小 vs 0.08% fees. Exceções (LABUSDT, SLXUSDT) são outliers illiquid |

## Hipóteses com sinal fraco/marginal (não refutadas, não confirmadas)

| # | Hipótese | Produto | Relatório | Achado central |
|---|---|---|---|---|
| 12 | H1 — Momentum pós-choque | Binance BTC → Deriv multiplicador | `docs/h1_momentum_report.md` | Edge bruto real (~0.013-0.022%) mas comissão Deriv (~0.026%/lado) é maior. Custo > sinal |
| 13 | H3 — Latência cross-venue (Deriv×Binance) | arbitragem de latência | `docs/h3_latency_arb_report.md` | **Definitivo mesmo co-locado em AWS Tóquio**: reagir mais rápido capturou MENOS edge (217ms vs 450ms de casa); `aligned-anti` IC95% cruza zero; custo ~489x a captura |
| 14 | T4 — Viés direcional pós-choque, horizonte longo | Binance BTC, 7 dias OOS | `trading-engine/docs/t4_long_horizon_report.md` | Nenhuma das 24 células (momentum nem fade) sobrevive a controle nulo + custo |
| 15 | `hft_bot` V6.2 (produção) — implementação ao vivo de H3 | Deriv `cryBTCUSD` sintético | `docs/hft_v62_audit_report.md` | N=40, WR 22.5%, EV/trade -$3.02, IC95% [-4.70,-1.18] não cruza zero. Pior de 6 configs testadas. **Reconfirmado 2026-07-08** via `audit_hft_trades.py` (trades reais dedup por contract_id): todas versões N=34, WR 23.5%, EV -$3.35 IC95%[-5.35,-1.21]; subset V6.2-por-parâmetro N=12, WR 8.3%, EV -$3.62 IC95%[-6.01,-0.81] — ambos negativos e estatisticamente significativos, não mais "inconclusivo por N baixo" |
| 16 | PA5 — Polymarket stale-book arbitrage | Polymarket BTC 5-15min | `pa5_collector.py` | N=1838, aligned WR=88.5% mas PnL=-$0.031; diff aligned-anti=-$0.037 IC95%[-$0.060,-$0.014] não cruza zero. Livro NÃO está stale |

**Implicação direta para o `hft_bot`:** ele é a hipótese H3 rodando em produção. O item 13 (H3
co-locado) já fechou essa pergunta com muito mais rigor (profundidade executável, A/B decisivo,
teste barato em Tóquio) do que o shadow A/B do bot consegue com seu N pequeno e sem co-locação.
Ver "Estado ao vivo — Shadow A/B do hft_bot" abaixo para o estado atual dele.

## Estado ao vivo — Shadow A/B do hft_bot (checado 2026-07-02 ~13:56 UTC — veredito fechado)

- **Código de Shadow A/B (`SHADOW_AB_ANTI_PROB`, `Grupo: ALIGNED/ANTI`) está deployado no servidor**
  (`hft_arbitrage_bot.py` ao vivo no EC2), mas **zero trade fechou desde que esse código entrou** —
  0 ALIGNED, 0 ANTI registrados até agora. Números antigos ("32 ALIGNED / 0 ANTI") são de ANTES
  desse deploy e não refletem mais o estado atual.
- **Seca de gatilho de 24h+**: último `GATILHO ACIONADO` real em `2026-07-01 13:59:36 UTC` (log
  mostra `10:59:36` em GMT-3). Zero gatilhos desde então, atravessando 3 restarts (queda de WS —
  todos por `Authenticated WebSocket died! Crashing bot to force restart...`, comportamento
  intencional do supervisor, não um bug novo) e a janela inteira de golden hour de 01/07.
- **Rajada de `👀 falhou no gate de timing` (40x às 09:30:07 UTC de hoje) era 1 evento só, não 40
  independentes** — todos os 40 logs caem numa janela de 55ms reais (mesmo `t_0`/`t_next_tick`),
  amostra ruim pra julgar o gate.
- **Teste decisivo — `passive_trigger_probe.py` rodado 1h inteira dentro da golden hour de hoje
  (12:56-13:56 UTC), contagem debounced (1 evento por janela de 50ms) e independente do bot em
  produção:**

  | threshold | formed (1h) | timing_eligible | taxa elegibilidade |
  |---|---|---|---|
  | ≥$5 | 867 | 268 | 30.9% |
  | ≥$10 | 163 | 57 | 35.0% |
  | ≥$15 | 49 | 16 | 32.7% |
  | ≥$30 | 6 | 2 | 33.3% |
  | ≥$45 (threshold real do bot) | **0** | 0 | n/a |

  **Veredito: gate de timing NÃO está quebrado.** Taxa de elegibilidade fica constante em ~31-35%
  em toda a faixa de thresholds testada — exatamente o previsto pela matemática do gate assumindo
  fase aleatória do choque em relação ao tick de 1Hz da Deriv (~34% teórico com
  `L_DERIV=0.350`/`DERIV_LAG=0.690`). Se o gate estivesse estruturalmente quebrado (ex.: suposição
  errada do período do tick), essa taxa cairia a ~0% em todos os thresholds, não ficaria estável.
  **A causa real da seca é frequência**: decaimento suave e monotônico de 867/h (≥$5) para 0/h
  (≥$45) — mercado genuinamente quieto nesse patamar de choque combinado, não falha de
  instrumentação nem gate mal calibrado.
- **Implicação para ação:** baixar `PRICE_SHOCK_THRESHOLD` aumentaria a frequência de disparo (ex.:
  ~6/h em $30, ~49/h em $15) mas **pioraria o EV**, não melhoraria — H1 (`docs/h1_momentum_report.md`)
  já mostrou que choques menores têm sinal bruto ainda mais fraco, e o próprio `hft_bot` já é a
  configuração testada com pior EV de 6 no audit (item 10 acima). Não há ajuste de parâmetro que
  transforme isso em edge positivo; o veredito de H3/item 10 já fecha essa frente.
- **Conclusão:** pergunta original (bug de filtro vs. mercado quieto) **respondida com dado de 1h,
  golden hour, gate saudável**: é mercado quieto. Não investigar mais o timing gate — não é aqui
  que está o problema.

### Update 2026-07-08 — trades reais existem agora, veredito reconfirmado negativo

O "veredito fechado" acima (2026-07-02, zero trades desde o deploy do shadow A/B) estava
**desatualizado**: `audit_hft_trades.py` re-rodado em 2026-07-08 encontra **32 ALIGNED / 2 ANTI**
trades reais já fechados (bot não foi reiniciado nem tocado, só rodou mais tempo). Resultado por
versão/corte (Wilson + bootstrap CI, dedup por `contract_id`):

| Corte | N | WR | EV/trade | IC95% |
|---|---|---|---|---|
| Todas as versões (V4.0-V6.2) | 34 | 23.5% | -$3.35 | [-$5.35, -$1.21] |
| V6.x (Momentum Rider + Ultra-Momentum) | 25 | 24.0% | -$2.18 | [-$4.54, +$0.40] |
| **V6.2-equivalente por parâmetro** (threshold=45 confirmado empiricamente, desde 2026-06-30) | **12** | **8.3%** | **-$3.62** | **[-$6.01, -$0.81]** |

**As duas leituras mais confiáveis (todas-versões N=34 e V6.2-por-parâmetro N=12) têm IC95%
inteiramente negativo.** Shadow A/B (ALIGNED N=32 vs ANTI N=2): diff=$3.21 IC95%[-$1.83,+$8.29],
cruza zero — sem sinal direcional, e **ambos os grupos são negativos** (ANTI EV=-$6.37),
reconfirmando o diagnóstico do H3/item 13: o problema é custo de execução/timing, não a escolha
de direção. **Veredito mantido: sem edge.**

## Proposto, nunca testado

- **`docs/high_gain_hypotheses.md`** — três hipóteses agressivas (Snowballing com Kelly Criterion,
  High-Frequency Scalping, Martingale Assimétrico) documentadas mas nunca rigorosamente testadas.
  Candidatas apenas se as frentes abaixo também se esgotarem.

## Eixo separado — gestão de risco (não é sobre edge)

- **`docs/batalha_dos_esquadroes.md`** — comparação de 7 esquemas de stake/juros compostos (0%,
  5%, 25%, 50%, 100%) sobre a MESMA estratégia, não sobre se existe sinal. Em andamento (aguardava
  ciclo longo de 5h/10h na última atualização). Achado preliminar: 100% de juros é ruinoso; 25-50%
  parecem o ponto ótimo. Não depende do resultado das hipóteses de edge acima.

## Frentes ativas / em aberto (trabalho do Carlos — `carlosicaro13@gmail.com`)

Estas três NÃO são deste autor de commits (Vitor) e rodam em infraestrutura própria do Carlos
(AWS `ap-northeast-1`, perfil AWS dele) ou em branches ainda não mergeadas. Sem acesso direto às
credenciais/instâncias — o que segue vem só da leitura do código/docs no repo.

### 1. Synthetic Anomaly Monitor (mergeado em `main`, rodando 24/7)
- **Doc:** `docs/synthetic_anomaly_monitor.md` · **Código:** `trading-engine/synthetic_anomaly_monitor.py` (996 linhas)
- Filosofia diferente das 10 hipóteses acima: não testa "sinal estrutural vence custo", **caça
  transiente** — mispricing momentâneo (`EV_EDGE`), viés de RNG, integridade de feed, timing de
  spike. Só alerta com limite inferior de Wilson + persistência por virada de janela (gates
  anti-variância).
- **Status:** instrumento de detecção ativo, **sem achado confirmado reportado até agora** (por
  design só "caça e registra"; virar aposta exige persistência + confirmação ao vivo + sobreviver
  a custo real). Evidência (`logs/anomaly_monitor/anomalies.jsonl`) só existe no servidor AWS do
  Carlos — sem acesso, não dá pra saber se já pegou algum achado sem checar com ele.

**Arquitetura (lido em detalhe 2026-07-02):**
- **5 detectores em paralelo**, a cada `--cycle` (5s default), sobre janela deslizante
  (`--window`, 2000 ticks default) por símbolo: `detect_rng_bias` (qui-quadrado na distribuição
  de dígitos, p=0.001), `detect_runs` (teste de corridas z-score em up/down), `detect_feed`
  (`FEED_FREEZE` = ticks idênticos consecutivos, `FEED_TIMING` = intervalo médio fora do spec),
  `detect_ev` (Wilson lower-bound de win rate × payout ao vivo via `proposal` da API — o "caçador
  de jackpot"), `detect_spike_timing` (cadência de spike Boom/Crash vs. spec documentado).
- **Persistência por turnover** (`streak_confirm`): não basta N ciclos seguidos — exige que uma
  fração da janela (`--persist-turnover`, 50% default) seja de ticks genuinamente NOVOS desde que
  a anomalia apareceu. Mata o caso de janela "presa" (símbolo lento como `R_50` fazendo a mesma
  amostra persistir trivialmente sem ticks novos de verdade).
- **Auto-vet de amostra fresca** (`_vet_ev_edge`): antes de qualquer `EV_EDGE` virar `CRITICAL`,
  busca `--vet-sample` (30.000 default) ticks novos e independentes via `ticks_history` e re-mede
  do zero. Não sobrevive → rebaixa pra `EV_EDGE_REJECTED` (informativo, sem alarme). É a mesma
  disciplina que refutou Accumulators (item 2) e Jump Index (item 3) acima, agora automatizada em
  tempo real.
- **Watchdog separado** (`_watchdog_loop`) pra `FEED_STALL`: detecta o bug histórico de WS caindo
  por ping-timeout que deixava o monitor "vivo mas cego" — silêncio de ticks além de
  `--stall-timeout` (30s default) dispara alarme imediato por símbolo.
- **10 testes de selftest offline** (`--selftest`, sem rede/credenciais) validam cada detector:
  taxa de falso-positivo sob RNG verdadeiramente uniforme, injeção de viés real detectada,
  controle EV (payout justo não dispara) vs. injeção EV (payout desajustado dispara), feed
  freeze/stall, spike controle vs. injeção, persistência por turnover, e o auto-vet (blip uniforme
  rejeitado, viés real sobrevive).

### 2. Polymarket PA1-PA5 (branch `feat/polymarket-arb`, **não mergeada**)
- Aplica a mesma disciplina (Wilson, gates anti-variância, A/B da H3) ao Polymarket.
- **PA1-PA4:** esperado repetir o padrão sub-custo (snipe <7s por bots, execução não-atômica,
  regra de resolução como assassino em cross-venue). Ainda não rodados ao vivo.
- **PA5 ⭐ (mais promissora):** mercados BTC de 5-15min que resolvem por benchmark de preço;
  perto do settlement, o resultado já é quase determinístico via Binance enquanto o livro CLOB
  pode ficar stale — ao contrário da H3, aqui a estrutura favorece quem reage rápido (evidência
  on-chain de wallets com >98% WR). Harness pronto (`polymarket_lag_probe.py`, read-only, paper,
  sem credenciais); já tem um **coletor de 48h com deploy AWS** (`pa5_collector.py`, timer + email
  SNS + auto-stop) **validado ao vivo com 1 janela capturada** (25 paper-trades, outcome=Down) —
  ainda abaixo do N≥30 por grupo que o próprio plano do Carlos define como necessário para veredito
  (`aligned_net>0` **e** IC95% de `aligned-anti` acima de zero).

**Arquitetura PA5 (lido em detalhe 2026-07-02):**
- **`polymarket_lag_probe.py`** (413 linhas) — dois modos: `run_leadlag` (diagnóstico puro, mede
  correlação cruzada entre retornos da Binance e do preço do token "Up" pra ver se o livro da
  Polymarket atrasa a Binance) e `paper_ab_window` (o teste de verdade). Nos últimos `--final-s`
  (30s default) de UMA janela Up/Down: monitora o preço Binance vs. o open da janela; quando
  `|move| >= min_move` (default $5), sorteia 50/50 **aligned** (aposta a favor do movimento já
  ocorrido) vs. **anti** (contra) — a MESMA metodologia A/B da H3/hft_bot — compra (paper) o ask do
  token do lado escolhido, e resolve no fim contra o close da Binance (proxy do Chainlink real).
- **Risco explicitamente sinalizado no próprio código**: Polymarket resolve por **Chainlink**, não
  Binance; a divergência entre os dois (citada no docstring como "H5 na literatura") é ruído/risco
  que esta sonda não resolve, só marca. **Sem execução real por design** — Polymarket exige
  assinatura EIP-712, deliberadamente fora de escopo (paper-only).
- **Estatística**: Wilson CI por grupo (aligned/anti) + `boot_diff_ci` (bootstrap) na diferença
  aligned-anti, com veredito automático (`edge_comprovado` se IC95% lo>0, `aligned_pior` se hi<0,
  `cruza_zero` caso contrário) — mesma disciplina de H1/H3/T4.
- **`pa5_collector.py`** (242 linhas) — orquestra `paper_ab_window` em loop por `--hours` (48h
  default): acha a próxima janela (5m/15m configurável) que fecha com lead suficiente, roda o A/B,
  acumula em JSONL (append idempotente, sobrevive a falhas por janela) e **reconsolida o sumário
  agregado após CADA janela** (pooling de todos os trades aligned/anti até então, mesmo cálculo de
  Wilson+bootstrap, agora sobre a amostra total) — resiliente a interrupção a qualquer momento.
  Escreve corpo de e-mail opcional (liga com o SNS do deploy AWS).
- Ambos com selftest offline (`--selftest`) cobrindo detecção de lag, fórmula de P&L, isolamento
  de edge no A/B sintético, parsing de horizonte, e consolidação de múltiplas janelas.
- Nenhum dado local encontrado (`data/pa5/*.jsonl` não existe neste checkout) — a única evidência
  real (1 janela, 25 trades) está no servidor AWS efêmero do Carlos.

**Coleta independente iniciada por este autor (2026-07-02 13:22 UTC)** — em vez de esperar acesso
à AWS do Carlos, subi `pa5_collector.py`/`polymarket_lag_probe.py`/`polymarket_arb_stats.py` (só
stdlib, sem credenciais) direto no EC2 compartilhado do `hft_bot`, `tmux pa5_collector`, `--hours
48`, sem tocar em nada do bot em produção. Roda até 2026-07-04 13:22 UTC; `data/pa5/summary.json`
reconsolida a cada janela fechada.
- **Checkpoint após 7 janelas (33min):** `aligned` n=21 WR=81.0% pnl_médio=-$0.069 total=-$1.44 |
  `anti` n=36 WR=16.7% pnl_médio=+$0.059 total=+$2.12 | `aligned-anti`=-$0.128/trade, IC95%
  [-0.276,+0.007] → `cruza_zero`. N ainda abaixo de 30/grupo (aligned) — não é veredito.
- **Padrão preliminar notável:** `aligned` acerta MUITO mais (81% vs 17%) — confirma que o sinal de
  momentum de curtíssimo prazo é real (o lado que já se moveu na Binance tende a fechar assim) —
  mas o PnL médio de `aligned` é **negativo**, porque comprar o lado favorito já custa perto de
  `ask≈1`. É o mesmo padrão sub-custo de H1/H3 (sinal real, custo de entrada já embutido no preço)
  — oposto do que a tese PA5 preveria se o livro estivesse realmente "stale". Ainda cedo pra
  descartar (N pequeno, sem IC fechado), mas é o primeiro sinal na direção contrária à tese.
  Reavaliar quando `windows_collected` for grande o suficiente pra N≥30 nos dois grupos.

### 3. `feat/operate-demo-synthetic` (branch **não mergeada**, commits de HOJE 2026-07-02)
- **Mexe diretamente em `trading-engine/hft_arbitrage_bot.py`** (o mesmo arquivo rodando ao vivo
  no EC2): adiciona kill switch (`MAX_DEMO_LOSS_USD`, `MAX_SESSION_TRADES`, estado `halted`) e
  trava de conta DEMO no `main()`. Não conflita linha-a-linha com o log diagnóstico deste autor
  (áreas diferentes da função), mas **precisa ser reconciliada antes do próximo deploy** para não
  perder nem os guardrails do Carlos nem o log diagnóstico.
- **`cloud_shadow_discord_monitor.py`** — tail do `hft_trades.log` com regex sobre linhas
  relevantes (GATILHO, ORDEM, TRADE, KILL SWITCH, Grupo) postando em Discord. Resolveria boa parte
  do problema de "descobrir se saiu um trade ANTI" sem precisar de polling manual da API.
- **`passive_trigger_probe.py`** — replica a MESMA fórmula/constantes do índice sintético
  (`COEFFS`, `INTERCEPT`, `JUMP_FORMATION_WINDOW`, `L_DERIV`, `DERIV_LAG`) só para contar quantos
  choques se formam (`formed`) vs. passam do gate de timing (`timing_eligible`) — **é
  essencialmente a mesma pergunta diagnóstica** resolvida de forma independente por outro caminho
  (ferramenta externa com contadores, em vez do log inline que foi adicionado em `03db97b`).
  Convergência interessante: dois caminhos diferentes chegaram à mesma pergunta no mesmo dia.
- **`strategy_tournament_runner.py`** (lido em detalhe 2026-07-02) — torneio SEQUENCIAL (um
  modelo por vez, não concorrente) de **12 padrões tick-a-tick** em `1HZ100V`/`R_100`/`1HZ10V`:
  `reversal` (fade após streak de N ticks), `trend` (segue o streak), `mean_revert` (volta pra
  média de janela curta de 5-7 ticks). Contratos CALL/PUT de 1 tick de duração.
  - **Gate 30→100**: promove pra fase de 100 trades só se `pnl > 0` E drawdown dentro do limite
    saudável (12.0/30 trades); kill-switch duro em -14.0 a qualquer momento. Backlog com motivo
    de falha (`failed_gate30_pnl_nonpositive`, `failed_gate30_drawdown`, etc.), estado 100%
    persistido e auditável (`strategy_tournament_state.json` + `.jsonl` de eventos).
  - **Já rodou de verdade hoje**: `seed_failed_trend_model` carrega o resultado real de
    `JOB-20260702-003` (`trend_2tick_cooldown30`), que **falhou o gate de 30** (PnL não-positivo)
    — é a origem dos comentários "Pivot from failed 2-tick trend-follow" nos specs dos 12 modelos.
  - **Observação metodológica:** diferente de TODO o resto deste repositório — inclusive do
    `synthetic_anomaly_monitor.py` do mesmo autor no mesmo dia — o critério de promoção não tem
    margem de custo nem teste de significância estatística (sem Wilson CI, sem bootstrap, sem
    controle nulo), só `pnl > 0` bruto em N=30. Como `jump_index_report.md` e
    `t2_boom_crash_spike_timing_report.md` já confirmam que os sintéticos são memoryless
    (direção 50/50, timing sem padrão), existe uma chance real de um modelo passar o gate por
    variância pura — o mesmo padrão do falso-positivo do Accumulators (`DIGITUNDER:4` a 43.7% em
    amostra pequena, ~40% justo em amostra grande).
- **`demo_tick_strategy_runner.py`** (lido em detalhe 2026-07-02) — o protótipo original
  (`JOB-20260702-002`): mesma lógica trend-follow de streak de ticks, mas sem gates/torneio (só
  `max_trades`, `max_demo_loss`, roda até acabar ou bater `max_runtime_seconds`). É a base de onde
  saiu o `JOB-20260702-003` que falhou e virou seed do torneio.
- **`tournament_dashboard.py`** (lido em detalhe 2026-07-02) — visualizador local, stdlib puro
  (`http.server`, sem Flask/dependência), porta 8765 (`127.0.0.1` default). Serve o HTML com
  gráficos (PnL ao longo do tempo, PnL por modelo, distribuição, tabela de pivôs) e dois endpoints
  somente-leitura: `/api/state` (le `strategy_tournament_state.json`) e `/api/events` (tail de
  `strategy_tournament_events.jsonl`). Nenhuma lógica de cálculo extra — só espelha o state file.

**Leitura de código do branch `feat/operate-demo-synthetic` concluída (100% dos arquivos novos).**
Pipeline do dia do Carlos, em ordem: protótipo simples → 1 job real testado e reprovado → torneio
generalizado com gates 30/100 → dashboard de acompanhamento + probe de diagnóstico do hft_bot +
monitor Discord do shadow A/B + guardrails no `hft_arbitrage_bot.py`.

**Nota de coordenação:** três frentes tocando a mesma área (`hft_bot`/shadow-AB) no mesmo dia,
de duas pessoas diferentes, em branches não sincronizadas. Vale alinhar com o Carlos antes do
próximo deploy em `hft_arbitrage_bot.py` para não perder trabalho de nenhum dos dois lados.

## Hipóteses em andamento

| # | Hipótese | Status | Notas |
|---|----------|--------|-------|
| 14 | Early sell optionality | **RE-REFUTADO (2026-07-07) — correção metodológica** | **Bug encontrado:** a métrica usada tanto no teste original (N=50) quanto na extensão multi-símbolo (`early_sell_multi.py`, N=550/10 símbolos) era `sell_profit = max(bid_price observado em TODAS as amostras) - buy_price` — isso é **viés de hindsight**: `max(caminho)` é trivialmente ≥ qualquer ponto fixo do mesmo caminho (incl. o valor terminal/hold), então "sell no melhor bid > hold" é quase uma tautologia matemática pra qualquer preço com ruído, independente de a Deriv ter algum mispricing. A checagem "non-hindsight" secundária (vender no 1º bid≥threshold) tinha um bug relacionado: calculava `EV_sell` só sobre os trials QUE DISPARARAM (condicional, também tautologicamente positivo já que só dispara quando bid>buy_price) e comparava contra um "EV_hold correspondente" que pegava os primeiros N elementos de uma lista por ÍNDICE, não os hold-profits pareados dos MESMOS trials que dispararam — uma comparação inválida. **Correção:** comparação pareada por trial (regra: vende se disparar, senão segura; diff = regra − hold sempre-segura) com bootstrap na diferença. **Resultado corrigido, N=550 (10 símbolos), pooled, 8 thresholds (ratio bid/buy=1.1 a 1.8):** diff EV cruza zero em 7/8 thresholds (ex. ratio=1.3: diff=+0.05bps IC95%[-0.54,+0.65]; ratio=1.5: diff=-0.29 IC95%[-0.71,+0.15]) e é **significativamente NEGATIVO** no ratio=1.8 (diff=-0.20 IC95%[-0.35,-0.01]). Nenhum dos 10 símbolos individualmente mostra IC95% excluindo zero. Interpretação: a regra de venda antecipada AUMENTA o win rate (vender trava lucro pequeno com mais frequência) mas DIMINUI o tamanho médio do ganho (perde os movimentos grandes que só aparecem segurando até o expiry) — os dois efeitos se cancelam, sem EV líquido. Script corrigido (`compute_stream_stats()` agora expõe `diff_ev_vs_hold` pareado, com os campos antigos renomeados p/ `*_HINDSIGHT` deixando claro que não são acionáveis) e redeployado na AWS. Ver `hypotheses-data.ts` (HYP-SELL-01, `status: refuted`) |
| 15 | Synthetic Anomaly Monitor | Rodando 24/7 (Carlos) | Inacessível neste servidor; sem achado confirmado reportado |
| 16 | PA1-PA4 Polymarket | Refutado | PA3: 940 mercados, 0 arb. PA2: diff=0bps. PA1: spread=100bps desde criação. PA4: refutado via PA5 |
| 17 | D17 — Token unlock short | Bot em paper na AWS | Edge validado IS+OOS-2025+OOS-2026. unlock_short_bot.py rodando, primeiro trade APTUSDT 9 Jul. **Tokenomist API integrada (2026-07-08)**: unlock_data.py busca eventos via api.tokenomist.ai com fallback hardcoded. Whitelist de 8 símbolos validados. Próximo: depositar USDT e ir live |
| 18 | D34 — Liquidation cascade | Loop contínuo na AWS | 0 cascades em 30min (mercado calmo). Bot reiniciado em loop infinito. Precisa dias para capturar eventos. **Reconfirmado 2026-07-08**: ainda 0 liquidações/cascades na janela mais recente monitorada (20min+). Framework fee-adjusted pronto, só falta o evento real |
| 19 | D36 — IV surface anomaly | Paper bot ativo na AWS | Backtest BS (histórico): BUY 7/7 wins +$4,500 (100% WR). **Paper trading ao vivo (2026-07-06)**: 7 settled, WR=42.9% (3/7), EV/trade=+$137.52, total=+$962.66, 115 posições abertas — WR ao vivo bem abaixo do backtest, mas EV segue positivo. Amostra pequena, **veredito ainda aberto** — acompanhar mais settles. **Update 2026-07-08**: N=37 settled, WR caiu para **40.5%**, trajetória monotonicamente decrescente (50.0%@N24 → 42.9%@N28 → 41.9%@N31 → 41.2%@N34 → 40.5%@N37). Total ainda positivo (+$1517.90) só por skew de poucos winners grandes; últimos 2 settles foram losses (maior: -$420.94), caindo de um pico de +$2074.76@N35. Mesmo padrão de decaimento que desmascarou o early-sell original — tratar como candidato a falso-positivo, não como confirmação parcial |
| 20 | D37 — Exchange outflow signal | Rodando 13h+ na AWS | 82 checks horários: 78 NO SIGNAL, 3 WEAK LONG, 0 STRONG. Nenhum outflow >$1M detectado ainda. Aguardando evento real para testar a tese preço-pós-outflow. **Update 2026-07-08**: amostra cresceu bastante (~1000 snapshots), maioria ainda NO SIGNAL/WEAK LONG. **Achado estrutural**: o script nunca correlaciona o signal score com retorno de preço subsequente — não existe caminho para EV/win-rate/veredito no design atual, precisaria de lógica de forward-return nova, não mais tempo rodando |
| 21 | D38 — Binance announcement front-run | Rodando 21h+ na AWS | Primeiros anúncios reais capturados (2026-07-06): 3 no total (2 sem token associado, 1 LISTING — delist TST/IOTX, sentimento bullish, preço $0.01001 registrado em t0). Price-reaction tracking em andamento para o TST. Ainda cedo para veredito. **Update 2026-07-08**: mais anúncios capturados (torneios/promoções/caridade, categoria OTHER, sentimento neutro), nenhum LISTING novo com token associado desde o TST. Amostra tradeable continua ~0-1, veredito impossível até um LISTING real aparecer |
| 22 | D39 — Options max pain magnet | Rodando 21h+ na AWS | Expiry 6JUL26 rolou para 7JUL26 em 2026-07-06T00:12 **sem convergência**: diff BTC spot-vs-max-pain foi de +2.00% para +3.04% (divergiu) nas ~7h antes do rollover. Primeiro ciclo completo não sustenta a tese de "magnet". Seguindo para o ciclo 7JUL26 |
| 23 | D40 — Stablecoin mint signal | Rodando 13h+ na AWS | **ATUALIZADO 07-07: 108 ciclos.** Regime mudou: ~29 ciclos NEUTRAL(0) → 9 ciclos STRONG LONG(2) → agora MODERATE LONG(1), 3d supply +$342M. Score interno dispara em sub-limiares (~+$100M/24h) bem abaixo do trigger formal do dashboard (±$500M/3d) — nenhum sinal formal LONG/SHORT disparou ainda. BTC caiu ~$64.0k→$62.9k durante a janela LONG (N=1, não conclusivo). Ainda sem framework de P&L sinal-vs-retorno. **Update 2026-07-08**: regime virou STRONG SHORT (3d supply -$1704M, grande redemption). Mesmo problema estrutural do D37 — score muda de sinal ao longo do tempo mas nunca é testado contra retorno futuro real; sem esse framework não há caminho para veredito |
| 24 | D41 — WS trade anomaly detector | Rodando 21h+ na AWS (reiniciado 2026-07-06, ver incidente) | Ciclo de referência antes do restart: N=157.000 trades, clusters=1128 (0.72%), volume_bursts=125 (0.08%), dup_ids=0, **timestamp_anomalies=38.068 (24.2% dos trades!)** — taxa alta, ainda sem análise de reação de preço pós-anomalia. `volume_timeline` tinha vazamento de memória sem limite (344MB RSS/~24h) que exigiu restart; corrigido (bound a 2000 entradas), contadores zeraram. Ainda exploratório — falta simulação de P&L com fees para veredito. **Update 2026-07-08**: confirmado nos 15 blocos "VERDICT" já impressos — nenhum jamais correlaciona anomalia com retorno de preço, é puramente contador de frequência (ciclo mais recente: ~15M trades/48.6h, clusters 0.401%, timestamp_anomalies 1.383%, volume_bursts 0.107%). **Não existe caminho para veredito no design atual, independente de tempo de execução** — precisaria de lógica nova (preço antes/depois de cada anomalia), não mais amostra |
| 25 | D42 — Deriv vs Binance latency arb | **REFUTADO** (via H3 + dados próprios) | N=6.830 amostras em 13h: avg lag=204.5ms, max=950ms — confirma que o lag do FEED é real e consistente. MAS H3 já testou isso exaustivamente no nível de EXECUÇÃO (60+41 ordens demo reais, incl. co-locado em Tóquio): fill sempre reprecifica fresco, custo ~489x a captura. D42 mede só o feed (equivalente ao Passo 1 de H3), não a execução (Passo 2/3, o teste decisivo). Não restartar — pergunta já respondida |
| 26 | D43 — Order book imbalance | **REFUTADO** (auto-concluído, N=24.994) | Processo rodou 33.487s (9.3h) e concluiu sozinho: 756 predictions resolvidas, accuracy 30s CAIU de 75.4%→**58.8%** (abaixo do próprio threshold de 60%). Confirma D33 (mesma tese, refutado por fees: WR direcional real mas 0% lucrativo). N=98 inicial era false positive de amostra pequena |
| 27 | D44 — Funding rate arb | Aguardando evento extremo | 113 ciclos completos em 13h (a cada 5min). Único sinal persistente: ATOMUSDT LONG_FUT, funding ~-0.03%/8h (bem na borda do threshold, magnitude pequena). Nenhum extremo real. Dominio parcialmente sobreposto com D35 (refutado) mas mecanismo diferente (reversão vs momentum). **Reconfirmado 2026-07-08**: ainda sem sinal extremo, monitor barato segue rodando. **AUDIT 2026-07-08**: confirmado o MESMO GAP estrutural do D37/D40/D41 — o script printava "VERDICT" mas nunca trackeava basis reversion + funding coletado vs horizonte; a docstring dizia "Track basis reversion over 1h, 4h, 24h" mas steps 4-5 nunca foram implementados. **CORRIGIDO**: criado `carry_return_tracker.py` (delta-neutral específico: grava funding_rate + basis_pct, resolve carry_pnl = basis_reversion + funding_collected - fees em 8h/24h/72h), integrado e reiniciado às ~15:30 UTC |
| 38 | D29 — Basis-Funding Disconnect (Binance carry trade) | Paper bot ativo na AWS (`basis_paper_bot.py`, tmux `basis_bot`) | Scan inicial (19 pares) achou sinal fraco. Paper bot ao vivo evoluiu: N=19 WR68.4%→N=24 WR70.8%→**N=33 WR72.7%** (2026-07-08), EV/trade +0.2635%, total +8.70%, avg duração 1.2h — tendência estável/melhorando conforme N cresce (oposto do decaimento do D36). **IC95% formal implementado 2026-07-08** (Wilson no WR + bootstrap no EV, mesmo padrão do repo): WR=72.7% IC95%[55.8%, 84.9%] — **exclui 50%, estatisticamente significativo**. EV=+0.2635% IC95%[-0.7964%, +1.4311%] — **CRUZA ZERO, INCONCLUSIVO**. O WR é real (não é sorte), mas o EV ainda não é estatisticamente positivo: losses grandes (worst -5.96%) offsetam wins. Precisa N~60-80 pra o IC do EV convergir. **Lead mais promissor entre os processos em andamento**, mas NÃO é edge confirmado ainda. Ver `hypotheses-data.ts` HYP-BASIS-02 |
| 28 | D45 — Liquidation cascade | **REDUNDANTE com D34** — retirado | Mesma tese exata (3+ liquidações/10s = cascade) que D34, que já roda há mais tempo com design mais rigoroso (fee-adjusted, 4 hold periods). D34 confirma 0 cascades em todos os ciclos (dias de dados). Não restartar D45, usar D34 como fonte única |
| 29 | D46 — Deriv tick patterns | **REFUTADO** (2026-07-06, N=190.000) | Amostra pequena de 2026-07-05 (N=542/300) mostrava ==D→UP 55.4%, ==U→DOWN 56.7% — pareciam edges. Com N=190.000 em uma única sessão contínua de 7h: ==D→UP **50.44%** (z≈2.89, tecnicamente fora do ruído mas 0.44pp — muito abaixo de qualquer custo de transação), ==U→UP **49.82%** (z≈-1.02, não significante). Mesmo padrão de todo o programa: sinal, quando existe, é menor que o custo. Bot parado, removido do supervisor. Bug de reconexão (mesmo do D43) também corrigido no script antes de encerrar |
| 30 | D47 — Stale proposal buy race | **REFUTADO** (N=40) | `stale_proposal_probe.py`: pede proposal, espera delay (TREAT=20s vs CONTROL=0s), compra com `proposal_id` antigo, compara barrier antigo vs barrier real do contrato. Barrier **SEMPRE recalculado** no momento da compra (39/40 rounds "RECALC(new)"; o 1/40 "STALE(old)" restante foi coincidência de preço parado, não cache). TREAT WR=45% IC95%[25.8,65.8] vs CONTROL WR=55% IC95%[34.2,74.2] — diferença dentro do ruído, consistente com custo de esperar 20s num random walk simétrico, não com exploit de preço obsoleto. HIGHER/LOWER R_100, 10 ticks |
| 31 | D48 — Accumulator tick-barrier race | **REFUTADO** (N=20, com EV negativo confirmado) | `accu_tick_race_probe.py`: testa se um sell manual consegue "vencer" o servidor quando um tick recebido localmente já rompeu a barreira do ACCU antes do knockout ser confirmado. Primeira versão teve falso positivo (client-side bid_price desatualizado); corrigido com fresh-check (`poll_open_contract` imediatamente antes de vender). Com o fix: em 5/20 trials o breach local era falso positivo (servidor já tinha `is_sold=True`/`bid_price=0` -- knockout atômico, sem janela de corrida). Nos outros 11/20 (55% WR) o sell REALMENTE executou a um bid fresco>0, capturando valor genuíno -- mas **EV agregado é negativo**: total=-$6.51/20 trials, média=-$0.3255/trial, bootstrap IC95%=[-0.585,-0.060] (não cruza zero, do lado negativo) -- vitórias pequenas (~$0.10-0.41) não compensam o stake integral perdido nas derrotas. Sem edge, com ou sem "vencer a corrida" |
| 32 | D49 — App ID / canal pricing arbitrage | **REFUTADO** | `app_id_pricing_probe.py`: pede `proposal` idêntica em paralelo por 2-3 canais. **Mesmo gateway** (`api.derivws.com/trading/v1/options/ws/public`), app_id do projeto (OAuth) vs app_id público genérico `1089`: **40/40 rounds com ask_price/payout/spot idênticos** (byte-a-byte) -- app_id não afeta preço dentro do mesmo canal. **Gateway legado** (`ws.derivws.com/websockets/v3`, app_id=1089, mesmo IP AWS-Europa): rejeita **todos** os sintéticos testados (R_10, 1HZ10V, WLDAUD, JD10 — `"Trading is not offered for this asset"`, campo=`symbol`) e só oferece categoria `multiplier` para forex (CALL/PUT rejeitado com campo=`contract_category`, qualquer duration). Isso é segmentação regulatória de entidade/jurisdição (compatível com restrição ESMA a binários/sintéticos para clientes EU) roteada por IP, não um bug de precificação — onde o mesmo produto é oferecido nos dois canais, o preço é idêntico |
| 33 | D50 — Multiplier stop-out slippage | **REFUTADO** (N=20) | `multiplier_stopout_probe.py`: compra MULTUP (1HZ100V, 400x, $10), poll a cada 0.3s até fechar, compara `stop_out_level` teórico vs `exit_spot` real. 6/20 trials foram stop-outs genuínos (profit≈-stake; os outros 14 bateram o timeout do probe com preço favorável e foram fechados manualmente, profit variável +$0.13 a +$27.28). Slippage nos 6 genuínos: média=+0.127 pts, min=-0.03, max=+0.39 (ruído bidirecional, sem viés direcional consistente) — mas o **profit realizado foi EXATAMENTE -$10.0000 (a perda teórica) em todos os 6 casos**: a Deriv absorve esse micro-overshoot e garante o cap de perda exato no stake, sem repassar slippage ao cliente. Não há excesso de perda nem espaço para "intervenção manual" melhorar o resultado |
| 34 | D51 — Static replication arbitrage | **REFUTADO** | `static_replication_probe.py`: CALL+PUT e HIGHER+LOWER(+0.5) no mesmo underlying/duration, `basis=payout` ($100 alvo), pedidos em paralelo (2 conexões, mesmo spot). Resultado **perfeitamente determinístico**: soma dos ask_price = $102.40 em TODAS as 39+14 rodadas com spot batendo, **arb_$=-$2.40 constante, variância zero**. Margem da casa é uma % fixa (2.4%) aplicada simetricamente às duas pernas complementares — nenhuma arbitragem estática possível |
| 35 | D52 — Deal Cancellation mispricing | **SINAL PRELIMINAR (teste ao vivo INCONCLUSIVO, N pequeno)** | `deal_cancellation_edge_scan.py`: a feature paga "Deal Cancellation" dos Multipliers (reembolso integral do stake se cancelado dentro de 5-60min) é uma put europeia embutida (strike=entry, notional=stake×multiplier). Fair value via Monte Carlo (bootstrap em sub-blocos de 60 ticks, 60k ticks histórico, 60k sims) vs fee cobrado ao vivo: **17/20 células (multiplier 400x/1000x × MULTUP/MULTDOWN × 5 durações) com fee < fair_value (IC95%)**, edge relativo ~8-12%, agora simétrico entre MULTUP/MULTDOWN (assimetria inicial de até 180% era artefato de block bootstrap com histórico insuficiente p/ blocos de 3600 ticks — corrigido). **Update 2026-07-06/07 — validado com trades reais** (`deal_cancellation_live.py`, N=20, 1HZ10V multiplier=400x stake=$10, cancellation=5min, MULTUP/MULTDOWN alternados): 12/20 cancelados com valor realizado (profit ficaria negativo se segurasse), 8/20 nunca ficaram negativos (fee "desperdiçado", `action=expired_held_to_profit`). Fee médio pago=$0.44, valor realizado médio na cancelação=$0.587. **EV líquido (valor_realizado − fee) = +$0.147/trade, IC95%=[-$0.1415,+$0.4775] — CRUZA ZERO, INCONCLUSIVO** (mesmo veredito impresso pelo próprio script). N=20 é pequeno demais pra decidir; ainda o único "quase-edge" nativo da Deriv nesta lista, mas precisa de bem mais amostra ao vivo antes de qualquer conclusão real |
| 36 | D53 — Concurrent duplicate-buy race | **REFUTADO** | `duplicate_buy_race_probe.py`: 2 buys simultâneos (`asyncio.gather`, sem delay) referenciando o MESMO `proposal_id`. Testado em 2 variantes: (a) 2 conexões autenticadas separadas, mesma conta — 0/15 trials com ambos aceitos, leg B sempre rejeitado instantaneamente com "Unknown contract proposal" (proposal_id é **escopado à sessão/conexão** que o criou, nem chega a competir); (b) mesma conexão, 2 buys concorrentes via req_id diferentes — 0/8 trials com ambos aceitos, sempre exatamente 1 sucesso + 1 rejeição, debitado sempre = 1x stake. Consumo do proposal_id é atômico, sem janela de corrida |
| 37 | D54 — Streamed proposal staleness | **REFUTADO** (+ achado inesperado) | `proposal_stream_staleness_probe.py`: assinar `proposal` com `subscribe:1` deveria realimentar a cada tick (~1/s), mas **nunca reenviou uma segunda atualização em 50+s** (confirmado via subscription id válido + `stream_client` seguindo responsivo a outros requests na mesma conexão) — comportamento inesperado do gateway novo, não um lag sutil. Como consequência, `proposal_id` do stream ficou obsoleto rapidamente: 2/3 tentativas de compra contra ele foram rejeitadas ("Unknown contract proposal"); a 1 aceita não deu para confirmar honra/recálculo de forma limpa (entry_spot ainda não populado no poll imediato). Sem janela de staleness explorável — proposals antigos expiram e são rejeitados, consistente com D47 |
| 38 | D96 — Flat Tick Frequency + RNG Deep Analysis | **REFUTADO** | 50k ticks × 17 símbolos. P(flat) max = JD100 9.06% (breakeven 11.11%). Hurst ~0.55 universal. CRASH1000 Ljung-Box p=0.0047 mas efeito insuficiente. Nenhum desvio explorável de aleatoriedade |
| 39 | D97 — Payout Curve Deep Scan | **REFUTADO** | 1874 células (23 types × 9 durations × 11 symbols × 3 stakes). 0 straddle arb. House margin ~4% consistente em todos. RUNHIGH/RUNLOW 30.53x ratio era payout alto com P(win) proporcionalmente baixa |
| 40 | D98 — Instant Resale Flip Scanner | **REFUTADO (v2)** | 250 células, 80 válidas. 17 "flip edges" (≥1/3 trades ITM), 12 com avg_ratio > 1.0. Melhor: R_100 CALL 5t 1.56x. MAS resale é binário ($0.92/$1.88) = exposição direcional, não flip estrutural. Mean ratio 0.9427 < 1.0 = house margin |
| 41 | D99 — RUNHIGH/RUNLOW Validation | **REFUTADO** | D97 flagou ratio 30.53x. Longcode revelou: "rises/falls successively for 5 ticks" = (0.5)^5 = 3.125% P(win). Breakeven 3.28%. 58 trades DEMO: 1/58 wins (1.72%). House margin 4.8% confirmado |
| 42 | D100 — Proposal Staleness v2 (ms-scale race) | **REFUTADO** | RACE (0ms, lag 193ms) WR=43.3% vs CONTROL (2000ms) WR=53.3%. Staleness não ajuda. spot_diff aleatório. N=60 |
| 43 | D101 — Barrier Proximity Edge (DIGITOVER/UNDER) | **INCONCLUSIVO (N=20/barreira)** | Payout ratio 1.09x-8.33x perfeitamente inverso à P(win). 120 trades DEMO: DIGITOVER_0/UNDER_9 WR=95% vs be=91.74%, DIGITOVER_5/UNDER_4 WR=50% vs theo=40%. CI95% cruza breakeven em todas. Nenhuma barreira com edge confirmado |

## Recomendação

1. **Deriv está exaustivamente fechado.** Todos os 14 produtos ativos na API foram testados e
   refutados. Nenhuma hipótese de mispricing de produto, execução, latência ou timing sobreviveu.
2. **PA5 Polymarket refutado** com N=1838 (aligned_pior, IC95% não cruza zero). O livro CLOB está
   corretamente precificado.
3. `hft_bot` shadow A/B tem valor marginal baixo — H3 co-locada já respondeu a mesma pergunta com
   mais rigor. Decisão de mantê-lo rodando ou não é operacional, não estatística.
4. **Solana DEX arb refutado** (Jupiter vs Binance + triangular). O agregador Jupiter já captura
   ineficiências intra-DEX; o gap CEX-DEX de ~9bps é fee estrutural, não edge explorável.
5. **Polymarket encerrado.** PA1-PA5 todos refutados. Market makers profissionais precificam
   corretamente desde a criação até a resolução.
6. **EVM DEX cross-aggregator arb refutado** (D6). Spreads de 20-450 bps entre OpenOcean,
   Paraswap e LiFi em BSC/Base/Arbitrum/Polygon são artefatos de quote APIs indicativas, não
   preços executáveis. BSC (chain mais líquida, controle de sanidade) mostra roundtrip negativo
   (-1 a -3 bps). O padrão espelha Solana DEX: agregadores já capturam ineficiências.
7. **CEX-CEX arb refutado** (D7). Binance, Bybit e OKX têm preços idênticos (spread 0-4 bps,
   fees 20 bps). Market makers cross-exchange comprimem qualquer ineficiência instantaneamente.
8. **Triangular CEX arb refutado** (D8). Binance triangular é -10 bps gross médio. O spread
   bid-ask em cada leg consome qualquer ineficiência. Mais eficiente que Solana DEX.
9. **Funding rate carry trade refutado** (D9). Scan inicial mostrou 14/20 "lucrativos", mas era
   viés de amostra curta (~11 dias). Validação com 30 dias completos: apenas 4/19, e 0% das
   janelas de 7 dias são lucrativas após fees (40 bps) + custo de capital (42 bps/30d).
10. **DeFi liquidation MEV refutado para retail** (D10). 108 liquidações Aave V3 na Base em 10.6
    dias, bonus médio 7.8%. Mas 95% dos eventos têm debt <$4, latência 30-60s vs <12s dos bots MEV,
    e RPCs gratuitos bloqueiam eth_getLogs. Sem infra profissional (WebSocket + flashbots + archive
    node), capture rate é <1%.
11. **Options IV mispricing refutado** (D11). VRP negativo em BTC (-8.2%) e ETH (-8.8%):
    IV < RV sugere comprar vol, mas theta decay + delta hedging costs + bid-ask spreads
    consomem o edge. Sem infra de vol trading profissional, não é capturável.
12. **Statistical arbitrage refutado** (D12). 76/190 pares cointegrados (40%), mas backtest
    OOS: 7/10 pares negativos após 40bps fees. avg PnL=-278bps, avg Sharpe=-0.26. Win rate
    de 63% é enganosa — ganhos pequenos vs perdas grandes nos stops.
13. **Funding rate signal — sinal fraco assimétrico** (D13). Short side (funding positivo →
    vender) tem WR 37-43% em 72h para BTC/ETH. Long side não funciona (WR 0-12%). Sharpe 5.4
    mas WR 26% — poucas trades grandes compensam muitas pequenas perdas. Melhor como filtro
    complementar, não standalone.
14. **Trend following — sinal marginal** (D14). SMA(10/50) long+short beat buy & hold em
    risk-adjusted (Sharpe 1.16 vs 0.85 BTC). MAS N=7 trades OOS não é significativo.
    Long-only não replica OOS. Custos de shorting (funding + borrow) reduzem edge.
15. **Combined funding+trend refutado** (D15). Funding filter PIORA trend following:
    delta Sharpe -0.27 BTC, -0.45 ETH, -0.80 SOL. Filtro remove trades bons — funding
    reflete positioning atual, não direção futura. Descoberta secundária: funding-only
    short em ETH tem Sharpe=2.96 mas MaxDD=95% — não é tradeable.
16. **CVD / order flow — REFUTADO em re-teste rigoroso** (D16v2). 5000 candles,
    5-fold CV, permutation test, Bonferroni correction (α=0.0019). Nenhum config
    significativo. ETH diverge_96h_48h WR 76% mas p=0.107 (56x acima do threshold).
    Sharpe 10+ do v1 era artefato de annualization inflation + multiple testing.
    Sinal é regime-dependent, não robusto.
17. **Token unlock short — EDGE VALIDADO OOS + CUSTOS + TIMING + 2026** (D17).
    215 unlock events (119 IS 2023-2024 + 48 OOS-2025 + 48 OOS-2026), 10 tokens.
    Short 3d antes/3d depois. IS: WR 61%, +285bps, t=2.66. OOS-2025: WR 79%, +660bps,
    t=5.43. **OOS-2026: WR 67%, +384bps, t=2.59.** Edge mantém em 2026 (mais fraco mas
    significativo). Timing optimization (25 combos): **-3d/+3d é o ótimo** — não precisa
    mudar. Funding cost: -4bps OOS (irrelevante). NET OOS-2025: +656bps, t=5.38.
    Large unlocks (≥$200M): 7/7 negativos. **Bot implementado: `unlock_short_bot.py`**
    (paper/live/backtest modes, half-Kelly sizing, +90.9% return backtest $10k→$19k).
18. **Binance listing impact — REFUTADO** (D18). 43 listings, buy at listing:
    WR 23%, avg +32bps (1d), t-stat=0.29. 30d excess=-15.3% (t=-3.34). Listings
    são "sell the news" — tokens caem após listing. Não há pump capturável.
19. **Cross-exchange latency arb — REFUTADO** (D32). 1200+ samples, divergência
    máx 0.02% vs 0.2% fees. REST API ~2.5s/sample (não 100ms). Não há leader
    consistente. Latency arb é jogo institucional (co-location sub-ms, WebSocket/FIX,
    maker orders). Não viável sem infra profissional.
20. **Order book imbalance — REFUTADO** (D33). 2400+ signals, WR direcional até
    62.5% em 10s MAS 0 wins após fees (100% negativo). Movimentos de preço < 0.1%
    fee em 10s. OBI tem poder preditivo direcional real mas insuficiente para
    superar taker fees. Precisaria WebSocket L2 + maker orders.
21. **Funding rate prediction — REFUTADO** (D35). Momentum direction WR 87.3%
    (N=1269) MAS Profitable WR 11.7%. EV -$0.43/trade, annualized -47.3%.
    Funding rates são太小 vs 0.08% fees. Momentum prediz direção mas valor
    coletado é insuficiente. Edge só em perps com funding anômalo (LABUSDT,
    SLXUSDT) — outliers illiquid não escaláveis.
22. **IV surface anomaly — EDGE PARCIALMENTE CONFIRMADO, mas divergindo** (D36). Backtest BS
    model-based: BUY side 7/7 wins +$4,500 (100% WR), SELL side 0/9 wins -$792 (bid-ask spread
    artifacts em deep ITM). Top BUY: BTC-26MAR27-115000-C +$1,289 (172% ROI).
    Theta decay mínimo após 7d. Reversion test: 6/6 reverting (0 stale).
    **Update 2026-07-06**: paper bot ao vivo com 7 settles reais mostra WR=42.9% (não 100%),
    EV/trade ainda positivo (+$137.52) com 115 posições abertas. Backtest pode ter sido
    otimista (look-ahead ou seleção de amostra) — **acompanhar settles reais antes de
    qualquer decisão de capital real.**
    **Update 2026-07-08**: WR caiu mais, para 40.5% (N=37), trajetória monotonicamente
    decrescente (50.0%→42.9%→41.9%→41.2%→40.5% conforme N cresceu 24→37). Total ainda
    positivo (+$1517.90) só por skew de poucos winners grandes; últimos 2 settles foram
    losses (maior: -$420.94). Mesmo padrão de decaimento que desmascarou o early-sell
    original — **tratar como candidato a falso-positivo até a trajetória estabilizar ou
    reverter**, não como confirmação parcial.
23. **Liquidation cascade — AGUARDANDO EVENTOS** (D34). 0 cascades em 30min
    (mercado calmo). Bot rodando em loop contínuo na AWS. Cascades são raras
    mas quando ocorrem, continuation é quase garantida (forced selling).
    Precisa dias/semanas para capturar eventos durante volatilidade alta.
24. **Status consolidado (atualizado 2026-07-07)**: 55 hipóteses, **49 refutadas** (D46-D51,D53,D54,
    Early Sell re-refutado),
    2 com sinal fraco/marginal, 1 com edge validado (D17),
    1 com edge parcialmente confirmado mas divergindo (D36 BUY only, ver nota),
    1 com sinal preliminar não confirmado (D52 — Deal Cancellation, teste ao vivo N=20 INCONCLUSIVO,
    IC95% cruza zero, ver item 35),
    2 aguardando eventos (D34, D44), 4 em validação inicial (D37/D38/D40/D41),
    1 em validação com sinal parcial (D55 — Hyperliquid vs Binance: LINK isolado como candidato
    forte após walk-forward + custo de capital, ver item 36).
    **Foco: D17 go live + D36 acompanhar settles ao vivo (WR caindo vs backtest) +
    D39 seguir ciclo 7JUL26 +
    D52 juntar mais trades reais (N=20 atual é pequeno demais p/ IC95% decisivo) +
    D55 acompanhar validação D55b do LINK rodando 6h na AWS (paralelo ao BTC/ETH/SOL
    original terminando ~12h) antes de cogitar paper-trade. Categorias
    "execução/plataforma" (D47-D50) e "replicação/concorrência/streaming" (D51,D53,D54)
    fechadas: nenhum race condition, buy/sell timing exploit, canal de pricing
    alternativo ou arbitragem estática sobreviveu ao teste.**
25. Sincronizar com o Carlos sobre `feat/operate-demo-synthetic` antes de tocar em
    `hft_arbitrage_bot.py` de novo.
26. **INCIDENTE AWS 2026-07-05**: instância t3.micro (911MB RAM, sem swap) ficou
    impossível de acessar via SSH por ~5h (09:26-15:46 UTC) devido a pressão de memória
    severa causada por ~20 processos Python concorrentes (D37-D46 + paper bots + hft_bot).
    Sem OOM-kill explícito nos logs, mas `systemd-journald`/`resolved` reportaram
    "under memory pressure" repetidamente; rede/SSH ficaram não-responsivos. Resolvido via
    reboot + 2GB swapfile (`/swapfile`, persistente via `/etc/fstab`). D42/D43/D45 NÃO
    foram religados (concluídos/refutados/redundantes, ver tabela). D46 corrigido com
    checkpoint periódico (a cada 500 ticks) para não perder dados em crashes futuros.
    Supervisor (`aggressive_monitor_supervisor.sh`) atualizado para a lista reduzida de
    14 processos + hft_bot/liq_bot (wrappers while-true separados).
27. **CHECAGEM 2026-07-06 (24h depois)**: memória voltou a ficar crítica (71MB disponíveis,
    swap em uso) por dois motivos novos. (a) `unlock_status_api.py` (porta 8788, parado no dia
    anterior por ser código morto) **voltou sozinho** — o supervisor já estava rodando havia
    horas com a lista antiga carregada em memória antes da minha edição do arquivo; editar o
    script no disco não afeta um processo já em execução. Corrigido reiniciando a sessão
    `aggressive_supervisor`. (b) `wash_trading_scan.py` (D41) tinha vazamento real: lista
    `volume_timeline` crescia sem limite por símbolo, gerando 344MB RSS + O(n) crescente no
    `sum()` a cada trade (explica também a CPU alta). Corrigido com bound de 2000 entradas
    (mesmo padrão já usado para a lista `trades`); processo reiniciado, memória caiu para
    ~400MB disponíveis. D46 tinha o mesmo bug de reconexão do D43 (sem loop de retry em
    `--continuous`, um WS drop mata o processo inteiro) — corrigido, mas como N=190.000 já
    dava veredito claro (REFUTADO), o bot foi encerrado em vez de mantido rodando.
    **Lição operacional: reiniciar o supervisor após editar sua lista de sessões; considerar
    um teste/alerta de memória disponível < 150MB.**
28. **Stale proposal buy race — REFUTADO** (D47). `stale_proposal_probe.py`, N=40 (20 TREAT
    delay=20s / 20 CONTROL delay=0s) em HIGHER/LOWER R_100 10-tick. O barrier do contrato
    comprado é **sempre recalculado** no momento da compra (39/40 "RECALC(new)"), nunca honra
    o preço da proposal antiga — mesmo dando 20s de vantagem para o mercado se mover a favor
    do barrier antigo. WR/EV TREAT vs CONTROL não significativo (IC95% sobrepostos), consistente
    com custo puro de esperar 20s, sem exploit de preço obsoleto.
29. **Accumulator tick-barrier race — REFUTADO** (D48). `accu_tick_race_probe.py` tenta vender
    manualmente no instante em que um tick recebido via WS local rompe a barreira do ACCU, antes
    do servidor confirmar o knockout. Versão inicial reportou "vitórias" que eram falso positivo
    (bid_price client-side desatualizado); com fresh-check server-side imediatamente antes do
    sell, toda tentativa encontra o contrato **já** knocked-out (`is_sold=True`, `bid_price=0`).
    O knockout é atômico com a ingestão do tick no back-end da Deriv — sem janela de corrida
    explorável do lado do cliente.
30. **App ID / canal pricing arbitrage — REFUTADO** (D49). `app_id_pricing_probe.py` comparou
    `proposal` idêntica (mesmo symbol/contract_type/duration/stake, mesmo instante) entre
    app_ids e gateways. Dentro do **mesmo gateway** (`api.derivws.com/trading/v1/options`),
    app_id do projeto vs app_id público `1089`: 40/40 rounds com ask_price/payout/spot
    **idênticos**. O **gateway legado** (`ws.derivws.com/websockets/v3`, app_id=1089, mesmo IP
    AWS-Europa) rejeitou todos os sintéticos testados e só ofereceu Multipliers para forex —
    segmentação regulatória de entidade/jurisdição (coerente com restrições ESMA na UE), não
    diferença de preço. Nenhuma arbitragem de canal encontrada.
31. **Multiplier stop-out slippage — REFUTADO** (D50). `multiplier_stopout_probe.py`, N=20
    MULTUP (1HZ100V, 400x, $10), 6 stop-outs genuínos identificados por profit≈-stake.
    `exit_spot` vs `stop_out_level` mostra micro-slippage de +0.127pts em média (min=-0.03,
    max=+0.39) mas **sem efeito no profit realizado**: exatamente -$10.00 em todos os 6 casos.
    A Deriv garante o cap de perda no stake independente do overshoot de 1 tick — não há
    slippage repassado ao cliente nem espaço para melhorar o resultado com fechamento manual.
32. **Static replication arbitrage — REFUTADO** (D51). `static_replication_probe.py`: comprar
    as duas pernas de um par complementar (CALL+PUT, ou HIGHER+LOWER no mesmo barrier),
    ambas com `basis=payout` fixado em $100, deveria ser risco-zero (exatamente uma ganha).
    Resultado determinístico: soma dos ask_price = $102.40 em 100% das rodadas com spot
    idêntico entre as pernas (39 + 14 rodadas), **arb_$=-$2.40 sem nenhuma variância** —
    margem da casa de 2.4% aplicada simetricamente, sem brecha de replicação estática.
33. **Deal Cancellation mispricing — SINAL PRELIMINAR, requer validação ao vivo** (D52).
    `deal_cancellation_edge_scan.py`: a "Deal Cancellation" dos Multipliers é uma put
    europeia embutida (protege o stake integral por 5-60min). Primeira tentativa de Monte
    Carlo (block bootstrap contíguo, 20k ticks) mostrou assimetria MULTUP vs MULTDOWN de
    até 180% — sinal claro de artefato (poucos comprimentos-de-bloco efetivos no histórico
    disponível para janelas de 3600 ticks). Corrigido com bootstrap em sub-blocos de 60
    ticks concatenados (mixing estatístico adequado mesmo p/ janelas longas) e ampliado
    para 60k ticks / 60k simulações: a assimetria **quase desaparece** (MULTUP≈MULTDOWN a
    cada duração), mas um edge residual **simétrico e persistente de ~8-12%** (fee cobrado
    abaixo do fair value MC, IC95% não cruza zero em 17/20 células) permanece mesmo após
    a correção e o aumento de amostra — diferente do padrão usual deste programa (onde
    mais rigor sempre derrubou o sinal). Ainda assim, é **só um modelo teórico** (depende
    de vol histórica de uma janela específica, aproximação European≈American, retornos
    aditivos) — não uma medição ao vivo como o Early Sell. **Não tratar como edge
    confirmado.** Próximo passo natural: comprar Multiplier+cancellation de verdade em
    demo e medir o valor extraído real (ao invés de simulado) contra o fee pago.
34. **Concurrent duplicate-buy race — REFUTADO** (D53). `duplicate_buy_race_probe.py`:
    disparar 2 `buy` simultâneos (mesmo proposal_id, zero delay) via 2 conexões
    autenticadas separadas (0/15 com ambos aceitos — proposal_id é escopado à sessão que
    o criou, o segundo leg nem compete, é rejeitado na hora) e via a mesma conexão com
    2 req_id concorrentes (0/8 com ambos aceitos — sempre 1 sucesso + 1 rejeição, débito
    sempre = 1x stake). Consumo de proposal_id é atômico dos dois jeitos testados.
35. **Streamed proposal staleness — REFUTADO, achado lateral inesperado** (D54).
    `proposal_stream_staleness_probe.py`: assinatura `proposal` com `subscribe:1` no
    gateway novo (`api.derivws.com/trading/v1/options`) recebeu a confirmação da
    subscription (id válido) mas **nunca reenviou uma segunda atualização em 50+ segundos**
    apesar do underlying tickar ~1x/s — a conexão seguiu viva e respondendo normalmente a
    outros requests na mesma sessão, então não foi uma queda de rede. Isso torna a
    proposta de "comprar do preço desatualizado que a tela mostra" moot: 2/3 tentativas de
    compra contra o proposal_id antigo do stream foram rejeitadas (`"Unknown contract
    proposal"`) por expiração normal, igual ao D47. Vale registrar como comportamento de
    plataforma a investigar separadamente (não é um exploit, mas pode afetar UX de bots/
    dashboards que dependem dessa subscription para preço "ao vivo").
36. **Hyperliquid vs Binance — VALIDANDO, LINK isolado como candidato forte** (D55).
    `hyperliquid_probe.py`. Primeira hipótese fora de Deriv/Polymarket/CEX-CEX (ver
    `docs/hyperliquid_report.md`). **D55a screening (funding arb perp-perp, 90d, N=270
    janelas/ativo):** 8/10 ativos pareciam lucrativos somando o período inteiro (mesmo
    padrão de falso-positivo do D9: 14/20 → 0/19 na validação real) — split IS/OOS único
    (direção decidida na 1ª metade, testada na 2ª) deixou 4/10: ETH, SOL, OP, LINK.
    **Walk-forward multi-janela (sem look-ahead, custo só em entrada/saída/flip de
    direção — cobrar round-trip toda semana seria simular a estratégia errada):
    derruba 3 dos 4.** ETH/SOL/OP têm win rate real (50-75%) mas trocam de lado com
    frequência suficiente pra que o custo por flip (19bps) coma o edge semanal pequeno
    (net -44 a -112bps em 90d). **Só LINK sobrevive, de forma robusta: ZERO flips em
    90 dias (testado com fold de 7d E 5d, mesmo resultado), 100% win rate, net
    +96-100bps, IC95% bem longe de zero** — funding da HL pro LINK-PERP é
    consistentemente mais alto que o da Binance toda semana, sem exceção. Direção:
    short HL LINK-PERP + long Binance LINK-PERP. **Custo de capital testado**
    (`capital_cost_sensitivity()`, mesma premissa T-bill 5% APR do D9): como é
    perp-perp (só margem, não notional cheio como a perna spot do D9), **LINK
    sobrevive a partir de ~3x de alavancagem por perna** (net-net +19.6 a +84.8bps
    entre 3x-20x); só fica negativo em capital 100%-cash-secured (≤2x) — diferença
    importante vs D9, que exigia capital pleno e por isso morria mesmo com números
    brutos maiores. **D55b (oraclePx/markPx/midPx da HL vs mid Binance, polling 3s),
    CONFIRMADO com N=10.021 (~8.3h AWS) em BTC/ETH/SOL E checado especificamente no
    LINK (N=100, 5min local, +7.64bps, mesmo padrão):** basis persistente e quase
    sempre positivo — não cruza zero, é prêmio estrutural, não mispricing tipo "livro
    desatualizado" que reverte. Consistente com o próprio mecanismo de funding da HL
    (markPx = EMA do prêmio sobre oraclePx, é esse prêmio que gera o funding) —
    **D55a e D55b provavelmente medem o MESMO fenômeno**, o que reduz um pouco a
    confiança em D55a ser "grátis" (pode ser compensação por segurar o prêmio, não
    uma ineficiência pura), mas não invalida ser capturável na prática. Falta: o
    walk-forward ainda é sobre os mesmos 90d do screening (robustez interna, não OOS
    temporal de verdade). Ver `docs/hyperliquid_report.md` atualizado. **PAPER TRADING
    OOS INICIADO 2026-07-08 16:50 UTC**: `hyperliquid_paper_bot.py` (tmux `d55_paper`,
    adicionado ao `aggressive_supervisor`) abriu posição simulada SHORT HL LINK @ $7.6071
    + LONG BN LINKUSDT @ $7.6033, $1000 notional, 19bps roundtrip debitado. A cada ciclo
    de funding da Binance (8h) settle: funding coletado em ambos venues + mark-to-mark
    P&L. Report com Wilson/bootstrap a cada 5 ciclos. Primeiro ciclo às 00:00 UTC
    (~7h após abertura). Dados daqui em diante são OOS temporal real (não overlap com
    os 90d do screening).
37. **Auditoria completa dos 16 processos ativos na AWS (2026-07-08)** — sem reiniciar/parar
    nada, checado `tmux ls` + `ps` + logs + `audit_hft_trades.py` para todo o fleet. Categorizado
    em 3 grupos:
    - **Estruturalmente incapaz de gerar veredito** (sem redesign): `d41_wash` (~15M trades/ciclo,
      "VERDICT" só conta % de anomalias, nunca correlaciona com preço), `d37_outflow` (~1000
      snapshots, só heurística), `d38_announce` (só loga anúncios), `d40_stable` (mesmo padrão de
      `d37`). Nenhum tem lógica de forward-return — precisam de código novo, não mais N.
    - **Esperando evento raro/agendado, framework pronto**: `liq_bot`/D34 (0 cascades),
      `twap_bot` (0 trades em 2 dias, próxima janela real 09JUL 07:30 UTC),
      `options_paper_bot` (9 posições abertas, 0 settled, primeira expiry em ~1 dia),
      `d39_maxpain` (aguardando expiry 9JUL26).
    - **Amostra real acumulando, tendência informativa**: `basis_paper_bot`/D29 (N=33, WR 72.7%,
      melhorando — ver item 38) e D36/`iv_anomaly_paper_bot` (N=37, WR 40.5%, piorando — ver
      item 19/22).
    - `hft_bot` reconfirmado com trades reais (não só por analogia a H3): N=34 todas-versões e
      N=12 V6.2-por-parâmetro, ambos IC95% negativo (ver item 15 e "Update 2026-07-08" na seção
      Shadow A/B). **Nenhum processo no fleet tem edge confirmado em execução ao vivo agora;
      D17 segue sendo o único backtest-validado, mas com N=0 trades paper até o momento.**
38. **Follow-up 2026-07-08 (parte 2) — corrigido o gap estrutural + esclarecido D17:**
    - **Código corrigido e redeployado**: criado `trading-engine/forward_return_tracker.py`
      (grava preço+direção do sinal a cada ciclo, resolve retorno no horizonte certo, reporta
      com o mesmo Wilson/bootstrap de `stats_utils.py`) e integrado em `exchange_outflow_scan.py`
      (D37, horizontes 1h/4h/24h), `stablecoin_mint_scan.py` (D40, 1h/4h/24h) e
      `wash_trading_scan.py` (D41, 10s/30s/60s — usa o próprio preço do stream WS, sem custo de
      rede extra). Os 3 processos (`d37_outflow`, `d40_stable`, `d41_wash`) foram reiniciados na
      AWS às ~15h UTC com o código novo (verificado sem erro pós-restart); todos os outros 13
      processos do fleet foram deixados intocados. A partir de agora, esses 3 PODEM produzir um
      veredito real de EV/WR — só falta tempo/amostra.
    - **D17 (unlock_bot) não é um gap** — investigado a fundo: o log só mostra "no open
      positions" porque o próximo entry (APTUSDT, unlock 2026-07-12, entry = unlock−3d =
      **2026-07-09, amanhã**) ainda não chegou; `unlock_short_bot.py` confirmado rodando em
      `--paper` (sem `--live`), checando a cada hora, vai disparar sozinho no horário certo. Sem
      bug, sem ação necessária — só esperar 1 dia.
    - **`early_sell_multi` (HYP-SELL-01)**: já tinha sido re-refutado em N=550 (2026-07-07), mas
      o processo continuou rodando na AWS e mais que triplicou a amostra (N=187/combo, ~1870
      trials). Mesmo resultado em 10/10 combos — recomendado **parar o processo**, é redundante.
      **PARADO 2026-07-08** (tmux `early_sell_multi` e `hft_bot` killados; fleet agora tem 14
      sessões, só as que ainda têm potencial).
    - **D29 IC95% formal implementado**: `basis_paper_bot.py` agora usa `stats_utils.wilson_ci`
      no WR + `bootstrap_ci` no EV (mesmo padrão do repo). Resultado em N=33: WR=72.7%
      IC95%[55.8%, 84.9%] (exclui 50%, significativo), EV=+0.2635% IC95%[-0.7964%, +1.4311%]
      (cruza zero, INCONCLUSIVO). O WR é real mas o EV ainda não é estatisticamente positivo —
      losses grandes offsetam wins. Precisa N~60-80 pra convergir. Bot reiniciado com o código
      novo, imprimindo o veredito formal a cada ciclo.
    - **D40 STRONG SHORT**: confirmado persistente por 5+ leituras seguidas antes do restart
      (score=-2, 3d supply −$1.704M) — não foi um blip de uma leitura só.
    - **D44 funding arb**: auditado e confirmado o MESMO GAP estrutural. A docstring dizia
      "Track basis reversion over 1h, 4h, 24h" mas steps 4-5 nunca foram implementados — o
      "VERDICT" impresso era só descrição do sinal atual. CORRIGIDO: criado
      `carry_return_tracker.py` (tracker delta-neutral específico: grava funding_rate +
      basis_pct no momento do sinal, resolve `carry_pnl = basis_reversion + funding_collected
      - fees` em 8h/24h/72h, reporta com Wilson/bootstrap). Integrado em
      `funding_basis_arb_scan.py`, redeployado e reiniciado às ~15:30 UTC.
39. **Follow-up 2026-07-08 (parte 3) — Tokenomist API integrada ao D17:**
    - **Tokenomist API ativa**: `unlock_data.py` agora busca eventos de unlock via
      `api.tokenomist.ai` (com fallback para `api.unlocks.app` e depois hardcoded).
      Requer `TOKENOMIST_API_KEY` no `.env` (configurado na AWS 2026-07-08).
    - **Descoberta de formato**: free trial não aceita `maxUnlockDate` nem
      `minTotalUnlockAmount` (HTTP 422). Solução: usar apenas `minUnlockDate` e filtrar
      client-side por data e valor. `cliffUnlocks` é um dict (não lista) com
      `totalCliffValue`/`totalCliffAmount` + `allocationBreakdown`.
    - **Whitelist de símbolos**: `VALIDATED_SYMBOLS` em `unlock_short_bot.py` restringe
      trades aos 8 tokens com edge backtestado (APT, ARB, AXS, DYDX, IMX, OP, SEI, STRK).
      Símbolos novos da API (ex: MOVE) são filtrados — sem edge validado, sem trade.
    - **Diferença de dados**: API mostra cliff-only value (APT $7M vs hardcoded $50M
      que incluía linear releases). Mais preciso para o sinal de cliff unlock.
    - **Primeiro evento API**: APTUSDT 2026-07-12 ($7M cliff), entry 2026-07-09.
      Bot confirmado rodando, API respondendo OK, whitelist ativa.
    - **D55 paper trading**: `hyperliquid_paper_bot.py` deployado e rodando na AWS
      (sessão `d55_paper`). Delta-neutral short HL + long Binance LINK funding arb.
      Aguardando ciclos de funding para acumular P&L.
40. **Follow-up 2026-07-11 — D56/D57/D58: 3 novas hipóteses de bugs Deriv testadas e refutadas:**
    - **D56 (Cross-Symbol Tick Correlation)**: testou se índices sintéticos 1HZ/R_ compartilham
      RNG. `cross_symbol_correlation_probe.py` subscreveu 9 símbolos simultaneamente, coletou
      2081 ticks, analisou 36 pares em 11 lags cada. **0/36 pares com correlação significativa**
      (|r|>0.05, p<0.05). Valores-p AUMENTARAM com amostra (0.65→0.80), confirmando independência.
      Símbolos sintéticos têm RNGs independentes — edge cross-symbol não existe.
    - **D57 (Stake Size Non-Linearity)**: testou se payout ratio varia com stake. 1162 proposals
      em 5 símbolos, 2 contract types, 12 stakes ($0.35-$100), 20 rounds. **Não-linearidade
      CONFIRMADA**: payout ratio 1.886 em $0.35 vs 1.923 em $100 (−1.9%). Causa: arredondamento
      de cents. PATTERN CONSISTENTE across all symbols/rounds. **MAS não exploitável**: o
      arredondamento sempre penaliza (floor), nunca beneficia. Achado adicional: payout em $0.35
      é $0.01 abaixo do floor teórico (esperado $0.67, atual $0.66), sugerindo haircut extra
      para stakes mínimas.
    - **D58 (Sell as Limit Order)**: testou se sell com price>0 funciona como limit order.
      50 trials (25 LIMIT + 25 MARKET) em CALL 10-tick 1HZ10V. **50/50 rejeitados** com
      'Resale of this contract is not offered'. Tick contracts não oferecem resale — não é
      possível vender antes do expiry a nenhum preço. Limit order é irrelevante quando sell
      não funciona. NOTA: resale pode existir para durações maiores (1d+), não testado.
    - **Conclusão Deriv**: D47-D58 (12 hipóteses de execução/plataforma) TODAS refutadas.
      O ecossistema Deriv está hermeticamente fechado para exploits de execução, race
      conditions, cross-symbol prediction, stake arbitrage e sell manipulation.
41. **Follow-up 2026-07-11 (parte 2) — D59/D60/D61/D62: Tier 2 (4 hipóteses de
    plataforma/streaming) testadas e refutadas:**
    - **D59 (POC Subscription vs Poll)**: testou se subscribe:1 para proposal_open_contract
      notifica settle antes do poll manual. N=30 trials CALL 5-tick 1HZ10V. **30/30: SUB
      NUNCA enviou atualizacoes** (sub_events=0), POLL detectou settle em 30/30. A
      subscription POC esta completamente quebrada — confirma D54. Nao ha timing gap
      porque a subscription simplesmente nao funciona. Poll e a unica opcao (~143ms RTT).
    - **D60 (Tick Subscription Gap)**: auditou stream de ticks vs historico. 10min, 20
      checks, 626 ticks. **5/626 missing (0.80%) — todos no startup** (5s consecutivas,
      latencia de conexao WS inicial). Checks 2-20: 0 missing. **0 quote mismatches**.
      Stream e completo e consistente apos conexao estabelecida. Nao ha gaps previsiveis.
    - **D61 (Reconnection State)**: forcou reconexao WS mid-contrato. N=20 trials, 13
      validos. **0/13 barrier mismatches, 0/13 sold state changes**. Reconnect ~1.7s.
      Bid_price muda (esperado — ticks moveu), mas barrier e is_sold identicos. Estado
      do contrato e consistente — servidor mantem estado por contract_id, nao por sessao.
    - **D62 (Barrier Rounding)**: testou se barrier tem menos precisao que tick. N=300
      proposals, 5 simbolos, 30 rounds. **253/253 CALL/PUT com barrier=None** — CALL/PUT
      nao expoe barrier explicita, e implicita (entry spot). Nao ha arredondamento
      separado para explorar. Payout ratio 1.920 consistente.
    - **Conclusão Deriv Tier 2**: D59-D62 (4 hipóteses de streaming/plataforma) TODAS
      refutadas. D47-D62 (16 hipóteses total) formam um bloco coeso: o ecossistema Deriv
      esta fechado para exploits de execução, race conditions, cross-symbol prediction,
      stake arbitrage, sell manipulation, subscription timing, tick gaps, reconnection
      state e barrier precision.
42. **Follow-up 2026-07-11 (parte 3) — D63/D64/D65/D66: Tier 3 (4 hipóteses de
    pricing/precision/settlement) testadas e refutadas:**
    - **D63 (Duration Non-Linearity)**: testou se payout ratio varia com a duracao do
      contrato. N=1200 proposals, 5 simbolos, 2 contract types, 8 duracoes (1-60 ticks),
      20 rounds. **Payout ratio = 1.920000 em TODAS as duracoes** com zero variancia
      (std=0.000000). Diferentemente do D57 (stake non-linearity confirmada por
      arredondamento de cents), a duracao nao afeta o payout ratio de forma alguma.
    - **D64 (Entry Spot Timing)**: testou se entry_spot difere do tick no momento do
      buy (staleness favoravel). N=30 trials, 3 validos (rate limit). entry_vs_tick_buy
      = [-0.10, -0.10, +0.14] — diferenca pequena e BIDIRECIONAL. spot_vs_tick_proposal
      = [0, 0, 0] — proposal spot sempre = tick atual. Entry_spot e capturado no proximo
      tick apos o buy, nao no tick atual. Nao ha staleness favoravel — a diferenca e de
      ~1 tick na direcao aleatoria, nao um atraso exploravel.
    - **D65 (Touch/No-Touch Barrier)**: testou se ONETOUCH/NOTOUCH expoe barrier explicita
      (D62 so testou CALL/PUT). ONETOUCH/NOTOUCH funcionam com barriers relativas (+5, -5)
      em tick e minuto. Porem **TODAS as proposals retornam barrier=None** — mesma
      limitacao do D62. Payout varia com barrier distance ($31.25 vs $3.06 vs $1.43),
      confirmando uso interno. API Deriv nao expoe barriers em nenhum contract type.
    - **D66 (Tick Count Settlement)**: testou se contratos sempre settle no numero exato
      de ticks. N=50 trials, 3 validos com tick_count reportado (todos dur=10 ticks):
      **tick_count=10, diff=+0 em 3/3**. Contratos sempre settle no numero exato de ticks.
      Nao ha variabilidade de settlement para explorar.
    - **Conclusão Deriv Tier 3**: D63-D66 (4 hipóteses de pricing/precision/settlement)
      TODAS refutadas. D47-D66 (20 hipóteses total) formam um bloco coeso: o ecossistema
      Deriv esta fechado para exploits de execução, race conditions, cross-symbol
      prediction, stake/duration arbitrage, sell manipulation, subscription timing, tick
      gaps, reconnection state, barrier precision, entry spot staleness e settlement
      variability.
43. **Follow-up 2026-07-11 (parte 4) — D67/D68/D69/D70: Tier 4 (4 hipóteses de
    info-edge/timing/resale/multi-contract) testadas:**
    - **D67 (Cross-Duration Info Edge)**: testou se saber o outcome de um contrato
      5-tick da edge em um contrato 10-tick simultaneo. N=35 trials. **35/35 LOST**
      em ambos 5t e 10t — 0% WR em CALL é estatisticamente impossível (p < 10^-10).
      Provável bug no wait_settle() (POC is_won não populado ou timeout). Sem
      variação (0 WON), não foi possível calcular P(10t|5t). INCONCLUSIVO.
    - **D68 (Tick Arrival Jitter)**: testou se há jitter sub-segundo na geração de
      ticks. N=300 ticks, 5min. **Server-side epoch diffs: 1.000s ± 0.000s** —
      servidor gera ticks perfeitamente regulares. Jitter local: 26.6ms (rede).
      Autocorrelação lag-1 = -0.72 (ping-pong de latência de rede, não servidor).
      Sem jitter previsível para explorar.
    - **D69 (Long-Duration Resale)**: ***DESCOBERTA SIGNIFICATIVA***. D58 concluiu
      "Resale not offered" mas só testou tick contracts. Sell ACEITO em 12/12 tests
      across ALL durations: 1m, 5m, 15m, 1h, 4h, 1d. Sell prices $0.87-$0.95,
      bid prices $0.87-$1.22, is_valid_to_sell=1 em todos. **ISTO REABRE a hipotese
      early-sell (HYP-SELL-01)** — agora pode ser re-testada com capacidade REAL de
      venda em durações 15m+. A pergunta mudou de "sell funciona?" para "sell no
      momento certo tem EV positivo vs hold-to-expiry?".
    - **D70 (Multi-Contract Entry Spot)**: testou se contratos simultaneos no mesmo
      símbolo recebem o mesmo entry_spot. N=20 trials, 60 contracts. **20/20 trials:
      entry_spots DIFERENTES** (spread médio 0.176, max 0.36). Mas os buys são
      sequenciais (0.3s apart), e o spread é apenas movimento aleatório do tick entre
      buys. Não é previsível qual contrato receberá o entry_spot favorável. P&L
      +$4.32 (WR=52%) — consistente com random walk.
    - **Conclusão Deriv Tier 4**: D67/D68/D70 refutados. D69 é a
      primeira DESCOBERTA não-refutada desde D47 — sell funciona em durações > tick,
      reabrindo early-sell. D47-D68, D70 (21 hipóteses) refutadas. D69 em validação.
44. **Follow-up 2026-07-11 (parte 5) — D67 corrigido + D71 Early-Sell Real Probe:**
    - **D67 (Cross-Duration Info Edge) CORRIGIDO**: bug no wait_settle() corrigido
      (is_won não populado antes de is_sold). Re-rodado com N=40. Resultado:
      P(10t WON | 5t WON)=0.867 (13/15), P(10t WON | 5t LOST)=0.200 (5/25),
      diff=+0.667. Mas isto é ARTEFATO MATEMÁTICO — o contrato 10-tick inclui os
      mesmos 5 ticks do 5-tick. Se os primeiros 5 ticks subiram, o 10-tick já está
      ITM e só precisa manter. Não é explorável diretamente (não dá para vender tick
      contracts). REFUTADO como artefato.
    - **D71 (Early-Sell Real Probe) — ***EDGE ENCONTRADO*****: re-testou HYP-SELL-01
      com metodologia corrigida (non-hindsight, pareado). N=30 trials, CALL/PUT 5m
      alternados em 1HZ10V. Hold-to-expiry: EV=-$0.040, WR=50%. Max bid ratio:
      mean=1.855, max=1.920. TODOS os thresholds 1.05-1.70 têm CI95% excluindo zero:
      threshold 1.05: diff=+$0.491 CI95%[+$0.070,+$0.915];
      threshold 1.10: diff=+$0.525 CI95%[+$0.109,+$0.941];
      threshold 1.30: diff=+$0.594 CI95%[+$0.205,+$0.993];
      threshold 1.50: diff=+$0.681 CI95%[+$0.318,+$1.063] (MELHOR);
      threshold 1.70: diff=+$0.671 CI95%[+$0.334,+$1.013];
      threshold 2.00: 0/30 triggered.
      Mecanismo: 1HZ10V (baixa volatilidade) oscila em torno do entry — bid chega
      perto do payout ($1.92) em quase todos os trials, mesmo os que perdem. Vender
      quando bid >= threshold trava o lucro antes do preço reverter.
      CAVEAT: poll de 2s pode superestimar sell price (bid salta de <1.30 para ~1.80
      entre polls). Mesmo com estimativa conservadora, o edge persiste.
      PROXIMO PASSO: D72 — validar com sells reais (fase 2).
45. **Follow-up 2026-07-11 (parte 6) — D72 Early-Sell REAL Validation (sells reais):**
    - **D72 (Early-Sell Real Validation) — REFUTADO / FALSO-POSITIVO D71**: validou
      D71 com sells REAIS usando metodologia A/B pareada (grupo A vende quando
      bid >= threshold, grupo B hold). N=40 trials, threshold 1.30, CALL/PUT 5m
      alternados em 1HZ10V.
      Resultado: Sell EV=-$0.037, WR=65% (15 sold, 5 expired). Hold EV=+$0.248,
      WR=65%. Diff (sell - hold)=-$0.285 CI95%[-$0.689,+$0.140] — INCONCLUSIVO
      mas point estimate NEGATIVO.
      **CAUSA RAIZ**: vender a bid_ratio ~1.30 trava lucro em ~$0.30, mas upside
      do hold é $0.92. Mesma WR (65%), hold tem EV muito maior. D71 superestimou
      sell price porque: (1) poll de 2s capturava picos de bid não realizáveis em
      sell real; (2) metodologia pareada de D71 usava mesmo contrato para sell_rule
      e hold, amplificando a diferença quando contrato perdia (sell salva de -$1.00,
      hold perde $1.00) mas ignorando que sell também corta upside (+$0.92 -> +$0.30).
      Segunda rodada com threshold 1.50 em andamento para confirmar.
    - **Conclusão D71+D72**: D71 edge era falso-positivo. Early-sell em 1HZ10V 5m
      não tem EV positivo vs hold-to-expiry. O ecossistema Deriv permanece fechado
      para early-sell exploitation.
46. **Follow-up 2026-07-11 (parte 7) — D73-D75 Tier 5 Deriv hypotheses:**
    - **D73 (Lookback Contract Fair Value) — REFUTADO por não-existência**: nenhum
      contract type LOOKBACK encontrado em 5 símbolos. 35 tipos disponíveis na API
      (ACCU, ASIAND, ASIANU, CALL, CALLE, DIGITDIFF, ..., VANILLALONGPUT), nenhum
      é LOOKBACK. Produto não existe na Deriv.
    - **D74 (Proposal Expiry Window) — REFUTADO**: proposal IDs permanecem válidos
      por 30+ segundos, mas entry_spot é SEMPRE T+1 (próximo tick após buy) — nunca
      igual ao proposal_spot (0/45) nem ao tick_at_buy (0/45). Delaying buy não dá
      optionality porque entry é sempre o próximo tick, independente de quando a
      proposal foi feita. N=45 trials, 9 delays (0-30s).
    - **D75 (Tick Spectral Analysis) — MARGINAL/REFUTADO**: Hurst em returns
      0.62-0.65 (mild trending) em TODOS os 8 símbolos. VR rejeita RW em q=10 para
      3/8 (1HZ10V z=-2.63 p=0.009). MAS Ljung-Box não rejeita em nenhum, FFT
      spectral entropy 0.93-0.94 (quase white noise), max autocorrelation 0.05.
      Sinal muito fraco — consistente com D46 (N=190k) que já mostrou micro-sinal
      menor que house margin. CAVEAT: apenas 1000 ticks (limite API).
    - **D76 (Early-Sell + Directional Signal) — REFUTADO**: N=90 (3 signals x 15
      sell + 15 hold). Momentum: diff=+$0.388 CI95%[-$0.087,+$0.859] — melhor sinal
      mas CI cruza zero. Mean reversion: diff=-$0.037 CI95%[-$0.507,+$0.456]. Tick
      direction: diff=+$0.043 CI95%[-$0.570,+$0.665]. Todos inconclusivos. Sinal
      direcional nao melhora early-sell EV suficiente.
47. **Follow-up 2026-07-11 (parte 8) — D77/D80/D81/D86 Tier 6 hypotheses:**
    - **D77 (Untested Contract Types) — REFUTADO**: MC mostrou PUTE P(win)=70%
      aparentando edge, mas D82 validacao com trades reais refutou: Run 1 (N=20)
      WR=70% foi falso-positivo; Run 2 (N=20) WR=45% regressou a media. Combinado
      WR=57.5% nao significativo. CALLE espelho tambem era viés de amostra.
      RESETCALL/RESETPUT: EV negativo. TURBOS: nao disponivel. UPORDOWN: requer
      barrier. Todos os 7 tipos refutados.
    - **D80 (Weekend Volatility) — REFUTADO**: API retorna apenas ~5000 ticks
      recentes (~1.4h), não cobre weekend. Max/Min vol ratio por hora = 1.03x
      (constante). RNG da Deriv é constante 24/7.
    - **D81 (Buy Limit Order) — REFUTADO**: Deriv rejeita 100% dos buys com
      price < ask_price. Erro: "Contract's stake amount is more than maximum
      purchase price". Apenas price = ask_price sucede.
    - **D86 (Straddle Arbitrage) — REFUTADO**: 0/330 oportunidades. Spread sempre
      -$0.08 (CALL+PUT) ou -$0.09 (CALLE+PUTE). Deriv precifica straddle
      corretamente: ask_total = 2 * stake, payout = 1.92 * stake, house margin
      embutida.
    - **D72 t150 (Early-sell threshold 1.50) — INCONCLUSIVO**: N=40, sell EV=+$0.008,
      hold EV=-$0.040, diff=+$0.048, CI95%[-$0.506,+$0.591]. CI cruza zero. Sell WR=60%,
      hold WR=50%. 14/20 sold, 6/20 expired. Precisa mais N para conclusão.
48. **Follow-up 2026-07-12 — D87-D90: novas hipóteses Deriv:**
    - **D87 (Complementary Exotic Pair Arbitrage) — REFUTADO no grid calibrado**:
      80/80 cotações válidas em ONETOUCH/NOTOUCH, EXPIRYRANGE/EXPIRYMISS e RANGE/UPORDOWN
      para 1HZ10V e R_100. Nenhum `min(payout) - ask_total` positivo. Melhor spread = -$0.24;
      pior = -$0.99. A margem da casa também aparece nos pares exóticos complementares.
    - **D88 (E-Suffixed Contract Variants) — REFUTADO no escopo cotável**:
      `EXPIRYMISSE` e `EXPIRYRANGEE` não foram oferecidos nos símbolos testados. `CALLE/PUTE`
      produziram 8 células válidas, todas com EV negativo e nenhuma passou o gate DGP. A tentativa
      em `frxEURUSD` ocorreu com o mercado fechado, sem amostra de preço.
    - **D89 (Cross-Market Pricing) — INCONCLUSIVO**: o controle sintético teve 24 células válidas,
      todas negativas, com melhor `EV_lo=-$0.0549`. Nova tentativa (2026-07-12) com `frxEURUSD`
      retornou *This market is presently closed* (fim de semana). `1HZ10V` 15m CALL/PUT teve EVlo
      negativo; nenhum gate candidate. Requer nova coleta em horário de mercado aberto.
    - **D90 (Long-Duration Early-Sell A/B) — EM VALIDAÇÃO DEMO**: o script foi iniciado com
      `--live`, 20 pares por duração, 15m/1h, threshold 1.5x e stake de US$1. Interim: 3 pares 15m
      concluídos — sell 0.54/0.51/0.53 vs hold 0.92/0.92/-1.00. O veredito final e o IC95% serão
      registrados após a coleta.
    - **D91 (Accumulator Survival Edge) — REFUTADO**: o scan testou 630 células de símbolo,
      growth rate e ticks-alvo, sem nenhum `EV_lo > 0`. A validação independente com 5.000 ticks
      reais de `1HZ100V` encontrou P(sobreviver 1 tick) abaixo da probabilidade fair para todos os
      growth rates. Nenhum ACCU foi comprado.
    - **D92 (Jump Indices Spike Timing) — REFUTADO**: 50k ticks por símbolo (JD10/JD25/JD50/JD75/JD100),
      30-34 saltos detectados (>10x mediana). Direção UP: 50.0%-63.3% com IC95% incluindo 50% em todos.
      CV 0.94-1.53 (compatível com memoryless). Hazard rates 0.000%-0.201% sem tendência crescente.
      Nenhum sinal de temporizador ou viés direcional.
    - **D93 (HIGHER/LOWER Barrier Mispricing) — REFUTADO**: 31 células (HIGHER/LOWER × 6/10 barriers
      × 5/10 ticks) em `1HZ10V`. 0 células com `EV_lo > 0`. EV médio -$0.6981, min -$8.34, max -$0.10.
      A Deriv cobra margem consistente; razão payout/fair no melhor caso ~0.99. Sem mispricing.
    - **D94 (E-Suffixed Variants em 1HZ100V) — REFUTADO**: 30 células testadas
      (EXPIRYMISSE/EXPIRYRANGEE intraday, CALLE/PUTE 5t/10t/1m/5m). EXPIRYMISSE/EXPIRYRANGEE só
      existem como daily (barreiras absolutas 883.08/964.42) e não aceitam durações intraday.
      CALLE/PUTE: 8/8 células com EV negativo (melhor EV=+0.053, mas EV_lo=-0.066), 0 gate candidates.
    - **D95 (Deal Cancellation Mispricing em Volatility Indices) — INCONCLUSIVO (atualizado 2026-07-12)**:
      scans read-only de 3 símbolos refeitos com **cap no payoff em stake** (a cancellation só devolve o
      stake, não o multiplicador completo). **Resultado corrigido:** 400x/60m é negativo em todos os
      símbolos. Células com edge_lo > 0: 40x-200x/5m-15m em 1HZ100V/R_100, 80x/200x/400x 5m-15m em 1HZ50V.
      **Live 5m DEMO 400x (1HZ100V, MULTUP/MULTDOWN, N=20):** valor realizado médio $0.37 vs fee $0.41,
      EV -$0.04 por trade, IC95% cruza zero. **Live 5m DEMO 100x (1HZ100V, N=20):** valor realizado médio
      $0.1705 vs fee $0.1100, EV +$0.0605 por trade, IC95% [$-0.0130, +$0.1510], também cruza zero.
      Nenhuma célula tem edge confirmado ao vivo; não abrir novo trial sem desenho pré-registrado.

41. **Remediação operacional EC2 (2026-07-12)**:
    - **D17**: `unlock_data.py` passou a aplicar o mínimo configurado de $20M em respostas Tokenomist;
      `unlock_short_bot.py` passou a respeitar a janela UTC de entrada/saída. As 2 posições paper
      legadas abaixo do mínimo foram preservadas e marcadas `out_of_policy_legacy`; nenhuma nova
      entrada fora da política foi aberta.
    - **D31**: parser de instrumentos Deribit corrigido para `currency-expiry-strike-type`; validação
      contra a API retornou 46 opções BTC 13JUL26 com strike numérico e tipo C/P. O bot foi reiniciado
      e aguarda a janela 13JUL 07:30 UTC.
    - **D55**: estado sem ciclos foi arquivado, a coorte v2 iniciou com custo de entrada e saída de
      9.5bps cada, e a liquidação agora usa primeiro histórico Binance de fundings concluídos.
    - **D36**: 111 settles e 342 posições abertas do período sem limite foram preservados como
      `legacy_unbounded` e excluídos de inferência; a coorte `capped_v2` começou com 6 de 10 posições.
    - **D34, D38, D39, D41 e D56**: sessões encerradas e removidas da recuperação automática.
      D34/D38/D39 ficaram pausados; D41 e D56 já estavam refutados. Backup remoto:
      `backups/remediation_20260712T171852Z`.
    - **D90 local**: não foi tocado, interrompido ou migrado.

42. **Auditoria completa da frota AWS (2026-07-13 19:03 UTC)**:
    - **D39 max_pain_tracker (PID 3339) PARADO**: a doc do item 41 marcou D39 como pausado e
      removido do supervisor, mas o processo `max_pain_tracker.py --continuous` (tmux
      `d39_maxpain`, PID 3339 desde 5 Jul) ainda estava rodando — o kill do tmux session
      na remediação 2026-07-12 não atingiu o processo Python que estava em pts/2. Killado
      manualmente nesta auditoria. O kill causou crash do tmux server, derrubando todas as
      11 sessões ativas. Supervisor + 8 processos gerenciados + D90 + d31_d55_monitor
      foram reiniciados a partir dos state files; todos os 10 processos saudáveis pós-restart.
    - **D90 (long-duration early sell)**: **COMPLETO (40/40 pares)**. 20 × 15m + 20 × 1h,
      threshold 1.5, 1HZ10V. **15m:** sell EV +$0.309, hold EV +$0.536, diff −$0.227
      IC95%[−$0.65, +$0.22]. **1h:** sell EV +$0.019, hold EV +$0.344, diff −$0.326
      IC95%[−$0.84, +$0.20]. Point estimate NEGATIVO em ambas durações (sell < hold).
      IC95% cruza zero estatisticamente, mas padrão consistente com early_sell_multi N=1870:
      hold supera sell. Early-sell optionality refutado em todas as durações testadas
      (5t/10t/25t/50t N=1870 + 15m/1h N=40). Processo completou e parou naturalmente.
    - **D55 (Hyperliquid LINK funding arb)**: 4 ciclos v2 completados. Cycle 1: −2.38 bps,
      Cycle 2: +5.28 bps, Cycle 3: −4.51 bps, Cycle 4: +7.03 bps. Total: −4.08 bps (−$0.41).
      WR 50% (2/4). Cycle 4 foi o melhor: funding_pnl +0.887bps + mark_pnl +6.144bps.
      Próximo ciclo às 08:00 UTC. Custo de entrada (−9.5 bps) ainda não recuperado,
      mas trajetória melhorando (2 últimos ciclos positivos).
    - **D29/Basis (Basis-funding disconnect)**: N=44, WR 70.5% IC95%[55.8%, 81.8%],
      EV +0.3284% IC95%[−0.47%, +1.21%]. WR exclui 50% (significativo), EV ainda cruza zero.
      Precisa N~60-80 para IC do EV convergir. Melhor lead operacional ativo.
    - **D17/Unlock**: 3 posições paper open (APT $7M out_of_policy_legacy, SEI $2.7M
      out_of_policy_legacy, ARB $30M in_policy_v2 unlock 2026-07-16). 0 closed trades.
      Bloqueado apenas por depósito de capital real.
    - **HYP-OPTBUY-01 (Options paper bot)**: 3 closed (todas loss, −$1507.93 total),
      13 open. N=3/30 mínimo para veredito preliminar. Próximo ciclo em 6h.
    - **D31/TWAP**: 1 trade completo (+12.9% PnL). Aguardando próxima janela TWAP
      (14JUL 07:30 UTC, ~12h). Parser corrigido 2026-07-12.
    - **D36 (IV anomaly) capped_v2**: 10/10 posições abertas, 0 settled. Próximo scan
      em 60min. Coorte legacy_unbounded preservada (111 settles, WR 41.4%, +$2.948)
      mas excluída de inferência.
    - **D37 (Exchange outflow)**: rodando contínuo, forward-return tracker ativo,
      0 sinais resolvidos (todos NO SIGNAL). Precisa de evento real de outflow >$5M.
    - **D89 (Cross-market pricing)**: **REFUTADO (2026-07-14, N=120 células forex)**.
      10 pares forex (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURGBP,
      EURJPY, GBPJPY) × 4 types (CALL/PUT/CALLE/PUTE) × 3 durations (15m/1h/4h).
      40k ticks/símbolo, MC 10k sims. **0 gate candidates** (nenhuma célula com EVlo > 0).
      Mean EV = -$0.119, best EVlo = -$0.064 (GBPUSD PUT 1h). House margin forex ~12%
      (MAIOR que sintéticos ~4% — forex tem spread bid-ask + overnight risk).
      Pemp vs Pmc alinhado (DGP divergence < 0.03). 4h durações têm poucas windows
      (2-3 non-overlapping) — não confiáveis. 15m e 1h com ~1000+ windows, conclusivos.
      Scripts: `d89_cross_market_scan.py`.
    - **Processos confirmados PARADOS/REFUTADOS (não reiniciar)**: D39 (paused,
      sem convergência), D34 (paused, 0 cascades), D38 (paused, sem amostra tradeable),
      D41 (refutado por fees), D52 (refutado N=120), D56 (refutado), D89 (refutado,
      120 células forex, 0 gate candidates), D90 (refutado, 40/40 pares completos,
      hold > sell), D95 (paused, IC cruza zero), D96-D100 (refutados, house margin
      consistente), HFT-01 (refutado N=34), early_sell_multi (re-refutado N=1870).

43. **D96-D99: Bug/exploit scan Deriv sintéticos (2026-07-13 20:06-21:00 UTC)**:
    - **D96 (Flat Tick Frequency + RNG Deep Analysis) — REFUTADO**: 50k ticks baixados
      para 17 símbolos sintéticos. P(flat tick) medido para todos: max = JD100 9.06%
      (CI95% [8.81%, 9.31%]), abaixo do breakeven de 11.11% para straddle CALLE+PUTE
      lucrativo. Todos os 17 símbolos refutados. RNG deep analysis: Hurst ~0.55 universal
      (slight trending, não explorável), CRASH1000 Ljung-Box p=0.0047 (autocorrelação
      significativa mas efeito r≈2.25% insuficiente vs house margin 4%), JD100 Runs z=3.016
      (trending). Nenhum teste estatístico mostrou desvio explorável de aleatoriedade pura.
      Scripts: `d96_flat_tick_frequency_scan.py`.
    - **D97 (Payout Curve Deep Scan) — REFUTADO**: 1874 células escaneadas (23 contract
      types × 9 durations × 11 symbols × 3 stake sizes). 32 anomalias de payout ratio
      detectadas (>mean+2std), todas RUNHIGH/RUNLOW com ratio 30.53x (5 ticks). 598
      anomalias de stake-dependence (diferença max 0.0032, insignificante). 0 anomalias
      de duration curve. 0 oportunidades de straddle arb (CALL+PUT ask >= payout em 100%
      das células). House margin ~4% consistente em todos os contract types, durations,
      symbols e stakes. Scripts: `d97_payout_curve_scan.py`.
    - **D98 (Instant Resale Flip Scanner) — REFUTADO (v2 corrigido)**: v1 teve bug
      (campo `ask_price` em vez de `bid_price` para resale). v2 corrigida: 250 células,
      80 células válidas (3 trades/cell). 17 células com "flip edge" (≥1/3 trades com
      resale > buy), 12 com avg_flip_ratio > 1.0. Melhor: R_100 CALL 5t ratio=1.56x
      (2/3 flips, +$0.56/cell). MAS: resale price é $0.92 (loss) ou $1.88 (win) —
      binário, não gradiente. Isso é exposição direcional (contract foi ITM/OTM nos
      primeiros ticks), não flip estrutural. Mean avg_flip_ratio = 0.9427 (< 1.0),
      consistente com house margin absorvendo o resale. "Flip edges" são apenas células
      onde 1-2 dos 3 trades aleatoriamente foram ITM no momento do check. Scripts:
      `d98_resale_flip_scan.py`.
    - **D99 (RUNHIGH/RUNLOW Validation) — REFUTADO**: D97 flagou RUNHIGH/RUNLOW 5t com
      payout ratio 30.53x como anômalo. `longcode` revelou condição real: "rises/falls
      successively for 5 ticks" (5 ticks consecutivos na mesma direção), não "último
      tick = máximo". P(win) teórico = (0.5)^5 = 3.125%, breakeven = 3.28%, house margin
      = 4.8%. Validado com 58 trades DEMO: RUNHIGH 0/28 wins, RUNLOW 1/30 wins (3.33%).
      WR combinada 1.72% CI95%[0.3%, 9.2%], consistente com 3.125% teórico. Mesmo padrão
      de house margin ~4.8% em todos os contract types exóticos. Scripts:
      `d99_runhigh_validation.py`.
    - **D100 (Proposal Staleness Exploit v2) — REFUTADO**: D47 testou stale proposal
      com 20s de delay; D54 descobriu que subscribe:1 nunca reenvia. D100 testou a
      janela crítica em milissegundos: RACE (0ms delay, lag médio 193ms) vs CONTROL
      (2000ms delay). N=60 trials (30 RACE + 30 CONTROL), 1HZ10V, 10 ticks, CALL/PUT
      alternados. RACE WR=43.3% EV=-$0.17 vs CONTROL WR=53.3% EV=+$0.02. RACE WR <
      CONTROL WR — staleness não ajuda, pelo contrário. spot_diff entre proposal e
      entry é aleatório (sem viés direcional). Lag de ~193ms é insuficiente para
      capturar movimento favorável. Scripts: `d100_proposal_staleness_v2.py`.
    - **D101 (Barrier Proximity Edge) — INCONCLUSIVO (N pequeno)**: Scan de payout
      ratios para DIGITOVER/DIGITUNDER com barreiras 0-9: payout varia de 1.09x
      (barrier=0/9, 90% P(win)) a 8.33x (barrier=8/1, 10% P(win)) — perfeitamente
      inverso à probabilidade, house margin consistente. Live DEMO: 6 barreiras × 20
      trades = 120 trades. DIGITOVER_0 e DIGITUNDER_9: WR=95% (19/20), breakeven=91.74%,
      EV=+$0.04/trade, CI95% cruza breakeven. DIGITOVER_5 e DIGITUNDER_4: WR=50% vs
      teórico 40%, breakeven 42.02%, EV=+$0.19/trade — mas CI95% [29.9%, 70.1%] cruza
      breakeven. Nenhuma barreira tem edge confirmado. Diferença theoretical vs actual
      WR é +5-10pp em 4/6 barreiras, mas com N=20 isso é dentro do ruído estatístico.
      Scripts: `d101_barrier_proximity_edge.py`.
    - **D102 (Crypto Contract House Margin Scan) — REFUTADO por design de API**: Testou
      cryBTCUSD, cryETHUSD, cryLTCUSD, cryXRPUSD, cryDSHUSD com CALL/PUT/CALLE/PUTE em
      durações de 1d a 30d. Todos os 140 proposals retornaram "Trading is not offered
      for this asset." Probe confirmou que crypto na Deriv SÓ suporta Multipliers
      (MULTUP/MULTDOWN) — não há binary options para crypto. Multipliers não têm payout
      ratio (payout=0), são produtos de alavancca sem house margin estrutural da mesma
      forma. Não há edge de house margin para explorar em crypto. Scripts:
      `d102_crypto_house_margin.py`, `probe_crypto_contracts.py`.
    - **D103 (Tick Arrival Timing Prediction) — REFUTADO (timing perfeitamente
      determinístico, sem edge)**: Coletou 4,563 ticks em 6 símbolos (1HZ10V, 1HZ50V,
      1HZ100V, R_10, R_100, cryBTCUSD) por 15 minutos via subscription callback.
      Resultado: TODOS os símbolos têm timing perfeitamente determinístico — 1HZ e
      cryBTCUSD: exatamente 1.0000s entre ticks (std=0, CV=0, jitter=0); R_10/R_100:
      exatamente 2.0000s. Zero variância, zero autocorrelação. O timing é 100%
      previsível mas isso não gera edge porque o VALOR dos ticks é o que determina
      P(win), não o timing. A Deriv entrega ticks em intervalos fixos perfeitos —
      não há jitter para explorar. Scripts: `d103_tick_timing_prediction.py`.
    - **D104 (Duration Boundary Pricing Discontinuity) — REFUTADO (payout curve smooth)**:
      Scan de payout ratios para CALL/PUT/CALLE/PUTE/DIGITEVEN/DIGITODD em 1HZ10V e
      R_100, durações 1t a 50t. Hipótese: descontinuidade de pricing na fronteira
      5t→6t (mudança de "short" para "medium" duration). Resultado: payout ratio
      constante 1.92x em TODAS as durações para TODOS os contract types. Zero
      descontinuidades. A Deriv precifica duração de forma perfeitamente smooth —
      não há edge em boundary transitions. Scripts: `d104_duration_boundary.py`.
    - **D105 (Multi-Leg Digit Combination Arbitrage) — REFUTADO (house margin previne
      arb)**: Testou combinações 2-leg (DIGITOVER(N) + DIGITUNDER(N+1) = full cover)
      e 3-leg em 7 símbolos (1HZ10V, 1HZ50V, 1HZ100V, R_10, R_25, R_50, R_100),
      durações 1t e 10t. Hipótese: combinar múltiplas pernas digit pode cobrir todos
      os outcomes com payout total > stake. Resultado: 0 arbitragem garantida em
      todas as 56 combinações. Best EV: -$0.05/trade (2-leg full cover). House margin
      de ~4% por perna faz o payout total ser sempre < stake quando se cobre todos
      os outcomes. Scripts: `d105_multi_leg_digit_arb.py`.
    - **Conclusão D96-D105**: Deriv precifica TODOS os 35+ contract types com house margin
      consistente de ~4-5%. O payout ratio é inversamente proporcional à probabilidade
      de vitória, mantendo EV negativo independente do tipo de contrato, duração, símbolo
      ou stake size. "Anomalias" de payout ratio são apenas contract types com payout
      alto e probabilidade proporcionalmente baixa — não são mispricing. Edge estrutural
      fixo confirmado como inexistente em TODOS os contratos Deriv. Tick timing é
      perfeitamente determinístico (zero jitter) mas não gera edge. Payout curve é
      smooth em todas as durações. Multi-leg arbitrage é previnido pela house margin
      cumulativa. Crypto só suporta Multipliers (sem binary options). Bug/exploit
      transitório permanece a única via possível (monitor de anomalias em tempo real
      é o instrumento correto).

    - **REAL-TIME ANOMALY MONITORING (24/7 na AWS)**: Duas camadas de monitoramento
      rodando continuamente no EC2 eu-central-1b:

      **Monitor 1: synthetic_anomaly_monitor.py** (tmux: anomaly_monitor)
      - 17 símbolos: 1HZ10V/25V/50V/75V/100V, R_10/25/50/75/100, BOOM1000, CRASH1000,
        JD10/25/50/75/100
      - 5000 ticks de priming por símbolo, janela deslizante de 3000 ticks
      - Detectores: RNG_BIAS (chi-square digit distribution), RNG_RUNS (runs test
        up/down), FEED_FREEZE (ticks identicos consecutivos), FEED_TIMING (intervalo
        anômalo), EV_EDGE (Wilson CI positivo com vet de amostra fresca),
        SPIKE_TIMING (cadência de spikes Boom/Crash), FEED_STALL (watchdog silencio)
      - Evidência: logs/anomaly_monitor/anomalies.jsonl
      - Status: rodando, heartbeats normais (chi2 < 15, bestEV_lo negativo em todos,
        sem anomalias RNG/feed detectadas)

      **Monitor 2: d106_pricing_anomaly_monitor.py** (tmux: d106_pricing)
      - 10 símbolos: 1HZ10V/25V/50V/75V/100V, R_10/25/50/75/100
      - 8 contract types: CALL, PUT, DIGITEVEN, DIGITODD, DIGITOVER:5, DIGITUNDER:4,
        DIGITDIFF:0, DIGITMATCH:5
      - 3 durações (1t, 5t, 10t) × 4 stakes ($0.35, $1, $10, $100) = 960 proposals/ciclo
      - Detectores: PAYOUT_RATIO_ANOMALY (desvio vs expected teórico), PAYOUT_RATIO_CHANGE
        (mudança súbita vs rolling baseline), SPOT_MISMATCH (proposal spot vs live tick),
        RESALE_ARB (buy → sell instant profit), CONTRACT_AVAILABLE/UNAVAILABLE
        (disponibilidade muda entre ciclos), STAKE_DEPENDENT_PAYOUT (payout varia >6%
        com stake)
      - Evidência: logs/d106_pricing_anomalies.jsonl
      - Calibração: house margin empiricamente calibrada por contract type
        (50/50: ~4%, DIGITMATCH P=10%: ~10.7%, DIGITDIFF P=90%: ~2.2%)
      - Status: rodando, 10 anomalies MEDIUM no 1o ciclo (DIGITMATCH payout varia por
        símbolo — estrutural; contract availability flickering — rate limiting).
        Zero CRITICAL, zero RESALE_ARB, zero SPOT_MISMATCH.

      **Conclusão do monitoramento**: Nenhum bug/exploit transitório detectado nas
      primeiras horas. Sistema rodando 24/7 e alertará se:
      - Payout ratio mudar >15% do esperado (mispricing bug)
      - Buy → instant resale > buy cost (resale arb bug)
      - Proposal spot divergir do live tick (staleness bug)
      - RNG se desviar da uniformidade (RNG bug)
      - EV_lo cruzar margem de custo com persistência (edge transitório)
      - Spikes Boom/Crash mudarem de cadência (gerador bug)
