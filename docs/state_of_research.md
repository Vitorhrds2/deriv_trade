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

## Estado ao vivo — Shadow A/B do hft_bot (checado 2026-07-02 ~11:30 UTC)

- **Código de Shadow A/B (`SHADOW_AB_ANTI_PROB`, `Grupo: ALIGNED/ANTI`) está deployado no servidor**
  (`hft_arbitrage_bot.py` ao vivo no EC2), mas **zero trade fechou desde que esse código entrou** —
  0 ALIGNED, 0 ANTI registrados até agora. Números antigos ("32 ALIGNED / 0 ANTI") são de ANTES
  desse deploy e não refletem mais o estado atual.
- **Seca de gatilho de 24h+**: último `GATILHO ACIONADO` em `2026-07-01 10:59:36 UTC`. Zero
  gatilhos e zero diagnóstico `👀` desde então, atravessando 3 restarts (queda de WS) e uma janela
  inteira de golden hour (01/07 12h-18h UTC).
- **Causa raiz descartada como bug**: rodado `passive_trigger_probe.py` (read-only, sem tocar no
  bot em produção) por 90s ao vivo — Binance (~120 updates/s), Coinbase, Kraken e Deriv tick feed
  todos conectados e atualizando; índice sintético calculando valores plausíveis (~$61.2k). Só 1
  choque ≥$5 formado em 90s, nenhum ≥$45 (o threshold do bot). **Feeds saudáveis; mercado
  genuinamente quieto perto desse patamar de preço**, consistente com o padrão histórico do log
  (gatilhos vêm em rajadas — ex.: 10 gatilhos em 6min no dia 01/07 — intercaladas por longos
  períodos quietos, não taxa constante).
- **Próximo teste barato:** golden hour (12h-18h UTC) é o checkpoint natural — se gatilhos voltarem
  quando a liquidez sobe, confirma sazonalidade; se a seca persistir também em golden hour, aí sim
  investigar mais fundo (não foi feito ainda).

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
- **Doc:** `docs/synthetic_anomaly_monitor.md` · **Código:** `trading-engine/synthetic_anomaly_monitor.py`
- Filosofia diferente das 10 hipóteses acima: não testa "sinal estrutural vence custo", **caça
  transiente** — mispricing momentâneo (`EV_EDGE`), viés de RNG, integridade de feed, timing de
  spike. Só alerta com limite inferior de Wilson + persistência por virada de janela (gates
  anti-variância).
- **Status:** instrumento de detecção ativo, **sem achado confirmado reportado até agora** (por
  design só "caça e registra"; virar aposta exige persistência + confirmação ao vivo + sobreviver
  a custo real).

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
- `demo_tick_strategy_runner.py` — runner de estratégia em tick separado, ainda não lido em
  detalhe.

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
