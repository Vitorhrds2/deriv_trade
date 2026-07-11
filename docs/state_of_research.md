# Estado da Pesquisa — Consolidado (2026-07-04)

**Propósito:** fonte única de verdade sobre todas as hipóteses de edge já testadas neste
repositório, seu veredito, e o que ainda está em aberto. Consolidado após o merge de
`feat/synthetic-anomaly-monitor` em `main` (commit `9cf907e`) trazer de volta várias frentes
de pesquisa paralelas. Atualizar esta tabela sempre que uma hipótese nova fechar veredito.

## TL;DR

**64 hipóteses testadas. 57 refutadas (D59 POC subscription vs poll REFUTADO 2026-07-11 30/30 SUB nunca notificou, D60 tick gap REFUTADO 2026-07-11 626 ticks 0.80% missing apenas startup, D61 reconnection state REFUTADO 2026-07-11 0/13 barrier mismatches, D62 barrier rounding REFUTADO 2026-07-11 253/253 barrier=None CALL/PUT, D56 cross-symbol correlation REFUTADO 2026-07-11 N=2081 ticks 0/36 pares significativos, D57 stake non-linearity CONFIRMADO mas nao exploitavel 2026-07-11 payout ratio 1.886 em $0.35 vs 1.923 em $100, D58 sell limit order REFUTADO 2026-07-11 50/50 sells rejeitados 'Resale not offered', D40 stablecoin mint REFUTADO 2026-07-10 WR=0% 24h, D44 funding extremo REFUTADO 2026-07-10 IC95% negativo, D52 deal cancellation REFUTADO 2026-07-09 N=120 EV encolhendo monotonicamente, D41 wash trading REFUTADO por fees 2026-07-08 WR 66% mas EV < 10bps), 2 com sinal fraco/marginal (D13, D14), 1 com edge validado (D17 — token unlock short, POSIÇÃO AO VIVO APTUSDT desde 2026-07-09), 1 com edge parcialmente confirmado (D36 — IV surface BUY side, N=58 WR RECUPEROU para 41.4%, total=+$2,948, pode não ser falso-positivo), 2 aguardando eventos (D34 — liquidation cascade, D39 — max pain), 3 em validação inicial (D37, D38, D55). D46 (Deriv tick mean-reversion) **REFUTADO em 2026-07-06 com N=190.000**. **D47-D62 todos REFUTADOS.** **D55 (Hyperliquid vs Binance) paper trading OOS ativo desde 2026-07-08, LINK como único candidato.**
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
