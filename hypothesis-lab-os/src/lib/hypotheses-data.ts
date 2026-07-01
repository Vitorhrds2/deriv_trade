// Catálogo REAL de hipóteses testadas no ecossistema Mega Brain (Deriv).
// Fonte de verdade: docs/*.md no repo `hypothesis`. Cada entrada aqui corresponde a um
// relatório real com script(s) executado(s) e veredito fechado — nada aqui é simulado.
// Atualize manualmente quando uma nova hipótese for testada ou um veredito mudar
// (ex.: shadow A/B do hft_bot acumular N suficiente para fechar veredito).

export type HypStatus = "live" | "validating" | "refuted" | "draft" | "paused" | "archived";

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
    confidence: 20,
    status: "validating",
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
      "Provisoriamente refutado — EV/trade IC95% [-$4.70, -$1.18] (não cruza zero). Config mais recente (V6.2, N=10) é a pior da série (10% WR). Consistente com H3: gargalo é a perna de execução da ordem na Deriv (~180-220ms), não a qualidade do sinal. Shadow A/B (ALIGNED vs ANTI) ativado ao vivo em 2026-07-01 para isolar sinal de execução — amostra ainda insuficiente (0 trades ANTI até o deploy).",
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
    confidence: 4,
    status: "refuted",
    tags: ["vanilla", "opcoes", "mispricing", "mega-brain-2"],
    trigger: "CALL/PUT × 5 strikes × 2 durações (15m, 60m)",
    invalidation: "IC95% do EV simulado cruzar zero em qualquer strike/duração",
    createdAt: "2026-07-01",
    author: "vanilla_edge_scan.py",
    pnl: 0,
    trades: 17,
    sampleUnit: "células testadas (20k caminhos Monte Carlo cada)",
    verdict:
      "Refutado — EV médio -8.98% em 17/20 células (CALL/PUT × strikes × durações), nenhuma com IC95% cruzando zero (min -19.48%, max -2.85%). Margem monotônica e coerente com precificação padrão: mais OTM = mais margem.",
    evPerTrade: -0.0898,
    ci95: [-19.48, -2.85],
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
    confidence: 3,
    status: "refuted",
    tags: ["boom-crash", "timing", "memoria", "weibull", "mega-brain-2"],
    trigger: "Spike detectado via |retorno| > 8x mediana na direção do índice",
    invalidation: "Weibull shape k > 1 (hazard crescente) replicado de forma independente",
    createdAt: "2026-07-01",
    author: "boom_timing_test.py",
    pnl: 0,
    trades: 177,
    sampleUnit: "gaps normalizados (6 símbolos, pool multi-símbolo)",
    verdict:
      "Refutado, replicado 2x de forma independente — Weibull k=1.000 IC95%[0.898,1.129] (coleta fresca, N=177) e k=1.024 IC95%[0.935,1.134] (dataset antigo, N=208). Ambos consistentes com processo memoryless; KS não rejeita exponencial em nenhuma coleta.",
    ci95: [0.898, 1.129],
    ci95Label: "Weibull shape k (1.0 = memoryless)",
    tools: ["boom_timing_test.py", "boom_memory_test.py"],
    reportFile: "docs/t2_boom_crash_spike_timing_report.md",
  },
];

export function hypStatusBadgeClass(s: HypStatus) {
  switch (s) {
    case "live":
      return "bg-success/15 text-success border-success/30";
    case "validating":
      return "bg-warning/15 text-warning border-warning/30";
    case "refuted":
      return "bg-destructive/15 text-destructive border-destructive/40";
    case "paused":
    case "draft":
    case "archived":
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}
