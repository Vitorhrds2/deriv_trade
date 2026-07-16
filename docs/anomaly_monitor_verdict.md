# Veredito Formal — Anomaly Monitor RNG Sintetico (JOB-2026-07-02-001)

**Data:** 2026-07-16  
**Branch:** `feat/sniper-lenta`  
**Autor:** Carlos Icaro (agente Codex)  
**Status:** ENCERRADO — hipotese refutada, monitor realocado

---

## 1. Job encerrado

| Campo | Valor |
|---|---|
| Job ID | `JOB-2026-07-02-001` |
| Tipo | Anomaly monitor (RNG sintetico Deriv) |
| Inicio | 2026-07-02 |
| Fim | 2026-07-16 (14 dias) |
| Eventos totais | 138 |
| `FEED_STALL` | 135 (ruido infra — interrupcoes de feed) |
| `RNG_RUNS` | 3 (execucoes de analise RNG sem achados) |
| **Klasses de interesse** | **0** (gate minimo = 2) |
| Veredito | **Nao ha anomalia detectavel em RNG sintetico da Deriv** |

## 2. Evidencia que fundamenta o encerramento

### 2.1 Backtest offline (`backtest_oracle.py`)

O backtest replicou fielmente a logica do `oracle_diff_bot_6.py` (janela rolante 1000
ticks, matriz de transicao 10x10, maquina de estados Virtual Loss):

| Amostra | Disparos | Win rate | IC95% Wilson | Controle aleatorio |
|---|---|---|---|---|
| Sintetico (RNG 500k) | 1.880 | 89.95% | [88.50%, 91.23%] | 90.00% |
| Real combinado (5x 1HZ, 200k ticks) | 739 | **88.77%** | **[86.29%, 90.85%]** | — |

O IC95% real esta **inteiramente abaixo** do break-even (90.91%-92%). O alvo
"inteligente" do Oraculo aparece **mais** que o acaso (P[alvo]=11.23% > 10%) —
levemente anti-preditivo.

### 2.2 Scan de contratos (`contract_edge_scan.py`)

Todos os 46 contratos testados (DIGITDIFF/MATCH/EVEN/ODD, OVER 0-8, UNDER 1-9,
CALL, PUT) em `1HZ10V` e `R_10` deram **EV negativo**:

| Faixa | P_win real | Payout | Taxa da casa |
|---|---|---|---|
| ~90% | ~90% | 8.7-9.6% | ~1.3-2% |
| ~50% | ~49-50% | 92-95% | ~2-6% |
| ~10% | ~10% | 730-793% | ~9-18% |

**Melhor EV de todos: -1.26%.** Nenhum mispricing encontrado.

### 2.3 Bug de `pip` como falsa evidencia

O scan inicial acusou `R_10 DIGITEVEN` com EV +0.0431. Era artefato de medicao:
`pip_size` default `0.01` mas R_10 tem pip `0.001`. Com pip correto:
- chi-quadrado: 213.62 -> **6.24 (uniforme)**
- P(even): 53.41% -> **49.91%**
- EV: +0.0431 -> **-0.0253 (perde)**

### 2.4 Conclusao empirica do monitor

14 dias de monitoramento ativo produziram **zero klasses de interesse**. Os 135
`FEED_STALL` sao ruido infra (interrupcoes de WebSocket), nao anomalias de RNG.
Os 3 `RNG_RUNS` rodaram sem encontrar desvio estatistico. **O gate esta corretamente
calibrado** — o problema nao e calibracao, e a ausencia de fenomeno a detectar.

## 3. Por que o gate nunca vai disparar

Indices sinteticos da Deriv sao **RNG justo e sem memoria** por construcao. A
distribuicao de digitos e uniforme (chi-quadrado ~6.24, p>0.7), as transicoes sao
independentes, e a margem da casa esta embutida em cada payout. Nenhuma combinacao
de anomalia, Virtual Loss, janela, simbolo ou tipo de contrato vence isso. Esperar
mais 7 dias (ou 7 meses) nao vai mudar o resultado — e um processo memoryless.

## 4. Realocacao: monitor para mercados com estrutura real

O monitor foi realocado para **Binance** via `trading-engine/anomaly_monitor_real.py`.

### Categorias monitoradas em mercado real

| Klass | O que detecta | Por que so existe em mercado real |
|---|---|---|
| `PRICE_SHOCK` | Salto >= 0.15% em <= 500ms | Microestrutura: ordens grandes, news impact |
| `VOLUME_SPIKE` | Volume 4+ sigma acima da media movel | Fluxo institucional, absorcao de liquidez |
| `SPREAD_WIDEN` | Spread bid-ask 3+ sigma acima da media | Stress de liquidez, risk-off |
| `MOMENTUM_BURST` | 8+ ticks consecutivos na mesma direcao | Cascata de stops, momentum real |
| `FEED_STALL` | Gap > 5s sem update | Ruido infra (controle negativo) |

### Diferenca fundamental

Em RNG sintetico, `PRICE_SHOCK` e `MOMENTUM_BURST` sao eventos iid com probabilidade
fixa — nao ha estrutura para explorar. Em mercado real, esses eventos refletem
**fluxo de ordens, participantes assimetricos e informacao** — exatamente o que
pode gerar edge.

### Uso

```bash
# Monitorar BTC e ETH (ilimitado, relatorio a cada hora)
python anomaly_monitor_real.py --symbols btcusdt,ethusdt --interval 3600

# Rodada de 1h com relatorio a cada 15min
python anomaly_monitor_real.py --symbols btcusdt,ethusdt --duration 3600 --interval 900

# Com log em arquivo
python anomaly_monitor_real.py --symbols btcusdt,ethusdt --log-file anomaly_monitor.log
```

Nao precisa de keys Binance. So usa streams publicos (`bookTicker` + `aggTrade`).

## 5. Edges validados que seguem ativos

| Edge | Status | Onde roda |
|---|---|---|
| D17 token-unlock short | Paper 24/7 na EC2 | systemd d17-sim10k/d17-sim100 |
| Early Sell optionality | Validado (N=50), na EC2 | tmux earlysell |

Estes sao os unicos edges confirmados do repo. O monitor real serve para encontrar
**novos** edges em microestrutura, nao para operar os existentes.

## 6. Referencias

- `docs/edge_investigation_report.md` — relatorio completo da refutacao do Oraculo
- `trading-engine/backtest_oracle.py` — backtest fiel do bot
- `trading-engine/contract_edge_scan.py` — scan de EV por contrato
- `trading-engine/anomaly_monitor_real.py` — novo monitor para mercados reais
