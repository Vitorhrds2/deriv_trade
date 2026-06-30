# Investigação de Arbitragem — Polymarket (delimitação de teses)

**Branch:** `feat/polymarket-arb` · **Status:** teses delimitadas; instrumentos de caça read-only prontos (PA1/PA2 + PA5), não operam
**Código:** `trading-engine/polymarket_arb_probe.py` (PA1/PA2), `trading-engine/polymarket_lag_probe.py` (PA5), `trading-engine/polymarket_arb_stats.py`
**Testes:** `trading-engine/test_polymarket_arb_stats.py` (15/15), `polymarket_arb_probe.py --selftest` (4/4), `polymarket_lag_probe.py --selftest` (4/4)

## De onde vem o método (conhecimento herdado)

Esta investigação reusa, sem exceção, a disciplina das duas frentes anteriores:

- **Synthetic Anomaly Monitor Hunt** (`feat/synthetic-anomaly-monitor`): _hunt do transiente_ — nada de
  edge de estrutura fixa; significância estatística antes de capital; limite **inferior** de Wilson;
  gates anti-variância (persistência por episódio, amostra mínima); toda decisão vira evidência JSONL
  auditável; **o monitor caça e registra, não opera.**
- **AWS H3 Test** (`feat/h1-momentum`, `docs/h3_latency_arb_report.md`): arbitragem cross-venue
  (Deriv×Binance) **REFUTADA mesmo co-locada em Tóquio**. Lições transplantadas: (1) **barra de custo**
  é a régua — micro-edge real porém sub-custo = inexplorável; (2) medir com **profundidade executável**,
  não midpoint; (3) **teste A/B decisivo** (aligned vs anti) isola o edge do custo/basis; (4) **teste
  barato primeiro** antes de qualquer capital.

> Padrão observado nas duas: **micro-sinal real, sub-custo → não explorável.** A pergunta para a Polymarket
> é se a estrutura dela quebra (ou não) esse padrão.

## O que é a Polymarket (estrutura que importa para arbitragem)

- Mercado de previsão **on-chain** (Polygon), liquidação em USDC via **CTF** (Conditional Token Framework).
  Cada condição tem um par de tokens **"YES"/"NO"**; o token que resolve TRUE paga **1 USDC**, o outro 0.
- Negociação por **CLOB** (order book central, off-chain matching + settlement on-chain), com **bid/ask/spread**
  e profundidade reais — não é AMM. Ordens são assinadas (**EIP-712**); o matching **não é atômico** entre
  pernas → toda arbitragem multi-perna carrega risco de execução.
- **Mercados NegRisk** (multi-resultado): um evento-pai com N condições filhas mutuamente exclusivas e
  exaustivas. O flag `negRisk` na ordem roteia para o contrato certo; esquecê-lo **aceita a ordem mas
  falha na liquidação**. A soma dos "YES" deveria ser ≈ 1.
- **Custos (a barra):** taxas de trading historicamente ~0, mas **gás/bridge USDC** (~$3–30/round-trip) e,
  em 2026, relatos de **taker fee ~1.5%**; **capital travado até o resolve** (semanas/meses); resolução
  por **oráculo UMA** (risco de disputa). A barra de custo é configurável no harness (`--taker-rate`,
  `--fixed-cost`) porque ela **muda** e precisa ser re-derivada na sua conta.

## Evidência da literatura (rastreável)

| Fonte | Achado central | Implicação para tese |
|---|---|---|
| Saguillo et al., _Unravelling the Probabilistic Forest_ (arXiv:2508.03474, 2025) | Dois tipos: **Market Rebalancing** (intra-mercado, ΣYES≠1) e **Combinatorial** (cross-mercado). ~**$39.6M** extraídos; top wallet **$2M**; comportamento **bot-like**; "comprar NO" domina. 7.051/17,2K condições com ≥1 oportunidade (mas mediana de soma ~$0.60 = livros rasos/stale). NegRisk: 662/1578 mercados, ~100 ops/mercado, **Sports** domina. Cross-market: ops em **baixa liquidez**, lucro máx ~$100. | PA1/PA2 reais mas **dominados por bots** e concentrados em **livros rasos**; janela curta. |
| Gebele & Matthes (2026), via NexusFi/ResearchGate | 100k+ eventos, 10 venues; **~6%** de eventos co-listados; desvios semânticos persistentes de **2–4%** ("semantic non-fungibility"). | PA4 (cross-venue) tem gap persistente, mas o **risco de regra de resolução** é o assassino. |
| "Basis Risk Arbitrage… Clarity Act" (ResearchGate, 2026) | Par Kalshi-YES + Polymarket-NO: ROI ~5% bruto → **~2.7%** após custo + custo de oportunidade (holding 6,5 meses). | PA4 pode sobreviver ao custo, mas **ROI anualizado** é baixo e depende de equivalência de regra. |
| OffGrid0xDAO, _Cross-Platform Arbitrage_ (6,4M trades) | **29 wallets com >98% WR** em mercados BTC de 5min, operando nos **últimos 15s** usando **Binance como feed grátis**; WR cai a ~50% em movimentos pequenos. H5: divergência de oráculo (Chainlink vs CF Benchmarks). | PA5 é o **descendente direto da H3** — mas aqui a estrutura **favorece** o edge (oposto da Deriv). |
| Practitioners (TradeSignal, PolyMarketsCoil, SimpleFunctions) | Complement arb sniped em **2–7s**, spread <2% em 2026, <0.5% após taxa. Cross-venue: ~80% dos gaps >5c convergem em 1h. | Confirma janela curta e barra de custo apertada. |

## Teses delimitadas (varredura de hipóteses → escopo)

Cada tese tem **gatilho**, **barra de custo**, **o que a refuta** e **teste barato decisivo** — no mesmo
formato das frentes anteriores.

### PA1 — Market Rebalancing intra-condição (YES+NO < 1)
- **Tese:** num binário, comprar YES+NO por < 1 USDC trava lucro risk-free no resolve.
- **Por que defensável:** matematicamente garantida (uma perna paga 1). Existe e foi explorada em escala.
- **O que refuta (provável):** sniped em 2–7s por bots sub-100ms via API pública; gaps quase sempre
  **sub-custo** após taxa/spread/profundidade executável; capital travado até resolve. **Mesmo padrão H1/H3.**
- **Teste decisivo barato:** `polymarket_arb_probe.py` mede net **executável** (anda o livro) com persistência;
  se `net>0` quase nunca persistir, PA1 morre como estratégia de varejo (vira só "monitor que registra").

### PA2 — NegRisk multi-resultado (ΣYES < 1, ou ΣYES > 1 para short)
- **Tese:** em mercados de 3+ resultados, comprar 1 unidade de cada "YES" quando ΣYES < 1 - custo.
- **Por que defensável:** lucro médio máx ~40c/$ na literatura; **bots erram combinações** quando há 5+ pernas;
  Sports é sub-explorado por arbitradores de política. Janela maior que PA1.
- **O que refuta:** execução **não-atômica** em N pernas (uma perna ilíquida quebra tudo); spread acumulado
  das N pernas pode exceder o desconto; capital travado até resolve; esquecer flag `negRisk` falha liquidação.
- **Teste decisivo barato:** rodar o probe sobre o conjunto completo de YES de mercados NegRisk de **Sports
  com 5+ pernas** e **baixa liquidez/novos**; confirmar que `net>0` líquido **persiste** e que a perna mais
  rasa comporta o tamanho (`max_fillable_set`).

### PA3 — Combinatorial cross-mercado (mercados dependentes)
- **Tese:** dois mercados logicamente dependentes (ex.: "ganha voto popular" × "vencedor do voto popular
  ganha a presidência") permitem portfólio hedgeado.
- **Por que defensável:** existe (5 de 11 pares de eleição com extração detectada na literatura).
- **O que refuta:** ops **só em baixa liquidez**, lucro máx ~$100; exige mapear **dependência semântica**
  correta (heurística cara, O(2^(n+m)) ingênuo); risco de regra. **Escopo: nicho, não escalável.**
- **Teste decisivo barato:** `polymarket_arb_stats.combinatorial_edge` sobre pares pré-mapeados; só avançar
  se net > custo **e** a dependência for logicamente exata.

### PA4 — Cross-venue basis arb (Polymarket × Kalshi/PredictIt)
- **Tese:** mesmo evento, venues diferentes; comprar YES barato numa + NO barato noutra somando < 1.
- **Por que defensável:** desvios semânticos **persistentes 2–4%**; ~80% dos gaps >5c convergem em 1h;
  caso Clarity Act dá ~2.7% líquido pós-custo.
- **O que refuta (o assassino):** **mismatch de regra de resolução** (semantic non-fungibility) — o contrato
  pode pagar YES numa venue e NÃO na outra para o "mesmo" evento; **Kalshi cobra ~7% do lucro**; bridge USDC;
  capital travado meses → ROI **anualizado** baixo. **É a H3 reencarnada como cross-venue.**
- **Teste decisivo barato:** aplicar o **método A/B da H3** — só conta como edge se sobreviver a custo de
  **ambas** as venues E a equivalência de regra for verificável; usar `cross_venue_edge` com `fee_b=0.07`.

### PA5 — Latência em mercados curtos de BTC (Polymarket 5/15min × Binance) ⭐
- **Tese:** mercados de BTC de 5–15min na Polymarket resolvem por benchmark de preço; nos **últimos ~15s**,
  o preço **já realizado** na Binance informa o resultado quase deterministicamente. Comprar a perna correta
  enquanto o livro da Polymarket ainda está stale.
- **Por que é a tese mais forte:** é **literalmente a H3**, mas com a estrutura **invertida a favor**: a H3
  morreu porque a Deriv **reprecifica o fill fresco**; aqui o que importa é o **livro CLOB stale** perto do
  settlement, e a evidência on-chain mostra **29 wallets a >98% WR** quando o movimento é grande (>$80).
- **O que refuta / limita:** WR cai a ~50% em movimentos pequenos (sem sinal); concorrência de bots
  co-locados; o gargalo é a **latência da SUA ordem** chegar antes do livro ajustar — exatamente o muro da
  H3 (leg de ordem location-independent). **Risco de oráculo (confirmado na fonte):** o mercado resolve por
  **Chainlink** ("Up se preço BTC no fim ≥ preço no início"), não pela Binance. Binance é só o **sinal grátis**;
  a divergência Binance × Chainlink é basis/oráculo (a H5 da literatura) e entra como ruído/risco.
- **Estrutura ao vivo (verificada via Gamma):** slugs `btc-updown-5m-<epoch>` / `-15m-`; `outcomes=["Up","Down"]`,
  `clobTokenIds=[Up, Down]`; janela = `endDate − horizonte`; novas janelas a cada 5/15min (sempre há mercado vivo).
- **Teste decisivo barato (mapeado da H3) — IMPLEMENTADO em `polymarket_lag_probe.py` (read-only, PAPER):**
  1. **Lead-lag do feed:** `--seconds N` correlaciona retornos Binance × mid do token Up (`cross_corr_profile`,
     análogo a `latency_probe.py`). `lag>0` = Polymarket atrasa = janela stale candidata.
  2. **A/B aligned vs anti** `--paper-ab` nos últimos `--final-s` **só quando |ΔBTC| > `--min-move`**: compra-paper
     o lado implícito pela Binance (aligned) ou o oposto (anti) ao **ask de topo de livro**, settla contra
     begin/close. Veredito: `aligned_net > 0` **e** IC95% de `aligned − anti` **acima de zero** (`boot_diff_ci`).
  3. Se marginal/sub-custo (como na H3), **não prosseguir**. Operar exigiria executor **EIP-712** —
     **fora do escopo** deste instrumento por decisão de projeto (ele mede, não assina ordens).

## Veredito preliminar (a defender com dados)

| Tese | Existe? | Barra principal | Aposta da investigação |
|---|---|---|---|
| PA1 intra-condição | Sim | snipe <7s + taker/spread | **Sub-custo p/ varejo** (vira monitor) |
| PA2 NegRisk 5+ pernas | Sim | exec. não-atômica + lockup | **Marginal**, melhor em Sports/baixa liq. |
| PA3 combinatorial | Sim (nicho) | liquidez + regra semântica | **Não escalável** |
| PA4 cross-venue | Sim | **regra de resolução** + 7% Kalshi | **Marginal**, ROI anual baixo |
| **PA5 latência curto-prazo** | Sim (>98% WR) | **latência da ordem** (muro H3) | **Mais promissora** — testar com método H3 |

**Hipótese diretriz:** a Polymarket repete o padrão Deriv/H3 (micro-edge real, sub-custo) em PA1–PA4, mas
**PA5 pode quebrar o padrão** porque o edge não é "reagir mais rápido que o re-pricing" e sim "explorar um
livro CLOB que fica stale perto do settlement de um evento já decidido na Binance". É exatamente onde a H3
falhou (fill fresco) **invertida**. É aí que vale gastar o teste A/B.

## Como rodar (sem capital)

```bash
cd trading-engine
python test_polymarket_arb_stats.py          # 15/15 — prova a matemática (custo, Wilson, walk-book, A/B, lead-lag)
python polymarket_arb_probe.py --selftest     # 4/4 — prova os gates offline

# Ao vivo (dados PÚBLICOS, sem auth, NÃO opera): conjunto completo de YES de um mercado
python polymarket_arb_probe.py --market-slug <slug> --taker-rate 0.0 --fixed-cost 0.0 --max-runtime 120
# binário simples: passe [YES_token, NO_token]
python polymarket_arb_probe.py --token-ids <YES_ID>,<NO_ID> --persistence 3

# PA5 — latência/staleness em mercados curtos BTC (read-only, PAPER, não opera):
python polymarket_lag_probe.py --selftest                 # 4/4 — prova lead-lag + A/B offline
python polymarket_lag_probe.py --discover btc-updown-5m   # lista as janelas vivas
python polymarket_lag_probe.py --slug <btc-updown-5m-...> --seconds 120 --grid-ms 500   # lead-lag
python polymarket_lag_probe.py --slug <btc-updown-5m-...> --paper-ab --final-s 30 --min-move 10  # A/B paper
```

Evidência confirmada (só o que **persiste** e é **net-positivo** após custo): `logs/polymarket_arb/opportunities.jsonl`.

## Protocolo antes de QUALQUER capital (herdado, inegociável)

1. **Net executável > 0** medido andando o livro (nunca midpoint), com profundidade que comporte o tamanho.
2. **Persistir** por N polls (mata variância/snipe transiente) — evidência JSONL.
3. **Sobreviver à barra de custo real** (taker + gás/bridge + custo de oportunidade do lockup).
4. **Regra de resolução verificável** (PA4) / **dependência lógica exata** (PA3).
5. Para PA5: **A/B aligned vs anti** com IC95% acima de zero, à la H3. Só então desenhar executor (paper primeiro).

> O harness **não assina ordens** de propósito. Caçar e registrar é um passo; armar capital é outro, separado e explícito.

## Próximos passos
- **PA5 (feito o harness):** rodar `polymarket_lag_probe.py --paper-ab` em várias janelas BTC de 5min em
  **horário volátil** (abertura US/EU) e acumular ≥30 paper-trades por grupo; verdito = `aligned_net > 0`
  **e** IC95% de `aligned − anti` acima de zero. Em paralelo, medir a **divergência Binance × Chainlink**
  (basis) — se for da ordem do edge, a tese morre como a H3.
- **PA2:** rodar `polymarket_arb_probe.py` em mercados NegRisk de Sports (5+ pernas, baixa liquidez) com
  `--max-notional` pequeno (topo de livro) para medir frequência/duração de `net>0` real.
- **PA4:** mapear 1–2 pares cross-venue Polymarket×Kalshi com regra de resolução **idêntica** e testar com `cross_venue_edge` (`fee_b=0.07`).

## Segurança
- Tudo aqui é **read-only** sobre APIs **públicas** (Gamma + CLOB), **sem credenciais** e **sem assinar ordens**.
- Operar na Polymarket exige carteira/assinatura EIP-712 — **fora do escopo deste instrumento** por decisão de projeto.
