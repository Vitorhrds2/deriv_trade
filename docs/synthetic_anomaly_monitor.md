# Monitor de Anomalias Sinteticas (Deriv)

**Branch:** `feat/synthetic-anomaly-monitor` · **Status:** instrumento ativo (deteccao, sem operar)
**Codigo:** `trading-engine/synthetic_anomaly_monitor.py`, `trading-engine/anomaly_stats.py`
**Testes:** `trading-engine/test_anomaly_stats.py` (10/10), `--selftest` (9/9)

## Por que (TL;DR)

O `edge_investigation_report.md` provou que **nao existe edge de estrutura fixa**: em
regime normal os 46 contratos tem EV negativo (margem da casa no payout). Mas o jackpot
que ja foi explorado uma vez era **transiente** — um mispricing/bug operacional corrigido
em dias. Backtest estatico nao acha isso. Este monitor e o instrumento certo: vigia o feed
**ao vivo** e dispara quando uma janela momentanea fica +EV ou quando o RNG/feed sai da
especificacao. Mesma filosofia que matou o Oraculo, agora apontada para o transiente.

## O que ele vigia

- **`EV_EDGE` (o jackpot):** poll continuo de `proposal` por contrato; payout vira
  `gross_return`. Compara com a probabilidade verdadeira da janela. **So alerta se o
  limite INFERIOR de Wilson de `p_win*payout-1` superar a margem de custo** — a casa
  pagando demais com confianca estatistica.
- **`RNG_BIAS`:** qui-quadrado dos digitos vs. uniforme (df=9). Nomeia o digito anomalo por z-score.
- **`RNG_RUNS`:** teste de corridas no up/down (memoria/reversao).
- **`FEED_FREEZE` / `FEED_TIMING` / `FEED_STALL`:** ticks identicos consecutivos (alerta
  imediato); intervalo medio fora do esperado (~1s para `1HZ*`, ~2s para `R_*`); e
  **silencio total** — nenhum tick por `--stall-timeout`s (default 30s), que delata um WS
  caido. `FEED_STALL` torna VISIVEL a falha que antes deixava o monitor "vivo porem cego"
  (o WS caia com 1011 ping timeout e o monitor seguia batendo heartbeat sem ingerir nada).
- **`SPIKE_TIMING` (Boom/Crash):** cadencia dos spikes vs. especificacao. Cada tick e
  Bernoulli(`p=1/N`) com `N` do nome (`BOOM1000`->1000); testa o gap medio entre spikes
  contra `N` (modelo geometrico). Spike = retorno na direcao do indice acima de
  `SPIKE_MULT`x a mediana do drift. So avalia apos `--min-spikes` spikes.

## Gates anti-variancia (inegociaveis)

- **Persistencia por VIRADA DE JANELA:** anomalia (exceto freeze) so confirma se, desde que
  comecou a aparecer, entrou `--persist-turnover` (default 50%) da janela em ticks NOVOS — e
  emite **1x por episodio**. Contar ciclos seguidos sobre a MESMA janela parada NAO basta:
  foi o que gerou 36 falsos `R_50/DIGITUNDER:4` (a janela de 2000, a ~1 tick/2s, mal mudava
  em 15s, entao uma flutuacao amostral "persistia" trivialmente). `--persistence` vira piso
  secundario de ciclos. Mispricing real de horas/dias passa folgado; blip de minutos morre.
- **Amostra minima:** `--min-samples` antes de qualquer veredito; `--min-spikes` para `SPIKE_TIMING`.
- **Pessimismo:** EV usa o piso do IC, nao a media.
- **Sem cegueira de aquecimento:** `--prime N` pre-carrega as janelas com `N` ticks de
  `ticks_history` no startup, entao os detectores ja avaliam no 1o ciclo (em vez de
  esperar ~`min_samples` ticks ao vivo). `prime=0` usa o valor de `--window`.
- **Evidencia:** todo alerta confirmado vai para `logs/anomaly_monitor/anomalies.jsonl`
  (timestamp ISO + stats) — auditavel, gitignored.
- **Resiliencia de conexao:** o `DerivClient` reconecta sozinho (backoff ate 30s, OTP novo,
  resubscreve os ticks) quando o WS cai; requests pendentes falham rapido em vez de travar.
  O heartbeat mostra `rc=N` (reconexoes) e o watchdog registra `FEED_STALL` uma vez por
  episodio (e avisa no console quando o feed retoma).

## Como rodar

```bash
# Offline, sem rede/credenciais — prova que os detectores funcionam:
python synthetic_anomaly_monitor.py --selftest
python test_anomaly_stats.py

# Ao vivo (DERIV_APP_ID no .env; EV exige DERIV_API_TOKEN), com priming:
python synthetic_anomaly_monitor.py \
  --symbols 1HZ10V,1HZ25V,1HZ50V,1HZ75V,1HZ100V,R_10 \
  --contracts DIGITEVEN,DIGITODD,CALL,PUT,DIGITDIFF:0 --prime 5000

# Cadencia de spikes Boom/Crash (precisa horizonte longo p/ acumular spikes):
python synthetic_anomaly_monitor.py --symbols BOOM1000,CRASH1000,BOOM500 --prime 20000

# So integridade de RNG/feed (sem token, dados publicos):
python synthetic_anomaly_monitor.py --no-token
```

## Protocolo antes de QUALQUER capital

O monitor **nao opera**. Caca e registra. Um `EV_EDGE` so vira aposta se:

1. **Persistir** (varios ciclos) e nao for artefato de um simbolo/contrato isolado.
2. For **confirmado ao vivo** repuxando o `proposal` no instante (payout muda).
3. Sobreviver a **custos reais** (a margem ja inclui buffer; revalidar com stake real).
4. Idealmente, **segundo sinal independente** (ex.: replicar em segunda conexao).

So entao se desenha o executor — em conta demo primeiro, com limite de perda.

## Limites

- `ticks_history` entrega no maximo 1000 ticks/request; o priming pagina para tras pelo tempo.
- `pip_size` correto vem de `active_symbols full` via chave `underlying_symbol`/`pip_size`
  (evita o bug do relatorio); fallback infere de amostra grande.
- **`SPIKE_TIMING` precisa de calibracao antes de capital:** o limiar de spike
  (`SPIKE_MULT=8`x mediana) e generico. Antes de confiar num alarme, valide a contagem
  de spikes contra a frequencia conhecida do indice (em janela longa o gap medio deve
  convergir para `N`); um detector que super-conta enviesa o gap para baixo.
- `SPIKE_TIMING` so e estatisticamente util em horizonte longo: `BOOM1000` rende ~1 spike
  por 1000 ticks, entao `--min-spikes 25` exige dezenas de milhares de ticks (priming ajuda).
- Rate limit da Deriv: ajuste `--ev-interval` e o conjunto de contratos se levar erro.
- A reconexao automatica cobre quedas de WS (o caso observado: 1011 ping timeout). Se o
  socket ficar half-open mas "vivo" (pongs ok, sem ticks), o `FEED_STALL` alarma mas a
  recuperacao depende do `ping_timeout` (45s) derrubar a conexao; em ultimo caso, reinicie.
