// Catálogo REAL de hipóteses testadas no ecossistema Mega Brain (Deriv).
// Fonte de verdade: docs/*.md no repo `hypothesis`. Cada entrada aqui corresponde a um
// relatório real com script(s) executado(s) e veredito fechado — nada aqui é simulado.
// Atualize manualmente quando uma nova hipótese for testada ou um veredito mudar
// (ex.: shadow A/B do hft_bot acumular N suficiente para fechar veredito).

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
    pnl: -120.66,
    trades: 40,
    sampleUnit: "trades reais (conta demo)",
    verdict:
      "Refutado — 40 trades reais (conta demo), EV/trade -$3.02, IC95% [-$4.70, -$1.18] (não cruza zero). " +
      "WR 22.5% (9/40). V6.2 com golden-hour filter produziu zero trades em 33h+ (threshold muito restritivo). " +
      "Consistente com H3: gargalo é a perna de execução da Deriv (~180-220ms), não a qualidade do sinal.",
    evPerTrade: -3.02,
    ci95: [-4.7, -1.18],
    ci95Label: "EV/trade (bootstrap)",
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
    market: "1HZ10V · CALL 15m",
    thesis:
      "A capacidade de vender antes do expiry a bid_price poderia ter valor de optionality (vender quando ITM antes de reverter) que excede o custo do spread bid/ask embutido.",
    confidence: 45,
    status: "validating",
    tags: ["early-sell", "optionality", "bid-price", "mega-brain-2", "edge-preliminar"],
    trigger: "Comprar CALL 15m, monitorar bid_price durante vida do contrato, comparar sell no melhor bid vs hold-to-expiry",
    invalidation: "IC95% da diferença sell_profit - hold_profit cruzar zero (non-hindsight, regra predefinida)",
    createdAt: "2026-07-03",
    author: "early_sell_test.py",
    pnl: 89.54,
    trades: 20,
    sampleUnit: "trials reais (20/20 completos, 15m cada) — confirmação com 50 trials em andamento",
    verdict:
      "EDGE PRELIMINAR (N=20) — Sell WR 75%, EV +$4.48/trade. Hold WR 50%, EV -$0.39/trade. " +
      "Diferença +$4.86/trade, IC95% [+$1.94, +$7.82] NÃO cruza zero. " +
      "Regra non-hindsight (thresh=$13): EV_sell +$3.84 vs EV_hold +$0.49. " +
      "Confirmação com 50 trials em andamento na EC2. N=20 ainda é pequeno — aguardar N≥50 para veredito final.",
    tools: ["early_sell_test.py", "probe_sellable.py"],
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
    tags: ["event-driven", "token-unlock", "vesting", "supply-pressure", "short", "binance", "significant", "oos-validated", "costs-tested", "timing-optimized", "2026-validated"],
    trigger: "Known token unlock date → short 3d before, exit 3d after. Filter: unlock value ≥$200M or ≥5% supply",
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
      "Large unlocks (≥$200M): 7/7 negativos. OPUSDT OOS-2025: 6/6 wins.",
    tools: ["token_unlock_scan.py", "shorting_cost_scan.py", "timing_optimization_scan.py"],
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
    id: "HYP-JUMP-01",
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
      "DTE curto (1d) negativo — fees dominam. Edge cresce com DTE (mais tempo para RV > IV).",
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
    id: "HYP-BASIS-01",
    title: "D29 — Basis-Funding Disconnect (Binance carry trade)",
    market: "BINANCE FUTURES · Top 30 USDT perps · spot + perp carry",
    thesis:
      "Quando perp > spot (contango) E funding negativo, long perp é carry trade grátis: " +
      "ganha basis convergence + recebe funding. Quando perp < spot E funding positivo, " +
      "short perp é carry grátis. O 'disconnect' é quando ambos componentes favorevem o mesmo lado. " +
      "Scan: 19 pares analisados, roundtrip fees 0.14% (spot 0.1% + futures 0.04%).",
    confidence: 4,
    status: "weak-signal",
    tags: ["binance", "futures", "funding-rate", "basis", "carry-trade", "arbitrage"],
    trigger: "Basis > 0 E funding < 0 (long carry) ou basis < 0 E funding > 0 (short carry). " +
      "Profit per 8h = |basis%| + funding% - 0.14% fees > 0.",
    invalidation: "Apenas 2 disconnects profitable após fees em 19 pares. " +
      "ARPAUSDT: +0.28%/8h (backwardation + pos funding). SYNUSDT: +0.01%/8h (marginal). " +
      "Funding rate muda a cada período — não é garantido.",
    createdAt: "2026-07-05",
    author: "basis_funding_disconnect_scan.py",
    verdict:
      "SINAL FRACO. 2/19 pares com disconnect profitable após fees. " +
      "ARPAUSDT: basis -0.41% + funding +0.01%/8h = +0.28% net per 8h (annualized ~+307%). " +
      "SYNUSDT: +0.01%/8h (marginal). 12 SHORT disconnects vs 1 LONG — mercado em backwardation geral. " +
      "CUIDADO: funding rate varia a cada 8h, basis converge mas timing é incerto. " +
      "Annualized carry IC95%: [-107%, +472%] — alta incerteza, poucos pontos.",
    evPerTrade: 0.15,
    ci95: [-0.14, 0.29],
    ci95Label: "Profit per 8h (%) for 2 profitable disconnects, net of 0.14% fees",
    tools: ["basis_funding_disconnect_scan.py"],
    reportFile: "basis_funding_disconnect_scan.log",
    pnl: 0,
    trades: 19,
    sampleUnit: "pares spot+perp analisados",
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
      "PRÓXIMO PASSO: paper trade em expiries reais — monitorar options market prices nos últimos 30min antes de settlement.",
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
    id: "HYP-LIQ-01",
    title: "D34 — Liquidation Cascade Detection & Front-Run",
    market: "BINANCE FUTURES · BTC/ETH/SOL · 2s polling · 30min",
    thesis:
      "Liquidações em cascata: 3+ liquidations em 10s mesma direção = cascade. " +
      "Se longs sendo liquidados, preço continua caindo → short e ride cascade. " +
      "Scan: monitora liquidations em tempo real, detecta cascades, simula P&L a 30s/60s/120s/300s hold. " +
      "Net após 0.1% taker fee por lado.",
    confidence: 25,
    status: "validating",
    tags: ["crypto", "liquidation", "cascade", "futures", "aggressive", "front-run"],
    trigger: "Cascade continuation WR > 60% após fees com N > 5",
    invalidation: "Cascades são raras ou não continuam após detecção + fees",
    createdAt: "2026-07-04",
    author: "liquidation_cascade_scan.py",
    verdict:
      "EM TESTE CONTÍNUO na AWS. Primeiro scan de 30min: 0 liquidations detectadas (mercado calmo). " +
      "Bot reiniciado em loop infinito (30min scan + 60s pause + repeat) para capturar eventos " +
      "ao longo de dias. Cascades são eventos raros — precisam volatilidade alta (crash/pump). " +
      "Quando detectar: cascade continuation é o edge mais agressivo possível (front-run forced selling). " +
      "Monitorar liquidation_cascade_scan.log na AWS para eventos.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "0 cascades em 30min. Bot rodando em loop contínuo na AWS.",
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
    confidence: 50,
    status: "validating",
    tags: ["crypto", "options", "deribit", "iv-surface", "mispricing", "aggressive"],
    trigger: "|IV - fair_IV| > 3 vol points com bid≥0.001, OI≥50, spread<50%",
    invalidation: "Anomalias são stale quotes ou desaparecem em re-scan",
    createdAt: "2026-07-04",
    author: "iv_surface_anomaly_scan.py + iv_anomaly_paper_bot.py + iv_anomaly_reversion_test.py",
    verdict:
      "ANOMALIAS REAIS CONFIRMADAS — IV REVERTENDO! Reversion test: 6/6 posições " +
      "mostrando IV convergindo toward fair value (0 stale, 0 widened). " +
      "BTC-31JUL26-82000-P: dev +3.7→+2.0 (reverting). " +
      "ETH-10JUL26-1300-C: dev +44.2→+39.1 (reverting). " +
      "ETH-25SEP26-1300-C: dev -44.1→-11.4 (strong reversion, fair IV ajustou de 106→73). " +
      "Paper bot ativo na AWS escaneando hourly. Settle quando dev < 1 vol point. " +
      "PRÓXIMO: aguardar settles para medir P&L real da reversion. " +
      "Se reversion confirmar profitável após fees (0.03% Deribit), este é o " +
      "PRIMEIRO EDGE estrutural do projeto em opções crypto.",
    evPerTrade: 0,
    ci95: [0, 0],
    ci95Label: "6/6 anomalias reverting (0 stale). Aguardando settles para P&L real.",
    tools: ["iv_surface_anomaly_scan.py", "iv_anomaly_paper_bot.py", "iv_anomaly_reversion_test.py"],
    reportFile: "iv_anomaly_reversion_test_results.json",
    pnl: 0,
    trades: 6,
    sampleUnit: "paper positions (6/6 reverting, scan hourly na AWS)",
  },
];

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
