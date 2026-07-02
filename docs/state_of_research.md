# Estado da Pesquisa — Consolidado (2026-07-02)

**Propósito:** fonte única de verdade sobre todas as hipóteses de edge já testadas neste
repositório, seu veredito, e o que ainda está em aberto. Consolidado após o merge de
`feat/synthetic-anomaly-monitor` em `main` (commit `9cf907e`) trazer de volta várias frentes
de pesquisa paralelas. Atualizar esta tabela sempre que uma hipótese nova fechar veredito.

## TL;DR

**10 hipóteses testadas até agora nos sintéticos Deriv e em BTC/cripto. Todas refutadas.**
O padrão se repete de forma notável: quando existe algum micro-sinal real (H1, H3, T4), ele é
**sempre menor que o custo de transação** (comissão/spread). Quando não há sinal real, a causa é
**margem da casa embutida no payout**, matematicamente presente em todo contrato testado (dígitos,
touch/no-touch, range, vanillas, accumulators, jump indices). Nenhuma hipótese sobreviveu a
controle nulo + IC95% + segunda fonte independente.

As duas frentes **ainda em aberto** (não refutadas nem confirmadas) mudam de categoria: não
tentam vencer a margem/custo com sinal mais forte, tentam explorar algo **transiente** (bug,
mispricing momentâneo, book desatualizado) — filosofia diferente das 10 anteriores.

## Hipóteses refutadas — sem edge (margem da casa embutida no payout)

| # | Hipótese | Produto | Relatório | Achado central |
|---|---|---|---|---|
| 1 | Oráculo Dinâmico (DIGITDIFF + Virtual Loss) | Deriv sintéticos | `docs/edge_investigation_report.md` | IC95% real abaixo do break-even; todos os 46 contratos testados têm EV negativo |
| 2 | Accumulators (ACCU) | Deriv sintéticos | `docs/accumulator_edge_report.md` | Falso positivo de amostra pequena capturado; com 5.000 ticks reais, EV negativo em toda grade growth_rate×N |
| 3 | Jump Indices (JD10-100) — direção e timing | Deriv sintéticos | `docs/jump_index_report.md` | Direção 50/50 confirmada; timing memoryless confirmado; sinal candidato (92.9% UP) era fluke de N=14, sumiu em N=50 |
| 4 | Vanilla Options — mispricing vs. valor justo | Deriv sintéticos | `docs/vanilla_options_report.md` | 17/17 células com EV<0; margem cresce com grau de OTM, exatamente como precificação padrão de opções |
| 5 | T2 — SPIKE_TIMING (Boom/Crash) | Deriv sintéticos | `docs/t2_boom_crash_spike_timing_report.md` | Intervalo entre spikes consistente com processo memoryless |
| 6 | T3 — Valor-relativo em exóticos/barreira | Deriv sintéticos | `trading-engine/docs/t3_exotic_value_report.md` | 0 células com `EV_lo>0`; "edges" do scan ingênuo eram drift de amostra + N baixo |

## Hipóteses refutadas — sinal real, porém sub-custo

| # | Hipótese | Produto | Relatório | Achado central |
|---|---|---|---|---|
| 7 | H1 — Momentum pós-choque | Binance BTC → Deriv multiplicador | `docs/h1_momentum_report.md` | Edge bruto real (~0.013-0.022%) mas comissão Deriv (~0.026%/lado) é maior. Custo > sinal |
| 8 | H3 — Latência cross-venue (Deriv×Binance) | arbitragem de latência | `docs/h3_latency_arb_report.md` | **Definitivo mesmo co-locado em AWS Tóquio**: reagir mais rápido capturou MENOS edge (217ms vs 450ms de casa); `aligned-anti` IC95% cruza zero; custo ~489x a captura |
| 9 | T4 — Viés direcional pós-choque, horizonte longo | Binance BTC, 7 dias OOS | `trading-engine/docs/t4_long_horizon_report.md` | Nenhuma das 24 células (momentum nem fade) sobrevive a controle nulo + custo |
| 10 | `hft_bot` V6.2 (produção) — implementação ao vivo de H3 | Deriv `cryBTCUSD` sintético | `docs/hft_v62_audit_report.md` | N=40, WR 22.5%, EV/trade -$3.02, IC95% [-4.70,-1.18] não cruza zero. Pior de 6 configs testadas |

**Implicação direta para o `hft_bot`:** ele é a hipótese H3 rodando em produção. O item 8 (H3
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

## Recomendação

1. Nenhuma hipótese testada até agora (10/10) justifica capital real.
2. `hft_bot` shadow A/B tem valor marginal baixo — H3 co-locada já respondeu a mesma pergunta com
   mais rigor. Decisão de mantê-lo rodando ou não é operacional, não estatística.
3. As duas frentes com potencial real de descoberta nova são **Synthetic Anomaly Monitor**
   (transiente, já rodando) e **Polymarket PA5** (estrutura invertida favoravelmente, harness
   pronto mas sem dado ainda) — nenhuma delas precisa de capital para o próximo passo.
4. Sincronizar com o Carlos sobre `feat/operate-demo-synthetic` antes de tocar em
   `hft_arbitrage_bot.py` de novo.
