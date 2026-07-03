# REPORT-20260703 - Champion model investigation

Modelo: `reversal_3tick_minmove020_1HZ10V`

Mercado: Deriv synthetic demo, `1HZ10V`

Contrato: Rise/Fall, 1 tick, stake base USD 1

Arquivos analisados:

- `trading-engine/strategy_tournament_events.jsonl`
- `trading-engine/strategy_tournament_state.json`

Data cut principal: `2026-07-03T18:02:01Z`

Observacao operacional: o runner do campeao parou apos o trade 954 por queda de luz/ambiente local. O evento em log aparece como `runtime_timeout` em `2026-07-03T13:47:34Z`, mas a causa operacional informada pelo operador foi queda de energia. O runner foi retomado depois como `JOB-20260703-009-CHAMPION-RESUME`.

## Resumo executivo

O modelo passou o gate inicial de 100 trades com resultado muito forte, mas perdeu grande parte da vantagem quando a amostra cresceu. No corte principal de 954 trades, o modelo ainda estava positivo, porem com edge pequeno e instavel.

Numeros principais no corte de 954 trades:

| Metrica | Valor |
|---|---:|
| Trades | 954 |
| Wins / Losses | 511 / 443 |
| Win rate | 53.56% |
| Break-even WR estimado | 52.08% |
| Margem sobre break-even | +1.48 p.p. |
| PnL | +USD 27.12 |
| EV por trade | +USD 0.0284 |
| Peak PnL | +USD 45.44 |
| Max drawdown | -USD 23.08 |
| Rejects / errors | 0 / 0 |
| Latencia mediana | 227.5 ms |
| Latencia p95 | 371.9 ms |

Conclusao curta: o modelo segue positivo, mas a evidencia nao sustenta aumento agressivo de stake. O melhor achado e que existe uma leve inclinacao positiva persistente, mas ela e pequena, intermitente e proxima demais do break-even para decisao forte.

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

| Fase | Trades | WR | PnL | EV/trade | Max DD |
|---|---:|---:|---:|---:|---:|
| Gate inicial 1-100 | 100 | 60.00% | +15.20 | +0.1520 | -7.08 |
| Continuacao 101-954 | 854 | 52.81% | +11.92 | +0.0140 | -23.08 |
| Total 1-954 | 954 | 53.56% | +27.12 | +0.0284 | -23.08 |
| Apos trade 200 | 754 | 52.25% | +2.48 | +0.0033 | -23.08 |

O ponto critico e o recorte apos o trade 200: em 754 trades, o PnL foi apenas +USD 2.48. Isso indica que a performance inicial superestimou a qualidade do edge.

## Rolling windows de 50 trades

| Janela | WR | PnL |
|---|---:|---:|
| 1-50 | 56% | +3.76 |
| 51-100 | 64% | +11.44 |
| 101-150 | 54% | +1.84 |
| 151-200 | 60% | +7.60 |
| 201-250 | 50% | -2.00 |
| 251-300 | 52% | -0.08 |
| 301-350 | 48% | -3.92 |
| 351-400 | 44% | -7.76 |
| 401-450 | 54% | +1.84 |
| 451-500 | 52% | -0.08 |
| 501-550 | 52% | -0.08 |
| 551-600 | 60% | +7.60 |
| 601-650 | 42% | -9.68 |
| 651-700 | 58% | +5.68 |
| 701-750 | 66% | +13.36 |
| 751-800 | 62% | +9.52 |
| 801-850 | 52% | -0.08 |
| 851-900 | 50% | -2.00 |
| 901-950 | 44% | -7.76 |

Leitura: o modelo alterna blocos claramente positivos e blocos claramente negativos. O edge nao e monotonicamente estavel. A performance dos primeiros 100 trades nao foi representativa do comportamento posterior.

## Execucao e latencia

| Metrica | Valor |
|---|---:|
| Signals | 954 |
| Buys | 954 |
| Settlements | 954 |
| Rejects | 0 |
| Errors/timeouts | 0 |
| Latencia media | 250.3 ms |
| Latencia mediana | 227.5 ms |
| Latencia p90 | 283.0 ms |
| Latencia p95 | 371.9 ms |
| Latencia maxima | 1849.1 ms |

Nao ha evidencia de falha de execucao por reject ou timeout. A degradacao de performance parece mais ligada ao sinal/regime do que a infraestrutura.

## Direcao do contrato

| Contrato | Trades | PnL |
|---|---:|---:|
| CALL | 487 | +10.28 |
| PUT | 467 | +16.84 |

Ambas as direcoes ficaram positivas no agregado. Na continuacao, `PUT` carregou a maior parte do PnL, enquanto `CALL` ficou levemente negativo:

| Recorte 101-954 | Trades | PnL |
|---|---:|---:|
| CALL | 442 | -2.32 |
| PUT | 412 | +14.24 |

Hipotese para investigar: a reversao curta pode estar assimetrica por direcao/regime no `1HZ10V`. Um filtro por direcao pode melhorar EV, mas precisa de teste separado para evitar overfit.

## Magnitude do movimento

| Metrica do `abs(move)` | Valor |
|---|---:|
| Media | 0.447 |
| Mediana | 0.420 |
| p90 | 0.670 |

O limiar minimo de `0.20` gera frequencia alta de sinais. O resultado posterior sugere que frequencia alta pode diluir o edge. Variantes com limiar diferente ja foram testadas no discovery, mas ate agora as variantes proximas em outros modelos nao superaram claramente o campeao.

## Risco

Sequencias:

| Metrica | Valor |
|---|---:|
| Maior sequencia de wins | 10 |
| Maior sequencia de losses | 7 |
| Max drawdown | -USD 23.08 |
| Drawdown do pico final | Peak +45.44 para final +27.12 |

Com stake USD 1, o drawdown maximo observado foi toleravel. Se escalado linearmente para stake USD 10, o drawdown equivalente seria aproximadamente -USD 230.80, ignorando mudancas de payout/execucao. Portanto, escalar stake sem novo gate e arriscado.

## Projecao prudente

Usando todos os 954 trades:

- EV/trade: +USD 0.0284
- Taxa ativa observada: cerca de 71 trades/h durante periodos operacionais
- PnL esperado por hora: aproximadamente +USD 2.0/h em stake USD 1

Usando apenas o recorte mais relevante apos o trade 200:

- EV/trade: +USD 0.0033
- PnL esperado por hora: aproximadamente +USD 0.23/h em stake USD 1

Projecao recomendada para decisao: usar o recorte pos-200 como base conservadora, nao os 100 primeiros trades.

## Interpretacao

O modelo encontrou um candidato real em demo, porque:

- executou contratos reais demo na Deriv;
- nao teve reject;
- nao teve timeout de settlement;
- ficou positivo em 954 trades;
- sobreviveu a varias janelas ruins sem quebrar.

Mas o modelo ainda nao deve ser tratado como edge robusto, porque:

- a vantagem caiu de +USD 0.152/trade nos 100 primeiros para +USD 0.014/trade na continuacao;
- apos o trade 200, o EV ficou praticamente zero;
- as janelas de 50 trades alternam entre forte ganho e forte perda;
- a margem sobre break-even e pequena;
- o drawdown cresceu para -USD 23.08 em stake USD 1.

## Decisao recomendada

Status: candidato positivo, nao promovido para stake maior nem real-money.

Gates recomendados antes de qualquer promocao:

1. Completar 1000 trades apos retomada da queda de luz.
2. Registrar `PLATFORMRESULT-*` ou resultado equivalente com o ledger final.
3. Rodar uma segunda sessao independente em conta demo separada.
4. Testar filtro por direcao: `PUT-only`, `CALL-only`, e sem filtro.
5. Testar subfamilia de limiares sem escolher janela vencedora depois.
6. Manter stake USD 1 ate confirmar EV pos-200 em nova amostra.

## Estado apos retomada

O runner foi retomado com:

- job: `JOB-20260703-009-CHAMPION-RESUME`
- trade inicial retomado: 955
- resultado do trade 955: -USD 1.00
- PnL apos retomada imediata: +USD 26.12

Esse trecho deve ser incorporado ao proximo relatorio quando o alvo de 1000 trades for concluido.
