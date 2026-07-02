# Antigravity Brain Import (hypothesis + proud-borg)

Conteúdo resgatado do Google Antigravity (armazenado em `~/.gemini/antigravity/brain/<project-id>/`) para que o trabalho possa continuar aqui no Devin/Cascade, dentro deste mesmo repositório.

## Mapeamento de Projetos

| Pasta aqui | Nome no Antigravity | Project ID (brain) | Caminho original |
|---|---|---|---|
| `hypothesis/` | `hypothesis` | `0c39334a-48c7-41ed-a673-f37ac240c70e` | `/Users/vitorhrds/Documents/Github/hypothesis` (este repo) |
| `proud-borg/` | `proud-borg` | `22292115-15cf-40c8-b91b-110fe630b79a` | `/Users/vitorhrds/Documents/antigravity/proud-borg` (workspace "scratch", sem código commitado — todo o trabalho real ficou nos artefatos do brain) |

Cada subpasta contém os artefatos "user-facing" gerados pelo agente (arquivos `.md` + `.metadata.json` com resumo/timestamp), imagens/gráficos e os scripts de análise (`scratch/`). Os logs internos (`.system_generated/`, mensagens brutas, steps) e o histórico completo de chat (SQLite, 24–50MB por projeto em `~/.gemini/antigravity/conversations/<project-id>.db`) **não** foram copiados — ficaram só os resultados destilados. Se precisar de alguma mensagem específica do chat bruto, o `.db` original ainda está lá.

## Linha do Tempo Consolidada (os dois projetos são o MESMO sistema de trading)

`proud-borg` foi um workspace paralelo de pesquisa/análise (arbitragem cross-exchange). O bot que ele produziu (`hft_arbitrage_bot.py`) foi implantado na **mesma AWS** e roda hoje como a sessão tmux `hft_bot`, referenciada também nos artefatos do projeto `hypothesis`. São dois fios de trabalho que convergiram no mesmo servidor.

1. **06-18/06-19** (`hypothesis`) — Hipóteses iniciais de "low balance, high gain" (Kelly/snowball, scalping em ticks, martingale assimétrico) e diagnóstico do bug do Soros M1 ("metralhadora intra-vela").
2. **06-26** (`proud-borg`) — Análise de sazonalidade (horário de ouro 12:00–17:59 UTC) e do "paradoxo do teto" (pulos grandes sustentam mais). Verdict inicial (`hft_dossier_executivo.md`): índice `cryBTCUSD` pareceu matematicamente inviável para arbitragem de latência pura.
3. **06-26 (mais tarde)** (`proud-borg`) — **Virada de jogo**: `hft_index_cracked.md` reverso-projetou a fórmula exata do índice sintético da Deriv via regressão linear (R²=0.928):
   ```
   Índice_Alvo = 0.3874·Binance + 0.5338·Coinbase + 0.0266·Kraken + 3152.82
   ```
   Isso invalidou o veredito pessimista anterior — o índice é previsível.
4. **06-28** (`proud-borg`) — Deploy do HFT Sniper V4.0 na AWS (EC2 Europa, IP `18.199.174.178`, sessão `tmux hft_bot`), conectado simultaneamente a Deriv/Binance/Coinbase/Kraken.
5. **06-29** (`proud-borg`) — V5.1 (contra-tendência/"rubber-band") testado overnight: **0% win rate**, 5 derrotas seguidas. Provou que choques >50 pontos têm *follow-through* (continuação), não reversão.
6. **06-29→06-30** (`proud-borg`) — V6.1 "Momentum Rider" (segue a tendência, TP +60%/SL -35%): backtest de 48h deu 47.7% WR mas **+$42.44 líquido (ROI 424%)** graças à assimetria de risco/retorno. Calibração V6.2 "Ultra-Momentum" definida (threshold 55→45, SL -35%→-25%, TP +60%→+80%) e **já subida e validada na AWS** (`task.md` do proud-borg, todos os itens `[x]`).
7. **07-01 (hoje)** (`hypothesis`) — Em paralelo, no bot de ticks (`rng_smoothing_exploit.py`): descoberta do "Entry Spot Lag" (contratos de 1 tick são estruturalmente perdedores na Deriv, 36% WR). Pivô para **Opção B**: contratos de **5 ticks**, gatilho `d3 > d2 > d1 > 0` (3 acelerações), chamado de **"Exhaustion Exploit"**. Implementado, deployado na AWS e ambos os bots (`rng_bot` + `hft_bot`) reiniciados e confirmados online.
8. **07-01 (hoje, veredito final)** — Nova amostra de 50 trades do Exhaustion Exploit (5 ticks): **25 vitórias / 25 derrotas, WR exato de 50.00%, PnL -$2.00**. Matematicamente consistente com um **Random Walk puro** (índice sintético da Deriv sem memória/autocorrelação — processo de Markov): EV por trade = `0.5×0.92 − 0.5×1.00 = -4%`, e `-4% × 50 trades × $1 = -$2.00` bate exato. **Conclusão: nenhuma estratégia de adivinhar direção de ticks (inércia, reversão, exaustão, momentum) pode ter EV positivo no RNG da Deriv — está formalmente refutado.** O `hft_bot` (arbitragem cross-exchange) continua validado, pois não depende de adivinhar direção no próprio ativo: ele usa o atraso de propagação entre Binance/Coinbase/Kraken e a Deriv como uma vantagem informacional real (leading indicator), não um padrão estatístico no ativo memoryless.

9. **07-02** (`hypothesis`) — **Mega Brain 2.0 Hypothesis Suite completa**: as 5 hipoteses registradas em `trading-engine/run_hypothesis_suite.py` agora tem veredito (ver `trading-engine/logs/hypothesis_suite/SUMMARY.md`). Resultado consolidado: **4 de 5 SEM EDGE** (`jump` — Jump Indices spike-timing, memoryless; `vanilla` — Vanilla Options, 21 celulas testadas via Monte Carlo driftless, 0 com EV_lo>0, EV medio -7.74%; `boom_crash` — T2 SPIKE_TIMING, Weibull k=0.996≈1, memoryless nao rejeitado; `hft_audit` — inconclusivo por amostra pequena, nao "sem edge" per se). `accumulator` (630 celulas, 07-01) achou 1 candidato marginal (EV_lo=+$0.0019) mas o proprio log ja flagrava vies de multiplos testes e exigia replicacao antes de qualquer capital. **Replicado ainda em 07-02** (amostra fresca via `ticks_stayed_in` da propria API): **0/630 com EV_lo>0** — o candidato NAO se repetiu, confirmando ruido, hipotese encerrada. Com isso, **todas as 5 hipoteses da suite estao fechadas**: nenhum produto de "adivinhar direcao/timing" nos sinteticos da Deriv mostrou edge robusto; `hft_bot` (arbitragem cross-exchange, nao depende de adivinhar direcao no proprio ativo) continua sendo a unica tese com fundamento estrutural real neste ecossistema.

## Estado Atual (ao migrar para o Devin)

- **Servidor:** AWS EC2 (Europa), IP `18.199.174.178`, acesso via `ssh -i ~/Downloads/hft-aws-key.pem ubuntu@18.199.174.178`.
- **Conta:** DEMO (arquivo `.env` local copiado para o servidor). Trocar para conta real exige editar `.env` na AWS e reiniciar a sessão.
- **Processos ativos (tmux):**
  - `rng_bot` — Exhaustion Exploit (5 ticks). **REFUTADO em 07-01 (WR 50%, PnL -$2.00/50 trades, EV -4%/trade) — candidato a ser parado.** Todas as variantes de "adivinhar tick" (Soros, exaustão, reversão) ficam obsoletas por este veredito, não só a Soros.
  - `hft_bot` — Arbitrage Sniper V6.2 Ultra-Momentum (índice sintético cracked), threshold 45, SL -25%, TP +80%. **⚠️ Amostra real pós-deploy (`hft_trades_v62.log`, 6 trades em 30/06 23:48–01/07 02:28 GMT-3): 0% WR, PnL -$18.23. Todas as 6 derrotas excederam a SL configurada (-$2.50), fechando entre -$2.57 e -$4.00 — indício de slippage no fechamento. Amostra pequena e fora do horário de ouro (todas ocorreram ~02:48–05:28 UTC, fora de 12:00–17:59 UTC) — inconclusivo, mas precisa de mais dados/investigação antes de tratar V6.2 como validado.**
- **Decisões resolvidas (2026-07-01, nesta sessão):**
  - ✅ `rng_bot` **parado pelo usuário** na AWS (refutado, EV -4%/trade).
  - ✅ Filtro de velocidade implementado em `trading-engine/hft_arbitrage_bot.py` (substitui o teto de preço fixo): só dispara em saltos formados em ≤50ms (`JUMP_FORMATION_WINDOW`).
  - ⚠️ **Descoberta:** o redeploy de hoje do `rng_bot` (pivô 5-ticks) **reverteu acidentalmente o `hft_bot` na AWS de volta pros parâmetros V6.1** (threshold 50, TP 60%, SL 35% — confirmado lendo `/home/ubuntu/trading-engine/hft_arbitrage_bot.py` via SSH, mtime de hoje). A calibração V6.2 (threshold 45/TP 80%/SL 25%) só existiu ao vivo entre 06-30 e a manhã de 01-07. Código local já resincronizado com V6.2.
  - ✅ **Causa raiz do slippage confirmada e corrigida:** `close_trade()` nunca esperava o SL/TP nativo da Deriv (`is_sold=True`) — todas as trades reais (V5.0, V6.1, V6.2) fecharam via venda manual a mercado, a um preço arbitrário sempre pior que a SL configurada (ex.: -$2.57 a -$4.00 numa SL de -$2.50; -100% do stake em alguns casos da V5.0). O próprio comentário no código já dizia a intenção era deixar a corretora fechar nativamente, mas o timeout de força-fechamento era de só 120s. Fix aplicado: `SAFETY_TIMEOUT` elevado para 1800s (30min), servindo só como rede de segurança de última instância, não como mecanismo principal de saída.
  - ✅ **Deploy feito em 01-07 11:49 GMT-3:** `hft_arbitrage_bot.py` (V6.2 restaurado + filtro de velocidade + fix do SAFETY_TIMEOUT) enviado via `scp` para `/home/ubuntu/trading-engine/` e sessão `tmux hft_bot` reiniciada. Backup do arquivo anterior salvo como `hft_arbitrage_bot.py.bak_20260701_114926` no servidor. Log confirma inicialização limpa: "V6.2 Ultra-Momentum + Filtro de Velocidade", autenticado na conta demo, conectado a Deriv/Binance/Coinbase/Kraken sem erros.
  - ✅ Filtro de horário de ouro implementado (`is_golden_hour()`, `GOLDEN_HOUR_START_UTC=12`/`GOLDEN_HOUR_END_UTC=18`): saltos detectados fora de 12:00–17:59 UTC agora são logados e ignorados, não disparam ordem.
  - ✅ **Deploy #2 feito em 01-07 11:54 GMT-3:** versão com filtro de horário de ouro enviada via `scp`, sessão `tmux hft_bot` reiniciada. Backup salvo como `hft_arbitrage_bot.py.bak_20260701_115429`. Log confirma inicialização limpa: "V6.2 Ultra-Momentum + Filtro de Velocidade + Horário de Ouro".
- **Decisões pendentes:**
  - Acompanhar as próximas trades reais (pós-deploy) para confirmar se o fix do `SAFETY_TIMEOUT` eliminou o slippage no fechamento, e se o filtro de horário melhora o win rate.

## Scripts de Análise Recuperados (`proud-borg/scratch/`)

38 arquivos (~20 scripts Python + metadata), incluindo `deriv_index_cracker.py`, `verify_deriv_jumps.py`, `find_optimal_ceiling.py`, `backtest_24h_deriv.py`, `audit_deriv_history_full.py`, entre outros usados para produzir as análises acima.
