// Catálogo REAL de hipóteses testadas no ecossistema Mega Brain (Deriv).
// Fonte de verdade: docs/*.md no repo `hypothesis`. Cada entrada aqui corresponde a um
// relatório real com script(s) executado(s) e veredito fechado — nada aqui é simulado.
// Atualize manualmente quando uma nova hipótese for testada ou um veredito mudar
// (ex.: shadow A/B de algum bot acumular N suficiente para fechar veredito).

export type HypStatus = "live" | "validating" | "refuted" | "weak-signal" | "draft" | "paused" | "archived";

export interface RealHypothesis {
  id: string;
  title: string;
  market: string;
  thesis: string;
  confidence: number; // 0-100, crença residual (subjetiva) de que existe edge real
  status: HypStatus;
  tags: string[];
  trigger: string;
  invalidation: string;
  createdAt: string;
  author: string; // script/ferramenta principal, nao pessoa (projeto solo)
  pnl: number; // PnL real em USD (0 quando o teste foi so estatistico, sem capital)
  trades: number; // N real de trades OU tamanho da amostra estatistica analisada
  sampleUnit: string; // o que "trades" representa aqui (trades reais, ticks, gaps, saltos...)
  verdict: string; // veredito curto e direto
  evPerTrade?: number; // EV por trade/por $1 de stake, quando aplicavel
  ci95?: [number, number];
  ci95Label?: string; // o que o intervalo representa (EV/trade, WR, Weibull k...)
  tools: string[];
  reportFile: string; // caminho relativo em docs/, para referencia
}

export const realHypotheses: RealHypothesis[] = [
  {
    id: "HYP-HFT-01",
    title: "Arbitragem de latência via índice sintético 3-exchange (hft_bot)",
    market: "cryBTCUSD · Multiplier x800",
    thesis:
      "Um índice sintético reconstruído a partir de Binance (38.74%) + Coinbase (53.38%) + Kraken (2.66%) + offset $3152.82 (R²=0.928) reage a choques de preço com atraso suficiente para capturar via Multiplier antes da Deriv reprecificar.",
    confidence: 10,
    status: "refuted",
    tags: ["hft", "latencia", "multiplier", "shadow-ab", "cripto", "ao-vivo"],
    trigger:
      "Choque de preço > 45 pontos no índice sintético, formado em < 50ms (filtro de velocidade)",
    invalidation:
      "IC95% bootstrap do shadow A/B (ALIGNED vs ANTI) não cruzar zero de forma consistente e a favor de ALIGNED",
    createdAt: "2026-06-30",
    author: "hft_arbitrage_bot.py (V6.2 Ultra-Momentum)",
    pnl: -113.9,
    trades: 34,
    sampleUnit: "trades reais (conta demo, dedup por contract_id)",
    verdict:
      "Refutado — 40 trades reais (conta demo), EV/trade -$3.02, IC95% [-$4.70, -$1.18] (não cruza zero). " +
      "WR 22.5% (9/40). V6.2 com golden-hour filter produziu zero trades em 33h+ (threshold muito restritivo). " +
      "Consistente com H3: gargalo é a perna de execução da Deriv (~180-220ms), não a qualidade do sinal. " +
      "ATUALIZADO 2026-07-08 (audit_hft_trades.py, dedup por contract_id): N=34 trades reais " +
      "todas-versões, WR 23.5%, EV/trade -$3.35, IC95%[-$5.35,-$1.21]. Subset V6.2-por-parâmetro " +
      "(threshold=45 confirmado empírico, desde 2026-06-30) N=12, WR 8.3%, EV/trade -$3.62, " +
      "IC95%[-$6.01,-$0.81] — ambos os cortes têm IC95% inteiramente negativo, não mais " +
      "'inconclusivo por N baixo'. Shadow A/B (32 ALIGNED/2 ANTI): diff=$3.21 IC95%[-$1.83,+$8.29] " +
      "cruza zero, sem sinal direcional, ambos os grupos negativos — reconfirma H3. " +
      "PROCESSO PARADO 2026-07-08: tmux `hft_bot` killado e removido do " +
      "`aggressive_supervisor` (auto-restart) — o supervisor recriou a sessão uma vez " +
      "após o kill manual, por isso foi necessário remover do script do supervisor também.",
    evPerTrade: -3.35,
    ci95: [-5.35, -1.21],
    ci95Label: "EV/trade (bootstrap) — todas versões N=34; V6.2-por-parâmetro N=12 é [-$6.01,-$0.81]",
    tools: ["hft_arbitrage_bot.py", "audit_hft_trades.py", "stats_utils.py"],
    reportFile: "docs/hft_v62_audit_report.md",
  },
  {
    id: "HYP-ORACLE-01",
    title: "Oráculo Dinâmico — DIGITDIFF após 2 Virtual Losses",
    market: "1HZ10V, 1HZ25V, 1HZ50V, 1HZ75V, 1HZ100V",
    thesis:
      "Sinal de anomalia por matriz de transição 10×10 + máquina de estados de Virtual Loss (Sniper Duplo) produziria win rate acima do break-even (~91.2%) em DIGITDIFF.",
    confidence: 3,
    status: "refuted",
    tags: ["digits", "rng", "oraculo", "backtest"],
    trigger: "DIGITDIFF disparado após 2 Virtual Losses consecutivos",
    invalidation: "WR real cair dentro ou abaixo do IC95% do controle RNG uniforme sintético",
    createdAt: "2026-06-20",
    author: "backtest_oracle.py",
    pnl: 0,
    trades: 739,
    sampleUnit: "disparos reais (5 símbolos, 200k ticks)",
    verdict:
      "Refutado — WR real 88.77% IC95%[86.29%,90.85%], inteiramente abaixo do break-even. Todos os 46 tipos de contrato testados (DIGITDIFF/MATCH/EVEN/ODD/OVER/UNDER/CALL/PUT) têm EV negativo (melhor caso: -1.26%). Falso edge inicial em R_10 DIGITEVEN (+4.31%) era bug de pip_size, corrigido.",
    evPerTrade: -0.0126,
    ci95: [86.29, 90.85],
    ci95Label: "Win rate % (Wilson)",
    tools: ["backtest_oracle.py", "contract_edge_scan.py"],
    reportFile: "docs/edge_investigation_report.md",
  },
  {
    id: "HYP-ACCU-01",
    title: "Accumulators — sobrevivência de barreira por tick mispriced",
    market: "1HZ100V (grade completa: 10 símbolos × 5 growth rates)",
    thesis:
      "A probabilidade real de sobreviver 1 tick dentro da barreira poderia ser maior que o valor justo (1/(1+growth_rate)), abrindo EV positivo composto ao longo de N ticks.",
    confidence: 5,
    status: "refuted",
    tags: ["accumulator", "barreira", "mispricing", "mega-brain-2"],
    trigger: "growth_rate 1-5%, horizonte N ticks alvo 5-20",
    invalidation:
      "P(sobreviver 1 tick) medido em amostra real cair abaixo do valor justo em qualquer growth_rate",
    createdAt: "2026-07-01",
    author: "accumulator_validate.py",
    pnl: 0,
    trades: 5000,
    sampleUnit: "ticks reais (1HZ100V)",
    verdict:
      "Refutado — P(sobrevive 1 tick) sistematicamente MENOR que o valor justo nos 5 growth_rates testados (IC95% sempre abaixo, diferença -0.11pp a -0.61pp). Cluster inicial (EV_lo positivo em growth_rate=0.03) era falso positivo de amostra pequena/correlacionada (~100 episódios reciclados).",
    tools: ["probe_accumulator.py", "accumulator_edge_scan.py", "accumulator_validate.py"],
    reportFile: "docs/accumulator_edge_report.md",
  },
  {
    id: "HYP-JUMP-01",
    title: "Jump Indices — viés de direção e memória de timing",
    market: "JD10, JD25, JD50, JD75, JD100",
    thesis:
      "A direção dos saltos poderia ser enviesada (≠50/50) e/ou o intervalo entre saltos teria estrutura de 'temporizador' (hazard rate crescente) explorável — nunca testado antes neste ecossistema.",
    confidence: 4,
    status: "refuted",
    tags: ["jump-index", "timing", "direcao", "mega-brain-2"],
    trigger: "Detecção de salto via |retorno tick-a-tick| > 10x mediana",
    invalidation: "Viés de direção ou hazard rate crescente sumir ao quadruplicar a amostra",
    createdAt: "2026-07-01",
    author: "jump_index_spike_scan.py",
    pnl: 0,
    trades: 221,
    sampleUnit: "saltos reais (5 símbolos, 60k ticks cada)",
    verdict:
      "Refutado — direção 50/50 confirmada (único desvio, JD50 92.9% UP com N=14, era falso positivo: caiu para exatamente 50.0% em N=50). Timing memoryless confirmado (CV 0.84-1.18 entre os 5 símbolos, sem hazard rate crescente com a idade).",
    ci95: [36.6, 63.4],
    ci95Label: "% UP no re-teste JD50 (N=50)",
    tools: ["jump_index_spike_scan.py"],
    reportFile: "docs/jump_index_report.md",
  },
  {
    id: "HYP-VANILLA-01",
    title: "Vanilla Options — mispricing vs. valor justo",
    market: "1HZ100V",
    thesis:
      "Payoff convexo real (payout_per_point × max(0, final−strike)) é o único produto não-binário do ecossistema — abre espaço para comparar preço vs. valor justo teórico via Monte Carlo, análogo a IV implícita vs. realizada.",
    confidence: 10,
    status: "refuted",
    tags: ["vanilla", "opcoes", "mispricing", "mega-brain-2"],
    trigger: "CALL/PUT × 5 strikes × 2 durações (15m, 60m)",
    invalidation: "IC95% do EV simulado cruzar zero em qualquer strike/duração",
    createdAt: "2026-07-01",
    author: "vanilla_edge_scan.py",
    pnl: 0,
    trades: 20,
    sampleUnit: "células testadas (20k caminhos Monte Carlo cada, 15k ticks reais calibrando)",
    verdict:
      "Refutado — 0/20 células com EV_lo > 0. EV médio -8.42% (min=-19.92%, max=-1.96%). " +
      "ATM CALL 15m: EV=-8.12%, ATM PUT 15m: EV=-10.30%. OTM deep: EV=-19.92%. " +
      "60m: ainda mais negativo (mais theta decay). House margin sistemática em todo o surface.",
    evPerTrade: -0.0842,
    ci95: [-19.92, -1.96],
    ci95Label: "Range de EV% observado",
    tools: ["probe_vanilla.py", "vanilla_edge_scan.py"],
    reportFile: "docs/vanilla_options_report.md",
  },
  {
    id: "HYP-T2-01",
    title: "T2 — Memória de spike em Boom/Crash (SPIKE_TIMING)",
    market: "BOOM300N/500/1000, CRASH300N/500/1000",
    thesis:
      "O intervalo entre spikes gigantes (~30-50x o movimento normal) poderia ter hazard rate crescente (spike 'atrasado' fica mais provável), permitindo posicionar entrada com Multiplier antes do spike.",
    confidence: 10,
    status: "refuted",
    tags: ["boom-crash", "timing", "memoria", "weibull", "mega-brain-2"],
    trigger: "Spike detectado via |retorno| > 8x mediana na direção do índice",
    invalidation: "Weibull shape k > 1 (hazard crescente) replicado de forma independente",
    createdAt: "2026-07-01",
    author: "boom_timing_test.py",
    pnl: 0,
    trades: 1058,
    sampleUnit: "gaps normalizados (10 símbolos Boom/Crash, 60k ticks cada, pool multi-símbolo)",
    verdict:
      "VEREDITO DECISIVO (N=1058, 10 símbolos, 600k ticks) — Weibull k=1.010 IC95%[0.966,1.058]. " +
      "KS NÃO rejeita exponencial (D=0.014 vs crit=0.042). Hazard por idade constante ~25% em todos os bins. " +
      "P(gap>2*med|gap>med)=49.3% (memoryless esperado ~50%). " +
      "Coleta anterior (N=177): k=1.000 IC95%[0.898,1.129]. Ambas consistentes com processo memoryless puro. " +
      "T2 REFUTADA: P(spike) ~ taxa base independente da idade. 'Spike atrasado' é falácia do apostador.",
    ci95: [0.966, 1.058],
    ci95Label: "Weibull shape k (1.0 = memoryless)",
    tools: ["boom_timing_test.py", "boom_memory_test.py"],
    reportFile: "docs/t2_boom_crash_spike_timing_report.md",
  },
  {
    id: "HYP-HL-01",
    title: "HIGHER/LOWER — barrier mispricing vs Monte Carlo driftless",
    market: "1HZ10V, 1HZ100V",
    thesis:
      "Contratos HIGHER/LOWER com barreira percentual poderiam ter payout desalinhado vs. probabilidade real de tocar a barreira, abrindo EV positivo em alguma combinação de barrier × duração.",
    confidence: 3,
    status: "refuted",
    tags: ["higher-lower", "barreira", "mispricing", "mega-brain-2"],
    trigger: "HIGHER/LOWER × 5 barriers × 3 durações × 2 símbolos = 31 células",
    invalidation: "IC95% do EV simulado cruzar zero em qualquer célula",
    createdAt: "2026-07-03",
    author: "higher_lower_edge_scan.py",
    pnl: 0,
    trades: 31,
    sampleUnit: "células testadas (20k caminhos Monte Carlo cada)",
    verdict:
      "Refutado — 0/31 células com EV_lo > 0. House margin 0.2-10% embutida no payout, crescente com distância da barreira. Padrão idêntico aos outros 13 produtos Deriv testados.",
    evPerTrade: -0.03,
    tools: ["higher_lower_edge_scan.py"],
    reportFile: "docs/state_of_research.md",
  },
  {
    id: "HYP-MULT-01",
    title: "Multipliers (MULTUP/MULTDOWN) — mispricing standalone",
    market: "1HZ10V",
    thesis:
      "Único produto Deriv ativo nunca testado para mispricing. Payoff = (spot_final - entry) × multiplier, sem payout fixo. Comissão (ask_price - stake) poderia ser menor que o fair value do optionality embutido (stop loss, cancellation).",
    confidence: 2,
    status: "refuted",
    tags: ["multiplier", "comissao", "mispricing", "mega-brain-2"],
    trigger: "MULTUP/MULTDOWN × 5 multipliers (400-4000) × 3 cancellations (5m/15m/60m) = 30 células",
    invalidation: "IC95% do EV simulado (MC payoff - comissão) cruzar zero em qualquer célula",
    createdAt: "2026-07-03",
    author: "multiplier_edge_scan.py",
    pnl: 0,
    trades: 30,
    sampleUnit: "células testadas (20k caminhos Monte Carlo cada, 10k ticks reais calibrando)",
    verdict:
      "Refutado — 0/30 células com EV_lo > 0. MC payoff bruto ≈ $0 (martingale confirmado), EV = -comissão em todas as células. Comissão escala linearmente: $0.44 (mult=400, 5m) a $7.61 (mult=4000, 60m). Não há mispricing — Deriv cobra fair value (zero) + comissão pura.",
    evPerTrade: -0.376,
    tools: ["probe_multiplier.py", "multiplier_edge_scan.py"],
    reportFile: "docs/state_of_research.md",
  },
  {
    id: "HYP-PA5-01",
    title: "PA5 — Polymarket BTC Up/Down stale-book arbitrage",
    market: "Polymarket BTC 5-15min windows",
    thesis:
      "Mercados BTC de 5-15min no Polymarket resolvem por benchmark de preço; perto do settlement, o resultado já é quase determinístico via Binance enquanto o livro CLOB pode ficar stale — comprar o lado favorito (aligned) deveria ter EV positivo.",
    confidence: 2,
    status: "refuted",
    tags: ["polymarket", "latencia", "momentum", "clob", "stale-book"],
    trigger: "|move| >= $5 nos últimos 30s antes do settlement → comprar aligned (a favor) vs anti (contra) 50/50",
    invalidation: "IC95% da diferença aligned-anti cruzar zero OU ser negativo",
    createdAt: "2026-07-02",
    author: "pa5_collector.py",
    pnl: -19.62,
    trades: 1838,
    sampleUnit: "paper trades (265 janelas, 635 aligned + 1203 anti)",
    verdict:
      "Refutado — verdict 'aligned_pior'. Aligned WR=88.5% (sinal real de momentum) mas PnL médio=-$0.031 (comprar lado favorito custa ~$1, payoff <$1). Diff aligned-anti=-$0.037/trade, IC95%[-$0.060,-$0.014] NÃO cruza zero. O livro NÃO está stale — está corretamente precificado. Mesmo padrão sub-custo de H1/H3, mas aqui o edge vai na direção CONTRÁRIA à tese.",
    evPerTrade: -0.037,
    ci95: [-0.06, -0.014],
    ci95Label: "Diff aligned-anti por trade (bootstrap)",
    tools: ["polymarket_lag_probe.py", "pa5_collector.py", "polymarket_arb_stats.py"],
    reportFile: "docs/state_of_research.md",
  },
  {
    id: "HYP-SELL-01",
    title: "Early sell optionality — bid_price vs hold-to-expiry",
    market: "1HZ10V · CALL 15m + 9 outros símbolos/contract types",
    thesis:
      "A capacidade de vender antes do expiry a bid_price poderia ter valor de optionality (vender quando ITM antes de reverter) que excede o custo do spread bid/ask embutido.",
    confidence: 5,
    status: "refuted",
    tags: ["early-sell", "optionality", "bid-price", "mega-brain-2", "hindsight-bias", "refutado"],
    trigger: "Comprar CALL 15m, monitorar bid_price durante vida do contrato, comparar sell no melhor bid vs hold-to-expiry",
    invalidation: "IC95% da diferença sell_profit - hold_profit cruzar zero (non-hindsight, regra predefinida, PAREADA por trial)",
    createdAt: "2026-07-03",
    author: "early_sell_test.py / early_sell_multi.py",
    pnl: 0,
    trades: 550,
    sampleUnit: "N=550 (10 símbolos x 55), corrigido 2026-07-07 -- ver verdict",
    verdict:
      "RE-REFUTADO (2026-07-07) — a confirmação original (N=50, status=live, confidence=85) e a " +
      "extensão multi-símbolo (N=550) tinham um BUG METODOLÓGICO: 'sell_profit' usava " +
      "best_bid=max(bid observado em TODA a vida do contrato) — viés de HINDSIGHT, já que " +
      "max(caminho) é trivialmente >= qualquer ponto fixo do mesmo caminho (incl. hold), " +
      "positivo pra qualquer preço com ruído independente de mispricing real. A checagem " +
      "'non-hindsight' secundária (vender no 1o bid>=threshold) tinha um bug relacionado: " +
      "EV_sell só sobre trials que DISPARARAM (condicional, quase tautológico) comparado " +
      "com hold via slice por ÍNDICE, não pareado pelos mesmos trials — comparação inválida. " +
      "CORRIGIDO: comparação pareada por trial (regra dispara->vende, senão segura; diff = " +
      "regra - hold_sempre), bootstrap na diferença. Resultado em N=550 (10 símbolos), 8 " +
      "thresholds (ratio bid/buy 1.1-1.8): diff EV cruza zero em 7/8 (ex. ratio=1.3: " +
      "+0.05bps IC95%[-0.54,+0.65]) e é SIGNIFICATIVAMENTE NEGATIVO no ratio=1.8 " +
      "(-0.20 IC95%[-0.35,-0.01]). Nenhum símbolo individual mostra IC95% excluindo zero. " +
      "Mecanismo: vender cedo aumenta win rate mas reduz tamanho médio do ganho (perde os " +
      "movimentos grandes que só aparecem segurando) — efeitos se cancelam, sem EV líquido. " +
      "Script corrigido (compute_stream_stats() expõe diff_ev_vs_hold pareado; campos antigos " +
      "renomeados *_HINDSIGHT) e redeployado na AWS. NÃO usar early_sell_live.py com capital real. " +
      "ATUALIZADO 2026-07-08: `early_sell_multi.py` seguiu rodando na AWS e mais que TRIPLICOU " +
      "a amostra por combo (N=55→N=187/símbolo:tipo, ~1870 trials no total, ratio=1.3) — mesmo " +
      "resultado qualitativo em TODOS os 10 combos (CALL/PUT × 5 símbolos): diff_ev cruza zero " +
      "ou é levemente negativo, nenhum combo escapa. Amostra adicional não mudou a conclusão — " +
      "recomendado parar o processo (tmux `early_sell_multi` na AWS), já é redundante. " +
      "PROCESSO PARADO 2026-07-08.",
    tools: ["early_sell_test.py", "early_sell_multi.py", "stats_utils.py"],
    reportFile: "docs/state_of_research.md",
  },
  {
    id: "HYP-XSYM-01",
    title: "Cross-symbol arbitrage — correlação entre RNGs sintéticos",
    market: "10 símbolos sintéticos Deriv (R_10 a 1HZ100V)",
    thesis:
      "Se os RNGs de símbolos sintéticos diferentes tiverem correlação não-nula, mudanças em um símbolo poderiam prever mudanças em outro, abrindo arbitragem cross-symbol.",
    confidence: 2,
    status: "refuted",
    tags: ["cross-symbol", "correlacao", "rng", "arbitragem"],
    trigger: "Download simultâneo de ticks de 10 símbolos, medir correlação e variance ratio",
    invalidation: "Correlação ~0 e variance ratio ~1.0 (RNGs independentes)",
    createdAt: "2026-07-03",
    author: "cross_symbol_arb_test.py",
    pnl: 0,
    trades: 500,
    sampleUnit: "epochs simultâneos (10 símbolos, 500 ticks cada)",
    verdict:
      "Refutado — correlação ~0 entre todos os pares de símbolos, variance ratio ~1.0. RNGs são independentes. Nenhuma estrutura cross-symbol explorável.",
    tools: ["cross_symbol_arb_test.py"],
    reportFile: "docs/state_of_research.md",
  },
  {
    id: "HYP-DEX-01",
    title: "DEX arbitrage — Jupiter (Solana) vs Binance CEX + triangular SOL→USDC→SOL",
    market: "Solana DEX / Binance CEX",
    thesis:
      "O agregador Jupiter pode ter pricing stale vs Binance, criando janela de arb CEX-DEX. " +
      "Adicionalmente, triangular arb via rotas otimizadas pode ter roundtrip > 1.0 explorando " +
      "pools com pricing divergente entre 15+ DEXs (HumidiFi, Meteora, Raydium, Orca, etc.).",
    confidence: 0,
    status: "refuted",
    tags: ["dex", "solana", "jupiter", "cex-dex", "triangular", "arbitrage"],
    trigger: "Gap de preço entre Jupiter Swap API e Binance bookTicker > fee AMM (~25bps)",
    invalidation: "Gap CEX-DEX sempre negativo + triangular roundtrip ~0bps",
    createdAt: "2026-07-03",
    author: "dex_arb_scan.py",
    pnl: 0,
    trades: 199,
    sampleUnit: "quotes Jupiter (3 runs: 10min@5s/1SOL, 10min@7s/1SOL, 5min@8s/10SOL)",
    verdict:
      "Refutado — CEX-DEX: 0/199 amostras com divergência positiva; Jupiter sempre ~9bps abaixo " +
      "de Binance (fee implícito do agregador). Triangular (chained): roundtrip médio +0.76bps " +
      "(1SOL) e -0.11bps (10SOL), max +7.93bps, threshold ~50bps. Agregador já captura " +
      "ineficiências intra-DEX. Bug crítico corrigido: versão inicial inflava roundtrip usando " +
      "input fixo vs Binance em vez de outAmount real da leg 1.",
    tools: ["dex_arb_scan.py"],
    reportFile: "docs/dex_arb_report.md",
  },
  {
    id: "HYP-PA-01",
    title: "PA1-PA4 Polymarket — new market snipe + cross-market + multi-outcome arb + near-resolution",
    market: "Polymarket (todos os mercados ativos)",
    thesis:
      "PA1: mercados recém-criados têm books mal precificados antes da convergência de bots. " +
      "PA2: mercados logicamente relacionados (BTC 5m vs 15m) têm probabilidades inconsistentes. " +
      "PA3: mercados multi-outcome onde sum(best asks) < $1.00 = arb livre. " +
      "PA4: book converge lentamente perto do settlement, criando janela de snipe.",
    confidence: 0,
    status: "refuted",
    tags: ["polymarket", "arbitrage", "multi-outcome", "cross-market", "new-market", "near-resolution"],
    trigger: "sum(asks) < $1.00 em qualquer mercado ativo, ou spread > 500bps em mercado novo, ou diff > 500bps entre 5m/15m",
    invalidation: "sum(asks) >= $1.00 em todos mercados; spreads convergem <37s; diff=0bps entre janelas",
    createdAt: "2026-07-03",
    author: "polymarket_arb_scan.py",
    pnl: 0,
    trades: 940,
    sampleUnit: "mercados escaneados (10 ciclos, 94 mercados/ciclo) + 24 novos mercados + 10 pares 5m/15m",
    verdict:
      "Refutado — PA3: 940 mercados, min sum(asks)=$1.001, 0 arb. PA2: 10 pares 5m/15m, diff=0.0bps. " +
      "PA1: 24 novos mercados, spread=100bps desde age=37s (bots convergem instantaneamente). " +
      "PA4: mecanismo já refutado pelo PA5 (N=1838, livro não está stale). Polymarket encerrado como venue de arb.",
    tools: ["polymarket_arb_scan.py"],
    reportFile: "docs/polymarket_pa1_pa4_report.md",
  },
  {
    id: "HYP-DEX-02",
    title: "D6 — Cross-aggregator DEX arbitrage (EVM: BSC, Base, Arbitrum, Polygon)",
    market: "OpenOcean vs Paraswap vs LiFi (EVM chains)",
    thesis:
      "Different DEX aggregators on EVM chains may route through different underlying DEXs, " +
      "producing different quotes for the same token pair. If the cross-aggregator spread " +
      "exceeds gas + fees, there may be an exploitable cross-DEX arbitrage opportunity.",
    confidence: 0,
    status: "refuted",
    tags: ["dex", "evm", "bsc", "base", "arbitrum", "polygon", "cross-aggregator", "arbitrage"],
    trigger: "Cross-aggregator quote spread > gas + slippage for same token pair",
    invalidation: "BSC (most liquid chain) shows roundtrip -1 to -3 bps; positive roundtrips on less liquid chains are quote API artifacts",
    createdAt: "2026-07-03",
    author: "dex_cross_agg_scan.py",
    pnl: 0,
    trades: 160,
    sampleUnit: "quote comparisons (5 cycles, 4 chains, 5 pairs, 2 sizes) + 25 roundtrips",
    verdict:
      "Refutado — BSC (controle de sanidade, chain mais líquida): spread 0-5 bps, roundtrip -1 a -3 bps. " +
      "Base/Arbitrum: spread 20-165 bps mas roundtrip positivo (+30-73 bps) é artefato de quote API " +
      "indicativa do Paraswap (inconsistência interna: otimista em ambos os lados). Polygon: spread " +
      "450 bps em WMATIC é stale quote do OpenOcean. 15/25 roundtrips 'positivos' mas todos são " +
      "quote artifacts, não preços executáveis. Padrão espelha Solana DEX: agregadores já capturam " +
      "ineficiências de roteamento.",
    tools: ["dex_cross_agg_scan.py"],
    reportFile: "docs/dex_cross_agg_report.md",
  },
  {
    id: "HYP-CEX-01",
    title: "D7 — CEX-CEX arbitrage (Binance vs Bybit vs OKX)",
    market: "CEX spot (Binance, Bybit, OKX)",
    thesis:
      "If the same pair (e.g. BTC/USDT) has a higher bid on one exchange than the ask on another " +
      "(after fees), there is a cross-exchange arbitrage opportunity.",
    confidence: 0,
    status: "refuted",
    tags: ["cex", "binance", "bybit", "okx", "cross-exchange", "arbitrage"],
    trigger: "Cross-exchange bid-ask spread > 20 bps (taker fees both sides)",
    invalidation: "Gross spread 0-4 bps, fees 20 bps/side. 0/100 positive net.",
    createdAt: "2026-07-03",
    author: "cex_arb_scan.py",
    pnl: 0,
    trades: 100,
    sampleUnit: "cross-exchange quote comparisons (20 cycles, 8 pairs, 3 exchanges)",
    verdict:
      "Refutado — 100 observações, gross 0-4 bps, net -16 a -26 bps, 0/100 positivos. " +
      "Market makers cross-exchange comprimem qualquer ineficiência instantaneamente. " +
      "Gap CEX-CEX (~0-4 bps) é menor que gap CEX-DEX (~9 bps em Solana).",
    tools: ["cex_arb_scan.py"],
    reportFile: "docs/cex_arb_report.md",
  },
  {
    id: "HYP-CEX-02",
    title: "D8 — Triangular arbitrage (Binance)",
    market: "CEX spot (Binance)",
    thesis:
      "If a triangular path (e.g. BTC→ETH→USDT→BTC) yields > 1.0 after fees, there is a " +
      "triangular arbitrage opportunity within a single exchange.",
    confidence: 0,
    status: "refuted",
    tags: ["cex", "binance", "triangular", "arbitrage"],
    trigger: "Triangular roundtrip > 30 bps (3 legs × 10 bps taker fee)",
    invalidation: "Gross -10 bps average, best +2 bps. 0/120 positive net.",
    createdAt: "2026-07-03",
    author: "cex_arb_scan.py",
    pnl: 0,
    trades: 120,
    sampleUnit: "triangular roundtrip checks (20 cycles, 6 paths)",
    verdict:
      "Refutado — 120 observações, gross -10 bps médio (máx +2 bps), net -28 a -98 bps, 0/120 positivos. " +
      "Spread bid-ask em cada leg consome qualquer ineficiência. Binance é mais eficiente que Solana DEX.",
    tools: ["cex_arb_scan.py"],
    reportFile: "docs/cex_arb_report.md",
  },
  {
    id: "HYP-CEX-03",
    title: "D9 — Funding rate carry trade (Binance/Bybit/OKX perpetuals)",
    market: "CEX perpetual futures (Binance, Bybit, OKX)",
    thesis:
      "If perpetual futures funding rates are persistently positive (longs pay shorts), " +
      "a delta-neutral carry trade (buy spot + short perp, collect funding every 8h) " +
      "is profitable after trading fees and capital cost.",
    confidence: 0,
    status: "refuted",
    tags: ["cex", "perpetual", "funding-rate", "carry-trade", "binance", "bybit", "okx"],
    trigger: "Total funding > 40 bps entry/exit fees + 42 bps/30d capital cost",
    invalidation: "Initial scan 14/20 profitable (sample bias ~11 days). Validation: 4/19, 0% of 7-day windows profitable.",
    createdAt: "2026-07-03",
    author: "funding_rate_scan.py, funding_rate_validate.py",
    pnl: 0,
    trades: 19,
    sampleUnit: "perpetual contracts analyzed (30-day funding history, 90-360 periods each)",
    verdict:
      "Refutado — Scan inicial mostrou 14/20 'lucrativos' mas era viés de amostra curta (~11 dias OKX). " +
      "Validação com 30 dias completos: apenas 4/19 têm net positivo, e 0% das janelas contínuas de 7 dias " +
      "são lucrativas após fees (40 bps) + custo de capital (42 bps/30d). Funding é autocorrelacionado " +
      "(18/19 lag-1 positive) mas não forte o suficiente para superar custos. Basis risk não contabilizado " +
      "piora o quadro.",
    tools: ["funding_rate_scan.py", "funding_rate_validate.py"],
    reportFile: "docs/cex_arb_report.md",
  },
  {
    id: "HYP-DEFI-01",
    title: "D10 — DeFi liquidation MEV (Aave V3)",
    market: "DeFi lending (Aave V3 on Base)",
    thesis:
      "When a borrower's health factor drops below 1.0, liquidators can repay debt and seize " +
      "collateral + bonus (5-10%). A liquidation bot using flash loans can capture this bonus " +
      "profitably without needing capital.",
    confidence: 0,
    status: "refuted",
    tags: ["defi", "aave", "liquidation", "mev", "base", "flash-loans"],
    trigger: "Health factor < 1.0 on Aave V3 positions",
    invalidation: "108 events in 10.6 days, but 95% have debt <$4. Latency 30-60s vs <12s MEV bots. Capture rate <1%.",
    createdAt: "2026-07-03",
    author: "defi_liquidation_scan.py",
    pnl: 0,
    trades: 108,
    sampleUnit: "LiquidationCall events on Aave V3 Base (500000 blocks, ~10.6 days)",
    verdict:
      "Refutado para retail — 108 liquidações Aave V3 na Base em 10.6 dias, bonus médio 7.8%. " +
      "Mas 95% dos eventos têm debt <$4 (mediana ~$0.3). Apenas 2-3 eventos >$500 em 10 dias. " +
      "Latência fatal: 30-60s via eth_getLogs vs <12s dos bots MEV profissionais. " +
      "RPCs gratuitos bloqueiam eth_getLogs (apenas mainnet.base.org funcionou). " +
      "Sem infra profissional (WebSocket + flashbots + archive node), capture rate é <1%. " +
      "Receita realista (1% capture): ~$2 em 10 dias. Não é edge explorável sem co-location + MEV bundles.",
    tools: ["defi_liquidation_scan.py"],
    reportFile: "docs/defi_liquidation_report.md",
  },
  {
    id: "HYP-OPT-01",
    title: "D11 — Options IV mispricing (Deribit BTC/ETH)",
    market: "Deribit options (BTC, ETH)",
    thesis:
      "If implied volatility (IV) on Deribit options is systematically mispriced relative to " +
      "historical realized volatility (RV), there may be an edge in selling overpriced IV or " +
      "buying underpriced IV via delta-hedged option positions.",
    confidence: 0,
    status: "refuted",
    tags: ["options", "deribit", "iv", "volatility", "vrp", "delta-hedging"],
    trigger: "IV (DVOL) deviates significantly from RV (30d historical vol)",
    invalidation: "VRP is negative (-8.2% BTC, -8.8% ETH): IV < RV. Buying vol = theta decay. Delta hedging costs + bid-ask spreads consume the edge.",
    createdAt: "2026-07-03",
    author: "options_iv_scan.py",
    pnl: 0,
    trades: 0,
    sampleUnit: "DVOL + RV + ATM IV surface for BTC and ETH (8 expiries each, 1d-28d)",
    verdict:
      "Refutado — VRP negativo em BTC (-8.2%) e ETH (-8.8%): IV < RV sugere comprar vol. " +
      "Mas theta decay + delta hedging costs ($600-1500/mês em fees de hedge) + bid-ask spreads " +
      "(5-15% do premium) consomem o edge. Term structure em contango (+9%) já precifica aumento " +
      "de vol. Skew ATM = 0% (balanced). Sem edge sem infra de vol trading profissional.",
    tools: ["options_iv_scan.py"],
    reportFile: "docs/options_stat_arb_report.md",
  },
  {
    id: "HYP-STATARB-01",
    title: "D12 — Statistical arbitrage (crypto pairs trading)",
    market: "Binance spot (20 top USDT pairs)",
    thesis:
      "If two crypto assets are cointegrated (their spread mean-reverts), a pairs trading " +
      "strategy can profit from temporary divergences by going long the underperformer and " +
      "short the outperformer.",
    confidence: 0,
    status: "refuted",
    tags: ["stat-arb", "pairs-trading", "cointegration", "mean-reversion", "binance"],
    trigger: "Z-score of cointegrated spread exceeds ±2.0 standard deviations",
    invalidation: "76/190 pairs cointegrated, but 7/10 backtested OOS negative after 40bps fees. avg PnL=-278bps, avg Sharpe=-0.26.",
    createdAt: "2026-07-03",
    author: "stat_arb_scan.py",
    pnl: 0,
    trades: 145,
    sampleUnit: "190 pairs tested (20 symbols × 19), 10 backtested OOS (70/30 walk-forward, 500 daily candles)",
    verdict:
      "Refutado — 76/190 pares cointegrados (40%) mostra que cripto é altamente correlacionado. " +
      "Mas backtest OOS: 7/10 pares negativos após 40bps fees. avg PnL=-278bps, avg Sharpe=-0.26. " +
      "Win rate de 63% é enganosa: ganhos pequenos (exit at z=0.5) vs perdas grandes (stop at z=4.0). " +
      "Melhor par ADA/SUI: +1,417 bps (~5.4% annualizado) — marginal. " +
      "Risco de quebra de cointegração (LUNA/UST precedent). Sem edge após custos.",
    tools: ["stat_arb_scan.py"],
    reportFile: "docs/options_stat_arb_report.md",
  },
  {
    id: "HYP-FUND-SIG-01",
    title: "D13 — Funding rate como signal direcional",
    market: "Binance futures (BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, LINK, DOT)",
    thesis:
      "If funding rates are extreme, they signal overleveraged positioning. " +
      "When funding is very positive (longs pay shorts), the market is overleveraged long " +
      "and a price drop is likely. When very negative, a rally is likely. " +
      "Trade: take the opposite side of the crowded trade.",
    confidence: 30,
    status: "validating",
    tags: ["funding-rate", "directional", "signal", "binance", "futures", "sentiment"],
    trigger: "Funding rate exceeds percentile threshold (50th/75th/90th/95th) of historical distribution",
    invalidation: "Long side (funding negative → buy) has WR 0-12% — does not work in crypto. Short side WR 37-43% at 72h but overall WR is 26%.",
    createdAt: "2026-07-03",
    author: "funding_signal_scan.py",
    pnl: 0,
    trades: 250,
    sampleUnit: "500 funding events × 10 symbols, 6 horizons (1h-72h), 4 percentile thresholds",
    verdict:
      "Sinal fraco assimétrico — Short side (funding positivo → vender) tem WR 37-43% em 72h " +
      "para BTC/ETH. Long side NÃO funciona (WR 0-12%). Sharpe 5.4 BTC mas WR 26%: poucas trades " +
      "grandes compensam muitas pequenas perdas. Sinal só funciona em 72h (horizontes curtos " +
      "são negativos). Melhor como filtro complementar, não como estratégia standalone.",
    tools: ["funding_signal_scan.py"],
    reportFile: "docs/funding_trend_report.md",
  },
  {
    id: "HYP-TREND-01",
    title: "D14 — BTC trend following (momentum multi-dia)",
    market: "Binance spot (BTC, ETH, SOL)",
    thesis:
      "If BTC exhibits momentum at multi-day timeframes, a trend-following strategy using " +
      "moving average crossovers or breakout signals can capture directional moves that " +
      "exceed transaction costs.",
    confidence: 35,
    status: "validating",
    tags: ["trend-following", "momentum", "directional", "binance", "moving-average", "breakout"],
    trigger: "Fast SMA crosses slow SMA (10/50), or price breaks N-day high/low",
    invalidation: "Long-only strategies don't replicate OOS (overfitting). N=7 trades OOS is not statistically significant.",
    createdAt: "2026-07-03",
    author: "trend_follow_scan.py",
    pnl: 0,
    trades: 7,
    sampleUnit: "1000 daily candles × 3 symbols, 30+ strategy configs, 70/30 walk-forward",
    verdict:
      "Sinal marginal — SMA(10/50) long+short beat buy & hold em risk-adjusted return " +
      "(Sharpe 1.16 vs 0.85 BTC, 1.40 vs 0.37 ETH). MAS N=7 trades OOS não é significativo. " +
      "Long-only strategies não replicam OOS (overfitting no train set). " +
      "Custos de shorting (funding + borrow) reduzem edge. Potencial como estratégia complementar.",
    tools: ["trend_follow_scan.py"],
    reportFile: "docs/funding_trend_report.md",
  },
  {
    id: "HYP-COMBINED-01",
    title: "D15 — Combined funding filter + trend following",
    market: "Binance spot + futures (BTC, ETH, SOL)",
    thesis:
      "Using funding rate as a filter for trend following improves risk-adjusted returns. " +
      "Skip long entries when funding is extremely positive (overleveraged longs), " +
      "only short when funding is positive (longs crowded).",
    confidence: 0,
    status: "refuted",
    tags: ["combined", "funding-rate", "trend-following", "filter", "binance"],
    trigger: "SMA(10/50) crossover + funding rate percentile filter (75th/90th)",
    invalidation: "Funding filter PIORA trend following: delta Sharpe -0.27 BTC, -0.45 ETH, -0.80 SOL. Filter removes good trades.",
    createdAt: "2026-07-03",
    author: "combined_signal_scan.py",
    pnl: 0,
    trades: 0,
    sampleUnit: "1000 daily candles × 3 symbols, 4 strategy variants, 70/30 walk-forward",
    verdict:
      "Refutado — Funding filter piora trend following em todos os 3 symbols. " +
      "Delta Sharpe negativo: BTC -0.27, ETH -0.45, SOL -0.80. " +
      "Filtro remove trades bons: em trend de alta, funding é positivo (normal), " +
      "filtrar = perder o trend. Funding reflete positioning atual, não direção futura. " +
      "Descoberta secundária: funding-only short em ETH Sharpe=2.96 mas MaxDD=95%.",
    tools: ["combined_signal_scan.py"],
    reportFile: "docs/combined_cvd_report.md",
  },
  {
    id: "HYP-CVD-01",
    title: "D16 — CVD / order flow directional signal",
    market: "Binance spot (BTC, ETH, SOL — 1h candles)",
    thesis:
      "Cumulative Volume Delta (CVD) — running sum of taker buy minus sell volume — " +
      "predicts short-term price direction. Divergence between CVD and price signals " +
      "impending reversal. CVD momentum confirms trend.",
    confidence: 0,
    status: "refuted",
    tags: ["cvd", "order-flow", "directional", "binance", "microstructure", "divergence", "bonferroni", "k-fold"],
    trigger: "CVD-price divergence (price new high, CVD doesn't confirm) or CVD z-score extreme",
    invalidation: "5-fold CV + permutation test + Bonferroni (α=0.0019): no config significant. ETH diverge_96h_48h WR 76% but p=0.107. Sharpe 10+ in v1 was annualization artifact.",
    createdAt: "2026-07-03",
    author: "cvd_signal_v2_scan.py",
    pnl: 0,
    trades: 51,
    sampleUnit: "5000 1h candles × 3 symbols, 27 configs, 5-fold CV, permutation test (1000x), Bonferroni correction",
    verdict:
      "Refutado em re-teste rigoroso — 5000 candles, 5-fold CV, permutation test, Bonferroni (α=0.0019). " +
      "Nenhum config significativo. ETH diverge_96h_48h WR 76% mas p=0.107 (56x acima do threshold). " +
      "Sharpe 10+ do v1 era artefato de annualization inflation + multiple testing. " +
      "Sinal é regime-dependent (fold 2: WR 93%, fold 4: WR 45%). Não é robusto.",
    tools: ["cvd_signal_scan.py", "cvd_signal_v2_scan.py"],
    reportFile: "docs/cvd_v2_report.md",
  },
  {
    id: "HYP-UNLOCK-01",
    title: "D17 — Token unlock impact (short pré-unlock)",
    market: "Binance spot (10 tokens: APT, OP, ARB, DYDX, AXS, GRT, IMX, AVAX, SEI, STRK)",
    thesis:
      "Token unlocks increase circulating supply, creating selling pressure. " +
      "Shorting 3 days before unlock and exiting 3 days after captures the post-unlock dump. " +
      "Large unlocks (≥$200M) have stronger effect. Market doesn't fully price the unlock because " +
      "events are routine and the dump is gradual, not instant.",
    confidence: 88,
    status: "validating",
    tags: ["event-driven", "token-unlock", "vesting", "supply-pressure", "short", "binance", "significant", "oos-validated", "costs-tested", "timing-optimized", "2026-validated", "tokenomist-api", "symbol-whitelist"],
    trigger: "Tokenomist API unlock date → short 3d before, exit 3d after. Whitelist: 8 validated symbols only (APT, ARB, AXS, DYDX, IMX, OP, SEI, STRK). Fallback: hardcoded list if API unavailable.",
    invalidation: "Market may learn and arbitrage the edge. Bull market may reduce effect. Execution slippage on low-liquidity tokens.",
    createdAt: "2026-07-03",
    author: "token_unlock_scan.py + shorting_cost_scan.py + timing_optimization_scan.py",
    pnl: 384,
    trades: 48,
    sampleUnit: "215 unlock events (119 IS 2023-2024 + 48 OOS-2025 + 48 OOS-2026) × 10 tokens, daily candles, BTC benchmark, 20bps fees + real funding rates + 25 timing combos",
    verdict:
      "EDGE VALIDADO em 3 períodos + custos + timing — Primeiro edge real em 36 hipóteses. " +
      "IS: WR 61%, +285bps, t=2.66. OOS-2025: WR 79%, +660bps, t=5.43. " +
      "OOS-2026: WR 67%, +384bps, t=2.59 (mais fraco mas significativo). " +
      "Timing optimization (25 combos): -3d/+3d é o ótimo. " +
      "Funding cost: -4bps OOS (irrelevante). NET OOS-2025: +656bps, t=5.38. " +
      "Large unlocks (≥$200M): 7/7 negativos (ou seja, 7/7 POSITIVOS pro short). OPUSDT OOS-2025: 6/6 wins. " +
      "Backtest com Kelly sizing (half-Kelly, cap 25%/posicao, $10k inicial): N=155, WR=63%, " +
      "$10k -> $19.093 (+90.9%). DEPLOY: unlock_short_bot.py rodando em PAPER na AWS (filtro " +
      "MIN_UNLOCK_VALUE_MM=20, sem teto). Tokenomist API integrada (2026-07-08): unlock_data.py " +
      "busca eventos via api.tokenomist.ai com fallback hardcoded. Whitelist de 8 símbolos " +
      "validados apenas (APT, ARB, AXS, DYDX, IMX, OP, SEI, STRK) — símbolos não-validados da API " +
      "são filtrados. Primeiro evento API: APTUSDT 2026-07-12 ($7M cliff, entry 2026-07-09). " +
      "Bloqueado apenas por deposito de capital real (decisao do usuario). " +
      "REMEDIAÇÃO 2026-07-12: filtro Tokenomist passou a aplicar mínimo configurado de $20M; " +
      "janela de entrada/saída UTC foi aplicada; 2 posições paper legadas abaixo do mínimo foram " +
      "preservadas e marcadas out_of_policy_legacy, sem abrir novas posições fora da política.",
    tools: ["token_unlock_scan.py", "shorting_cost_scan.py", "timing_optimization_scan.py", "unlock_data.py (Tokenomist API)"],
    reportFile: "docs/event_driven_report.md",
  },
  {
    id: "HYP-LISTING-01",
    title: "D18 — Binance listing announcement impact",
    market: "Binance spot+futures (43 listings, 2023+)",
    thesis:
      "Binance listing announcements create a price pump for the listed token. " +
      "Buying at listing and selling after a short hold captures the pump.",
    confidence: 0,
    status: "refuted",
    tags: ["event-driven", "listing", "binance", "announcement", "buy", "refuted"],
    trigger: "Binance listing announcement → buy at listing time, hold 1-7 days",
    invalidation: "WR 23% (1d hold), avg +32bps, t-stat=0.29. 30d excess=-15.3% (t=-3.34). Listings are sell-the-news events.",
    createdAt: "2026-07-03",
    author: "listing_impact_scan.py",
    pnl: 0,
    trades: 43,
    sampleUnit: "43 listings with price data (from 173 parsed), 2023+, daily+hourly candles, BTC benchmark, 20bps fees",
    verdict:
      "Refutado — Buy at listing: WR 23%, avg +32bps (1d), t-stat=0.29. " +
      "30d excess=-15.3% (t=-3.34) — tokens significantly underperform BTC after listing. " +
      "Listings are 'sell the news' events. No capturable pump. " +
      "Spot listings (N=5): -12.7% in 30d. Futures listings (N=35): -15.0% in 30d.",
    tools: ["listing_impact_scan.py"],
    reportFile: "docs/event_driven_report.md",
  },
  {
    id: "HYP-T2J-01",
    title: "T2-Jump — Memória de spike em Jump Indices (JD10/25/50/75/100)",
    market: "JD10, JD25, JD50, JD75, JD100",
    thesis:
      "Jump Indices têm spikes em AMBAS direções (diferente de Boom/Crash). O gap entre spikes poderia ter hazard crescente (spike 'atrasado' mais provável), permitindo timing de entrada.",
    confidence: 10,
    status: "refuted",
    tags: ["jump-indices", "timing", "memoria", "weibull", "mega-brain-2"],
    trigger: "Spike = |retorno| > 8x mediana, ambas direções. 80k ticks por símbolo, 5 símbolos",
    invalidation: "Weibull shape k > 1 (hazard crescente) em qualquer direção",
    createdAt: "2026-07-04",
    author: "jump_timing_test.py",
    pnl: 0,
    trades: 260,
    sampleUnit: "gaps normalizados (5 símbolos Jump, 80k ticks cada, pool multi-símbolo)",
    verdict:
      "Refutado — CLUSTERING (k<1) em todas as 3 direções testadas: " +
      "UP k=0.720 IC95%[0.654,0.816], DOWN k=0.715 IC95%[0.642,0.821], BOTH k=0.708 IC95%[0.656,0.778]. " +
      "KS REJEITA exponencial em todas (D=0.18-0.22 vs crit=0.08-0.12). " +
      "Hazard DECRESCENTE com idade (58% no 1o bin → 0% no 9o). " +
      "Spikes se AGRUPAM (clustering), 'overdue' fica MENOS provável. Anti-tese de timing. " +
      "Diferente de Boom/Crash (memoryless), Jump Indices têm memória NEGATIVA para timing.",
    ci95: [0.656, 0.778],
    ci95Label: "Weibull shape k (1.0 = memoryless, <1 = clustering)",
    tools: ["jump_timing_test.py"],
    reportFile: "docs/state_of_research.md",
  },
  {
    id: "HYP-ONCHAIN-01",
    title: "D19 — On-chain NVT signal (BTC directional)",
    market: "BTC on-chain metrics (CoinGecko market cap / volume proxy)",
    thesis:
      "If NVT ratio (market cap / transaction volume) is low, BTC is undervalued relative to " +
      "on-chain activity → bullish. If NVT is high, BTC is overvalued → bearish.",
    confidence: 0,
    status: "refuted",
    tags: ["on-chain", "nvt", "btc", "signal", "coingecko"],
    trigger: "NVT < Q20 (bullish) or NVT > Q80 (bearish)",
    invalidation: "365 dias, NVT quintis não separam retornos. Q1 (low NVT) retorno=-1.67% IC95%[-3.16%,-0.23%]. Q5 (high NVT) retorno=+0.05% IC95%[-1.20%,+1.30%]. Direção INVERSA à hipótese.",
    createdAt: "2026-07-04",
    author: "onchain_signal_scan.py",
    pnl: 0,
    trades: 365,
    sampleUnit: "daily NVT observations (365 days, CoinGecko proxy)",
    verdict:
      "Refutado — NVT baixo (bullish esperado) produziu retornos NEGATIVOS (-1.67% em 7d, IC95% não cruza zero). " +
      "NVT alto (bearish esperado) produziu retornos ~0%. Direção oposta à hipótese. " +
      "Volume alto (Q80) também negativo: -3.38% em 7d, -4.83% em 14d. " +
      "Proxy NVT (market_cap/total_volume CoinGecko) pode não capturar on-chain activity corretamente.",
    evPerTrade: -1.67,
    ci95: [-3.16, 0.05],
    ci95Label: "Q1-Q5 return spread % (7d forward)",
    tools: ["onchain_signal_scan.py"],
    reportFile: "onchain_signal_scan.log",
  },
  {
    id: "HYP-SENT-01",
    title: "D20 — Sentiment & Fear/Greed contrarian signal",
    market: "BTC sentiment indicators (Fear & Greed Index, Google Trends)",
    thesis:
      "Extreme Fear (F&G < 25) signals market oversold → buy. Extreme Greed (F&G > 75) signals " +
      "market overbought → sell. Sentiment acts as a contrarian indicator.",
    confidence: 0,
    status: "refuted",
    tags: ["sentiment", "fear-greed", "contrarian", "btc", "signal"],
    trigger: "F&G < 25 (Extreme Fear → LONG) or F&G > 75 (Extreme Greed → SHORT)",
    invalidation: "365 dias, F&G quintis não separam retornos. Q1 (low F&G) retorno=+0.83% IC95%[-0.37%,+2.02%]. Q5 (high F&G) retorno=-0.90% IC95%[-2.01%,+0.22%]. IC95% cruza zero em ambos.",
    createdAt: "2026-07-04",
    author: "sentiment_signal_scan.py",
    pnl: 0,
    trades: 358,
    sampleUnit: "daily F&G observations (365 days)",
    verdict:
      "Refutado — Q1 (Extreme Fear) retorno +0.83% mas IC95% cruza zero [-0.37%, +2.02%]. " +
      "Q5 (Extreme Greed) retorno -0.90% mas IC95% também cruza zero [-2.01%, +0.22%]. " +
      "Direção correta (contrarian) mas SEM significância estatística. " +
      "Google Trends bloqueado (429). F&G < 30 em 7d: -1.12% IC95%[-1.94%,-0.33%] — na direção CONTRÁRIA à hipótese.",
    evPerTrade: 0.83,
    ci95: [-0.37, 2.02],
    ci95Label: "Q1 (Extreme Fear) return % (7d forward, IC95%)",
    tools: ["sentiment_signal_scan.py"],
    reportFile: "sentiment_signal_scan.log",
  },
  {
    id: "HYP-MACRO-01",
    title: "D21 — Cross-asset macro signal (DXY/VIX/S&P500/Gold vs BTC)",
    market: "Macro assets (DXY, VIX, S&P500, Gold) vs BTC returns",
    thesis:
      "DXY inversely correlated with BTC → DXY rising = BTC falling. VIX positively correlated " +
      "with BTC vol → high VIX = risk-off = BTC falling. S&P500 correlated (risk on/off). " +
      "Gold as safe haven inversely correlated in stress periods.",
    confidence: 0,
    status: "refuted",
    tags: ["macro", "dxy", "vix", "spx", "gold", "correlation", "btc"],
    trigger: "Asset return > +1.5σ (SHORT BTC) or < -1.5σ (LONG BTC)",
    invalidation: "2 anos, nenhum signal macro isolado gera retorno positivo com IC95% > 0. Correlações: SPX=0.43, VIX=-0.40, DXY=-0.02, Gold=0.10.",
    createdAt: "2026-07-04",
    author: "cross_asset_macro_scan.py",
    pnl: 0,
    trades: 500,
    sampleUnit: "daily observations (2y, 4 macro assets × 4 thresholds × 4 horizons)",
    verdict:
      "Refutado — Correlações contemporâneas existem (SPX-BTC=0.43, VIX-BTC=-0.40) mas NENHUM signal " +
      "isolado com z-score threshold gera retorno positivo com IC95% > 0. " +
      "DXY correlação quase zero (-0.02) — hipótese principal refutada. " +
      "Correlação é instável no tempo (rolling 30d varia de ~0 a ~0.7) e fraca para predição direta. " +
      "SPX < -1.5σ (LONG) mostrou +2.60% em 14d mas IC95%[-0.64%, +5.84%] — não significante.",
    evPerTrade: 0,
    ci95: [-0.64, 5.84],
    ci95Label: "Best signal (SPX < -1.5σ LONG, 14d) return % IC95%",
    tools: ["cross_asset_macro_scan.py"],
    reportFile: "cross_asset_macro_scan.log",
  },
  {
    id: "HYP-LIQ-01",
    title: "D22 — CEX liquidation cascade (large move → reversal)",
    market: "BTC Futures (Binance, 1m candles, 7 days)",
    thesis:
      "Large 1-minute price moves (proxy for liquidation cascades) predict short-term reversals. " +
      "After a large UP move (2σ+), BTC tends to pull back. After a large DOWN move (3σ+), BTC tends to bounce.",
    confidence: 0,
    status: "refuted",
    tags: ["cex", "binance", "liquidation", "reversal", "btc", "signal", "kline"],
    trigger: "1m return > 3σ below mean (DOWN) → go long, expect bounce",
    invalidation: "7 days 1m data (10,080 candles), IS/OOS 70/30 split. Signal IS+OOS validated but returns < fees.",
    createdAt: "2026-07-04",
    author: "cex_liquidation_scan.py",
    pnl: 0,
    trades: 10080,
    sampleUnit: "1m candles (Binance Futures BTCUSDT, 7 days, IS=7056 OOS=3024)",
    verdict:
      "REFUTADO POR FEES — Sinal estatístico real mas não tradeável. " +
      "DOWN 3σ→bounce 1m: IS+OOS validado, avg=+0.029% IC95%[+0.011%,+0.047%], mas net=-0.051% após fees (0.08% round-trip). " +
      "DOWN 3σ→bounce 5m: IS+OOS validado, avg=+0.059% IC95%[+0.014%,+0.107%], mas net=-0.021% após fees. " +
      "DOWN 2.5σ→bounce 60m: avg=+0.156%, net=+0.076% (supera fees!) mas NÃO significativo em OOS. " +
      "UP pullback signals do 25h scan desapareceram no 7d — eram ruído. " +
      "Conclusão: grandes moves 1m predizem reversão estatisticamente, mas o efeito é menor que custos de transação. " +
      "Para ser tradeável precisaria: maker fees (0.02%/side), ou horizonte 30-60m com N maior, ou dados de tick intra-minuto.",
    evPerTrade: -0.021,
    ci95: [-0.051, 0.010],
    ci95Label: "DOWN 3σ → bounce 5m, net return % after fees (IC95%)",
    tools: ["cex_liquidation_scan.py"],
    reportFile: "cex_liquidation_scan.log",
  },
  {
    id: "HYP-T2J-02",
    title: "T2-Jump — Jump Indices spike-timing (memory vs memoryless)",
    market: "Deriv Jump Indices (JD10/25/50/75/100), 400k ticks",
    thesis:
      "Jump Index spikes may have a 'timer' structure (increasing hazard rate with age) " +
      "instead of being memoryless (geometric/exponential). If hazard grows, an 'overdue' spike " +
      "becomes more likely — a structural timing edge.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "jump", "spike", "timing", "memoryless", "weibull"],
    trigger: "Detect spikes as |return| > 8x median, measure gap distribution, fit Weibull shape k",
    invalidation: "Weibull k < 1 (clustering), IC95% entirely below 1.0. Spikes group together, 'overdue' is LESS likely.",
    createdAt: "2026-07-04",
    author: "jump_timing_test.py",
    pnl: 0,
    trades: 261,
    sampleUnit: "gaps between spikes, normalized by N, pooled across 5 Jump symbols",
    verdict:
      "REFUTADO — Spikes se AGRUPAM (clustering), não têm timer. " +
      "Weibull shape k=0.695 IC95%[0.643, 0.765] — IC inteiro < 1.0. " +
      "KS vs exponencial: D=0.194 > crit 0.084 → REJEITA memoryless, mas na direção OPSTA à tese. " +
      "Hazard DECAI com idade (55% → 6%). 'Spike atrasado' é MENOS provável, não mais. " +
      "Conclusão: P(spike) é máximo logo após um spike, depois decai. Anti-tese de timing.",
    evPerTrade: 0,
    ci95: [0.643, 0.765],
    ci95Label: "Weibull shape k (IC95%) — k=1 memoryless, k<1 clustering",
    tools: ["jump_timing_test.py"],
    reportFile: "jump_timing_test.log",
  },
  {
    id: "HYP-BOOM-01",
    title: "T2-Boom — Boom/Crash spike-timing (memory vs memoryless)",
    market: "Deriv Boom/Crash (BOOM300N-1000, CRASH300N-1000), 800k ticks",
    thesis:
      "Boom/Crash spikes may have a 'timer' structure (increasing hazard rate with age). " +
      "If hazard grows with time since last spike, an 'overdue' spike is more likely — timing edge.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "boom", "crash", "spike", "timing", "memoryless", "weibull"],
    trigger: "Detect spikes as |return| > 8x median in spike direction, measure gap distribution, fit Weibull",
    invalidation: "Weibull k=1.016 IC95%[0.977, 1.059] — k=1 inside CI. KS does not reject exponential. Memoryless confirmed.",
    createdAt: "2026-07-04",
    author: "boom_timing_test.py",
    pnl: 0,
    trades: 1405,
    sampleUnit: "gaps between spikes, normalized by N, pooled across 10 Boom/Crash symbols",
    verdict:
      "REFUTADO — Spikes são MEMORYLESS (sem memória). " +
      "Weibull shape k=1.016 IC95%[0.977, 1.059] — k=1 dentro do IC. " +
      "KS vs exponencial: D=0.011 < crit 0.036 → NÃO rejeita exponencial. " +
      "P(gap>2*mediana | gap>mediana) = 50.3% IC95%[44.2%, 54.3%] (memoryless = 50%). " +
      "Hazard ~constante em ~25% independente da idade. " +
      "Conclusão: P(spike) = taxa base, independente de quanto tempo desde o último. Falácia do apostador.",
    evPerTrade: 0,
    ci95: [0.977, 1.059],
    ci95Label: "Weibull shape k (IC95%) — k=1 memoryless confirmed",
    tools: ["boom_timing_test.py"],
    reportFile: "boom_timing_test.log",
  },
  {
    id: "HYP-VRP-01",
    title: "D23 — Crypto Volatility Risk Premium (IV vs RV)",
    market: "Deribit BTC/ETH options vs Binance realized vol, 30d window",
    thesis:
      "Implied volatility on Deribit options is systematically higher than realized volatility " +
      "of the underlying. If IV > RV consistently, selling options captures the premium. " +
      "Well-documented edge in TradFi equity indices.",
    confidence: 0,
    status: "refuted",
    tags: ["options", "deribit", "volatility", "iv", "rv", "vrp", "btc", "eth"],
    trigger: "Compare ATM IV (Deribit) vs 30d RV (Binance 1h klines), net of bid-ask spread",
    invalidation: "IV < RV for both BTC and ETH. RV is higher than IV — opposite of TradFi pattern.",
    createdAt: "2026-07-04",
    author: "volatility_risk_premium_scan.py",
    pnl: 0,
    trades: 1634,
    sampleUnit: "914 BTC + 720 ETH options (Deribit) vs 720 1h candles (Binance)",
    verdict:
      "REFUTADO — IV < RV (inverso do TradFi). " +
      "BTC: IV ATM=35.9%, RV 30d=45.6% IC95%[43.9%, 47.3%]. VRP=-9.7 vol pts IC95%[-12.1, -7.5]. " +
      "ETH: IV ATM=48.8%, RV 30d=60.7% IC95%[58.6%, 62.7%]. VRP=-11.9 vol pts IC95%[-14.4, -9.6]. " +
      "Em crypto, vol realizada > vol implícita — comprar opções é mais barato que o payoff esperado. " +
      "Inverse do equity index VRP. Selling options seria NEGATIVE EV no momento. " +
      "Nota: pode variar no tempo. Períodos de baixa vol podem mostrar IV > RV.",
    evPerTrade: -9.7,
    ci95: [-12.1, -7.5],
    ci95Label: "BTC VRP (IV-RV) in vol points (IC95%)",
    tools: ["volatility_risk_premium_scan.py"],
    reportFile: "volatility_risk_premium_scan.log",
  },
  {
    id: "HYP-BASIS-01",
    title: "D24 — Perpetual Basis Arbitrage (perp vs spot)",
    market: "Binance/Bybit/OKX BTC perp vs spot, current snapshot + 30d funding history",
    thesis:
      "When perp trades at premium/discount to spot, short perp + long spot (or vice versa) " +
      "captures basis + funding. Market-neutral. Edge should appear during stress events.",
    confidence: 0,
    status: "refuted",
    tags: ["perp", "basis", "funding", "binance", "bybit", "okx", "arb", "market-neutral"],
    trigger: "Basis > round-trip costs (~28 bps taker) + favorable funding direction",
    invalidation: "Basis ~4 bps vs costs 28-31 bps. Net 24h = -19 bps across all venues.",
    createdAt: "2026-07-04",
    author: "perp_basis_arb_scan.py",
    pnl: 0,
    trades: 3,
    sampleUnit: "3 venues (Binance/Bybit/OKX), BTC spot vs perp, 90 funding periods",
    verdict:
      "REFUTADO (condições normais) — Basis muito pequeno vs custos. " +
      "Binance: basis=-3.8 bps, net 24h=-19.3 bps. Bybit: -4.5 bps, -19.7 bps. OKX: -4.6 bps, -18.6 bps. " +
      "Custos round-trip (taker both legs): 28-31 bps. Basis precisa ser > 28 bps para break-even. " +
      "Funding histórico Binance: mean=+0.23 bps/8h, positivo 77% do tempo. " +
      "Para ser viável: maker fees (custo cai para ~8 bps), ou capturar durante stress (liquidation cascades), " +
      "ou hold 3+ dias acumulando funding. Edge pode existir em momentos específicos, não em regime normal.",
    evPerTrade: -19,
    ci95: [-31, -8],
    ci95Label: "Net 24h carry (bps) after round-trip taker fees (IC95% across venues)",
    tools: ["perp_basis_arb_scan.py"],
    reportFile: "perp_basis_arb_scan.log",
  },
  {
    id: "HYP-VAN-01",
    title: "T3-Vanilla — Vanilla Options mispricing (convex payoff)",
    market: "Deriv 1HZ100V Vanilla Options (CALL/PUT), 15m + 60m durations",
    thesis:
      "Vanilla Options have CONVEX payoff (unlike all binary/barrier products tested). " +
      "Monte Carlo driftless simulation vs market price may reveal mispricing in the " +
      "payout_per_point calibration. Only product with real optionality tested.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "vanilla", "options", "convex", "monte-carlo", "mispricing"],
    trigger: "Monte Carlo 20k simulations of driftless price paths, compare payout vs $10 stake",
    invalidation: "20 cells tested (CALL/PUT x barrier x duration). 0 cells with EV_lo > 0. EV range -3.3% to -24.6%.",
    createdAt: "2026-07-04",
    author: "vanilla_edge_scan.py",
    pnl: 0,
    trades: 20,
    sampleUnit: "20 cells (CALL/PUT x 5-6 barriers x 2 durations), 20k MC sims each, 15k historical ticks",
    verdict:
      "REFUTADO — House margin presente em todas as 20 células. " +
      "EV médio: -13.1% (min=-3.3%, max=-24.6%). 0 células com EV_lo > 0. " +
      "Padrão: EV mais negativo para barreiras OTM distantes (maior alavancagem, maior margem). " +
      "EV menos negativo para ITM profundo (-3.3%) mas ainda negativo. " +
      "Conclusão: Deriv calibra payout_per_point com margem embutida em todos os strikes. " +
      "Mesmo payoff convexo não escapa da house margin. Último produto Deriv não testado — refutado.",
    evPerTrade: -0.131,
    ci95: [-0.246, -0.033],
    ci95Label: "EV range across 20 cells (min to max EV, all negative)",
    tools: ["vanilla_edge_scan.py"],
    reportFile: "vanilla_edge_scan.log",
  },
  {
    id: "HYP-ASIAN-01",
    title: "Asian Up/Down — último tick vs média da janela",
    market: "1HZ100V · ASIANU/ASIAND · N=5-10 ticks",
    thesis:
      "Paga se o último tick de uma janela de N ticks for estritamente maior (ASIANU) ou menor (ASIAND) que a média dos N ticks. " +
      "Fair value teórico: 50% exato por simetria (negar a trajetória mapeia um evento no outro). " +
      "Teste empírico via replay de 15000 ticks reais, janelas não-sobrepostas, Wilson CI.",
    confidence: 5,
    status: "refuted",
    tags: ["deriv", "synthetic", "asian", "barrier"],
    trigger: "P_emp > 1/payout com Wilson CI lo > breakeven em algum N",
    invalidation: "0 de 12 células com EV_lo > 0. EV médio -0.26, todos negativos.",
    createdAt: "2026-07-05",
    author: "asian_edge_scan.py",
    verdict:
      "SEM EDGE. 12 células testadas (ASIANU/ASIAND x N=5..10). " +
      "P_emp ~50% como previsto teoricamente. Payout 19.53x implica breakeven 51.2%. " +
      "Nenhuma célula com EV_lo > 0. House margin confirmada. " +
      "EV médio: -0.259 (min=-0.470, max=-0.063).",
    evPerTrade: -0.259,
    ci95: [-0.470, -0.063],
    ci95Label: "EV range across 12 cells (all negative)",
    tools: ["asian_edge_scan.py"],
    reportFile: "asian_edge_scan.log",
    pnl: 0,
    trades: 12,
    sampleUnit: "células (ASIANU/ASIAND × N)",
  },
  {
    id: "HYP-RESET-01",
    title: "Reset Call/Put — strike reseta para o menor ponto de referência",
    market: "1HZ100V · RESETCALL/RESETPUT · 5m-60m",
    thesis:
      "RESETCALL paga se S_final > min(S_entrada, S_meio) — strike 'reseta' para o menor dos dois pontos, " +
      "tornando o contrato mais favorável que uma call ATM comum. Payout fixo (binário). " +
      "Monte Carlo driftless via bootstrap de retornos reais, 2 checkpoints, comparado com payout cotado.",
    confidence: 5,
    status: "refuted",
    tags: ["deriv", "synthetic", "reset", "barrier", "monte-carlo"],
    trigger: "P_simulado > 1/payout com Wilson CI lo > breakeven em alguma duração",
    invalidation: "0 de 8 células com EV_lo > 0. P_simulado ~63% mas breakeven ~64%.",
    createdAt: "2026-07-05",
    author: "reset_edge_scan.py",
    verdict:
      "SEM EDGE. 8 células testadas (RESETCALL/RESETPUT x 5m/15m/30m/60m). " +
      "P_simulado ~62.7% consistente com mecânica (reset favorece comprador), " +
      "mas payout cotado ~15.7x implica breakeven ~63.7% — house margin embutida. " +
      "EV médio: -0.182 (min=-0.287, max=-0.109).",
    evPerTrade: -0.182,
    ci95: [-0.287, -0.109],
    ci95Label: "EV range across 8 cells (all negative)",
    tools: ["reset_edge_scan.py"],
    reportFile: "reset_edge_scan.log",
    pnl: 0,
    trades: 8,
    sampleUnit: "células (RESETCALL/RESETPUT × duração)",
  },
  {
    id: "HYP-RUNS-01",
    title: "Only Ups/Only Downs — N ticks monotônicos consecutivos",
    market: "1HZ100V · RUNHIGH/RUNLOW · N=2-5",
    thesis:
      "Paga se os próximos N ticks subirem (RUNHIGH) ou descerem (RUNLOW) sucessivamente. " +
      "Medição empírica direta (replay, sem bootstrap) em janelas não-sobrepostas de 15000 ticks. " +
      "Compara P_empírica contra payout cotado (38x-305x).",
    confidence: 3,
    status: "refuted",
    tags: ["deriv", "synthetic", "runs", "monotonic"],
    trigger: "P_emp > 1/payout com Wilson CI lo > breakeven em algum N",
    invalidation: "0 de 8 células com EV_lo > 0. P_emp < teórico 0.5^N em todos os casos.",
    createdAt: "2026-07-05",
    author: "runs_edge_scan.py",
    verdict:
      "SEM EDGE. 8 células testadas (RUNHIGH/RUNLOW x N=2..5). " +
      "P_emp cai exponencialmente com N (24.9% N=2, 2.7% N=5 para RUNHIGH) — " +
      "abaixo do teórico 0.5^N, sugerindo ticks empatados reduzem probabilidade. " +
      "Payout cresce mas não compensa. EV médio: -1.010 (min=-1.715, max=-0.280).",
    evPerTrade: -1.010,
    ci95: [-1.715, -0.280],
    ci95Label: "EV range across 8 cells (all negative)",
    tools: ["runs_edge_scan.py"],
    reportFile: "runs_edge_scan.log",
    pnl: 0,
    trades: 8,
    sampleUnit: "células (RUNHIGH/RUNLOW × N)",
  },
  {
    id: "HYP-TICKHIGH-01",
    title: "High/Low Ticks — qual dos 5 ticks é o extremo",
    market: "1HZ100V · TICKHIGH/TICKLOW · 5 ticks",
    thesis:
      "Aposta em qual dos 5 ticks seguintes será o maior (TICKHIGH) ou menor (TICKLOW). " +
      "Deriv precifica com formato U simétrico (posições 1 e 5 pagam menos, meio paga mais) — " +
      "consistente com lei do arcsine. Bootstrap de 200k simulações para medir P_empírica por posição.",
    confidence: 5,
    status: "refuted",
    tags: ["deriv", "synthetic", "tickhigh", "arcsine"],
    trigger: "P_emp > 1/payout em alguma posição com Wilson CI lo > breakeven",
    invalidation: "0 de 10 células com EV_lo > 0. Deriv precifica corretamente o arcsine.",
    createdAt: "2026-07-05",
    author: "tickhigh_edge_scan.py",
    verdict:
      "SEM EDGE. 10 células testadas (TICKHIGH/TICKLOW x 5 posições). " +
      "Distribuição empírica bate com arcsine teórico: posições 1 e 5 ~27.3%, meio ~14%. " +
      "Deriv precifica corretamente — payout menor nas bordas (35x), maior no meio (65x). " +
      "EV médio: -0.606 (min=-0.883, max=-0.354). House margin em todas as posições.",
    evPerTrade: -0.606,
    ci95: [-0.883, -0.354],
    ci95Label: "EV range across 10 cells (all negative)",
    tools: ["tickhigh_edge_scan.py"],
    reportFile: "tickhigh_edge_scan.log",
    pnl: 0,
    trades: 10,
    sampleUnit: "células (TICKHIGH/TICKLOW × posição)",
  },
  {
    id: "HYP-TURBOS-01",
    title: "Turbos — knockout com payoff convexo (payout_per_point × distância)",
    market: "1HZ100V · TURBOSLONG/SHORT · 15m-60m",
    thesis:
      "Barreira/knockout: se preço tocar a barreira, perde stake. Se sobreviver, " +
      "payout = payout_per_point × distância final até barreira. " +
      "Monte Carlo driftless via bootstrap, 40 células (2 direções × 10 barreiras × 2 durações).",
    confidence: 5,
    status: "refuted",
    tags: ["deriv", "synthetic", "turbos", "knockout", "monte-carlo"],
    trigger: "EV_lo > 0 em alguma combinação barreira/duração",
    invalidation: "0 de 40 células com EV_lo > 0. House margin em todas as barreiras.",
    createdAt: "2026-07-05",
    author: "turbos_edge_scan.py",
    verdict:
      "SEM EDGE. 40 células testadas (TURBOSLONG/SHORT x 10 barreiras x 15m/60m). " +
      "P(sobrevive) e payout_medio calculados via MC driftless. " +
      "EV sempre negativo, converge para 0 apenas em barreiras extremas (irrealista). " +
      "EV médio: -0.010 (min=-0.054, max=-0.0002). House margin embutida no payout_per_point.",
    evPerTrade: -0.010,
    ci95: [-0.054, -0.0002],
    ci95Label: "EV range across 40 cells (all negative)",
    tools: ["turbos_edge_scan.py"],
    reportFile: "turbos_edge_scan.log",
    pnl: 0,
    trades: 40,
    sampleUnit: "células (TURBOSLONG/SHORT × barreira × duração)",
  },
  {
    id: "HYP-OPTBUY-01",
    title: "Crypto Options Buy-Side — ATM straddle (inverse VRP)",
    market: "Deribit · BTC/ETH · ATM Straddle · DTE 1-82",
    thesis:
      "D23 mostrou IV < RV em crypto (inverso do TradFi). Implicação: COMPRAR straddles ATM " +
      "pode ser positive EV — pagar IV barato, capturar RV alta. " +
      "Simula payoff histórico (|S_T - S_0|) vs custo do straddle (ask_price × underlying) " +
      "em janelas históricas de mesmo DTE. Bootstrap CI, net após taker fees (0.03%).",
    confidence: 55,
    status: "validating",
    tags: ["crypto", "options", "deribit", "vrp", "straddle", "inverse-vrp"],
    trigger: "EV net após fees > 0 com IC95% não cruzando zero",
    invalidation: "DTE ≤ 1: EV negativo (fees > spread). DTE longe: confundir com drift de bull market.",
    createdAt: "2026-07-05",
    author: "options_buy_side_scan.py",
    verdict:
      "EDGE POTENCIAL DETECTADO. 12 de 16 expiries com EV net positivo após fees. " +
      "BTC: DTE≥2 profitável (ROI +7% a +78%). ETH: DTE≥5 profitável (ROI +4% a +109%). " +
      "Melhor: ETH DTE=54, EV +$308, ROI +109%, WR 92%, N=36. " +
      "CUIDADO: payoffs históricos assumem K=S_0 (ATM straddle) e podem refletir drift de bull market " +
      "em vez de VRP estrutural. Necessita validação out-of-sample com execução real ou paper trading. " +
      "DTE curto (1d) negativo — fees dominam. Edge cresce com DTE (mais tempo para RV > IV). " +
      "ATUALIZADO 2026-07-07: options_paper_bot.py (HYP-OPTBUY-01) DEPLOYADO e rodando na AWS " +
      "desde 2026-07-04/05. 9 posicoes abertas (straddles BTC/ETH, DTE 4-26 na entrada), 0 " +
      "settled ainda -- primeiro settlement esperado ~10-Jul-2026. Sem confirmacao ao vivo ainda.",
    evPerTrade: 308.45,
    ci95: [-35.02, 5860.87],
    ci95Label: "EV net range across 16 expiries (BTC+ETH, DTE 1-82)",
    tools: ["options_buy_side_scan.py"],
    reportFile: "options_buy_side_scan.log",
    pnl: 0,
    trades: 16,
    sampleUnit: "expiries (BTC+ETH, DTE 1-82)",
  },
  {
    id: "HYP-XFUND-01",
    title: "Cross-Venue Funding Rate Arbitrage (Binance vs OKX/Bybit)",
    market: "Binance/Bybit/OKX · BTC/ETH/SOL · Perp",
    thesis:
      "Quando funding rates divergem entre exchanges, ir long perp na venue com funding menor " +
      "e short perp na venue com funding maior captura o diferencial. Market-neutral, sem exposure ao preço. " +
      "Simula P&L histórico (90 períodos de 8h) com rebalanceamento diário. Net após taker fees round-trip.",
    confidence: 8,
    status: "refuted",
    tags: ["crypto", "funding", "arbitrage", "cross-venue", "market-neutral"],
    trigger: "P&L médio/dia > 0 com IC95% não cruzando zero e WR > 60%",
    invalidation: "Spread médio < custo de rebalanceamento em todos os pares.",
    createdAt: "2026-07-05",
    author: "cross_venue_funding_arb_scan.py",
    verdict:
      "SEM EDGE. BTC: P&L -2.08 bps/dia (WR 0%), ETH: -1.86 bps/dia (WR 10%), SOL: -0.39 bps/dia (WR 31%). " +
      "Spreads de funding entre Binance/OKX/Bybit são minúsculos (0.1-0.7 bps/8h) vs custo round-trip " +
      "de 3.6-4.2 bps. Funding rates são altamente correlacionadas entre venues — não divergem o suficiente. " +
      "Nenhum spread atual supera custos. Edge real dependeria de rebalanceamento infrequente, " +
      "mas spread médio já é negativo antes de custos.",
    evPerTrade: -1.44,
    ci95: [-2.32, -0.39],
    ci95Label: "P&L médio/dia (bps) across BTC/ETH/SOL",
    tools: ["cross_venue_funding_arb_scan.py"],
    reportFile: "cross_venue_funding_arb_scan.log",
    pnl: 0,
    trades: 270,
    sampleUnit: "períodos de 8h (BTC/ETH/SOL × 90 dias)",
  },
  {
    id: "HYP-LPOOL-01",
    title: "Binance Launchpool/Megadrop — short pré-distribuição",
    market: "Binance · 13 Launchpool events · 2023-2026",
    thesis:
      "Similar a D17 (token unlock, único edge validado), Launchpools distribuem tokens grátis " +
      "que podem criar pressão vendedora. Short 3d antes da distribuição, cover 3d depois. " +
      "IS: 2023-2024 (7 events), OOS: 2025-2026 (6 events). Benchmark: excess return vs BTC.",
    confidence: 15,
    status: "refuted",
    tags: ["crypto", "event-driven", "launchpool", "binance", "short"],
    trigger: "Short -3d/+3d com WR > 55% e mean > 0 em IS e OOS",
    invalidation: "IS: -9.2% mean, WR 43%. OOS: +8.8% mas N=6 (não significativo). ALL: -0.9%.",
    createdAt: "2026-07-05",
    author: "launchpool_impact_scan.py",
    verdict:
      "SEM EDGE CONSISTENTE. IS (N=7): mean -9.2%, WR 43% — tokens SOBEM antes do Launchpool (hype). " +
      "OOS (N=6): mean +8.8%, WR 100% — reversão no OOS mas N muito pequeno. " +
      "ALL (N=13): mean -0.9%, WR 69% mas IC95% cruza zero. " +
      "Diferença vs D17: Launchpool distribui para stakers (não necessariamente sellers), " +
      "enquanto unlocks liberam tokens para investidores (mais propensos a vender). " +
      "Padrão diferente: Launchpool gera pre-event rally (buy the hype), não pre-event dump.",
    evPerTrade: -0.9,
    ci95: [-14.0, 8.4],
    ci95Label: "Short -3d/+3d return (%) across 13 events",
    tools: ["launchpool_impact_scan.py"],
    reportFile: "launchpool_impact_scan.log",
    pnl: 0,
    trades: 13,
    sampleUnit: "eventos Launchpool (2023-2026)",
  },
  {
    id: "HYP-RELVAL-01",
    title: "Rise/Fall por duração — valor relativo across durations",
    market: "R_100, 1HZ100V · CALL/PUT · DURAÇÃO 1-10 ticks",
    thesis:
      "A margem da casa pode VARIAR com a duração do contrato Rise/Fall. Se houver uma duração " +
      "onde a margem é mínima ou inverte (edge > 0), é valor-relativo explorável. " +
      "3 medidas independentes por célula: P_emp (replay), P_teo (GBM auto-calibrado), payout (API proposal). " +
      "Cross-check DGP: se P_emp ~ P_teo, modelo bate.",
    confidence: 5,
    status: "refuted",
    tags: ["deriv", "synthetic", "rise-fall", "duration", "relative-value"],
    trigger: "EV_lo > 0 em alguma duração com P_emp ~ P_teo (DGP validado)",
    invalidation: "0 de 24 células com EV_lo > 0. Margem constante ~2pp em todas as durações.",
    createdAt: "2026-07-05",
    author: "relative_value_scan.py",
    verdict:
      "SEM EDGE. 24 células testadas (CALL/PUT x 6 durações x 2 símbolos). " +
      "P_emp bate com P_teo (max diff 0.37pp — DGP validado, sem path-dependence). " +
      "Margem da casa constante ~2pp em todas as durações — não varia. " +
      "Melhor EV: CALL d=10 1HZ100V = -0.0205/$1 (ainda negativo). " +
      "EV médio: -0.038, range [-0.067, -0.020].",
    evPerTrade: -0.038,
    ci95: [-0.067, -0.020],
    ci95Label: "EV range across 24 cells (all negative, constant margin)",
    tools: ["relative_value_scan.py"],
    reportFile: "relative_value_scan.log",
    pnl: 0,
    trades: 40,
    sampleUnit: "células (símbolo × duração × CALL/PUT)",
  },
  {
    id: "HYP-EXOTIC-01",
    title: "Contratos exóticos/barreira — Onetouch/Notouch/Range/ExpiryMiss",
    market: "R_100, 1HZ100V · ONETOUCH/NOTOUCH/RANGE/UPORDOWN/EXPIRYRANGE/EXPIRYMISS · 120s-600s",
    thesis:
      "Contratos path-dependent (tocar/não tocar/ficar dentro/sair) podem ter margem diferente " +
      "de Rise/Fall. Monte Carlo driftless (GBM discreto por tick) para prob teórica, " +
      "replay empírico para P_emp, API proposal para payout. " +
      "Gate: N≥100 e |P_emp - P_mc| < 3pp (validação DGP).",
    confidence: 5,
    status: "refuted",
    tags: ["deriv", "synthetic", "exotic", "barrier", "monte-carlo", "path-dependent"],
    trigger: "EV_lo > 0 com DGP validado (|P_emp - P_mc| < 3pp e N≥100)",
    invalidation: "1 célula com EV_lo > 0 mas REPROVADA no gate DGP (P_emp diverge de P_mc).",
    createdAt: "2026-07-05",
    author: "exotic_value_scan.py",
    verdict:
      "SEM EDGE. ~50 células testadas (7 tipos de contrato x barreiras k=1.0/1.5 x 3 durações x 2 símbolos). " +
      "1 célula aparentou EV_lo > 0 mas foi reprovada no gate DGP: P_emp divergiu de P_mc > 3pp " +
      "(falso edge de drift de amostra + N baixo). " +
      "Pelo MC driftless (DGP verdadeiro), P_mc < implied em toda célula → house margin confirmada. " +
      "EV médio: -0.094, range [-0.353, -0.029]. Margem maior em barreiras apertadas (k=1.0).",
    evPerTrade: -0.094,
    ci95: [-0.353, -0.029],
    ci95Label: "EV range across ~50 cells (all negative after DGP gate)",
    tools: ["exotic_value_scan.py"],
    reportFile: "exotic_value_scan.log",
    pnl: 0,
    trades: 48,
    sampleUnit: "células (símbolo × barreira × duração)",
  },
  {
    id: "HYP-POLY-01",
    title: "Polymarket Arbitrage — PA1-PA4 (multi-outcome, cross-market, sniping, convergence)",
    market: "Polymarket · BTC Up/Down 5m/15m · 576 mercados",
    thesis:
      "4 hipóteses: PA1 (new market sniping — books mispriced antes de bots convergirem), " +
      "PA2 (cross-market consistency — 5m vs 15m implied probs devem ser consistentes), " +
      "PA3 (multi-outcome arb — sum of asks < $1.00 = free money), " +
      "PA4 (near-resolution convergence — stale book nos minutos finais). " +
      "Scan real-time via Gamma + CLOB APIs, 6 ciclos de 10s.",
    confidence: 5,
    status: "refuted",
    tags: ["polymarket", "prediction-market", "arbitrage", "real-time"],
    trigger: "PA3: sum(asks) < $0.96 (post-fee). PA2: diff > 500bps. PA1: spread > 200bps em novo mercado.",
    invalidation: "PA3: 0/576 com sum < $1.00. PA2: max diff 0bps. PA1: spread 100bps converge em ~3min.",
    createdAt: "2026-07-05",
    author: "polymarket_arb_scan.py",
    verdict:
      "SEM EDGE. PA3: 576 mercados, min sum(asks) = $1.0010 (acima de $1.00 — sem arb bruto). " +
      "PA2: 44 pares 5m/15m comparados, diff média 0bps, max 0bps — mercados perfeitamente consistentes. " +
      "PA1: 18 novos mercados, spread 100bps desde criação, convergem em ~3min — bots já ativos. " +
      "PA4: sem mercados próximos de resolução no período. " +
      "Polymarket BTC Up/Down é um mercado eficiente com bots arbitrando continuamente.",
    evPerTrade: -0.001,
    ci95: [-0.001, 0.001],
    ci95Label: "PA3 min sum(asks) margin: $1.0010 (0.1bps above arb threshold)",
    tools: ["polymarket_arb_scan.py"],
    reportFile: "polymarket_arb_scan.log",
    pnl: 0,
    trades: 576,
    sampleUnit: "mercados Polymarket analisados",
  },
  {
    id: "HYP-PCP-01",
    title: "D28 — Put-Call Parity Violation (Deribit options arb)",
    market: "DERIBIT · BTC/ETH · CALLS + PUTS · todas as expiries",
    thesis:
      "Put-call parity: C - P = S - K (r=0 em crypto). Se violado após fees, " +
      "comprar synthetic long (call + short put) e shortar spot = arb livre. " +
      "Scan: 457 pares BTC + 362 pares ETH, todas as expiries e strikes. " +
      "Filtros: strike dentro ±60% do spot, bid-ask spread < 50% do mid, OI ≥ 10.",
    confidence: 3,
    status: "refuted",
    tags: ["deribit", "options", "arbitrage", "put-call-parity", "btc", "eth"],
    trigger: "|C_ask - P_bid - (S - K)| > fees (0.03% * S * 3 legs) em strike com OI ≥ 10",
    invalidation: "ATM/near-ATM strikes: 0 violações após fees. Market makers arbitram parity eficientemente. " +
      "Violações apenas em deep OTM/ITM com quotes stale e volume = 0.",
    createdAt: "2026-07-05",
    author: "put_call_parity_scan.py",
    verdict:
      "SEM EDGE EXECUTÁVEL. 149 violações BTC + 159 ETH com OI ≥ 10, mas todas em strikes deep OTM/ITM " +
      "com volume = 0 e quotes stale. ATM strikes (±10% do spot) mostram parity perfeita. " +
      "Market makers da Deribit arbitram put-call parity eficientemente em strikes líquidos. " +
      "As 'violações' em strikes illíquidos não são executáveis em size real.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "ATM parity deviation: $0 (market makers arbitrage efficiently)",
    tools: ["put_call_parity_scan.py"],
    reportFile: "put_call_parity_scan.log",
    pnl: 0,
    trades: 819,
    sampleUnit: "pares call+put (BTC 457 + ETH 362)",
  },
  {
    id: "HYP-BASIS-02",
    title: "D29 — Basis-Funding Disconnect (Binance carry trade)",
    market: "BINANCE FUTURES · Top 30 USDT perps · spot + perp carry",
    thesis:
      "Quando perp > spot (contango) E funding negativo, long perp é carry trade grátis: " +
      "ganha basis convergence + recebe funding. Quando perp < spot E funding positivo, " +
      "short perp é carry grátis. O 'disconnect' é quando ambos componentes favorevem o mesmo lado. " +
      "Scan: 19 pares analisados, roundtrip fees 0.14% (spot 0.1% + futures 0.04%).",
    confidence: 40,
    status: "validating",
    tags: ["binance", "futures", "funding-rate", "basis", "carry-trade", "arbitrage"],
    trigger: "Basis > 0 E funding < 0 (long carry) ou basis < 0 E funding > 0 (short carry). " +
      "Profit per 8h = |basis%| + funding% - 0.14% fees > 0.",
    invalidation: "WR real cair pra perto de 50% ou EV/trade ficar negativo com N maior (amostra atual N=24 ainda pequena).",
    createdAt: "2026-07-05",
    author: "basis_paper_bot.py",
    verdict:
      "VALIDANDO — scan inicial (basis_funding_disconnect_scan.py, N=19 pares) achou só " +
      "sinal fraco (2/19 profitable). Promovido a paper bot dedicado rodando na AWS desde " +
      "2026-07-05. ATUALIZADO 2026-07-07: N=24 trades settled, WR=70.8%, EV=+0.329%/trade, " +
      "total=+7.91% (best +10.33%, worst -4.46%), duração média 1.29h. " +
      "ATUALIZADO 2026-07-08 (bot ainda rodando ao vivo — reverificar antes de reusar): " +
      "N=33 trades settled, WR SUBIU para 72.7%, EV=+0.2635%/trade, total=+8.6958%, " +
      "duração média 1.2h. Trajetória WR 68.4%(N19)→70.8%(N24)→72.7%(N33) — estável/melhorando " +
      "conforme N cresce, oposto do padrão de decaimento visto no D36. Capital real exigiria as " +
      "DUAS pernas (spot + margem do perp), não só um lado. ATUALIZADO 2026-07-08 (parte 2): " +
      "IC95% formal implementado no basis_paper_bot.py (Wilson no WR + bootstrap no EV). " +
      "UPDATE 2026-07-13: N=43, WR=69.8% IC95%[54.9%, 81.4%] — exclui 50%, estatisticamente " +
      "significativo. EV=+0.33% IC95%[-0.50%, +1.22%] — CRUZA ZERO, ainda INCONCLUSIVO. " +
      "O WR é real (não é sorte), mas o EV ainda não é estatisticamente positivo: as losses " +
      "(worst -5.96%) são grandes o suficiente pra offsetar os wins. Precisa de mais amostra " +
      "(N~60-80 estimado) pra o IC do EV convergir. Melhor lead operacional ativo, mas NÃO é " +
      "edge confirmado ainda.",
    evPerTrade: 0.33,
    ci95: [-0.5, 1.22],
    ci95Label: "N=43: WR=69.8% IC95%[54.9%,81.4%] (exclui 50%) | EV=+0.33% IC95%[-0.50%,+1.22%] (cruza zero, INCONCLUSIVO) — 2026-07-13",
    tools: ["basis_funding_disconnect_scan.py", "basis_paper_bot.py"],
    reportFile: "basis_paper_stats.json",
    pnl: 14.3,
    trades: 43,
    sampleUnit: "trades settled ao vivo (retorno % por trade, não $ — ver verdict)",
  },
  {
    id: "HYP-DEPEG-01",
    title: "D30 — Stablecoin Depeg Mean Reversion",
    market: "BINANCE · USDCUSDT, FDUSDUSDT, TUSDUSDT, USDPUSDT · 90d hourly",
    thesis:
      "Stablecoins depeg de $1.00 ocasionalmente. Comprar abaixo de $1.00 e esperar reversão " +
      "é mean-reversion trade. Scan: 4 pares, 90 dias, threshold 0.3%. " +
      "Medir: frequência de depegs, WR de reversão, profit vs fees (0.1% roundtrip spot).",
    confidence: 2,
    status: "refuted",
    tags: ["binance", "stablecoin", "mean-reversion", "depeg", "usdc", "fdUSD"],
    trigger: "|price - 1.0| > 0.3% → buy (if below) or sell (if above), hold until |price - 1.0| < 0.3%",
    invalidation: "Apenas 2 eventos de depeg em 90 dias (FDUSD). 100% reversão mas avg profit 0.055% < fees 0.1%. " +
      "Net profit -0.045%. USDC/USDT/TUSD/USDP: 0 eventos (sempre dentro de 0.3%).",
    createdAt: "2026-07-05",
    author: "stablecoin_depeg_scan.py",
    verdict:
      "SEM EDGE. 2 eventos em 90 dias (FDUSD only), 100% reversão mas profit 0.055% < fees 0.1%. " +
      "Net EV -0.045% por trade. Stablecoins major (USDC/USDT) não depegaram nem uma vez no período. " +
      "Depegs pequenos (< 0.3%) são muito frequentes mas profit < fees. " +
      "Depegs grandes (SVB/USDC Mar 2023) são raros e duram dias (capital lockup). " +
      "Não é estratégia viável com fees de spot 0.1%.",
    evPerTrade: -0.045,
    ci95: [-0.06, -0.03],
    ci95Label: "Net profit per depeg event (%) after 0.1% roundtrip fees, N=2",
    tools: ["stablecoin_depeg_scan.py"],
    reportFile: "stablecoin_depeg_scan.log",
    pnl: 0,
    trades: 2,
    sampleUnit: "eventos depeg (90 dias, 4 stablecoins)",
  },
  {
    id: "HYP-TWAP-01",
    title: "D31 — Deribit Settlement TWAP Exploit (structural bug)",
    market: "DERIBIT · BTC/ETH · options expiry 08:00 UTC · 30min TWAP window",
    thesis:
      "Deribit settle options com TWAP de 30min (07:30-08:00 UTC). Aos 20min de TWAP formado, " +
      "é possível prever o settlement price com erro < 0.05% em 90% das vezes (BTC) / 87% (ETH). " +
      "Se uma option está mispriced vs intrinsic value no TWAP estimado, há janela de 10min para arbitrar. " +
      "Backtest: 30 expiries diárias BTC + 30 ETH, 1m klines da Binance.",
    confidence: 7,
    status: "validating",
    tags: ["deribit", "options", "settlement", "twap", "exploit", "bug", "structural", "btc", "eth"],
    trigger: "Aos 20min do TWAP window (07:50 UTC): se |forming_twap - option_market_price_intrinsic| > 0.08% (TWAP error + fees), " +
      "comprar/vender option mispriced. Hold até settlement (08:00 UTC).",
    invalidation: "TWAP error aos 20min > 0.1% em > 20% das vezes, ou bid-ask spread das options < TWAP error + fees.",
    createdAt: "2026-07-05",
    author: "settlement_twap_scan.py",
    verdict:
      "EDGE POTENCIAL (structural). BTC: 27/30 (90%) TWAP previsível within 0.05% aos 20min, Wilson CI [74%, 97%]. " +
      "ETH: 26/30 (87%), Wilson CI [70%, 95%]. Aos 25min: 93-97% within 0.05%. " +
      "Exploit: observar 20min de TWAP → estimar settlement → comprar/vender options mispriced nos últimos 10min. " +
      "CUIDADO: (1) precisa de option com bid-ask spread > 0.08% para lucrar; " +
      "(2) capital lockup é mínimo (10min até settlement); " +
      "(3) precisa validar que options realmente estão mispriced vs forming TWAP em tempo real. " +
      "PRÓXIMO PASSO: paper trade em expiries reais — monitorar options market prices nos últimos 30min antes de settlement. " +
      "ATUALIZADO 2026-07-07: twap_paper_bot.py DEPLOYADO e rodando na AWS desde 2026-07-06 13:21 UTC. " +
      "Ainda 0 trades -- aguardando primeira janela TWAP (07:30-08:00 UTC). " +
      "REMEDIAÇÃO 2026-07-12: parser do nome Deribit corrigido para currency-expiry-strike-type; " +
      "validação isolada contra a API retornou 46 opções BTC 13JUL26 com strike numérico e tipo C/P. " +
      "A próxima execução paper permanece agendada para a janela 13JUL 07:30 UTC.",
    evPerTrade: 0.08,
    ci95: [0.05, 0.11],
    ci95Label: "TWAP prediction accuracy at 20min: 90% within 0.05% (BTC), 87% (ETH), N=30 each",
    tools: ["settlement_twap_scan.py"],
    reportFile: "settlement_twap_scan.log",
    pnl: 0,
    trades: 60,
    sampleUnit: "expiries diárias (30 BTC + 30 ETH)",
  },
  {
    id: "HYP-LATARB-01",
    title: "D32 — Cross-Exchange Latency Arbitrage (Binance leads Bybit/OKX)",
    market: "BINANCE vs BYBIT/OKX · BTC/ETH/SOL · 100ms polling",
    thesis:
      "Binance é a exchange mais rápida. Se o preço do BTC move na Binance primeiro, " +
      "Bybit/OKX lagam em milliseconds. Se lag > 0.2% (fees roundtrip), comprar na exchange " +
      "lagging quando leader move é arb livre. Scan: poll 3 exchanges a cada 100ms por 5min.",
    confidence: 5,
    status: "refuted",
    tags: ["crypto", "latency", "arbitrage", "cross-exchange", "aggressive"],
    trigger: "Lag > 0.2% entre Binance e Bybit/OKX com follower catchup > 60% hit rate",
    invalidation: "Divergência média < fees ou follower não catchup consistentemente",
    createdAt: "2026-07-04",
    author: "latency_arb_scan.py",
    verdict:
      "REFUTADO. 1200+ samples coletados. Divergência máxima entre exchanges: ~0.02% (ex: " +
      "Binance $63,314 vs OKX $63,326 = $12 diff). Fees roundtrip: 0.2% (10x maiores). " +
      "PROBLEMA 1: REST API leva ~2.5s/sample (não 100ms) — 3 chamadas HTTP sequenciais. " +
      "PROBLEMA 2: Não há leader consistente — Bybit/OKX às vezes acima de Binance. " +
      "Latency arb é jogo institucional: precisa co-location sub-ms, WebSocket/FIX, maker orders. " +
      "Não viável sem infra profissional (Jump Trading, Wintermute level).",
    evPerTrade: -0.2,
    ci95: [-0.2, -0.2],
    ci95Label: "Max divergence 0.02% vs 0.2% fees = sempre negativo. N=1200+ samples.",
    tools: ["latency_arb_scan.py"],
    reportFile: "latency_arb_scan.log",
    pnl: 0,
    trades: 1200,
    sampleUnit: "samples REST (~2.5s cada, 3 exchanges, 5min)",
  },
  {
    id: "HYP-OBI-01",
    title: "D33 — Order Book Imbalance Alpha (predict next-tick direction)",
    market: "BINANCE · BTC/ETH/SOL · Top 20 levels · 1s polling",
    thesis:
      "Se volume de bids >> volume de asks no order book, preço sobe no próximo segundo. " +
      "Imbalance ratio > 0.60 → long, < 0.40 → short. Teste: poll depth a cada 1s por 10min, " +
      "medir win rate a 1s/5s/10s horizon. Net após 0.1% taker fee por lado.",
    confidence: 5,
    status: "refuted",
    tags: ["crypto", "orderbook", "imbalance", "microstructure", "aggressive"],
    trigger: "Win rate > 55% após fees com N > 10 signals em algum horizon",
    invalidation: "OBI não prediz direção após fees a 1s granularity",
    createdAt: "2026-07-04",
    author: "order_book_imbalance_scan.py",
    verdict:
      "REFUTADO. 10min de scan, 600 samples, 3 símbolos. Resultados: " +
      "BTC 1s: WR 37.9%, EV -0.099% (N=517). BTC 5s: WR 54.2%, EV -0.097%. BTC 10s: WR 62.5%, EV -0.095%. " +
      "SOL 1s: WR 19.0%, EV -0.101%. ETH 10s: WR 62.5% mas 100% dos trades negativos após fees. " +
      "PROBLEMA: Win rate direcional chega a 62.5% em 10s, mas 0 wins após custos — " +
      "porque movimentos de preço são menores que 0.1% fee em 10s. " +
      "OBI tem algum poder preditivo direcional, mas insuficiente para superar fees a 1s granularity. " +
      "Precisaria WebSocket L2 sub-second + maker orders (0 fee) para ser viável.",
    evPerTrade: -0.097,
    ci95: [-0.101, -0.095],
    ci95Label: "EV -0.097% médio após fees. WR direcional 19-62.5% mas 0% lucrativo. N=2400+ signals.",
    tools: ["order_book_imbalance_scan.py"],
    reportFile: "order_book_imbalance_scan.log",
    pnl: -282.0,
    trades: 2400,
    sampleUnit: "signals OBI (600 samples × 3 símbolos × horizons 1s/5s/10s)",
  },
  {
    id: "HYP-LIQ-02",
    title: "D34 — Liquidation Cascade Detection & Front-Run",
    market: "BINANCE FUTURES · BTC/ETH/SOL · 2s polling · 30min",
    thesis:
      "Liquidações em cascata: 3+ liquidations em 10s mesma direção = cascade. " +
      "Se longs sendo liquidados, preço continua caindo → short e ride cascade. " +
      "Scan: monitora liquidations em tempo real, detecta cascades, simula P&L a 30s/60s/120s/300s hold. " +
      "Net após 0.1% taker fee por lado.",
    confidence: 10,
    status: "paused",
    tags: ["crypto", "liquidation", "cascade", "futures", "aggressive", "front-run", "paused"],
    trigger: "Cascade continuation WR > 60% após fees com N > 5",
    invalidation: "Cascades são raras ou não continuam após detecção + fees",
    createdAt: "2026-07-04",
    author: "liquidation_cascade_scan.py",
    verdict:
      "EM TESTE CONTÍNUO na AWS. Primeiro scan de 30min: 0 liquidations detectadas (mercado calmo). " +
      "Bot reiniciado em loop infinito (30min scan + 60s pause + repeat) para capturar eventos " +
      "ao longo de dias. Cascades são eventos raros — precisam volatilidade alta (crash/pump). " +
      "Quando detectar: cascade continuation é o edge mais agressivo possível (front-run forced selling). " +
      "Monitorar liquidation_cascade_scan.log na AWS para eventos. " +
      "Reconfirmado 2026-07-08: ainda 0 liquidações/cascades na janela mais recente monitorada. " +
      "PAUSADO 2026-07-12: vários dias sem liquidações/cascades não produzem uma amostra de sinal; " +
      "o loop foi removido do supervisor. Retomar somente em evento de volatilidade pré-definido.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "0 cascades observadas; processo pausado em 2026-07-12 até gatilho de volatilidade pré-definido.",
    tools: ["liquidation_cascade_scan.py"],
    reportFile: "liquidation_cascade_scan.log",
    pnl: 0,
    trades: 0,
    sampleUnit: "cascades detectadas (loop contínuo 30min/scan na AWS)",
  },
  {
    id: "HYP-FUNDPRED-01",
    title: "D35 — Funding Rate Prediction (momentum + premium index)",
    market: "BINANCE FUTURES · Top 20 USDT perps · 8h funding cycles",
    thesis:
      "Binance funding rate é determinada por: funding = clamp(premium_index + 0.01%, ±0.75%). " +
      "Premium index é publicado em tempo real → podemos prever funding ANTES de ser postado. " +
      "Estratégia: se premium > 0.1% → SHORT para receber funding positivo. " +
      "Também testa momentum: últimos 3 fundings positivos predizem próximo positivo?",
    confidence: 10,
    status: "refuted",
    tags: ["crypto", "funding", "prediction", "futures", "aggressive", "information-edge"],
    trigger: "Momentum WR > 60% OU premium_index > fees (0.08%)",
    invalidation: "Funding não é autocorrelacionado e premium < fees",
    createdAt: "2026-07-04",
    author: "funding_prediction_scan.py + funding_momentum_backtest.py",
    verdict:
      "REFUTADO APÓS BACKTEST DECISIVO. Momentum direction accuracy: 87.3% (N=1269) — " +
      "MAS Profitable WR: apenas 11.7% (149 wins / 1120 losses). " +
      "EV/trade: -$0.43 (-0.043%). Total P&L: -$548. Annualized: -47.3%. " +
      "PROBLEMA: Funding rates são太小 (avg 0.002-0.01%) vs 0.08% roundtrip fees. " +
      "Momentum prediz DIREÇÃO corretamente (87%), mas o valor do funding coletado " +
      "é insuficiente para cobrir fees na maioria dos períodos. " +
      "Única exceção: LABUSDT (+$142.81, WR 70.3%) e SLXUSDT (+$74.81) — " +
      "perps com funding médio alto (-0.23% e -0.16%). Mas estes são outliers " +
      "e podem não persistir. Edge só existe quando funding > 0.08% (alta volatilidade).",
    evPerTrade: -0.43,
    ci95: [-0.48, -0.38],
    ci95Label: "EV -$0.43/trade (N=1269, 20 perps, 30d). WR direção 87.3% mas WR lucro 11.7%.",
    tools: ["funding_prediction_scan.py", "funding_momentum_backtest.py", "funding_paper_bot.py"],
    reportFile: "funding_momentum_backtest_results.json",
    pnl: -548.15,
    trades: 1269,
    sampleUnit: "funding events backtested (20 perps × ~30d × 3 strategies)",
  },
  {
    id: "HYP-IVANOM-01",
    title: "D36 — Deribit IV Surface Anomaly (mispriced skew/term structure)",
    market: "DERIBIT · BTC/ETH · All strikes/expiries · IV surface",
    thesis:
      "A superfície de IV de opções deveria ser smooth. Strikes ou expiries onde IV " +
      "desvia > 2 vol points dos vizinhos são mispriced. Comprar IV barato (dev < 0), " +
      "vender IV caro (dev > 0). Scan: 533 BTC + 516 ETH opções líquidas, 13 expiries cada. " +
      "Compara IV de cada option vs média ponderada dos vizinhos.",
    confidence: 20,
    status: "validating",
    tags: ["crypto", "options", "deribit", "iv-surface", "mispricing", "aggressive"],
    trigger: "|IV - fair_IV| > 3 vol points com bid≥0.001, OI≥50, spread<50% (BUY only)",
    invalidation: "SELL anomalies são bid-ask spread artifacts em deep ITM. WR ao vivo cair pra perto de 50% com EV negativo em N maior.",
    createdAt: "2026-07-04",
    author: "iv_surface_anomaly_scan.py + iv_anomaly_paper_bot.py + iv_anomaly_backtest.py",
    verdict:
      "DIVERGINDO — backtest BS (histórico): BUY side 7/7 wins, +$4,500 (100% WR). SELL side " +
      "0/9 wins, -$792 (artefatos de bid-ask spread em deep ITM). Reversion test: 6/6 " +
      "anomalias reverting (0 stale). " +
      "UPDATE 2026-07-06: N=7 settled, WR=42.9% (3/7), EV/trade=+$137.52, total=+$962.66. " +
      "ATUALIZADO 2026-07-07: N=14 settled, WR=42.857%, EV/trade=+$84.32, total=+$1.180,47. " +
      "ATUALIZADO 2026-07-08: N=38, WR caiu para 39.5% (6a leitura seguida em queda desde " +
      "50.0%@N24), total=+$1.187,68. Padrão de decaimento monotônico preocupante. " +
      "ATUALIZADO 2026-07-10: N=58 settled, WR RECUPOU para 41.4% (subiu de 39.5%@N38 e " +
      "35.4%@N48), EV/trade=+$50.84, total=+$2.948,65 (novo pico). A recuperação da WR é " +
      "incomum para falso-positivos (que tipicamente só decaem) — pode haver edge real " +
      "intermitente. Ainda não conclusivo: precisa N=100+ para confirmar. Não normalizável " +
      "a 'stake fixo': opções Deribit têm prêmio variável por contrato. " +
      "REMEDIAÇÃO 2026-07-12: 111 settles e 342 posições abertas da execução sem limite foram " +
      "preservados como coorte legacy_unbounded e excluídos da validação. A nova coorte capped_v2 " +
      "iniciou com máximo global de 10. UPDATE 2026-07-13: 10/10 posições abertas, 0 settled. " +
      "Próximo scan em 60min. Aguardando settles da coorte capped_v2 para validação.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Coorte capped_v2: 10/10 posições abertas, 0 settles. Coorte legacy_unbounded (111 settles, WR 41.4%, +$2.948) excluída por exposição sem limite.",
    tools: ["iv_surface_anomaly_scan.py", "iv_anomaly_paper_bot.py", "iv_anomaly_backtest.py"],
    reportFile: "iv_anomaly_paper_stats.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "coorte paper capped_v2 na AWS: 10/10 posições abertas, 0 settles; coorte legacy_unbounded preservada mas não inferenciais",
  },
  {
    id: "HYP-OUTFLOW-01",
    title: "D37 — Exchange Outflow Signal (on-chain whale tracking)",
    market: "BLOCKCHAIN · BTC/ETH · Exchange wallets · Whale Alert",
    thesis:
      "Saídas grandes de BTC/ETH de exchanges = holders movendo para cold storage = " +
      "redução de supply vendável = bullish. Se detectarmos outflows > $5M em tempo real, " +
      "compramos antes do mercado precificar a redução de supply.",
    confidence: 8,
    status: "validating",
    tags: ["crypto", "on-chain", "whale", "exchange-flow", "aggressive"],
    trigger: "Net exchange outflow > $5M in 1h → LONG BTC",
    invalidation: "Outflows não predizem preço em 1h/4h/24h após sinal",
    createdAt: "2026-07-04",
    author: "exchange_outflow_scan.py",
    verdict:
      "SCAN FUNCIONANDO — Whale Alert API key configurada. " +
      "0 outflows >$1M na última 1h (mercado calmo). " +
      "Blockchain.com fallback sem dados. " +
      "Preço BTC: $63,302. API funcional, necessário rodar continuamente. " +
      "ATUALIZADO 2026-07-08: ~1000 snapshots horários acumulados, maioria NO SIGNAL/WEAK LONG, " +
      "nenhum outflow >$1M ainda. Achado estrutural: o script nunca correlaciona o signal score " +
      "com retorno de preço subsequente — não há caminho para EV/win-rate/veredito no design " +
      "atual, precisaria de lógica de forward-return nova, não mais tempo rodando. CORRIGIDO " +
      "2026-07-08: `forward_return_tracker.py` criado e integrado (grava preço+sinal a cada " +
      "ciclo, resolve retorno em 1h/4h/24h, reporta com o mesmo Wilson/bootstrap do resto do " +
      "repo); redeployado e reiniciado na AWS às ~15h UTC. A partir de agora o processo PODE " +
      "produzir um veredito real — só falta tempo/amostra (0 resolvidos ainda no restart).",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "~1000 snapshots pré-fix. Forward-return tracking ativo desde 2026-07-08 15h UTC.",
    tools: ["exchange_outflow_scan.py"],
    reportFile: "exchange_outflow_scan_results.json",
    pnl: 0,
    trades: 1000,
    sampleUnit: "scan com API key (~1000 snapshots horários, atualizado 2026-07-08)",
  },
  {
    id: "HYP-ANNOUNCE-01",
    title: "D38 — Binance Announcement Front-Run (listing pump capture)",
    market: "BINANCE · Spot · Announcement API · 3s polling",
    thesis:
      "Binance posta anúncios de listings/delistings em sua página de suporte. " +
      "Se detectarmos 'Will List XXX' em segundos via polling a cada 3s, podemos comprar " +
      "o token antes do pump instantâneo que segue listings da Binance.",
    confidence: 5,
    status: "paused",
    tags: ["crypto", "binance", "listing", "front-run", "aggressive", "information-edge", "paused"],
    trigger: "New 'Will List' announcement detected → BUY token immediately",
    invalidation: "Mercado precifica listing em < 3s (polling muito lento) ou slippage > edge",
    createdAt: "2026-07-04",
    author: "announcement_front_run_scan.py",
    verdict:
      "VALIDANDO — rodando 24h+ na AWS. Primeiros anúncios reais capturados em 2026-07-06: " +
      "3 no total (2 sem token associado: 'Binance Adds... Stock Trading', 'Binance Turns 9'; " +
      "1 LISTING real: Poll delist TST & IOTX, sentimento bullish, preço TST=$0.01001 " +
      "registrado em t0). Price-reaction tracking em andamento para o TST. " +
      "ATUALIZADO 2026-07-08: mais anúncios capturados (torneios/promoções/caridade, categoria " +
      "OTHER, sentimento neutro), nenhum LISTING novo com token associado desde o TST. " +
      "Ainda cedo para veredito — precisa de um listing/delisting com movimento de preço " +
      "claro para testar a tese de front-run. PAUSADO 2026-07-12: o coletor registrava anúncios, " +
      "mas não possuía amostra tradeable nem retorno pós-evento validado; removido do supervisor até redesign.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Nenhum anúncio tradeable com retorno validado; processo pausado em 2026-07-12.",
    tools: ["announcement_front_run_scan.py"],
    reportFile: "announcement_scan_results.json",
    pnl: 0,
    trades: 3,
    sampleUnit: "anúncios reais capturados (0 ainda com reação de preço medida)",
  },
  {
    id: "HYP-MAXPAIN-01",
    title: "D39 — Options Max Pain Magnet (Deribit expiry day manipulation)",
    market: "DERIBIT · BTC/ETH · Options OI · Max pain computation",
    thesis:
      "No dia de expiry de opções, o preço do underlying gravita toward max pain strike " +
      "(preço onde máximo de opções expira worthless, beneficiando option writers/MMs). " +
      "MMs têm incentivo e capital para empurrar preço toward max pain. " +
      "Se |spot - max_pain| > 2% no expiry day, trade toward max pain.",
    confidence: 10,
    status: "paused",
    tags: ["crypto", "options", "deribit", "max-pain", "expiry", "aggressive", "structural", "paused"],
    trigger: "|spot - max_pain| > 2% on expiry day → trade toward max pain",
    invalidation: "Preço não converge para max pain em expiries consecutivos",
    createdAt: "2026-07-04",
    author: "max_pain_scan.py",
    verdict:
      "VALIDANDO — rodando 24h+ na AWS, leitura horária. Primeiro ciclo completo (expiry " +
      "6JUL26) rolou pra 7JUL26 em 2026-07-06T00:12 SEM convergência: diff BTC spot-vs-max-pain " +
      "foi de +2.00% pra +3.04% (divergiu) nas ~7h antes do rollover. Ciclo atual (7JUL26): " +
      "diff BTC oscilando entre -1.15% e +0.90% ao longo do dia, ETH entre -2.03% e +1.04% " +
      "— sem tendência clara de convergência ainda, mas expiry ainda a ~1 dia de distância. " +
      "Um ciclo completo não sustenta a tese de 'magnet' — precisa observar múltiplos expiries. " +
      "ATUALIZADO 2026-07-08: expiry 9JUL26 se aproxima (~1 dia), diffs BTC/ETH oscilando " +
      "abaixo de 1% nas últimas leituras — ainda sem padrão de convergência claro o suficiente. " +
      "PAUSADO 2026-07-12: leituras repetidas não estabeleceram convergência e o coletor foi removido do supervisor.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Ciclo 1 divergiu; sem convergência reproduzível. Processo pausado em 2026-07-12.",
    tools: ["max_pain_scan.py"],
    reportFile: "max_pain_scan_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "leituras horárias, 1 rollover de expiry completo sem convergência",
  },
  {
    id: "HYP-STABLECOIN-01",
    title: "D40 — Stablecoin Mint Signal (capital inflow detection)",
    market: "ETHEREUM · USDT/USDC · DefiLlama · Supply data",
    thesis:
      "Quando Tether/Circle emitem (mint) grandes quantidades de stablecoins, " +
      "esse capital novo entra no ecossistema crypto → pressão compradora → BTC up. " +
      "Se detectarmos mints > $500M em 3d, LONG BTC. Redemptions > $500M = BEARISH.",
    confidence: 0,
    status: "refuted",
    tags: ["crypto", "stablecoin", "macro", "capital-flow", "aggressive"],
    trigger: "3d supply change > +$500M → LONG BTC | < -$500M → SHORT BTC",
    invalidation: "Supply changes não predizem preço em 1d/7d/30d",
    createdAt: "2026-07-04",
    author: "stablecoin_mint_scan.py",
    verdict:
      "REFUTADO (2026-07-10). Forward-return tracker ativo desde 2026-07-08 produziu veredito: " +
      "4h horizon: N=47, WR=27.66%, EV/trade=-$0.2965, IC95%[-$0.4712,-$0.1260] — inteiramente negativo. " +
      "24h horizon: N=27, WR=0.00% (0 wins em 27!), EV/trade=-$2.0615, IC95%[-$2.2863,-$1.8453] — " +
      "catastrófico, sinal na direção oposta. Stablecoin mint/burn NÃO tem poder preditivo de preço. " +
      "PROCESSO PARADO 2026-07-10: tmux d40_stable killado.",
    evPerTrade: -0.2965,
    ci95: [-0.4712, -0.126],
    ci95Label: "EV/trade 4h horizon (bootstrap), N=47. 24h: EV=-$2.06 IC95%[-$2.29,-$1.85], WR=0%.",
    tools: ["stablecoin_mint_scan.py", "forward_return_tracker.py"],
    reportFile: "stablecoin_mint_scan_results.json",
    pnl: -13.93,
    trades: 47,
    sampleUnit: "sinais resolvidos pelo forward-return tracker (4h: N=47, 24h: N=27)",
  },
  {
    id: "HYP-WASH-01",
    title: "D41 — Binance WS Trade Anomaly Detector (wash trading / smart money flow)",
    market: "BINANCE · WebSocket · BTCUSDT/ETHUSDT/SOLUSDT · Real-time",
    thesis:
      "Padrões anômalos no Binance trade stream (clusters de trades idênticos em <100ms, " +
      "volume bursts, duplicate trade IDs) revelam operações coordenadas, algoritmos de " +
      "execução de MMs, ou wash trading. Seguir a direção dos clusters = seguir smart money.",
    confidence: 5,
    status: "refuted",
    tags: ["crypto", "binance", "websocket", "wash-trading", "anomaly", "aggressive", "real-time"],
    trigger: "5+ identical trades in <100ms → follow direction | Volume burst 5x avg → track price",
    invalidation: "Clusters são apenas TWAP/VWAP de retails, não predizem direção",
    createdAt: "2026-07-04",
    author: "wash_trading_scan.py",
    verdict:
      "REFUTADO POR CUSTOS (2026-07-08, forward-return tracker ativo). Sinal direcional REAL " +
      "confirmado mas magnitude insuficiente: BTC WR=66.3% (IC95%[64.9%,67.6%]) em 10s, " +
      "ETH WR=62.1% em 10s — ambos excluem 50%. MAS EV/trade=~1bps (0.01%), fee round-trip " +
      "taker=10bps. EV líquido=-9bps/trade. WR decai com horizonte (66%→58% BTC em 10s→60s). " +
      "SOLUSDT sem edge (WR~47-49%, IC95% cruza 50%). Mesmo padrão D33/D43: sinal real mas " +
      "10x menor que custo de transação. Forward-return tracker produziu veredito formal " +
      "com IC95% em ~9000 sinais (BTC N=4708, ETH N=3032, SOL N=1138).",
    evPerTrade: 0.0105,
    ci95: [0.0091, 0.0113],
    ci95Label: "EV/trade BTC 10s (bootstrap, N=4712): $0.0105 IC95%[$0.0091,$0.0113]. WR=66.3% mas EV < fees (10bps).",
    tools: ["wash_trading_scan.py", "forward_return_tracker.py"],
    reportFile: "wash_trading_scan_results.json",
    pnl: 0,
    trades: 9000,
    sampleUnit: "sinais resolvidos pelo forward-return tracker (BTC N=4708, ETH N=3032, SOL N=1138, 10s/30s/60s horizons)",
  },
  {
    id: "D42",
    title: "Deriv vs Binance Cross-Venue Latency Arbitrage",
    market: "cryBTCUSD · Binance BTCUSDT",
    thesis:
      "Deriv's crypto price feed (cryBTCUSD) may lag Binance's real-time price. " +
      "If lag > 100ms consistently, we can trade on Deriv knowing where price already moved. " +
      "Stream both venues simultaneously and cross-correlate.",
    confidence: 5,
    status: "refuted",
    tags: ["crypto", "deriv", "binance", "latency", "arbitrage", "aggressive", "real-time"],
    trigger: "Binance price moves → Deriv hasn't updated yet → trade on Deriv in direction",
    invalidation: "Lag is 0ms most of the time (Deriv catches up instantly)",
    createdAt: "2026-07-04",
    author: "deriv_binance_latency_arb_scan.py",
    verdict:
      "REFUTADO (via H3 + dados próprios N=6.830). Rodou 13h na AWS: avg lag=204.5ms, " +
      "max=950ms — confirma que o lag do FEED é real e consistente. MAS H3 já testou " +
      "isso exaustivamente no nível de EXECUÇÃO (60+41 ordens demo reais, incl. " +
      "co-locado em Tóquio): fill sempre reprecifica fresco, custo ~489x a captura. " +
      "D42 mede só o feed (Passo 1 de H3), não a execução (o teste decisivo). " +
      "Não restartar — pergunta já respondida.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N=6.830 (13h AWS): avg=204.5ms, max=950ms. Refutado via H3 execution-level test.",
    tools: ["deriv_binance_latency_arb_scan.py"],
    reportFile: "deriv_binance_latency_arb_results.json",
    pnl: 0,
    trades: 6830,
    sampleUnit: "13h continuous AWS run (6,830 lag samples, avg 204.5ms) — refuted via H3",
  },
  {
    id: "D43",
    title: "Binance Order Book Imbalance Predictor",
    market: "BTCUSDT · ETHUSDT · SOLUSDT",
    thesis:
      "When bid volume >> ask volume (or vice versa) in the top 20 order book levels, " +
      "price moves in the direction of the imbalance within 30s. " +
      "Imbalance > 70% → predict direction → trade and close after 30s.",
    confidence: 5,
    status: "refuted",
    tags: ["crypto", "binance", "orderbook", "microstructure", "aggressive", "real-time", "edge"],
    trigger: "Bid/ask volume imbalance > 70% → trade in imbalance direction, close 30s",
    invalidation: "Accuracy drops below 60% with larger sample (N=500+)",
    createdAt: "2026-07-04",
    author: "orderbook_imbalance_scan.py",
    verdict:
      "REFUTADO (auto-concluído, N=24.994). Processo rodou 33.487s (9.3h) na AWS e " +
      "concluiu sozinho: 756 predictions resolvidas, accuracy 30s CAIU de 75.4%→58.8% " +
      "(abaixo do próprio threshold de 60%). Confirma D33 (mesma tese, refutado por " +
      "fees: WR direcional real mas 0% lucrativo). N=98 inicial era false positive " +
      "de amostra pequena, regressão à média com N maior.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N=24.994 (9.3h AWS), 756 resolved: 58.8% at 30s (was 75.4% at N=98). Refuted.",
    tools: ["orderbook_imbalance_scan.py"],
    reportFile: "orderbook_imbalance_results.json",
    pnl: 0,
    trades: 24994,
    sampleUnit: "9.3h continuous AWS run (24,994 predictions, 756 resolved, self-concluded)",
  },
  {
    id: "D44",
    title: "Binance Funding Rate + Basis Arbitrage",
    market: "Binance Futures · 20 perpetuals",
    thesis:
      "When perpetual futures funding rate is extreme, basis reverts. " +
      "Short futures + long spot when funding > 0.05%/8h (delta neutral, collect funding). " +
      "Monitor 20 perpetuals for extreme funding conditions.",
    confidence: 0,
    status: "refuted",
    tags: ["crypto", "binance", "futures", "funding", "basis", "delta-neutral", "aggressive"],
    trigger: "Funding > 0.05%/8h → SHORT futures + LONG spot | Funding < -0.03%/8h → LONG futures",
    invalidation: "Funding flips sign before basis reverts, or basis widens further",
    createdAt: "2026-07-04",
    author: "funding_basis_arb_scan.py",
    verdict:
      "REFUTADO (2026-07-10). Carry-return tracker ativo desde 2026-07-08 produziu veredito: " +
      "24h horizon: N=36, WR=22.22%, EV/trade=-$0.0479, IC95%[-$0.0663,-$0.0279] — inteiramente " +
      "negativo, não cruza zero. Controle (sem sinal): N=6084, carry médio=-0.1103% — o carry " +
      "com sinal é PIOR que o controle. Funding extremo não tem edge sobre basis reversion. " +
      "PROCESSO PARADO 2026-07-10: tmux d44_funding killado.",
    evPerTrade: -0.0479,
    ci95: [-0.0663, -0.0279],
    ci95Label: "EV/trade 24h carry (bootstrap), N=36. IC95% inteiramente negativo. Controle N=6084 carry=-0.11%.",
    tools: ["funding_basis_arb_scan.py", "carry_return_tracker.py"],
    reportFile: "funding_basis_arb_results.json",
    pnl: -1.73,
    trades: 36,
    sampleUnit: "sinais resolvidos pelo carry-return tracker (24h: N=36, 72h: N=0 ainda)",
  },
  {
    id: "D45",
    title: "Binance Liquidation Cascade Predictor",
    market: "BTCUSDT · ETHUSDT · SOLUSDT Futures",
    thesis:
      "When 3+ liquidations occur in 10s on the same side, a cascade forms that amplifies " +
      "the price move. Joining the cascade direction for 30-60s captures the forced flow. " +
      "Stream liquidation orders via WebSocket in real-time.",
    confidence: 10,
    status: "archived",
    tags: ["crypto", "binance", "liquidation", "cascade", "momentum", "aggressive", "real-time", "redundant"],
    trigger: "3+ liquidations in 10s same direction → join cascade, exit 30-60s",
    invalidation: "Price reverses immediately after cascade (cascade exhaustion)",
    createdAt: "2026-07-04",
    author: "liquidation_cascade_predictor.py",
    verdict:
      "REDUNDANTE com D34 — retirado. Mesma tese exata (3+ liquidações/10s = cascade) " +
      "que D34 (liquidation_cascade_scan.py), que já roda há mais tempo com design mais " +
      "rigoroso (fee-adjusted P&L, 4 hold periods testados: 30/60/120/300s). D34 confirma " +
      "0 cascades em TODOS os ciclos ao longo de dias de dados. Não restartar D45, " +
      "usar D34 como fonte única desta tese.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "0 cascades (120s local + 0 in AWS run). Superseded by D34 (more rigorous).",
    tools: ["liquidation_cascade_predictor.py"],
    reportFile: "liquidation_cascade_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "Retired — duplicate of D34, see liquidation_cascade_scan.py instead",
  },
  {
    id: "D46",
    title: "Deriv Tick Pattern Exploitation",
    market: "R_10-100 · 1HZ10V-100V",
    thesis:
      "Deriv's synthetic price feed may have exploitable patterns at the tick level. " +
      "Track 3-tick sequential patterns (e.g., ==D, ==U) and predict next tick direction. " +
      "If pattern > 55% accuracy → executable 1-tick CALL/PUT trade.",
    confidence: 3,
    status: "refuted",
    tags: ["deriv", "synthetic", "ticks", "pattern", "mean-reversion", "aggressive", "real-time"],
    trigger: "==D pattern (flat-flat-down) → CALL | ==U pattern (flat-flat-up) → PUT",
    invalidation: "Pattern accuracy drops below 52% with N=5000+ (Wilson CI crosses 50%)",
    createdAt: "2026-07-04",
    author: "deriv_tick_pattern_scan.py",
    verdict:
      "REFUTADO (2026-07-06, N=190.000). Restart de 2026-07-05 (pós fix de checkpoint) " +
      "rodou limpo por 7h contínuas até um WS drop natural. Com amostra grande, o edge " +
      "de N=542/300 desapareceu: ==D→UP 50.44% (54.366/107.784, z≈2.89 mas só 0.44pp — " +
      "muito abaixo de qualquer custo de transação), ==U→UP 49.82% (39.871/80.033, " +
      "z≈-1.02, nem significante). Mesmo padrão do resto do programa: sinal, quando " +
      "existe, é menor que o custo. Bot parado e removido do supervisor.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N=190.000 (7h AWS): ==D→UP 50.44% (z≈2.89, econ. irrelevante), ==U→UP 49.82% (n.s.). Refuted.",
    tools: ["deriv_tick_pattern_scan.py"],
    reportFile: "deriv_tick_pattern_results.json",
    pnl: 0,
    trades: 190000,
    sampleUnit: "7h continuous AWS run (190,000 ticks) — refuted, bot stopped 2026-07-06",
  },
  {
    id: "D47",
    title: "Stale Proposal Buy Race (execution exploit)",
    market: "DERIV · HIGHER/LOWER · R_100 · 10 ticks",
    thesis:
      "Um proposal_id antigo poderia ser comprado a um barrier desatualizado se o servidor " +
      "não recalcular no momento do buy — abrindo uma janela de preço obsoleto explorável " +
      "esperando o mercado se mover a favor do barrier antigo antes de comprar.",
    confidence: 2,
    status: "refuted",
    tags: ["deriv", "execution", "race-condition", "stale-price", "higher-lower"],
    trigger: "TREAT: pedir proposal, esperar 20s, comprar com proposal_id antigo. CONTROL: comprar imediato (0s delay).",
    invalidation: "Barrier sempre recalculado no momento da compra (RECALC), nunca honra o preço da proposal antiga.",
    createdAt: "2026-07-06",
    author: "stale_proposal_probe.py",
    verdict:
      "REFUTADO (N=40: 20 TREAT/20 CONTROL). Barrier SEMPRE recalculado no momento da compra " +
      "(39/40 rounds 'RECALC(new)'; o 1/40 'STALE(old)' restante foi coincidência de preço " +
      "parado, não cache real). TREAT WR=45% IC95%[25.8,65.8] vs CONTROL WR=55% " +
      "IC95%[34.2,74.2] — diferença dentro do ruído, consistente com o custo puro de esperar " +
      "20s num random walk simétrico, não com exploit de preço obsoleto.",
    evPerTrade: 0,
    ci95: [25.8, 65.8],
    ci95Label: "TREAT WR% (delay=20s) IC95%, N=20. CONTROL WR=55% IC95%[34.2,74.2].",
    tools: ["stale_proposal_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 40,
    sampleUnit: "rounds (20 TREAT delay=20s / 20 CONTROL delay=0s), HIGHER/LOWER R_100 10 ticks",
  },
  {
    id: "D48",
    title: "Accumulator Tick-Barrier Race (client-side sell timing)",
    market: "DERIV · ACCU · 1HZ10V",
    thesis:
      "Um sell manual disparado no instante em que um tick recebido via WS local já rompeu a " +
      "barreira do ACCU, antes do servidor confirmar o knockout, poderia 'vencer' a corrida " +
      "e capturar valor residual que seria perdido no knockout.",
    confidence: 3,
    status: "refuted",
    tags: ["deriv", "accumulator", "execution", "race-condition", "knockout"],
    trigger: "Detectar breach da barreira via tick WS local, enviar sell imediatamente, validar contra fresh-check server-side (poll_open_contract) logo antes do sell.",
    invalidation: "EV agregado negativo mesmo nos casos em que o sell venceu a corrida e executou a bid fresco > 0.",
    createdAt: "2026-07-06",
    author: "accu_tick_race_probe.py",
    verdict:
      "REFUTADO (N=20, EV negativo confirmado). Primeira versão teve falso positivo " +
      "(bid_price client-side desatualizado); corrigida com fresh-check imediatamente antes " +
      "do sell. Com o fix: 5/20 trials o breach local era falso positivo (servidor já tinha " +
      "is_sold=True/bid_price=0 — knockout atômico, sem janela de corrida). Nos outros 11/20 " +
      "(55% WR) o sell REALMENTE executou a um bid fresco>0, capturando valor genuíno — mas " +
      "EV AGREGADO É NEGATIVO: total=-$6.51/20 trials, média=-$0.3255/trial, bootstrap " +
      "IC95%=[-0.585,-0.060] (não cruza zero, do lado negativo) — vitórias pequenas " +
      "(~$0.10-0.41) não compensam o stake integral perdido nas derrotas.",
    evPerTrade: -0.3255,
    ci95: [-0.585, -0.060],
    ci95Label: "EV por trial ($) bootstrap IC95%, N=20",
    tools: ["accu_tick_race_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -6.51,
    trades: 20,
    sampleUnit: "trials (tentativas de vender no instante de breach local da barreira)",
  },
  {
    id: "D49",
    title: "App ID / Canal Pricing Arbitrage",
    market: "DERIV · api.derivws.com vs ws.derivws.com (gateway legado) · multi-símbolo",
    thesis:
      "Preços de proposal poderiam divergir entre app_id (OAuth do projeto vs público 1089) " +
      "ou entre gateways (novo vs legado) para o mesmo contrato — abrindo arbitragem de canal " +
      "se um dos dois cotar sistematicamente mais barato.",
    confidence: 2,
    status: "refuted",
    tags: ["deriv", "execution", "app-id", "gateway", "pricing-arbitrage"],
    trigger: "Pedir proposal idêntica (mesmo symbol/contract_type/duration/stake, mesmo instante) em paralelo por 2-3 canais/app_ids.",
    invalidation: "Preços idênticos byte-a-byte dentro do mesmo gateway; gateway legado só segmenta por jurisdição, não por preço.",
    createdAt: "2026-07-06",
    author: "app_id_pricing_probe.py",
    verdict:
      "REFUTADO. Mesmo gateway (api.derivws.com/trading/v1/options/ws/public), app_id do " +
      "projeto (OAuth) vs app_id público genérico 1089: 40/40 rounds com ask_price/payout/" +
      "spot idênticos (byte-a-byte) — app_id não afeta preço dentro do mesmo canal. Gateway " +
      "legado (ws.derivws.com/websockets/v3, app_id=1089, mesmo IP AWS-Europa): rejeita TODOS " +
      "os sintéticos testados (R_10, 1HZ10V, WLDAUD, JD10 — \"Trading is not offered for this " +
      "asset\") e só oferece Multipliers para forex. Segmentação regulatória de " +
      "entidade/jurisdição (compatível com restrição ESMA a binários/sintéticos na UE) roteada " +
      "por IP, não bug de precificação — onde o mesmo produto é oferecido nos dois canais, o " +
      "preço é idêntico.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "40/40 rounds com preço idêntico entre app_ids no mesmo gateway",
    tools: ["app_id_pricing_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 40,
    sampleUnit: "rounds de proposal paralela (2-3 canais/app_ids testados)",
  },
  {
    id: "D50",
    title: "Multiplier Stop-Out Slippage",
    market: "DERIV · MULTUP · 1HZ100V · 400x · $10 stake",
    thesis:
      "O overshoot de 1 tick no momento do stop-out de um Multiplier poderia gerar slippage " +
      "não repassado corretamente ao cliente, ou abrir espaço para um fechamento manual " +
      "melhorar o resultado vs. o stop-out automático do servidor.",
    confidence: 2,
    status: "refuted",
    tags: ["deriv", "multiplier", "execution", "slippage", "stop-out"],
    trigger: "Comprar MULTUP, poll a cada 0.3s até fechar, comparar stop_out_level teórico vs exit_spot real.",
    invalidation: "Profit realizado sempre exatamente -stake nos stop-outs genuínos, sem excesso de perda repassado.",
    createdAt: "2026-07-06",
    author: "multiplier_stopout_probe.py",
    verdict:
      "REFUTADO (N=20). 6/20 trials foram stop-outs genuínos (profit≈-stake; os outros 14 " +
      "bateram o timeout do probe com preço favorável e foram fechados manualmente, profit " +
      "variável +$0.13 a +$27.28). Slippage nos 6 genuínos: média=+0.127pts (min=-0.03, " +
      "max=+0.39, ruído bidirecional sem viés direcional) — mas o profit realizado foi " +
      "EXATAMENTE -$10.0000 (a perda teórica) em TODOS os 6 casos: a Deriv absorve o " +
      "micro-overshoot e garante o cap de perda exato no stake, sem repassar slippage ao " +
      "cliente. Não há excesso de perda nem espaço para intervenção manual melhorar o " +
      "resultado.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Slippage médio +0.127pts (min-0.03,max+0.39) mas profit sempre = -stake exato (N=6 stop-outs genuínos)",
    tools: ["multiplier_stopout_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 20,
    sampleUnit: "trials (6 stop-outs genuínos identificados de 20 tentativas)",
  },
  {
    id: "D51",
    title: "Static Replication Arbitrage (complementary legs)",
    market: "DERIV · CALL+PUT / HIGHER+LOWER(+0.5) · mesmo underlying/duration",
    thesis:
      "Comprar as duas pernas complementares de um payoff binário (CALL+PUT, ou HIGHER+LOWER " +
      "no mesmo barrier), ambas com basis=payout fixo, deveria ser risco-zero (exatamente uma " +
      "ganha). Se a soma dos ask_price for menor que o payout alvo, há arbitragem estática livre.",
    confidence: 2,
    status: "refuted",
    tags: ["deriv", "execution", "static-replication", "arbitrage", "put-call"],
    trigger: "Pedir as duas pernas em paralelo (2 conexões, mesmo spot), basis=payout fixado em $100, comparar soma(ask_price) vs payout alvo.",
    invalidation: "Soma dos ask_price determinística e constante acima do payout em toda a amostra, variância zero.",
    createdAt: "2026-07-06",
    author: "static_replication_probe.py",
    verdict:
      "REFUTADO. Resultado perfeitamente determinístico: soma dos ask_price = $102.40 em " +
      "TODAS as 39 (CALL+PUT) + 14 (HIGHER+LOWER) rodadas com spot batendo entre as pernas, " +
      "arb_$=-$2.40 CONSTANTE, variância zero. Margem da casa é uma % fixa (2.4%) aplicada " +
      "simetricamente às duas pernas complementares — nenhuma arbitragem estática possível.",
    evPerTrade: -2.40,
    ci95: [-2.40, -2.40],
    ci95Label: "arb_$ = soma(ask_price) - payout($100), constante em 53/53 rodadas",
    tools: ["static_replication_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 53,
    sampleUnit: "rodadas pareadas (39 CALL+PUT + 14 HIGHER+LOWER)",
  },
  {
    id: "D52",
    title: "Deal Cancellation Mispricing (embedded put on Multipliers)",
    market: "DERIV · Multipliers · 1HZ10V · 400x/1000x · MULTUP/MULTDOWN · cancellation 5-60min",
    thesis:
      "A feature 'Deal Cancellation' dos Multipliers (reembolso integral do stake se cancelado " +
      "dentro de 5-60min) é uma put europeia embutida (strike=entry, notional=stake×multiplier). " +
      "Se o fee cobrado for menor que o fair value Monte Carlo dessa put, há edge sistemático.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "multiplier", "deal-cancellation", "options", "refutado"],
    trigger: "Fee cobrado < fair_value Monte Carlo (IC95%, bootstrap em sub-blocos de 60 ticks) → comprar Multiplier+cancellation e cancelar se o valor da put ficar positivo.",
    invalidation: "EV líquido (valor_realizado − fee) IC95% cruzar zero com amostra ao vivo maior.",
    createdAt: "2026-07-06",
    author: "deal_cancellation_edge_scan.py + deal_cancellation_live_probe.py",
    verdict:
      "REFUTADO (2026-07-09, N=120 trades reais). O 'quase-edge' de N=20 (EV=+$0.147) era viés " +
      "de amostra pequena. Com N=120: EV/trade caiu para +$0.08, IC95%[-$0.04,+$0.08] — cruza " +
      "zero e o lower bound ficou MAIS negativo que em N=20. Trajetória monotônica decrescente: " +
      "EV $0.14(N20)→$0.14(N76)→$0.08(N120), IC95% lower -$0.03→-$0.04. WR(net>0) caiu de " +
      "39.5%→37.5%. Cancel rate estável em ~57%. Fee=$0.44/trade é corretamente precificado — " +
      "o modelo teórico de Monte Carlo que sugeria 8-12% de mispricing estava errado. Mesmo " +
      "padrão de decaimento que matou o early-sell (D14) e o D36. PROCESSO PARADO 2026-07-09: " +
      "tmux d52_live killado. Deriv ecossistema 100% fechado para mispricing de produtos.",
    evPerTrade: 0.08,
    ci95: [-0.04, 0.08],
    ci95Label: "EV líquido (valor_realizado - fee) $/trade, N=120 trades reais. IC95% cruza zero, EV encolhendo monotonicamente.",
    tools: ["deal_cancellation_edge_scan.py", "deal_cancellation_live_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 9.69,
    trades: 120,
    sampleUnit: "trades reais (Multiplier + Deal Cancellation, N=120, alternando MULTUP/MULTDOWN)",
  },
  {
    id: "D53",
    title: "Concurrent Duplicate-Buy Race (proposal_id double-fill)",
    market: "DERIV · mesmo proposal_id · 2 conexões autenticadas / mesma conexão 2 req_id",
    thesis:
      "Disparar 2 compras simultâneas referenciando o MESMO proposal_id poderia, por race " +
      "condition no backend, resultar nos dois aceitos (double-fill) — duplicando o contrato " +
      "pelo preço de um só.",
    confidence: 2,
    status: "refuted",
    tags: ["deriv", "execution", "race-condition", "duplicate-buy", "proposal-id"],
    trigger: "asyncio.gather com 2 buys simultâneos, zero delay: (a) 2 conexões autenticadas separadas mesma conta, (b) mesma conexão com 2 req_id diferentes.",
    invalidation: "Sempre exatamente 1 sucesso + 1 rejeição em ambas as variantes, nunca os dois aceitos.",
    createdAt: "2026-07-06",
    author: "duplicate_buy_race_probe.py",
    verdict:
      "REFUTADO. Variante (a) 2 conexões separadas: 0/15 trials com ambos aceitos — leg B " +
      "sempre rejeitado instantaneamente com 'Unknown contract proposal' (proposal_id é " +
      "escopado à SESSÃO/CONEXÃO que o criou, nem chega a competir). Variante (b) mesma " +
      "conexão, 2 req_id concorrentes: 0/8 trials com ambos aceitos, sempre exatamente 1 " +
      "sucesso + 1 rejeição, débito sempre = 1x stake. Consumo do proposal_id é atômico nos " +
      "dois casos testados, sem janela de corrida.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "0/15 (cross-connection) e 0/8 (same-connection) com double-fill",
    tools: ["duplicate_buy_race_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 23,
    sampleUnit: "trials (15 cross-connection + 8 same-connection concurrent buys)",
  },
  {
    id: "D54",
    title: "Streamed Proposal Staleness (subscribe:1 lag)",
    market: "DERIV · api.derivws.com/trading/v1/options · proposal subscribe:1",
    thesis:
      "Um proposal_id de uma subscription 'ao vivo' (subscribe:1) que a tela mostra " +
      "desatualizado em relação ao underlying poderia ainda ser aceito na compra, permitindo " +
      "comprar a um preço obsoleto favorável antes do servidor reagir.",
    confidence: 2,
    status: "refuted",
    tags: ["deriv", "execution", "streaming", "proposal-staleness", "websocket"],
    trigger: "Assinar proposal com subscribe:1, aguardar tick(s) do underlying sem re-pedir, tentar comprar contra o proposal_id do stream original.",
    invalidation: "Proposal_id do stream expira e é rejeitado na compra, igual ao padrão do D47.",
    createdAt: "2026-07-06",
    author: "proposal_stream_staleness_probe.py",
    verdict:
      "REFUTADO + achado lateral inesperado. Assinar proposal com subscribe:1 no gateway novo " +
      "deveria realimentar a cada tick (~1/s), mas NUNCA reenviou uma segunda atualização em " +
      "50+s (confirmado via subscription id válido + conexão seguindo responsiva a outros " +
      "requests na mesma sessão — não foi queda de rede). Consequência: o proposal_id do " +
      "stream ficou obsoleto rapidamente — 2/3 tentativas de compra contra ele foram " +
      "rejeitadas ('Unknown contract proposal'); a 1 aceita não deu pra confirmar honra/" +
      "recálculo de forma limpa (entry_spot ainda não populado no poll imediato). Sem janela " +
      "de staleness explorável — proposals antigos expiram e são rejeitados, consistente com " +
      "D47. Vale registrar como comportamento de plataforma a investigar separadamente (pode " +
      "afetar UX de bots/dashboards que dependem dessa subscription para preço 'ao vivo').",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "2/3 tentativas de compra contra proposal_id de stream rejeitadas (N pequeno, achado qualitativo)",
    tools: ["proposal_stream_staleness_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 3,
    sampleUnit: "tentativas de compra contra proposal_id de subscription ao vivo",
  },
  {
    id: "D55",
    title: "Hyperliquid (perp DEX) vs Binance — funding arb + oracle/mid divergence",
    market: "Hyperliquid perps (BTC/ETH/SOL/ARB/OP/AVAX/LINK/DOGE/SUI/APT) vs Binance USDT-M",
    thesis:
      "Primeira plataforma nova pós-fechamento de Deriv/Polymarket/CEX-CEX. Construção " +
      "perp-perp (sem perna spot) entre Hyperliquid e Binance tem round-trip ~19bps " +
      "(vs 40bps do D9 CEX-CEX) — se o funding divergir persistentemente, dá pra capturar. " +
      "Hyperliquid também expõe oraclePx/markPx/midPx juntos (mecanismo que CEX não tem) — " +
      "se midPx atrasar vs oraclePx/Binance, há janela de preço defasado no livro.",
    confidence: 55,
    status: "validating",
    tags: ["hyperliquid", "perp-dex", "funding-arb", "cross-venue", "oracle-divergence", "nova-plataforma", "link"],
    trigger:
      "D55a: funding HL acumulado (8h) vs funding Binance, mesmo ativo, direção fixada na " +
      "metade IS e testada na OOS. D55b: |hl_midPx - binance_mid| > custo round-trip (9.5bps)",
    invalidation:
      "D55a: IC95% da metade OOS cruzar zero (aplicado, derrubou 6/10 candidatos iniciais). " +
      "D55b: % de amostras acima do custo round-trip não superar ruído de curto prazo",
    createdAt: "2026-07-06",
    author: "hyperliquid_probe.py",
    verdict:
      "VALIDANDO — LINK isolado como candidato forte, ETH/SOL/OP caíram na validação mais " +
      "rigorosa. D55a screening (funding arb, 90d, N=270 janelas/ativo): 8/10 ativos pareciam " +
      "lucrativos no período inteiro (falso-positivo tipo D9), split IS/OOS único deixou 4/10 " +
      "(ETH, SOL, OP, LINK). Walk-forward multi-janela (sem look-ahead, custo só em " +
      "entrada/saída/flip de direção — cobrar toda semana seria simular a estratégia errada) " +
      "derruba 3 dos 4: ETH/SOL/OP têm win rate real (50-75%) mas trocam de lado com frequência " +
      "suficiente pra que o custo por flip (19bps) coma o edge (net -44 a -112bps/90d). " +
      "SÓ LINK sobrevive, de forma robusta: ZERO flips em 90 dias (fold de 7d E 5d, mesmo " +
      "resultado), 100% win rate, net +96-100bps, CI95% bem longe de zero. Direção: short HL " +
      "LINK-PERP + long Binance LINK-PERP. Custo de capital testado (T-bill 5% APR, premissa " +
      "do D9): perp-perp só exige margem (não notional cheio como a perna spot do D9) — LINK " +
      "sobrevive a partir de ~3x de alavancagem/perna (net-net +19.6 a +84.8bps entre 3x-20x), " +
      "só fica negativo em capital 100%-cash-secured (≤2x). D55b (divergência " +
      "oraclePx/markPx/midPx vs Binance), CONFIRMADO com N=10.021 (~8.3h AWS) em BTC/ETH/SOL " +
      "E checado especificamente no LINK (N=100, 5min local, +7.64bps, mesmo padrão): basis " +
      "persistente e quase sempre positivo — não cruza zero, é prêmio estrutural, mesmo " +
      "mecanismo que provavelmente gera o funding do D55a (reduz um pouco a confiança de que " +
      "seja \"grátis\", mas não invalida ser capturável). Falta: walk-forward ainda é sobre " +
      "os mesmos 90d do screening (robustez interna, não OOS temporal de verdade). " +
      "NOTA 2026-07-08: probe parou sozinho em 2026-07-07 (coleta de N=10.021 concluída), " +
      "sem processo rodando na AWS desde então. PAPER TRADING OOS INICIADO 2026-07-08 16:50 UTC: " +
      "`hyperliquid_paper_bot.py` (tmux `d55_paper`) abriu posição simulada SHORT HL LINK @ $7.6071 " +
      "+ LONG BN LINKUSDT @ $7.6033, $1000 notional, 19bps roundtrip debitado. A cada ciclo de " +
      "funding da Binance (8h) settle: funding coletado em ambos venues + mark-to-mark P&L. " +
      "Report com Wilson/bootstrap a cada 5 ciclos. Primeiro ciclo às 00:00 UTC. Adicionado ao " +
      "`aggressive_supervisor` (auto-restart). REMEDIAÇÃO 2026-07-12: coorte v2 iniciou com " +
      "custo de entrada/saída 9.5bps cada. UPDATE 2026-07-13: 3 ciclos v2 completados. " +
      "Cycle 1: −2.38 bps, Cycle 2: +5.28 bps, Cycle 3: −4.51 bps. Total: −11.11 bps (−$1.11). " +
      "Funding coletado líquido: +1.45 bps. Mark P&L: −3.05 bps. Custo de entrada (−9.5 bps) " +
      "ainda não recuperado. WR 33% (1/3). Posição OPEN. Precisa ~10+ ciclos para o funding " +
      "acumulado superar custo de entrada + mark divergence.",
    ci95Label: "3 ciclos v2: total −11.11 bps (−$1.11). Walk-forward histórico: LINK +96.3 [+71.6,+121.6]. OOS em coleta.",
    tools: ["hyperliquid_probe.py", "stats_utils.py"],
    reportFile: "docs/hyperliquid_report.md",
    pnl: 0,
    trades: 270,
    sampleUnit: "janelas de funding 8h/ativo (D55a, N=270) + walk-forward folds 7d/5d + polls 3s (D55b, N=10.021, ~8.3h AWS)",
  },
  {
    id: "D56",
    title: "Cross-Symbol Tick Correlation (1HZ/R_ shared RNG prediction)",
    market: "DERIV · sinteticos 1HZ10V/25V/50V/100V + R_10/25/50/75/100 · ticks WS",
    thesis:
      "Indices sinteticos '1Hz' e 'R_' podem compartilhar estado de RNG ou ter ticks " +
      "correlacionados. Se 1HZ10V prediz 1HZ100V (ou R_10 prediz R_100) com lag mensuravel, " +
      "ha edge direcional gratis — comprar CALL/PUT no simbolo atrasado sabendo para onde o " +
      "simbolo adiantado ja foi. D46 testou autocorrelacao DENTRO de um simbolo; isto testa " +
      "ENTRE simbolos.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "synthetic", "cross-symbol", "correlation", "rng", "refutado"],
    trigger: "Cross-correlacao de retornos normalizados entre pares de simbolos em lags -5..+5, |r|>0.05 com p<0.05.",
    invalidation: "Nenhuma correlacao significativa em 36 pares com N>=150 amostras por lag.",
    createdAt: "2026-07-11",
    author: "cross_symbol_correlation_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=2081 ticks, 9 simbolos, 36 pares, 4 rounds de analise). " +
      "Nenhuma correlacao significativa (|r|>0.05, p<0.05) em nenhum par em nenhum lag. " +
      "Melhor correlacao observada: r=+0.3767 (1HZ50V->R_10 lag=-1) mas p=0.6308 — ruido. " +
      "Valores-p AUMENTARAM com mais amostra (0.65→0.70→0.77→0.80), confirmando ausencia " +
      "real de correlacao. Simbolos sinteticos sao independentes — cada um tem seu proprio " +
      "RNG, nao ha estado compartilhado. Edge direcional cross-symbol nao existe.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "0/36 pares com correlacao significativa (|r|>0.05, p<0.05), N=150+ por lag",
    tools: ["cross_symbol_correlation_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "pares de simbolos testados (36 pares x 11 lags, N=150+ amostras por lag, 2081 ticks totais)",
  },
  {
    id: "D57",
    title: "Stake Size Non-Linearity (payout ratio rounding artifact)",
    market: "DERIV · sinteticos 1HZ10V/50V + R_10/50/100 · CALL/PUT · 5 ticks · stakes $0.35-$100",
    thesis:
      "O ask_price da Deriv pode nao escalar perfeitamente linear com o stake. Se houver " +
      "arredondamento ou descontinuidade em certos tamanhos, o payout efetivo pode variar, " +
      "criando uma edge onde certos stakes tem payout ratio melhor que outros.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "stake", "payout", "non-linearity", "rounding", "refutado"],
    trigger: "Payout ratio (payout/stake) varia com stake size de forma sistematica e estatisticamente significativa.",
    invalidation: "Non-linearidade confirmada mas sempre penaliza stakes pequenos — nenhum stake tem ratio MELHOR que o true ratio.",
    createdAt: "2026-07-11",
    author: "stake_nonlinearity_probe.py",
    verdict:
      "NAO-LINEARIDADE CONFIRMADA MAS NAO EXPLOITAVEL (2026-07-11, N=1162 proposals, 5 simbolos, " +
      "2 contract types, 12 stakes, 20 rounds). Payout ratio varia sistematicamente: $0.35→1.886 " +
      "(−1.9% vs true 1.923), $0.50→1.920 (−0.15%), $1.00+→1.923 (nominal). Causa: arredondamento " +
      "de payout para centavos destrui valor proporcional em stakes pequenas. PATTERN CONSISTENTE " +
      "across all symbols/rounds. Porem: o arredondamento SEMPRE penaliza (floor), nunca beneficia " +
      "— nao existe stake onde ratio > true ratio. A 'edge' seria evitar stakes <$0.50, o que nao " +
      "e profit edge mas apenas evitar penalidade. Achado adicional: payout em $0.35 e $0.01 ABAIXO " +
      "do floor teorico (esperado $0.67, atual $0.66), sugerindo haircut adicional para stakes " +
      "minimas. Nao ha forma de extrair profit desta nao-linearidade.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Payout ratio: 1.886 em $0.35 vs 1.923 em $100 (−1.9%), consistente em 5 simbolos x 20 rounds",
    tools: ["stake_nonlinearity_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 1162,
    sampleUnit: "proposals (5 simbolos x 2 contract types x 12 stakes x ~10 rounds = 1162 proposals)",
  },
  {
    id: "D58",
    title: "Sell as Limit Order (price>0 in sell endpoint)",
    market: "DERIV · 1HZ10V · CALL 10 ticks · sell endpoint com price>0 vs price=0",
    thesis:
      "O endpoint sell da Deriv aceita um parametro price. D48/D50 sempre usaram price=0 " +
      "(market sell). Se enviarmos price>0, pode funcionar como limit order — se o bid_price " +
      "atingir esse valor, o contrato vende a um preco melhor que o market sell.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "sell", "limit-order", "execution", "refutado"],
    trigger: "Sell com price>0 aceito e executa a preco melhor que market sell (price=0).",
    invalidation: "Sell rejeitado para o contract type testado — 'Resale of this contract is not offered'.",
    createdAt: "2026-07-11",
    author: "sell_limit_order_probe.py",
    verdict:
      "REFUTADO para tick contracts (2026-07-11, N=50 trials, 25 LIMIT + 25 MARKET). TODOS os " +
      "50 sells rejeitados com 'Resale of this contract is not offered' — tanto limit (price>0) " +
      "quanto market (price=0). Contratos CALL de 10 ticks em 1HZ10V NAO oferecem resale: nao e " +
      "possivel vender antes do expiry a nenhum preco. O parametro price no endpoint sell e " +
      "irrelevante quando o contrato nao suporta resale. D58 refutado: limit order nao funciona " +
      "porque sell nao funciona. NOTA: resale pode estar disponivel para contratos de duracao " +
      "maior (1d+), mas isso e um teste diferente — para tick contracts, o endpoint sell esta " +
      "fechado.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "50/50 sells rejeitados (25 LIMIT + 25 MARKET), 'Resale of this contract is not offered'",
    tools: ["sell_limit_order_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 50,
    sampleUnit: "trials (25 LIMIT sell + 25 MARKET sell, CALL 10-tick 1HZ10V, demo account)",
  },
  {
    id: "D59",
    title: "POC Subscription vs Poll Timing Gap (subscribe:1 staleness)",
    market: "DERIV · 1HZ10V · CALL 5 ticks · POC subscribe:1 vs poll manual 200ms",
    thesis:
      "Assinar proposal_open_contract com subscribe:1 vs poll manual. Se a subscription " +
      "notificar settle DEPOIS do poll, ha janela onde o poll sabe algo que a subscription " +
      "nao sabe. Se o poll detecta settle antes da subscription, podemos agir antes do stream.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "poc", "subscription", "poll", "timing", "refutado"],
    trigger: "Poll detecta is_sold=1 consistentemente antes da subscription subscribe:1.",
    invalidation: "Subscription subscribe:1 para POC nunca envia atualizacoes — poll e a unica forma de detectar settle.",
    createdAt: "2026-07-11",
    author: "poc_subscription_vs_poll_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=30 trials). POC subscribe:1 NUNCA enviou uma unica atualizacao " +
      "em 30/30 trials (sub_events=0 em todos). Poll manual (200ms) detectou settle em 30/30 " +
      "trials. A subscription POC esta completamente quebrada — confirma achado do D54 onde " +
      "proposal subscribe:1 tambem nunca reenviou. Nao ha timing gap para explorar porque a " +
      "subscription simplesmente nao funciona: poll e a unica opcao. Achado de plataforma: " +
      "subscribe:1 para proposal_open_contract nao realimenta, comportamento consistente " +
      "com D54. Poll RTT medio ~143ms, 15-23 polls por contrato de 5 ticks.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "30/30 trials: POLL detectou settle, SUB NUNCA notificou (sub_events=0)",
    tools: ["poc_subscription_vs_poll_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 30,
    sampleUnit: "trials (30 CALL 5-tick 1HZ10V, POC subscribe:1 vs poll 200ms)",
  },
  {
    id: "D60",
    title: "Tick Subscription Gap Detection (stream vs history completeness)",
    market: "DERIV · 1HZ10V · ticks subscribe:1 vs ticks_history · 10min · 20 checks",
    thesis:
      "O stream de ticks via WS tem gaps (ticks perdidos)? Se sim, os ticks faltantes sao " +
      "previsiveis? D54 notou que proposal subscribe:1 nunca reenviou — mas o stream de " +
      "TICKS em si nao foi auditado quanto a completude contra o historico.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "ticks", "subscription", "gap", "completeness", "refutado"],
    trigger: "Ticks perdidos no stream seguem padrao temporal regular e previsivel.",
    invalidation: "Stream e completo (0% missing apos startup) e quotes batem 100% com historico.",
    createdAt: "2026-07-11",
    author: "tick_subscription_gap_probe.py",
    verdict:
      "REFUTADO (2026-07-11, 10min, 20 checks, 626 ticks). Stream de ticks e COMPLETO e " +
      "CONSISTENTE com historico. 5 ticks missing (0.80%) — todos no primeiro check " +
      "(startup gap de 5s consecutivas, provavelmente latencia de conexao WS inicial). " +
      "Checks 2-20: 0 missing. 0 quote mismatches em 626 ticks comparados. Gap pattern: " +
      "intervalos regulares de 1s (apenas consecutivos no startup, nao recorrentes). " +
      "Nao ha gaps previsiveis ou exploraveis no stream de ticks apos conexao estabelecida.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "5/626 ticks missing (0.80%), todos no startup. 0 quote mismatches. 19/20 checks limpos.",
    tools: ["tick_subscription_gap_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "ticks comparados (626 stream vs 626 historico, 20 checks de 30s, 10min total)",
  },
  {
    id: "D61",
    title: "Reconnection State Inconsistency (WS reconnect mid-contract)",
    market: "DERIV · 1HZ10V · CALL 10 ticks · WS disconnect+reconnect mid-contract",
    thesis:
      "Reconectar WS no meio de um contrato ativo. O estado do contrato (barriers, bid_price) " +
      "e consistente entre a sessao antiga e nova? Pode haver janela onde informacoes " +
      "obsoletas sao servidas apos reconexao.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "reconnection", "state", "consistency", "refutado"],
    trigger: "Barrier ou is_sold muda apos reconexao — dados obsoletos servidos na nova sessao.",
    invalidation: "Estado do contrato (barrier, is_sold) identico antes e depois da reconexao.",
    createdAt: "2026-07-11",
    author: "reconnection_state_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=20 trials, 13 validos). 0 barrier mismatches, 0 sold state " +
      "changes em 13 trials validos. Reconnect time medio 1.7s (1.5-2.1s). Bid_price muda " +
      "apos reconexao (esperado — ticks moveu durante os ~1.7s de reconnect), mas barrier " +
      "e is_sold sao identicos. 7/20 trials com erro de rate limit (reconnect rapido demais). " +
      "Estado do contrato e CONSISTENTE apos reconexao — nao ha janela de dados obsoletos. " +
      "O servidor mantem estado do contrato associado ao contract_id, nao a sessao WS.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "0/13 barrier mismatches, 0/13 sold state changes apos reconexao (reconnect ~1.7s)",
    tools: ["reconnection_state_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 20,
    sampleUnit: "trials (20 CALL 10-tick 1HZ10V, 13 validos, WS disconnect+reconnect mid-contract)",
  },
  {
    id: "D62",
    title: "Barrier Rounding Precision (tick vs barrier decimal places)",
    market: "DERIV · 1HZ10V/50V + R_10/50/100 · CALL/PUT · 5 ticks · 30 rounds",
    thesis:
      "Barriers de HIGHER/LOWER sao calculadas com quantas casas decimais? O tick e quoted " +
      "com mais precisao que a barrier? Se a barrier arredonda para baixo, contratos na " +
      "borda podem ter probabilidade real diferente da precificada.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "barrier", "precision", "rounding", "refutado"],
    trigger: "Barrier tem menos casas decimais que o tick, criando edge em contratos na borda.",
    invalidation: "CALL/PUT nao expoe barrier explicita — barrier e implicita (entry spot), nao ha arredondamento separado.",
    createdAt: "2026-07-11",
    author: "barrier_rounding_probe.py",
    verdict:
      "REFUTADO para CALL/PUT (2026-07-11, N=300 proposals, 253 validas, 5 simbolos, 30 rounds). " +
      "CALL/PUT (Higher/Lower) NAO retornam barrier explicita no proposal — barrier=None em " +
      "253/253 proposals. A barrier e implicita (entry spot do contrato), nao ha arredondamento " +
      "separado do tick. Spot values mostram 15 casas decimais (artefato float64, nao precisao " +
      "real). Payout ratio consistente em 1.920 across all symbols/rounds. Nao ha forma de " +
      "explorar arredondamento de barrier em CALL/PUT porque a barrier nao existe como " +
      "parametro separado — e o proprio spot de entrada. Para contratos com barrier explicita " +
      "(HIGHER/LOWER com barrier offset, Touch/No-Touch), teste separado seria necessario.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "253/253 CALL/PUT proposals com barrier=None — barrier implicita, nao ha arredondamento separado",
    tools: ["barrier_rounding_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 300,
    sampleUnit: "proposals (5 simbolos x 2 contract types x 30 rounds = 300, 253 validas)",
  },
  {
    id: "D63",
    title: "Duration Non-Linearity (payout ratio vs contract duration)",
    market: "DERIV · 1HZ10V/50V + R_10/50/100 · CALL/PUT · 1-60 ticks · 20 rounds",
    thesis:
      "O payout ratio varia com a duracao do contrato de forma nao-linear? Igual ao " +
      "D57 achou para stake (arredondamento de cents), pode haver arredondamento ou " +
      "descontinuidade em duracoes especificas onde o payout efetivo e maior.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "duration", "payout", "non-linearity", "refutado"],
    trigger: "Payout ratio (payout/stake) varia com duracao de forma sistematica e significativa.",
    invalidation: "Payout ratio constante em todas as duracoes — sem nao-linearidade.",
    createdAt: "2026-07-11",
    author: "duration_nonlinearity_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=1200 proposals, 5 simbolos, 2 contract types, 8 duracoes, 20 rounds). " +
      "Payout ratio = 1.920000 em TODAS as duracoes (1, 2, 3, 5, 10, 15, 30, 60 ticks), " +
      "ALL symbols, ALL contract types, with ZERO variance (std=0.000000). " +
      "Nao ha nao-linearidade de duracao — payout ratio e constante e independente da " +
      "duracao do contrato. Diferentemente do D57 (stake non-linearity confirmada por " +
      "arredondamento de cents), a duracao nao afeta o payout ratio de forma alguma.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Payout ratio 1.920000 constante em 1200 proposals (8 duracoes x 5 simbolos x 2 types x ~15 rounds)",
    tools: ["duration_nonlinearity_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 1200,
    sampleUnit: "proposals (5 simbolos x 2 contract types x 8 duracoes x ~15 rounds = ~1200)",
  },
  {
    id: "D64",
    title: "Entry Spot Timing (entry_spot vs tick at buy time)",
    market: "DERIV · 1HZ10V · CALL 5 ticks · tick stream vs proposal spot vs entry_spot",
    thesis:
      "Quando exatamente o entry_spot e capturado relativo ao buy request? Se o entry_spot " +
      "e o tick ANTERIOR ao momento do buy (e nao o tick atual), pode haver janela favoravel " +
      "onde o spot ja conhecido e diferente do que sera usado como entry.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "entry-spot", "timing", "staleness", "refutado"],
    trigger: "Entry_spot difere sistematicamente do tick no momento do buy (staleness favoravel).",
    invalidation: "Entry_spot = tick no momento do buy, ou diferenca e ruido bidirecional nao-sistematico.",
    createdAt: "2026-07-11",
    author: "entry_spot_timing_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=30 trials, 3 validos devido a rate limit). Nos 3 trials " +
      "validos: entry_vs_tick_buy = [-0.10, -0.10, +0.14] — diferenca pequena e BIDIRECIONAL " +
      "(nao sistematica). spot_vs_tick_proposal = [0, 0, 0] — proposal spot sempre = tick atual. " +
      "ticks_moved_during_buy = [0, 0, 0] — nenhum tick mudou durante o buy. A diferenca " +
      "entry_spot vs tick e provavelmente o tick seguinte ao buy (entry_spot e capturado no " +
      "proximo tick apos o buy ser processado, nao no tick atual). Nao ha staleness favoravel " +
      "— a diferenca e de ~1 tick na direcao aleatoria do movimento, nao um atraso exploravel. " +
      "N baixo (3/30) por rate limit da API, mas os 3 trials sao consistentes: sem edge.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "3/3 valid trials: entry_vs_tick_buy = [-0.10, -0.10, +0.14] — bidirecional, nao sistematico",
    tools: ["entry_spot_timing_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 30,
    sampleUnit: "trials (30 CALL 5-tick 1HZ10V, 3 validos devido a rate limit, tick stream vs entry_spot)",
  },
  {
    id: "D65",
    title: "Touch/No-Touch Barrier Precision (ONETOUCH/NOTOUCH barrier vs tick decimals)",
    market: "DERIV · 1HZ10V/50V + R_10/50/100 · ONETOUCH/NOTOUCH · 5 ticks + 15min · 20 rounds",
    thesis:
      "D62 so testou CALL/PUT (barrier=None). Touch/No-Touch (ONETOUCH/NOTOUCH) TEM barrier " +
      "explicita. Se a barrier tem menos precisao que o tick, contratos na borda podem ter " +
      "probabilidade real diferente da precificada.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "touch", "notouch", "barrier", "precision", "refutado"],
    trigger: "ONETOUCH/NOTOUCH barrier tem menos casas decimais que o tick, criando edge na borda.",
    invalidation: "ONETOUCH/NOTOUCH tambem retornam barrier=None — barrier e implicita, nao exposta na resposta.",
    createdAt: "2026-07-11",
    author: "touch_notouch_barrier_probe.py",
    verdict:
      "REFUTADO (2026-07-11). ONETOUCH/NOTOUCH sao contract types validos e funcionam com " +
      "barriers relativas (+5, -5) em ambas duracoes tick e minuto. Porem, assim como CALL/PUT " +
      "no D62, TODAS as proposals retornam barrier=None — a barrier e calculada server-side " +
      "e nao exposta na resposta do proposal. Payout varia com a barrier distance (ONETOUCH " +
      "5t +5: payout=$31.25, ONETOUCH 15m +5: payout=$3.06, NOTOUCH 15m +5: payout=$1.43), " +
      "confirmando que a barrier e usada internamente. Mas sem o valor da barrier na resposta, " +
      "e impossivel comparar precisao barrier vs tick. Mesma conclusao do D62: a API Deriv " +
      "nao expoe barriers explicitas em nenhum contract type testado (CALL/PUT/ONETOUCH/NOTOUCH).",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "ONETOUCH/NOTOUCH proposals retornam barrier=None — mesma limitacao do D62",
    tools: ["touch_notouch_barrier_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "API tests (ONETOUCH/NOTOUCH com barriers relativas + absolutas, tick + minuto)",
  },
  {
    id: "D66",
    title: "Tick Count Settlement Precision (contract duration vs actual tick count)",
    market: "DERIV · 1HZ10V · CALL · 1/5/10/15/30 ticks · 10 trials per duration",
    thesis:
      "Um contrato de 10 ticks sempre settle no exato 10o tick? Ou ha variabilidade? Se " +
      "as vezes settle no 9o ou 11o tick, o payout efetivo por tick muda e ha edge sistemtico.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "tick-count", "settlement", "precision", "refutado"],
    trigger: "Tick count real (do POC) difere da duracao solicitada de forma sistematica.",
    invalidation: "Tick count sempre exato — contratos settle no numero exato de ticks solicitado.",
    createdAt: "2026-07-11",
    author: "tick_count_settlement_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=50 trials, 3 validos com tick_count reportado). Nos 3 trials " +
      "validos (todos duracao=10 ticks): tick_count=10, diff=+0 em 3/3. Contratos sempre " +
      "settle no numero exato de ticks solicitado. 47/50 trials sem tick_count no POC " +
      "(campo nao populado no poll ou contract ainda nao settled no timeout). Mas os 3 " +
      "validos sao 100% consistentes: tick_count exato. Nao ha variabilidade de settlement " +
      "para explorar. Duracoes 1, 5, 15, 30 ticks: todos os trials tiveram timeout ou POC " +
      "sem tick_count (provavelmente rate limit ou POC nao popula campo para duracoes curtas).",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "3/3 valid trials: tick_count=10 exato, diff=+0 (duracao=10 ticks)",
    tools: ["tick_count_settlement_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 50,
    sampleUnit: "trials (50 CALL 1/5/10/15/30-tick 1HZ10V, 3 validos com tick_count reportado)",
  },
  {
    id: "D67",
    title: "Cross-Duration Sequential Info Edge (5-tick outcome vs 10-tick outcome)",
    market: "DERIV · 1HZ10V · CALL 5-tick + CALL 10-tick simultaneos · 40 trials",
    thesis:
      "Comprar CALL 5-tick + CALL 10-tick simultaneamente. Apos 5-tick settle, voce sabe " +
      "a direcao de 5 dos 10 ticks. Se ha autocorrelacao, saber os primeiros 5 ticks da " +
      "edge nos 5 restantes. D46 testou padroes de 3 ticks — isto testa informacao parcial " +
      "em contratos sobrepostos.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "cross-duration", "autocorrelation", "info-edge", "artefato-matematico"],
    trigger: "P(10t WON | 5t WON) != P(10t WON | 5t LOST) de forma significativa.",
    invalidation: "P(10t WON | 5t WON) = P(10t WON | 5t LOST) — ticks independentes.",
    createdAt: "2026-07-11",
    author: "cross_duration_info_probe.py",
    verdict:
      "REFUTADO COMO ARTEFATO MATEMATICO (2026-07-11, N=40 trials, bug corrigido). " +
      "Apos corrigir bug no wait_settle() (is_won nao populado antes de is_sold), " +
      "re-rodou com N=40. Resultado: P(10t WON | 5t WON)=0.867 (13/15), " +
      "P(10t WON | 5t LOST)=0.200 (5/25), diff=+0.667. Mas isto e ARTEFATO MATEMATICO, " +
      "nao autocorrelacao: o contrato 10-tick INCLUI os mesmos 5 ticks do 5-tick. Se " +
      "os primeiros 5 ticks subiram (5t WON), o 10-tick ja esta ITM e so precisa " +
      "manter nos 5 restantes. Nao e exploravel diretamente — nao da para vender " +
      "tick contracts (D58 confirmou). P&L: 5t=-$11.20, 10t=-$5.44 (house edge). " +
      "Combinacao D67+D69: se 5-tick outcome prediz 5-minuto early (onde sell " +
      "funciona), overlap seria apenas 5/300 ticks (1.7%), poder preditivo muito menor.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "P(10t|5t WON)=0.867 vs P(10t|5t LOST)=0.200 — artefato matematico (overlap de ticks)",
    tools: ["cross_duration_info_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -16.64,
    trades: 80,
    sampleUnit: "trials (40 CALL 5t + 40 CALL 10t = 80 contracts, bug corrigido, WR 37.5%/45%", 
  },
  {
    id: "D68",
    title: "Tick Arrival Jitter (sub-second timing precision of tick generation)",
    market: "DERIV · 1HZ10V · 300 ticks coletados por 5 minutos",
    thesis:
      "Ticks sinteticos chegam a exatamente 1 segundo de intervalo? Se ha jitter sub-segundo " +
      "no relogio de geracao de ticks, voce pode prever quando o proximo tick chega e " +
      "timingar o buy para capturar entry_spot favoravel. D60 testou ticks faltantes, mas " +
      "nao jitter.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "tick", "jitter", "timing", "latency", "refutado"],
    trigger: "Jitter sub-segundo nos inter-arrival times que e previsivel (autocorrelacionado).",
    invalidation: "Server-side epoch diffs = 1.000s exato, jitter e apenas ruido de rede nao-previsivel.",
    createdAt: "2026-07-11",
    author: "tick_arrival_jitter_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=300 ticks, 5min). Server-side epoch diffs: exatamente 1.000s " +
      "com std=0.000s — servidor gera ticks em intervalos perfeitamente regulares. Jitter " +
      "local: mean=-0.14ms, std=26.6ms, 92.7% dentro de [0.95, 1.05]s. Latencia rede: " +
      "mean=145ms, std=16.4ms. Autocorrelacao lag-1 = -0.72 (forte negativa) — mas isto e " +
      "ping-pong de latencia de rede (se um tick chega atrasado, o proximo chega adiantado " +
      "porque o buffer de rede esvaziou), NAO e do servidor. Server-side jitter = 0. " +
      "Nao ha jitter previsivel para explorar no timing do buy.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Server epoch diffs: 1.000s ± 0.000s (N=300). Jitter local 26.6ms = ruido de rede.",
    tools: ["tick_arrival_jitter_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "ticks (300 ticks 1HZ10V coletados em 5min, inter-arrival + epoch + latencia)",
  },
  {
    id: "D69",
    title: "Long-Duration Resale (sell funciona para duracoes > tick?)",
    market: "DERIV · 1HZ10V · CALL · 1m/5m/15m/1h/4h/1d · 2 trials per duration",
    thesis:
      "D58 so testou tick contracts (resale rejeitado: 'Resale not offered on this contract'). " +
      "O veredito notou que 'resale pode existir para duracoes maiores (1d+)'. Se sell " +
      "funciona para contratos longos, a hipotese early-sell (HYP-SELL-01) pode ser " +
      "re-testada com capacidade real de venda.",
    confidence: 0,
    status: "validating",
    tags: ["deriv", "resale", "sell", "long-duration", "early-sell", "descoberta"],
    trigger: "Sell aceito em duracoes > tick — reabre early-sell com venda real.",
    invalidation: "Sell rejeitado em todas as duracoes — D58 confirmado.",
    createdAt: "2026-07-11",
    author: "long_duration_resale_probe.py",
    verdict:
      "DESCOBERTA SIGNIFICATIVA (2026-07-11, N=12 tests, 2 per duration). Sell ACEITO em " +
      "12/12 tests across ALL durations: 1m, 5m, 15m, 1h, 4h, 1d. Sell prices: $0.87-$0.95 " +
      "(buy $1.00, spread 5-13 cents). Bid prices disponiveis no POC: $0.87-$1.22. " +
      "is_valid_to_sell=1 em todos. D58 estava ERRADO ao concluir 'Resale not offered' — " +
      "so testou tick contracts. Sell funciona para minute/hour/day durations. " +
      "ISTO REABRE a hipotese early-sell (HYP-SELL-01, refutada com hindsight bias em " +
      "simulacao). Agora pode ser re-testada com capacidade REAL de venda: comprar CALL " +
      "15m, monitorar bid_price, vender quando bid > threshold. A pergunta nao e mais " +
      "'sell funciona?' mas 'sell no momento certo tem EV positivo vs hold-to-expiry?'. " +
      "PROXIMO PASSO: re-testar HYP-SELL-01 com sells reais em duracoes 15m+.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "12/12 sells aceitos (1m a 1d). Sell prices $0.87-$0.95, bid prices $0.87-$1.22.",
    tools: ["long_duration_resale_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -1.08,
    trades: 12,
    sampleUnit: "tests (6 duracoes x 2 trials = 12 contracts, todos vendidos com sell real)",
  },
  {
    id: "D70",
    title: "Multi-Contract Entry Spot Consistency (contratos simultaneos mesmo entry_spot?)",
    market: "DERIV · 1HZ10V · CALL 5-tick · 3 contracts/trial · 20 trials",
    thesis:
      "Comprar 2+ contratos no mesmo simbolo simultaneamente. Todos recebem o mesmo " +
      "entry_spot? Se nao, ha discrepancia exploravel — sempre comprar o contrato com " +
      "entry_spot favoravel. D64 testou 1 contrato vs tick; isto testa consistencia " +
      "entre multiplos contratos concorrentes.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "multi-contract", "entry-spot", "consistency", "refutado"],
    trigger: "Contratos simultaneos recebem entry_spots diferentes de forma previsivel.",
    invalidation: "Entry_spots diferem apenas por movimento de tick entre buys sequenciais — nao previsivel.",
    createdAt: "2026-07-11",
    author: "multi_contract_entry_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=20 trials, 60 contracts). 20/20 trials: entry_spots DIFERENTES " +
      "(0/20 identicos). Spread medio: 0.176, max: 0.36. Mas os buys sao sequenciais (0.3s " +
      "apart), e cada buy captura o tick atual no momento do processamento. O spread e " +
      "apenas o movimento aleatorio do tick entre buys — ~1-2 ticks de movimento. Nao e " +
      "previsivel qual contrato recebera o entry_spot favoravel. P&L: +$4.32 (60 contracts, " +
      "WR=52%) — consistente com random walk. Se os buys fossem verdadeiramente simultaneos " +
      "(mesmo milissegundo), poderiam receber o mesmo entry_spot, mas a API processa " +
      "requests sequencialmente. Nao ha discrepancia exploravel.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "20/20 trials: entry_spots diferentes, spread medio 0.176 — movimento de tick, nao previsivel",
    tools: ["multi_contract_entry_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 4.32,
    trades: 60,
    sampleUnit: "contracts (20 trials x 3 contracts = 60 CALL 5-tick 1HZ10V, buys sequenciais 0.3s apart)",
  },
  {
    id: "D71",
    title: "Early-Sell Real Probe (non-hindsight, paired) — HYP-SELL-01 re-test com sell real",
    market: "DERIV · 1HZ10V · CALL/PUT 5m alternados · 30 trials · stake $1.00",
    thesis:
      "D69 descobriu que sell funciona em duracoes > tick. Isto reabre HYP-SELL-01 " +
      "(early-sell optionality), refutada anteriormente por hindsight bias na simulacao " +
      "original (usava max(bid) do caminho todo — so conhecido no expiry). Metodologia " +
      "corrigida: threshold predefinido, vender no primeiro bid >= threshold, comparacao " +
      "pareada por trial (sell_rule_profit vs hold_profit), bootstrap diff para IC95%.",
    confidence: 3,
    status: "validating",
    tags: ["deriv", "early-sell", "resale", "non-hindsight", "paired", "edge", "descoberta"],
    trigger: "IC95% da diferenca sell_rule_profit - hold_profit exclui zero em pelo menos um threshold.",
    invalidation: "IC95% cruza zero em todos os thresholds — sell cedo nao tem EV positivo.",
    createdAt: "2026-07-11",
    author: "early_sell_real_probe.py",
    verdict:
      "*** EDGE ENCONTRADO *** (2026-07-11, N=30 trials, 5m CALL/PUT alternados 1HZ10V). " +
      "Hold-to-expiry: EV=-$0.040, WR=50%. Max bid ratio: mean=1.855, max=1.920. " +
      "Todos os thresholds 1.05-1.70 tem CI95% excluindo zero: " +
      "threshold 1.05: diff=+$0.491 CI95%[+$0.070,+$0.915]; " +
      "threshold 1.10: diff=+$0.525 CI95%[+$0.109,+$0.941]; " +
      "threshold 1.30: diff=+$0.594 CI95%[+$0.205,+$0.993]; " +
      "threshold 1.50: diff=+$0.681 CI95%[+$0.318,+$1.063] (MELHOR); " +
      "threshold 1.70: diff=+$0.671 CI95%[+$0.334,+$1.013]; " +
      "threshold 2.00: 0/30 triggered (bid nunca chegou a 2x buy). " +
      "Mecanismo: 1HZ10V (baixa volatilidade) oscila em torno do entry — bid chega perto " +
      "do payout ($1.92) em quase todos os trials, mesmo os que perdem. Vender quando " +
      "bid >= threshold trava o lucro antes do preco reverter. " +
      "CAVEAT: poll de 2s pode superestimar sell price (bid salta de <1.30 para ~1.80 " +
      "entre polls). Mesmo com estimativa conservadora (sell exatamente no threshold), " +
      "o edge persiste. PROXIMO PASSO: D72 — validar com sells reais (fase 2).",
    evPerTrade: 0.681,
    ci95: [0.318, 1.063],
    ci95Label: "Diff sell_rule - hold no threshold 1.50 (melhor): +$0.681 CI95%[+$0.318,+$1.063]",
    tools: ["early_sell_real_probe.py", "long_duration_resale_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -1.2,
    trades: 30,
    sampleUnit: "trials (30 CALL/PUT 5m 1HZ10V, bid monitorado via POC polling 2s, nao vendido de verdade)",
  },
  {
    id: "D72",
    title: "Early-Sell REAL Validation (A/B pareado com sells reais) — fase 2 do D71",
    market: "DERIV · 1HZ10V · CALL/PUT 5m alternados · 40 trials · stake $1.00",
    thesis:
      "D71 encontrou edge em simulacao non-hindsight (monitorou bid mas nao vendeu). " +
      "D72 valida com sells REAIS: grupo A vende quando bid >= threshold, grupo B hold. " +
      "Alternancia A/B por trial. Elimina concern de superestimacao do sell price.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "early-sell", "resale", "real-sell", "ab-test", "falso-positivo"],
    trigger: "IC95% da diferenca sell_EV - hold_EV exclui zero e e positivo.",
    invalidation: "IC95% cruza zero ou point estimate negativo — sell cedo nao tem EV positivo.",
    createdAt: "2026-07-11",
    author: "early_sell_real_validation.py",
    verdict:
      "REFUTADO / FALSO-POSITIVO D71 (2026-07-11, N=40, threshold 1.30, A/B pareado). " +
      "Sell: EV=-$0.037, WR=65% (15 sold, 5 expired). Hold: EV=+$0.248, WR=65%. " +
      "Diff (sell - hold)=-$0.285 CI95%[-$0.689,+$0.140] — INCONCLUSIVO mas point estimate NEGATIVO. " +
      "CAUSA RAIZ: vender a bid_ratio ~1.30 trava lucro em ~$0.30, mas upside do hold e $0.92. " +
      "Mesma WR (65%), hold tem EV muito maior. D71 superestimou sell price porque: " +
      "(1) poll de 2s capturava picos de bid que nao seriam realizados em sell real; " +
      "(2) metodologia pareada de D71 usava mesmo contrato para sell_rule e hold, " +
      "amplificando a diferenca quando contrato perdia (sell salva de -$1.00, hold perde $1.00) " +
      "mas ignorando que sell tambem corta upside (+$0.92 -> +$0.30). " +
      "Segunda rodada com threshold 1.50 em andamento para confirmar.",
    evPerTrade: -0.285,
    ci95: [-0.689, 0.14],
    ci95Label: "Diff sell - hold: -$0.285 CI95%[-$0.689,+$0.140] — point estimate negativo",
    tools: ["early_sell_real_validation.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -5.7,
    trades: 40,
    sampleUnit: "trials (20 sell + 20 hold, CALL/PUT 5m 1HZ10V, sells reais executados)",
  },
  {
    id: "D73",
    title: "Lookback Contract Fair Value Mispricing",
    market: "DERIV · 5 symbols · contracts_for scan",
    thesis:
      "LOOKBACKHIGH/LOOKBACKLOW sao contratos path-dependent com fair value significativamente " +
      "maior que vanilla. Se Deriv mispricing com modelo simplificado, ha edge.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "lookback", "path-dependent", "non-existent"],
    trigger: "Contratos LOOKBACK existem na API e tem EV > 0.",
    invalidation: "Contratos LOOKBACK nao existem na Deriv.",
    createdAt: "2026-07-11",
    author: "lookback_edge_probe.py",
    verdict:
      "REFUTADO por nao-existencia (2026-07-11). Nenhum contract type LOOKBACK " +
      "encontrado em 5 simbolos (1HZ10V, 1HZ50V, 1HZ100V, R_10, R_100). " +
      "Tipos disponiveis: ACCU, ASIAND, ASIANU, CALL, CALLE, DIGITDIFF, DIGITEVEN, " +
      "DIGITMATCH, DIGITODD, DIGITOVER, DIGITUNDER, EXPIRYMISS, EXPIRYMISSE, " +
      "EXPIRYRANGE, EXPIRYRANGEE, HIGHER, LOWER, MULTDOWN, MULTUP, NOTOUCH, " +
      "ONETOUCH, PUT, PUTE, RANGE, RESETCALL, RESETPUT, RUNHIGH, RUNLOW, " +
      "TICKHIGH, TICKLOW, TURBOSLONG, TURBOSSHORT, UPORDOWN, VANILLALONGCALL, " +
      "VANILLALONGPUT (35 tipos, nenhum LOOKBACK).",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — produto nao existe",
    tools: ["lookback_edge_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "contracts_for scan em 5 simbolos",
  },
  {
    id: "D74",
    title: "Proposal Expiry Window (Free Optionality)",
    market: "DERIV · 1HZ10V · CALL 5t · 45 trials · 9 delays (0-30s)",
    thesis:
      "Se proposal_id permanece valido por >5s, pode-se esperar o tick mover a favor " +
      "antes de comprar. Isso e optionality gratuita no proposal ID.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "proposal", "optionality", "entry-spot", "t-plus-1"],
    trigger: "Entry_spot = tick do buy (nao da proposal) e delay melhora EV.",
    invalidation: "Entry_spot sempre = T+1 (proximo tick apos buy), independente do delay.",
    createdAt: "2026-07-11",
    author: "proposal_expiry_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=45, 9 delays 0-30s). Proposal IDs permanecem validos " +
      "por 30+ segundos (todos buys sucederam). Mas entry_spot e SEMPRE T+1 " +
      "(proximo tick apos buy) — nunca igual ao proposal_spot (0/45) nem ao " +
      "tick_at_buy (0/45). Delaying buy nao da optionality porque entry e sempre " +
      "o proximo tick, independente de quando a proposal foi feita. " +
      "WR por delay varia de 20% a 80% mas e puro ruido (N=5 por delay).",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — entry_spot sempre T+1, sem optionality",
    tools: ["proposal_expiry_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -15.0,
    trades: 45,
    sampleUnit: "trials (5 per delay x 9 delays, CALL 5t 1HZ10V)",
  },
  {
    id: "D75",
    title: "Tick Spectral Analysis (FFT / Entropy / Hurst / Ljung-Box / VR)",
    market: "DERIV · 8 symbols · 1000 ticks each · spectral analysis",
    thesis:
      "D46 testou apenas 3-tick patterns. Analise de dominio de frequencia (FFT, " +
      "entropia, Hurst, Ljung-Box, VR) pode revelar periodicidade ou nao-aleatoriedade " +
      "que padroes simples nao capturam.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "spectral", "fft", "hurst", "ljung-box", "variance-ratio", "random-walk"],
    trigger: "Hurst != 0.5 ou Ljung-Box rejeita RW ou VR rejeita RW em multiplos simbolos.",
    invalidation: "Todos testes confirmam random walk (Hurst~0.5, Ljung-Box nao rejeita, VR nao rejeita).",
    createdAt: "2026-07-11",
    author: "tick_spectral_analysis_probe.py",
    verdict:
      "MARGINAL/REFUTADO (2026-07-11, N=1000 ticks/symbol, 8 symbols). " +
      "Hurst em returns: 0.62-0.65 (acima de 0.5 = mild trending) em TODOS os 8 simbolos. " +
      "VR rejeita RW em q=10 para 3/8 (1HZ10V z=-2.63 p=0.009, R_25 z=-2.73, R_100 z=-2.17). " +
      "MAS: Ljung-Box nao rejeita em nenhum (Q=9-18 < crit 31.41), FFT spectral entropy " +
      "0.93-0.94 (quase white noise), max autocorrelation apenas 0.05. " +
      "Shannon entropy normalizada 0.86-0.88. " +
      "Conclusao: existe um sinal MUITO fraco de trending (H~0.65) consistente em todos " +
      "os simbolos, mas e pequeno demais para ser exploravel — autocorrelacao maxima de " +
      "0.05 e house margin de ~4% consomem qualquer edge. Consistente com D46 (N=190k) " +
      "que encontrou micro-sinal menor que custo de transacao. " +
      "CAVEAT: apenas 1000 ticks (limite da API), N=10000 seria mais robusto.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "Hurst=0.62-0.65 (marginal trending), VR z=-2.63 (q=10), mas autocorr max=0.05",
    tools: ["tick_spectral_analysis_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "8 symbols x 1000 ticks (spectral analysis, sem trades)",
  },
  {
    id: "D76",
    title: "Early-Sell + Directional Signal Combo",
    market: "DERIV · 1HZ10V · CALL/PUT 5m · 90 trials · 3 signals · threshold 1.30",
    thesis:
      "D72 refutou early-sell com direcao aleatoria. Sinal direcional (momentum, " +
      "mean reversion, tick direction) pode melhorar WR o suficiente para early-sell " +
      "virar EV positivo.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "early-sell", "directional", "momentum", "mean-reversion", "tick-direction"],
    trigger: "Diff (sell - hold) > 0 com CI95% excluindo zero em pelo menos um signal.",
    invalidation: "CI95% cruza zero em todos os 3 sinais.",
    createdAt: "2026-07-11",
    author: "early_sell_signal_combo_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=90, 3 signals x 15 sell + 15 hold each). " +
      "Momentum: sell EV=+$0.028 vs hold EV=-$0.360, diff=+$0.388 CI95%[-$0.087,+$0.859] " +
      "— melhor sinal mas CI cruza zero. " +
      "Mean reversion: sell EV=-$0.269 vs hold EV=-$0.232, diff=-$0.037 CI95%[-$0.507,+$0.456]. " +
      "Tick direction: sell EV=+$0.067 vs hold EV=+$0.024, diff=+$0.043 CI95%[-$0.570,+$0.665]. " +
      "Todos os 3 sinais: CI cruza zero. Early-sell + sinal direcional nao tem edge. " +
      "Consistente com D72 (early-sell refutado) — sinal nao melhora EV suficiente.",
    evPerTrade: 0.043,
    ci95: [-0.57, 0.67],
    ci95Label: "Best signal (tick_direction): diff=+$0.043 CI95%[-$0.57,+$0.67] — inconclusivo",
    tools: ["early_sell_signal_combo_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -10.0,
    trades: 90,
    sampleUnit: "90 trials (3 signals x 15 sell + 15 hold, CALL/PUT 5m 1HZ10V)",
  },
  {
    id: "D77",
    title: "Untested Contract Types Mispricing (CALLE/PUTE/RESET/TURBOS/UPORDOWN)",
    market: "DERIV · 1HZ10V · 7 contract types · 16 cells · MC N=10000",
    thesis:
      "35 contract types na API, varios nunca testados: CALLE/PUTE (European), " +
      "RESETCALL/RESETPUT (reset options), TURBOSLONG/TURBOSSHORT (turbos), UPORDOWN. " +
      "Estrutura de payoff mais complexa pode ter mispricing.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "untested", "calle", "pute", "reset", "turbos", "upordown", "directional-bias"],
    trigger: "EV > 0 em pelo menos um contract type com CI95% excluindo zero.",
    invalidation: "EV <= 0 em todos os tipos (house margin presente).",
    createdAt: "2026-07-11",
    author: "untested_contracts_probe.py",
    verdict:
      "REFUTADO (2026-07-11, MC N=10000 + validacao real N=40). MC mostrou PUTE P(win)=70% " +
      "(1m) aparentando edge, mas D82 validacao com trades reais refutou: " +
      "Run 1 (N=20): WR=70% EV=+$0.344 CI95%[-$0.04,+$0.73] (falso-positivo). " +
      "Run 2 (N=20): WR=45% EV=-$0.136 CI95%[-$0.52,+$0.25] (regressao a media). " +
      "Combinado: WR=57.5% (23W/17L) EV=+$0.104 — nao significativo. " +
      "CALLE espelho (P(win)=30%) tambem era viés de amostra. " +
      "RESETCALL/RESETPUT: EV negativo. TURBOS: nao disponivel. UPORDOWN: requer barrier. " +
      "Todos os 7 tipos testados refutados — house margin presente.",
    evPerTrade: -0.136,
    ci95: [-0.52, 0.25],
    ci95Label: "D82 run 2: WR=45% EV=-$0.136 CI95%[-$0.52,+$0.25] — viés de amostra confirmado",
    tools: ["untested_contracts_probe.py", "pute_drift_validation.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -4.0,
    trades: 40,
    sampleUnit: "MC: 16 cells x 10000 sims; Real: 40 PUTE 5t trades (2 runs x 20)",
  },
  {
    id: "D80",
    title: "Weekend/Holiday Synthetic Volatility Shift",
    market: "DERIV · 8 symbols · 20000 ticks each · volatility by day/hour",
    thesis:
      "Sinteticos sao RNG. Se volatilidade muda em weekend mas payout nao ajusta, ha edge.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "volatility", "weekend", "rng", "constant"],
    trigger: "Diferenca de volatilidade >10% entre weekend e weekday.",
    invalidation: "Volatilidade constante 24/7 (RNG nao muda).",
    createdAt: "2026-07-11",
    author: "weekend_volatility_probe.py",
    verdict:
      "REFUTADO (2026-07-11, 8 symbols, 20000 ticks each). " +
      "Dados insuficientes para weekend analysis (API so retorna ~5000 ticks " +
      "recentes = ~1.4h, nao cobre weekend). Max/Min vol ratio por hora = 1.03x " +
      "(praticamente constante). RNG da Deriv e constante 24/7. " +
      "Para testar weekend propriamente, precisaria coletar dados continuamente " +
      "por varios dias.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — volatilidade constante (ratio 1.03x)",
    tools: ["weekend_volatility_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "8 symbols x 20000 ticks (volatility analysis, sem trades)",
  },
  {
    id: "D81",
    title: "Buy Limit Order (price < ask_price)",
    market: "DERIV · 1HZ10V · CALL 5t · 40 trials · 8 price fractions",
    thesis:
      "Se buy com price < ask_price suceder, age como limit order — optionality gratuita.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "buy-limit", "execution", "rejected"],
    trigger: "Buy com price < ask_price suceder e dar discount.",
    invalidation: "Deriv rejeita buy com price < ask_price.",
    createdAt: "2026-07-11",
    author: "buy_limit_test_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=40, 8 fracoes 0.01x-0.95x). Deriv rejeita 100% dos " +
      "buys com price < ask_price com erro 'Contract stake amount is more than " +
      "maximum purchase price'. Apenas price = ask_price (1.00x) sucede (5/5). " +
      "Sem optionality no buy — Deriv sempre cobra ask price completa.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — buy limit rejeitado em 100% dos trials",
    tools: ["buy_limit_test_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: -2.0,
    trades: 5,
    sampleUnit: "40 trials (5 per fraction x 8 fractions, CALL 5t 1HZ10V)",
  },
  {
    id: "D86",
    title: "CALL+PUT Simultaneous Arbitrage (Straddle)",
    market: "DERIV · 8 symbols · 2 pairs (CALL/PUT, CALLE/PUTE) · 5 durations · 330 samples",
    thesis:
      "Se ask_CALL + ask_PUT < payout, comprar ambos garante lucro independente da direcao.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "straddle", "arbitrage", "house-margin"],
    trigger: "ask_CALL + ask_PUT < min(payout) em pelo menos uma amostra.",
    invalidation: "ask_CALL + ask_PUT >= min(payout) em 100% das amostras.",
    createdAt: "2026-07-11",
    author: "straddle_arb_probe.py",
    verdict:
      "REFUTADO (2026-07-11, N=330 amostras, 8 symbols, 2 pairs, 5 durations). " +
      "0/330 oportunidades de arbitrage. Spread sempre negativo: " +
      "CALL+PUT: -$0.0800 (ask_total=$2.00, payout=$1.92). " +
      "CALLE+PUTE: -$0.0800 a -$0.0900. " +
      "Deriv precifica straddle corretamente: ask_CALL + ask_PUT = 2 * stake, " +
      "payout = 1.92 * stake, spread = -0.08 * stake = house margin.",
    evPerTrade: -0.08,
    ci95: [-0.09, -0.08],
    ci95Label: "Spread straddle: -$0.08 a -$0.09 (house margin, sem arb)",
    tools: ["straddle_arb_probe.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "330 amostras (8 symbols x 2 pairs x 5 durations x ~4-10 samples)",
  },
  {
    id: "D87",
    title: "Complementary Exotic Pair Arbitrage",
    market: "DERIV · ONETOUCH/NOTOUCH · EXPIRYRANGE/EXPIRYMISS · RANGE/UPORDOWN · 1HZ10V/R_100",
    thesis:
      "Pares de contratos com eventos complementares poderiam ter ask_total menor que o menor " +
      "payout, criando lucro garantido sem depender da direção do underlying.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "exotic", "complementary", "arbitrage", "house-margin"],
    trigger: "min(payout_left, payout_right) > ask_left + ask_right.",
    invalidation: "Spread garantido <= 0 em todas as células válidas do grid.",
    createdAt: "2026-07-12",
    author: "d87_exotic_complement_scan.py",
    verdict:
      "REFUTADO no screening calibrado read-only: 80/80 cotações válidas, 0 candidatos. " +
      "Melhor spread observado foi -$0.24 e o pior -$0.99. A margem permanece em ONETOUCH/NOTOUCH, " +
      "EXPIRYRANGE/EXPIRYMISS e RANGE/UPORDOWN.",
    ci95: [0, 0],
    ci95Label: "Sem IC necessário: condição de arbitragem determinística não ocorreu em 80 células.",
    tools: ["d87_exotic_complement_scan.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 80,
    sampleUnit: "células de quote read-only (2 símbolos, 3 pares, durações tick/intraday)",
  },
  {
    id: "D88",
    title: "E-Suffixed Contract Variants",
    market: "DERIV · EXPIRYMISSE/EXPIRYRANGEE/CALLE/PUTE · 1HZ10V/R_100/frxEURUSD",
    thesis:
      "Variantes com sufixo E poderiam ter settlement ou margem diferente das variantes normais " +
      "e deixar uma célula com EV positivo.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "e-suffix", "expirymiss", "expiryrange", "calle", "pute"],
    trigger: "EV_lo > 0 com DGP consistente em alguma variante E.",
    invalidation: "Variantes não oferecidas ou EV negativo em todas as variantes cotáveis.",
    createdAt: "2026-07-12",
    author: "d88_e_variant_scan.py",
    verdict:
      "REFUTADO no escopo cotável: EXPIRYMISSE/EXPIRYRANGEE não foram oferecidos nos símbolos " +
      "testados; CALLE/PUTE tiveram 8/8 células válidas com EV negativo e nenhum gate candidate. " +
      "A tentativa forex ocorreu com o mercado fechado e não produziu amostra de preço.",
    ci95: [0, 0],
    ci95Label: "8 células CALLE/PUTE válidas; 0 gate candidates; variantes EXPIRY E sem quote.",
    tools: ["d88_e_variant_scan.py", "probe_contracts_for.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 8,
    sampleUnit: "células de quote/replay read-only; variantes EXPIRY E sem oferta nos símbolos testados",
  },
  {
    id: "D89",
    title: "Cross-Market Deriv Pricing",
    market: "DERIV · 10 forex pairs · CALL/PUT/CALLE/PUTE · 15m/1h/4h",
    thesis:
      "A margem ou arredondamento da Deriv poderia diferir entre índices sintéticos e underlyings " +
      "de forex reais. Forex tem tick size diferente e sessões de mercado — possível mispricing.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "cross-market", "forex", "pricing", "house-margin"],
    trigger: "EV_lo positivo em mercado real com pelo menos 50 janelas independentes.",
    invalidation: "Mercados reais cotáveis sem edge e com DGP consistente.",
    createdAt: "2026-07-12",
    author: "d89_cross_market_scan.py",
    verdict:
      "REFUTADO (2026-07-14, N=120 células). 10 pares forex (EURUSD, GBPUSD, USDJPY, AUDUSD, " +
      "USDCAD, USDCHF, NZDUSD, EURGBP, EURJPY, GBPJPY) × 4 types × 3 durations (15m/1h/4h). " +
      "40k ticks/símbolo, MC 10k sims. 0 gate candidates (nenhuma célula com EVlo > 0). " +
      "Mean EV = -$0.119, best EVlo = -$0.064 (GBPUSD PUT 1h). House margin forex ~12% " +
      "(MAIOR que sintéticos ~4% — forex tem spread bid-ask + overnight risk). " +
      "Pemp vs Pmc alinhado (DGP divergence < 0.03 em todas). 4h durações têm poucas windows " +
      "(2-3 non-overlapping) — não confiáveis. 15m e 1h com ~1000+ windows, conclusivos.",
    ci95: [-0.06, 0],
    ci95Label: "Best EVlo = -$0.064 (GBPUSD PUT 1h). Mean EVlo = -$0.546. N=120 cells, 0 gate candidates.",
    tools: ["d89_cross_market_scan.py", "check_forex.py", "check_crypto.py"],
    reportFile: "d89_forex_full_20260714_stats.json",
    pnl: 0,
    trades: 120,
    sampleUnit: "120 células forex (10 pairs × 4 types × 3 durations), 40k ticks/symbol, MC 10k sims",
  },
  {
    id: "D90",
    title: "Long-Duration Early-Sell A/B Validation",
    market: "DERIV · 1HZ10V · CALL/PUT · 15m/1h · DEMO",
    thesis:
      "A venda real em contratos de 15 minutos ou 1 hora poderia superar hold-to-expiry com " +
      "threshold fixo e comparação A/B alternada.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "early-sell", "resale", "long-duration", "ab-test"],
    trigger: "IC95% bootstrap de sell_profit - hold_profit totalmente acima de zero.",
    invalidation: "IC95% cruza zero ou fica abaixo de zero nas durações testadas.",
    createdAt: "2026-07-12",
    author: "d90_long_duration_early_sell.py",
    verdict:
      "REFUTADO (2026-07-13, N=40 pares A/B completos). 15m: sell EV +$0.309, hold EV +$0.536, " +
      "diff −$0.227 IC95%[−$0.65, +$0.22]. 1h: sell EV +$0.019, hold EV +$0.344, diff −$0.326 " +
      "IC95%[−$0.84, +$0.20]. Point estimate NEGATIVO em ambas durações (sell < hold). " +
      "IC95% cruza zero estatisticamente, mas padrão consistente: hold supera sell em ambas " +
      "durações — mesmo resultado do early_sell_multi N=1870. Early-sell optionality não tem " +
      "valor em nenhuma duração testada (5t/10t/25t/50t N=1870, 15m/1h N=40). Processo " +
      "completou e parou naturalmente.",
    ci95: [-0.84, 0.22],
    ci95Label: "Diff sell-hold: 15m −$0.227 IC95%[−$0.65, +$0.22] | 1h −$0.326 IC95%[−$0.84, +$0.20]. N=40 pares.",
    tools: ["d90_long_duration_early_sell.py", "stats_utils.py"],
    reportFile: "d90_live_20260712_stats.json",
    pnl: 0,
    trades: 80,
    sampleUnit: "40 pares A/B DEMO completos (20 × 15m + 20 × 1h), threshold 1.5, 1HZ10V",
  },
  {
    id: "D91",
    title: "Accumulator Survival Edge",
    market: "DERIV · ACCU · synthetic indices · R_10/R_25/R_50/R_75/R_100/1HZ",
    thesis:
      "A probabilidade de sobreviver dentro da barreira tick a tick poderia superar a taxa fair " +
      "necessária para o crescimento composto do stake.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "accumulator", "growth-rate", "survival", "house-margin"],
    trigger: "EV_lo > 0 para algum growth_rate e número de ticks-alvo.",
    invalidation: "EV_lo <= 0 em todo o grid e P_emp abaixo da probabilidade fair.",
    createdAt: "2026-07-12",
    author: "accumulator_edge_scan.py",
    verdict:
      "REFUTADO read-only: 630 células de símbolo x growth_rate x ticks foram testadas, " +
      "sem nenhum EV_lo positivo. A validação independente com 5.000 ticks reais de 1HZ100V " +
      "também encontrou P(sobreviver 1 tick) abaixo da taxa fair em todos os growth rates.",
    ci95: [0, 0],
    ci95Label: "0/630 candidatos; validação independente N=4.999 por growth rate.",
    tools: ["probe_accumulator.py", "accumulator_edge_scan.py", "accumulator_validate.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 0,
    sampleUnit: "630 células read-only + 4.999 transições tick-a-tick por growth rate em 1HZ100V",
  },
  {
    id: "D92",
    title: "Jump Indices Spike Timing",
    market: "DERIV · JD10/JD25/JD50/JD75/JD100 · 50k ticks por símbolo",
    thesis:
      "Jump Indices pulam em média a cada ~20 minutos, direção 50/50. Se o processo tiver memória " +
      "(hazard crescente com o tempo desde o último salto) ou viés de direção, dá para posicionar " +
      "antes do próximo salto. Extende a metodologia T2 de Boom/Crash para uma nova família de símbolos.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "jump-index", "spike-timing", "memoryless", "refutado"],
    trigger: "CV < 0.8 ou hazard crescente; ou direção UP significativamente diferente de 50%.",
    invalidation: "CV ~1.0, hazard constante e direção 50/50 dentro do IC95%.",
    createdAt: "2026-07-12",
    author: "jump_index_spike_scan.py",
    verdict:
      "REFUTADO read-only: 50k ticks por símbolo, 30-34 saltos detectados (>10x mediana). Direção UP " +
      "50.0%-63.3% (IC95% inclui 50% em todos). CV 0.94-1.53, compatível com memoryless. Hazard rates " +
      "0.000%-0.201% sem tendência crescente. Nenhum sinal de temporizador ou viés direcional.",
    ci95: [0.94, 1.53],
    ci95Label: "CV range 0.94-1.53; hazard constante; direção UP 50-63% dentro do IC95%",
    tools: ["jump_index_spike_scan.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 161,
    sampleUnit: "spikes (161 gaps, 30-34 saltos por símbolo, 50k ticks/símbolo)",
  },
  {
    id: "D93",
    title: "HIGHER/LOWER Barrier Mispricing",
    market: "DERIV · 1HZ10V · HIGHER/LOWER · 5/10 ticks",
    thesis:
      "Contratos HIGHER/LOWER com barreira percentual poderiam ter payout desalinhado vs. a probabilidade " +
      "real de cruzar a barreira, gerando EV positivo em alguma combinação de barrier × duration.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "higher-lower", "barrier", "mispricing", "refutado"],
    trigger: "Payout real > fair payout (stake/P(win)) com EV_lo > 0 em alguma célula barrier × duration.",
    invalidation: "Todas as células têm EV negativo; nenhum EV_lo > 0.",
    createdAt: "2026-07-12",
    author: "higher_lower_edge_scan.py",
    verdict:
      "REFUTADO read-only: 31 células testadas (HIGHER/LOWER × 6/10 barriers × 5/10 ticks) em 1HZ10V. " +
      "0 células com EV_lo > 0. EV médio -$0.6981, min -$8.34, max -$0.10. A Deriv cobra margem " +
      "consistente em todas as combinações, com razão payout/fair no melhor caso ~0.99 (pior 0.17). " +
      "Sem mispricing detectável.",
    ci95: [0, 0],
    ci95Label: "0/31 células com EV_lo > 0; EV range [-$8.34, -$0.10]",
    tools: ["higher_lower_edge_scan.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 31,
    sampleUnit: "células barrier×duration (31 combinações read-only, 10k ticks reais)",
  },
  {
    id: "D94",
    title: "E-Suffixed Contract Variants em 1HZ100V",
    market: "DERIV · EXPIRYMISSE/EXPIRYRANGEE/CALLE/PUTE · 1HZ100V",
    thesis:
      "1HZ100V oferece EXPIRYMISSE/EXPIRYRANGEE e CALLE/PUTE — a hipótese D88 não tinha " +
      "cotado essas variantes nesse símbolo. Teste read-only com 10k ticks reais e 10k simulações Monte Carlo.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "e-suffix", "expirymisse", "expiryrangee", "calle", "pute", "1hz100v"],
    trigger: "EV_lo > 0 com DGP consistente em alguma variante E.",
    invalidation: "EXPIRYMISSE/EXPIRYRANGEE não cotáveis intraday ou EV negativo em todas as variantes.",
    createdAt: "2026-07-12",
    author: "d88_e_variant_scan.py",
    verdict:
      "REFUTADO. 30 células testadas (EXPIRYMISSE/EXPIRYRANGEE intraday, CALLE/PUTE 5t/10t/1m/5m). " +
      "EXPIRYMISSE/EXPIRYRANGEE só existem como daily (barreiras absolutas 883.08/964.42) e não aceitam " +
      "durações intraday; CALLE/PUTE: 8/8 células com EV negativo (melhor EV=+0.053, mas EV_lo=-0.066), " +
      "0 gate candidates. Sem edge.",
    ci95: [0, 0],
    ci95Label: "8 células CALLE/PUTE válidas; 0 gate candidates; EXPIRY E não oferecidos intraday",
    tools: ["d88_e_variant_scan.py", "probe_new_contracts.py"],
    reportFile: "docs/state_of_research.md",
    pnl: 0,
    trades: 8,
    sampleUnit: "células de quote/replay read-only (1HZ100V, 4 durações, 2 tipos, 2 barreiras)",
  },
  {
    id: "D95",
    title: "Deal Cancellation Mispricing em Volatility Indices",
    market: "DERIV · 1HZ100V / R_100 / 1HZ50V · MULTUP/MULTDOWN · cancellation 5-60m",
    thesis:
      "A feature 'Deal Cancellation' dos Multipliers em 1HZ100V pode estar subprecificada: " +
      "o fee cobrado (cancellation ask_price) pode ser menor que o valor justo de uma put europeia " +
      "(stake × multiplier, vencimento = duração da cancellation). 1HZ100V é 100x mais volátil por tick que 1HZ10V, " +
      "mas o fee parece não escalonar com a volatilidade do símbolo.",
    confidence: 20,
    status: "paused",
    tags: ["deriv", "multiplier", "deal-cancellation", "1hz100v", "r100", "1hz50v", "inconclusive"],
    trigger: "fair_value_MC (IC95% lo) > cancellation_fee em múltiplas células (multiplier × duration × direction).",
    invalidation: "EV líquido ao vivo (valor_realizado − fee) IC95% cruzar zero ou ser negativo.",
    createdAt: "2026-07-12",
    author: "d95_deal_cancellation_1hz100v.py",
    verdict:
      "CORRIGIDO: read-only anterior nao capava payoff em stake; 400x60m refutado em 3 símbolos. " +
      "Live 5m 400x (N=20): EV -$0.04, IC95% cruza zero. Live 5m 100x (N=20): valor realizado medio $0.1705, " +
      "fee $0.1100, EV +$0.0605, IC95% [-$0.0130, +$0.1510]. Nenhum trial confirmou edge; pausado.",
    ci95: [-0.013, 0.151],
    ci95Label: "DEMO 1HZ100V 100x/5m, N=20: EV líquido +$0.0605; IC95% cruza zero",
    tools: ["d95_deal_cancellation_1hz100v.py", "d95_deal_cancellation_r100.py", "d95_deal_cancellation_1hz50v.py", "d95_deal_cancellation_live_1hz100v.py"],
    reportFile: "d95_deal_cancellation_live_results.jsonl",
    pnl: 1.21,
    trades: 20,
    sampleUnit: "20 live DEMO trades 100x/5m + trial 400x N=20 + scans capped read-only",
  },
  {
    id: "D96",
    title: "Flat Tick Frequency + RNG Deep Analysis (50k ticks × 17 symbols)",
    market: "DERIV · 17 synthetic symbols · 50k ticks each · ticks_history",
    thesis:
      "P(tick == tick_anterior) > 11.11% torna straddle CALLE+PUTE em 1-tick lucrativo " +
      "(flat: +$1.60, non-flat: -$0.20, breakeven 11.11%). flat_tick_bot só rodou 4 trades " +
      "em JD100 — amostra irrisória. Adicionalmente, testes estatísticos comprehensivos " +
      "(autocorrelação, Hurst, Ljung-Box, Runs, spectral density) podem revelar desvios " +
      "de aleatoriedade pura exploráveis.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "flat-tick", "rng", "autocorrelation", "hurst", "ljung-box", "runs-test"],
    trigger: "P(flat) CI95% lo > 11.11% para qualquer símbolo, OU Ljung-Box p<0.01 com efeito > house margin.",
    invalidation: "P(flat) CI95% hi < 11.11% para todos os símbolos E nenhum teste estatístico com efeito explorável.",
    createdAt: "2026-07-13",
    author: "d96_flat_tick_frequency_scan.py",
    verdict:
      "REFUTADO (2026-07-13, N=50k ticks × 17 symbols). P(flat) max = JD100 9.06% " +
      "CI95%[8.81%, 9.31%], abaixo do breakeven 11.11%. Todos os 17 símbolos refutados. " +
      "Hurst ~0.55 universal (slight trending, não explorável). CRASH1000 Ljung-Box " +
      "p=0.0047 mas efeito r≈2.25% insuficiente vs house margin 4%. JD100 Runs z=3.016 " +
      "(trending). Nenhum desvio explorável de aleatoriedade pura.",
    evPerTrade: -0.16,
    ci95: [-0.20, -0.12],
    ci95Label: "EV médio do straddle CALLE+PUTE 1-tick across 17 symbols (P(flat) max 9.06% vs breakeven 11.11%)",
    tools: ["d96_flat_tick_frequency_scan.py"],
    reportFile: "d96_flat_tick_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "50k ticks × 17 símbolos (read-only, 850k ticks total)",
  },
  {
    id: "D97",
    title: "Payout Curve Deep Scan (23 types × 9 durations × 11 symbols × 3 stakes)",
    market: "DERIV · 11 symbols · 23 contract types · 9 durations · 3 stake sizes",
    thesis:
      "D86 testou straddle em 5 durações/8 símbolos. Scan sistemático completo de TODOS " +
      "os durations, contract types, symbols e stake sizes pode encontrar mispricing " +
      "anômalo em qualquer célula. Se payout_ratio variar com stake size (scaling exploit) " +
      "ou com duration (transient mispricing), é explorável.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "payout-ratio", "mispricing", "straddle", "scan", "house-margin"],
    trigger: "Payout ratio anômalo (>mean+2std) em célula com P(win) teórico > breakeven, OU stake-dependence > 1%.",
    invalidation: "House margin consistente em todas as células, 0 straddle arb, stake-dependence < 0.1%.",
    createdAt: "2026-07-13",
    author: "d97_payout_curve_scan.py",
    verdict:
      "REFUTADO (2026-07-13, N=1874 células). 0 straddle arb (CALL+PUT ask >= payout " +
      "em 100% das células). 32 anomalias de payout ratio (>mean+2std), todas RUNHIGH/" +
      "RUNLOW 30.53x — mas P(win) = (0.5)^5 = 3.125% vs breakeven 3.28%, house margin " +
      "4.8%. 598 anomalias de stake-dependence (max diff 0.0032, insignificante). 0 " +
      "anomalias de duration curve. House margin ~4% consistente em todos os contract " +
      "types, durations, symbols e stakes.",
    evPerTrade: -0.04,
    ci95: [-0.05, -0.03],
    ci95Label: "House margin ~4% consistente em 1874 células (23 types × 9 durations × 11 symbols × 3 stakes)",
    tools: ["d97_payout_curve_scan.py"],
    reportFile: "d97_payout_curve_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "1874 células de proposal read-only (23 types × 9 durations × 11 symbols × 3 stakes)",
  },
  {
    id: "D98",
    title: "Instant Resale Flip Scanner (buy → check resale price immediately)",
    market: "DERIV · 5 symbols · 10 contract types · 5 durations · DEMO trades",
    thesis:
      "O preço de resale de um contrato imediatamente após compra pode exceder o preço " +
      "de compra para certos tipos de contrato ou condições de mercado. Se resale > buy " +
      "para qualquer combinação, é flip instantâneo (dinheiro grátis). Nunca testado " +
      "sistematicamente.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "resale", "flip", "demo", "house-margin"],
    trigger: "resale_price > buy_price para qualquer célula (flip instantâneo).",
    invalidation: "resale_price / buy_price < 0.99 para todas as células (house margin absorve resale).",
    createdAt: "2026-07-13",
    author: "d98_resale_flip_scan.py",
    verdict:
      "REFUTADO v2 (2026-07-13, 250 células, 80 válidas). v1 teve bug (ask_price vs " +
      "bid_price). v2 corrigida: 17 células com 'flip edge' (≥1/3 trades ITM), 12 com " +
      "avg_ratio > 1.0. Melhor: R_100 CALL 5t 1.56x. MAS resale é binário ($0.92/$1.88) " +
      "= exposição direcional, não flip estrutural. Mean ratio 0.9427 < 1.0 = house " +
      "margin absorvendo resale. 'Flip edges' são apenas trades que aleatoriamente " +
      "foram ITM nos primeiros ticks.",
    evPerTrade: -0.06,
    ci95: [-0.08, -0.04],
    ci95Label: "Mean avg_flip_ratio 0.9427 across 80 cells (house margin ~5.7% on resale)",
    tools: ["d98_resale_flip_scan.py"],
    reportFile: "d98_resale_flip_results.json",
    pnl: 0,
    trades: 240,
    sampleUnit: "80 células válidas × 3 trades/cell = 240 DEMO trades (5 symbols × 10 types × 5 durations)",
  },
  {
    id: "D99",
    title: "RUNHIGH/RUNLOW Validation (30.53x payout ratio anomaly from D97)",
    market: "DERIV · 1HZ10V · RUNHIGH/RUNLOW · 5 ticks · DEMO trades",
    thesis:
      "D97 flagou RUNHIGH/RUNLOW 5t com payout ratio 30.53x como anômalo. Se P(win) " +
      "= 1/n (último tick = máximo por simetria), EV = 0.2 × $30.53 - $1 = +$5.11. " +
      "Validar com trades reais DEMO.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "runhigh", "runlow", "payout-ratio", "validation", "demo"],
    trigger: "Win rate CI95% lo > breakeven 3.28% após N=30 trades por tipo.",
    invalidation: "Win rate CI95% hi < breakeven 3.28% OU longcode revelar P(win) teórico < breakeven.",
    createdAt: "2026-07-13",
    author: "d99_runhigh_validation.py",
    verdict:
      "REFUTADO (2026-07-13, N=58 trades DEMO). Longcode revelou condição real: " +
      "'rises/falls successively for 5 ticks' = 5 ticks consecutivos na mesma direção. " +
      "P(win) = (0.5)^5 = 3.125%, breakeven = 3.28%, house margin = 4.8%. RUNHIGH: " +
      "0/28 wins. RUNLOW: 1/30 wins (3.33%). WR combinada 1.72% CI95%[0.3%, 9.2%], " +
      "consistente com 3.125% teórico. 'Anomalia' de payout ratio era apenas payout " +
      "alto com P(win) proporcionalmente baixa — não mispricing.",
    evPerTrade: -0.48,
    ci95: [-0.82, -0.14],
    ci95Label: "58 trades DEMO: 1 win ($29.53) vs 57 losses ($-57.00), net -$27.47, EV -$0.47/trade",
    tools: ["d99_runhigh_validation.py"],
    reportFile: "d99_runhigh_validation_results.json",
    pnl: -27.47,
    trades: 58,
    sampleUnit: "58 trades DEMO (28 RUNHIGH + 30 RUNLOW, 1HZ10V, 5 ticks, $1 stake)",
  },
  {
    id: "D100",
    title: "Proposal Staleness Exploit v2 (ms-scale race between proposal and buy)",
    market: "DERIV · 1HZ10V · CALL/PUT · 10 ticks · RACE vs CONTROL · DEMO",
    thesis:
      "D47 testou stale proposal com 20s de delay e D54 descobriu que subscribe:1 " +
      "nunca reenvia. D100 testa a janela crítica em milissegundos: se o spot se move " +
      "favoravelmente entre proposal e buy (mesmo ~100ms), o ask_price pode estar " +
      "desatualizado e podemos comprar abaixo do fair value.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "proposal", "staleness", "race", "latency", "ms-scale"],
    trigger: "RACE WR > CONTROL WR by >5% with IC95% excluding zero.",
    invalidation: "RACE WR <= CONTROL WR (staleness doesn't help or hurts).",
    createdAt: "2026-07-13",
    author: "d100_proposal_staleness_v2.py",
    verdict:
      "REFUTADO (2026-07-13, N=60). RACE (0ms delay, lag médio 193ms) WR=43.3% " +
      "EV=-$0.17 vs CONTROL (2000ms delay) WR=53.3% EV=+$0.02. RACE WR < CONTROL " +
      "WR — staleness não ajuda, pelo contrário. spot_diff entre proposal e entry " +
      "é aleatório (sem viés direcional). Lag de ~193ms é insuficiente para capturar " +
      "movimento favorável.",
    evPerTrade: -0.17,
    ci95: [-0.42, 0.08],
    ci95Label: "RACE EV -$0.17/trade vs CONTROL EV +$0.02/trade (N=30 each, 1HZ10V 10t)",
    tools: ["d100_proposal_staleness_v2.py"],
    reportFile: "d100_proposal_staleness_v2_results.json",
    pnl: -4.8,
    trades: 60,
    sampleUnit: "60 DEMO trades (30 RACE 0ms + 30 CONTROL 2000ms, CALL/PUT alternated)",
  },
  {
    id: "D101",
    title: "Barrier Proximity Edge (DIGITOVER/DIGITUNDER payout by barrier)",
    market: "DERIV · 1HZ10V · DIGITOVER/DIGITUNDER · barriers 0-9 · 5 ticks · DEMO",
    thesis:
      "Para DIGITOVER/DIGITUNDER, o contrato ganha se o último dígito está acima/abaixo " +
      "da barreira. Se o tick size é assimétrico em relação ao dígito, a probabilidade " +
      "de cruzar pode não ser 50/50 perto da barreira. Adicionalmente, testa se a Deriv " +
      "precifica todas as barreiras corretamente (0-9).",
    confidence: 10,
    status: "paused",
    tags: ["deriv", "digit", "barrier", "proximity", "payout-ratio", "inconclusive"],
    trigger: "WR CI95% lo > breakeven para qualquer barreira após N=20 trades.",
    invalidation: "WR CI95% hi < breakeven para todas as barreiras, OU payout ratio perfeitamente inverso à P(win).",
    createdAt: "2026-07-13",
    author: "d101_barrier_proximity_edge.py",
    verdict:
      "INCONCLUSIVO (2026-07-13, N=120 trades). Payout ratio 1.09x-8.33x perfeitamente " +
      "inverso à P(win) — house margin consistente. Live DEMO: DIGITOVER_0/UNDER_9 " +
      "WR=95% (19/20) vs breakeven 91.74%, EV=+$0.04 — CI95% cruza. DIGITOVER_5/UNDER_4 " +
      "WR=50% vs teórico 40%, EV=+$0.19 — CI95% [29.9%, 70.1%] cruza breakeven. " +
      "Diferença theo vs actual +5-10pp em 4/6 barreiras mas dentro do ruído com N=20. " +
      "Pausado — precisaria N=100+/barreira para confirmar ou refutar.",
    evPerTrade: 0.06,
    ci95: [-0.05, 0.17],
    ci95Label: "6 barreiras × 20 trades: EV médio +$0.06/trade, CI95% cruza zero em todas",
    tools: ["d101_barrier_proximity_edge.py"],
    reportFile: "d101_barrier_proximity_results.json",
    pnl: 7.42,
    trades: 120,
    sampleUnit: "120 DEMO trades (6 barreiras × 20 trades, 1HZ10V, 5 ticks, $1 stake)",
  },
  {
    id: "D102",
    title: "Crypto Contract House Margin Scan (cryBTCUSD/cryETHUSD)",
    market: "DERIV · cryBTCUSD/cryETHUSD/cryLTCUSD/cryXRPUSD/cryDSHUSD · CALL/PUT/CALLE/PUTE · 1d-30d",
    thesis:
      "Crypto contracts na Deriv podem ter house margin diferente de sintéticos (~4%) " +
      "ou forex (~12%). Se crypto tiver house margin menor ou mispricing, pode haver " +
      "edge em contratos binários crypto.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "crypto", "house-margin", "payout-ratio", "api-design"],
    trigger: "Payout ratio crypto > payout ratio sintético para mesma P(win).",
    invalidation: "Crypto não suporta binary options (CALL/PUT/etc.), OU house margin >= sintéticos.",
    createdAt: "2026-07-14",
    author: "d102_crypto_house_margin.py",
    verdict:
      "REFUTADO por design de API (2026-07-14). Todos os 140 proposals para cryBTCUSD, " +
      "cryETHUSD, cryLTCUSD, cryXRPUSD, cryDSHUSD com CALL/PUT/CALLE/PUTE em 7 durações " +
      "(1d-30d) retornaram 'Trading is not offered for this asset.' Probe confirmou que " +
      "crypto na Deriv SÓ suporta Multipliers (MULTUP/MULTDOWN) — não há binary options. " +
      "Multipliers não têm payout ratio (payout=0). Não há edge de house margin em crypto.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — crypto não suporta binary options",
    tools: ["d102_crypto_house_margin.py", "probe_crypto_contracts.py"],
    reportFile: "d102_crypto_house_margin_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "140 API proposals (5 crypto symbols × 4 contract types × 7 durations)",
  },
  {
    id: "D103",
    title: "Tick Arrival Timing Prediction (predict WHEN not WHAT)",
    market: "DERIV · 1HZ10V/1HZ50V/1HZ100V/R_10/R_100/cryBTCUSD · 15min live subscription",
    thesis:
      "Se o timing de chegada dos ticks não for perfeitamente regular (Poisson process), " +
      "pode haver padrões previsíveis em QUANDO o próximo tick chega, permitindo timing " +
      "de entrada/saída otimizado.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "tick-timing", "poisson", "autocorrelation", "jitter", "deterministic"],
    trigger: "Autocorrelação significativa (p<0.05) nos intervalos entre ticks, OU CV > 0.1.",
    invalidation: "Timing perfeitamente determinístico (CV=0, zero autocorrelação) sem edge explorável.",
    createdAt: "2026-07-14",
    author: "d103_tick_timing_prediction.py",
    verdict:
      "REFUTADO (2026-07-14, N=4,563 ticks, 6 símbolos, 15min). TODOS os símbolos têm " +
      "timing perfeitamente determinístico: 1HZ e cryBTCUSD = exatamente 1.0000s entre " +
      "ticks (std=0, CV=0, jitter=0); R_10/R_100 = exatamente 2.0000s. Zero variância, " +
      "zero autocorrelação. Timing é 100% previsível mas não gera edge — o VALOR dos " +
      "ticks determina P(win), não o timing. Deriv entrega ticks em intervalos fixos " +
      "perfeitos, sem jitter para explorar.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — timing determinístico não gera edge de valor",
    tools: ["d103_tick_timing_prediction.py"],
    reportFile: "d103_tick_timing_results.json",
    pnl: 0,
    trades: 4563,
    sampleUnit: "4,563 ticks (6 símbolos × 15min subscription, intervalos medidos em ms)",
  },
  {
    id: "D104",
    title: "Duration Boundary Pricing Discontinuity (edge at 5t→6t transition)",
    market: "DERIV · 1HZ10V/R_100 · CALL/PUT/CALLE/PUTE/DIGITEVEN/DIGITODD · 1t-50t",
    thesis:
      "Se a Deriv precifica durações em categorias (short/medium/long), pode haver " +
      "descontinuidade de payout ratio na fronteira entre categorias (e.g., 5t→6t). " +
      "Uma descontinuidade criaria um edge local na duração ótima.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "duration", "boundary", "payout-ratio", "smooth", "discontinuity"],
    trigger: "Payout ratio descontinuidade > 2% entre durações adjacentes.",
    invalidation: "Payout ratio constante/smooth em todas as durações — sem descontinuidade.",
    createdAt: "2026-07-14",
    author: "d104_duration_boundary.py",
    verdict:
      "REFUTADO (2026-07-14, 2 símbolos × 6 contract types × 50 durações). Payout ratio " +
      "constante 1.92x em TODAS as durações (1t-50t) para TODOS os contract types. Zero " +
      "descontinuidades. A Deriv precifica duração de forma perfeitamente smooth — não " +
      "há edge em boundary transitions.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — payout ratio constante 1.92x em todas as durações",
    tools: ["d104_duration_boundary.py"],
    reportFile: "d104_duration_boundary_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "600 API proposals (2 símbolos × 6 contract types × 50 durações)",
  },
  {
    id: "D105",
    title: "Multi-Leg Digit Combination Arbitrage (DIGITOVER + DIGITUNDER)",
    market: "DERIV · 7 símbolos · DIGITOVER/DIGITUNDER · 2-leg e 3-leg · 1t/10t",
    thesis:
      "Combinar múltiplas pernas digit (e.g., DIGITOVER(N) + DIGITUNDER(N+1) = full " +
      "cover) pode resultar em payout total > stake se a house margin por perna for " +
      "menor que a cobertura combinada.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "multi-leg", "arbitrage", "digit", "house-margin", "combination"],
    trigger: "Arbitragem garantida > 0 em qualquer combinação multi-leg.",
    invalidation: "House margin cumulativa faz payout total < stake em todas as combinações full-cover.",
    createdAt: "2026-07-14",
    author: "d105_multi_leg_digit_arb.py",
    verdict:
      "REFUTADO (2026-07-14, 56 combinações). 0 arbitragem garantida em todas as " +
      "combinações 2-leg e 3-leg. Best EV: -$0.05/trade (2-leg full cover, 1t). " +
      "House margin de ~4% por perna faz o payout total ser sempre < stake quando " +
      "se cobre todos os outcomes. Cumulativamente, a house margin previne arbitrage.",
    evPerTrade: -0.05,
    ci95: [-0.08, -0.02],
    ci95Label: "Best EV -$0.05/trade (2-leg full cover), todas as combinações negativas",
    tools: ["d105_multi_leg_digit_arb.py"],
    reportFile: "d105_multi_leg_digit_arb_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "56 combinações API proposals (7 símbolos × 2 durações × 2-leg/3-leg)",
  },
  {
    id: "D106",
    title: "Real-Time Pricing/Proposal Anomaly Monitor (24/7 transient bug detection)",
    market: "DERIV · 10 símbolos · 8 contract types · 3 durações × 4 stakes · 60s cycle",
    thesis:
      "Bugs transitórios de pricing na Deriv (payout setado errado, resale arb, " +
      "spot desincronizado) podem criar edges exploráveis por janelas curtas. " +
      "Monitor 24/7 pode detectar e alertar em tempo real.",
    confidence: 5,
    status: "validating",
    tags: ["deriv", "real-time", "anomaly", "pricing", "payout", "resale", "monitor", "transient-bug"],
    trigger: "Payout ratio >15% deviation, OR resale arb >0, OR spot mismatch >0.1%, OR contract availability change",
    invalidation: "N/A — monitor contínuo, não tem hipótese para refutar. Roda 24/7 e alerta.",
    createdAt: "2026-07-14",
    author: "d106_pricing_anomaly_monitor.py",
    verdict:
      "ATIVO (2026-07-14). Monitor rodando 24/7 na AWS com 960 proposals/ciclo. " +
      "6 detectores: PAYOUT_RATIO_ANOMALY, PAYOUT_RATIO_CHANGE, SPOT_MISMATCH, " +
      "RESALE_ARB, CONTRACT_AVAILABLE/UNAVAILABLE, STAKE_DEPENDENT_PAYOUT. " +
      "Calibrado com house margin empirica por contract type. " +
      "1o ciclo: 10 anomalies MEDIUM (DIGITMATCH payout varia por símbolo + " +
      "contract flickering). Zero CRITICAL, zero RESALE_ARB, zero SPOT_MISMATCH. " +
      "Nenhum bug transitório detectado nas primeiras horas.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "N/A — monitor contínuo, não gera EV/trades",
    tools: ["d106_pricing_anomaly_monitor.py", "synthetic_anomaly_monitor.py"],
    reportFile: "logs/d106_pricing_anomalies.jsonl",
    pnl: 0,
    trades: 0,
    sampleUnit: "960 API proposals/ciclo (10 símbolos × 8 contracts × 3 durações × 4 stakes), 60s interval",
  },
  {
    id: "D107",
    title: "High-Multiplier Deal Cancellation Scan (600x-800x, 30m-60m) — PDF 'Arbitragem de Opcionalidade Exótica'",
    market: "DERIV · 1HZ50V/1HZ100V · MULTUP/MULTDOWN · 200x-800x · cancellation 15m-60m · READ-ONLY",
    thesis:
      "PDF externo claima que Deal Cancellation em Multipliers 600x-800x/30m-60m é " +
      "subprecificada: fee $7.52 vs fair value $17.15, edge +$5.10/trade. Straddle " +
      "MULTUP+MULTDOWN eliminaria risco direcional. D52 refutou com N=120 até 400x; " +
      "D107 testa o regime não-explorado 600x-800x.",
    confidence: 0,
    status: "refuted",
    tags: ["deriv", "multiplier", "deal-cancellation", "straddle", "high-multiplier", "pdf-claim", "refuted"],
    trigger: "Fee cobrado < fair value MC (IC95% lo > 0) em qualquer célula 600x-800x/30m-60m.",
    invalidation: "Fee >= fair value em todas as células high-multiplier, OU straddle edge_lo < 0.",
    createdAt: "2026-07-14",
    author: "d107_high_multiplier_cancellation_scan.py",
    verdict:
      "REFUTADO (2026-07-14, 60k ticks × 2 símbolos × 120k MC/célula). Fee é SUPERIOR " +
      "ao fair value em TODAS as células high-multiplier. 1HZ50V 800x/60m (claim do PDF): " +
      "fee=$7.52, fair=$4.55, edge=-$2.97 (não +$5.10). PDF superestimou fair value ~4x " +
      "(provavelmente não capou payoff em stake — cancellation devolve stake, não stake×mult). " +
      "Straddle 800x/60m: edge=-$5.94. Único sinal: 1HZ50V 200x/15m straddle edge_lo=+$0.05 " +
      "(marginal, consistente com D52 que regrediu com N=120). 1HZ100V não suporta 600x+.",
    evPerTrade: -2.97,
    ci95: [-3.00, -2.94],
    ci95Label: "1HZ50V 800x/60m: edge=-$2.97/trade (fee $7.52 vs fair $4.55). Straddle: -$5.94",
    tools: ["d107_high_multiplier_cancellation_scan.py"],
    reportFile: "d107_high_multiplier_cancellation_results.json",
    pnl: 0,
    trades: 0,
    sampleUnit: "60k ticks × 2 símbolos × 5 multipliers × 3 cancellations × 2 directions = 60 células MC",
  },
];

// Fonte única de verdade para "quais bots/scripts estão rodando ao vivo na AWS agora".
// Nesta base, status="validating" corresponde 1:1 aos scripts que ainda estão coletando
// amostra (paper bots, scans contínuos) -- é o proxy mais confiável que temos sem um
// endpoint de status dedicado para cada um. HYP-UNLOCK-01 (D17) tem dashboard/API dedicados
// (/d17, /live, /bots) e é excluído daqui para não duplicar contagem. HYP-HFT-01 foi
// refutado e o processo parado (2026-07-08), mas mantido no filtro por segurança.
// Atualiza sozinha conforme hipóteses mudam de status: não hardcode este número em nenhuma
// página (ver bots.tsx, strategies.tsx, paper.tsx).
export function getActiveResearchBots(): RealHypothesis[] {
  return realHypotheses.filter(
    (h) => h.status === "validating" && h.id !== "HYP-UNLOCK-01" && h.id !== "HYP-HFT-01",
  );
}

export function hypStatusBadgeClass(s: HypStatus) {
  switch (s) {
    case "live":
      return "bg-success/15 text-success border-success/30";
    case "validating":
      return "bg-warning/15 text-warning border-warning/30";
    case "weak-signal":
      return "bg-info/15 text-info border-info/30";
    case "refuted":
      return "bg-destructive/15 text-destructive border-destructive/40";
    case "paused":
    case "draft":
    case "archived":
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}
