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
  Inconclusivo (sem volatilidade). Confirmou custo: round-trip ≈ comissão (~$0.026).
- **Run 2 (3h UTC, mercado ativo, 60 trades, coin-flip aligned/anti):**
  - aligned: n=34, **WR 0%**, P&L médio **−$0.0259**.
  - anti: n=26, **WR 0%**, P&L médio **−$0.0300**.
  - `aligned − anti = +$0.0041/trade`, IC95% **[+0.0000, +0.0082]** (limite inferior encostando em zero → marginal).
  - Decomposição: **captura de lag ≈ $0.002/trade (bruto)** vs **custo ≈ $0.028/trade**.
  - `entry` ≈ Binance − basis (~$26) = **preço de fill FRESCO**, não defasado.

## VEREDITO FINAL — H3 REFUTADA como estratégia lucrativa

O teste de fill decisivo (60 ordens demo, coin-flip aligned/anti) mostra que:

- **O "lag de ~1s" do feed era o artefato de amostragem 1/s.** O preço de **execução
  (entry_spot) é fresco** (segue a Binance ao vivo − basis). Quando reajo a um
  movimento (~1s: detecção + envio da ordem), a Deriv já reprecificou.
- **Existe um micro-edge direcional residual (~$0.002/trade, ~0.002%)**, mas é
  **marginal** (IC95% encosta em zero) e **~14× MENOR que o custo** (~0.028%/round-trip).
- **Todo trade perdeu** (WR 0% nos dois grupos). "aligned > anti" só significa perder
  um pouco menos.

**Mesmo padrão de H1:** micro-sinal real, **sub-custo** → não explorável.

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
- **Não prosseguir com capital real** nesta forma: edge sub-custo.
- O harness fica disponível p/ re-teste em **alta volatilidade extrema** (moves
  $50-100+ frequentes), onde a captura *poderia* superar o custo — mas a barreira
  estrutural (latência de reação ~1s ≈ a defasagem) torna isso improvável.
- Pivotar para a outra frente: **monitor de anomalia transitória no sintético**
  (a tese do usuário: explorar mispricing efêmero antes do patch da Deriv).

## Latência real e viabilidade de VM (EC2/GCE) — diagnóstico

Diagnóstico de rede (de casa, Brasil) — `deriv_rtt_probe.py` + checagem CF/RTT:
- **Deriv atrás de Cloudflare** (`Server: cloudflare`; IPs `104.18.x`/`172.66.x`).
  TCP até a borda CF de SP: **~4ms** — mas o round-trip de **aplicação** (`ping`) é
  **~146ms** → o hop **borda→origem→borda** (origem real da Deriv) é ~140ms.
  **A origem da Deriv é distante** (~70ms one-way de SP).
- **`proposal`: ~178-191ms** round-trip (~146ms rede + **~32ms** de cômputo de preço).
- **Binance em AWS Tóquio** (`ap-northeast-1`); RTT de casa **~275ms** (perna lenta).

Reação total (move→fill): casa ≈ **450ms** (275 sinal + 178 ordem). H3 viu fills
frescos a ~450ms ⇒ **janela 'stale' da Deriv < ~450ms**.

O que uma VM em **AWS Tóquio** muda:
- **Sinal Binance: 275ms → ~1ms** (único ganho grande, co-locada com a Binance).
- **Ordem Deriv: ~178ms → desconhecido** — é o hop CF→origem (origem oculta pela CF);
  de Tóquio pode ser igual ou pior. **Não necessariamente melhora.**
- Reação total ≈ **180ms** (melhor caso).

**Veredito:** VM só vale se a janela stale estiver **entre ~180ms (Tóquio) e ~450ms
(casa)**. Provável que o fill reprecifique fresco (< 180ms) ⇒ nem Tóquio resolve; e
ainda há o **muro da comissão** (~$31/round-trip em $60k) a vencer dentro da janela.

**Teste decisivo barato:** spot AWS `ap-northeast-1` (~centavos/hora), subir o harness
e re-rodar os 60 trades de lá. `aligned_net > 0` ⇒ edge destravado pela latência;
senão H3 morto mesmo co-locado.

## Segurança
- Token do `.env` acessa **demo (DOT) e real (ROT)**. `use_demo=True` + a trava
  garantem operação só na demo. Nunca rodar com a conta real sem decisão explícita.
