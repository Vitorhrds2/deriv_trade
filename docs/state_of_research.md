# Estado da Pesquisa — Consolidado (2026-07-04)

**Propósito:** fonte única de verdade sobre todas as hipóteses de edge já testadas neste
repositório, seu veredito, e o que ainda está em aberto. Consolidado após o merge de
`feat/synthetic-anomaly-monitor` em `main` (commit `9cf907e`) trazer de volta várias frentes
de pesquisa paralelas. Atualizar esta tabela sempre que uma hipótese nova fechar veredito.

## TL;DR

**46 hipóteses testadas. 36 refutadas, 2 com sinal fraco/marginal (D13, D14), 1 com edge validado em 3 períodos (D17 — token unlock short), 1 com edge parcialmente confirmado (D36 — IV surface BUY side 100% WR), 1 aguardando eventos (D34 — liquidation cascade), 5 novas em validação inicial (D37-D41 — hipóteses agressivas).**
O padrão se repete de forma notável: quando existe algum micro-sinal real (H1, H3, T4, PA5, D33, D35), ele é
**sempre menor que o custo de transação** (comissão/spread). Quando não há sinal real, a causa é
**margem da casa embutida no payout**, matematicamente presente em todo contrato testado (dígitos,
touch/no-touch, range, vanillas, accumulators, jump indices, multipliers, higher/lower, tickhigh,
runs, asian, reset, turbos). Nenhuma hipótese sobreviveu a controle nulo + IC95% + segunda fonte
independente, exceto D17 (edge validado) e D36 (anomalias reverting, aguardando P&L).

**Todos os 14 produtos Deriv ativos na API estão agora exaustivamente testados e refutados.**
O ecossistema Deriv está fechado para mispricing de produtos. O Polymarket também está fechado
(PA1-PA5 todos refutados). As frentes **ainda em aberto** são: D17 (token unlock, bot em paper),
D34 (liquidation cascade, loop contínuo na AWS), D36 (IV surface anomaly, paper bot ativo na AWS),
e Early sell optionality (trial 32/50 na AWS).

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
| 15 | `hft_bot` V6.2 (produção) — implementação ao vivo de H3 | Deriv `cryBTCUSD` sintético | `docs/hft_v62_audit_report.md` | N=40, WR 22.5%, EV/trade -$3.02, IC95% [-4.70,-1.18] não cruza zero. Pior de 6 configs testadas |
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
| 14 | Early sell optionality | Trial 32/50 na AWS | 15 sell wins vs 17 hold wins. Tendência mudou — era 75% sell antes, agora hold está vencendo. Aguardando N=50 |
| 15 | Synthetic Anomaly Monitor | Rodando 24/7 (Carlos) | Inacessível neste servidor; sem achado confirmado reportado |
| 16 | PA1-PA4 Polymarket | Refutado | PA3: 940 mercados, 0 arb. PA2: diff=0bps. PA1: spread=100bps desde criação. PA4: refutado via PA5 |
| 17 | D17 — Token unlock short | Bot em paper na AWS | Edge validado IS+OOS-2025+OOS-2026. unlock_short_bot.py rodando, primeiro trade APTUSDT 9 Jul. Próximo: depositar USDT e ir live |
| 18 | D34 — Liquidation cascade | Loop contínuo na AWS | 0 cascades em 30min (mercado calmo). Bot reiniciado em loop infinito. Precisa dias para capturar eventos |
| 19 | D36 — IV surface anomaly | Paper bot ativo na AWS | 6/6 anomalias reverting (0 stale). Backtest BS: BUY 7/7 wins +$4,500 (100% WR), SELL 0/9 wins -$792 (bid-ask spread artifact). **Edge parcialmente confirmado — BUY only** |
| 20 | D37 — Exchange outflow signal | Scan inicial | APIs free tier limitadas (Whale Alert 401). Sem dados em tempo real. Necessário API key |
| 21 | D38 — Binance announcement front-run | Scanner funcional | API Binance retorna 80 anúncios em 8 catalogs. Polling 3s. 0 novos em 60s (esperado). Deploy AWS para capturar listing real |
| 22 | D39 — Options max pain magnet | Dados em tempo real | Max pain 10JUL26: BTC $61k vs spot $63.4k (+3.86%), ETH $1,700 vs $1,788 (+4.90%). SHORT toward max pain. Trackear até expiry |
| 23 | D40 — Stablecoin mint signal | Dados em tempo real | DefiLlama: $309.5B supply, 3d change -$337M (redemption, bearish). Sem sinal bullish. Etherscan API key necessária para real-time |
| 24 | D41 — WS trade anomaly detector | Scan funcional | 5,235 trades em 120s. 0 dup IDs (não há wash trading). 150 clusters (2.87%, provável TWAP/VWAP). Buy pressure em 3/3 símbolos |

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
22. **IV surface anomaly — EDGE PARCIALMENTE CONFIRMADO** (D36). Backtest BS model-based:
    BUY side 7/7 wins +$4,500 (100% WR), SELL side 0/9 wins -$792 (bid-ask spread
    artifacts em deep ITM). Top BUY: BTC-26MAR27-115000-C +$1,289 (172% ROI).
    Theta decay mínimo após 7d. Reversion test: 6/6 reverting (0 stale).
    **Próximo: ajustar paper bot para BUY only, validar settles reais.**
23. **Liquidation cascade — AGUARDANDO EVENTOS** (D34). 0 cascades em 30min
    (mercado calmo). Bot rodando em loop contínuo na AWS. Cascades são raras
    mas quando ocorrem, continuation é quase garantida (forced selling).
    Precisa dias/semanas para capturar eventos durante volatilidade alta.
24. **Status consolidado**: 46 hipóteses, 36 refutadas, 2 com sinal fraco/marginal,
    1 com edge validado (D17), 1 com edge parcialmente confirmado (D36 BUY only),
    1 aguardando eventos (D34), 5 novas em validação inicial (D37-D41).
    **Foco: D17 go live + D36 paper bot settles + D39 max pain trackear até 10JUL26 +
    D38/D41 deploy AWS em loop contínuo + D37/D40 obter API keys.**
25. Sincronizar com o Carlos sobre `feat/operate-demo-synthetic` antes de tocar em
    `hft_arbitrage_bot.py` de novo.
