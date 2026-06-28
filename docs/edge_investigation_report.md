# Investigacao de Edge — Oraculo Dinamico (Deriv)

**Branch:** `feat/sniper-lenta` · **Status:** hipotese REFUTADA · **Ferramentas:** `trading-engine/backtest_oracle.py`, `trading-engine/contract_edge_scan.py`

## Veredito (TL;DR)

**Nao existe edge.** A estrategia "Oraculo Dinamico" (DIGITDIFF apos 2 Virtual Losses) e
estatisticamente indistinguivel de apostar em um digito aleatorio, e **todos** os tipos de
contrato da Deriv em indices sinteticos tem EV negativo. A margem da casa esta embutida em
cada payout, matematicamente. A "destruicao" causada por 4 losses seguidos nao foi azar: foi
a media regredindo ao real (~90%) depois de uma sequencia de vitorias por variancia.

## Hipotese testada

> O sinal do Oraculo produziria um win rate **acima do break-even (~91.2%)**, transformando
> o jogo DIGITDIFF (probabilidade base 90%) em positivo.

## Metodo

- **`backtest_oracle.py`** — replay FIEL do `oracle_diff_bot_6`: janela rolante de 1000 ticks,
  recalculo de anomalias por matriz de transicao 10x10 (incremental), maquina de estados de
  Virtual Loss (Sniper Duplo = 2VL) e o skip do tick de settlement. Mede win rate pos-sinal,
  IC95% de Wilson, P[alvo aparecer], e dois controles:
  - **barreira aleatoria** nos mesmos pontos de disparo (se o Oraculo nao vence o dardo, nao ha skill);
  - **baseline sintetico** (RNG uniforme) — se em dados provadamente aleatorios o resultado for
    igual, o algoritmo nao extrai estrutura nenhuma.
- **`contract_edge_scan.py`** — para cada contrato, busca o **payout real ao vivo** (API `proposal`,
  campo `underlying_symbol`) e mede a **probabilidade verdadeira** no historico, extraindo o digito
  pelo **`pip_size` correto** (inferido pela granularidade real dos precos). `EV/$1 = p_win * retorno_bruto - 1`.

> **Fato de API descoberto:** `ticks_history` entrega no maximo **1000 ticks por request** (ignora `count=5000`).

## Resultado 1 — Backtest DIGITDIFF

| Amostra | Disparos | Win rate | IC95% Wilson | P[alvo] | Controle aleatorio |
|---|---|---|---|---|---|
| Sintetico (RNG 500k) | 1.880 | 89.95% | [88.50%, 91.23%] | 10.05% | 90.00% |
| Real combinado (5x 1HZ, 200k ticks) | 739 | **88.77%** | **[86.29%, 90.85%]** | 11.23% | — |

O IC95% real esta **inteiramente abaixo** do break-even (90.91% a 92%, conforme payout 8.7–10%) =
perdedor com **significancia estatistica**. P[alvo]=11.23% > 10% indica que o alvo "inteligente" do
Oraculo aparece **mais** que o acaso (levemente anti-preditivo). Em 4 dos 5 simbolos o Oraculo
**perdeu** para a barreira aleatoria.

## Resultado 2 — Scan de todos os contratos (1HZ10V e R_10)

Todos os 46 contratos testados (DIGITDIFF/MATCH/EVEN/ODD, OVER 0–8, UNDER 1–9, CALL, PUT) deram **EV negativo**:

| Faixa | Exemplos | P_win real | Payout | Taxa da casa |
|---|---|---|---|---|
| ~90% | `DIGITOVER 0`, `DIGITUNDER 9`, `DIGITDIFF` | ~90% | 8.7–9.6% | **~1.3–2%** (menor) |
| ~50% | `EVEN`/`ODD`, `OVER 4`/`UNDER 5`, `CALL`/`PUT` | ~49–50% | 92–95% | ~2–6% |
| ~10% | `DIGITMATCH`, `OVER 8`, `UNDER 1` | ~10% | 730–793% | **~9–18%** (maior) |

**Melhor EV de todos: −1.26%.** A taxa da casa cresce com o payout: quanto mais "longe" a aposta,
maior a mordida.

## O falso edge e o bug de `pip`

O scan inicial acusou `R_10 DIGITEVEN` com **EV +0.0431** (parecia um edge real). Era **artefato de medicao**:
o `pip_size` caiu no default `0.01`, mas o **R_10 tem pip 0.001 (3 casas)**. Com o digito de liquidacao
correto, o falso sinal evapora:

| | pip errado (`*100`) | **pip correto (`0.001`)** |
|---|---|---|
| R_10 chi-quadrado (uniformidade) | 213.62 (nao-uniforme) | **6.24 (uniforme)** |
| R_10 P(even) | 53.41% | **49.91%** |
| R_10 DIGITEVEN EV | +0.0431 (falso) | **−0.0253 (perde)** |

## Bug latente encontrado no bot

`oracle_diff_bot_6.py::extract_last_digit` usa `int(round(price*100))%10` para **todos** os simbolos.
Isso le o **digito errado** em qualquer simbolo com `pip != 0.01` (ex.: R_10, R_25). Nao altera o EV
(o digito verdadeiro tambem e uniforme → 90%), mas e um bug real ao operar esses simbolos.

## Como reproduzir

```bash
# Prova offline (sem rede): Oraculo em RNG uniforme
python backtest_oracle.py --synthetic 500000 --vl 2

# Backtest em ticks reais
python backtest_oracle.py --symbols 1HZ10V,1HZ25V,1HZ50V,1HZ75V,1HZ100V --chunks 40 --vl 2

# Scan de edge por tipo de contrato (payout real x prob verdadeira)
python contract_edge_scan.py --symbols 1HZ10V,R_10 --chunks 40
```

Evidencias brutas: `trading-engine/logs/backtest_big.out`, `logs/contract_scan.out` (pip errado),
`logs/contract_scan2.out` (pip corrigido).

## Implicacao

Indices sinteticos da Deriv sao RNG justo e sem memoria. Nenhuma combinacao de anomalia, Virtual Loss,
juros compostos, janela, simbolo ou tipo de contrato vence uma margem de casa embutida em cada payout.
Qualquer busca por edge precisa migrar para **mercados com estrutura real** (ex.: experimentos de
Binance/forex ja existentes no repo) — e ser validada por estas mesmas ferramentas **antes** de
arriscar capital.
