# REPORT-20260703 - Champion model investigation

Modelo: `reversal_3tick_minmove020_1HZ10V`

Mercado: Deriv synthetic demo, `1HZ10V`

Contrato: Rise/Fall, 1 tick, stake base USD 1

Arquivos analisados:

- `trading-engine/strategy_tournament_events.jsonl`
- `trading-engine/strategy_tournament_state.json`
- `research_library/data_artifacts/STUDY-2026-07-02-007__hft_demo_execution_ledger/async/JOB-20260702-005/champion_metrics_1000.json`

Data cut final: `2026-07-03T18:42:59Z`

## Resumo executivo

O modelo completou 1000 trades em conta Deriv demo e terminou positivo. Isso valida o modelo como candidato operacional demo, mas nao como edge robusto para aumento agressivo de stake ou real-money.

| Metrica | Valor |
|---|---:|
| Trades | 1000 |
| Wins / Losses | 533 / 467 |
| Win rate | 53.30% |
| Break-even WR estimado | 52.08% |
| Margem sobre break-even | +1.22 p.p. |
| PnL oficial do modelo | +USD 23.36 |
| EV por trade | +USD 0.02336 |
| ROI sobre stake | +2.34% |
| Peak PnL | +USD 45.44 |
| Max drawdown | -USD 23.08 |
| Rejects / errors | 0 / 0 |
| Latencia mediana | 228.363 ms |
| Latencia p95 | 371.584 ms |

Conclusao curta: passou o alvo de 1000 trades positivo, mas a vantagem decaiu muito. O primeiro bloco de 100 trades concentrou +USD 15.20 do resultado; os ultimos 100 trades perderam -USD 13.60. A decisao correta e `collect_more / challenge_candidate`, nao escalar.

## Tese operacional testada

Regra do modelo:

1. Observar o indice `1HZ10V`.
2. Detectar 3 ticks consecutivos na mesma direcao.
3. Exigir deslocamento minimo absoluto de `0.20`.
4. Operar contra o movimento local:
   - movimento para cima -> `PUT`
   - movimento para baixo -> `CALL`
5. Duracao do contrato: 1 tick.
6. Stake base: USD 1.

Interpretacao: fade/reversao de micro-overextension em horizonte de 1 tick.

## Resultado por fases

| Fase | Trades | WR | PnL | EV/trade |
|---|---:|---:|---:|---:|
| Gate inicial 1-100 | 100 | 60.00% | +15.20 | +0.15200 |
| Continuacao 101-1000 | 900 | 52.56% | +8.16 | +0.00907 |
| Apos trade 200 | 800 | 52.00% | -1.28 | -0.00160 |
| Ultimos 100 | 100 | 45.00% | -13.60 | -0.13600 |
| Total 1-1000 | 1000 | 53.30% | +23.36 | +0.02336 |

O recorte mais importante e apos o trade 200: em 800 trades, o modelo ficou levemente negativo. Isso indica que o gate inicial superestimou a qualidade do edge.

## Blocos e regime

| Janela | Melhor bloco | Pior bloco |
|---|---:|---:|
| 30 trades | +12.24, trades 644-673 | -10.80, trades 362-391 |
| 50 trades | +15.28, trades 703-752 | -13.52, trades 342-391 |
| 100 trades | +24.80, trades 703-802 | -17.44, trades 307-406 |

Leitura: o modelo alterna blocos claramente positivos e negativos. Essa foi a motivacao direta para testar filtros de pausa por bloco ruim/quente na wave seguinte.

## Direcao do contrato

| Contrato | Trades | Wins | Losses | WR | PnL | EV/trade |
|---|---:|---:|---:|---:|---:|---:|
| CALL | 510 | 272 | 238 | 53.33% | +12.24 | +0.02400 |
| PUT | 490 | 261 | 229 | 53.27% | +11.12 | +0.02269 |

No total de 1000 trades, `CALL` e `PUT` ficaram muito parecidos. Isso enfraquece a tese de que apenas um lado explica o resultado agregado, mas ainda justifica testar `CALL-only` e `PUT-only` como candidatos separados para controlar blocos negativos.

## Execucao e latencia

| Metrica | Valor |
|---|---:|
| Buys oficiais do modelo | 1000 |
| Settlements oficiais do modelo | 1000 |
| Rejects | 0 |
| Errors/timeouts | 0 |
| Latencia media | 250.391 ms |
| Latencia mediana | 228.363 ms |
| Latencia p95 | 371.584 ms |

Nao ha evidencia de falha de execucao por reject ou timeout. A degradacao de performance parece ligada ao sinal/regime, nao a infraestrutura.

## Incidente operacional

Houve duas interrupcoes relevantes:

- Queda de luz/ambiente local apos o trade 954. O log local marcou `runtime_timeout`, mas a causa operacional informada foi queda de energia. O runner foi retomado como `JOB-20260703-009-CHAMPION-RESUME`.
- Durante a retomada final, um segundo runner temporario (`JOB-20260703-012-CHAMPION-RESUME-980`) abriu um buy duplicado antes de ser encerrado. O contrato `4086317599` perdeu -USD 1.00. Esse contrato foi excluido do PnL oficial do modelo, mas entra na auditoria de conta.

PnL oficial do modelo: `+USD 23.36`.

PnL de auditoria incluindo o contrato orfao: `+USD 22.36`.

## Risco de stake

Com stake USD 1, o max drawdown observado foi -USD 23.08. Escalado linearmente para stake USD 10, o drawdown equivalente seria cerca de -USD 230.80, sem contar efeitos psicologicos, limite de conta, mudanca de payout ou possivel degradacao de execucao.

Como os ultimos 100 trades foram negativos e o pos-200 ficou praticamente flat/negativo, aumento de stake deve ser testado apenas como candidato separado em demo, nunca como promocao direta do campeao.

## Decisao recomendada

Status: `passed_1000_demo_candidate_collect_more`.

O modelo venceu o criterio operacional de 1000 trades positivos em demo, mas nao venceu o criterio de robustez forte. Ele deve ser usado como benchmark a ser batido, nao como estrategia final.

Proximos testes ja encaminhados:

1. Limiar menor que 0.20: `reversal_3tick_minmove016_1HZ10V_w3`.
2. Filtro por direcao: `CALL-only` e `PUT-only`.
3. Aumento de stake em demo: `stake_multiplier=1.5` sobre o default discovery.
4. Filtro anti-blocos: pausa apos blocos recentes muito negativos ou muito positivos.
5. Modelo adaptativo: `adaptive_agent_tick_research_1HZ10V_w3`, com sub-regras explicitas e score de paper-trading por tick.

Real-money continua bloqueado.
