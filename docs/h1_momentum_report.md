# H1 — Momentum pos-choque (Binance BTC) : sinal real, mas sub-custo

**Branch:** `feat/h1-momentum` · **Status:** hipotese REFUTADA por custo · **Ferramentas:** `trading-engine/realmarket_backtest.py`, `trading-engine/deriv_cost_probe.py`

## Veredito (TL;DR)

Diferente do Oraculo (que nao vencia nem o acaso), o H1 tem um **micro-sinal direcional REAL**:
apos um choque de >=$50 em 500ms, o preco continua na direcao do choque com **EV bruto positivo**
(+0.013% a +0.022% por trade) e **bate o controle nulo**. Mas o sinal e **pequeno demais**: a
**comissao real do multiplicador Deriv (0.0256%/lado, ~0.051% round-trip) e maior que o edge**.
Custo > sinal -> **inviavel**.

## Hipotese

> Apos um choque de >=$50 em <=500ms, o BTC CONTINUA na direcao do choque por ~2s o suficiente
> para lucrar liquido de custos (via multiplicador Deriv cryBTCUSD).

## Metodo (rigor = o mesmo que matou o Oraculo)

- **Simulacao FIEL** (`realmarket_backtest.py`): entrada no **gatilho** (`prices[right]` + latencia),
  hold definido, saida real. (Corrige o furo do `analyze_weekly_sustained.py`, que media a partir do
  inicio da janela, ANTES do choque, inflando o "90%+".)
- **Custos**: comissao + slippage round-trip.
- **Controles**: direcao **aleatoria** (nulo) e **fade** (mean-reversion).
- **Estatistica**: Wilson CI no WR + bootstrap CI no EV/trade.
- **Sweep**: grade threshold x hold x latency (150 configs), decidindo pela premissa PURA (EV bruto).
- **Custo real** (`deriv_cost_probe.py`): comissao do multiplicador via API `proposal` (so cotacao, demo).

## Resultado 1 — Teste fiel de 1 dia (84 gatilhos, 2026-06-26)

| Estrategia | WR | EV/trade | IC95% |
|---|---|---|---|
| momentum | 15.48% | -$3.24 | [-4.15, -2.24] |
| random (nulo) | 11.90% | -$4.26 | [-5.21, -3.33] |
| fade | 8.33% | -$4.76 | [-5.76, -3.85] |

**O "90%+" era artefato.** O WR real do momentum e ~15%, nao 90%+. (O relatorio antigo embutia o
proprio choque de $50 no "lucro", medindo do inicio da janela.)

## Resultado 2 — Sweep (150 configs, EV BRUTO sem custo)

`momentum` tem **EV bruto positivo em todas as configs** (+$0.6 a +$1.78/trade @ mult 800) e **bate o
nulo** em ~$1-2.5/trade. Sinal direcional real. Melhor: thr=50, hold=5000ms, lat=50ms -> bruto +$1.78.
Convertendo em movimento (independe do multiplicador): **edge ~0.013% (realista) a 0.022% (melhor caso)**.

## Resultado 3 — Custo real do multiplicador (cryBTCUSD)

| Mult | Comissao | % do nocional | Round-trip |
|---|---|---|---|
| 100 | $0.26 | 0.0260% | 0.052% |
| 200 | $0.51 | 0.0255% | 0.051% |
| 300 | $0.77 | 0.0257% | 0.051% |

(Multiplicadores validos: 100, 200, 300, 500, 800.) **Comissao real ~0.0256%/lado.**

## Confronto final

| | valor |
|---|---|
| Edge bruto realista | ~0.0128%/trade |
| Edge bruto melhor caso | ~0.0223%/trade |
| **Comissao Deriv (1 lado)** | **0.0256%/trade** |

Mesmo na leitura mais generosa (comissao de um lado, sem round-trip, sem slippage, sem basis
cross-venue Binance->Deriv), **0.0256% > 0.0223%**: a comissao sozinha ja supera o melhor edge.
Na leitura realista, o custo round-trip (0.051%) e **~4x** o edge. **OOS dispensado**: o teto de
custo sozinho refuta.

## Como reproduzir

```bash
# Teste fiel de 1 dia
python realmarket_backtest.py --symbol BTCUSDT --start 2026-06-26 --days 1

# Sweep de parametros (usa cache, sem novo download)
python realmarket_backtest.py --symbol BTCUSDT --start 2026-06-26 --days 1 --sweep

# Custo real do multiplicador Deriv (so cotacao, demo)
python deriv_cost_probe.py
```

## Implicacao

O micro-momentum existe e foi medido com precisao, mas e estruturalmente menor que os custos de
transacao acessiveis (comissao Deriv ~0.026%/lado; taker Binance futures ~0.04%). Estrategias de
captura de movimento <0.05% por evento nao pagam custo em nenhuma venue acessivel. Qualquer proxima
hipotese precisa de um **edge bruto por evento bem maior que ~0.05%** para ter chance liquida.
