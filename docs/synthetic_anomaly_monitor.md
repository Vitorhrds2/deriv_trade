# Monitor de Anomalias Sinteticas (Deriv)

**Branch:** `feat/synthetic-anomaly-monitor` · **Status:** instrumento ativo (deteccao, sem operar)
**Codigo:** `trading-engine/synthetic_anomaly_monitor.py`, `trading-engine/anomaly_stats.py`
**Testes:** `trading-engine/test_anomaly_stats.py` (9/9), `--selftest` (5/5)

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
- **`FEED_FREEZE` / `FEED_TIMING`:** ticks identicos consecutivos (alerta imediato) e
  intervalo medio fora do esperado (~1s para `1HZ*`, ~2s para `R_*`).

## Gates anti-variancia (inegociaveis)

- **Persistencia:** anomalia (exceto freeze) so confirma apos `--persistence` ciclos seguidos.
  Blip de 1 ciclo nunca confirma; mispricing real de horas/dias confirma rapido.
- **Amostra minima:** `--min-samples` antes de qualquer veredito.
- **Pessimismo:** EV usa o piso do IC, nao a media.
- **Evidencia:** todo alerta confirmado vai para `logs/anomaly_monitor/anomalies.jsonl`
  (timestamp ISO + stats) — auditavel, gitignored.

## Como rodar

```bash
# Offline, sem rede/credenciais — prova que os detectores funcionam:
python synthetic_anomaly_monitor.py --selftest
python test_anomaly_stats.py

# Ao vivo (DERIV_APP_ID no .env; EV exige DERIV_API_TOKEN):
python synthetic_anomaly_monitor.py \
  --symbols 1HZ10V,1HZ25V,1HZ50V,1HZ75V,1HZ100V,R_10 \
  --contracts DIGITEVEN,DIGITODD,CALL,PUT,DIGITDIFF:0

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

- `ticks_history` entrega no maximo 1000 ticks/request (a janela enche ao vivo via stream).
- `pip_size` correto vem de `active_symbols full` (evita o bug `*100` do relatorio); fallback inferido.
- Rate limit da Deriv: ajuste `--ev-interval` e o conjunto de contratos se levar erro.
