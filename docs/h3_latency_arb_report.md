# H3 — Arbitragem de latência cross-venue (Deriv cryBTCUSD × Binance)

**Hipótese:** o feed/preço da Deriv `cryBTCUSD` **atrasa** a Binance BTCUSDT. Se o
preço *transacionável* atrasar de forma explorável, dá pra abrir um multiplicador
na Deriv na direção de um movimento que **já aconteceu** na Binance — arbitragem de
latência (edge **estrutural**, não previsão de mercado).

**Barra de custo (de H1):** comissão medida ~**0.026%/lado** (~0.052% round-trip).
O movimento capturado na janela de defasagem precisa exceder isso.

## Método (3 passos) e ferramentas

| Passo | Script | O que mede |
|---|---|---|
| 1 | `latency_probe.py` | Lead-lag do **feed** (tick Deriv vs Binance) por correlação cruzada de retornos |
| 2 | `exec_lag_probe.py` | Lead-lag do **preço transacionável** (spot do `proposal`) vs Binance |
| 3 | `arb_order_test.py` | **Fill real**: ordem demo cronometrada a um movimento, P&L aligned vs anti |
| aux | `account_check.py` | Validação read-only de conta (`account_type` demo vs real) |

Todos os scripts carregam o `.env` do repo principal e usam `DerivClient(use_demo=True)`.

## Resultados

### Passo 1 — lag do feed (captura 60s)
- Binance 4.5 ticks/s; Deriv **1.01 ticks/s**.
- Correlação cruzada: lag 0 ≈ 0.04; **máx 0.51 em +400ms**. Aparente atraso da Deriv.

### Passo 2 — lag do preço transacionável (180s, 403 proposals)
- **Proposal spot vs Binance:** corr máx **0.31 em +1200ms**.
- Tick vs Binance: corr máx 0.29 em +1000ms.
- O spot do proposal atrasa **≈ igual ao tick** → o `spot` parece ser o próprio tick amostrado a **1/s**.

### Caveat central (não resolvido pela correlação)
A Deriv só atualiza ~**1 tick/s**. Logo, boa parte do "lag de ~1s" é a **taxa de
amostragem**, não necessariamente um atraso *explorável*. A correlação cruzada
**não distingue** "quote genuinamente velho (arbitrável)" de "amostragem 1/s de um
preço que é reprecificado fresco no fill". Só o **teste de fill** decide.

### Passo 3 — teste de fill (ordem demo)
- **Pipeline validado:** trava de conta (confirma DEMO `DOT92172514`, recusa real
  `ROT91014561`), `--live` obrigatório, stake $1, tetos de trades/tempo, fecha posição.
- **Run 1 (5h UTC, mercado morto):** 12 ordens, **0 aligned** (sem movimentos de $20).
  Todos "control" aleatórios: **WR 0%, −$0.0267/trade**, total −$0.32.
- **Confirmação de custo:** em mercado parado, cada round-trip perde **exatamente a
  comissão** (~$0.026 no nocional de $100) — bate com o probe de custo do H1.
- **Inconclusivo para a arb:** sem volatilidade, não há nada defasado para explorar.

## Estado atual

- **Confirmado:** pipeline de ordem demo funciona; trava de conta segura; custo real
  por round-trip ≈ comissão; feed da Deriv atrasa a Binance ~1s (mas confundido com
  amostragem 1/s).
- **Falta (bloqueador = mercado):** o teste de fill decisivo precisa de **janela
  volátil** (movimentos reais na Binance) para disparar trades `aligned`.

## Harness pronto (melhorado)

`arb_order_test.py` agora dispara **todo trade por um movimento real** e faz
**coin-flip aligned vs anti** na mesma condição (A/B que isola o edge do lag,
controlando custo e basis). Veredito: `aligned − anti > 0` e `aligned > 0` = arb real.

**Rodar em horário volátil (ex. abertura US/EU):**
```
python arb_order_test.py --live --stake 1 --mult 100 --hold-s 2 \
  --threshold 25 --max-trades 30 --max-seconds 900
```
Dry-run (valida conta/fluxo sem ordens): omitir `--live`.

## Próximos passos
1. Rodar o Passo 3 melhorado em janela volátil (amostra ≥ 30 trades).
2. Se `aligned − anti > 0` com significância → confirmar com hold/threshold variados.
3. Só então considerar capital real — e mesmo assim, edge limitado pela barra de custo.

## Segurança
- Token do `.env` acessa **demo (DOT) e real (ROT)**. `use_demo=True` + a trava
  garantem operação só na demo. Nunca rodar com a conta real sem decisão explícita.
